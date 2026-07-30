from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

Domain = Literal["portrait", "ocr"]
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


class PipelineRef(TypedDict):
    pipeline_id: str
    version: str


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
    original_deleted_at: NotRequired[float | None]
    temporary: bool
    created_at: float


class ModelPackage(TypedDict):
    model_id: str
    version: str
    capability: str
    adapter: str
    sha256: str
    source_uri: str
    license_id: str
    model_card: str
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
    invariants: list[str]


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
    model_id: str
    version: str
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
    status: RunStatus
    revision: int
    progress: float
    error_code: NotRequired[str | None]
    termination_reason: NotRequired[str | None]
    created_at: float
    updated_at: float


class ResultEnvelope(TypedDict):
    schema_version: str
    run_id: str
    domain: Domain
    pipeline: PipelineRef
    units: list[dict[str, Any]]
    domain_payload: dict[str, Any]
    models: list[dict[str, Any]]
    timings: dict[str, float]
    warnings: list[str]
    created_at: float
