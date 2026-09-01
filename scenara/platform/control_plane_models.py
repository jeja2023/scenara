"""Control-plane records and request contracts.

Separated from the service implementation so API, SDK, and storage consumers share
small, dependency-light schemas without importing the full service.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from scenara.platform.models import StrictModel

DEFAULT_BILLING_PERIOD_SECONDS = 2_592_000


class IdentityProviderKind(StrEnum):
    OIDC = "oidc"
    SAML = "saml"
    SCIM = "scim"


class LifecycleStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DELETED = "deleted"
    PENDING_RESTORE = "pending_restore"


class FlowNodeKind(StrEnum):
    RUN = "run"
    CONDITION = "condition"
    APPROVAL = "approval"
    WEBHOOK = "webhook"


class AgentActionStatus(StrEnum):
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


class EdgeDeviceStatus(StrEnum):
    PENDING = "pending"
    ONLINE = "online"
    OFFLINE = "offline"
    REVOKED = "revoked"


class IdentityProvider(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    kind: IdentityProviderKind
    display_name: str = Field(min_length=1, max_length=160)
    issuer_url: str = Field(min_length=1, max_length=2048)
    client_id: str = Field(min_length=1, max_length=256)
    scopes: frozenset[str] = Field(
        default_factory=lambda: frozenset({"openid", "profile", "email"})
    )
    enabled: bool = True
    last_health: str = "unknown"
    created_at: float
    updated_at: float


class CreateIdentityProviderRequest(StrictModel):
    kind: IdentityProviderKind
    display_name: str = Field(min_length=1, max_length=160)
    issuer_url: str = Field(min_length=1, max_length=2048)
    client_id: str = Field(min_length=1, max_length=256)
    scopes: frozenset[str] = Field(
        default_factory=lambda: frozenset({"openid", "profile", "email"})
    )


class InteractiveSession(StrictModel):
    session_id: str
    tenant_id: str
    project_id: str
    user_id: str
    token_prefix: str
    token_sha256: str
    scopes: frozenset[str] = Field(default_factory=frozenset)
    product_ids: frozenset[str] = Field(default_factory=frozenset)
    created_at: float
    expires_at: float
    revoked_at: float | None = None
    last_used_at: float | None = None


class CreateSessionRequest(StrictModel):
    user_id: str = Field(min_length=2, max_length=128)
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class SessionResponse(StrictModel):
    session: InteractiveSession
    token: str


class ResourceLifecycleRecord(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    resource_type: str
    resource_id: str
    status: LifecycleStatus = LifecycleStatus.ACTIVE
    reason: str = ""
    updated_by: str
    created_at: float
    updated_at: float
    deleted_at: float | None = None


class CreateProjectLifecycleRequest(StrictModel):
    project_id: str = Field(min_length=2, max_length=128)
    action: str = Field(pattern=r"^(disable|restore|delete)$")
    reason: str = Field(default="", max_length=2_000)


class ProjectLifecycleRequest(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    action: str
    status: str = "pending"
    reason: str = ""
    requested_by: str
    decided_by: str | None = None
    decision_comment: str = ""
    created_at: float
    updated_at: float
    decided_at: float | None = None


class DecideProjectLifecycleRequest(StrictModel):
    approved: bool
    comment: str = Field(default="", max_length=2_000)


class AuditRetentionPolicy(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    retention_days: int = Field(ge=1, le=3_650)
    export_approval_required: bool = True
    enabled: bool = True
    updated_by: str
    created_at: float
    updated_at: float


class SetAuditRetentionPolicyRequest(StrictModel):
    retention_days: int = Field(ge=1, le=3_650)
    export_approval_required: bool = True
    enabled: bool = True


class PurgeAuditRequest(StrictModel):
    dry_run: bool = False
    reason: str = Field(min_length=1, max_length=2_000)


class PurgeAuditResponse(StrictModel):
    deleted_count: int = Field(ge=0)
    cutoff_at: float
    dry_run: bool
    executed_at: float


class BillingAccount(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    plan_id: str
    currency: str = Field(default="USD", min_length=3, max_length=3)
    status: str = "active"
    seat_limit: int = Field(default=5, ge=1, le=1_000_000)
    period_started_at: float
    period_ends_at: float
    created_at: float
    updated_at: float


class CreateBillingAccountRequest(StrictModel):
    plan_id: str = Field(min_length=2, max_length=128)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    seat_limit: int = Field(default=5, ge=1, le=1_000_000)
    period_seconds: int = Field(
        default=DEFAULT_BILLING_PERIOD_SECONDS, ge=86_400, le=31_536_000
    )


class MeterEvent(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    account_id: str
    metric: str = Field(min_length=1, max_length=128)
    amount: int = Field(gt=0, le=1_000_000_000)
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_.:-]{8,160}$")
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float


class RecordMeterEventRequest(StrictModel):
    account_id: str
    metric: str = Field(min_length=1, max_length=128)
    amount: int = Field(gt=0, le=1_000_000_000)
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_.:-]{8,160}$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class BillingUsage(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    account_id: str
    metric: str
    amount: int = Field(ge=0)
    period_started_at: float
    period_ends_at: float
    updated_at: float


class SeatAssignment(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    account_id: str
    user_id: str
    status: str = "active"
    assigned_by: str
    created_at: float
    revoked_at: float | None = None


class AssignSeatRequest(StrictModel):
    account_id: str
    user_id: str = Field(min_length=2, max_length=128)


class AnnotationProvider(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    name: str = Field(min_length=1, max_length=160)
    kind: str = Field(min_length=1, max_length=64)
    endpoint: str = Field(min_length=1, max_length=2_048)
    enabled: bool = True
    last_health: str = "unknown"
    created_at: float
    updated_at: float


class CreateAnnotationProviderRequest(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    kind: str = Field(min_length=1, max_length=64)
    endpoint: str = Field(min_length=1, max_length=2_048)


class IndexBackend(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    name: str = Field(min_length=1, max_length=160)
    kind: str = Field(min_length=1, max_length=64)
    endpoint: str = Field(min_length=1, max_length=2_048)
    capabilities: frozenset[str] = Field(default_factory=frozenset)
    enabled: bool = True
    health: str = "unknown"
    created_at: float
    updated_at: float


class CreateIndexBackendRequest(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    kind: str = Field(min_length=1, max_length=64)
    endpoint: str = Field(min_length=1, max_length=2_048)
    capabilities: frozenset[str] = Field(default_factory=frozenset)


class SearchReranker(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    name: str = Field(min_length=1, max_length=160)
    kind: str = Field(min_length=1, max_length=64)
    endpoint: str = Field(min_length=1, max_length=2_048)
    enabled: bool = True
    health: str = "unknown"
    created_at: float
    updated_at: float


class CreateSearchRerankerRequest(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    kind: str = Field(min_length=1, max_length=64)
    endpoint: str = Field(min_length=1, max_length=2_048)


class QuotaPlan(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    name: str = Field(min_length=1, max_length=128)
    limits: dict[str, int] = Field(default_factory=dict)
    window_seconds: int = Field(default=86400, ge=60, le=31_536_000)
    enabled: bool = True
    created_at: float
    updated_at: float


class CreateQuotaPlanRequest(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    limits: dict[str, int] = Field(default_factory=dict)
    window_seconds: int = Field(default=86400, ge=60, le=31_536_000)


class QuotaUsage(StrictModel):
    metric: str
    used: int = Field(default=0, ge=0)
    limit: int | None = Field(default=None, ge=0)
    window_started_at: float
    window_ends_at: float


class QuotaCheckRequest(StrictModel):
    metric: str = Field(min_length=1, max_length=128)
    amount: int = Field(default=1, ge=1, le=1_000_000)


class QuotaCheckResponse(StrictModel):
    allowed: bool
    usage: QuotaUsage


class AnnotationTaskStatus(StrEnum):
    QUEUED = "queued"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class AnnotationTask(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    asset_ids: list[str] = Field(min_length=1, max_length=10_000)
    schema_name: str = Field(min_length=1, max_length=160)
    assignee: str | None = None
    status: AnnotationTaskStatus = AnnotationTaskStatus.QUEUED
    labels: dict[str, Any] = Field(default_factory=dict)
    consistency_score: float | None = Field(default=None, ge=0, le=1)
    review_comment: str = ""
    created_by: str
    created_at: float
    updated_at: float


class CreateAnnotationTaskRequest(StrictModel):
    asset_ids: list[str] = Field(min_length=1, max_length=10_000)
    schema_name: str = Field(min_length=1, max_length=160)
    assignee: str | None = None
    labels: dict[str, Any] = Field(default_factory=dict)


class ReviewAnnotationTaskRequest(StrictModel):
    approved: bool
    consistency_score: float = Field(ge=0, le=1)
    comment: str = Field(default="", max_length=2_000)


class SearchRankingProfile(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    name: str = Field(min_length=1, max_length=160)
    exact_weight: float = Field(default=0.5, ge=0, le=1)
    vector_weight: float = Field(default=0.5, ge=0, le=1)
    reranker: str = "none"
    active: bool = False
    created_at: float
    updated_at: float


class CreateSearchRankingProfileRequest(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    exact_weight: float = Field(default=0.5, ge=0, le=1)
    vector_weight: float = Field(default=0.5, ge=0, le=1)
    reranker: str = Field(default="none", max_length=64)


class SearchRelevanceFeedback(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    search_id: str
    hit_record_id: str
    relevant: bool
    created_by: str
    created_at: float


class CreateSearchRelevanceFeedbackRequest(StrictModel):
    search_id: str
    hit_record_id: str
    relevant: bool


class SearchEvaluation(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    profile_id: str | None = None
    query: str
    expected_record_ids: list[str] = Field(default_factory=list)
    result_record_ids: list[str] = Field(default_factory=list)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    created_by: str
    created_at: float


class CreateSearchEvaluationRequest(StrictModel):
    profile_id: str | None = None
    query: str = Field(min_length=1, max_length=10_000)
    expected_record_ids: list[str] = Field(default_factory=list)
    result_record_ids: list[str] = Field(default_factory=list)


class IndexRebuildJob(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    index_id: str
    status: str = "queued"
    records_seen: int = 0
    records_rebuilt: int = 0
    created_by: str
    created_at: float
    completed_at: float | None = None


class CreateIndexRebuildRequest(StrictModel):
    index_id: str = Field(min_length=2, max_length=160)


class EdgeHeartbeatRequest(StrictModel):
    status: EdgeDeviceStatus = EdgeDeviceStatus.ONLINE
    metadata: dict[str, Any] = Field(default_factory=dict)


class AcknowledgeEdgeSyncRequest(StrictModel):
    acknowledged: bool = True


class AcknowledgeEdgeDeploymentRequest(StrictModel):
    applied: bool = True
    error: str | None = Field(default=None, max_length=2_000)


class WorkerLease(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    worker_id: str
    lane: str = Field(pattern=r"^(batch|realtime)$")
    status: str = "active"
    capacity: int = Field(default=1, ge=1, le=1024)
    last_heartbeat_at: float
    lease_expires_at: float
    created_at: float


class RegisterWorkerRequest(StrictModel):
    worker_id: str = Field(min_length=2, max_length=128)
    lane: str = Field(pattern=r"^(batch|realtime)$")
    capacity: int = Field(default=1, ge=1, le=1024)
    lease_seconds: int = Field(default=30, ge=5, le=300)


class WorkerHeartbeatRequest(StrictModel):
    lease_seconds: int = Field(default=30, ge=5, le=300)


class ModelMetricPoint(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    model_id: str
    model_version: str
    capability: str
    latency_ms: float = Field(gt=0)
    error_rate: float = Field(default=0, ge=0, le=1)
    quality_score: float | None = Field(default=None, ge=0, le=1)
    throughput: float | None = Field(default=None, ge=0)
    created_at: float


class ModelHealthSnapshot(StrictModel):
    model_id: str
    model_version: str
    capability: str
    sample_count: int = Field(ge=0)
    p95_latency_ms: float | None = None
    error_rate: float = Field(ge=0, le=1)
    quality_score: float | None = Field(default=None, ge=0, le=1)
    degraded: bool = False
    rollback_recommended: bool = False
    evaluated_at: float


class AutoRollbackModelRequest(StrictModel):
    model_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$")
    capability: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=2_000)


class FlowNode(StrictModel):
    node_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    kind: FlowNodeKind
    config: dict[str, Any] = Field(default_factory=dict)
    next_nodes: list[str] = Field(default_factory=list, max_length=32)


class FlowDefinition(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=32)
    status: str = "draft"
    nodes: list[FlowNode] = Field(min_length=1, max_length=256)
    entry_node_id: str
    created_by: str
    created_at: float
    updated_at: float


class CreateFlowRequest(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=32)
    nodes: list[FlowNode] = Field(min_length=1, max_length=256)
    entry_node_id: str


class FlowExecution(StrictModel):
    record_id: str
    flow_id: str
    tenant_id: str
    project_id: str
    status: str = "running"
    current_node_id: str
    context: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_at: float
    updated_at: float
    completed_at: float | None = None


class FlowApproval(StrictModel):
    record_id: str
    execution_id: str
    node_id: str
    tenant_id: str
    project_id: str
    status: str = "pending"
    comment: str = ""
    decided_by: str | None = None
    created_at: float
    updated_at: float


class ExecuteFlowRequest(StrictModel):
    context: dict[str, Any] = Field(default_factory=dict)


class DecideApprovalRequest(StrictModel):
    approved: bool
    comment: str = Field(default="", max_length=2_000)


class AgentTrace(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    action_id: str | None = None
    trace_type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_at: float


class CreateAgentTraceRequest(StrictModel):
    action_id: str | None = None
    trace_type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentEvaluation(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    suite_name: str = Field(min_length=1, max_length=160)
    sample_count: int = Field(ge=0)
    success_rate: float = Field(ge=0, le=1)
    policy_violation_count: int = Field(default=0, ge=0)
    created_by: str
    created_at: float


class CreateAgentEvaluationRequest(StrictModel):
    suite_name: str = Field(min_length=1, max_length=160)
    sample_count: int = Field(ge=0)
    success_rate: float = Field(ge=0, le=1)
    policy_violation_count: int = Field(default=0, ge=0)


class AgentMemoryEntry(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    namespace: str = Field(min_length=1, max_length=128)
    key: str = Field(min_length=1, max_length=256)
    value: dict[str, Any] = Field(default_factory=dict)
    expires_at: float | None = None
    updated_by: str
    updated_at: float


class PutAgentMemoryRequest(StrictModel):
    namespace: str = Field(min_length=1, max_length=128)
    key: str = Field(min_length=1, max_length=256)
    value: dict[str, Any] = Field(default_factory=dict)
    ttl_seconds: int | None = Field(default=None, ge=60, le=31_536_000)


class PortraitCluster(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    feature_space_id: str
    label: str = ""
    member_record_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    confirmed: bool = False
    created_at: float
    updated_at: float


class CreatePortraitClusterRequest(StrictModel):
    feature_space_id: str = Field(min_length=2, max_length=128)
    member_record_ids: list[str] = Field(min_length=1, max_length=10_000)
    label: str = Field(default="", max_length=256)
    confidence: float = Field(default=0, ge=0, le=1)


class PortraitAssociation(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    feature_space_id: str
    left_record_id: str
    right_record_id: str
    score: float = Field(ge=-1, le=1)
    source: str = "manual"
    created_at: float


class CreatePortraitAssociationRequest(StrictModel):
    feature_space_id: str = Field(min_length=2, max_length=128)
    left_record_id: str
    right_record_id: str
    score: float = Field(ge=-1, le=1)
    source: str = Field(default="manual", max_length=64)


class PortraitEvent(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    event_type: str
    subject_record_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    started_at: float
    ended_at: float | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreatePortraitEventRequest(StrictModel):
    event_type: str = Field(min_length=1, max_length=128)
    subject_record_ids: list[str] = Field(default_factory=list, max_length=10_000)
    source_ids: list[str] = Field(default_factory=list, max_length=1_000)
    started_at: float
    ended_at: float | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EdgeDevice(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    name: str = Field(min_length=1, max_length=160)
    status: EdgeDeviceStatus = EdgeDeviceStatus.PENDING
    capabilities: frozenset[str] = Field(default_factory=frozenset)
    certificate_fingerprint: str
    last_seen_at: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float
    updated_at: float


class RegisterEdgeDeviceRequest(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    capabilities: frozenset[str] = Field(default_factory=frozenset)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EdgeDeployment(StrictModel):
    record_id: str
    device_id: str
    tenant_id: str
    project_id: str
    model_id: str
    model_version: str
    pipeline_id: str
    pipeline_version: str
    status: str = "pending"
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: float
    updated_at: float
    applied_at: float | None = None


class CreateEdgeDeploymentRequest(StrictModel):
    device_id: str
    model_id: str
    model_version: str
    pipeline_id: str
    pipeline_version: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EdgeSyncItem(StrictModel):
    record_id: str
    device_id: str
    tenant_id: str
    project_id: str
    direction: str = "upload"
    object_ref: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: str = "pending"
    created_at: float
    acknowledged_at: float | None = None


class AgentTool(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    description: str = Field(min_length=1, max_length=500)
    scopes: frozenset[str] = Field(default_factory=frozenset)
    requires_approval: bool = True
    enabled: bool = True
    created_at: float


class RegisterAgentToolRequest(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    description: str = Field(min_length=1, max_length=500)
    scopes: frozenset[str] = Field(default_factory=frozenset)
    requires_approval: bool = True


class AgentAction(StrictModel):
    record_id: str
    tool_id: str
    tenant_id: str
    project_id: str
    input: dict[str, Any] = Field(default_factory=dict)
    status: AgentActionStatus = AgentActionStatus.PROPOSED
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_by: str
    created_at: float
    updated_at: float


class ProposeAgentActionRequest(StrictModel):
    tool_id: str
    input: dict[str, Any] = Field(default_factory=dict)


class ApproveAgentActionRequest(StrictModel):
    approved: bool
    comment: str = Field(default="", max_length=2_000)


class DeploymentTopology(StrictModel):
    record_id: str
    tenant_id: str
    project_id: str
    mode: str = "single_node"
    workers: int = Field(default=1, ge=1, le=10_000)
    lanes: dict[str, int] = Field(default_factory=lambda: {"batch": 1, "realtime": 1})
    readiness: str = "configured"
    constraints: list[str] = Field(default_factory=list)
    updated_at: float


__all__ = [
    "DEFAULT_BILLING_PERIOD_SECONDS",
    "IdentityProviderKind",
    "LifecycleStatus",
    "FlowNodeKind",
    "AgentActionStatus",
    "EdgeDeviceStatus",
    "IdentityProvider",
    "CreateIdentityProviderRequest",
    "InteractiveSession",
    "CreateSessionRequest",
    "SessionResponse",
    "ResourceLifecycleRecord",
    "CreateProjectLifecycleRequest",
    "ProjectLifecycleRequest",
    "DecideProjectLifecycleRequest",
    "AuditRetentionPolicy",
    "SetAuditRetentionPolicyRequest",
    "PurgeAuditRequest",
    "PurgeAuditResponse",
    "BillingAccount",
    "CreateBillingAccountRequest",
    "MeterEvent",
    "RecordMeterEventRequest",
    "BillingUsage",
    "SeatAssignment",
    "AssignSeatRequest",
    "AnnotationProvider",
    "CreateAnnotationProviderRequest",
    "IndexBackend",
    "CreateIndexBackendRequest",
    "SearchReranker",
    "CreateSearchRerankerRequest",
    "QuotaPlan",
    "CreateQuotaPlanRequest",
    "QuotaUsage",
    "QuotaCheckRequest",
    "QuotaCheckResponse",
    "AnnotationTaskStatus",
    "AnnotationTask",
    "CreateAnnotationTaskRequest",
    "ReviewAnnotationTaskRequest",
    "SearchRankingProfile",
    "CreateSearchRankingProfileRequest",
    "SearchRelevanceFeedback",
    "CreateSearchRelevanceFeedbackRequest",
    "SearchEvaluation",
    "CreateSearchEvaluationRequest",
    "IndexRebuildJob",
    "CreateIndexRebuildRequest",
    "EdgeHeartbeatRequest",
    "AcknowledgeEdgeSyncRequest",
    "AcknowledgeEdgeDeploymentRequest",
    "WorkerLease",
    "RegisterWorkerRequest",
    "WorkerHeartbeatRequest",
    "ModelMetricPoint",
    "ModelHealthSnapshot",
    "AutoRollbackModelRequest",
    "FlowNode",
    "FlowDefinition",
    "CreateFlowRequest",
    "FlowExecution",
    "FlowApproval",
    "ExecuteFlowRequest",
    "DecideApprovalRequest",
    "AgentTrace",
    "CreateAgentTraceRequest",
    "AgentEvaluation",
    "CreateAgentEvaluationRequest",
    "AgentMemoryEntry",
    "PutAgentMemoryRequest",
    "PortraitCluster",
    "CreatePortraitClusterRequest",
    "PortraitAssociation",
    "CreatePortraitAssociationRequest",
    "PortraitEvent",
    "CreatePortraitEventRequest",
    "EdgeDevice",
    "RegisterEdgeDeviceRequest",
    "EdgeDeployment",
    "CreateEdgeDeploymentRequest",
    "EdgeSyncItem",
    "AgentTool",
    "RegisterAgentToolRequest",
    "AgentAction",
    "ProposeAgentActionRequest",
    "ApproveAgentActionRequest",
    "DeploymentTopology",
]
