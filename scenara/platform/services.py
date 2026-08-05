from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from scenara.platform.artifacts import RunArtifactSink
from scenara.platform.audit import AuditLogger
from scenara.platform.index import IndexDefinition, IndexRecord, IndexRecordKind, IndexSourceRef, IndexStore
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
    ResultSummary,
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

logger = logging.getLogger(__name__)


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
        run_artifacts_enabled: bool = True,
        run_artifact_max_crops: int = 200,
        run_artifact_max_frames: int = 64,
        run_artifact_crop_max_edge: int = 256,
        run_artifact_frame_max_edge: int = 1920,
        indexes: IndexStore | None = None,
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
        self.run_artifacts_enabled = run_artifacts_enabled
        self.run_artifact_max_crops = run_artifact_max_crops
        self.run_artifact_max_frames = run_artifact_max_frames
        self.run_artifact_crop_max_edge = run_artifact_crop_max_edge
        self.run_artifact_frame_max_edge = run_artifact_frame_max_edge
        self.indexes = indexes
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
        if await self.state.has_non_terminal_run(
            context.tenant_id,
            context.project_id,
            asset_id=asset_id,
        ):
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
        if self.indexes is not None:
            await self.indexes.delete_asset(context.tenant_id, context.project_id, asset_id)

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
        if await self.state.has_non_terminal_run(
            context.tenant_id,
            context.project_id,
            source_id=source_id,
        ):
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

    async def get_source_preview(
        self,
        context: PrincipalContext,
        source_id: str,
        *,
        timeout_ms: int = 10_000,
    ) -> tuple[bytes, str]:
        source = await self.get_source(context, source_id)
        await require_allowed(self.policy, context, "execute", "media_source", {"source_id": source_id})
        source_url = await self.secrets.get(source.secret_ref)
        await validate_external_url(
            source_url,
            allowed_schemes=frozenset({"rtsp", "rtmp", "http", "https"}),
            allow_private=self.allow_private_media_sources,
            allow_credentials=True,
        )
        try:
            _metadata, preview = await asyncio.wait_for(
                asyncio.to_thread(
                    inspect_media,
                    MediaInput(kind=MediaKind.STREAM, content_type="application/octet-stream", source_url=source_url),
                ),
                timeout=timeout_ms / 1000 + 1,
            )
        except TimeoutError as exc:
            raise ValueError("media source preview timed out") from exc
        return preview, "image/jpeg"

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
        rows, total = await asyncio.gather(
            self.state.list_runs(
                context.tenant_id,
                context.project_id,
                status=status,
                domain=domain,
                offset=offset,
                limit=limit,
            ),
            self.state.count_runs(
                context.tenant_id,
                context.project_id,
                status=status,
                domain=domain,
            ),
        )
        return rows, total

    async def list_results(
        self,
        context: PrincipalContext,
        *,
        domain: str | None = None,
        media_kind: MediaKind | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ResultSummary], int]:
        await require_allowed(self.policy, context, "list", "run")
        references, total = await asyncio.gather(
            self.state.list_result_references(
                context.tenant_id,
                context.project_id,
                domain=domain,
                media_kind=media_kind.value if media_kind else None,
                query=query,
                offset=offset,
                limit=limit,
            ),
            self.state.count_result_references(
                context.tenant_id,
                context.project_id,
                domain=domain,
                media_kind=media_kind.value if media_kind else None,
                query=query,
            ),
        )
        runs = {
            run.run_id: run
            for run in await self.state.get_runs(
                context.tenant_id,
                context.project_id,
                [reference.run_id for reference in references],
            )
        }
        items: list[ResultSummary] = []
        for reference in references:
            run = runs.get(reference.run_id)
            if run is None:
                continue
            items.append(
                ResultSummary(
                    result_id=reference.run_id,
                    run_id=reference.run_id,
                    domain=reference.domain,
                    pipeline=run.pipeline,
                    status=run.status,
                    asset_id=reference.asset_id or run.asset_id,
                    source_id=reference.source_id or run.source_id,
                    media_kind=reference.media_kind,
                    resource_name=reference.resource_name,
                    unit_count=reference.unit_count,
                    object_count=reference.object_count,
                    person_count=reference.person_count,
                    face_count=reference.face_count,
                    ocr_block_count=reference.ocr_block_count,
                    text_length=reference.text_length,
                    warning_count=reference.warning_count,
                    index_status=reference.index_status,
                    created_at=reference.created_at,
                )
            )
        return items, total

    async def _result_index(
        self,
        context: PrincipalContext,
        run_id: str,
    ) -> tuple[ResultEnvelope, ResultReference]:
        """Load the result index document without materialising sharded units."""

        await self._get_run(context, run_id)
        reference = await self.state.get_result_reference(context.tenant_id, context.project_id, run_id)
        if reference is None:
            raise ResourceNotFound("run result is not available")
        document = await self.objects.get(reference.object_key)
        if hashlib.sha256(document).hexdigest() != reference.sha256:
            raise PipelineError("stored result checksum does not match its database reference")
        return ResultEnvelope.model_validate_json(document), reference

    async def result(self, context: PrincipalContext, run_id: str) -> ResultEnvelope:
        await require_allowed(self.policy, context, "read", "run", {"run_id": run_id})
        result, reference = await self._result_index(context, run_id)
        if reference.shard_keys:
            if len(reference.shard_keys) != len(reference.shard_sha256):
                raise PipelineError("stored result shard manifest is invalid")
            async def load_shard(object_key: str, expected_sha256: str) -> list[MediaUnitResult]:
                shard = await self.objects.get(object_key)
                if hashlib.sha256(shard).hexdigest() != expected_sha256:
                    raise PipelineError("stored result shard checksum does not match its reference")
                payload = json.loads(shard)
                if not isinstance(payload, list):
                    raise PipelineError("stored result shard is not a unit list")
                return [MediaUnitResult.model_validate(item) for item in payload]

            shard_units = await asyncio.gather(
                *(
                    load_shard(object_key, expected_sha256)
                    for object_key, expected_sha256 in zip(
                        reference.shard_keys,
                        reference.shard_sha256,
                        strict=True,
                    )
                )
            )
            units = [unit for shard in shard_units for unit in shard]
            if len(units) != reference.unit_count:
                raise PipelineError("stored result shard count does not match its reference")
            result = result.model_copy(update={"units": units}, deep=True)
        return result

    async def result_artifact(
        self,
        context: PrincipalContext,
        run_id: str,
        artifact_id: str,
    ) -> tuple[bytes, str, str]:
        """Return the bytes, content type, and checksum of one declared run artifact.

        Only artifacts listed in the stored result are readable, so an unknown or
        forged identifier can never reach the object store.
        """

        await require_allowed(self.policy, context, "read", "run", {"run_id": run_id})
        result, _ = await self._result_index(context, run_id)
        artifact = next((item for item in result.artifacts if item.artifact_id == artifact_id), None)
        if artifact is None:
            raise ResourceNotFound("run artifact not found")
        try:
            data = await self.objects.get(artifact.object_key)
        except Exception as exc:
            raise ResourceNotFound("run artifact is no longer stored") from exc
        if hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise PipelineError("stored run artifact checksum does not match its result reference")
        return data, artifact.content_type, artifact.sha256

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

    def _artifact_sink(self, run: RunRecord) -> RunArtifactSink | None:
        if not self.run_artifacts_enabled:
            return None
        return RunArtifactSink(
            self.objects,
            tenant_id=run.tenant_id,
            project_id=run.project_id,
            run_id=run.run_id,
            max_crops=self.run_artifact_max_crops,
            max_frames=self.run_artifact_max_frames,
            crop_max_edge=self.run_artifact_crop_max_edge,
            frame_max_edge=self.run_artifact_frame_max_edge,
        )

    async def execute_run(self, tenant_id: str, project_id: str, run_id: str) -> None:
        run = await self.state.get_run(tenant_id, project_id, run_id)
        if run is None:
            raise ResourceNotFound("queued run does not exist")
        if run.status in TERMINAL_RUN_STATUSES:
            return
        sink = self._artifact_sink(run)
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
            checkpoint_run: RunRecord = run
            execution_run = run

            async def report_progress(progress: float, payload: dict[str, Any]) -> None:
                nonlocal checkpoint_run
                for _ in range(4):
                    latest = await self.state.get_run(
                        execution_run.tenant_id,
                        execution_run.project_id,
                        execution_run.run_id,
                    )
                    if latest is None:
                        raise ResourceNotFound("run disappeared while reporting progress")
                    if latest.status in TERMINAL_RUN_STATUSES:
                        return
                    next_progress = max(latest.progress, min(0.99, progress))
                    if next_progress <= latest.progress:
                        return
                    updated = latest.model_copy(update={"progress": next_progress, "updated_at": time.time()})
                    try:
                        saved = await self.state.save_run(updated, expected_revision=latest.revision)
                    except StateConflict:
                        continue
                    checkpoint_run = saved
                    await self._event(
                        saved,
                        "run.progress",
                        {"progress": saved.progress, **payload},
                    )
                    return
                raise StateConflict("run progress could not be saved")

            async def publish_partial_result(partial: Any) -> None:
                if not isinstance(partial, ResultEnvelope):
                    raise PipelineError("partial pipeline result is not a ResultEnvelope")
                if sink is not None and (sink.artifacts or sink.warnings):
                    partial = partial.model_copy(
                        update={
                            "artifacts": [*partial.artifacts, *sink.artifacts],
                            "warnings": [*partial.warnings, *sink.warnings],
                        },
                        deep=True,
                    )
                try:
                    await self._store_result(execution_run, partial, sink, partial=True)
                    latest = await self.state.get_run(
                        execution_run.tenant_id,
                        execution_run.project_id,
                        execution_run.run_id,
                    )
                    if latest is not None and latest.status not in TERMINAL_RUN_STATUSES:
                        await self._event(
                            latest,
                            "result.partial",
                            {"unit_count": len(partial.units), "progress": latest.progress},
                        )
                except Exception:
                    logger.exception("could not publish partial result for run %s", execution_run.run_id)

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
                artifacts=sink,
                progress_reporter=report_progress,
                partial_result_publisher=publish_partial_result,
            )

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
            if sink is not None and (sink.artifacts or sink.warnings):
                result = result.model_copy(
                    update={
                        "artifacts": [*result.artifacts, *sink.artifacts],
                        "warnings": [*result.warnings, *sink.warnings],
                    },
                    deep=True,
                )
            await self._store_result(run, result, sink)
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
            await self._discard_partial_result(run)
            if sink is not None:
                await sink.discard()
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
            await self._discard_partial_result(run)
            if sink is not None:
                await sink.discard()
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

    async def _store_result(
        self,
        run: RunRecord,
        result: ResultEnvelope,
        sink: RunArtifactSink | None = None,
        *,
        partial: bool = False,
    ) -> ResultReference:
        run_base_key = f"tenants/{run.tenant_id}/projects/{run.project_id}/runs/{run.run_id}"
        base_key = f"{run_base_key}/partial/snapshot-{len(result.units):06d}" if partial else run_base_key
        shard_keys: list[str] = []
        shard_sha256: list[str] = []
        written_keys: list[str] = []
        previous = await self.state.get_result_reference(run.tenant_id, run.project_id, run.run_id)
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
            asset = (
                await self.state.get_asset(run.tenant_id, run.project_id, run.asset_id)
                if run.asset_id
                else None
            )
            source = (
                await self.state.get_source(run.tenant_id, run.project_id, run.source_id)
                if run.source_id
                else None
            )
            reference = ResultReference(
                run_id=run.run_id,
                object_key=result_key,
                sha256=hashlib.sha256(result_document).hexdigest(),
                unit_count=len(result.units),
                shard_keys=shard_keys,
                shard_sha256=shard_sha256,
                domain=result.domain,
                created_at=result.created_at,
                asset_id=run.asset_id,
                source_id=run.source_id,
                media_kind=asset.kind if asset is not None else (MediaKind.STREAM if source else None),
                resource_name=asset.filename if asset is not None else source.name if source is not None else None,
                object_count=sum(len(unit.objects) for unit in result.units),
                person_count=len(getattr(result.domain_payload, "persons", [])),
                face_count=len(getattr(result.domain_payload, "faces", [])),
                ocr_block_count=len(getattr(result.domain_payload, "blocks", [])),
                text_length=len(getattr(result.domain_payload, "text", "") or ""),
                warning_count=len(result.warnings),
                index_status="partial" if partial else "ready",
            )
            expires_at = run.created_at + self.structured_result_retention_days * 86_400
            for object_key in written_keys:
                await self.state.track_object(
                    ObjectRetentionRecord(
                        tenant_id=run.tenant_id,
                        project_id=run.project_id,
                        object_key=object_key,
                        category="structured_result",
                        owner_type="run_result",
                        owner_id=run.run_id,
                        created_at=run.created_at,
                        expires_at=expires_at,
                    )
                )
            if sink is not None and not partial:
                # Feature crops and unit frames are derived previews: they follow the
                # preview retention window, not the longer structured-result window.
                for record in sink.retention_records(
                    created_at=run.created_at,
                    expires_at=run.created_at + self.preview_retention_days * 86_400,
                ):
                    await self.state.track_object(record)
            if not partial and self.indexes is not None:
                try:
                    await self._index_result(run, result)
                except Exception:
                    logger.exception("result index update failed for run %s", run.run_id)
                    reference = reference.model_copy(update={"index_status": "partial"})
            await self.state.save_result_reference(run.tenant_id, run.project_id, reference)
            if previous is not None and previous.object_key != reference.object_key:
                previous_keys = [previous.object_key, *previous.shard_keys]
                for object_key in previous_keys:
                    with suppress(Exception):
                        await self.objects.delete(object_key)
                with suppress(Exception):
                    await self.state.mark_objects_deleted(previous_keys, time.time())
            return reference
        except Exception:
            for object_key in written_keys:
                with suppress(Exception):
                    await self.objects.delete(object_key)
            with suppress(Exception):
                await self.state.mark_objects_deleted(written_keys, time.time())
            raise

    async def _index_result(self, run: RunRecord, result: ResultEnvelope) -> None:
        if self.indexes is None:
            return
        index_id = f"result.{result.domain}"
        await self.indexes.delete_source(run.tenant_id, run.project_id, "run_result", run.run_id)
        await self.indexes.create_index(
            IndexDefinition(
                index_id=index_id,
                domain=result.domain,
                record_kind=IndexRecordKind.MULTIMODAL,
                text_analyzer="simple",
            )
        )
        index_expires_at = run.created_at + self.structured_result_retention_days * 86_400

        def safe_metadata(value: object) -> dict[str, object]:
            if not isinstance(value, dict):
                return {}
            return {
                str(key): nested
                for key, nested in value.items()
                if str(key) not in {"embedding", "_tracking_embedding", "vector", "crop"}
                and isinstance(nested, (str, int, float, bool, list, dict, type(None)))
            }

        records: list[IndexRecord] = []
        for unit in result.units:
            for item in unit.objects:
                records.append(
                    IndexRecord(
                        record_id=f"idxr_{run.run_id}_{unit.unit_id}_{item.object_id}",
                        tenant_id=run.tenant_id,
                        project_id=run.project_id,
                        index_id=index_id,
                        domain=result.domain,
                        kind=IndexRecordKind.MULTIMODAL,
                        source=IndexSourceRef(
                            source_type="run_result",
                            source_id=run.run_id,
                            asset_id=run.asset_id,
                            run_id=run.run_id,
                            unit_id=unit.unit_id,
                            object_id=item.object_id,
                            artifact_id=item.crop_artifact_id,
                            page_number=unit.page_number,
                            pts_ms=unit.pts_ms,
                        ),
                        metadata={
                            "object_type": item.object_type,
                            "score": item.score,
                            "bbox": item.bbox.model_dump(mode="json") if item.bbox else None,
                            "attributes": safe_metadata(item.attributes),
                            "source_id": run.source_id,
                        },
                        expires_at=index_expires_at,
                    )
                )
        payload = result.domain_payload
        full_text = str(getattr(payload, "text", "") or "")
        if full_text:
            records.append(
                IndexRecord(
                    record_id=f"idxr_{run.run_id}_text",
                    tenant_id=run.tenant_id,
                    project_id=run.project_id,
                    index_id=index_id,
                    domain=result.domain,
                    kind=IndexRecordKind.MULTIMODAL,
                    source=IndexSourceRef(
                        source_type="run_result",
                        source_id=run.run_id,
                        asset_id=run.asset_id,
                        run_id=run.run_id,
                    ),
                    text=full_text,
                    metadata={
                        "language": getattr(payload, "language", None),
                        "block_count": len(getattr(payload, "blocks", [])),
                        "source_id": run.source_id,
                    },
                    expires_at=index_expires_at,
                )
            )
        for block in getattr(payload, "blocks", []):
            block_id = str(getattr(block, "block_id", ""))
            text = str(getattr(block, "text", "") or "")
            if not block_id or not text:
                continue
            records.append(
                IndexRecord(
                    record_id=f"idxr_{run.run_id}_block_{block_id}",
                    tenant_id=run.tenant_id,
                    project_id=run.project_id,
                    index_id=index_id,
                    domain=result.domain,
                    kind=IndexRecordKind.MULTIMODAL,
                    source=IndexSourceRef(
                        source_type="run_result",
                        source_id=run.run_id,
                        asset_id=run.asset_id,
                        run_id=run.run_id,
                    ),
                    text=text,
                    metadata={
                        "score": getattr(block, "score", None),
                        "block_type": getattr(block, "block_type", "text"),
                        "source_id": run.source_id,
                    },
                    expires_at=index_expires_at,
                )
            )
        for record in records:
            await self.indexes.upsert(record)
        for hint in result._index_vectors:
            vector_index_id = f"result.{hint.feature_space_id}"
            await self.indexes.create_index(
                IndexDefinition(
                    index_id=vector_index_id,
                    domain=result.domain,
                    record_kind=IndexRecordKind.VECTOR,
                    vector_dimension=len(hint.vector),
                    vector_model_id=hint.model_id,
                    vector_model_version=hint.model_version,
                    distance_metric="cosine",
                    threshold=0.8,
                )
            )
            location: tuple[str | None, int | None, int | None, int | None] = (None, None, None, None)
            artifact_id: str | None = None
            for unit in result.units:
                for item in unit.objects:
                    if item.object_id == hint.object_id:
                        location = (unit.unit_id, unit.page_number, unit.pts_ms, unit.index)
                        artifact_id = item.crop_artifact_id
                        break
                if location[0] is not None:
                    break
            unit_id, page_number, pts_ms, unit_index = location
            await self.indexes.upsert(
                IndexRecord(
                    record_id=f"idxv_{run.run_id}_{hint.object_id}",
                    tenant_id=run.tenant_id,
                    project_id=run.project_id,
                    index_id=vector_index_id,
                    domain=result.domain,
                    kind=IndexRecordKind.VECTOR,
                    source=IndexSourceRef(
                        source_type="run_result",
                        source_id=run.run_id,
                        asset_id=run.asset_id,
                        run_id=run.run_id,
                        unit_id=unit_id,
                        object_id=hint.object_id,
                        artifact_id=artifact_id,
                        page_number=page_number,
                        pts_ms=pts_ms,
                    ),
                    vector=hint.vector,
                    metadata={
                        "object_type": "face",
                        "feature_space_id": hint.feature_space_id,
                        "model_id": hint.model_id,
                        "model_version": hint.model_version,
                        "quality": hint.quality,
                        "unit_index": unit_index,
                        "source_id": run.source_id,
                    },
                    expires_at=index_expires_at,
                )
            )

    async def _discard_partial_result(self, run: RunRecord) -> None:
        try:
            reference = await self.state.get_result_reference(run.tenant_id, run.project_id, run.run_id)
        except Exception:
            logger.exception("could not inspect partial result for run %s", run.run_id)
            return
        if reference is None or "/partial/" not in reference.object_key:
            return
        object_keys = [reference.object_key, *reference.shard_keys]
        for object_key in object_keys:
            with suppress(Exception):
                await self.objects.delete(object_key)
        with suppress(Exception):
            await self.state.mark_objects_deleted(object_keys, time.time())

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
