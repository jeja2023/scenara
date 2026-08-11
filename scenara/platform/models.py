from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


class ExtensibleModel(BaseModel):
    model_config = ConfigDict(extra="allow", protected_namespaces=())


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    STREAM = "stream"


class SourceKind(StrEnum):
    STREAM = "stream"


class SampleStrategy(StrEnum):
    """视频与实时流的抽帧策略。"""

    INTERVAL = "interval"
    KEYFRAME = "keyframe"
    SCENE_CHANGE = "scene_change"
    UNIFORM = "uniform"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


TERMINAL_RUN_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}


class PipelineStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    ACTIVE = "active"
    RETIRED = "retired"


type DomainId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")]


class PrincipalContext(StrictModel):
    tenant_id: str
    project_id: str
    principal_id: str = "anonymous"
    # 本地开发边界创建的上下文不受限制。
    # 已认证凭据始终提供明确且非空的集合，因此显式空集合表示该凭据没有访问权限。
    scopes: frozenset[str] = Field(default_factory=lambda: frozenset({"*"}))
    product_ids: frozenset[str] = Field(default_factory=lambda: frozenset({"*"}))


class MediaTechnicalMetadata(StrictModel):
    format: str | None = None
    container: str | None = None
    codec: str | None = None
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    fps: float | None = Field(default=None, gt=0)
    frame_count: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    page_count: int | None = Field(default=None, ge=1)
    sampled_units: int | None = Field(default=None, ge=0)
    frames_read: int | None = Field(default=None, ge=0)
    sample_interval_ms: int | None = Field(default=None, ge=1)
    sample_strategy: SampleStrategy | None = None
    sample_start_ms: int | None = Field(default=None, ge=0)
    sample_end_ms: int | None = Field(default=None, ge=0)
    keyframe_count: int | None = Field(default=None, ge=0)
    scene_change_count: int | None = Field(default=None, ge=0)
    frame_max_edge: int | None = Field(default=None, gt=0)
    decode_seek_used: bool | None = None
    reconnect_count: int | None = Field(default=None, ge=0)
    elapsed_ms: int | None = Field(default=None, ge=0)
    stream_segment_duration_ms: int | None = Field(default=None, ge=1_000)
    stream_segment_index: int | None = Field(default=None, ge=0)
    timestamp_source: Literal["decoder_pts", "position_msec", "monotonic_clock"] | None = None


class MediaAsset(StrictModel):
    asset_id: str
    tenant_id: str
    project_id: str
    kind: MediaKind
    filename: str | None = None
    content_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    object_key: str
    preview_object_key: str | None = None
    preview_content_type: str | None = None
    preview_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    metadata: MediaTechnicalMetadata = Field(default_factory=MediaTechnicalMetadata)
    temporary: bool = False
    created_at: float
    expires_at: float | None = None
    original_deleted_at: float | None = None
    deleted_at: float | None = None


class CreateMediaSourceRequest(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    url: str = Field(min_length=1, max_length=4096)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MediaSource(StrictModel):
    source_id: str
    tenant_id: str
    project_id: str
    kind: SourceKind = SourceKind.STREAM
    name: str
    masked_url: str
    secret_ref: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float


class MediaSourceView(StrictModel):
    source_id: str
    kind: SourceKind = SourceKind.STREAM
    name: str
    masked_url: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float


class MediaSourceProbe(StrictModel):
    source_id: str
    reachable: bool
    latency_ms: int = Field(ge=0)
    metadata: MediaTechnicalMetadata = Field(default_factory=MediaTechnicalMetadata)
    checked_at: float


class DatasetStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class DatasetVersionStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PUBLISHED = "published"
    RETIRED = "retired"


class DatasetRecord(StrictModel):
    dataset_id: str = Field(min_length=2, max_length=128)
    tenant_id: str
    project_id: str
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=4_000)
    status: DatasetStatus = DatasetStatus.DRAFT
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float
    updated_at: float


class DatasetVersion(StrictModel):
    version_id: str = Field(min_length=2, max_length=128)
    dataset_id: str
    tenant_id: str
    project_id: str
    version: str = Field(min_length=1, max_length=64)
    status: DatasetVersionStatus = DatasetVersionStatus.DRAFT
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    asset_ids: list[str] = Field(default_factory=list, max_length=100_000)
    item_count: int = Field(default=0, ge=0)
    quality_score: float | None = Field(default=None, ge=0, le=1)
    lineage: dict[str, Any] = Field(default_factory=dict)
    annotation_summary: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_at: float
    updated_at: float


class CreateDatasetRequest(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=4_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateDatasetRequest(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=4_000)
    status: DatasetStatus | None = None
    metadata: dict[str, Any] | None = None


class CreateDatasetVersionRequest(StrictModel):
    version: str = Field(min_length=1, max_length=64)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    asset_ids: list[str] = Field(default_factory=list, max_length=100_000)
    quality_score: float | None = Field(default=None, ge=0, le=1)
    lineage: dict[str, Any] = Field(default_factory=dict)
    annotation_summary: dict[str, Any] = Field(default_factory=dict)


class TransitionDatasetVersionRequest(StrictModel):
    status: DatasetVersionStatus


class DatasetPage(StrictModel):
    items: list[DatasetRecord]
    offset: int
    limit: int
    total: int


class DatasetVersionPage(StrictModel):
    items: list[DatasetVersion]
    offset: int
    limit: int
    total: int


class SavedSearchMode(StrEnum):
    TEXT = "text"
    PORTRAIT = "portrait"


class SavedSearch(StrictModel):
    saved_search_id: str = Field(min_length=2, max_length=128)
    tenant_id: str
    project_id: str
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2_000)
    mode: SavedSearchMode
    definition: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_at: float
    updated_at: float
    last_run_at: float | None = None


class CreateSavedSearchRequest(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2_000)
    mode: SavedSearchMode
    definition: dict[str, Any] = Field(default_factory=dict)


class UpdateSavedSearchRequest(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2_000)
    definition: dict[str, Any] | None = None


class SavedSearchPage(StrictModel):
    items: list[SavedSearch]
    offset: int
    limit: int
    total: int


class CreateWebhookSubscriptionRequest(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=2048)
    secret: str = Field(min_length=16, max_length=512)
    event_types: frozenset[str] = Field(min_length=1, max_length=32)


class WebhookSubscription(StrictModel):
    endpoint_id: str
    tenant_id: str
    project_id: str
    name: str
    url: str
    secret_ref: str
    event_types: frozenset[str]
    enabled: bool = True
    created_at: float


class WebhookSubscriptionView(StrictModel):
    endpoint_id: str
    name: str
    url: str
    event_types: frozenset[str]
    enabled: bool
    created_at: float


class WebhookDeliveryRecord(StrictModel):
    delivery_id: str
    tenant_id: str
    project_id: str
    endpoint_id: str
    event_id: str
    event_type: str
    payload: dict[str, Any]
    status: Literal["pending", "delivering", "delivered", "dead_letter"] = "pending"
    attempts: int = Field(default=0, ge=0, le=100)
    next_attempt_at: float
    status_code: int | None = None
    last_error: str | None = None
    created_at: float
    updated_at: float
    delivered_at: float | None = None


class PipelineRef(StrictModel):
    pipeline_id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=32)


class PipelineSelection(StrictModel):
    pipeline_id: str = Field(min_length=1, max_length=128)
    version: str | None = Field(default=None, min_length=1, max_length=32)


class PipelineTransitionRequest(StrictModel):
    status: PipelineStatus


class CreateRunRequest(StrictModel):
    domain: DomainId
    pipeline: PipelineRef
    asset_id: str | None = None
    source_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=-100, le=100)
    wait_ms: int = Field(default=0, ge=0, le=30_000)


class RunRecord(StrictModel):
    run_id: str
    tenant_id: str
    project_id: str
    principal_id: str = "anonymous"
    domain: DomainId
    pipeline: PipelineRef
    asset_id: str | None = None
    source_id: str | None = None
    stream_session_id: str | None = None
    stream_segment_index: int | None = Field(default=None, ge=0)
    previous_run_id: str | None = None
    next_run_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    status: RunStatus = RunStatus.QUEUED
    revision: int = Field(default=1, ge=1)
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    error_code: str | None = None
    termination_reason: str | None = None
    created_at: float
    updated_at: float
    started_at: float | None = None
    completed_at: float | None = None


class RunEvent(StrictModel):
    run_id: str
    event_id: int = Field(ge=1)
    event_type: str
    status: RunStatus
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: float


class StreamSessionView(StrictModel):
    session_id: str
    source_id: str
    domain: DomainId
    pipeline: PipelineRef
    status: Literal["active", "completed", "failed", "cancelled"]
    current_run_id: str
    segment_count: int = Field(ge=1)
    created_at: float
    updated_at: float


class BoundingBox(StrictModel):
    x: float
    y: float
    width: float = Field(ge=0)
    height: float = Field(ge=0)


class Point(StrictModel):
    x: float
    y: float


class VisionObject(ExtensibleModel):
    object_id: str
    object_type: str
    score: float | None = Field(default=None, ge=0, le=1)
    bbox: BoundingBox | None = None
    polygon: list[Point] | None = None
    track_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    feature_refs: list[str] = Field(default_factory=list)
    crop_artifact_id: str | None = None
    """Identifier of the cropped feature image in ``ResultEnvelope.artifacts``."""


class PortraitDomainPayload(ExtensibleModel):
    domain: Literal["portrait"] = "portrait"
    schema_version: Literal["1.0"] = "1.0"
    persons: list[VisionObject] = Field(default_factory=list)
    faces: list[VisionObject] = Field(default_factory=list)
    tracks: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class OcrTextBlock(ExtensibleModel):
    block_id: str
    text: str
    score: float | None = Field(default=None, ge=0, le=1)
    polygon: list[Point] = Field(default_factory=list)
    block_type: Literal["text", "title", "paragraph", "image", "table"] = "text"
    reading_order: int | None = Field(default=None, ge=0)


class OcrDomainPayload(ExtensibleModel):
    domain: Literal["ocr"] = "ocr"
    schema_version: Literal["1.0"] = "1.0"
    text: str = ""
    blocks: list[OcrTextBlock] = Field(default_factory=list)
    language: str | None = None


class GenericDomainPayload(ExtensibleModel):
    """Fallback payload for a registered domain without a platform model."""

    domain: DomainId
    schema_version: str = "1.0"


# 保持一方负载的强类型，同时允许插件引入自己的负载结构，
# 无需修改平台模型联合类型。
DomainPayload = PortraitDomainPayload | OcrDomainPayload | GenericDomainPayload


class MediaUnitResult(StrictModel):
    unit_id: str
    unit_type: Literal["frame", "page"]
    index: int = Field(ge=0)
    pts_ms: int | None = Field(default=None, ge=0)
    page_number: int | None = Field(default=None, ge=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    objects: list[VisionObject] = Field(default_factory=list)
    frame_artifact_id: str | None = None
    """Identifier of the full unit image in ``ResultEnvelope.artifacts``."""


class ModelProvenance(StrictModel):
    capability: str
    model_id: str
    version: str
    sha256: str | None = None
    production_ready: bool = False


class ResultRelation(StrictModel):
    relation_type: str
    source_object_id: str
    target_object_id: str
    score: float | None = Field(default=None, ge=0, le=1)


class ResultArtifact(StrictModel):
    """Derived binary produced while executing a run (feature crops, unit frames)."""

    artifact_id: str
    artifact_type: str
    object_key: str
    content_type: str
    sha256: str = Field(min_length=64, max_length=64)


class ResultIndexVector(StrictModel):
    """Protected vector hint consumed while a result is being indexed.

    This field is intentionally attached to the in-memory result only. It is
    never serialized into the public result document or API response.
    """

    object_id: str
    feature_space_id: str
    model_id: str
    model_version: str
    vector: list[float] = Field(min_length=1, max_length=65_536)
    quality: float | None = Field(default=None, ge=0, le=1)
    modality: str = "face"


class ProvenanceEvidence(StrictModel):
    source_sha256: str | None = None
    generated_by: str = "scenara"
    development_substitutes: list[str] = Field(default_factory=list)


class ResultEnvelope(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    domain: DomainId
    pipeline: PipelineRef
    asset_id: str | None = None
    source_id: str | None = None
    units: list[MediaUnitResult] = Field(default_factory=list)
    domain_payload: DomainPayload
    relations: list[ResultRelation] = Field(default_factory=list)
    artifacts: list[ResultArtifact] = Field(default_factory=list)
    models: list[ModelProvenance] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)
    media_metadata: MediaTechnicalMetadata = Field(default_factory=MediaTechnicalMetadata)
    warnings: list[str] = Field(default_factory=list)
    provenance: ProvenanceEvidence = Field(default_factory=ProvenanceEvidence)
    created_at: float
    _index_vectors: list[ResultIndexVector] = PrivateAttr(default_factory=list)
    # Private handoff used by the trajectory registrar; never serialized.
    _trajectory_tracks: list[dict[str, Any]] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def validate_domain_payload(self) -> ResultEnvelope:
        if self.domain != self.domain_payload.domain:
            raise ValueError("domain must match domain_payload.domain")
        return self


class ResultReference(StrictModel):
    run_id: str
    schema_version: Literal["1.0"] = "1.0"
    object_key: str
    sha256: str = Field(min_length=64, max_length=64)
    unit_count: int = Field(ge=0)
    shard_keys: list[str] = Field(default_factory=list)
    shard_sha256: list[str] = Field(default_factory=list)
    shard_unit_counts: list[int] = Field(default_factory=list)
    domain: DomainId
    created_at: float
    asset_id: str | None = None
    source_id: str | None = None
    media_kind: MediaKind | None = None
    resource_name: str | None = None
    object_count: int = Field(default=0, ge=0)
    person_count: int = Field(default=0, ge=0)
    face_count: int = Field(default=0, ge=0)
    ocr_block_count: int = Field(default=0, ge=0)
    text_length: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    index_status: Literal["ready", "partial"] = "ready"


class ResultSummary(StrictModel):
    """Searchable result projection used by the global result center."""

    result_id: str
    run_id: str
    domain: DomainId
    pipeline: PipelineRef
    status: RunStatus
    asset_id: str | None = None
    source_id: str | None = None
    media_kind: MediaKind | None = None
    resource_name: str | None = None
    unit_count: int = Field(ge=0)
    object_count: int = Field(ge=0)
    person_count: int = Field(ge=0)
    face_count: int = Field(ge=0)
    ocr_block_count: int = Field(ge=0)
    text_length: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    index_status: Literal["ready", "partial"] = "ready"
    created_at: float


class ResultSummaryPage(StrictModel):
    items: list[ResultSummary]
    offset: int
    limit: int
    total: int


class ObjectRetentionRecord(StrictModel):
    tenant_id: str
    project_id: str
    object_key: str
    category: Literal["raw_media", "preview", "structured_result", "biometric"]
    owner_type: Literal["media_asset", "run_result", "portrait_enrollment"]
    owner_id: str
    created_at: float
    expires_at: float | None = None
    deleted_at: float | None = None


class ApiEnvelope[T](StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: str
    data: T


class RunPage(StrictModel):
    items: list[RunRecord]
    offset: int
    limit: int
    total: int


class ResultPage(StrictModel):
    result: ResultEnvelope
    unit_offset: int
    unit_limit: int
    unit_total: int


class ParseImageResponse(StrictModel):
    asset: MediaAsset
    run: RunRecord
    result: ResultEnvelope | None = None


class ParseVideoResponse(StrictModel):
    asset: MediaAsset
    run: RunRecord
    result: ResultEnvelope | None = None


class ParseDocumentResponse(StrictModel):
    asset: MediaAsset
    run: RunRecord
    result: ResultEnvelope | None = None


class ParseStreamRequest(StrictModel):
    source_id: str = Field(min_length=1, max_length=128)
    domain: DomainId
    pipeline: PipelineSelection
    parameters: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=-100, le=100)
    wait_ms: int = Field(default=0, ge=0, le=30_000)


class MediaAssetPage(StrictModel):
    items: list[MediaAsset]
    offset: int
    limit: int
    total: int


class MediaSourcePage(StrictModel):
    items: list[MediaSourceView]
    offset: int
    limit: int
    total: int


class SystemStatus(StrictModel):
    version: str
    profile: str
    state_backend: str
    object_backend: str
    queue_backend: str
    production_models_required: bool
    auth_required: bool
    enterprise_policy_provider: str = "not_configured"


type ProductId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")]


class ProductLayer(StrEnum):
    PRODUCT_MODULE = "product_module"
    CONTROL_PLANE = "control_plane"
    DEVELOPER_SURFACE = "developer_surface"
    FOUNDATION = "foundation"


class ProductMaturity(StrEnum):
    AVAILABLE = "available"
    SEED = "seed"
    PLANNED = "planned"
    GATED = "gated"


class ProductCatalogItem(StrictModel):
    product_id: ProductId
    name: str
    layer: ProductLayer
    maturity: ProductMaturity
    summary: str
    current_scope: list[str] = Field(default_factory=list)
    not_in_scope_yet: list[str] = Field(default_factory=list)
    console_route: str | None = None
    api_paths: list[str] = Field(default_factory=list)
    depends_on: list[ProductId] = Field(default_factory=list)
    next_gate: str


type RepositoryId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")]
type RepositoryResponsibilityId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,95}$")]


class RepositoryKind(StrEnum):
    PLATFORM_INTEGRATION = "platform_integration"
    SPECIALIZED_PRODUCT = "specialized_product"


class RepositoryLifecycle(StrEnum):
    CURRENT = "current"
    EXTERNAL_EXISTING = "external_existing"
    PLANNED = "planned"


class RepositoryBoundaryRule(StrEnum):
    VERSIONED_CONTRACTS_ONLY = "versioned_contracts_only"
    NO_SHARED_DATABASE = "no_shared_database"
    NO_CROSS_REPOSITORY_SOURCE_IMPORTS = "no_cross_repository_source_imports"
    IMMUTABLE_ARTIFACT_REFERENCES = "immutable_artifact_references"


class RepositoryContractTransport(StrEnum):
    VERSIONED_API = "versioned_api"
    EVENT = "event"
    IMMUTABLE_MANIFEST = "immutable_manifest"


class RepositoryTopologyItem(StrictModel):
    repository_id: RepositoryId
    name: str
    kind: RepositoryKind
    lifecycle: RepositoryLifecycle
    current_repository: bool = False
    primary_product_ids: list[ProductId] = Field(default_factory=list)
    integration_product_ids: list[ProductId] = Field(default_factory=list)
    responsibilities: list[RepositoryResponsibilityId] = Field(default_factory=list)
    excluded_responsibilities: list[RepositoryResponsibilityId] = Field(default_factory=list)
    next_gate: str


class RepositoryIntegrationContract(StrictModel):
    contract_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")]
    producer_repository_id: RepositoryId
    consumer_repository_id: RepositoryId
    transport: RepositoryContractTransport
    payload_type: Annotated[str, Field(pattern=r"^[A-Z][A-Za-z0-9]{1,63}$")]
    release_version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    schema_path: Annotated[str, Field(pattern=r"^contracts/repository/[^/]+/[^/]+\.schema\.json$")]
    compatibility: Literal["backward"] = "backward"
    invariants: list[RepositoryResponsibilityId] = Field(default_factory=list)


class RepositoryTopology(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    current_repository_id: RepositoryId
    repositories: list[RepositoryTopologyItem]
    integration_contracts: list[RepositoryIntegrationContract]
    boundary_rules: list[RepositoryBoundaryRule]

    @model_validator(mode="after")
    def validate_repository_references(self) -> RepositoryTopology:
        repository_ids = [repository.repository_id for repository in self.repositories]
        if len(repository_ids) != len(set(repository_ids)):
            raise ValueError("repository identifiers must be unique")
        if self.current_repository_id not in repository_ids:
            raise ValueError("current repository must exist in repositories")
        current = [repository.repository_id for repository in self.repositories if repository.current_repository]
        if current != [self.current_repository_id]:
            raise ValueError("exactly the declared current repository must be marked current")
        for contract in self.integration_contracts:
            if contract.producer_repository_id not in repository_ids:
                raise ValueError(f"unknown producer repository: {contract.producer_repository_id}")
            if contract.consumer_repository_id not in repository_ids:
                raise ValueError(f"unknown consumer repository: {contract.consumer_repository_id}")
        return self


class AccessCapabilityStatus(StrEnum):
    AVAILABLE = "available"
    SEED = "seed"
    PLANNED = "planned"
    GATED = "gated"


class AccessCapabilityItem(StrictModel):
    capability_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    name: str
    status: AccessCapabilityStatus
    summary: str
    current_scope: list[str] = Field(default_factory=list)
    not_in_scope_yet: list[str] = Field(default_factory=list)
    next_gate: str


class AccessFoundationStatus(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    auth_mode: Literal["development_open", "single_bearer_token"]
    principal_source: Literal["anonymous", "api_token", "service_account_api_key", "header"]
    tenant_id: str
    project_id: str
    principal_id: str
    policy_provider: str
    capabilities: list[AccessCapabilityItem]


type AccessId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")]


class PrincipalType(StrEnum):
    USER = "user"
    SERVICE_ACCOUNT = "service_account"


class EntitlementStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Organization(StrictModel):
    tenant_id: AccessId
    display_name: str = Field(min_length=1, max_length=256)
    created_at: float
    updated_at: float


class Project(StrictModel):
    tenant_id: AccessId
    project_id: AccessId
    display_name: str = Field(min_length=1, max_length=256)
    created_at: float
    updated_at: float


class UserAccount(StrictModel):
    tenant_id: AccessId
    user_id: AccessId
    display_name: str = Field(min_length=1, max_length=256)
    email: str | None = Field(default=None, max_length=320)
    disabled: bool = False
    created_at: float
    updated_at: float


class UserCredential(StrictModel):
    tenant_id: AccessId
    user_id: AccessId
    password_hash: str = Field(min_length=32, max_length=512)
    created_at: float
    updated_at: float


class Role(StrictModel):
    tenant_id: AccessId
    role_id: AccessId
    display_name: str = Field(min_length=1, max_length=256)
    scopes: frozenset[str] = Field(min_length=1, max_length=128)
    product_ids: frozenset[ProductId] = Field(default_factory=frozenset)
    created_at: float
    updated_at: float


class Membership(StrictModel):
    tenant_id: AccessId
    project_id: AccessId
    principal_id: AccessId
    principal_type: PrincipalType
    role_ids: frozenset[AccessId] = Field(min_length=1, max_length=64)
    created_at: float
    updated_at: float


class ServiceAccount(StrictModel):
    tenant_id: AccessId
    project_id: AccessId
    service_account_id: AccessId
    display_name: str = Field(min_length=1, max_length=256)
    scopes: frozenset[str] = Field(min_length=1, max_length=128)
    product_ids: frozenset[ProductId] = Field(default_factory=frozenset)
    disabled: bool = False
    created_at: float
    updated_at: float


class ApiKeyRecord(StrictModel):
    tenant_id: AccessId
    project_id: AccessId
    key_id: AccessId
    service_account_id: AccessId
    name: str = Field(min_length=1, max_length=256)
    token_prefix: str = Field(min_length=8, max_length=32)
    scopes: frozenset[str] = Field(min_length=1, max_length=128)
    product_ids: frozenset[ProductId] = Field(default_factory=frozenset)
    expires_at: float | None = None
    revoked_at: float | None = None
    last_used_at: float | None = None
    created_at: float


class ProductEntitlement(StrictModel):
    tenant_id: AccessId
    project_id: AccessId
    product_id: ProductId
    status: EntitlementStatus = EntitlementStatus.ACTIVE
    source: Literal["manual", "enterprise_license", "system"] = "manual"
    created_at: float
    updated_at: float


class CreateOrganizationRequest(StrictModel):
    display_name: str = Field(min_length=1, max_length=256)


class CreateProjectRequest(StrictModel):
    project_id: AccessId | None = None
    display_name: str = Field(min_length=1, max_length=256)


class CreateUserRequest(StrictModel):
    user_id: AccessId | None = None
    display_name: str = Field(min_length=1, max_length=256)
    email: str | None = Field(default=None, max_length=320)
    password: str | None = Field(default=None, min_length=8, max_length=256)


class LoginRequest(StrictModel):
    username: AccessId
    password: str = Field(min_length=1, max_length=256)
    ttl_seconds: int = Field(default=28_800, ge=60, le=86_400)


class CreateRoleRequest(StrictModel):
    role_id: AccessId | None = None
    display_name: str = Field(min_length=1, max_length=256)
    scopes: frozenset[str] = Field(min_length=1, max_length=128)
    product_ids: frozenset[ProductId] = Field(default_factory=frozenset)


class CreateMembershipRequest(StrictModel):
    project_id: AccessId | None = None
    principal_id: AccessId
    principal_type: PrincipalType
    role_ids: frozenset[AccessId] = Field(min_length=1, max_length=64)


class CreateServiceAccountRequest(StrictModel):
    service_account_id: AccessId | None = None
    display_name: str = Field(min_length=1, max_length=256)
    scopes: frozenset[str] = Field(min_length=1, max_length=128)
    product_ids: frozenset[ProductId] = Field(default_factory=frozenset)


class CreateApiKeyRequest(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    scopes: frozenset[str] | None = Field(default=None, min_length=1, max_length=128)
    product_ids: frozenset[ProductId] | None = None
    expires_at: float | None = None


class CreateApiKeyResponse(StrictModel):
    record: ApiKeyRecord
    api_key: str


class CreateProductEntitlementRequest(StrictModel):
    project_id: AccessId | None = None
    product_id: ProductId
    status: EntitlementStatus = EntitlementStatus.ACTIVE
    source: Literal["manual", "enterprise_license", "system"] = "manual"


class UpdateProductEntitlementRequest(StrictModel):
    status: EntitlementStatus
    source: Literal["manual", "enterprise_license", "system"] = "manual"


class IamInventory(StrictModel):
    organizations: int
    projects: int
    users: int
    roles: int
    memberships: int
    service_accounts: int
    api_keys: int
    product_entitlements: int


class IamSummary(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: str
    project_id: str
    inventory: IamInventory
    default_admin_scopes: frozenset[str]


class ApiErrorDetail(StrictModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApiErrorEnvelope(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: str
    error: ApiErrorDetail


# ---------------------------------------------------------------------------
# 人像智能基础平台契约类型
# ---------------------------------------------------------------------------

type PortraitModuleId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")]


class PortraitModuleMaturity(StrEnum):
    """Six-value maturity ladder for portrait AI modules.

    ``external`` means the responsibility belongs to another repository
    (e.g. model training → scenara-model).  The platform contract records
    the gap explicitly rather than omitting the module.
    """

    AVAILABLE = "available"
    PARTIAL = "partial"
    SEED = "seed"
    PLANNED = "planned"
    EXTERNAL = "external"


class PortraitCapabilityReadiness(StrEnum):
    """Maps directly to the ``status`` field in model-capabilities.yml."""

    READY = "ready"
    FALLBACK = "fallback"
    PLACEHOLDER = "placeholder"
    NOT_CONFIGURED = "not_configured"


class PortraitCapabilityItem(StrictModel):
    """Readiness record for a single portrait AI capability."""

    capability_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")]
    readiness: PortraitCapabilityReadiness
    production_ready: bool
    current_model: str | None = None
    target_model: str | None = None
    embedding_dimension: int | None = None
    target_embedding_dimension: int | None = None


class PortraitModuleItem(StrictModel):
    """One of the six strategic capability modules."""

    module_id: PortraitModuleId
    name: str
    maturity: PortraitModuleMaturity
    summary: str
    owner_repository_id: RepositoryId
    current_scope: list[str] = Field(default_factory=list)
    not_in_scope_yet: list[str] = Field(default_factory=list)
    next_gate: str


class PortraitAssetItem(StrictModel):
    """One of the three long-term strategic assets."""

    asset_id: PortraitModuleId
    name: str
    maturity: PortraitModuleMaturity
    summary: str
    depends_on_modules: list[PortraitModuleId] = Field(default_factory=list)
    next_gate: str


class PortraitIntelligenceStatus(StrictModel):
    """Machine-readable projection of the Portrait Intelligence Foundation Platform strategy.

    Consumed by ``GET /api/v1/platform/portrait-intelligence``,
    ``get_portrait_intelligence()`` in both SDKs, and the Console overview panel.
    This contract describes *intent and current readiness*, not deployed capability.
    Deployed model capability truth is in ``model-capabilities.yml``.
    """

    schema_version: Literal["1.0"] = "1.0"
    positioning: Literal["portrait_intelligence_foundation_platform"] = "portrait_intelligence_foundation_platform"
    modules: list[PortraitModuleItem]
    assets: list[PortraitAssetItem]
    capabilities: list[PortraitCapabilityItem]

    @model_validator(mode="after")
    def validate_references(self) -> PortraitIntelligenceStatus:
        module_ids = [m.module_id for m in self.modules]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("portrait module identifiers must be unique")
        asset_ids = [a.asset_id for a in self.assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("portrait asset identifiers must be unique")
        known = set(module_ids)
        for asset in self.assets:
            for dep in asset.depends_on_modules:
                if dep not in known:
                    raise ValueError(f"portrait asset references unknown module: {dep}")
        capability_ids = [c.capability_id for c in self.capabilities]
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("portrait capability identifiers must be unique")
        return self
