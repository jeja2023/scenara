from __future__ import annotations

import asyncio
import hmac
import json
import re
import sys
import tempfile
import time
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated, TypeVar
from uuid import uuid4


from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
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
from scenara.bootstrap import Runtime, build_runtime
from scenara.domains.portrait.capabilities import portrait_capability_snapshot
from scenara.domains.portrait.encoder import PortraitEncodingError
from scenara.domains.portrait.service import (
    CreateIdentityRequest,
    EnrollIdentityRequest,
    PortraitAssetCompareRequest,
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
from scenara.domains.portrait.trajectory import (
    CameraRecord,
    CameraTransition,
    IdentityPage,
    LongTermIdentity,
    MergeIdentitiesRequest,
    RegisterCameraRequest,
    SegmentPage,
    SetCameraTransitionsRequest,
    SplitIdentityRequest,
    TimelineEntry,
    TrajectoryConflict,
    TrajectoryNotFound,
    TrajectoryStatus,
    UpdateCameraRequest,
    UpdateIdentityRequest,
)
from scenara.platform.surveillance import (
    AlertPage,
    AlertRecord,
    AlertStatus,
    CreateAlertFeedbackRequest,
    CreateSurveillanceTaskRequest,
    CreateWatchlistMemberRequest,
    CreateWatchlistRequest,
    SurveillanceConflict,
    SurveillanceNotFound,
    SurveillanceTask,
    SurveillanceTaskPage,
    TriageAlertRequest,
    UpdateSurveillanceTaskRequest,
    UpdateWatchlistMemberRequest,
    UpdateWatchlistRequest,
    Watchlist,
    WatchlistMember,
    WatchlistMemberPage,
    WatchlistPage,
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
from scenara.platform.control_plane import (
    AcknowledgeEdgeDeploymentRequest,
    AcknowledgeEdgeSyncRequest,
    AgentAction,
    AgentEvaluation,
    AgentMemoryEntry,
    AgentTool,
    AgentTrace,
    AutoRollbackModelRequest,
    AnnotationProvider,
    AnnotationTask,
    ApproveAgentActionRequest,
    AssignSeatRequest,
    AuditRetentionPolicy,
    BillingAccount,
    BillingUsage,
    CreateAgentEvaluationRequest,
    CreateAgentTraceRequest,
    CreateAnnotationProviderRequest,
    CreateAnnotationTaskRequest,
    CreateBillingAccountRequest,
    CreateEdgeDeploymentRequest,
    CreateFlowRequest,
    CreateIdentityProviderRequest,
    CreateIndexBackendRequest,
    CreateIndexRebuildRequest,
    CreatePortraitAssociationRequest,
    CreatePortraitClusterRequest,
    CreatePortraitEventRequest,
    CreateProjectLifecycleRequest,
    CreateQuotaPlanRequest,
    CreateSearchEvaluationRequest,
    CreateSearchRankingProfileRequest,
    CreateSearchRelevanceFeedbackRequest,
    CreateSearchRerankerRequest,
    CreateSessionRequest,
    DecideApprovalRequest,
    DecideProjectLifecycleRequest,
    DeploymentTopology,
    EdgeDeployment,
    EdgeDevice,
    EdgeHeartbeatRequest,
    EdgeSyncItem,
    ExecuteFlowRequest,
    FlowApproval,
    FlowDefinition,
    FlowExecution,
    IdentityProvider,
    IndexBackend,
    IndexRebuildJob,
    MeterEvent,
    ModelHealthSnapshot,
    ModelMetricPoint,
    PortraitAssociation,
    PortraitCluster,
    PortraitEvent,
    ProjectLifecycleRequest,
    ProposeAgentActionRequest,
    PurgeAuditRequest,
    PurgeAuditResponse,
    PutAgentMemoryRequest,
    QuotaCheckRequest,
    QuotaCheckResponse,
    QuotaPlan,
    RecordMeterEventRequest,
    RegisterAgentToolRequest,
    RegisterEdgeDeviceRequest,
    RegisterWorkerRequest,
    ResourceLifecycleRecord,
    ReviewAnnotationTaskRequest,
    SearchEvaluation,
    SearchRankingProfile,
    SearchRelevanceFeedback,
    SearchReranker,
    SeatAssignment,
    SessionResponse,
    SetAuditRetentionPolicyRequest,
    WorkerHeartbeatRequest,
    WorkerLease,
)
from scenara.platform.data_platform import DataPlatformRemoteError
from scenara.platform.error_codes import registered_error_code
from scenara.platform.data_events import DataEventEnvelope
from scenara.platform.dataset import DatasetConflict, DatasetNotFound
from scenara.platform.features import FeatureStoreError
from scenara.platform.feedback import (
    CreateFeedbackRequest,
    CreateHardSampleManifestRequest,
    CreateModelReleaseRequest,
    FeedbackConflict,
    FeedbackKind,
    FeedbackNotFound,
    FeedbackRecord,
    HardSampleManifest,
    ModelDeploymentEvent,
    ModelRelease,
    ReviewFeedbackRequest,
    RollbackModelReleaseRequest,
    TransitionModelReleaseRequest,
)
from scenara.platform.index import (
    IndexDefinition,
    IndexHit,
    IndexRecordView,
    IndexStoreError,
    IndexTextQueryRequest,
    IndexVectorQueryRequest,
)
from scenara.platform.model_runtime import ModelPackageManifest, builtin_model_packages

from scenara.platform.objects import (
    ObjectAlreadyExistsError,
    ObjectIntegrityError,
    ObjectStoreCapabilityError,
)
from scenara.platform.models import (
    TERMINAL_RUN_STATUSES,
    AccessFoundationStatus,
    ApiEnvelope,
    ApiErrorDetail,
    ApiErrorEnvelope,
    ApiKeyRecord,
    CompleteMediaUploadRequest,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    CreateDatasetRequest,
    CreateDatasetVersionRequest,
    CreateMediaSourceRequest,
    CreateMembershipRequest,
    CreateOrganizationRequest,
    CreateProductEntitlementRequest,
    CreateProjectRequest,
    CreateRoleRequest,
    CreateRunRequest,
    CreateSavedSearchRequest,
    CreateServiceAccountRequest,
    CreateUserRequest,
    CreateWebhookSubscriptionRequest,
    DatasetPage,
    DatasetRecord,
    DatasetVersion,
    DatasetVersionPage,
    DomainId,
    IamSummary,
    LoginRequest,
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
    PresignedMediaDownload,
    PresignedMediaUpload,
    PresignMediaUploadRequest,
    PipelineTransitionRequest,
    PortraitIntelligenceStatus,
    PrincipalContext,
    ProductCatalogItem,
    ProductEntitlement,
    Project,
    RepositoryTopology,
    ResultPage,
    ResultSummaryPage,
    Role,
    RunPage,
    RunRecord,
    RunStatus,
    SampleStrategy,
    StreamSessionView,
    SavedSearch,
    SavedSearchPage,
    ServiceAccount,
    SystemStatus,
    TransitionDatasetVersionRequest,
    UpdateDatasetRequest,
    UpdateProductEntitlementRequest,
    UpdateSavedSearchRequest,
    UserAccount,
    WebhookDeliveryRecord,
    WebhookSubscriptionView,
)
from scenara.platform.observability import RequestMetrics
from scenara.platform.pipeline import PipelineError
from scenara.platform.policy import PolicyDenied, PolicyUnavailable, require_allowed
from scenara.platform.portrait_intelligence import build_portrait_intelligence
from scenara.platform.product_catalog import build_product_catalog
from scenara.platform.repository_contracts import (
    CONTRACT_ROOT,
    RepositoryContractCatalog,
    load_repository_contract_catalog,
)
from scenara.platform.repository_topology import build_repository_topology
from scenara.platform.search import (
    SavedSearchConflict,
    SavedSearchNotFound,
    SearchAssetRequest,
    SearchResponse,
    SearchTextRequest,
)
from scenara.platform.services import InvalidTransition, ResourceNotFound, sse_payload
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

    def bind_context(context: PrincipalContext) -> PrincipalContext:
        request_id = _request_id(request)
        traceparent = getattr(request.state, "traceparent", None)
        return context.model_copy(update={"request_id": request_id, "traceparent": traceparent})

    if settings.auth_required or authorization:
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
            return bind_context(PrincipalContext(
                tenant_id=tenant_id,
                project_id=project_id,
                principal_id=principal_id,
                request_id=_request_id(request),
                traceparent=getattr(request.state, "traceparent", None),
            ))
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
        credential = await runtime.access.authenticate_api_key(token)
        if credential is None:
            session_context = await runtime.control_plane.authenticate_session(token)
            if session_context is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
            if await runtime.access.is_user_disabled(session_context.tenant_id, session_context.principal_id):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user session is disabled")
            if x_principal_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="principal identity is credential-derived"
                )
            if x_tenant_id and x_tenant_id != session_context.tenant_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="session tenant mismatch")
            if x_project_id and x_project_id != session_context.project_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="session project mismatch")
            return bind_context(session_context)
        if x_principal_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="principal identity is credential-derived"
            )
        if x_tenant_id and x_tenant_id != credential.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="credential tenant mismatch")
        if x_project_id and x_project_id != credential.project_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="credential project mismatch")
        return bind_context(credential)
    tenant_id = x_tenant_id or settings.default_tenant_id
    project_id = x_project_id or settings.default_project_id
    principal_id = x_principal_id or ("api-token" if settings.auth_required else "anonymous")
    if not all(CONTEXT_ID.fullmatch(value) for value in (tenant_id, project_id, principal_id)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid context identifier")
    return bind_context(PrincipalContext(
        tenant_id=tenant_id,
        project_id=project_id,
        principal_id=principal_id,
        request_id=_request_id(request),
        traceparent=getattr(request.state, "traceparent", None),
    ))


def create_app(settings: Settings | None = None, *, runtime: Runtime | None = None) -> FastAPI:
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
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(runtime.settings.allowed_hosts))
    console_assets = CONSOLE_DIST / "assets"
    if console_assets.is_dir():
        app.mount("/console/assets", StaticFiles(directory=console_assets), name="console-assets")

    async def spool_upload(file: UploadFile, max_bytes: int) -> Path:
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

    def require_presigned_storage() -> None:
        if not runtime.settings.s3_presigned_urls_enabled:
            raise HTTPException(status_code=404, detail="presigned object URLs are not enabled")
        if runtime.settings.object_backend != "s3":
            raise HTTPException(status_code=409, detail="presigned object URLs require an S3 provider")

    def validate_direct_upload_size(body: PresignMediaUploadRequest) -> None:
        maximum = runtime.settings.max_image_bytes if body.kind == MediaKind.IMAGE else runtime.settings.max_media_bytes
        if body.size_bytes > maximum:
            raise ValueError(f"media exceeds {maximum} bytes")

    def upload_token(
        context: PrincipalContext,
        upload_id: str,
        body: PresignMediaUploadRequest,
        expires_at: int,
    ) -> str:
        secret = runtime.settings.api_token or runtime.settings.secret_encryption_key
        if not secret:
            raise HTTPException(status_code=503, detail="presigned upload signing key is not configured")
        payload = json.dumps(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "upload_id": upload_id,
                "filename": body.filename,
                "content_type": body.content_type,
                "kind": body.kind.value,
                "size_bytes": body.size_bytes,
                "sha256": body.sha256,
                "expires_at": expires_at,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), "sha256").hexdigest()

    @app.middleware("http")
    async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = normalize_request_id(request.headers.get("X-Request-Id")) or f"req_{uuid4().hex}"
        traceparent = traceparent_from_headers(request)
        if traceparent is None:
            traceparent = new_traceparent()
        request.state.traceparent = traceparent
        log_tokens = set_log_context(
            request_id=request.state.request_id,
            tenant_id=request.headers.get("X-Scenara-Tenant-Id") or request.headers.get("X-Tenant-Id"),
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
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if runtime.settings.hsts_enabled:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={runtime.settings.hsts_max_age_seconds}; includeSubDomains",
            )
        return response

    app.include_router(build_audit_router(runtime, principal_context, _envelope))

    def error_response(
        request: Request,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> JSONResponse:
        payload = ApiErrorEnvelope(
            request_id=_request_id(request),
            error=ApiErrorDetail(code=registered_error_code(code), message=message, details=details or {}),
        )
        if payload.error.code == "INTERNAL_SERVER_ERROR":
            payload = payload.model_copy(update={"error": payload.error.model_copy(update={"message": "internal server error"})})
        return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))

    def enterprise_service() -> EnterpriseService:
        if runtime.enterprise is None:
            raise HTTPException(status_code=404, detail="enterprise modules are not installed")
        return runtime.enterprise

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        detail_msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return error_response(request, exc.status_code, "HTTP_ERROR", detail_msg)


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

    @app.exception_handler(PortraitEncodingError)
    async def portrait_encoding_error(request: Request, exc: PortraitEncodingError) -> JSONResponse:
        return error_response(request, 422, "PORTRAIT_ENCODING_ERROR", str(exc))

    @app.exception_handler(TrajectoryNotFound)
    async def trajectory_not_found(request: Request, exc: TrajectoryNotFound) -> JSONResponse:
        return error_response(request, 404, "TRAJECTORY_NOT_FOUND", str(exc))

    @app.exception_handler(TrajectoryConflict)
    async def trajectory_conflict(request: Request, exc: TrajectoryConflict) -> JSONResponse:
        return error_response(request, 409, "TRAJECTORY_CONFLICT", str(exc))

    @app.exception_handler(SurveillanceNotFound)
    async def surveillance_not_found(request: Request, exc: SurveillanceNotFound) -> JSONResponse:
        return error_response(request, 404, "SURVEILLANCE_NOT_FOUND", str(exc))

    @app.exception_handler(SurveillanceConflict)
    async def surveillance_conflict(request: Request, exc: SurveillanceConflict) -> JSONResponse:
        return error_response(request, 409, "SURVEILLANCE_CONFLICT", str(exc))

    @app.exception_handler(DatasetNotFound)
    async def dataset_not_found(request: Request, exc: DatasetNotFound) -> JSONResponse:
        return error_response(request, 404, "DATASET_NOT_FOUND", str(exc))

    @app.exception_handler(DatasetConflict)
    async def dataset_conflict(request: Request, exc: DatasetConflict) -> JSONResponse:
        return error_response(request, 409, "DATASET_CONFLICT", str(exc))

    @app.exception_handler(DataPlatformRemoteError)
    async def data_platform_error(request: Request, exc: DataPlatformRemoteError) -> JSONResponse:
        return error_response(request, exc.status_code, exc.code, str(exc), exc.details)

    @app.exception_handler(SavedSearchNotFound)
    async def saved_search_not_found(request: Request, exc: SavedSearchNotFound) -> JSONResponse:
        return error_response(request, 404, "SAVED_SEARCH_NOT_FOUND", str(exc))

    @app.exception_handler(SavedSearchConflict)
    async def saved_search_conflict(request: Request, exc: SavedSearchConflict) -> JSONResponse:
        return error_response(request, 409, "SAVED_SEARCH_CONFLICT", str(exc))

    @app.exception_handler(AccessNotFound)
    async def access_not_found(request: Request, exc: AccessNotFound) -> JSONResponse:
        return error_response(request, 404, "ACCESS_NOT_FOUND", str(exc))

    @app.exception_handler(FeatureStoreError)
    async def feature_store_error(request: Request, exc: FeatureStoreError) -> JSONResponse:
        return error_response(request, 409, "FEATURE_SPACE_CONFLICT", str(exc))

    @app.exception_handler(IndexStoreError)
    async def index_store_error(request: Request, exc: IndexStoreError) -> JSONResponse:
        return error_response(request, 409, "INDEX_CONTRACT_ERROR", str(exc))

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

    @app.exception_handler(ObjectAlreadyExistsError)
    async def immutable_object_conflict(request: Request, exc: ObjectAlreadyExistsError) -> JSONResponse:
        return error_response(request, 409, "IMMUTABLE_OBJECT_CONFLICT", str(exc))

    @app.exception_handler(ObjectIntegrityError)
    async def object_integrity_error(request: Request, exc: ObjectIntegrityError) -> JSONResponse:
        return error_response(request, 409, "OBJECT_INTEGRITY_ERROR", str(exc))

    @app.exception_handler(ObjectStoreCapabilityError)
    async def object_capability_error(request: Request, exc: ObjectStoreCapabilityError) -> JSONResponse:
        return error_response(request, 409, "OBJECT_CAPABILITY_UNAVAILABLE", str(exc))

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
            raise HTTPException(status_code=401, detail="invalid Data event service credential")
        if idempotency_key != body.event_id:
            raise HTTPException(status_code=400, detail="Idempotency-Key must match event_id")
        if (tenant_id, project_id) != (body.tenant_id, body.project_id):
            raise HTTPException(status_code=400, detail="event scope headers must match the event envelope")
        accepted = await runtime.state.append_external_event_audit(
            body.audit_event(), body.payload_hash()
        )
        return JSONResponse(
            status_code=202 if accepted else 200,
            content={"accepted": accepted, "event_id": body.event_id},
        )

    @app.get("/metrics", include_in_schema=False)
    async def metrics(context: PrincipalContext = Depends(principal_context)) -> Response:
        await require_allowed(runtime.policy, context, "read", "operations")
        return Response(
            content=app.state.request_metrics.render() + runtime.surveillance_metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.post("/api/v1/media/assets", status_code=201, tags=["Media"])
    async def create_media_asset(
        request: Request,
        file: Annotated[UploadFile, File()],
        kind: Annotated[MediaKind, Form()] = MediaKind.IMAGE,
        domain: Annotated[str | None, Form()] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaAsset]:
        max_read = (
            runtime.settings.max_image_bytes + 1 if kind == MediaKind.IMAGE else runtime.settings.max_media_bytes + 1
        )
        if kind == MediaKind.VIDEO:
            path = await spool_upload(file, runtime.settings.max_media_bytes)
            try:
                asset = await runtime.runs.create_asset_from_path(
                    context,
                    path=str(path),
                    filename=file.filename,
                    content_type=file.content_type or "application/octet-stream",
                    kind=kind,
                    domain=domain,
                )
            finally:
                with suppress(FileNotFoundError, PermissionError):
                    path.unlink()
        else:
            data = await file.read(max_read)
            asset = await runtime.runs.create_asset(
                context,
                data=data,
                filename=file.filename,
                content_type=file.content_type or "application/octet-stream",
                kind=kind,
                domain=domain,
            )
        return _envelope(request, asset)  # type: ignore[return-value]

    @app.post("/api/v1/media/uploads/presign", tags=["Media"])
    async def presign_media_upload(
        body: PresignMediaUploadRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PresignedMediaUpload]:
        require_presigned_storage()
        validate_direct_upload_size(body)
        await require_allowed(runtime.policy, context, "create", "media_asset", {"kind": body.kind.value})
        upload_id = f"upl_{uuid4().hex}"
        object_key = (
            f"tenants/{context.tenant_id}/projects/{context.project_id}"
            f"/pending-uploads/{upload_id}/original"
        )
        expires_at = int(time.time()) + runtime.settings.s3_presign_expiry_seconds
        signed = await runtime.objects.presign_upload(
            object_key,
            content_type=body.content_type,
            sha256=body.sha256,
            size_bytes=body.size_bytes,
            expires_in=runtime.settings.s3_presign_expiry_seconds,
            retention_category="pending_upload",
        )
        response = PresignedMediaUpload(
            upload_id=upload_id,
            upload_token=upload_token(context, upload_id, body, expires_at),
            url=signed.url,
            headers=signed.headers,
            expires_at=expires_at,
        )
        return _envelope(request, response)  # type: ignore[return-value]

    @app.post("/api/v1/media/uploads/complete", status_code=201, tags=["Media"])
    async def complete_media_upload(
        body: CompleteMediaUploadRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaAsset]:
        require_presigned_storage()
        validate_direct_upload_size(body)
        expected_token = upload_token(context, body.upload_id, body, int(body.expires_at))
        if not hmac.compare_digest(expected_token, body.upload_token):
            raise HTTPException(status_code=403, detail="presigned upload token is invalid")
        if time.time() > body.expires_at + PRESIGN_UPLOAD_EXPIRY_GRACE_SECONDS:
            raise HTTPException(status_code=410, detail="presigned upload has expired")
        object_key = (
            f"tenants/{context.tenant_id}/projects/{context.project_id}"
            f"/pending-uploads/{body.upload_id}/original"
        )
        if not await runtime.objects.exists(object_key):
            raise HTTPException(status_code=409, detail="presigned upload object is not available")
        metadata = await runtime.objects.verify(object_key, body.sha256)
        if metadata.size_bytes != body.size_bytes:
            raise ValueError("uploaded object size does not match the request")
        suffix = Path(body.filename or "media.bin").suffix or ".bin"
        handle = tempfile.NamedTemporaryFile(prefix="scenara-direct-upload-", suffix=suffix, delete=False)
        handle.close()
        path = Path(handle.name)
        try:
            await runtime.objects.get_to_file(object_key, path, expected_sha256=body.sha256)
            asset = await runtime.runs.create_asset_from_path(
                context,
                path=str(path),
                filename=body.filename,
                content_type=body.content_type,
                kind=body.kind,
            )
        finally:
            with suppress(FileNotFoundError, PermissionError):
                path.unlink()
            with suppress(Exception):
                await runtime.objects.delete(object_key)
        return _envelope(request, asset)  # type: ignore[return-value]

    @app.get("/api/v1/media/assets/{asset_id}/download-url", tags=["Media"])
    async def presign_media_download(
        asset_id: str,
        request: Request,
        expires_in: Annotated[int | None, Query(ge=60, le=86_400)] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PresignedMediaDownload]:
        require_presigned_storage()
        await require_allowed(runtime.policy, context, "read", "media_asset", {"asset_id": asset_id})
        asset = await runtime.state.get_asset(context.tenant_id, context.project_id, asset_id)
        if asset is None or asset.deleted_at is not None or asset.original_deleted_at is not None:
            raise ResourceNotFound("media asset not found")
        await runtime.objects.verify(asset.object_key, asset.sha256)
        signed = await runtime.objects.presign_download(
            asset.object_key,
            expires_in=expires_in or runtime.settings.s3_presign_expiry_seconds,
            filename=asset.filename,
        )
        response = PresignedMediaDownload(
            url=signed.url,
            headers=signed.headers,
            expires_at=signed.expires_at,
        )
        return _envelope(request, response)  # type: ignore[return-value]

    @app.get("/api/v1/media/assets", tags=["Media"])
    async def list_media_assets(
        request: Request,
        domain: Annotated[str | None, Query()] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaAssetPage]:
        await require_allowed(runtime.policy, context, "list", "media_asset")
        rows, total = await asyncio.gather(
            runtime.state.list_assets(
                context.tenant_id,
                context.project_id,
                domain=domain,
                include_deleted=False,
                offset=offset,
                limit=limit,
            ),
            runtime.state.count_assets(
                context.tenant_id,
                context.project_id,
                domain=domain,
                include_deleted=False,
            ),
        )
        return _envelope(
            request,
            MediaAssetPage(items=rows, offset=offset, limit=limit, total=total),
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
        rows, total = await asyncio.gather(
            runtime.state.list_sources(
                context.tenant_id,
                context.project_id,
                offset=offset,
                limit=limit,
            ),
            runtime.state.count_sources(context.tenant_id, context.project_id),
        )
        return _envelope(
            request,
            MediaSourcePage(
                items=[_media_source_view(item) for item in rows],
                offset=offset,
                limit=limit,
                total=total,
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

    @app.get("/api/v1/media/sources/{source_id}/preview", tags=["Media"])
    async def get_media_source_preview(
        source_id: str,
        timeout_ms: Annotated[int, Query(ge=100, le=30_000)] = 10_000,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        data, content_type = await runtime.runs.get_source_preview(context, source_id, timeout_ms=timeout_ms)
        return Response(content=data, media_type=content_type)

    @app.delete("/api/v1/media/sources/{source_id}", status_code=204, tags=["Media"])
    async def delete_media_source(
        source_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.runs.delete_source(context, source_id)
        return Response(status_code=204)

    @app.post("/api/v1/datasets", status_code=201, tags=["Data"])
    async def create_dataset(
        body: CreateDatasetRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[DatasetRecord]:
        result = await runtime.data.create_dataset(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get("/api/v1/datasets", tags=["Data"])
    async def list_datasets(
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[DatasetPage]:
        result = await runtime.data.list_datasets(context, offset=offset, limit=limit)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get("/api/v1/datasets/{dataset_id}", tags=["Data"])
    async def get_dataset(
        dataset_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[DatasetRecord]:
        result = await runtime.data.get_dataset(context, dataset_id)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.patch("/api/v1/datasets/{dataset_id}", tags=["Data"])
    async def update_dataset(
        dataset_id: str,
        body: UpdateDatasetRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[DatasetRecord]:
        result = await runtime.data.update_dataset(context, dataset_id, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/datasets/{dataset_id}/versions", status_code=201, tags=["Data"])
    async def create_dataset_version(
        dataset_id: str,
        body: CreateDatasetVersionRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[DatasetVersion]:
        result = await runtime.data.create_dataset_version(context, dataset_id, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get("/api/v1/datasets/{dataset_id}/versions", tags=["Data"])
    async def list_dataset_versions(
        dataset_id: str,
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[DatasetVersionPage]:
        result = await runtime.data.list_dataset_versions(context, dataset_id, offset=offset, limit=limit)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/dataset-versions/{version_id}/transition", tags=["Data"])
    async def transition_dataset_version(
        version_id: str,
        body: TransitionDatasetVersionRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[DatasetVersion]:
        result = await runtime.data.transition_dataset_version(context, version_id, body)
        return _envelope(request, result)  # type: ignore[return-value]

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
        domain: DomainId | None = None,
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

    @app.get("/api/v1/stream-sessions/{session_id}", tags=["Runs"])
    async def get_stream_session(
        session_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[StreamSessionView]:
        return _envelope(request, await runtime.runs.stream_session(context, session_id))  # type: ignore[return-value]

    @app.post("/api/v1/stream-sessions/{session_id}/cancel", tags=["Runs"])
    async def cancel_stream_session(
        session_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[StreamSessionView]:
        return _envelope(request, await runtime.runs.cancel_stream_session(context, session_id))  # type: ignore[return-value]

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
        page = await runtime.runs.result_page(
            context,
            run_id,
            unit_offset=unit_offset,
            unit_limit=unit_limit,
        )
        return _envelope(request, page)  # type: ignore[return-value]

    @app.get("/api/v1/results", tags=["Results"])
    async def list_results(
        request: Request,
        domain: DomainId | None = None,
        media_kind: MediaKind | None = None,
        query: Annotated[str | None, Query(max_length=256)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ResultSummaryPage]:
        items, total = await runtime.runs.list_results(
            context,
            domain=domain,
            media_kind=media_kind,
            query=query.strip() if query else None,
            offset=offset,
            limit=limit,
        )
        return _envelope(
            request,
            ResultSummaryPage(items=items, offset=offset, limit=limit, total=total),
        )  # type: ignore[return-value]

    @app.get("/api/v1/runs/{run_id}/artifacts/{artifact_id}", tags=["Results"])
    async def get_result_artifact(
        run_id: str,
        artifact_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        """Return one derived image declared by the run result.

        Feature crops (``crop_artifact_id`` on an object) and unit frames
        (``frame_artifact_id`` on a media unit) are served from here.
        """
        data, content_type, sha256 = await runtime.runs.result_artifact(context, run_id, artifact_id)
        return Response(
            content=data,
            media_type=content_type,
            headers={"ETag": f'"sha256:{sha256}"', "Cache-Control": "private, max-age=300"},
        )

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

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/v1/parse/image", tags=["Parsing"])
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
        selected_pipeline_ref = await runtime.runs.resolve_pipeline_ref(selected_pipeline, pipeline_version)
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
        return _envelope(
            request,
            ParseVideoResponse(asset=asset, run=outcome.run, result=result),
        )  # type: ignore[return-value]

    @app.post("/api/v1/parse/document", status_code=202, tags=["Parsing"])
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
        selected_pipeline_ref = await runtime.runs.resolve_pipeline_ref(selected_pipeline, pipeline_version)
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

    @app.get("/api/v1/portrait/trajectories/identities", tags=["Portrait Intelligence"])
    async def list_long_term_portrait_identities(
        request: Request,
        status: Annotated[TrajectoryStatus | None, Query()] = None,
        camera_id: Annotated[str | None, Query(max_length=128)] = None,
        since: Annotated[float | None, Query(ge=0)] = None,
        until: Annotated[float | None, Query(ge=0)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[IdentityPage]:
        page = await runtime.trajectory.list_identities(
            context,
            status=status,
            camera_id=camera_id,
            since=since,
            until=until,
            offset=offset,
            limit=limit,
        )
        return _envelope(request, page)  # type: ignore[return-value]

    @app.get("/api/v1/portrait/trajectories/identities/{identity_id}", tags=["Portrait Intelligence"])
    async def get_long_term_portrait_identity(
        identity_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[LongTermIdentity]:
        return _envelope(request, await runtime.trajectory.get_identity(context, identity_id))  # type: ignore[return-value]

    @app.patch("/api/v1/portrait/trajectories/identities/{identity_id}", tags=["Portrait Intelligence"])
    async def update_long_term_portrait_identity(
        identity_id: str,
        body: UpdateIdentityRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[LongTermIdentity]:
        identity = await runtime.trajectory.update_identity(context, identity_id, body)
        return _envelope(request, identity)  # type: ignore[return-value]

    @app.delete(
        "/api/v1/portrait/trajectories/identities/{identity_id}",
        status_code=204,
        tags=["Portrait Intelligence"],
    )
    async def delete_long_term_portrait_identity(
        identity_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.trajectory.delete_identity(context, identity_id)
        return Response(status_code=204)

    @app.get("/api/v1/portrait/trajectories/identities/{identity_id}/segments", tags=["Portrait Intelligence"])
    async def list_long_term_portrait_segments(
        identity_id: str,
        request: Request,
        camera_id: Annotated[str | None, Query(max_length=128)] = None,
        since: Annotated[float | None, Query(ge=0)] = None,
        until: Annotated[float | None, Query(ge=0)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SegmentPage]:
        page = await runtime.trajectory.list_segments(
            context,
            identity_id,
            camera_id=camera_id,
            since=since,
            until=until,
            offset=offset,
            limit=limit,
        )
        return _envelope(request, page)  # type: ignore[return-value]

    @app.get("/api/v1/portrait/trajectories/identities/{identity_id}/timeline", tags=["Portrait Intelligence"])
    async def get_long_term_portrait_timeline(
        identity_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[TimelineEntry]]:
        return _envelope(request, await runtime.trajectory.timeline(context, identity_id))  # type: ignore[return-value]

    @app.post("/api/v1/portrait/trajectories/identities/merge", tags=["Portrait Intelligence"])
    async def merge_long_term_portrait_identities(
        body: MergeIdentitiesRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[LongTermIdentity]:
        return _envelope(request, await runtime.trajectory.merge_identities(context, body))  # type: ignore[return-value]

    @app.post(
        "/api/v1/portrait/trajectories/identities/{identity_id}/split",
        status_code=201,
        tags=["Portrait Intelligence"],
    )
    async def split_long_term_portrait_identity(
        identity_id: str,
        body: SplitIdentityRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[LongTermIdentity]:
        identity = await runtime.trajectory.split_identity(context, identity_id, body)
        return _envelope(request, identity)  # type: ignore[return-value]

    @app.post("/api/v1/portrait/cameras", status_code=201, tags=["Portrait Intelligence"])
    async def register_portrait_camera(
        body: RegisterCameraRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[CameraRecord]:
        return _envelope(request, await runtime.trajectory.register_camera(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/portrait/cameras", tags=["Portrait Intelligence"])
    async def list_portrait_cameras(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[CameraRecord]]:
        return _envelope(request, await runtime.trajectory.list_cameras(context))  # type: ignore[return-value]

    @app.patch("/api/v1/portrait/cameras/{camera_id}", tags=["Portrait Intelligence"])
    async def update_portrait_camera(
        camera_id: str,
        body: UpdateCameraRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[CameraRecord]:
        return _envelope(request, await runtime.trajectory.update_camera(context, camera_id, body))  # type: ignore[return-value]

    @app.delete("/api/v1/portrait/cameras/{camera_id}", status_code=204, tags=["Portrait Intelligence"])
    async def delete_portrait_camera(
        camera_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.trajectory.delete_camera(context, camera_id)
        return Response(status_code=204)

    @app.get("/api/v1/portrait/cameras/{camera_id}/transitions", tags=["Portrait Intelligence"])
    async def list_portrait_camera_transitions(
        camera_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[CameraTransition]]:
        transitions = await runtime.trajectory.list_camera_transitions(context, camera_id)
        return _envelope(request, transitions)  # type: ignore[return-value]

    @app.put("/api/v1/portrait/cameras/{camera_id}/transitions", tags=["Portrait Intelligence"])
    async def set_portrait_camera_transitions(
        camera_id: str,
        body: SetCameraTransitionsRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[CameraTransition]]:
        transitions = await runtime.trajectory.set_camera_transitions(context, camera_id, body)
        return _envelope(request, transitions)  # type: ignore[return-value]

    @app.post("/api/v1/surveillance/watchlists", status_code=201, tags=["Surveillance"])
    async def create_surveillance_watchlist(
        body: CreateWatchlistRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Watchlist]:
        return _envelope(request, await runtime.surveillance.create_watchlist(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/surveillance/watchlists", tags=["Surveillance"])
    async def list_surveillance_watchlists(
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[WatchlistPage]:
        return _envelope(request, await runtime.surveillance.list_watchlists(context, offset=offset, limit=limit))  # type: ignore[return-value]

    @app.get("/api/v1/surveillance/watchlists/{watchlist_id}", tags=["Surveillance"])
    async def get_surveillance_watchlist(
        watchlist_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Watchlist]:
        return _envelope(request, await runtime.surveillance.get_watchlist(context, watchlist_id))  # type: ignore[return-value]

    @app.patch("/api/v1/surveillance/watchlists/{watchlist_id}", tags=["Surveillance"])
    async def update_surveillance_watchlist(
        watchlist_id: str,
        body: UpdateWatchlistRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Watchlist]:
        return _envelope(request, await runtime.surveillance.update_watchlist(context, watchlist_id, body))  # type: ignore[return-value]

    @app.delete("/api/v1/surveillance/watchlists/{watchlist_id}", status_code=204, tags=["Surveillance"])
    async def delete_surveillance_watchlist(
        watchlist_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.surveillance.delete_watchlist(context, watchlist_id)
        return Response(status_code=204)

    @app.post("/api/v1/surveillance/watchlists/{watchlist_id}/members", status_code=201, tags=["Surveillance"])
    async def create_surveillance_watchlist_member(
        watchlist_id: str,
        body: CreateWatchlistMemberRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[WatchlistMember]:
        return _envelope(request, await runtime.surveillance.create_member(context, watchlist_id, body))  # type: ignore[return-value]

    @app.get("/api/v1/surveillance/watchlists/{watchlist_id}/members", tags=["Surveillance"])
    async def list_surveillance_watchlist_members(
        watchlist_id: str,
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[WatchlistMemberPage]:
        page = await runtime.surveillance.list_members(context, watchlist_id, offset=offset, limit=limit)
        return _envelope(request, page)  # type: ignore[return-value]

    @app.patch("/api/v1/surveillance/watchlists/{watchlist_id}/members/{member_id}", tags=["Surveillance"])
    async def update_surveillance_watchlist_member(
        watchlist_id: str,
        member_id: str,
        body: UpdateWatchlistMemberRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[WatchlistMember]:
        result = await runtime.surveillance.update_member(context, watchlist_id, member_id, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.delete(
        "/api/v1/surveillance/watchlists/{watchlist_id}/members/{member_id}", status_code=204, tags=["Surveillance"]
    )
    async def delete_surveillance_watchlist_member(
        watchlist_id: str,
        member_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.surveillance.delete_member(context, watchlist_id, member_id)
        return Response(status_code=204)

    @app.post("/api/v1/surveillance/tasks", status_code=201, tags=["Surveillance"])
    async def create_surveillance_task(
        body: CreateSurveillanceTaskRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SurveillanceTask]:
        return _envelope(request, await runtime.surveillance.create_task(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/surveillance/tasks", tags=["Surveillance"])
    async def list_surveillance_tasks(
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SurveillanceTaskPage]:
        return _envelope(request, await runtime.surveillance.list_tasks(context, offset=offset, limit=limit))  # type: ignore[return-value]

    @app.get("/api/v1/surveillance/tasks/{task_id}", tags=["Surveillance"])
    async def get_surveillance_task(
        task_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SurveillanceTask]:
        return _envelope(request, await runtime.surveillance.get_task(context, task_id))  # type: ignore[return-value]

    @app.patch("/api/v1/surveillance/tasks/{task_id}", tags=["Surveillance"])
    async def update_surveillance_task(
        task_id: str,
        body: UpdateSurveillanceTaskRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SurveillanceTask]:
        return _envelope(request, await runtime.surveillance.update_task(context, task_id, body))  # type: ignore[return-value]

    @app.post("/api/v1/surveillance/tasks/{task_id}/start", tags=["Surveillance"])
    async def start_surveillance_task(
        task_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SurveillanceTask]:
        return _envelope(request, await runtime.surveillance.start_task(context, task_id))  # type: ignore[return-value]

    @app.post("/api/v1/surveillance/tasks/{task_id}/pause", tags=["Surveillance"])
    async def pause_surveillance_task(
        task_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SurveillanceTask]:
        return _envelope(request, await runtime.surveillance.pause_task(context, task_id))  # type: ignore[return-value]

    @app.post("/api/v1/surveillance/tasks/{task_id}/resume", tags=["Surveillance"])
    async def resume_surveillance_task(
        task_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SurveillanceTask]:
        return _envelope(request, await runtime.surveillance.resume_task(context, task_id))  # type: ignore[return-value]

    @app.get("/api/v1/surveillance/alerts", tags=["Surveillance"])
    async def list_surveillance_alerts(
        request: Request,
        alert_status: Annotated[AlertStatus | None, Query(alias="status")] = None,
        task_id: Annotated[str | None, Query(max_length=128)] = None,
        camera_id: Annotated[str | None, Query(max_length=128)] = None,
        watchlist_id: Annotated[str | None, Query(max_length=128)] = None,
        portrait_identity_id: Annotated[str | None, Query(max_length=128)] = None,
        since: Annotated[float | None, Query(ge=0)] = None,
        until: Annotated[float | None, Query(ge=0)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AlertPage]:
        page = await runtime.surveillance.list_alerts(
            context,
            status=alert_status,
            task_id=task_id,
            camera_id=camera_id,
            watchlist_id=watchlist_id,
            portrait_identity_id=portrait_identity_id,
            since=since,
            until=until,
            offset=offset,
            limit=limit,
        )
        return _envelope(request, page)  # type: ignore[return-value]

    @app.get("/api/v1/surveillance/alerts/live-stream", tags=["Surveillance"])
    async def surveillance_alert_live_stream(
        request: Request,
        last_event_id_header: Annotated[int | None, Header(alias="Last-Event-ID")] = None,
        last_event_id: Annotated[int, Query(ge=0)] = 0,
        context: PrincipalContext = Depends(principal_context),
    ) -> StreamingResponse:
        cursor = last_event_id_header if last_event_id_header is not None else last_event_id

        async def stream() -> AsyncIterator[str]:
            nonlocal cursor
            heartbeat_at = asyncio.get_running_loop().time() + 15
            while True:
                if await request.is_disconnected():
                    return
                events = await runtime.surveillance.events_after(context, cursor, limit=500)
                for event in events:
                    cursor = event.event_cursor
                    payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
                    yield f"id: {cursor}\nevent: {event.event_type}\ndata: {payload}\n\n"
                now = asyncio.get_running_loop().time()
                if now >= heartbeat_at:
                    yield ": heartbeat\n\n"
                    heartbeat_at = now + 15
                await asyncio.sleep(0.25)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/surveillance/alerts/{alert_id}", tags=["Surveillance"])
    async def get_surveillance_alert(
        alert_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AlertRecord]:
        return _envelope(request, await runtime.surveillance.get_alert(context, alert_id))  # type: ignore[return-value]

    @app.patch("/api/v1/surveillance/alerts/{alert_id}/status", tags=["Surveillance"])
    async def triage_surveillance_alert(
        alert_id: str,
        body: TriageAlertRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AlertRecord]:
        return _envelope(request, await runtime.surveillance.triage_alert(context, alert_id, body))  # type: ignore[return-value]

    @app.post("/api/v1/surveillance/alerts/{alert_id}/feedback", status_code=201, tags=["Surveillance"])
    async def create_surveillance_alert_feedback(
        alert_id: str,
        body: CreateAlertFeedbackRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[FeedbackRecord]:
        alert = await runtime.surveillance.get_alert(context, alert_id)
        if alert.status != AlertStatus.FALSE_POSITIVE:
            raise SurveillanceConflict("only a false-positive alert can create feedback")
        binding = alert.model_bindings.get("face") or alert.model_bindings.get("body")
        if binding is None:
            raise SurveillanceConflict("alert has no model binding for feedback")
        feedback = await runtime.feedback.create(
            context,
            CreateFeedbackRequest(
                kind=FeedbackKind.FALSE_POSITIVE,
                run_id=alert.run_id,
                model_id=binding["model_id"],
                model_version=binding["model_version"],
                correction={
                    "alert_id": alert.alert_id,
                    "triage_reason": alert.triage_reason,
                    **body.correction,
                },
                authorized_for_training=False,
                deidentified=False,
            ),
        )
        return _envelope(request, feedback)  # type: ignore[return-value]

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

    @app.post(
        "/api/v1/portrait/identities/{identity_id}/enrollments/image",
        status_code=201,
        tags=["Portrait"],
    )
    async def enroll_portrait_identity_image(
        identity_id: str,
        file: Annotated[UploadFile, File()],
        request: Request,
        feature_space_id: Annotated[str | None, Form()] = None,
        quality: Annotated[float | None, Form(ge=0, le=1)] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitEnrollment]:
        data = await file.read(runtime.settings.max_image_bytes + 1)
        if len(data) > runtime.settings.max_image_bytes:
            raise ValueError(f"image exceeds {runtime.settings.max_image_bytes} bytes")
        enrollment = await runtime.portrait.enroll_image(
            context,
            identity_id,
            data,
            feature_space_id=feature_space_id,
            quality_override=quality,
        )
        return _envelope(request, enrollment)  # type: ignore[return-value]

    @app.post("/api/v1/portrait/search", tags=["Portrait"])
    async def search_portrait_identities(
        body: PortraitSearchRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitSearchResponse]:
        result = await runtime.portrait.search(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/portrait/search/image", tags=["Portrait"])
    async def search_portrait_identities_image(
        file: Annotated[UploadFile, File()],
        request: Request,
        feature_space_id: Annotated[str | None, Form()] = None,
        limit: Annotated[int, Form(ge=1, le=200)] = 20,
        threshold: Annotated[float | None, Form(ge=-1, le=1)] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitSearchResponse]:
        data = await file.read(runtime.settings.max_image_bytes + 1)
        if len(data) > runtime.settings.max_image_bytes:
            raise ValueError(f"image exceeds {runtime.settings.max_image_bytes} bytes")
        result = await runtime.portrait.search_image(
            context,
            data,
            feature_space_id=feature_space_id,
            limit=limit,
            threshold=threshold,
        )
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/portrait/compare", tags=["Portrait"])
    async def compare_portrait_features(
        body: PortraitCompareRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitCompareResponse]:
        result = await runtime.portrait.compare(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/portrait/compare/images", tags=["Portrait"])
    async def compare_portrait_images(
        left: Annotated[UploadFile, File()],
        right: Annotated[UploadFile, File()],
        request: Request,
        feature_space_id: Annotated[str | None, Form()] = None,
        threshold: Annotated[float | None, Form(ge=-1, le=1)] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitCompareResponse]:
        left_data = await left.read(runtime.settings.max_image_bytes + 1)
        right_data = await right.read(runtime.settings.max_image_bytes + 1)
        if len(left_data) > runtime.settings.max_image_bytes or len(right_data) > runtime.settings.max_image_bytes:
            raise ValueError(f"image exceeds {runtime.settings.max_image_bytes} bytes")
        result = await runtime.portrait.compare_images(
            context,
            left_data,
            right_data,
            feature_space_id=feature_space_id,
            threshold=threshold,
        )
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/portrait/compare/assets", tags=["Portrait"])
    async def compare_portrait_assets(
        body: PortraitAssetCompareRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitCompareResponse]:
        await require_allowed(runtime.policy, context, "read", "media_asset", {"asset_id": body.left_asset_id})
        await require_allowed(runtime.policy, context, "read", "media_asset", {"asset_id": body.right_asset_id})
        left_asset = await runtime.state.get_asset(context.tenant_id, context.project_id, body.left_asset_id)
        right_asset = await runtime.state.get_asset(context.tenant_id, context.project_id, body.right_asset_id)
        if (
            left_asset is None
            or right_asset is None
            or left_asset.deleted_at is not None
            or right_asset.deleted_at is not None
            or left_asset.original_deleted_at is not None
            or right_asset.original_deleted_at is not None
        ):
            raise PortraitNotFound("portrait comparison asset not found")
        if left_asset.kind.value != "image" or right_asset.kind.value != "image":
            raise ValueError("portrait comparison assets must be images")
        result = await runtime.portrait.compare_images(
            context,
            await runtime.objects.get(left_asset.object_key),
            await runtime.objects.get(right_asset.object_key),
            feature_space_id=body.feature_space_id,
            threshold=body.threshold,
            mode="asset",
        )
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/portrait/compare/asset-image", tags=["Portrait"])
    async def compare_portrait_asset_image(
        asset_id: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
        request: Request,
        feature_space_id: Annotated[str | None, Form()] = None,
        threshold: Annotated[float | None, Form(ge=-1, le=1)] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitCompareResponse]:
        await require_allowed(runtime.policy, context, "read", "media_asset", {"asset_id": asset_id})
        asset = await runtime.state.get_asset(context.tenant_id, context.project_id, asset_id)
        if asset is None or asset.deleted_at is not None or asset.original_deleted_at is not None:
            raise PortraitNotFound("portrait comparison asset not found")
        if asset.kind != MediaKind.IMAGE:
            raise ValueError("portrait comparison assets must be images")
        right_data = await file.read(runtime.settings.max_image_bytes + 1)
        if len(right_data) > runtime.settings.max_image_bytes:
            raise ValueError(f"image exceeds {runtime.settings.max_image_bytes} bytes")
        result = await runtime.portrait.compare_images(
            context,
            await runtime.objects.get(asset.object_key),
            right_data,
            feature_space_id=feature_space_id,
            threshold=threshold,
            mode="mixed",
        )
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/portrait/compare/image-asset", tags=["Portrait"])
    async def compare_portrait_image_asset(
        file: Annotated[UploadFile, File()],
        asset_id: Annotated[str, Form()],
        request: Request,
        feature_space_id: Annotated[str | None, Form()] = None,
        threshold: Annotated[float | None, Form(ge=-1, le=1)] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitCompareResponse]:
        await require_allowed(runtime.policy, context, "read", "media_asset", {"asset_id": asset_id})
        asset = await runtime.state.get_asset(context.tenant_id, context.project_id, asset_id)
        if asset is None or asset.deleted_at is not None or asset.original_deleted_at is not None:
            raise PortraitNotFound("portrait comparison asset not found")
        if asset.kind != MediaKind.IMAGE:
            raise ValueError("portrait comparison assets must be images")
        left_data = await file.read(runtime.settings.max_image_bytes + 1)
        if len(left_data) > runtime.settings.max_image_bytes:
            raise ValueError(f"image exceeds {runtime.settings.max_image_bytes} bytes")
        result = await runtime.portrait.compare_images(
            context,
            left_data,
            await runtime.objects.get(asset.object_key),
            feature_space_id=feature_space_id,
            threshold=threshold,
            mode="mixed",
        )
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/search/text", tags=["Search"])
    async def search_text(
        body: SearchTextRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchResponse]:
        result = await runtime.search.text(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/search/image", tags=["Search"])
    async def search_portrait_image(
        file: Annotated[UploadFile, File()],
        request: Request,
        feature_space_id: Annotated[str | None, Form()] = None,
        profile_id: Annotated[str | None, Form()] = None,
        media_kinds: Annotated[str | None, Form()] = None,
        limit: Annotated[int, Form(ge=1, le=200)] = 50,
        threshold: Annotated[float | None, Form(ge=-1, le=1)] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchResponse]:
        data = await file.read(runtime.settings.max_image_bytes + 1)
        if len(data) > runtime.settings.max_image_bytes:
            raise ValueError(f"image exceeds {runtime.settings.max_image_bytes} bytes")
        selected_kinds = [MediaKind(value.strip()) for value in (media_kinds or "").split(",") if value.strip()]
        result = await runtime.search.portrait_image(
            context,
            data,
            feature_space_id=feature_space_id,
            profile_id=profile_id,
            media_kinds=selected_kinds,
            limit=limit,
            threshold=threshold,
        )
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/search/asset", tags=["Search"])
    async def search_portrait_asset(
        body: SearchAssetRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchResponse]:
        await require_allowed(runtime.policy, context, "read", "media_asset", {"asset_id": body.asset_id})
        asset = await runtime.state.get_asset(context.tenant_id, context.project_id, body.asset_id)
        if asset is None or asset.deleted_at is not None or asset.original_deleted_at is not None:
            raise ResourceNotFound("search asset not found")
        if asset.kind != MediaKind.IMAGE:
            raise ValueError("portrait search assets must be images")
        result = await runtime.search.portrait_image(
            context,
            await runtime.objects.get(asset.object_key),
            feature_space_id=body.feature_space_id,
            profile_id=body.profile_id,
            media_kinds=body.media_kinds,
            limit=body.limit,
            threshold=body.threshold,
        )
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post("/api/v1/search/saved", status_code=201, tags=["Search"])
    async def create_saved_search(
        body: CreateSavedSearchRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SavedSearch]:
        result = await runtime.search.create_saved_search(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get("/api/v1/search/saved", tags=["Search"])
    async def list_saved_searches(
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SavedSearchPage]:
        result = await runtime.search.list_saved_searches(context, offset=offset, limit=limit)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get("/api/v1/search/saved/{saved_search_id}", tags=["Search"])
    async def get_saved_search(
        saved_search_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SavedSearch]:
        result = await runtime.search.get_saved_search(context, saved_search_id)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.patch("/api/v1/search/saved/{saved_search_id}", tags=["Search"])
    async def update_saved_search(
        saved_search_id: str,
        body: UpdateSavedSearchRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SavedSearch]:
        result = await runtime.search.update_saved_search(context, saved_search_id, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.delete("/api/v1/search/saved/{saved_search_id}", status_code=204, tags=["Search"])
    async def delete_saved_search(
        saved_search_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.search.delete_saved_search(context, saved_search_id)
        return Response(status_code=204)

    @app.post("/api/v1/search/saved/{saved_search_id}/run", tags=["Search"])
    async def run_saved_search(
        saved_search_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchResponse]:
        result = await runtime.search.run_saved_search(context, saved_search_id)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get("/api/v1/indexes", tags=["Search"])
    async def list_search_indexes(
        request: Request,
        domain: Annotated[str | None, Query()] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[IndexDefinition]]:
        await require_allowed(runtime.policy, context, "list", "search_index", {"domain": domain})
        rows = await runtime.indexes.list_indexes(context.tenant_id, context.project_id, domain=domain)
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.post("/api/v1/indexes", status_code=201, tags=["Search"])
    async def create_search_index(
        body: IndexDefinition,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[IndexDefinition]:
        await require_allowed(runtime.policy, context, "write", "search_index", {"index_id": body.index_id})
        created = await runtime.indexes.create_index(body)
        await runtime.audit.record(
            context,
            action="index.create",
            resource_type="search_index",
            resource_id=created.index_id,
            evidence={"domain": created.domain, "record_kind": created.record_kind.value},
        )
        return _envelope(request, created)  # type: ignore[return-value]

    @app.get("/api/v1/indexes/{index_id}/records", tags=["Search"])
    async def list_search_index_records(
        index_id: str,
        request: Request,
        source_type: Annotated[str | None, Query()] = None,
        source_id: Annotated[str | None, Query()] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[IndexRecordView]]:
        await require_allowed(runtime.policy, context, "read", "search_index", {"index_id": index_id})
        if await runtime.indexes.get_index(index_id) is None:
            raise PortraitNotFound("search index not found")
        rows = await runtime.indexes.list_records(
            context.tenant_id,
            context.project_id,
            index_id=index_id,
            source_type=source_type,
            source_id=source_id,
            offset=offset,
            limit=limit,
        )
        views = [
            IndexRecordView(
                record_id=row.record_id,
                index_id=row.index_id,
                domain=row.domain,
                kind=row.kind,
                source=row.source,
                feature_id=row.feature_id,
                has_vector=row.vector is not None or row.feature_id is not None,
                text_snippet=(row.text or "")[:240] or None,
                metadata=row.metadata,
                status=row.status,
                created_at=row.created_at,
                expires_at=row.expires_at,
                deleted_at=row.deleted_at,
            )
            for row in rows
        ]
        return _envelope(request, views)  # type: ignore[return-value]

    @app.post("/api/v1/indexes/{index_id}/query/text", tags=["Search"])
    async def query_search_index_text(
        index_id: str,
        body: IndexTextQueryRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[dict[str, object]]]:
        await require_allowed(runtime.policy, context, "query", "search_index", {"index_id": index_id})
        if await runtime.indexes.get_index(index_id) is None:
            raise PortraitNotFound("search index not found")
        hits = await runtime.indexes.query_text(
            context.tenant_id,
            context.project_id,
            index_id,
            body.query,
            limit=body.limit,
        )
        await runtime.audit.record(
            context,
            action="index.query.text",
            resource_type="search_index",
            resource_id=index_id,
            evidence={"query_length": len(body.query), "hit_count": len(hits)},
        )
        return _envelope(request, [hit.model_dump(mode="json") for hit in hits])  # type: ignore[return-value]

    @app.post("/api/v1/indexes/{index_id}/query/vector", tags=["Search"])
    async def query_search_index_vector(
        index_id: str,
        body: IndexVectorQueryRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[IndexHit]]:
        await require_allowed(runtime.policy, context, "query", "search_index", {"index_id": index_id})
        if await runtime.indexes.get_index(index_id) is None:
            raise PortraitNotFound("search index not found")
        hits = await runtime.indexes.query_vector(
            context.tenant_id,
            context.project_id,
            index_id,
            body.vector,
            limit=body.limit,
            threshold=body.threshold,
        )
        await runtime.audit.record(
            context,
            action="index.query.vector",
            resource_type="search_index",
            resource_id=index_id,
            evidence={"dimension": len(body.vector), "hit_count": len(hits)},
        )
        return _envelope(request, hits)  # type: ignore[return-value]

    @app.get("/api/v1/enterprise/status", tags=["Legacy"], deprecated=True, include_in_schema=False)
    async def enterprise_status(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[EnterpriseStatus]:
        result = await enterprise_service().status(context)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post(
        "/api/v1/enterprise/sla/evaluate", tags=["Legacy"], deprecated=True, include_in_schema=False
    )
    async def enterprise_sla(
        body: dict[str, float],
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SlaSnapshot]:
        result = await enterprise_service().sla(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get(
        "/api/v1/enterprise/incidents", tags=["Legacy"], deprecated=True, include_in_schema=False
    )
    async def list_enterprise_incidents(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[Incident]]:
        rows = await enterprise_service().list_incidents(context)
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.post(
        "/api/v1/enterprise/incidents",
        status_code=201,
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def create_enterprise_incident(
        body: CreateIncidentRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Incident]:
        result = await enterprise_service().create_incident(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.post(
        "/api/v1/enterprise/incidents/{incident_id}/resolve",
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def resolve_enterprise_incident(
        incident_id: str,
        body: ResolveIncidentRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Incident]:
        result = await enterprise_service().resolve_incident(context, incident_id, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get(
        "/api/v1/enterprise/support/cases", tags=["Legacy"], deprecated=True, include_in_schema=False
    )
    async def list_enterprise_support_cases(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[SupportCase]]:
        rows = await enterprise_service().list_support_cases(context)
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.post(
        "/api/v1/enterprise/support/cases",
        status_code=201,
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def create_enterprise_support_case(
        body: CreateSupportCaseRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SupportCase]:
        result = await enterprise_service().create_support_case(context, body)
        return _envelope(request, result)  # type: ignore[return-value]

    @app.get(
        "/api/v1/enterprise/compliance/evidence",
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def list_enterprise_evidence(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[ComplianceEvidence]]:
        rows = await enterprise_service().list_evidence(context)
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.post(
        "/api/v1/enterprise/compliance/evidence",
        status_code=201,
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
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
        # Core owns qualification; Data owns idempotent intake and dataset construction.
        if runtime.settings.data_platform_mode == "http":
            await runtime.data.submit_hard_sample_manifest(context, result)
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
        packages = await runtime.state.list_model_packages()
        if not packages:
            packages = builtin_model_packages()
        rows = [package.model_dump(mode="json") for package in packages]
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
                "description": manifest.description,
                "supported_media_kinds": list(manifest.supported_media_kinds),
                "default_pipeline_id": manifest.default_pipeline_id
                or runtime.plugins.default_pipeline_id(manifest.domain_id),
                "navigation_order": manifest.navigation_order,
            }
            for manifest in runtime.plugins.manifests()
        ]
        return _envelope(request, rows)  # type: ignore[return-value]

    @app.get("/api/v1/platform/products", tags=["Platform"])
    async def list_platform_products(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[ProductCatalogItem]]:
        del context
        manifests = runtime.plugins.manifests()
        installed_domains = [manifest.domain_id for manifest in manifests]
        domain_scopes = {manifest.domain_id: manifest.product_scope for manifest in manifests}
        return _envelope(
            request,
            build_product_catalog(installed_domains, domain_scopes=domain_scopes),
        )  # type: ignore[return-value]

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
        snapshot = {}
        if "portrait" in installed_domains:
            with suppress(Exception):  # optional migrated runtime
                snapshot = portrait_capability_snapshot()
        return _envelope(  # type: ignore[return-value]
            request,
            build_portrait_intelligence(snapshot, installed_domains=installed_domains),
        )

    @app.get("/api/v1/platform/iam/summary", tags=["IAM"])
    async def iam_summary(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[IamSummary]:
        return _envelope(request, await runtime.access.summary(context))  # type: ignore[return-value]

    @app.post("/api/v1/auth/login", tags=["IAM"])
    async def login(body: LoginRequest, request: Request) -> ApiEnvelope[SessionResponse]:
        context = await runtime.access.authenticate_user(
            body.username,
            body.password,
            runtime.settings.default_tenant_id,
            runtime.settings.default_project_id,
        )
        if context is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid username or password")
        return _envelope(  # type: ignore[return-value]
            request,
            await runtime.control_plane.create_authenticated_session(context, ttl_seconds=body.ttl_seconds),
        )

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

    @app.post("/api/v1/platform/users/{user_id}/disable", tags=["IAM"])
    async def disable_user(
        user_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[UserAccount]:
        return _envelope(request, await runtime.access.set_user_disabled(context, user_id, True))  # type: ignore[return-value]

    @app.post("/api/v1/platform/users/{user_id}/restore", tags=["IAM"])
    async def restore_user(
        user_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[UserAccount]:
        return _envelope(request, await runtime.access.set_user_disabled(context, user_id, False))  # type: ignore[return-value]

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

    @app.post("/api/v1/platform/service-accounts/{service_account_id}/disable", tags=["IAM"])
    async def disable_service_account(
        service_account_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ServiceAccount]:
        return _envelope(request, await runtime.access.set_service_account_disabled(context, service_account_id, True))  # type: ignore[return-value]

    @app.post("/api/v1/platform/service-accounts/{service_account_id}/restore", tags=["IAM"])
    async def restore_service_account(
        service_account_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ServiceAccount]:
        return _envelope(request, await runtime.access.set_service_account_disabled(context, service_account_id, False))  # type: ignore[return-value]

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

    # 以下产品模块共享同一控制面，通过明确的权限作用域进行保护；
    # 所有变更都会像现有 Parse/Model/Data 资源一样写入审计记录。
    @app.post("/api/v1/platform/identity-providers", status_code=201, tags=["IAM"])
    async def create_identity_provider(
        body: CreateIdentityProviderRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[IdentityProvider]:
        return _envelope(request, await runtime.control_plane.create_identity_provider(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/platform/identity-providers", tags=["IAM"])
    async def list_identity_providers(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[IdentityProvider]]:
        return _envelope(request, await runtime.control_plane.list_identity_providers(context))  # type: ignore[return-value]

    @app.post("/api/v1/platform/identity-providers/{provider_id}/probe", tags=["IAM"])
    async def probe_identity_provider(
        provider_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[IdentityProvider]:
        return _envelope(request, await runtime.control_plane.probe_identity_provider(context, provider_id))  # type: ignore[return-value]

    @app.post("/api/v1/platform/sessions", status_code=201, tags=["IAM"])
    async def create_interactive_session(
        body: CreateSessionRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SessionResponse]:
        if await runtime.access.is_user_disabled(context.tenant_id, body.user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user is disabled")
        return _envelope(request, await runtime.control_plane.create_session(context, body))  # type: ignore[return-value]

    @app.post("/api/v1/platform/projects/lifecycle-requests", status_code=202, tags=["IAM"])
    async def request_project_lifecycle(
        body: CreateProjectLifecycleRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ProjectLifecycleRequest]:
        return _envelope(request, await runtime.control_plane.request_project_lifecycle(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/platform/projects/lifecycle-requests", tags=["IAM"])
    async def list_project_lifecycle_requests(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[ProjectLifecycleRequest]]:
        return _envelope(request, await runtime.control_plane.list_project_lifecycle_requests(context))  # type: ignore[return-value]

    @app.post("/api/v1/platform/projects/lifecycle-requests/{request_id}/decide", tags=["IAM"])
    async def decide_project_lifecycle(
        request_id: str,
        body: DecideProjectLifecycleRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ProjectLifecycleRequest]:
        return _envelope(request, await runtime.control_plane.decide_project_lifecycle(context, request_id, body))  # type: ignore[return-value]

    @app.put("/api/v1/platform/audit/retention", tags=["Operations"])
    async def set_audit_retention_policy(
        body: SetAuditRetentionPolicyRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AuditRetentionPolicy]:
        return _envelope(request, await runtime.control_plane.set_audit_retention_policy(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/platform/audit/retention", tags=["Operations"])
    async def get_audit_retention_policy(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[AuditRetentionPolicy]:
        return _envelope(request, await runtime.control_plane.get_audit_retention_policy(context))  # type: ignore[return-value]

    @app.post("/api/v1/platform/audit/purge", tags=["Operations"])
    async def purge_audit_events(
        body: PurgeAuditRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PurgeAuditResponse]:
        return _envelope(request, await runtime.control_plane.purge_audit_events(context, body))  # type: ignore[return-value]

    @app.post("/api/v1/platform/lifecycle/{resource_type}/{resource_id}/{action}", tags=["IAM"])
    async def transition_resource_lifecycle(
        resource_type: str,
        resource_id: str,
        action: str,
        request: Request,
        reason: str = Query(default="", max_length=2_000),
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ResourceLifecycleRecord]:
        return _envelope(
            request, await runtime.control_plane.lifecycle(context, resource_type, resource_id, action, reason)
        )  # type: ignore[return-value]

    @app.post("/api/v1/platform/quotas/plans", status_code=201, tags=["Operations"])
    async def create_quota_plan(
        body: CreateQuotaPlanRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[QuotaPlan]:
        return _envelope(request, await runtime.control_plane.create_quota_plan(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/platform/quotas/plans", tags=["Operations"])
    async def list_quota_plans(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[QuotaPlan]]:
        return _envelope(request, await runtime.control_plane.list_quota_plans(context))  # type: ignore[return-value]

    @app.post("/api/v1/platform/quotas/check", tags=["Operations"])
    async def check_quota(
        body: QuotaCheckRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[QuotaCheckResponse]:
        return _envelope(request, await runtime.control_plane.check_quota(context, body))  # type: ignore[return-value]

    @app.post(
        "/api/v1/platform/billing/accounts",
        status_code=201,
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def create_billing_account(
        body: CreateBillingAccountRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[BillingAccount]:
        return _envelope(request, await runtime.control_plane.create_billing_account(context, body))  # type: ignore[return-value]

    @app.get(
        "/api/v1/platform/billing/accounts", tags=["Legacy"], deprecated=True, include_in_schema=False
    )
    async def list_billing_accounts(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[BillingAccount]]:
        return _envelope(request, await runtime.control_plane.list_billing_accounts(context))  # type: ignore[return-value]

    @app.post(
        "/api/v1/platform/billing/meter-events",
        status_code=201,
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def record_meter_event(
        body: RecordMeterEventRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MeterEvent]:
        return _envelope(request, await runtime.control_plane.record_meter_event(context, body))  # type: ignore[return-value]

    @app.get(
        "/api/v1/platform/billing/usage", tags=["Legacy"], deprecated=True, include_in_schema=False
    )
    async def list_billing_usage(
        request: Request,
        account_id: str | None = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[BillingUsage]]:
        return _envelope(request, await runtime.control_plane.list_billing_usage(context, account_id))  # type: ignore[return-value]

    @app.post(
        "/api/v1/platform/billing/seats",
        status_code=201,
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def assign_billing_seat(
        body: AssignSeatRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SeatAssignment]:
        return _envelope(request, await runtime.control_plane.assign_billing_seat(context, body))  # type: ignore[return-value]

    @app.get(
        "/api/v1/platform/billing/seats", tags=["Legacy"], deprecated=True, include_in_schema=False
    )
    async def list_billing_seats(
        request: Request,
        account_id: str | None = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[SeatAssignment]]:
        return _envelope(request, await runtime.control_plane.list_billing_seats(context, account_id))  # type: ignore[return-value]

    @app.post("/api/v1/data/annotation-tasks", status_code=201, tags=["Data"])
    async def create_annotation_task(
        body: CreateAnnotationTaskRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AnnotationTask]:
        return _envelope(request, await runtime.data.create_annotation_task(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/data/annotation-tasks", tags=["Data"])
    async def list_annotation_tasks(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[AnnotationTask]]:
        return _envelope(request, await runtime.data.list_annotation_tasks(context))  # type: ignore[return-value]

    @app.post("/api/v1/data/annotation-providers", status_code=201, tags=["Data"])
    async def register_annotation_provider(
        body: CreateAnnotationProviderRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AnnotationProvider]:
        return _envelope(request, await runtime.data.register_annotation_provider(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/data/annotation-providers", tags=["Data"])
    async def list_annotation_providers(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[AnnotationProvider]]:
        return _envelope(request, await runtime.data.list_annotation_providers(context))  # type: ignore[return-value]

    @app.post("/api/v1/data/annotation-providers/{provider_id}/probe", tags=["Data"])
    async def probe_annotation_provider(
        provider_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AnnotationProvider]:
        return _envelope(request, await runtime.data.probe_annotation_provider(context, provider_id))  # type: ignore[return-value]

    @app.post("/api/v1/data/annotation-tasks/{task_id}/review", tags=["Data"])
    async def review_annotation_task(
        task_id: str,
        body: ReviewAnnotationTaskRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AnnotationTask]:
        return _envelope(request, await runtime.data.review_annotation_task(context, task_id, body))  # type: ignore[return-value]

    @app.post("/api/v1/platform/model-metrics", status_code=201, tags=["Model Governance"])
    async def record_model_metric(
        body: ModelMetricPoint,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ModelMetricPoint]:
        return _envelope(request, await runtime.control_plane.record_model_metric(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/platform/model-health", tags=["Model Governance"])
    async def model_health(
        model_id: str,
        model_version: str,
        capability: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ModelHealthSnapshot]:
        return _envelope(
            request, await runtime.control_plane.model_health(context, model_id, model_version, capability)
        )  # type: ignore[return-value]

    @app.post("/api/v1/platform/model-health/auto-rollback", tags=["Model Governance"])
    async def auto_rollback_model(
        body: AutoRollbackModelRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[dict[str, object]]:
        health = await runtime.control_plane.model_health(context, body.model_id, body.model_version, body.capability)
        if not health.rollback_recommended:
            return _envelope(request, {"rolled_back": False, "health": health})  # type: ignore[return-value]
        release = await runtime.feedback.auto_rollback(
            context,
            body.model_id,
            body.model_version,
            reason=body.reason,
        )
        return _envelope(request, {"rolled_back": True, "health": health, "release": release})  # type: ignore[return-value]

    @app.post("/api/v1/search/ranking-profiles", status_code=201, tags=["Search"])
    async def create_search_ranking_profile(
        body: CreateSearchRankingProfileRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchRankingProfile]:
        return _envelope(request, await runtime.control_plane.create_search_profile(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/search/ranking-profiles", tags=["Search"])
    async def list_search_ranking_profiles(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[SearchRankingProfile]]:
        return _envelope(request, await runtime.control_plane.list_search_profiles(context))  # type: ignore[return-value]

    @app.post("/api/v1/search/index-backends", status_code=201, tags=["Search"])
    async def register_index_backend(
        body: CreateIndexBackendRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[IndexBackend]:
        return _envelope(request, await runtime.control_plane.register_index_backend(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/search/index-backends", tags=["Search"])
    async def list_index_backends(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[IndexBackend]]:
        return _envelope(request, await runtime.control_plane.list_index_backends(context))  # type: ignore[return-value]

    @app.post("/api/v1/search/index-backends/{backend_id}/probe", tags=["Search"])
    async def probe_index_backend(
        backend_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[IndexBackend]:
        return _envelope(request, await runtime.control_plane.probe_index_backend(context, backend_id))  # type: ignore[return-value]

    @app.post("/api/v1/search/rerankers", status_code=201, tags=["Search"])
    async def register_search_reranker(
        body: CreateSearchRerankerRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchReranker]:
        return _envelope(request, await runtime.control_plane.register_search_reranker(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/search/rerankers", tags=["Search"])
    async def list_search_rerankers(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[SearchReranker]]:
        return _envelope(request, await runtime.control_plane.list_search_rerankers(context))  # type: ignore[return-value]

    @app.post("/api/v1/search/rerankers/{reranker_id}/probe", tags=["Search"])
    async def probe_search_reranker(
        reranker_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchReranker]:
        return _envelope(request, await runtime.control_plane.probe_search_reranker(context, reranker_id))  # type: ignore[return-value]

    @app.post("/api/v1/search/relevance-feedback", status_code=201, tags=["Search"])
    async def submit_search_relevance_feedback(
        body: CreateSearchRelevanceFeedbackRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchRelevanceFeedback]:
        return _envelope(request, await runtime.control_plane.submit_search_feedback(context, body))  # type: ignore[return-value]

    @app.post("/api/v1/search/evaluations", status_code=201, tags=["Search"])
    async def evaluate_search(
        body: CreateSearchEvaluationRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchEvaluation]:
        return _envelope(request, await runtime.control_plane.evaluate_search(context, body))  # type: ignore[return-value]

    @app.post("/api/v1/indexes/rebuild", status_code=202, tags=["Search"])
    async def rebuild_index(
        body: CreateIndexRebuildRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[IndexRebuildJob]:
        return _envelope(request, await runtime.control_plane.rebuild_index(context, body))  # type: ignore[return-value]

    @app.post("/api/v1/flows", status_code=201, tags=["Flow"])
    async def create_flow(
        body: CreateFlowRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[FlowDefinition]:
        return _envelope(request, await runtime.control_plane.create_flow(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/flows", tags=["Flow"])
    async def list_flows(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[FlowDefinition]]:
        return _envelope(request, await runtime.control_plane.list_flows(context))  # type: ignore[return-value]

    @app.post("/api/v1/flows/{flow_id}/execute", status_code=202, tags=["Flow"])
    async def execute_flow(
        flow_id: str,
        body: ExecuteFlowRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[FlowExecution]:
        return _envelope(request, await runtime.control_plane.execute_flow(context, flow_id, body))  # type: ignore[return-value]

    @app.get("/api/v1/flows/{flow_id}/executions/{execution_id}/approvals", tags=["Flow"])
    async def list_flow_approvals(
        flow_id: str,
        execution_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[FlowApproval]]:
        del flow_id
        return _envelope(request, await runtime.control_plane.list_flow_approvals(context, execution_id))  # type: ignore[return-value]

    @app.post("/api/v1/flows/approvals/{approval_id}/decide", tags=["Flow"])
    async def decide_flow_approval(
        approval_id: str,
        body: DecideApprovalRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[FlowApproval]:
        return _envelope(request, await runtime.control_plane.decide_flow_approval(context, approval_id, body))  # type: ignore[return-value]

    @app.post("/api/v1/portrait/clusters", status_code=201, tags=["Portrait Intelligence"])
    async def create_portrait_cluster(
        body: CreatePortraitClusterRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitCluster]:
        return _envelope(request, await runtime.control_plane.create_cluster(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/portrait/clusters", tags=["Portrait Intelligence"])
    async def list_portrait_clusters(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[PortraitCluster]]:
        return _envelope(request, await runtime.control_plane.list_clusters(context))  # type: ignore[return-value]

    @app.post("/api/v1/portrait/associations", status_code=201, tags=["Portrait Intelligence"])
    async def create_portrait_association(
        body: CreatePortraitAssociationRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitAssociation]:
        return _envelope(request, await runtime.control_plane.create_association(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/portrait/associations", tags=["Portrait Intelligence"])
    async def list_portrait_associations(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[PortraitAssociation]]:
        return _envelope(request, await runtime.control_plane.list_associations(context))  # type: ignore[return-value]

    @app.post("/api/v1/portrait/events", status_code=201, tags=["Portrait Intelligence"])
    async def create_portrait_event(
        body: CreatePortraitEventRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitEvent]:
        return _envelope(request, await runtime.control_plane.create_event(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/portrait/events", tags=["Portrait Intelligence"])
    async def list_portrait_events(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[PortraitEvent]]:
        return _envelope(request, await runtime.control_plane.list_events(context))  # type: ignore[return-value]

    @app.post("/api/v1/edge/devices", status_code=201, tags=["Edge"])
    async def register_edge_device(
        body: RegisterEdgeDeviceRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[EdgeDevice]:
        return _envelope(request, await runtime.control_plane.register_device(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/edge/devices", tags=["Edge"])
    async def list_edge_devices(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[EdgeDevice]]:
        return _envelope(request, await runtime.control_plane.list_devices(context))  # type: ignore[return-value]

    @app.post("/api/v1/edge/deployments", status_code=202, tags=["Edge"])
    async def create_edge_deployment(
        body: CreateEdgeDeploymentRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[EdgeDeployment]:
        return _envelope(request, await runtime.control_plane.deploy_edge(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/edge/deployments", tags=["Edge"])
    async def list_edge_deployments(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[EdgeDeployment]]:
        return _envelope(request, await runtime.control_plane.list_edge_deployments(context))  # type: ignore[return-value]

    @app.post("/api/v1/edge/deployments/{deployment_id}/acknowledge", tags=["Edge"])
    async def acknowledge_edge_deployment(
        deployment_id: str,
        body: AcknowledgeEdgeDeploymentRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[EdgeDeployment]:
        return _envelope(request, await runtime.control_plane.acknowledge_edge_deployment(context, deployment_id, body))  # type: ignore[return-value]

    @app.post("/api/v1/edge/devices/{device_id}/sync", status_code=202, tags=["Edge"])
    async def enqueue_edge_sync(
        device_id: str,
        object_ref: str,
        sha256: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[EdgeSyncItem]:
        return _envelope(request, await runtime.control_plane.edge_sync(context, device_id, object_ref, sha256))  # type: ignore[return-value]

    @app.post("/api/v1/edge/devices/{device_id}/heartbeat", tags=["Edge"])
    async def edge_device_heartbeat(
        device_id: str,
        body: EdgeHeartbeatRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[EdgeDevice]:
        return _envelope(request, await runtime.control_plane.edge_heartbeat(context, device_id, body))  # type: ignore[return-value]

    @app.post("/api/v1/edge/sync/{item_id}/acknowledge", tags=["Edge"])
    async def acknowledge_edge_sync(
        item_id: str,
        body: AcknowledgeEdgeSyncRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[EdgeSyncItem]:
        return _envelope(request, await runtime.control_plane.acknowledge_edge_sync(context, item_id, body))  # type: ignore[return-value]

    @app.post("/api/v1/agents/tools", status_code=201, tags=["Agent"])
    async def register_agent_tool(
        body: RegisterAgentToolRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentTool]:
        return _envelope(request, await runtime.control_plane.register_tool(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/agents/tools", tags=["Agent"])
    async def list_agent_tools(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[AgentTool]]:
        return _envelope(request, await runtime.control_plane.list_tools(context))  # type: ignore[return-value]

    @app.post("/api/v1/agents/actions", status_code=202, tags=["Agent"])
    async def propose_agent_action(
        body: ProposeAgentActionRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentAction]:
        return _envelope(request, await runtime.control_plane.propose_action(context, body))  # type: ignore[return-value]

    @app.post("/api/v1/agents/actions/{action_id}/decide", tags=["Agent"])
    async def decide_agent_action(
        action_id: str,
        body: ApproveAgentActionRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentAction]:
        return _envelope(request, await runtime.control_plane.decide_action(context, action_id, body))  # type: ignore[return-value]

    @app.post("/api/v1/agents/actions/{action_id}/execute", tags=["Agent"])
    async def execute_agent_action(
        action_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentAction]:
        return _envelope(request, await runtime.control_plane.execute_action(context, action_id))  # type: ignore[return-value]

    @app.post("/api/v1/agents/traces", status_code=201, tags=["Agent"])
    async def record_agent_trace(
        body: CreateAgentTraceRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentTrace]:
        return _envelope(request, await runtime.control_plane.record_agent_trace(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/agents/traces", tags=["Agent"])
    async def list_agent_traces(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[AgentTrace]]:
        return _envelope(request, await runtime.control_plane.list_agent_traces(context))  # type: ignore[return-value]

    @app.post("/api/v1/agents/evaluations", status_code=201, tags=["Agent"])
    async def record_agent_evaluation(
        body: CreateAgentEvaluationRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentEvaluation]:
        return _envelope(request, await runtime.control_plane.record_agent_evaluation(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/agents/evaluations", tags=["Agent"])
    async def list_agent_evaluations(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[AgentEvaluation]]:
        return _envelope(request, await runtime.control_plane.list_agent_evaluations(context))  # type: ignore[return-value]

    @app.put("/api/v1/agents/memory", tags=["Agent"])
    async def put_agent_memory(
        body: PutAgentMemoryRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentMemoryEntry]:
        return _envelope(request, await runtime.control_plane.put_agent_memory(context, body))  # type: ignore[return-value]

    @app.get("/api/v1/agents/memory", tags=["Agent"])
    async def get_agent_memory(
        namespace: str,
        key: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentMemoryEntry | None]:
        return _envelope(request, await runtime.control_plane.get_agent_memory(context, namespace, key))  # type: ignore[return-value]

    @app.post("/api/v1/platform/workers", status_code=201, tags=["Operations"])
    async def register_worker(
        body: RegisterWorkerRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[WorkerLease]:
        return _envelope(request, await runtime.control_plane.register_worker(context, body))  # type: ignore[return-value]

    @app.post("/api/v1/platform/workers/{worker_id}/heartbeat", tags=["Operations"])
    async def heartbeat_worker(
        worker_id: str,
        body: WorkerHeartbeatRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[WorkerLease]:
        return _envelope(request, await runtime.control_plane.heartbeat_worker(context, worker_id, body))  # type: ignore[return-value]

    @app.get("/api/v1/platform/workers", tags=["Operations"])
    async def list_workers(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[WorkerLease]]:
        return _envelope(request, await runtime.control_plane.list_workers(context))  # type: ignore[return-value]

    @app.get("/api/v1/platform/deployment/topology", tags=["Operations"])
    async def deployment_topology(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[DeploymentTopology]:
        return _envelope(request, await runtime.control_plane.topology(context))  # type: ignore[return-value]

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
                policy_provider=runtime.policy.provider_id,
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
