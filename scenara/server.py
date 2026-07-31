from __future__ import annotations

import asyncio
import hmac
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.staticfiles import StaticFiles

from scenara import __version__
from scenara.bootstrap import Runtime, build_runtime
from scenara.domains.portrait.service import (
    CreateIdentityRequest,
    EnrollIdentityRequest,
    PortraitCompareRequest,
    PortraitCompareResponse,
    PortraitConflict,
    PortraitEnrollment,
    PortraitIdentity,
    PortraitIdentityPage,
    PortraitNotFound,
    PortraitSearchRequest,
    PortraitSearchResponse,
)
from scenara.enterprise.service import (
    ComplianceEvidence,
    CreateComplianceEvidenceRequest,
    CreateIncidentRequest,
    CreateSupportCaseRequest,
    EnterpriseService,
    EnterpriseStatus,
    Incident,
    ResolveIncidentRequest,
    SlaSnapshot,
    SupportCase,
)
from scenara.platform.access import AccessNotFound
from scenara.platform.access_foundation import build_access_foundation
from scenara.platform.audit import AuditUnavailable
from scenara.platform.features import FeatureStoreError
from scenara.platform.feedback import (
    CreateFeedbackRequest,
    CreateHardSampleManifestRequest,
    CreateModelReleaseRequest,
    FeedbackConflict,
    FeedbackNotFound,
    FeedbackRecord,
    HardSampleManifest,
    ModelDeploymentEvent,
    ModelRelease,
    ReviewFeedbackRequest,
    RollbackModelReleaseRequest,
    TransitionModelReleaseRequest,
)
from scenara.platform.model_runtime import ModelPackageManifest
from scenara.platform.models import (
    TERMINAL_RUN_STATUSES,
    AccessFoundationStatus,
    ApiEnvelope,
    ApiErrorDetail,
    ApiErrorEnvelope,
    ApiKeyRecord,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    CreateMediaSourceRequest,
    CreateMembershipRequest,
    CreateOrganizationRequest,
    CreateProductEntitlementRequest,
    CreateProjectRequest,
    CreateRoleRequest,
    CreateRunRequest,
    CreateServiceAccountRequest,
    CreateUserRequest,
    CreateWebhookSubscriptionRequest,
    IamSummary,
    MediaAsset,
    MediaAssetPage,
    MediaKind,
    MediaSource,
    MediaSourcePage,
    MediaSourceProbe,
    MediaSourceView,
    Membership,
    Organization,
    ParseDocumentResponse,
    ParseImageResponse,
    ParseStreamRequest,
    ParseVideoResponse,
    PipelineTransitionRequest,
    PortraitIntelligenceStatus,
    PrincipalContext,
    ProductCatalogItem,
    ProductEntitlement,
    Project,
    RepositoryTopology,
    ResultPage,
    Role,
    RunPage,
    RunRecord,
    RunStatus,
    SampleStrategy,
    ServiceAccount,
    SystemStatus,
    UpdateProductEntitlementRequest,
    UserAccount,
    WebhookDeliveryRecord,
    WebhookSubscriptionView,
)
from scenara.platform.observability import RequestMetrics
from scenara.platform.pipeline import PipelineError
from scenara.platform.policy import PolicyDenied, PolicyUnavailable, require_allowed
from scenara.platform.portrait_intelligence import CapabilitySnapshot, build_portrait_intelligence
from scenara.platform.product_catalog import build_product_catalog
from scenara.platform.repository_contracts import (
    CONTRACT_ROOT,
    RepositoryContractCatalog,
    load_repository_contract_catalog,
)
from scenara.platform.repository_topology import build_repository_topology
from scenara.platform.services import InvalidTransition, ResourceNotFound, sse_payload
from scenara.platform.store import StateConflict
from scenara.platform.webhook_service import WebhookNotFound
from scenara.settings import Settings

CONTEXT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
CONSOLE_DIST = Path(__file__).resolve().parents[1] / "frontend" / "console" / "dist"
CONSOLE_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; connect-src 'self' http: https:; img-src 'self' data:; "
        "style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
}


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", f"req_{uuid4().hex}"))


def _envelope(request: Request, data: object) -> ApiEnvelope[object]:
    return ApiEnvelope(request_id=_request_id(request), data=data)


def _media_source_view(source: MediaSource) -> MediaSourceView:
    return MediaSourceView(
        source_id=source.source_id,
        kind=source.kind,
        name=source.name,
        masked_url=source.masked_url,
        metadata=source.metadata,
        created_at=source.created_at,
    )


async def principal_context(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_principal_id: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header()] = None,
    x_project_id: Annotated[str | None, Header()] = None,
) -> PrincipalContext:
    runtime: Runtime = request.app.state.runtime
    settings = runtime.settings
    if settings.auth_required:
        expected = f"Bearer {settings.api_token}"
        if not authorization:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
        if hmac.compare_digest(authorization, expected):
            if x_principal_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="principal identity is credential-derived"
                )
            tenant_id = x_tenant_id or settings.default_tenant_id
            project_id = x_project_id or settings.default_project_id
            principal_id = "api-token"
            if not all(CONTEXT_ID.fullmatch(value) for value in (tenant_id, project_id, principal_id)):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid context identifier")
            return PrincipalContext(tenant_id=tenant_id, project_id=project_id, principal_id=principal_id)
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
        credential = await runtime.access.authenticate_api_key(token)
        if credential is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
        if x_principal_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="principal identity is credential-derived"
            )
        if x_tenant_id and x_tenant_id != credential.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="credential tenant mismatch")
        if x_project_id and x_project_id != credential.project_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="credential project mismatch")
        return credential
    tenant_id = x_tenant_id or settings.default_tenant_id
    project_id = x_project_id or settings.default_project_id
    principal_id = x_principal_id or ("api-token" if settings.auth_required else "anonymous")
    if not all(CONTEXT_ID.fullmatch(value) for value in (tenant_id, project_id, principal_id)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid context identifier")
    return PrincipalContext(tenant_id=tenant_id, project_id=project_id, principal_id=principal_id)


def create_app(settings: Settings | None = None, *, runtime: Runtime | None = None) -> FastAPI:
    runtime = runtime or build_runtime(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await runtime.open()
        try:
            yield
        finally:
            await runtime.close()

    app = FastAPI(
        title="Scenara API",
        version=__version__,
        description="Scenara 景枢企业视觉 AI 中枢平台",
        docs_url="/docs" if not runtime.settings.production else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.state.request_metrics = RequestMetrics()
    console_assets = CONSOLE_DIST / "assets"
    if console_assets.is_dir():
        app.mount("/console/assets", StaticFiles(directory=console_assets), name="console-assets")

    @app.middleware("http")
    async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = request.headers.get("X-Request-Id", f"req_{uuid4().hex}")[:128]
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            route = request.scope.get("route")
            route_path = str(getattr(route, "path", "unmatched"))
            app.state.request_metrics.observe(
                request.method,
                route_path,
                status_code,
                time.perf_counter() - started,
            )
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    def error_response(
        request: Request,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> JSONResponse:
        payload = ApiErrorEnvelope(
            request_id=_request_id(request),
            error=ApiErrorDetail(code=code, message=message, details=details or {}),
        )
        return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))

    def enterprise_service() -> EnterpriseService:
        if runtime.enterprise is None:
            raise HTTPException(status_code=404, detail="enterprise modules are not installed")
        return runtime.enterprise

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error_response(request, exc.status_code, "HTTP_ERROR", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(request, 422, "VALIDATION_ERROR", "request validation failed", {"errors": exc.errors()})

    @app.exception_handler(ResourceNotFound)
    async def not_found(request: Request, exc: ResourceNotFound) -> JSONResponse:
        return error_response(request, 404, "NOT_FOUND", str(exc))

    @app.exception_handler(WebhookNotFound)
    async def webhook_not_found(request: Request, exc: WebhookNotFound) -> JSONResponse:
        return error_response(request, 404, "WEBHOOK_NOT_FOUND", str(exc))

    @app.exception_handler(InvalidTransition)
    async def invalid_transition(request: Request, exc: InvalidTransition) -> JSONResponse:
        return error_response(request, 409, "INVALID_RUN_TRANSITION", str(exc))

    @app.exception_handler(StateConflict)
    async def state_conflict(request: Request, exc: StateConflict) -> JSONResponse:
        return error_response(request, 409, "STATE_CONFLICT", str(exc))

    @app.exception_handler(FeedbackNotFound)
    async def feedback_not_found(request: Request, exc: FeedbackNotFound) -> JSONResponse:
        return error_response(request, 404, "FEEDBACK_NOT_FOUND", str(exc))

    @app.exception_handler(FeedbackConflict)
    async def feedback_conflict(request: Request, exc: FeedbackConflict) -> JSONResponse:
        return error_response(request, 409, "FEEDBACK_CONFLICT", str(exc))

    @app.exception_handler(PortraitNotFound)
    async def portrait_not_found(request: Request, exc: PortraitNotFound) -> JSONResponse:
        return error_response(request, 404, "PORTRAIT_NOT_FOUND", str(exc))

    @app.exception_handler(PortraitConflict)
    async def portrait_conflict(request: Request, exc: PortraitConflict) -> JSONResponse:
        return error_response(request, 409, "PORTRAIT_CONFLICT", str(exc))

    @app.exception_handler(AccessNotFound)
    async def access_not_found(request: Request, exc: AccessNotFound) -> JSONResponse:
        return error_response(request, 404, "ACCESS_NOT_FOUND", str(exc))

    @app.exception_handler(FeatureStoreError)
    async def feature_store_error(request: Request, exc: FeatureStoreError) -> JSONResponse:
        return error_response(request, 409, "FEATURE_SPACE_CONFLICT", str(exc))

    @app.exception_handler(PolicyDenied)
    async def policy_denied(request: Request, exc: PolicyDenied) -> JSONResponse:
        return error_response(request, 403, "POLICY_DENIED", str(exc))

    @app.exception_handler(PolicyUnavailable)
    async def policy_unavailable(request: Request, exc: PolicyUnavailable) -> JSONResponse:
        return error_response(request, 503, "POLICY_UNAVAILABLE", str(exc))

    @app.exception_handler(AuditUnavailable)
    async def audit_unavailable(request: Request, exc: AuditUnavailable) -> JSONResponse:
        return error_response(request, 503, "AUDIT_UNAVAILABLE", str(exc))

    @app.exception_handler(PipelineError)
    async def pipeline_error(request: Request, exc: PipelineError) -> JSONResponse:
        return error_response(request, 422, "PIPELINE_ERROR", str(exc))

    @app.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError) -> JSONResponse:
        return error_response(request, 400, "INVALID_ARGUMENT", str(exc))

    @app.get("/healthz", tags=["Operations"])
    async def health(request: Request) -> ApiEnvelope[dict[str, str]]:
        return _envelope(request, {"status": "ok", "version": __version__})  # type: ignore[return-value]

    @app.get("/livez", tags=["Operations"])
    async def live(request: Request) -> ApiEnvelope[dict[str, str]]:
        return _envelope(request, {"status": "ok", "version": __version__})  # type: ignore[return-value]

    @app.get("/readyz", tags=["Operations"])
    async def ready(request: Request) -> ApiEnvelope[dict[str, object]]:
        try:
            components = await asyncio.wait_for(runtime.health_check(), timeout=5)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="runtime dependency is unavailable") from exc
        return _envelope(request, {"status": "ready", "components": components})  # type: ignore[return-value]

    @app.get("/metrics", include_in_schema=False)
    async def metrics(context: PrincipalContext = Depends(principal_context)) -> Response:
        await require_allowed(runtime.policy, context, "read", "operations")
        return Response(
            content=app.state.request_metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.post("/api/v1/media/assets", status_code=201, tags=["Media"])
    async def create_media_asset(
        request: Request,
        file: Annotated[UploadFile, File()],
        kind: Annotated[MediaKind, Form()] = MediaKind.IMAGE,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaAsset]:
        max_read = (
            runtime.settings.max_image_bytes + 1 if kind == MediaKind.IMAGE else runtime.settings.max_media_bytes + 1
        )
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
        await require_allowed(runtime.policy, context, "list", "media_asset")
        rows = await runtime.state.list_assets(context.tenant_id, context.project_id)
        rows = [item for item in rows if item.deleted_at is None]
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
        await require_allowed(runtime.policy, context, "read", "media_asset", {"asset_id": asset_id})
        asset = await runtime.state.get_asset(context.tenant_id, context.project_id, asset_id)
        if asset is None or asset.deleted_at is not None:
            raise ResourceNotFound("media asset not found")
        return _envelope(request, asset)  # type: ignore[return-value]

    @app.get("/api/v1/media/assets/{asset_id}/preview", tags=["Media"])
    async def get_media_asset_preview(
        asset_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        data, content_type = await runtime.runs.get_asset_preview(context, asset_id)
        return Response(content=data, media_type=content_type)

    @app.delete("/api/v1/media/assets/{asset_id}", status_code=204, tags=["Media"])
    async def delete_media_asset(
        asset_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.runs.delete_asset(context, asset_id)
        return Response(status_code=204)

    @app.post("/api/v1/media/sources", status_code=201, tags=["Media"])
    async def create_media_source(
        body: CreateMediaSourceRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaSourceView]:
        source = await runtime.runs.create_source(context, body)
        return _envelope(request, _media_source_view(source))  # type: ignore[return-value]

    @app.get("/api/v1/media/sources", tags=["Media"])
    async def list_media_sources(
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaSourcePage]:
        await require_allowed(runtime.policy, context, "list", "media_source")
        rows = await runtime.state.list_sources(context.tenant_id, context.project_id)
        return _envelope(
            request,
            MediaSourcePage(
                items=[_media_source_view(item) for item in rows[offset : offset + limit]],
                offset=offset,
                limit=limit,
                total=len(rows),
            ),
        )  # type: ignore[return-value]

    @app.get("/api/v1/media/sources/{source_id}", tags=["Media"])
    async def get_media_source(
        source_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaSourceView]:
        source = await runtime.runs.get_source(context, source_id)
        return _envelope(request, _media_source_view(source))  # type: ignore[return-value]

    @app.post("/api/v1/media/sources/{source_id}/probe", tags=["Media"])
    async def probe_media_source(
        source_id: str,
        request: Request,
        timeout_ms: Annotated[int, Query(ge=100, le=30_000)] = 10_000,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaSourceProbe]:
        return _envelope(
            request,
            await runtime.runs.probe_source(context, source_id, timeout_ms=timeout_ms),
        )  # type: ignore[return-value]

    @app.delete("/api/v1/media/sources/{source_id}", status_code=204, tags=["Media"])
    async def delete_media_source(
        source_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.runs.delete_source(context, source_id)
        return Response(status_code=204)

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

    async def lifecycle(
        run_id: str, action: str, request: Request, context: PrincipalContext
    ) -> ApiEnvelope[RunRecord]:
        return _envelope(request, await runtime.runs.transition(context, run_id, action))  # type: ignore[return-value]

    @app.post("/api/v1/runs/{run_id}/cancel", tags=["Runs"])
    async def cancel_run(
        run_id: str, request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[RunRecord]:
        return await lifecycle(run_id, "cancel", request, context)

    @app.post("/api/v1/runs/{run_id}/pause", tags=["Runs"])
    async def pause_run(
        run_id: str, request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[RunRecord]:
        return await lifecycle(run_id, "pause", request, context)

    @app.post("/api/v1/runs/{run_id}/resume", tags=["Runs"])
    async def resume_run(
        run_id: str, request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[RunRecord]:
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
        selected_pipeline = pipeline_id or ("portrait.person-detection" if domain == "portrait" else "ocr.document")
        selected_pipeline_ref = await runtime.runs.resolve_pipeline_ref(selected_pipeline, pipeline_version)
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
        return _envelope(request, ParseImageResponse(asset=asset, run=outcome.run, result=result))  # type: ignore[return-value]

    @app.post("/api/v1/parse/video", status_code=202, tags=["Parsing"])
    async def parse_video(
        request: Request,
        file: Annotated[UploadFile, File()],
        domain: Annotated[Literal["portrait", "ocr"], Form()] = "portrait",
        pipeline_id: Annotated[str | None, Form()] = None,
        pipeline_version: Annotated[str | None, Form()] = None,
        sample_interval_ms: Annotated[int, Form(ge=1, le=3_600_000)] = 1000,
        max_units: Annotated[int, Form(ge=1, le=10_000)] = 64,
        sample_strategy: Annotated[SampleStrategy, Form()] = SampleStrategy.INTERVAL,
        sample_start_ms: Annotated[int, Form(ge=0)] = 0,
        sample_end_ms: Annotated[int | None, Form(ge=0)] = None,
        scene_change_threshold: Annotated[float, Form(ge=0.01, le=1.0)] = 0.35,
        frame_max_edge: Annotated[int | None, Form(ge=64, le=8192)] = None,
        page_scale: Annotated[float, Form(ge=0.5, le=4.0)] = 1.5,
        wait_ms: Annotated[int, Form(ge=0, le=30_000)] = 0,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ParseVideoResponse]:
        data = await file.read(runtime.settings.max_media_bytes + 1)
        asset = await runtime.runs.create_asset(
            context,
            data=data,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            kind=MediaKind.VIDEO,
            temporary=True,
        )
        selected_pipeline = pipeline_id or ("portrait.person-detection" if domain == "portrait" else "ocr.document")
        selected_pipeline_ref = await runtime.runs.resolve_pipeline_ref(selected_pipeline, pipeline_version)
        params: dict[str, object] = {
            "sample_interval_ms": sample_interval_ms,
            "max_units": max_units,
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
        return _envelope(
            request,
            ParseVideoResponse(asset=asset, run=outcome.run, result=result),
        )  # type: ignore[return-value]

    @app.post("/api/v1/parse/document", status_code=202, tags=["Parsing"])
    async def parse_document(
        request: Request,
        file: Annotated[UploadFile, File()],
        domain: Annotated[Literal["portrait", "ocr"], Form()] = "ocr",
        pipeline_id: Annotated[str | None, Form()] = None,
        pipeline_version: Annotated[str | None, Form()] = None,
        max_units: Annotated[int, Form(ge=1, le=1000)] = 64,
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
        selected_pipeline = pipeline_id or ("portrait.person-detection" if domain == "portrait" else "ocr.document")
        selected_pipeline_ref = await runtime.runs.resolve_pipeline_ref(selected_pipeline, pipeline_version)
        outcome = await runtime.runs.create_run(
            context,
            CreateRunRequest(
                domain=domain,
                pipeline=selected_pipeline_ref,
                asset_id=asset.asset_id,
                parameters={"max_units": max_units, "page_scale": page_scale},
                wait_ms=wait_ms,
            ),
            idempotency_key=idempotency_key or f"shortcut_{uuid4().hex}",
        )
        result = None
        if outcome.run.status == RunStatus.COMPLETED:
            result = await runtime.runs.result(context, outcome.run.run_id)
        return _envelope(
            request,
            ParseDocumentResponse(asset=asset, run=outcome.run, result=result),
        )  # type: ignore[return-value]

    @app.post("/api/v1/parse/stream", status_code=202, tags=["Parsing"])
    async def parse_stream(
        body: ParseStreamRequest,
        request: Request,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[RunRecord]:
        pipeline = await runtime.runs.resolve_pipeline_ref(body.pipeline.pipeline_id, body.pipeline.version)
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
        return _envelope(request, outcome.run)  # type: ignore[return-value]

    @app.post("/api/v1/portrait/identities", status_code=201, tags=["Portrait"])
    async def create_portrait_identity(
        body: CreateIdentityRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitIdentity]:
        identity = await runtime.portrait.create_identity(context, body)
        return _envelope(request, identity)  # type: ignore[return-value]

    @app.get("/api/v1/portrait/identities", tags=["Portrait"])
    async def list_portrait_identities(
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitIdentityPage]:
        page = await runtime.portrait.list_identities(context, offset=offset, limit=limit)
        return _envelope(request, page)  # type: ignore[return-value]

    @app.get("/api/v1/portrait/identities/{identity_id}", tags=["Portrait"])
    async def get_portrait_identity(
        identity_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitIdentity]:
        identity = await runtime.portrait.get_identity(context, identity_id)
        return _envelope(request, identity)  # type: ignore[return-value]

    @app.delete("/api/v1/portrait/identities/{identity_id}", status_code=204, tags=["Portrait"])
    async def delete_portrait_identity(
        identity_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.portrait.delete_identity(context, identity_id)
        return Response(status_code=204)

    @app.post(
        "/api/v1/portrait/identities/{identity_id}/enrollments",
        status_code=201,
        tags=["Portrait"],
    )
    async def enroll_portrait_identity(
        identity_id: str,
        body: EnrollIdentityRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitEnrollment]:
        enrollment = await runtime.portrait.enroll(context, identity_id, body)
        return _envelope(request, enrollment)  # type: ignore[return-value]

    @app.post("/api/v1/portrait/search", tags=["Portrait"])
    async def search_portrait_identities(
        body: PortraitSearchRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitSearchResponse]:
        result = await runtime.portrait.search(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/portrait/compare", tags=["Portrait"])
    async def compare_portrait_features(
        body: PortraitCompareRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitCompareResponse]:
        result = await runtime.portrait.compare(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get("/api/v1/enterprise/status", tags=["Enterprise"])
    async def enterprise_status(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[EnterpriseStatus]:
        result = await enterprise_service().status(context)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/enterprise/sla/evaluate", tags=["Enterprise"])
    async def enterprise_sla(
        body: dict[str, float],
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SlaSnapshot]:
        result = await enterprise_service().sla(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get("/api/v1/enterprise/incidents", tags=["Enterprise"])
    async def list_enterprise_incidents(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[Incident]]:
        rows = await enterprise_service().list_incidents(context)
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.post("/api/v1/enterprise/incidents", status_code=201, tags=["Enterprise"])
    async def create_enterprise_incident(
        body: CreateIncidentRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Incident]:
        result = await enterprise_service().create_incident(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/enterprise/incidents/{incident_id}/resolve", tags=["Enterprise"])
    async def resolve_enterprise_incident(
        incident_id: str,
        body: ResolveIncidentRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Incident]:
        result = await enterprise_service().resolve_incident(context, incident_id, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get("/api/v1/enterprise/support/cases", tags=["Enterprise"])
    async def list_enterprise_support_cases(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[SupportCase]]:
        rows = await enterprise_service().list_support_cases(context)
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.post("/api/v1/enterprise/support/cases", status_code=201, tags=["Enterprise"])
    async def create_enterprise_support_case(
        body: CreateSupportCaseRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SupportCase]:
        result = await enterprise_service().create_support_case(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get("/api/v1/enterprise/compliance/evidence", tags=["Enterprise"])
    async def list_enterprise_evidence(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[ComplianceEvidence]]:
        rows = await enterprise_service().list_evidence(context)
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.post(
        "/api/v1/enterprise/compliance/evidence",
        status_code=201,
        tags=["Enterprise"],
    )
    async def create_enterprise_evidence(
        body: CreateComplianceEvidenceRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ComplianceEvidence]:
        result = await enterprise_service().create_evidence(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get("/api/v1/pipelines", tags=["Pipelines"])
    async def list_pipelines(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[dict[str, object]]]:
        await require_allowed(runtime.policy, context, "list", "pipeline")
        rows = [pipeline.model_dump(mode="json") for pipeline in await runtime.runs.sync_pipeline_catalog()]
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.post("/api/v1/pipelines/{pipeline_id}/versions/{version}/transition", tags=["Pipelines"])
    async def transition_pipeline(
        pipeline_id: str,
        version: str,
        body: PipelineTransitionRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[dict[str, object]]:
        pipeline = await runtime.runs.transition_pipeline(context, pipeline_id, version, body.status)
        return _envelope(request, pipeline.model_dump(mode="json"))  # type: ignore[return-value]

    @app.post("/api/v1/feedback", status_code=201, tags=["Feedback"])
    async def create_feedback(
        body: CreateFeedbackRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[FeedbackRecord]:
        result = await runtime.feedback.create(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get("/api/v1/feedback", tags=["Feedback"])
    async def list_feedback(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[FeedbackRecord]]:
        rows = await runtime.feedback.feedback_records(context)
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.post("/api/v1/feedback/{feedback_id}/review", tags=["Feedback"])
    async def review_feedback(
        feedback_id: str,
        body: ReviewFeedbackRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[FeedbackRecord]:
        result = await runtime.feedback.review(context, feedback_id, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/hard-sample-manifests", status_code=201, tags=["Feedback"])
    async def create_hard_sample_manifest(
        body: CreateHardSampleManifestRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[HardSampleManifest]:
        result = await runtime.feedback.create_manifest(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get("/api/v1/hard-sample-manifests", tags=["Feedback"])
    async def list_hard_sample_manifests(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[HardSampleManifest]]:
        rows = await runtime.feedback.list_manifests(context)
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.post("/api/v1/model-releases", status_code=201, tags=["Model Governance"])
    async def create_model_release(
        body: CreateModelReleaseRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ModelRelease]:
        result = await runtime.feedback.create_release(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/model-packages/admissions", status_code=201, tags=["Model Governance"])
    async def admit_model_package(
        body: ModelPackageManifest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ModelPackageManifest]:
        result = await runtime.feedback.admit_package(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get("/api/v1/model-releases", tags=["Model Governance"])
    async def list_model_releases(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[ModelRelease]]:
        rows = await runtime.feedback.list_releases(context)
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.post(
        "/api/v1/model-releases/{model_id}/versions/{version}/transition",
        tags=["Model Governance"],
    )
    async def transition_model_release(
        model_id: str,
        version: str,
        body: TransitionModelReleaseRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ModelRelease]:
        result = await runtime.feedback.transition_release(context, model_id, version, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/model-releases/{model_id}/rollback", tags=["Model Governance"])
    async def rollback_model_release(
        model_id: str,
        body: RollbackModelReleaseRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ModelRelease]:
        result = await runtime.feedback.rollback(context, model_id, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get("/api/v1/model-deployment-events", tags=["Model Governance"])
    async def list_model_deployment_events(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[ModelDeploymentEvent]]:
        rows = await runtime.feedback.deployment_events(context, limit)
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.post("/api/v1/webhooks/subscriptions", status_code=201, tags=["Webhooks"])
    async def create_webhook_subscription(
        body: CreateWebhookSubscriptionRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[WebhookSubscriptionView]:
        endpoint = await runtime.webhooks.create(context, body)
        return _envelope(request, endpoint)  # type: ignore[return-value]

    @app.get("/api/v1/webhooks/subscriptions", tags=["Webhooks"])
    async def list_webhook_subscriptions(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[WebhookSubscriptionView]]:
        rows = await runtime.webhooks.subscriptions(context)
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.delete("/api/v1/webhooks/subscriptions/{endpoint_id}", status_code=204, tags=["Webhooks"])
    async def delete_webhook_subscription(
        endpoint_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.webhooks.delete(context, endpoint_id)
        return Response(status_code=204)

    @app.get("/api/v1/webhooks/deliveries", tags=["Webhooks"])
    async def list_webhook_deliveries(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[WebhookDeliveryRecord]]:
        rows = await runtime.webhooks.deliveries(context, limit=limit)
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.get("/api/v1/models", tags=["Models"])
    async def list_models(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[dict[str, object]]]:
        await require_allowed(runtime.policy, context, "list", "model_package")
        rows = [package.model_dump(mode="json") for package in await runtime.state.list_model_packages()]
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.get("/api/v1/domains", tags=["Domains"])
    async def list_domains(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[dict[str, object]]]:
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

    @app.get("/api/v1/platform/products", tags=["Platform"])
    async def list_platform_products(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[ProductCatalogItem]]:
        del context
        installed_domains = [manifest.domain_id for manifest in runtime.plugins.manifests()]
        return _envelope(request, build_product_catalog(installed_domains))  # type: ignore[return-value]

    @app.get("/api/v1/platform/repositories", tags=["Platform"])
    async def platform_repository_topology(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[RepositoryTopology]:
        del context
        return _envelope(request, build_repository_topology())  # type: ignore[return-value]

    @app.get("/api/v1/platform/contracts", tags=["Platform"])
    async def platform_repository_contracts(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[RepositoryContractCatalog]:
        del context
        return _envelope(request, load_repository_contract_catalog())  # type: ignore[return-value]

    @app.get("/api/v1/platform/contracts/{contract_id}/schema", tags=["Platform"])
    async def platform_repository_contract_schema(
        contract_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> FileResponse:
        del context
        catalog = load_repository_contract_catalog()
        artifact = next((item for item in catalog.contracts if item.contract_id == contract_id), None)
        if artifact is None:
            raise HTTPException(status_code=404, detail="repository contract not found")
        schema_path = CONTRACT_ROOT / Path(artifact.schema_path).name
        return FileResponse(
            schema_path,
            media_type="application/schema+json",
            filename=schema_path.name,
            headers={"ETag": f'"sha256:{artifact.schema_sha256}"'},
        )

    @app.get("/api/v1/platform/access-foundation", tags=["Platform"])
    async def platform_access_foundation(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[AccessFoundationStatus]:
        return _envelope(
            request,
            build_access_foundation(runtime.settings, context, policy_provider=runtime.policy.provider_id),
        )  # type: ignore[return-value]

    @app.get("/api/v1/platform/portrait-intelligence", tags=["Platform"])
    async def platform_portrait_intelligence(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[PortraitIntelligenceStatus]:
        """Portrait Intelligence Foundation Platform contract.

        Returns the six strategic modules, three core assets, and per-capability
        readiness state derived from the installed model-capabilities configuration.
        This endpoint reflects *intent and current readiness*, not deployed model
        quality.  Refer to ``model-capabilities.yml`` for the authoritative
        capability status used at inference time.
        """
        del context
        installed_domains = [manifest.domain_id for manifest in runtime.plugins.manifests()]
        snapshot: dict[str, CapabilitySnapshot] = {}
        if "portrait" in installed_domains:
            try:
                from app.portrait_model_capabilities import capability_status as _cap_status
                from app.portrait_model_capabilities import production_model_ready as _prod_ready
                from scenara.platform.portrait_intelligence import PORTRAIT_CAPABILITY_IDS

                for cap_id in PORTRAIT_CAPABILITY_IDS:
                    cap = _cap_status(cap_id)
                    snapshot[cap_id] = CapabilitySnapshot(
                        readiness=cap.get("status", "not_configured"),
                        production_ready=bool(_prod_ready(cap_id)),
                        current_model=cap.get("model_id") or None,
                        target_model=cap.get("production_model") or None,
                        embedding_dimension=cap.get("embedding_dim") or None,
                        target_embedding_dimension=cap.get("production_embedding_dim") or None,
                    )
            except Exception:  # pragma: no cover — app layer may not be installed
                pass
        return _envelope(  # type: ignore[return-value]
            request,
            build_portrait_intelligence(snapshot, installed_domains=installed_domains),
        )

    @app.get("/api/v1/platform/iam/summary", tags=["IAM"])
    async def iam_summary(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[IamSummary]:
        return _envelope(request, await runtime.access.summary(context))  # type: ignore[return-value]

    @app.post("/api/v1/platform/organizations", status_code=201, tags=["IAM"])
    async def create_organization(
        body: CreateOrganizationRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Organization]:
        return _envelope(request, await runtime.access.create_organization(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/platform/organizations", tags=["IAM"])
    async def list_organizations(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[Organization]]:
        return _envelope(request, await runtime.access.list_organizations(context))  # type: ignore[return-value]

    @app.post("/api/v1/platform/projects", status_code=201, tags=["IAM"])
    async def create_project(
        body: CreateProjectRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Project]:
        return _envelope(request, await runtime.access.create_project(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/platform/projects", tags=["IAM"])
    async def list_projects(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[Project]]:
        return _envelope(request, await runtime.access.list_projects(context))  # type: ignore[return-value]

    @app.post("/api/v1/platform/users", status_code=201, tags=["IAM"])
    async def create_user(
        body: CreateUserRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[UserAccount]:
        return _envelope(request, await runtime.access.create_user(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/platform/users", tags=["IAM"])
    async def list_users(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[UserAccount]]:
        return _envelope(request, await runtime.access.list_users(context))  # type: ignore[return-value]

    @app.post("/api/v1/platform/roles", status_code=201, tags=["IAM"])
    async def create_role(
        body: CreateRoleRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Role]:
        return _envelope(request, await runtime.access.create_role(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/platform/roles", tags=["IAM"])
    async def list_roles(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[Role]]:
        return _envelope(request, await runtime.access.list_roles(context))  # type: ignore[return-value]

    @app.post("/api/v1/platform/memberships", status_code=201, tags=["IAM"])
    async def create_membership(
        body: CreateMembershipRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Membership]:
        return _envelope(request, await runtime.access.create_membership(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/platform/memberships", tags=["IAM"])
    async def list_memberships(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[Membership]]:
        return _envelope(request, await runtime.access.list_memberships(context))  # type: ignore[return-value]

    @app.post("/api/v1/platform/service-accounts", status_code=201, tags=["IAM"])
    async def create_service_account(
        body: CreateServiceAccountRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ServiceAccount]:
        return _envelope(request, await runtime.access.create_service_account(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/platform/service-accounts", tags=["IAM"])
    async def list_service_accounts(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[ServiceAccount]]:
        return _envelope(request, await runtime.access.list_service_accounts(context))  # type: ignore[return-value]

    @app.post("/api/v1/platform/service-accounts/{service_account_id}/api-keys", status_code=201, tags=["IAM"])
    async def create_api_key(
        service_account_id: str,
        body: CreateApiKeyRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[CreateApiKeyResponse]:
        return _envelope(
            request,
            await runtime.access.create_api_key(context, service_account_id, body),
        )  # type: ignore[return-value]

    @app.get("/api/v1/platform/api-keys", tags=["IAM"])
    async def list_api_keys(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[ApiKeyRecord]]:
        return _envelope(request, await runtime.access.list_api_keys(context))  # type: ignore[return-value]

    @app.post("/api/v1/platform/api-keys/{key_id}/revoke", tags=["IAM"])
    async def revoke_api_key(
        key_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ApiKeyRecord]:
        return _envelope(request, await runtime.access.revoke_api_key(context, key_id))  # type: ignore[return-value]

    @app.post("/api/v1/platform/product-entitlements", status_code=201, tags=["IAM"])
    async def create_product_entitlement(
        body: CreateProductEntitlementRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ProductEntitlement]:
        return _envelope(
            request,
            await runtime.access.create_product_entitlement(context, body),
        )  # type: ignore[return-value]

    @app.get("/api/v1/platform/product-entitlements", tags=["IAM"])
    async def list_product_entitlements(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[ProductEntitlement]]:
        return _envelope(request, await runtime.access.list_product_entitlements(context))  # type: ignore[return-value]

    @app.put("/api/v1/platform/product-entitlements/{product_id}", tags=["IAM"])
    async def update_product_entitlement(
        product_id: str,
        body: UpdateProductEntitlementRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ProductEntitlement]:
        return _envelope(
            request,
            await runtime.access.update_product_entitlement(context, product_id, body),
        )  # type: ignore[return-value]

    @app.get("/api/v1/system/status", tags=["Operations"])
    async def system_status(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SystemStatus]:
        await require_allowed(runtime.policy, context, "read", "operations")
        settings = runtime.settings
        return _envelope(
            request,
            SystemStatus(
                version=__version__,
                profile=settings.profile,
                state_backend=settings.state_backend,
                object_backend=settings.object_backend,
                queue_backend=settings.queue_backend,
                production_models_required=settings.production_models_required,
                auth_required=settings.auth_required,
                enterprise_policy_provider=runtime.policy.provider_id,
            ),
        )  # type: ignore[return-value]

    def console_file(name: str) -> FileResponse:
        target = CONSOLE_DIST / name
        if not target.is_file():
            raise HTTPException(status_code=503, detail="console static bundle is not installed")
        return FileResponse(target, headers=CONSOLE_SECURITY_HEADERS)

    @app.get("/", include_in_schema=False)
    async def console_redirect() -> RedirectResponse:
        return RedirectResponse(url="/console/", status_code=307)

    @app.get("/console/favicon.svg", include_in_schema=False)
    async def console_favicon() -> FileResponse:
        return console_file("favicon.svg")

    @app.get("/console", include_in_schema=False)
    @app.get("/console/", include_in_schema=False)
    @app.get("/console/{path:path}", include_in_schema=False)
    async def console_application(path: str = "") -> FileResponse:
        del path
        return console_file("index.html")

    return app


app = create_app()

__all__ = ["app", "create_app"]
