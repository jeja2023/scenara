from __future__ import annotations

import asyncio
import hmac
import re
import sys
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, TypeVar
from uuid import uuid4


from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
)
from starlette.middleware.base import RequestResponseEndpoint
from starlette.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from scenara.platform.log_context import (
    new_traceparent,
    normalize_request_id,
    reset_log_context,
    set_log_context,
    traceparent_from_headers,
)
from scenara import __version__
from scenara.api.routers.audit import build_audit_router
from scenara.api.routers.access import build_access_router
from scenara.api.routers.catalog import build_catalog_router
from scenara.api.routers.datasets import build_datasets_router
from scenara.api.routers.media import build_media_router
from scenara.api.routers.runs import build_runs_router
from scenara.api.routers.surveillance import build_surveillance_router
from scenara.api.routers.iam import build_iam_router
from scenara.api.routers.data_governance import build_data_governance_router
from scenara.api.routers.flows import build_flows_router
from scenara.api.routers.portrait_intelligence import build_portrait_intelligence_router
from scenara.api.routers.edge import build_edge_router
from scenara.api.routers.agents import build_agents_router
from scenara.api.routers.operations import build_operations_router
from scenara.api.routers.parse import build_parse_router
from scenara.api.routers.portrait import build_portrait_router
from scenara.api.routers.search import build_search_router
from scenara.api.routers.enterprise import build_enterprise_router
from scenara.api.routers.feedback import build_feedback_router
from scenara.bootstrap import Runtime, build_runtime
from scenara.domains.portrait.encoder import PortraitEncodingError
from scenara.domains.portrait.service import (
    PortraitConflict,
    PortraitNotFound,
)
from scenara.domains.portrait.trajectory import (
    TrajectoryConflict,
    TrajectoryNotFound,
)
from scenara.platform.surveillance import SurveillanceConflict, SurveillanceNotFound
from scenara.enterprise.service import (
    EnterpriseService,
)
from scenara.platform.access import AccessNotFound
from scenara.platform.audit import AuditUnavailable
from scenara.platform.data_platform import DataPlatformRemoteError
from scenara.platform.error_codes import registered_error_code
from scenara.platform.data_events import DataEventEnvelope
from scenara.platform.dataset import DatasetConflict, DatasetNotFound
from scenara.platform.features import FeatureStoreError
from scenara.platform.feedback import (
    FeedbackConflict,
    FeedbackNotFound,
)
from scenara.platform.index import (
    IndexStoreError,
)

from scenara.platform.objects import (
    ObjectAlreadyExistsError,
    ObjectIntegrityError,
    ObjectStoreCapabilityError,
)
from scenara.platform.models import (
    ApiEnvelope,
    ApiErrorDetail,
    ApiErrorEnvelope,
    PrincipalContext,
)
from scenara.platform.observability import RequestMetrics
from scenara.platform.pipeline import PipelineError
from scenara.platform.policy import PolicyDenied, PolicyUnavailable, require_allowed
from scenara.platform.search import (
    SavedSearchConflict,
    SavedSearchNotFound,
)
from scenara.platform.services import InvalidTransition, ResourceNotFound
from scenara.platform.store import StateConflict
from scenara.platform.webhook_service import WebhookNotFound
from scenara.settings import Settings

if sys.platform == "win32" and sys.version_info < (3, 14):
    # psycopg's async connection pool requires selector-based I/O on Windows.
    _set_policy = getattr(asyncio, "set_event_loop_policy", None)
    _selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if callable(_set_policy) and callable(_selector_policy):
        _set_policy(_selector_policy())


CONTEXT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
PRESIGN_UPLOAD_EXPIRY_GRACE_SECONDS = 60
CONSOLE_DIST = Path(__file__).resolve().parents[1] / "frontend" / "console" / "dist"
CONSOLE_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; connect-src 'self' http: https:; img-src 'self' data: blob:; "
        "media-src 'self' blob:; style-src 'self'; script-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
}


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", f"req_{uuid4().hex}"))


_T = TypeVar("_T")


def _envelope(request: Request, data: _T) -> ApiEnvelope[_T]:
    return ApiEnvelope(request_id=_request_id(request), data=data)


async def principal_context(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_principal_id: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header()] = None,
    x_project_id: Annotated[str | None, Header()] = None,
) -> PrincipalContext:
    runtime: Runtime = request.app.state.runtime
    settings = runtime.settings

    def bind_context(context: PrincipalContext) -> PrincipalContext:
        request_id = _request_id(request)
        traceparent = getattr(request.state, "traceparent", None)
        return context.model_copy(
            update={"request_id": request_id, "traceparent": traceparent}
        )

    if settings.auth_required or authorization:
        expected = f"Bearer {settings.api_token}"
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token"
            )
        if hmac.compare_digest(authorization, expected):
            if x_principal_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="principal identity is credential-derived",
                )
            tenant_id = x_tenant_id or settings.default_tenant_id
            project_id = x_project_id or settings.default_project_id
            principal_id = "api-token"
            if not all(
                CONTEXT_ID.fullmatch(value)
                for value in (tenant_id, project_id, principal_id)
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="invalid context identifier",
                )
            return bind_context(
                PrincipalContext(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    principal_id=principal_id,
                    request_id=_request_id(request),
                    traceparent=getattr(request.state, "traceparent", None),
                )
            )
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token"
            )
        credential = await runtime.access.authenticate_api_key(token)
        if credential is None:
            session_context = await runtime.control_plane.authenticate_session(token)
            if session_context is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="invalid bearer token",
                )
            if await runtime.access.is_user_disabled(
                session_context.tenant_id, session_context.principal_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="user session is disabled",
                )
            if x_principal_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="principal identity is credential-derived",
                )
            if x_tenant_id and x_tenant_id != session_context.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="session tenant mismatch",
                )
            if x_project_id and x_project_id != session_context.project_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="session project mismatch",
                )
            return bind_context(session_context)
        if x_principal_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="principal identity is credential-derived",
            )
        if x_tenant_id and x_tenant_id != credential.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="credential tenant mismatch",
            )
        if x_project_id and x_project_id != credential.project_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="credential project mismatch",
            )
        return bind_context(credential)
    tenant_id = x_tenant_id or settings.default_tenant_id
    project_id = x_project_id or settings.default_project_id
    principal_id = x_principal_id or (
        "api-token" if settings.auth_required else "anonymous"
    )
    if not all(
        CONTEXT_ID.fullmatch(value) for value in (tenant_id, project_id, principal_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid context identifier"
        )
    return bind_context(
        PrincipalContext(
            tenant_id=tenant_id,
            project_id=project_id,
            principal_id=principal_id,
            request_id=_request_id(request),
            traceparent=getattr(request.state, "traceparent", None),
        )
    )


def create_app(
    settings: Settings | None = None, *, runtime: Runtime | None = None
) -> FastAPI:
    runtime = runtime or build_runtime(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        await runtime.open()
        try:
            yield
        finally:
            await runtime.close()

    app = FastAPI(
        title="Scenara API",
        version=__version__,
        description="Scenara 景枢视觉 AI 中枢平台",
        docs_url="/docs" if not runtime.settings.production else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.state.request_metrics = RequestMetrics()
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=list(runtime.settings.allowed_hosts)
    )
    console_assets = CONSOLE_DIST / "assets"
    if console_assets.is_dir():
        app.mount(
            "/console/assets",
            StaticFiles(directory=console_assets),
            name="console-assets",
        )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request.state.request_id = (
            normalize_request_id(request.headers.get("X-Request-Id"))
            or f"req_{uuid4().hex}"
        )
        traceparent = traceparent_from_headers(request)
        if traceparent is None:
            traceparent = new_traceparent()
        request.state.traceparent = traceparent
        log_tokens = set_log_context(
            request_id=request.state.request_id,
            tenant_id=request.headers.get("X-Scenara-Tenant-Id")
            or request.headers.get("X-Tenant-Id"),
            traceparent=traceparent,
        )
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
            reset_log_context(log_tokens)
        response.headers["X-Request-Id"] = request.state.request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if runtime.settings.hsts_enabled:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={runtime.settings.hsts_max_age_seconds}; includeSubDomains",
            )
        return response

    app.include_router(build_audit_router(runtime, principal_context, _envelope))
    app.include_router(build_access_router(runtime, principal_context, _envelope))
    app.include_router(build_catalog_router(runtime, principal_context, _envelope))
    app.include_router(build_datasets_router(runtime, principal_context, _envelope))
    app.include_router(build_media_router(runtime, principal_context, _envelope))
    app.include_router(build_runs_router(runtime, principal_context, _envelope))
    app.include_router(build_surveillance_router(runtime, principal_context, _envelope))
    app.include_router(build_parse_router(runtime, principal_context, _envelope))
    app.include_router(build_portrait_router(runtime, principal_context, _envelope))
    app.include_router(build_search_router(runtime, principal_context, _envelope))
    app.include_router(build_enterprise_router(runtime, principal_context, _envelope))
    app.include_router(build_feedback_router(runtime, principal_context, _envelope))
    app.include_router(build_iam_router(runtime, principal_context, _envelope))
    app.include_router(
        build_data_governance_router(runtime, principal_context, _envelope)
    )
    app.include_router(build_flows_router(runtime, principal_context, _envelope))
    app.include_router(
        build_portrait_intelligence_router(runtime, principal_context, _envelope)
    )
    app.include_router(build_edge_router(runtime, principal_context, _envelope))
    app.include_router(build_agents_router(runtime, principal_context, _envelope))
    app.include_router(build_operations_router(runtime, principal_context, _envelope))

    def error_response(
        request: Request,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> JSONResponse:
        payload = ApiErrorEnvelope(
            request_id=_request_id(request),
            error=ApiErrorDetail(
                code=registered_error_code(code), message=message, details=details or {}
            ),
        )
        if payload.error.code == "INTERNAL_SERVER_ERROR":
            payload = payload.model_copy(
                update={
                    "error": payload.error.model_copy(
                        update={"message": "internal server error"}
                    )
                }
            )
        return JSONResponse(
            status_code=status_code, content=payload.model_dump(mode="json")
        )

    def enterprise_service() -> EnterpriseService:
        if runtime.enterprise is None:
            raise HTTPException(
                status_code=404, detail="enterprise modules are not installed"
            )
        return runtime.enterprise

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        detail_msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return error_response(request, exc.status_code, "HTTP_ERROR", detail_msg)

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            request,
            422,
            "VALIDATION_ERROR",
            "request validation failed",
            {"errors": exc.errors()},
        )

    @app.exception_handler(ResourceNotFound)
    async def not_found(request: Request, exc: ResourceNotFound) -> JSONResponse:
        return error_response(request, 404, "NOT_FOUND", str(exc))

    @app.exception_handler(WebhookNotFound)
    async def webhook_not_found(request: Request, exc: WebhookNotFound) -> JSONResponse:
        return error_response(request, 404, "WEBHOOK_NOT_FOUND", str(exc))

    @app.exception_handler(InvalidTransition)
    async def invalid_transition(
        request: Request, exc: InvalidTransition
    ) -> JSONResponse:
        return error_response(request, 409, "INVALID_RUN_TRANSITION", str(exc))

    @app.exception_handler(StateConflict)
    async def state_conflict(request: Request, exc: StateConflict) -> JSONResponse:
        return error_response(request, 409, "STATE_CONFLICT", str(exc))

    @app.exception_handler(FeedbackNotFound)
    async def feedback_not_found(
        request: Request, exc: FeedbackNotFound
    ) -> JSONResponse:
        return error_response(request, 404, "FEEDBACK_NOT_FOUND", str(exc))

    @app.exception_handler(FeedbackConflict)
    async def feedback_conflict(
        request: Request, exc: FeedbackConflict
    ) -> JSONResponse:
        return error_response(request, 409, "FEEDBACK_CONFLICT", str(exc))

    @app.exception_handler(PortraitNotFound)
    async def portrait_not_found(
        request: Request, exc: PortraitNotFound
    ) -> JSONResponse:
        return error_response(request, 404, "PORTRAIT_NOT_FOUND", str(exc))

    @app.exception_handler(PortraitConflict)
    async def portrait_conflict(
        request: Request, exc: PortraitConflict
    ) -> JSONResponse:
        return error_response(request, 409, "PORTRAIT_CONFLICT", str(exc))

    @app.exception_handler(PortraitEncodingError)
    async def portrait_encoding_error(
        request: Request, exc: PortraitEncodingError
    ) -> JSONResponse:
        return error_response(request, 422, "PORTRAIT_ENCODING_ERROR", str(exc))

    @app.exception_handler(TrajectoryNotFound)
    async def trajectory_not_found(
        request: Request, exc: TrajectoryNotFound
    ) -> JSONResponse:
        return error_response(request, 404, "TRAJECTORY_NOT_FOUND", str(exc))

    @app.exception_handler(TrajectoryConflict)
    async def trajectory_conflict(
        request: Request, exc: TrajectoryConflict
    ) -> JSONResponse:
        return error_response(request, 409, "TRAJECTORY_CONFLICT", str(exc))

    @app.exception_handler(SurveillanceNotFound)
    async def surveillance_not_found(
        request: Request, exc: SurveillanceNotFound
    ) -> JSONResponse:
        return error_response(request, 404, "SURVEILLANCE_NOT_FOUND", str(exc))

    @app.exception_handler(SurveillanceConflict)
    async def surveillance_conflict(
        request: Request, exc: SurveillanceConflict
    ) -> JSONResponse:
        return error_response(request, 409, "SURVEILLANCE_CONFLICT", str(exc))

    @app.exception_handler(DatasetNotFound)
    async def dataset_not_found(request: Request, exc: DatasetNotFound) -> JSONResponse:
        return error_response(request, 404, "DATASET_NOT_FOUND", str(exc))

    @app.exception_handler(DatasetConflict)
    async def dataset_conflict(request: Request, exc: DatasetConflict) -> JSONResponse:
        return error_response(request, 409, "DATASET_CONFLICT", str(exc))

    @app.exception_handler(DataPlatformRemoteError)
    async def data_platform_error(
        request: Request, exc: DataPlatformRemoteError
    ) -> JSONResponse:
        return error_response(request, exc.status_code, exc.code, str(exc), exc.details)

    @app.exception_handler(SavedSearchNotFound)
    async def saved_search_not_found(
        request: Request, exc: SavedSearchNotFound
    ) -> JSONResponse:
        return error_response(request, 404, "SAVED_SEARCH_NOT_FOUND", str(exc))

    @app.exception_handler(SavedSearchConflict)
    async def saved_search_conflict(
        request: Request, exc: SavedSearchConflict
    ) -> JSONResponse:
        return error_response(request, 409, "SAVED_SEARCH_CONFLICT", str(exc))

    @app.exception_handler(AccessNotFound)
    async def access_not_found(request: Request, exc: AccessNotFound) -> JSONResponse:
        return error_response(request, 404, "ACCESS_NOT_FOUND", str(exc))

    @app.exception_handler(FeatureStoreError)
    async def feature_store_error(
        request: Request, exc: FeatureStoreError
    ) -> JSONResponse:
        return error_response(request, 409, "FEATURE_SPACE_CONFLICT", str(exc))

    @app.exception_handler(IndexStoreError)
    async def index_store_error(request: Request, exc: IndexStoreError) -> JSONResponse:
        return error_response(request, 409, "INDEX_CONTRACT_ERROR", str(exc))

    @app.exception_handler(PolicyDenied)
    async def policy_denied(request: Request, exc: PolicyDenied) -> JSONResponse:
        return error_response(request, 403, "POLICY_DENIED", str(exc))

    @app.exception_handler(PolicyUnavailable)
    async def policy_unavailable(
        request: Request, exc: PolicyUnavailable
    ) -> JSONResponse:
        return error_response(request, 503, "POLICY_UNAVAILABLE", str(exc))

    @app.exception_handler(AuditUnavailable)
    async def audit_unavailable(
        request: Request, exc: AuditUnavailable
    ) -> JSONResponse:
        return error_response(request, 503, "AUDIT_UNAVAILABLE", str(exc))

    @app.exception_handler(PipelineError)
    async def pipeline_error(request: Request, exc: PipelineError) -> JSONResponse:
        return error_response(request, 422, "PIPELINE_ERROR", str(exc))

    @app.exception_handler(ObjectAlreadyExistsError)
    async def immutable_object_conflict(
        request: Request, exc: ObjectAlreadyExistsError
    ) -> JSONResponse:
        return error_response(request, 409, "IMMUTABLE_OBJECT_CONFLICT", str(exc))

    @app.exception_handler(ObjectIntegrityError)
    async def object_integrity_error(
        request: Request, exc: ObjectIntegrityError
    ) -> JSONResponse:
        return error_response(request, 409, "OBJECT_INTEGRITY_ERROR", str(exc))

    @app.exception_handler(ObjectStoreCapabilityError)
    async def object_capability_error(
        request: Request, exc: ObjectStoreCapabilityError
    ) -> JSONResponse:
        return error_response(request, 409, "OBJECT_CAPABILITY_UNAVAILABLE", str(exc))

    @app.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError) -> JSONResponse:
        return error_response(request, 400, "INVALID_ARGUMENT", str(exc))

    @app.get("/healthz", tags=["Operations"])
    async def health(request: Request) -> ApiEnvelope[dict[str, str]]:
        return _envelope(request, {"status": "ok", "version": __version__})

    @app.get("/livez", tags=["Operations"])
    async def live(request: Request) -> ApiEnvelope[dict[str, str]]:
        return _envelope(request, {"status": "ok", "version": __version__})

    @app.get("/readyz", tags=["Operations"])
    async def ready(request: Request) -> ApiEnvelope[dict[str, object]]:
        try:
            components = await asyncio.wait_for(runtime.health_check(), timeout=5)
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="runtime dependency is unavailable"
            ) from exc
        return _envelope(request, {"status": "ready", "components": components})

    @app.post("/internal/v1/data/events", include_in_schema=False)
    async def receive_data_event(
        body: DataEventEnvelope,
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        tenant_id: Annotated[str | None, Header(alias="X-Scenara-Tenant-Id")] = None,
        project_id: Annotated[str | None, Header(alias="X-Scenara-Project-Id")] = None,
    ) -> JSONResponse:
        scheme, _, credential = (authorization or "").partition(" ")
        expected = runtime.settings.data_event_service_token
        if (
            scheme.lower() != "bearer"
            or not credential
            or not expected
            or not hmac.compare_digest(credential, expected)
        ):
            raise HTTPException(
                status_code=401, detail="invalid Data event service credential"
            )
        if idempotency_key != body.event_id:
            raise HTTPException(
                status_code=400, detail="Idempotency-Key must match event_id"
            )
        if (tenant_id, project_id) != (body.tenant_id, body.project_id):
            raise HTTPException(
                status_code=400,
                detail="event scope headers must match the event envelope",
            )
        accepted = await runtime.state.append_external_event_audit(
            body.audit_event(), body.payload_hash()
        )
        return JSONResponse(
            status_code=202 if accepted else 200,
            content={"accepted": accepted, "event_id": body.event_id},
        )

    @app.get("/metrics", include_in_schema=False)
    async def metrics(
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await require_allowed(runtime.policy, context, "read", "operations")
        return Response(
            content=app.state.request_metrics.render()
            + runtime.surveillance_metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    def console_file(name: str) -> FileResponse:
        target = CONSOLE_DIST / name
        if not target.is_file():
            raise HTTPException(
                status_code=503, detail="console static bundle is not installed"
            )
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
