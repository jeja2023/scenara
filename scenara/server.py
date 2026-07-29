from __future__ import annotations

import asyncio
import hmac
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

from scenara.bootstrap import Runtime, build_runtime
from scenara.platform.models import (
    TERMINAL_RUN_STATUSES,
    ApiEnvelope,
    ApiErrorDetail,
    ApiErrorEnvelope,
    CreateMediaSourceRequest,
    CreateRunRequest,
    MediaAsset,
    MediaAssetPage,
    MediaKind,
    MediaSource,
    MediaSourcePage,
    ParseImageResponse,
    PipelineRef,
    PrincipalContext,
    ResultPage,
    RunPage,
    RunRecord,
    RunStatus,
    SystemStatus,
)
from scenara.platform.pipeline import PipelineError
from scenara.platform.services import InvalidTransition, ResourceNotFound, sse_payload
from scenara.platform.store import StateConflict
from scenara.settings import Settings

CONTEXT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", f"req_{uuid4().hex}"))


def _envelope(request: Request, data: object) -> ApiEnvelope[object]:
    return ApiEnvelope(request_id=_request_id(request), data=data)


async def principal_context(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header()] = None,
    x_project_id: Annotated[str | None, Header()] = None,
) -> PrincipalContext:
    runtime: Runtime = request.app.state.runtime
    settings = runtime.settings
    if settings.auth_required:
        expected = f"Bearer {settings.api_token}"
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
    tenant_id = x_tenant_id or settings.default_tenant_id
    project_id = x_project_id or settings.default_project_id
    if not CONTEXT_ID.fullmatch(tenant_id) or not CONTEXT_ID.fullmatch(project_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid tenant or project identifier")
    return PrincipalContext(tenant_id=tenant_id, project_id=project_id)


def create_app(settings: Settings | None = None, *, runtime: Runtime | None = None) -> FastAPI:
    runtime = runtime or build_runtime(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await runtime.open()
        try:
            yield
        finally:
            await runtime.close()

    app = FastAPI(
        title="Scenara API",
        version="0.1.0",
        description="Enterprise unified vision parsing platform",
        docs_url="/docs" if not runtime.settings.production else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.runtime = runtime

    @app.middleware("http")
    async def request_context(request: Request, call_next: object) -> Response:
        request.state.request_id = request.headers.get("X-Request-Id", f"req_{uuid4().hex}")[:128]
        response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    def error_response(request: Request, status_code: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
        payload = ApiErrorEnvelope(
            request_id=_request_id(request),
            error=ApiErrorDetail(code=code, message=message, details=details or {}),
        )
        return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error_response(request, exc.status_code, "HTTP_ERROR", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(request, 422, "VALIDATION_ERROR", "request validation failed", {"errors": exc.errors()})

    @app.exception_handler(ResourceNotFound)
    async def not_found(request: Request, exc: ResourceNotFound) -> JSONResponse:
        return error_response(request, 404, "NOT_FOUND", str(exc))

    @app.exception_handler(InvalidTransition)
    async def invalid_transition(request: Request, exc: InvalidTransition) -> JSONResponse:
        return error_response(request, 409, "INVALID_RUN_TRANSITION", str(exc))

    @app.exception_handler(StateConflict)
    async def state_conflict(request: Request, exc: StateConflict) -> JSONResponse:
        return error_response(request, 409, "STATE_CONFLICT", str(exc))

    @app.exception_handler(PipelineError)
    async def pipeline_error(request: Request, exc: PipelineError) -> JSONResponse:
        return error_response(request, 422, "PIPELINE_ERROR", str(exc))

    @app.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError) -> JSONResponse:
        return error_response(request, 400, "INVALID_ARGUMENT", str(exc))

    @app.get("/healthz", tags=["Operations"])
    async def health(request: Request) -> ApiEnvelope[dict[str, str]]:
        return _envelope(request, {"status": "ok", "version": "0.1.0"})  # type: ignore[return-value]

    @app.post("/api/v1/media/assets", status_code=201, tags=["Media"])
    async def create_media_asset(
        request: Request,
        file: Annotated[UploadFile, File()],
        kind: Annotated[MediaKind, Form()] = MediaKind.IMAGE,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaAsset]:
        max_read = runtime.settings.max_image_bytes + 1 if kind == MediaKind.IMAGE else 512 * 1024 * 1024 + 1
        data = await file.read(max_read)
        asset = await runtime.runs.create_asset(
            context,
            data=data,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            kind=kind,
        )
        return _envelope(request, asset)  # type: ignore[return-value]

    @app.get("/api/v1/media/assets", tags=["Media"])
    async def list_media_assets(
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaAssetPage]:
        rows = await runtime.state.list_assets(context.tenant_id, context.project_id)
        return _envelope(
            request,
            MediaAssetPage(items=rows[offset : offset + limit], offset=offset, limit=limit, total=len(rows)),
        )  # type: ignore[return-value]

    @app.get("/api/v1/media/assets/{asset_id}", tags=["Media"])
    async def get_media_asset(
        asset_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaAsset]:
        asset = await runtime.state.get_asset(context.tenant_id, context.project_id, asset_id)
        if asset is None:
            raise ResourceNotFound("media asset not found")
        return _envelope(request, asset)  # type: ignore[return-value]

    @app.post("/api/v1/media/sources", status_code=201, tags=["Media"])
    async def create_media_source(
        body: CreateMediaSourceRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaSource]:
        source = await runtime.runs.create_source(context, body)
        return _envelope(request, source)  # type: ignore[return-value]

    @app.get("/api/v1/media/sources", tags=["Media"])
    async def list_media_sources(
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaSourcePage]:
        rows = await runtime.state.list_sources(context.tenant_id, context.project_id)
        return _envelope(
            request,
            MediaSourcePage(items=rows[offset : offset + limit], offset=offset, limit=limit, total=len(rows)),
        )  # type: ignore[return-value]

    @app.post("/api/v1/runs", status_code=202, tags=["Runs"])
    async def create_run(
        body: CreateRunRequest,
        request: Request,
        response: Response,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[RunRecord]:
        outcome = await runtime.runs.create_run(context, body, idempotency_key=idempotency_key)
        response.status_code = 202 if outcome.created else 200
        return _envelope(request, outcome.run)  # type: ignore[return-value]

    @app.get("/api/v1/runs", tags=["Runs"])
    async def list_runs(
        request: Request,
        run_status: Annotated[RunStatus | None, Query(alias="status")] = None,
        domain: Literal["portrait", "ocr"] | None = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[RunPage]:
        items, total = await runtime.runs.list_runs(
            context,
            status=run_status,
            domain=domain,
            offset=offset,
            limit=limit,
        )
        return _envelope(request, RunPage(items=items, offset=offset, limit=limit, total=total))  # type: ignore[return-value]

    @app.get("/api/v1/runs/{run_id}", tags=["Runs"])
    async def get_run(
        run_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[RunRecord]:
        return _envelope(request, await runtime.runs.get_run(context, run_id))  # type: ignore[return-value]

    async def lifecycle(run_id: str, action: str, request: Request, context: PrincipalContext) -> ApiEnvelope[RunRecord]:
        return _envelope(request, await runtime.runs.transition(context, run_id, action))  # type: ignore[return-value]

    @app.post("/api/v1/runs/{run_id}/cancel", tags=["Runs"])
    async def cancel_run(run_id: str, request: Request, context: PrincipalContext = Depends(principal_context)) -> ApiEnvelope[RunRecord]:
        return await lifecycle(run_id, "cancel", request, context)

    @app.post("/api/v1/runs/{run_id}/pause", tags=["Runs"])
    async def pause_run(run_id: str, request: Request, context: PrincipalContext = Depends(principal_context)) -> ApiEnvelope[RunRecord]:
        return await lifecycle(run_id, "pause", request, context)

    @app.post("/api/v1/runs/{run_id}/resume", tags=["Runs"])
    async def resume_run(run_id: str, request: Request, context: PrincipalContext = Depends(principal_context)) -> ApiEnvelope[RunRecord]:
        return await lifecycle(run_id, "resume", request, context)

    @app.get("/api/v1/runs/{run_id}/result", tags=["Results"])
    async def get_result(
        run_id: str,
        request: Request,
        unit_offset: Annotated[int, Query(ge=0)] = 0,
        unit_limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ResultPage]:
        result = await runtime.runs.result(context, run_id)
        total = len(result.units)
        page = result.model_copy(update={"units": result.units[unit_offset : unit_offset + unit_limit]}, deep=True)
        return _envelope(
            request,
            ResultPage(result=page, unit_offset=unit_offset, unit_limit=unit_limit, unit_total=total),
        )  # type: ignore[return-value]

    @app.get("/api/v1/runs/{run_id}/events", tags=["Runs"])
    async def run_events(
        run_id: str,
        request: Request,
        last_event_id_header: Annotated[int | None, Header(alias="Last-Event-ID")] = None,
        last_event_id: Annotated[int, Query(ge=0)] = 0,
        context: PrincipalContext = Depends(principal_context),
    ) -> StreamingResponse:
        await runtime.runs.get_run(context, run_id)
        cursor = last_event_id_header if last_event_id_header is not None else last_event_id

        async def stream() -> AsyncIterator[str]:
            nonlocal cursor
            heartbeat_at = asyncio.get_running_loop().time() + 15
            while True:
                if await request.is_disconnected():
                    return
                events = await runtime.state.events_after(context.tenant_id, context.project_id, run_id, cursor)
                for event in events:
                    cursor = event.event_id
                    yield sse_payload(event)
                run = await runtime.runs.get_run(context, run_id)
                if run.status in TERMINAL_RUN_STATUSES and not events:
                    return
                now = asyncio.get_running_loop().time()
                if now >= heartbeat_at:
                    yield ": heartbeat\n\n"
                    heartbeat_at = now + 15
                await asyncio.sleep(0.25)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.post("/api/v1/parse/image", tags=["Parsing"])
    async def parse_image(
        request: Request,
        file: Annotated[UploadFile, File()],
        domain: Annotated[Literal["portrait", "ocr"], Form()] = "portrait",
        pipeline_id: Annotated[str | None, Form()] = None,
        pipeline_version: Annotated[str, Form()] = "0.1.0",
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
        selected_pipeline = pipeline_id or ("portrait.person-detection" if domain == "portrait" else "ocr.document")
        create = CreateRunRequest(
            domain=domain,
            pipeline=PipelineRef(pipeline_id=selected_pipeline, version=pipeline_version),
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
        return _envelope(request, ParseImageResponse(asset=asset, run=outcome.run, result=result))  # type: ignore[return-value]

    @app.get("/api/v1/pipelines", tags=["Pipelines"])
    async def list_pipelines(request: Request, context: PrincipalContext = Depends(principal_context)) -> ApiEnvelope[list[dict]]:
        del context
        rows = [pipeline.model_dump(mode="json") for pipeline in runtime.pipelines.pipelines()]
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.get("/api/v1/domains", tags=["Domains"])
    async def list_domains(request: Request, context: PrincipalContext = Depends(principal_context)) -> ApiEnvelope[list[dict]]:
        del context
        rows = [
            {
                "domain_id": manifest.domain_id,
                "display_name": manifest.display_name,
                "schema_version": manifest.schema_version,
                "console_route": manifest.console_route,
                "capabilities": list(manifest.capabilities),
            }
            for manifest in runtime.plugins.manifests()
        ]
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.get("/api/v1/system/status", tags=["Operations"])
    async def system_status(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SystemStatus]:
        del context
        settings = runtime.settings
        return _envelope(
            request,
            SystemStatus(
                version="0.1.0",
                profile=settings.profile,
                state_backend=settings.state_backend,
                object_backend=settings.object_backend,
                queue_backend=settings.queue_backend,
                production_models_required=settings.production_models_required,
                auth_required=settings.auth_required,
            ),
        )  # type: ignore[return-value]

    return app


app = create_app()

__all__ = ["app", "create_app"]
