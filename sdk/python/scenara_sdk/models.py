from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

Domain = Literal["portrait", "ocr"]
SampleStrategy = Literal["interval", "keyframe", "scene_change", "uniform"]
TimestampSource = Literal["decoder_pts", "position_msec", "monotonic_clock"]
RunStatus = Literal["queued", "running", "pausing", "paused", "completed", "failed", "cancelling", "cancelled"]
FeedbackStatus = Literal["pending", "approved", "rejected"]
ModelReleaseStatus = Literal["candidate", "validated", "approved", "active", "retired"]
ProductLayer = Literal["product_module", "control_plane", "developer_surface", "foundation"]
ProductMaturity = Literal["available", "seed", "planned", "gated"]
RepositoryKind = Literal["platform_integration", "specialized_product"]
RepositoryLifecycle = Literal["current", "external_existing", "planned"]
RepositoryBoundaryRule = Literal[
    "versioned_contracts_only",
    "no_shared_database",
    "no_cross_repository_source_imports",
    "immutable_artifact_references",
]
RepositoryContractTransport = Literal["versioned_api", "event", "immutable_manifest"]
AccessCapabilityStatus = Literal["available", "seed", "planned", "gated"]
PortraitModuleMaturity = Literal["available", "partial", "seed", "planned", "external"]
PortraitCapabilityReadiness = Literal["ready", "fallback", "placeholder", "not_configured"]


class PipelineRef(TypedDict):
    pipeline_id: str
    version: str


class MediaTechnicalMetadata(TypedDict):
    format: NotRequired[str | None]
    container: NotRequired[str | None]
    codec: NotRequired[str | None]
    width: NotRequired[int | None]
    height: NotRequired[int | None]
    fps: NotRequired[float | None]
    frame_count: NotRequired[int | None]
    duration_ms: NotRequired[int | None]
    page_count: NotRequired[int | None]
    sampled_units: NotRequired[int | None]
    frames_read: NotRequired[int | None]
    sample_interval_ms: NotRequired[int | None]
    sample_strategy: NotRequired[SampleStrategy | None]
    sample_start_ms: NotRequired[int | None]
    sample_end_ms: NotRequired[int | None]
    stream_segment_duration_ms: NotRequired[int | None]
    stream_segment_index: NotRequired[int | None]
    keyframe_count: NotRequired[int | None]
    scene_change_count: NotRequired[int | None]
    frame_max_edge: NotRequired[int | None]
    decode_seek_used: NotRequired[bool | None]
    reconnect_count: NotRequired[int | None]
    elapsed_ms: NotRequired[int | None]
    timestamp_source: NotRequired[TimestampSource | None]


class MediaAsset(TypedDict):
    asset_id: str
    kind: Literal["image", "video", "document"]
    filename: NotRequired[str | None]
    content_type: str
    size_bytes: int
    sha256: str
    preview_object_key: NotRequired[str | None]
    preview_content_type: NotRequired[str | None]
    preview_sha256: NotRequired[str | None]
    metadata: MediaTechnicalMetadata
    original_deleted_at: NotRequired[float | None]
    temporary: bool
    created_at: float


class MediaSource(TypedDict):
    source_id: str
    kind: Literal["stream"]
    name: str
    masked_url: str
    metadata: dict[str, Any]
    created_at: float


class MediaSourceProbe(TypedDict):
    source_id: str
    reachable: bool
    latency_ms: int
    metadata: MediaTechnicalMetadata
    checked_at: float


DatasetStatus = Literal["draft", "active", "archived"]
DatasetVersionStatus = Literal["draft", "validated", "published", "retired"]


class DatasetRecord(TypedDict):
    dataset_id: str
    tenant_id: str
    project_id: str
    name: str
    description: str
    status: DatasetStatus
    metadata: dict[str, Any]
    created_at: float
    updated_at: float


class DatasetVersion(TypedDict):
    version_id: str
    dataset_id: str
    tenant_id: str
    project_id: str
    version: str
    status: DatasetVersionStatus
    manifest_sha256: str
    asset_ids: list[str]
    item_count: int
    quality_score: float | None
    lineage: dict[str, Any]
    annotation_summary: dict[str, Any]
    created_by: str
    created_at: float
    updated_at: float


class AuditEvent(TypedDict):
    event_id: str
    tenant_id: str
    project_id: str
    principal_id: str
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    request_id: str | None
    evidence: dict[str, Any]
    created_at: float


class SavedSearch(TypedDict):
    saved_search_id: str
    tenant_id: str
    project_id: str
    name: str
    description: str
    mode: Literal["text", "portrait"]
    definition: dict[str, Any]
    created_by: str
    created_at: float
    updated_at: float
    last_run_at: float | None


class ModelPackage(TypedDict):
    schema_version: Literal["1.0"]
    model_id: str
    version: str
    capability: str
    adapter: str
    runtime_model_id: str
    sha256: str
    source_uri: str
    license_id: str
    model_card: str
    evaluation_evidence: list[str]
    vram_mb: int
    regression_samples: list[str]
    production_ready: bool


class ProductCatalogItem(TypedDict):
    product_id: str
    name: str
    layer: ProductLayer
    maturity: ProductMaturity
    summary: str
    current_scope: list[str]
    not_in_scope_yet: list[str]
    console_route: str | None
    api_paths: list[str]
    depends_on: list[str]
    next_gate: str


class RepositoryTopologyItem(TypedDict):
    repository_id: str
    name: str
    kind: RepositoryKind
    lifecycle: RepositoryLifecycle
    current_repository: bool
    primary_product_ids: list[str]
    integration_product_ids: list[str]
    responsibilities: list[str]
    excluded_responsibilities: list[str]
    next_gate: str


class RepositoryIntegrationContract(TypedDict):
    contract_id: str
    producer_repository_id: str
    consumer_repository_id: str
    transport: RepositoryContractTransport
    payload_type: str
    release_version: str
    schema_path: str
    compatibility: Literal["backward"]
    invariants: list[str]


class RepositoryContractArtifact(TypedDict):
    contract_id: str
    payload_type: str
    release_version: str
    payload_schema_version: str
    producer_repository_id: str
    consumer_repository_id: str
    transport: RepositoryContractTransport
    compatibility: Literal["backward"]
    schema_path: str
    schema_sha256: str
    example_path: str
    example_sha256: str


class RepositoryContractCatalog(TypedDict):
    schema_version: Literal["1.0"]
    release_version: str
    package_name: str
    contracts: list[RepositoryContractArtifact]


class RepositoryTopology(TypedDict):
    schema_version: Literal["1.0"]
    current_repository_id: str
    repositories: list[RepositoryTopologyItem]
    integration_contracts: list[RepositoryIntegrationContract]
    boundary_rules: list[RepositoryBoundaryRule]


class AccessCapabilityItem(TypedDict):
    capability_id: str
    name: str
    status: AccessCapabilityStatus
    summary: str
    current_scope: list[str]
    not_in_scope_yet: list[str]
    next_gate: str


class AccessFoundationStatus(TypedDict):
    schema_version: Literal["1.0"]
    auth_mode: Literal["development_open", "single_bearer_token"]
    principal_source: Literal["anonymous", "api_token", "service_account_api_key", "header"]
    tenant_id: str
    project_id: str
    principal_id: str
    policy_provider: str
    capabilities: list[AccessCapabilityItem]


class PortraitCapabilityItem(TypedDict):
    capability_id: str
    readiness: PortraitCapabilityReadiness
    production_ready: bool
    current_model: NotRequired[str | None]
    target_model: NotRequired[str | None]
    embedding_dimension: NotRequired[int | None]
    target_embedding_dimension: NotRequired[int | None]


class PortraitModuleItem(TypedDict):
    module_id: str
    name: str
    maturity: PortraitModuleMaturity
    summary: str
    owner_repository_id: str
    current_scope: list[str]
    not_in_scope_yet: list[str]
    next_gate: str


class PortraitAssetItem(TypedDict):
    asset_id: str
    name: str
    maturity: PortraitModuleMaturity
    summary: str
    depends_on_modules: list[str]
    next_gate: str


class PortraitIntelligenceStatus(TypedDict):
    schema_version: Literal["1.0"]
    positioning: Literal["portrait_intelligence_foundation_platform"]
    modules: list[PortraitModuleItem]
    assets: list[PortraitAssetItem]
    capabilities: list[PortraitCapabilityItem]


class Organization(TypedDict):
    tenant_id: str
    display_name: str
    created_at: float
    updated_at: float


class Project(TypedDict):
    tenant_id: str
    project_id: str
    display_name: str
    created_at: float
    updated_at: float


class UserAccount(TypedDict):
    tenant_id: str
    user_id: str
    display_name: str
    email: str | None
    disabled: bool
    created_at: float
    updated_at: float


class Role(TypedDict):
    tenant_id: str
    role_id: str
    display_name: str
    scopes: list[str]
    product_ids: list[str]
    created_at: float
    updated_at: float


class Membership(TypedDict):
    tenant_id: str
    project_id: str
    principal_id: str
    principal_type: Literal["user", "service_account"]
    role_ids: list[str]
    created_at: float
    updated_at: float


class ServiceAccount(TypedDict):
    tenant_id: str
    project_id: str
    service_account_id: str
    display_name: str
    scopes: list[str]
    product_ids: list[str]
    disabled: bool
    created_at: float
    updated_at: float


class ApiKeyRecord(TypedDict):
    tenant_id: str
    project_id: str
    key_id: str
    service_account_id: str
    name: str
    token_prefix: str
    scopes: list[str]
    product_ids: list[str]
    expires_at: float | None
    revoked_at: float | None
    last_used_at: float | None
    created_at: float


class CreateApiKeyResponse(TypedDict):
    record: ApiKeyRecord
    api_key: str


class ProductEntitlement(TypedDict):
    tenant_id: str
    project_id: str
    product_id: str
    status: Literal["active", "suspended"]
    source: Literal["manual", "enterprise_license", "system"]
    created_at: float
    updated_at: float


class IamInventory(TypedDict):
    organizations: int
    projects: int
    users: int
    roles: int
    memberships: int
    service_accounts: int
    api_keys: int
    product_entitlements: int


class IamSummary(TypedDict):
    schema_version: Literal["1.0"]
    tenant_id: str
    project_id: str
    inventory: IamInventory
    default_admin_scopes: list[str]


class WebhookSubscription(TypedDict):
    endpoint_id: str
    name: str
    url: str
    event_types: list[str]
    enabled: bool
    created_at: float


class WebhookDelivery(TypedDict):
    delivery_id: str
    endpoint_id: str
    event_id: str
    event_type: str
    status: Literal["pending", "delivering", "delivered", "dead_letter"]
    attempts: int
    status_code: NotRequired[int | None]
    last_error: NotRequired[str | None]
    created_at: float
    updated_at: float


class FeedbackRecord(TypedDict):
    schema_version: Literal["1.0"]
    feedback_id: str
    kind: str
    run_id: str
    result_ref: str
    media_ref: str
    pipeline_id: str
    pipeline_version: str
    model_id: str
    model_version: str
    correction: dict[str, Any]
    authorized_for_training: bool
    deidentified: bool
    status: FeedbackStatus
    submitted_by: str
    reviewed_by: str | None
    review_notes: str
    created_at: float
    updated_at: float


class HardSampleManifest(TypedDict):
    schema_version: Literal["1.0"]
    manifest_id: str
    dataset_id: str
    version: str
    label_schema: str
    split: Literal["train", "validation", "test"]
    items: list[dict[str, Any]]
    sha256: str
    created_by: str
    created_at: float


class ModelRelease(TypedDict):
    schema_version: Literal["1.0"]
    model_id: str
    version: str
    capability: str
    runtime_model_id: str
    package_sha256: str
    evidence_refs: list[str]
    status: ModelReleaseStatus
    created_by: str
    created_at: float
    updated_at: float
    activated_at: float | None
    retired_at: float | None


class ModelDeploymentEvent(TypedDict):
    schema_version: Literal["1.0"]
    event_id: str
    tenant_id: str
    project_id: str
    model_id: str
    version: str
    capability: str
    runtime_model_id: str
    package_sha256: str
    action: str
    from_status: ModelReleaseStatus | None
    to_status: ModelReleaseStatus
    reason: str
    operator_id: str
    audit_id: str
    created_at: float


class Run(TypedDict):
    run_id: str
    domain: Domain
    pipeline: PipelineRef
    asset_id: NotRequired[str | None]
    source_id: NotRequired[str | None]
    stream_session_id: NotRequired[str | None]
    stream_segment_index: NotRequired[int | None]
    previous_run_id: NotRequired[str | None]
    next_run_id: NotRequired[str | None]
    parameters: dict[str, Any]
    priority: int
    status: RunStatus
    revision: int
    progress: float
    error_code: NotRequired[str | None]
    termination_reason: NotRequired[str | None]
    created_at: float
    updated_at: float
    started_at: NotRequired[float | None]
    completed_at: NotRequired[float | None]


class ResultEnvelope(TypedDict):
    schema_version: str
    run_id: str
    domain: Domain
    pipeline: PipelineRef
    asset_id: str | None
    source_id: str | None
    units: list[dict[str, Any]]
    domain_payload: dict[str, Any]
    relations: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    models: list[dict[str, Any]]
    timings: dict[str, float]
    media_metadata: MediaTechnicalMetadata
    warnings: list[str]
    provenance: dict[str, Any]
    created_at: float


class ResultPage(TypedDict):
    result: ResultEnvelope
    unit_offset: int
    unit_limit: int
    unit_total: int


class ParseImageResponse(TypedDict):
    asset: MediaAsset
    run: Run
    result: ResultEnvelope | None


class ParseVideoResponse(TypedDict):
    asset: MediaAsset
    run: Run
    result: ResultEnvelope | None


class ParseDocumentResponse(TypedDict):
    asset: MediaAsset
    run: Run
    result: ResultEnvelope | None
