from __future__ import annotations

import asyncio
import hashlib
import json
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from scenara.platform.audit import AuditLogger
from scenara.platform.media_batch import MediaInput, inspect_media
from scenara.platform.model_runtime import RuntimeModelBinding, runtime_binding_scope
from scenara.platform.models import (
    TERMINAL_RUN_STATUSES,
    CreateMediaSourceRequest,
    CreateRunRequest,
    MediaAsset,
    MediaKind,
    MediaSource,
    MediaSourceProbe,
    MediaTechnicalMetadata,
    MediaUnitResult,
    ObjectRetentionRecord,
    PipelineRef,
    PipelineStatus,
    PrincipalContext,
    ResultEnvelope,
    ResultReference,
    RunEvent,
    RunRecord,
    RunStatus,
)
from scenara.platform.network import validate_external_url
from scenara.platform.objects import ObjectStore
from scenara.platform.pipeline import (
    DomainUnavailable,
    ExecutionContext,
    ExecutionControl,
    ExecutionInterrupted,
    PipelineDefinition,
    PipelineError,
    PipelineRegistry,
)
from scenara.platform.policy import PolicyProvider, require_allowed
from scenara.platform.queue import RunQueue
from scenara.platform.secrets import SecretStore
from scenara.platform.store import StateConflict, StateStore


class ResourceNotFound(RuntimeError):
    pass


class InvalidTransition(RuntimeError):
    pass


class ExecutionStopped(ExecutionInterrupted):
    pass


class ActiveModelResolver(Protocol):
    async def active_runtime_bindings(
        self,
        tenant_id: str,
        project_id: str,
    ) -> dict[str, RuntimeModelBinding]: ...


@dataclass(frozen=True, slots=True)
class CreateRunOutcome:
    run: RunRecord
    created: bool


class RunService:
    def __init__(
        self,
        *,
        state: StateStore,
        objects: ObjectStore,
        queue: RunQueue,
        pipelines: PipelineRegistry,
        secrets: SecretStore,
        audit: AuditLogger,
        policy: PolicyProvider,
        max_image_bytes: int,
        max_media_bytes: int,
        max_media_units: int,
        media_sample_interval_ms: int,
        result_shard_units: int,
        raw_media_retention_days: int,
        preview_retention_days: int,
        structured_result_retention_days: int,
        production: bool,
        allow_private_media_sources: bool = False,
        active_model_resolver: ActiveModelResolver | None = None,
    ) -> None:
        self.state = state
        self.objects = objects
        self.queue = queue
        self.pipelines = pipelines
        self.secrets = secrets
        self.audit = audit
        self.policy = policy
        self.max_image_bytes = max_image_bytes
        self.max_media_bytes = max_media_bytes
        self.max_media_units = max_media_units
        self.media_sample_interval_ms = media_sample_interval_ms
        self.result_shard_units = result_shard_units
        self.raw_media_retention_days = raw_media_retention_days
        self.preview_retention_days = preview_retention_days
        self.structured_result_retention_days = structured_result_retention_days
        self.production = production
        self.allow_private_media_sources = allow_private_media_sources
        self.active_model_resolver = active_model_resolver
        self.queue.set_handler(self.execute_run)

    async def create_asset(
        self,
        context: PrincipalContext,
        *,
        data: bytes,
        filename: str | None,
        content_type: str,
        kind: MediaKind,
        temporary: bool = False,
    ) -> MediaAsset:
        await require_allowed(self.policy, context, "create", "media_asset", {"kind": kind.value})
        if not data:
            raise ValueError("media asset is empty")
        if len(data) > self.max_media_bytes:
            raise ValueError(f"media exceeds {self.max_media_bytes} bytes")
        if kind == MediaKind.IMAGE and len(data) > self.max_image_bytes:
            raise ValueError(f"image exceeds {self.max_image_bytes} bytes")
        if kind == MediaKind.STREAM:
            raise ValueError("stream inputs must be registered as media sources")
        media_input = MediaInput(
            kind=kind,
            content_type=content_type,
            data=data,
            filename=filename,
        )
        try:
            raw_metadata, preview_data = await asyncio.to_thread(inspect_media, media_input)
            metadata = MediaTechnicalMetadata.model_validate(raw_metadata)
        except PipelineError as exc:
            raise ValueError(f"invalid {kind.value} media: {exc}") from exc
        asset_id = f"ast_{uuid4().hex}"
        object_key = f"tenants/{context.tenant_id}/projects/{context.project_id}/assets/{asset_id}/original"
        preview_key = f"tenants/{context.tenant_id}/projects/{context.project_id}/assets/{asset_id}/preview.jpg"
        now = time.time()
        retention_days = 1 if temporary else self.raw_media_retention_days
        asset = MediaAsset(
            asset_id=asset_id,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            kind=kind,
            filename=filename,
            content_type=content_type or "application/octet-stream",
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            object_key=object_key,
            preview_object_key=preview_key,
            preview_content_type="image/jpeg",
            preview_sha256=hashlib.sha256(preview_data).hexdigest(),
            metadata=metadata,
            temporary=temporary,
            created_at=now,
            expires_at=now + retention_days * 86_400,
        )
        await self.objects.put(object_key, data, asset.content_type)
        try:
            await self.objects.put(preview_key, preview_data, "image/jpeg")
        except Exception:
            with suppress(Exception):
                await self.objects.delete(object_key)
            raise
        stored: MediaAsset | None = None
        tracked_keys: list[str] = []
        try:
            stored = await self.state.create_asset(asset)
            await self.state.track_object(
                ObjectRetentionRecord(
                    tenant_id=context.tenant_id,
                    project_id=context.project_id,
                    object_key=object_key,
                    category="raw_media",
                    owner_type="media_asset",
                    owner_id=asset_id,
                    created_at=now,
                    expires_at=asset.expires_at,
                )
            )
            tracked_keys.append(object_key)
            await self.state.track_object(
                ObjectRetentionRecord(
                    tenant_id=context.tenant_id,
                    project_id=context.project_id,
                    object_key=preview_key,
                    category="preview",
                    owner_type="media_asset",
                    owner_id=asset_id,
                    created_at=now,
                    expires_at=now + self.preview_retention_days * 86_400,
                )
            )
            tracked_keys.append(preview_key)
            await self.policy.consume(context, "media_bytes", len(data), {"asset_id": asset_id})
            await self.audit.record(
                context,
                action="media.asset.create",
                resource_type="media_asset",
                resource_id=asset_id,
                evidence={"kind": kind.value, "size_bytes": len(data), "sha256": asset.sha256},
            )
            return stored
        except Exception:
            if tracked_keys:
                with suppress(Exception):
                    await self.state.mark_objects_deleted(tracked_keys, time.time())
            if stored is not None:
                with suppress(Exception):
                    await self.state.delete_asset(context.tenant_id, context.project_id, asset_id)
            with suppress(Exception):
                await self.objects.delete(object_key)
            with suppress(Exception):
                await self.objects.delete(preview_key)
            raise

    async def sync_pipeline_catalog(self) -> list[PipelineDefinition]:
        for pipeline in self.pipelines.pipelines():
            await self.state.register_pipeline_definition(pipeline)
        return await self.state.list_pipeline_definitions()

    async def pipeline_definition(
        self,
        pipeline_id: str,
        version: str,
        *,
        active_only: bool = True,
    ) -> PipelineDefinition:
        await self.sync_pipeline_catalog()
        persisted = await self.state.get_pipeline_definition(pipeline_id, version)
        if persisted is None:
            raise PipelineError(f"pipeline not found: {pipeline_id}@{version}")
        compiled = self.pipelines.pipeline(pipeline_id, version, active_only=False)
        if compiled.definition_sha256 != persisted.definition_sha256:
            raise PipelineError("persisted pipeline does not match the installed implementation")
        if active_only and persisted.status != PipelineStatus.ACTIVE:
            raise PipelineError(f"pipeline is not active: {pipeline_id}@{version}")
        return persisted

    async def resolve_pipeline_ref(self, pipeline_id: str, version: str | None = None) -> PipelineRef:
        if version is None:
            active = [
                pipeline
                for pipeline in await self.sync_pipeline_catalog()
                if pipeline.pipeline_id == pipeline_id and pipeline.status == PipelineStatus.ACTIVE
            ]
            if len(active) != 1:
                raise PipelineError(f"pipeline must have exactly one active version: {pipeline_id}")
            version = active[0].version
        await self.pipeline_definition(pipeline_id, version)
        return PipelineRef(pipeline_id=pipeline_id, version=version)

    async def transition_pipeline(
        self,
        context: PrincipalContext,
        pipeline_id: str,
        version: str,
        target: PipelineStatus,
    ) -> PipelineDefinition:
        await require_allowed(
            self.policy,
            context,
            "transition",
            "pipeline",
            {"pipeline_id": pipeline_id, "version": version, "target": target.value},
        )
        await self.sync_pipeline_catalog()
        persisted = await self.state.get_pipeline_definition(pipeline_id, version)
        if persisted is None:
            raise PipelineError(f"pipeline not found: {pipeline_id}@{version}")
        compiled = self.pipelines.pipeline(pipeline_id, version, active_only=False)
        if persisted.definition_sha256 != compiled.definition_sha256:
            raise PipelineError("persisted pipeline does not match the installed implementation")
        updated = await self.state.transition_pipeline_definition(pipeline_id, version, target)
        await self.audit.record(
            context,
            action="pipeline.transition",
            resource_type="pipeline",
            resource_id=f"{pipeline_id}@{version}",
            evidence={"from": persisted.status.value, "to": target.value},
        )
        return updated

    async def get_asset_preview(self, context: PrincipalContext, asset_id: str) -> tuple[bytes, str]:
        await require_allowed(self.policy, context, "read", "media_asset", {"asset_id": asset_id})
        asset = await self.state.get_asset(context.tenant_id, context.project_id, asset_id)
        if asset is None or asset.deleted_at is not None or asset.preview_object_key is None:
            raise ResourceNotFound("media asset preview not found")
        return await self.objects.get(asset.preview_object_key), asset.preview_content_type or "image/jpeg"

    async def delete_asset(self, context: PrincipalContext, asset_id: str) -> None:
        await require_allowed(self.policy, context, "delete", "media_asset", {"asset_id": asset_id})
        asset = await self.state.get_asset(context.tenant_id, context.project_id, asset_id)
        if asset is None:
            raise ResourceNotFound("media asset not found")
        runs = await self.state.list_runs(context.tenant_id, context.project_id)
        if any(item.asset_id == asset_id and item.status not in TERMINAL_RUN_STATUSES for item in runs):
            raise StateConflict("media asset has a non-terminal run")
        await self.audit.record(
            context,
            action="media.asset.delete",
            resource_type="media_asset",
            resource_id=asset_id,
            evidence={"sha256": asset.sha256, "object_key": asset.object_key},
        )
        object_keys = [asset.object_key]
        if asset.preview_object_key is not None:
            object_keys.append(asset.preview_object_key)
        for object_key in object_keys:
            await self.objects.delete(object_key)
        await self.state.mark_objects_deleted(object_keys, time.time())
        await self.state.delete_asset(context.tenant_id, context.project_id, asset_id)

    async def create_source(
        self,
        context: PrincipalContext,
        request: CreateMediaSourceRequest,
    ) -> MediaSource:
        await require_allowed(self.policy, context, "create", "media_source")
        await validate_external_url(
            request.url,
            allowed_schemes=frozenset({"rtsp", "rtmp", "http", "https"}),
            allow_private=self.allow_private_media_sources,
            allow_credentials=True,
        )
        parsed = urlsplit(request.url)
        if parsed.scheme.lower() not in {"rtsp", "rtmp", "http", "https"} or not parsed.hostname:
            raise ValueError("source URL must use rtsp, rtmp, http, or https")
        source_id = f"src_{uuid4().hex}"
        host = parsed.hostname
        if parsed.port:
            host = f"{host}:{parsed.port}"
        masked_url = urlunsplit((parsed.scheme, host, parsed.path, "", ""))
        source = MediaSource(
            source_id=source_id,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            name=request.name,
            masked_url=masked_url,
            secret_ref=f"secret://media-sources/{source_id}",
            metadata=request.metadata,
            created_at=time.time(),
        )
        await self.secrets.put(source.secret_ref, request.url)
        stored: MediaSource | None = None
        try:
            stored = await self.state.create_source(source)
            await self.audit.record(
                context,
                action="media.source.create",
                resource_type="media_source",
                resource_id=source_id,
                evidence={"scheme": parsed.scheme.lower(), "host": host},
            )
            return stored
        except Exception:
            if stored is not None:
                with suppress(Exception):
                    await self.state.delete_source(context.tenant_id, context.project_id, source_id)
            with suppress(Exception):
                await self.secrets.delete(source.secret_ref)
            raise

    async def get_source(self, context: PrincipalContext, source_id: str) -> MediaSource:
        await require_allowed(self.policy, context, "read", "media_source", {"source_id": source_id})
        source = await self.state.get_source(context.tenant_id, context.project_id, source_id)
        if source is None:
            raise ResourceNotFound("media source not found")
        return source

    async def delete_source(self, context: PrincipalContext, source_id: str) -> None:
        await require_allowed(self.policy, context, "delete", "media_source", {"source_id": source_id})
        source = await self.state.get_source(context.tenant_id, context.project_id, source_id)
        if source is None:
            raise ResourceNotFound("media source not found")
        runs = await self.state.list_runs(context.tenant_id, context.project_id)
        if any(item.source_id == source_id and item.status not in TERMINAL_RUN_STATUSES for item in runs):
            raise StateConflict("media source has a non-terminal run")
        await self.audit.record(
            context,
            action="media.source.delete",
            resource_type="media_source",
            resource_id=source_id,
            evidence={"masked_url": source.masked_url},
        )
        await self.state.delete_source(context.tenant_id, context.project_id, source_id)
        await self.secrets.delete(source.secret_ref)

    async def probe_source(
        self,
        context: PrincipalContext,
        source_id: str,
        *,
        timeout_ms: int = 10_000,
    ) -> MediaSourceProbe:
        source = await self.get_source(context, source_id)
        await require_allowed(self.policy, context, "execute", "media_source", {"source_id": source_id})
        source_url = await self.secrets.get(source.secret_ref)
        await validate_external_url(
            source_url,
            allowed_schemes=frozenset({"rtsp", "rtmp", "http", "https"}),
            allow_private=self.allow_private_media_sources,
            allow_credentials=True,
        )
        started = time.perf_counter()
        try:
            raw_metadata, _preview = await asyncio.wait_for(
                asyncio.to_thread(
                    inspect_media,
                    MediaInput(kind=MediaKind.STREAM, content_type="application/octet-stream", source_url=source_url),
                ),
                timeout=timeout_ms / 1000 + 1,
            )
        except TimeoutError as exc:
            raise ValueError("media source probe timed out") from exc
        probe = MediaSourceProbe(
            source_id=source_id,
            reachable=True,
            latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
            metadata=MediaTechnicalMetadata.model_validate(raw_metadata),
            checked_at=time.time(),
        )
        await self.audit.record(
            context,
            action="media.source.probe",
            resource_type="media_source",
            resource_id=source_id,
            evidence={"reachable": True, "latency_ms": probe.latency_ms},
        )
        return probe

    async def create_run(
        self,
        context: PrincipalContext,
        request: CreateRunRequest,
        *,
        idempotency_key: str,
    ) -> CreateRunOutcome:
        if not idempotency_key or len(idempotency_key) > 128:
            raise ValueError("Idempotency-Key is required and must not exceed 128 characters")
        if (request.asset_id is None) == (request.source_id is None):
            raise ValueError("exactly one of asset_id or source_id is required")
        await require_allowed(
            self.policy,
            context,
            "create",
            "run",
            {"domain": request.domain, "pipeline_id": request.pipeline.pipeline_id},
        )
        pipeline = await self.pipeline_definition(request.pipeline.pipeline_id, request.pipeline.version)
        if pipeline.domain != request.domain:
            raise ValueError("requested domain does not match pipeline domain")
        self.pipelines.validate_run_parameters(pipeline, request.parameters)
        if request.asset_id:
            asset = await self.state.get_asset(context.tenant_id, context.project_id, request.asset_id)
            if asset is None or asset.deleted_at is not None or asset.original_deleted_at is not None:
                raise ResourceNotFound("media asset not found")
        else:
            source = await self.state.get_source(context.tenant_id, context.project_id, request.source_id or "")
            if source is None:
                raise ResourceNotFound("media source not found")
        now = time.time()
        run = RunRecord(
            run_id=f"run_{uuid4().hex}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            principal_id=context.principal_id,
            domain=request.domain,
            pipeline=request.pipeline,
            asset_id=request.asset_id,
            source_id=request.source_id,
            parameters=request.parameters,
            priority=request.priority,
            created_at=now,
            updated_at=now,
        )
        request_hash = hashlib.sha256(request.model_dump_json().encode("utf-8")).hexdigest()
        stored, created = await self.state.create_run_idempotent(
            run,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        if created:
            try:
                await self.policy.consume(
                    context,
                    "runs",
                    1,
                    {"domain": request.domain, "pipeline_id": request.pipeline.pipeline_id},
                )
                await self.audit.record(
                    context,
                    action="run.create",
                    resource_type="run",
                    resource_id=stored.run_id,
                    evidence={"domain": request.domain, "pipeline": request.pipeline.model_dump()},
                )
            except Exception:
                with suppress(Exception):
                    await self.state.delete_run(context.tenant_id, context.project_id, stored.run_id)
                raise
            await self._event(stored, "run.queued")
            try:
                await self.queue.enqueue(stored)
            except Exception as exc:
                stored = await self._set_status(
                    stored,
                    RunStatus.FAILED,
                    error_code="QUEUE_UNAVAILABLE",
                    termination_reason=str(exc)[:500],
                    completed_at=time.time(),
                )
        if request.wait_ms:
            stored = await self.wait(context, stored.run_id, request.wait_ms)
        return CreateRunOutcome(run=stored, created=created)

    async def wait(self, context: PrincipalContext, run_id: str, wait_ms: int) -> RunRecord:
        deadline = asyncio.get_running_loop().time() + wait_ms / 1000
        while asyncio.get_running_loop().time() < deadline:
            run = await self._get_run(context, run_id)
            if run.status in TERMINAL_RUN_STATUSES:
                return run
            await asyncio.sleep(0.02)
        return await self._get_run(context, run_id)

    async def get_run(self, context: PrincipalContext, run_id: str) -> RunRecord:
        await require_allowed(self.policy, context, "read", "run", {"run_id": run_id})
        return await self._get_run(context, run_id)

    async def _get_run(self, context: PrincipalContext, run_id: str) -> RunRecord:
        run = await self.state.get_run(context.tenant_id, context.project_id, run_id)
        if run is None:
            raise ResourceNotFound("run not found")
        return run

    async def list_runs(
        self,
        context: PrincipalContext,
        *,
        status: RunStatus | None = None,
        domain: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[RunRecord], int]:
        await require_allowed(self.policy, context, "list", "run")
        rows = await self.state.list_runs(context.tenant_id, context.project_id)
        if status is not None:
            rows = [item for item in rows if item.status == status]
        if domain is not None:
            rows = [item for item in rows if item.domain == domain]
        return rows[offset : offset + limit], len(rows)

    async def result(self, context: PrincipalContext, run_id: str) -> ResultEnvelope:
        await require_allowed(self.policy, context, "read", "run", {"run_id": run_id})
        await self._get_run(context, run_id)
        reference = await self.state.get_result_reference(context.tenant_id, context.project_id, run_id)
        if reference is None:
            raise ResourceNotFound("run result is not available")
        document = await self.objects.get(reference.object_key)
        if hashlib.sha256(document).hexdigest() != reference.sha256:
            raise PipelineError("stored result checksum does not match its database reference")
        result = ResultEnvelope.model_validate_json(document)
        if reference.shard_keys:
            if len(reference.shard_keys) != len(reference.shard_sha256):
                raise PipelineError("stored result shard manifest is invalid")
            units: list[MediaUnitResult] = []
            for object_key, expected_sha256 in zip(
                reference.shard_keys,
                reference.shard_sha256,
                strict=True,
            ):
                shard = await self.objects.get(object_key)
                if hashlib.sha256(shard).hexdigest() != expected_sha256:
                    raise PipelineError("stored result shard checksum does not match its reference")
                payload = json.loads(shard)
                if not isinstance(payload, list):
                    raise PipelineError("stored result shard is not a unit list")
                units.extend(MediaUnitResult.model_validate(item) for item in payload)
            if len(units) != reference.unit_count:
                raise PipelineError("stored result shard count does not match its reference")
            result = result.model_copy(update={"units": units}, deep=True)
        return result

    async def transition(self, context: PrincipalContext, run_id: str, action: str) -> RunRecord:
        await require_allowed(self.policy, context, action, "run", {"run_id": run_id})
        for _ in range(4):
            run = await self._get_run(context, run_id)
            pipeline = await self.pipeline_definition(
                run.pipeline.pipeline_id,
                run.pipeline.version,
                active_only=False,
            )
            if action == "pause":
                if not pipeline.pausable:
                    raise InvalidTransition("this pipeline does not support pause")
                if run.status != RunStatus.RUNNING:
                    raise InvalidTransition("only a running run can be paused")
                target = RunStatus.PAUSING
            elif action == "resume":
                if run.status != RunStatus.PAUSED:
                    raise InvalidTransition("only a paused run can be resumed")
                target = RunStatus.RUNNING
            elif action == "cancel":
                if run.status in TERMINAL_RUN_STATUSES:
                    raise InvalidTransition("a terminal run cannot be cancelled")
                if run.status == RunStatus.CANCELLING:
                    return run
                target = RunStatus.CANCELLING
            else:
                raise ValueError("unknown lifecycle action")
            updated = run.model_copy(update={"status": target, "updated_at": time.time()})
            try:
                saved = await self.state.save_run(updated, expected_revision=run.revision)
                await self.audit.record(
                    context,
                    action=f"run.{action}",
                    resource_type="run",
                    resource_id=run_id,
                    evidence={"status": target.value},
                )
                await self._event(saved, f"run.{target.value}")
                return saved
            except StateConflict:
                continue
        raise StateConflict("run transition could not be applied")

    async def execute_run(self, tenant_id: str, project_id: str, run_id: str) -> None:
        run = await self.state.get_run(tenant_id, project_id, run_id)
        if run is None:
            raise ResourceNotFound("queued run does not exist")
        if run.status in TERMINAL_RUN_STATUSES:
            return
        try:
            run = await self._begin_execution(run)
            if run.status == RunStatus.CANCELLED:
                return
            data: bytes | None = None
            source_url: str | None = None
            filename: str | None = None
            content_type = "application/octet-stream"
            if run.asset_id:
                asset = await self.state.get_asset(run.tenant_id, run.project_id, run.asset_id)
                if asset is None or asset.deleted_at is not None or asset.original_deleted_at is not None:
                    raise ResourceNotFound("media asset disappeared before execution")
                data = await self.objects.get(asset.object_key)
                media_kind = asset.kind
                filename = asset.filename
                content_type = asset.content_type
            else:
                source = await self.state.get_source(run.tenant_id, run.project_id, run.source_id or "")
                if source is None:
                    raise ResourceNotFound("media source disappeared before execution")
                source_url = await self.secrets.get(source.secret_ref)
                await validate_external_url(
                    source_url,
                    allowed_schemes=frozenset({"rtsp", "rtmp", "http", "https"}),
                    allow_private=self.allow_private_media_sources,
                    allow_credentials=True,
                )
                media_kind = MediaKind.STREAM
            pipeline = await self.pipeline_definition(
                run.pipeline.pipeline_id,
                run.pipeline.version,
                active_only=False,
            )
            model_bindings = (
                await self.active_model_resolver.active_runtime_bindings(run.tenant_id, run.project_id)
                if self.active_model_resolver is not None
                else {}
            )
            context = ExecutionContext(
                run_id=run.run_id,
                tenant_id=run.tenant_id,
                project_id=run.project_id,
                pipeline_id=run.pipeline.pipeline_id,
                pipeline_version=run.pipeline.version,
                asset_id=run.asset_id,
                source_id=run.source_id,
                filename=filename,
                content_type=content_type,
                production=self.production,
                model_bindings=model_bindings,
            )

            checkpoint_run: RunRecord = run

            async def checkpoint() -> None:
                await self._checkpoint(checkpoint_run, context.control)

            parameters = {
                "max_units": self.max_media_units,
                "sample_interval_ms": self.media_sample_interval_ms,
                **run.parameters,
            }
            with runtime_binding_scope(model_bindings):
                result = await self.pipelines.execute(
                    pipeline,
                    context,
                    {
                        "$media.bytes": data or b"",
                        "$media.input": MediaInput(
                            kind=media_kind,
                            content_type=content_type,
                            data=data,
                            source_url=source_url,
                            filename=filename,
                        ),
                    },
                    parameters,
                    checkpoint,
                )
            if not isinstance(result, ResultEnvelope):
                raise PipelineError("pipeline did not return a ResultEnvelope")
            await self._store_result(run, result)
            latest = await self.state.get_run(run.tenant_id, run.project_id, run.run_id)
            if latest is None:
                raise ResourceNotFound("run disappeared during execution")
            worker_context = PrincipalContext(
                tenant_id=run.tenant_id,
                project_id=run.project_id,
                principal_id=run.principal_id,
            )
            await self.audit.record(
                worker_context,
                action="run.complete",
                resource_type="run",
                resource_id=run.run_id,
                evidence={"unit_count": len(result.units), "domain": result.domain},
            )
            media_termination = next(
                (
                    warning.removeprefix("media_termination:")
                    for warning in result.warnings
                    if warning.startswith("media_termination:")
                ),
                None,
            )
            run = await self._set_status(
                latest,
                RunStatus.COMPLETED,
                progress=1.0,
                completed_at=time.time(),
                termination_reason=media_termination,
            )
            await self._event(run, "result.available", {"result_schema_version": result.schema_version})
        except ExecutionStopped:
            latest = await self.state.get_run(run.tenant_id, run.project_id, run.run_id)
            if latest and latest.status != RunStatus.CANCELLED:
                cancelled = await self._set_status(
                    latest,
                    RunStatus.CANCELLED,
                    completed_at=time.time(),
                    termination_reason="cancelled_by_user",
                )
                await self.audit.record(
                    PrincipalContext(
                        tenant_id=run.tenant_id,
                        project_id=run.project_id,
                        principal_id=run.principal_id,
                    ),
                    action="run.cancel",
                    resource_type="run",
                    resource_id=run.run_id,
                    evidence={"status": cancelled.status.value},
                )
        except Exception as exc:
            latest = await self.state.get_run(run.tenant_id, run.project_id, run.run_id)
            if latest and latest.status not in TERMINAL_RUN_STATUSES:
                code = "DOMAIN_UNAVAILABLE" if isinstance(exc, DomainUnavailable) else "PIPELINE_EXECUTION_FAILED"
                failed = await self._set_status(
                    latest,
                    RunStatus.FAILED,
                    completed_at=time.time(),
                    error_code=code,
                    termination_reason=str(exc)[:500],
                )
                await self._event(failed, "run.error", {"code": code, "message": str(exc)[:500]})
                await self.audit.record(
                    PrincipalContext(
                        tenant_id=run.tenant_id,
                        project_id=run.project_id,
                        principal_id=run.principal_id,
                    ),
                    action="run.fail",
                    resource_type="run",
                    resource_id=run.run_id,
                    outcome="failure",
                    evidence={"code": code, "message": str(exc)[:500]},
                )

    async def _store_result(self, run: RunRecord, result: ResultEnvelope) -> ResultReference:
        base_key = f"tenants/{run.tenant_id}/projects/{run.project_id}/runs/{run.run_id}"
        shard_keys: list[str] = []
        shard_sha256: list[str] = []
        written_keys: list[str] = []
        try:
            if len(result.units) > self.result_shard_units:
                for offset in range(0, len(result.units), self.result_shard_units):
                    units = result.units[offset : offset + self.result_shard_units]
                    shard_document = json.dumps(
                        [unit.model_dump(mode="json") for unit in units],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    shard_key = f"{base_key}/units-{offset // self.result_shard_units:06d}.json"
                    await self.objects.put(shard_key, shard_document, "application/json")
                    written_keys.append(shard_key)
                    shard_keys.append(shard_key)
                    shard_sha256.append(hashlib.sha256(shard_document).hexdigest())
                index_result = result.model_copy(update={"units": []}, deep=True)
            else:
                index_result = result
            result_document = index_result.model_dump_json().encode("utf-8")
            result_key = f"{base_key}/result.json"
            await self.objects.put(result_key, result_document, "application/json")
            written_keys.append(result_key)
            reference = ResultReference(
                run_id=run.run_id,
                object_key=result_key,
                sha256=hashlib.sha256(result_document).hexdigest(),
                unit_count=len(result.units),
                shard_keys=shard_keys,
                shard_sha256=shard_sha256,
                domain=result.domain,
                created_at=result.created_at,
            )
            expires_at = result.created_at + self.structured_result_retention_days * 86_400
            for object_key in written_keys:
                await self.state.track_object(
                    ObjectRetentionRecord(
                        tenant_id=run.tenant_id,
                        project_id=run.project_id,
                        object_key=object_key,
                        category="structured_result",
                        owner_type="run_result",
                        owner_id=run.run_id,
                        created_at=result.created_at,
                        expires_at=expires_at,
                    )
                )
            await self.state.save_result_reference(run.tenant_id, run.project_id, reference)
            return reference
        except Exception:
            for object_key in written_keys:
                with suppress(Exception):
                    await self.objects.delete(object_key)
            with suppress(Exception):
                await self.state.mark_objects_deleted(written_keys, time.time())
            raise

    async def _begin_execution(self, run: RunRecord) -> RunRecord:
        for _ in range(4):
            if run.status in TERMINAL_RUN_STATUSES:
                return run
            if run.status == RunStatus.CANCELLING:
                return await self._set_status(
                    run,
                    RunStatus.CANCELLED,
                    completed_at=time.time(),
                    termination_reason="cancelled_by_user",
                )
            if run.status == RunStatus.QUEUED:
                try:
                    return await self._set_status(run, RunStatus.RUNNING, started_at=time.time())
                except StateConflict:
                    latest = await self.state.get_run(run.tenant_id, run.project_id, run.run_id)
                    if latest is None:
                        raise ResourceNotFound("run disappeared before execution") from None
                    run = latest
                    continue
            if run.status in {RunStatus.RUNNING, RunStatus.PAUSING, RunStatus.PAUSED}:
                return run
            raise InvalidTransition(f"run cannot start from {run.status.value}")
        raise StateConflict("run could not acquire execution state")

    async def _checkpoint(self, run: RunRecord, control: ExecutionControl | None = None) -> None:
        while True:
            latest = await self.state.get_run(run.tenant_id, run.project_id, run.run_id)
            if latest is None:
                if control is not None:
                    control.cancel()
                raise ExecutionStopped
            if latest.status == RunStatus.CANCELLING:
                if control is not None:
                    control.cancel()
                await self._set_status(
                    latest,
                    RunStatus.CANCELLED,
                    completed_at=time.time(),
                    termination_reason="cancelled_by_user",
                )
                raise ExecutionStopped
            if latest.status == RunStatus.PAUSING:
                if control is not None:
                    control.pause()
                latest = await self._set_status(latest, RunStatus.PAUSED)
            if latest.status == RunStatus.PAUSED:
                if control is not None:
                    control.pause()
                await asyncio.sleep(0.1)
                continue
            if control is not None:
                control.resume()
            return

    async def _set_status(self, run: RunRecord, status: RunStatus, **changes: Any) -> RunRecord:
        updated = run.model_copy(update={"status": status, "updated_at": time.time(), **changes})
        saved = await self.state.save_run(updated, expected_revision=run.revision)
        await self._event(saved, f"run.{status.value}")
        return saved

    async def _event(self, run: RunRecord, event_type: str, payload: dict[str, Any] | None = None) -> RunEvent:
        return await self.state.append_event(
            run.tenant_id,
            run.project_id,
            RunEvent(
                run_id=run.run_id,
                event_id=1,
                event_type=event_type,
                status=run.status,
                payload=payload or {},
                created_at=time.time(),
            ),
        )


def sse_payload(event: RunEvent) -> str:
    data = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    return f"id: {event.event_id}\nevent: {event.event_type}\ndata: {data}\n\n"


__all__ = [
    "CreateRunOutcome",
    "InvalidTransition",
    "ResourceNotFound",
    "RunService",
    "sse_payload",
]
