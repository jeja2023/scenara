from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile
import asyncio
from contextlib import suppress
from pathlib import Path
import tempfile
from uuid import uuid4

from scenara.bootstrap import Runtime
from scenara.platform.models import (
    ApiEnvelope,
    CreateRunRequest,
    DomainId,
    MediaKind,
    ParseDocumentResponse,
    ParseImageResponse,
    ParseStreamRequest,
    ParseVideoResponse,
    PrincipalContext,
    RunRecord,
    RunStatus,
    SampleStrategy,
)
from typing import Annotated


EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


async def spool_upload(file: UploadFile, max_bytes: int) -> Path:
    """Persist a bounded upload for parse endpoints that require a filesystem path."""
    handle = tempfile.NamedTemporaryFile(prefix="scenara-upload-", delete=False)
    path = Path(handle.name)
    size = 0
    failed = False
    try:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise ValueError(f"media exceeds {max_bytes} bytes")
            await asyncio.to_thread(handle.write, chunk)
        await asyncio.to_thread(handle.flush)
        return path
    except Exception:
        failed = True
        raise
    finally:
        with suppress(Exception):
            handle.close()
        if failed:
            with suppress(FileNotFoundError, PermissionError):
                path.unlink()


def build_parse_router(
    runtime: Runtime, principal_context: PrincipalDependency, envelope: EnvelopeFactory
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/parse/image", tags=["Parsing"])
    async def parse_image(
        request: Request,
        file: Annotated[UploadFile, File()],
        domain: Annotated[DomainId, Form()] = "portrait",
        pipeline_id: Annotated[str | None, Form()] = None,
        pipeline_version: Annotated[str | None, Form()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ParseImageResponse]:
        data = await file.read(runtime.settings.max_image_bytes + 1)
        asset = await runtime.runs.create_asset(
            context,
            data=data,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            kind=MediaKind.IMAGE,
            temporary=True,
        )
        selected_pipeline = pipeline_id or runtime.plugins.default_pipeline_id(domain)
        selected_pipeline_ref = await runtime.runs.resolve_pipeline_ref(
            selected_pipeline, pipeline_version
        )
        create = CreateRunRequest(
            domain=domain,
            pipeline=selected_pipeline_ref,
            asset_id=asset.asset_id,
            wait_ms=runtime.settings.image_wait_timeout_ms,
        )
        outcome = await runtime.runs.create_run(
            context,
            create,
            idempotency_key=idempotency_key or f"shortcut_{uuid4().hex}",
        )
        result = None
        if outcome.run.status == RunStatus.COMPLETED:
            result = await runtime.runs.result(context, outcome.run.run_id)
        return envelope(
            request, ParseImageResponse(asset=asset, run=outcome.run, result=result)
        )

    @router.post("/api/v1/parse/video", status_code=202, tags=["Parsing"])
    async def parse_video(
        request: Request,
        file: Annotated[UploadFile, File()],
        domain: Annotated[DomainId, Form()] = "portrait",
        pipeline_id: Annotated[str | None, Form()] = None,
        pipeline_version: Annotated[str | None, Form()] = None,
        sample_interval_ms: Annotated[int, Form(ge=1, le=3_600_000)] = 1000,
        sample_strategy: Annotated[SampleStrategy, Form()] = SampleStrategy.INTERVAL,
        sample_start_ms: Annotated[int, Form(ge=0)] = 0,
        sample_end_ms: Annotated[int | None, Form(ge=0)] = None,
        scene_change_threshold: Annotated[float, Form(ge=0.01, le=1.0)] = 0.35,
        frame_max_edge: Annotated[int | None, Form(ge=64, le=8192)] = None,
        page_scale: Annotated[float, Form(ge=0.5, le=4.0)] = 1.5,
        camera_id: Annotated[str | None, Form(max_length=128)] = None,
        recording_started_at: Annotated[float | None, Form(ge=0)] = None,
        wait_ms: Annotated[int, Form(ge=0, le=30_000)] = 0,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ParseVideoResponse]:
        path = await spool_upload(file, runtime.settings.max_media_bytes)
        try:
            asset = await runtime.runs.create_asset_from_path(
                context,
                path=str(path),
                filename=file.filename,
                content_type=file.content_type or "application/octet-stream",
                kind=MediaKind.VIDEO,
                temporary=True,
            )
        finally:
            with suppress(FileNotFoundError, PermissionError):
                path.unlink()
        selected_pipeline = pipeline_id or runtime.plugins.default_pipeline_id(domain)
        selected_pipeline_ref = await runtime.runs.resolve_pipeline_ref(
            selected_pipeline, pipeline_version
        )
        params: dict[str, object] = {
            "sample_interval_ms": sample_interval_ms,
            "sample_strategy": sample_strategy.value,
            "sample_start_ms": sample_start_ms,
            "scene_change_threshold": scene_change_threshold,
        }
        if sample_end_ms is not None:
            params["sample_end_ms"] = sample_end_ms
        if frame_max_edge is not None:
            params["frame_max_edge"] = frame_max_edge
        if page_scale != 1.5:
            params["page_scale"] = page_scale
        if camera_id:
            params["camera_id"] = camera_id
        if recording_started_at is not None:
            params["recording_started_at"] = recording_started_at
        outcome = await runtime.runs.create_run(
            context,
            CreateRunRequest(
                domain=domain,
                pipeline=selected_pipeline_ref,
                asset_id=asset.asset_id,
                parameters=params,
                wait_ms=wait_ms,
            ),
            idempotency_key=idempotency_key or f"shortcut_{uuid4().hex}",
        )
        result = None
        if outcome.run.status == RunStatus.COMPLETED:
            result = await runtime.runs.result(context, outcome.run.run_id)
        return envelope(
            request,
            ParseVideoResponse(asset=asset, run=outcome.run, result=result),
        )

    @router.post("/api/v1/parse/document", status_code=202, tags=["Parsing"])
    async def parse_document(
        request: Request,
        file: Annotated[UploadFile, File()],
        domain: Annotated[DomainId, Form()] = "ocr",
        pipeline_id: Annotated[str | None, Form()] = None,
        pipeline_version: Annotated[str | None, Form()] = None,
        page_scale: Annotated[float, Form(ge=0.5, le=4.0)] = 1.5,
        wait_ms: Annotated[int, Form(ge=0, le=30_000)] = 0,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ParseDocumentResponse]:
        data = await file.read(runtime.settings.max_media_bytes + 1)
        asset = await runtime.runs.create_asset(
            context,
            data=data,
            filename=file.filename,
            content_type=file.content_type or "application/pdf",
            kind=MediaKind.DOCUMENT,
            temporary=True,
        )
        selected_pipeline = pipeline_id or runtime.plugins.default_pipeline_id(domain)
        selected_pipeline_ref = await runtime.runs.resolve_pipeline_ref(
            selected_pipeline, pipeline_version
        )
        outcome = await runtime.runs.create_run(
            context,
            CreateRunRequest(
                domain=domain,
                pipeline=selected_pipeline_ref,
                asset_id=asset.asset_id,
                parameters={"page_scale": page_scale},
                wait_ms=wait_ms,
            ),
            idempotency_key=idempotency_key or f"shortcut_{uuid4().hex}",
        )
        result = None
        if outcome.run.status == RunStatus.COMPLETED:
            result = await runtime.runs.result(context, outcome.run.run_id)
        return envelope(
            request,
            ParseDocumentResponse(asset=asset, run=outcome.run, result=result),
        )

    @router.post("/api/v1/parse/stream", status_code=202, tags=["Parsing"])
    async def parse_stream(
        body: ParseStreamRequest,
        request: Request,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[RunRecord]:
        pipeline = await runtime.runs.resolve_pipeline_ref(
            body.pipeline.pipeline_id, body.pipeline.version
        )
        outcome = await runtime.runs.create_run(
            context,
            CreateRunRequest(
                domain=body.domain,
                pipeline=pipeline,
                source_id=body.source_id,
                parameters=body.parameters,
                priority=body.priority,
                wait_ms=body.wait_ms,
            ),
            idempotency_key=idempotency_key or f"shortcut_{uuid4().hex}",
        )
        return envelope(request, outcome.run)

    return router


__all__ = ["build_parse_router"]
