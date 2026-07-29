from __future__ import annotations

import asyncio
import hashlib
import json
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from scenara.platform.models import (
    TERMINAL_RUN_STATUSES,
    CreateMediaSourceRequest,
    CreateRunRequest,
    MediaAsset,
    MediaKind,
    MediaSource,
    PrincipalContext,
    ResultEnvelope,
    ResultReference,
    RunEvent,
    RunRecord,
    RunStatus,
)
from scenara.platform.objects import ObjectStore
from scenara.platform.pipeline import DomainUnavailable, ExecutionContext, PipelineError, PipelineRegistry
from scenara.platform.queue import RunQueue
from scenara.platform.store import StateConflict, StateStore


class ResourceNotFound(RuntimeError):
    pass


class InvalidTransition(RuntimeError):
    pass


class ExecutionStopped(RuntimeError):
    pass


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
        max_image_bytes: int,
    ) -> None:
        self.state = state
        self.objects = objects
        self.queue = queue
        self.pipelines = pipelines
        self.max_image_bytes = max_image_bytes
        self._source_secrets: dict[tuple[str, str, str], str] = {}
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
        if not data:
            raise ValueError("media asset is empty")
        if kind == MediaKind.IMAGE and len(data) > self.max_image_bytes:
            raise ValueError(f"image exceeds {self.max_image_bytes} bytes")
        asset_id = f"ast_{uuid4().hex}"
        object_key = f"tenants/{context.tenant_id}/projects/{context.project_id}/assets/{asset_id}/original"
        now = time.time()
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
            temporary=temporary,
            created_at=now,
            expires_at=now + 86_400 if temporary else None,
        )
        await self.objects.put(object_key, data, asset.content_type)
        try:
            return await self.state.create_asset(asset)
        except Exception:
            with suppress(Exception):
                await self.objects.delete(object_key)
            raise

    async def create_source(
        self,
        context: PrincipalContext,
        request: CreateMediaSourceRequest,
    ) -> MediaSource:
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
        stored = await self.state.create_source(source)
        self._source_secrets[(context.tenant_id, context.project_id, source_id)] = request.url
        return stored

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
        pipeline = self.pipelines.pipeline(request.pipeline.pipeline_id, request.pipeline.version)
        if pipeline.domain != request.domain:
            raise ValueError("requested domain does not match pipeline domain")
        self.pipelines.validate_run_parameters(pipeline, request.parameters)
        if request.asset_id:
            asset = await self.state.get_asset(context.tenant_id, context.project_id, request.asset_id)
            if asset is None:
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
            run = await self.get_run(context, run_id)
            if run.status in TERMINAL_RUN_STATUSES:
                return run
            await asyncio.sleep(0.02)
        return await self.get_run(context, run_id)

    async def get_run(self, context: PrincipalContext, run_id: str) -> RunRecord:
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
        rows = await self.state.list_runs(context.tenant_id, context.project_id)
        if status is not None:
            rows = [item for item in rows if item.status == status]
        if domain is not None:
            rows = [item for item in rows if item.domain == domain]
        return rows[offset : offset + limit], len(rows)

    async def result(self, context: PrincipalContext, run_id: str) -> ResultEnvelope:
        await self.get_run(context, run_id)
        reference = await self.state.get_result_reference(context.tenant_id, context.project_id, run_id)
        if reference is None:
            raise ResourceNotFound("run result is not available")
        document = await self.objects.get(reference.object_key)
        if hashlib.sha256(document).hexdigest() != reference.sha256:
            raise PipelineError("stored result checksum does not match its database reference")
        return ResultEnvelope.model_validate_json(document)

    async def transition(self, context: PrincipalContext, run_id: str, action: str) -> RunRecord:
        for _ in range(4):
            run = await self.get_run(context, run_id)
            pipeline = self.pipelines.pipeline(run.pipeline.pipeline_id, run.pipeline.version, active_only=False)
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
            if run.source_id:
                raise DomainUnavailable("stream execution worker is not installed in Scenara 0.1")
            asset = await self.state.get_asset(run.tenant_id, run.project_id, run.asset_id or "")
            if asset is None:
                raise ResourceNotFound("media asset disappeared before execution")
            data = await self.objects.get(asset.object_key)
            pipeline = self.pipelines.pipeline(run.pipeline.pipeline_id, run.pipeline.version)
            context = ExecutionContext(
                run_id=run.run_id,
                tenant_id=run.tenant_id,
                project_id=run.project_id,
                pipeline_id=run.pipeline.pipeline_id,
                pipeline_version=run.pipeline.version,
                asset_id=run.asset_id,
                source_id=run.source_id,
                filename=asset.filename,
                content_type=asset.content_type,
            )

            async def checkpoint() -> None:
                await self._checkpoint(run)

            result = await self.pipelines.execute(
                pipeline,
                context,
                {"$media.bytes": data},
                run.parameters,
                checkpoint,
            )
            if not isinstance(result, ResultEnvelope):
                raise PipelineError("pipeline did not return a ResultEnvelope")
            result_document = result.model_dump_json().encode("utf-8")
            result_key = f"tenants/{run.tenant_id}/projects/{run.project_id}/runs/{run.run_id}/result.json"
            await self.objects.put(result_key, result_document, "application/json")
            await self.state.save_result_reference(
                run.tenant_id,
                run.project_id,
                ResultReference(
                    run_id=run.run_id,
                    object_key=result_key,
                    sha256=hashlib.sha256(result_document).hexdigest(),
                    unit_count=len(result.units),
                    domain=result.domain,
                    created_at=result.created_at,
                ),
            )
            latest = await self.state.get_run(run.tenant_id, run.project_id, run.run_id)
            if latest is None:
                raise ResourceNotFound("run disappeared during execution")
            run = await self._set_status(latest, RunStatus.COMPLETED, progress=1.0, completed_at=time.time())
            await self._event(run, "result.available", {"result_schema_version": result.schema_version})
        except ExecutionStopped:
            latest = await self.state.get_run(run.tenant_id, run.project_id, run.run_id)
            if latest and latest.status != RunStatus.CANCELLED:
                await self._set_status(latest, RunStatus.CANCELLED, completed_at=time.time(), termination_reason="cancelled_by_user")
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

    async def _checkpoint(self, run: RunRecord) -> None:
        while True:
            latest = await self.state.get_run(run.tenant_id, run.project_id, run.run_id)
            if latest is None:
                raise ExecutionStopped
            if latest.status == RunStatus.CANCELLING:
                cancelled = await self._set_status(
                    latest,
                    RunStatus.CANCELLED,
                    completed_at=time.time(),
                    termination_reason="cancelled_by_user",
                )
                await self._event(cancelled, "run.cancelled")
                raise ExecutionStopped
            if latest.status == RunStatus.PAUSING:
                latest = await self._set_status(latest, RunStatus.PAUSED)
                await self._event(latest, "run.paused")
            if latest.status == RunStatus.PAUSED:
                await asyncio.sleep(0.1)
                continue
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
