"""Shared control-plane services for the post-1.0 product modules.

The first implementation deliberately keeps the product modules in the
existing modular monolith.  All records are tenant/project scoped, changes
are audited, and persistence is supplied by a small document repository so
the same service works with memory and PostgreSQL deployments.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from enum import StrEnum
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import Field

from scenara.platform.audit import AuditLogger
from scenara.platform.control_plane_store import (
    AuditRetentionStore,
    ControlPlaneStore,
    SessionAccessResolver,
)
from scenara.platform.control_plane_store import (
    MemoryControlPlaneStore as MemoryControlPlaneStore,
)
from scenara.platform.index import IndexStore
from scenara.platform.models import PrincipalContext, StrictModel
from scenara.platform.policy import PolicyDenied, PolicyProvider, require_allowed

RecordT = TypeVar("RecordT", bound=StrictModel)


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
    scopes: frozenset[str] = Field(default_factory=lambda: frozenset({"openid", "profile", "email"}))
    enabled: bool = True
    last_health: str = "unknown"
    created_at: float
    updated_at: float


class CreateIdentityProviderRequest(StrictModel):
    kind: IdentityProviderKind
    display_name: str = Field(min_length=1, max_length=160)
    issuer_url: str = Field(min_length=1, max_length=2048)
    client_id: str = Field(min_length=1, max_length=256)
    scopes: frozenset[str] = Field(default_factory=lambda: frozenset({"openid", "profile", "email"}))


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
    period_seconds: int = Field(default=2_592_000, ge=86_400, le=31_536_000)


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


class ControlPlaneService:
    """Tenant-scoped product control plane with fail-closed approvals."""

    def __init__(
        self,
        store: ControlPlaneStore,
        policy: PolicyProvider,
        audit: AuditLogger,
        indexes: IndexStore | None = None,
        access: SessionAccessResolver | None = None,
        audit_store: AuditRetentionStore | None = None,
    ) -> None:
        self.store = store
        self.policy = policy
        self.audit = audit
        self.indexes = indexes
        self.access = access
        self.audit_store = audit_store

    async def _check(self, context: PrincipalContext, action: str, resource: str) -> None:
        await require_allowed(self.policy, context, action, resource)

    async def _record(
        self,
        context: PrincipalContext,
        action: str,
        resource: str,
        resource_id: str | None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        await self.audit.record(
            context, action=action, resource_type=resource, resource_id=resource_id, evidence=evidence or {}
        )

    async def _save(self, kind: str, record: RecordT) -> RecordT:
        payload = record.model_dump(mode="json")
        record_id = payload.get("record_id") or payload.get("session_id")
        tenant_id = payload.get("tenant_id")
        project_id = payload.get("project_id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError(f"control-plane record {kind} has no stable identifier")
        if not isinstance(tenant_id, str) or not isinstance(project_id, str):
            raise ValueError(f"control-plane record {kind} has no tenant/project scope")
        await self.store.put(
            kind,
            tenant_id,
            project_id,
            record_id,
            payload,
        )
        return record

    async def _get(
        self, kind: str, tenant_id: str, project_id: str, record_id: str, model: type[RecordT]
    ) -> RecordT | None:
        document = await self.store.get(kind, tenant_id, project_id, record_id)
        return model.model_validate(document) if document else None

    async def _list(self, kind: str, tenant_id: str, project_id: str, model: type[RecordT]) -> list[RecordT]:
        return [model.model_validate(item) for item in await self.store.list(kind, tenant_id, project_id)]

    async def create_identity_provider(
        self, context: PrincipalContext, body: CreateIdentityProviderRequest
    ) -> IdentityProvider:
        await self._check(context, "write", "iam")
        now = time.time()
        record = IdentityProvider(
            record_id=_id("idp"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_at=now,
            updated_at=now,
            **body.model_dump(),
        )
        await self._save("identity_provider", record)
        await self._record(
            context, "iam.identity_provider.create", "identity_provider", record.record_id, {"kind": record.kind.value}
        )
        return record

    async def list_identity_providers(self, context: PrincipalContext) -> list[IdentityProvider]:
        await self._check(context, "read", "iam")
        return await self._list("identity_provider", context.tenant_id, context.project_id, IdentityProvider)

    async def probe_identity_provider(self, context: PrincipalContext, provider_id: str) -> IdentityProvider:
        await self._check(context, "write", "iam")
        provider = await self._get(
            "identity_provider", context.tenant_id, context.project_id, provider_id, IdentityProvider
        )
        if provider is None:
            raise ValueError("identity provider not found")
        updated = provider.model_copy(update={"last_health": "configured", "updated_at": time.time()})
        await self._save("identity_provider", updated)
        await self._record(context, "iam.identity_provider.probe", "identity_provider", provider_id)
        return updated

    async def create_session(self, context: PrincipalContext, body: CreateSessionRequest) -> SessionResponse:
        await self._check(context, "write", "iam")
        return await self._issue_session(context, body.user_id, body.ttl_seconds)

    async def create_authenticated_session(self, context: PrincipalContext, *, ttl_seconds: int) -> SessionResponse:
        """Issue a session after the caller has already verified a user password."""
        return await self._issue_session(context, context.principal_id, ttl_seconds)

    async def _issue_session(self, context: PrincipalContext, user_id: str, ttl_seconds: int) -> SessionResponse:
        now = time.time()
        token = secrets.token_urlsafe(32)
        resolved = (
            await self.access.resolve_user_context(context.tenant_id, context.project_id, user_id)
            if self.access is not None
            else None
        )
        if self.access is not None and resolved is None:
            raise ValueError("session user is unknown, disabled, or has no project membership")
        if resolved is not None and resolved.principal_id != user_id:
            raise ValueError("session principal resolution failed")
        record = InteractiveSession(
            session_id=_id("ses"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            user_id=user_id,
            token_prefix=token[:8],
            token_sha256=_sha(token),
            scopes=resolved.scopes if resolved is not None else context.scopes,
            product_ids=resolved.product_ids if resolved is not None else context.product_ids,
            created_at=now,
            expires_at=now + ttl_seconds,
        )
        await self._save("session", record)
        await self._record(
            context,
            "iam.session.create",
            "session",
            record.session_id,
            {"user_id": user_id, "expires_at": record.expires_at},
        )
        return SessionResponse(session=record, token=token)

    async def authenticate_session(self, token: str) -> PrincipalContext | None:
        if not token:
            return None
        digest = _sha(token)
        document = await self.store.get_by_token_sha256(digest)
        if document is None or not hmac.compare_digest(str(document.get("token_sha256", "")), digest):
            return None
        now = time.time()
        if document.get("revoked_at") is not None or float(document.get("expires_at", 0)) <= now:
            return None
        scopes = frozenset(document.get("scopes", []))
        product_ids = frozenset(document.get("product_ids", []))
        if not scopes:
            return None
        last_used_at = document.get("last_used_at")
        if last_used_at is None or now - float(last_used_at) >= 60:
            document["last_used_at"] = now
            await self.store.put(
                "session",
                str(document["tenant_id"]),
                str(document["project_id"]),
                str(document["session_id"]),
                document,
            )
        return PrincipalContext(
            tenant_id=str(document["tenant_id"]),
            project_id=str(document["project_id"]),
            principal_id=str(document["user_id"]),
            scopes=scopes,
            product_ids=product_ids,
        )

    async def purge_expired_sessions(self, now: float | None = None) -> int:
        return await self.store.delete_expired_sessions(time.time() if now is None else now)

    async def lifecycle(
        self, context: PrincipalContext, resource_type: str, resource_id: str, action: str, reason: str = ""
    ) -> ResourceLifecycleRecord:
        await self._check(context, "write", "iam")
        if action not in {"disable", "restore", "delete"}:
            raise ValueError("unsupported lifecycle action")
        current = await self._get(
            "lifecycle",
            context.tenant_id,
            context.project_id,
            f"{resource_type}:{resource_id}",
            ResourceLifecycleRecord,
        )
        now = time.time()
        status = {
            "disable": LifecycleStatus.DISABLED,
            "restore": LifecycleStatus.ACTIVE,
            "delete": LifecycleStatus.DELETED,
        }[action]
        record = ResourceLifecycleRecord(
            record_id=f"{resource_type}:{resource_id}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            reason=reason,
            updated_by=context.principal_id,
            created_at=current.created_at if current else now,
            updated_at=now,
            deleted_at=now if status == LifecycleStatus.DELETED else None,
        )
        await self._save("lifecycle", record)
        await self._record(
            context, f"iam.lifecycle.{action}", resource_type, resource_id, {"reason": reason, "status": status.value}
        )
        return record

    async def request_project_lifecycle(
        self, context: PrincipalContext, body: CreateProjectLifecycleRequest
    ) -> ProjectLifecycleRequest:
        await self._check(context, "write", "iam")
        now = time.time()
        record = ProjectLifecycleRequest(
            record_id=_id("project-lifecycle"),
            tenant_id=context.tenant_id,
            project_id=body.project_id,
            action=body.action,
            reason=body.reason,
            requested_by=context.principal_id,
            created_at=now,
            updated_at=now,
        )
        await self._save("project_lifecycle_request", record)
        await self._record(
            context,
            "iam.project_lifecycle.request",
            "project",
            body.project_id,
            {"action": body.action, "reason": body.reason},
        )
        return record

    async def list_project_lifecycle_requests(self, context: PrincipalContext) -> list[ProjectLifecycleRequest]:
        await self._check(context, "read", "iam")
        return await self._list("project_lifecycle_request", context.tenant_id, "*", ProjectLifecycleRequest)

    async def decide_project_lifecycle(
        self, context: PrincipalContext, request_id: str, body: DecideProjectLifecycleRequest
    ) -> ProjectLifecycleRequest:
        await self._check(context, "write", "iam")
        request = await self._get(
            "project_lifecycle_request",
            context.tenant_id,
            context.project_id,
            request_id,
            ProjectLifecycleRequest,
        )
        if request is None:
            candidates = await self.store.list("project_lifecycle_request", context.tenant_id, "*")
            request = next(
                (
                    ProjectLifecycleRequest.model_validate(item)
                    for item in candidates
                    if item.get("record_id") == request_id
                ),
                None,
            )
        if request is None or request.status != "pending":
            raise ValueError("project lifecycle request is unavailable")
        now = time.time()
        updated = request.model_copy(
            update={
                "status": "approved" if body.approved else "rejected",
                "decided_by": context.principal_id,
                "decision_comment": body.comment,
                "decided_at": now,
                "updated_at": now,
            }
        )
        await self._save("project_lifecycle_request", updated)
        if body.approved:
            target_context = context.model_copy(update={"project_id": request.project_id})
            await self.lifecycle(target_context, "project", request.project_id, request.action, request.reason)
        await self._record(
            context,
            "iam.project_lifecycle.decide",
            "project",
            request.project_id,
            {"approved": body.approved, "request_id": request_id},
        )
        return updated

    async def set_audit_retention_policy(
        self, context: PrincipalContext, body: SetAuditRetentionPolicyRequest
    ) -> AuditRetentionPolicy:
        await self._check(context, "write", "audit_event")
        now = time.time()
        current = await self._get(
            "audit_retention", context.tenant_id, context.project_id, "default", AuditRetentionPolicy
        )
        policy = AuditRetentionPolicy(
            record_id="default",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            updated_by=context.principal_id,
            created_at=current.created_at if current else now,
            updated_at=now,
            **body.model_dump(),
        )
        await self._save("audit_retention", policy)
        await self._record(
            context,
            "audit.retention.update",
            "audit_retention",
            policy.record_id,
            {"retention_days": policy.retention_days},
        )
        return policy

    async def get_audit_retention_policy(self, context: PrincipalContext) -> AuditRetentionPolicy:
        await self._check(context, "read", "audit_event")
        policy = await self._get(
            "audit_retention", context.tenant_id, context.project_id, "default", AuditRetentionPolicy
        )
        if policy is not None:
            return policy
        now = time.time()
        return AuditRetentionPolicy(
            record_id="default",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            retention_days=365,
            updated_by="system",
            created_at=now,
            updated_at=now,
        )

    async def purge_audit_events(self, context: PrincipalContext, body: PurgeAuditRequest) -> PurgeAuditResponse:
        await self._check(context, "write", "audit_event")
        policy = await self.get_audit_retention_policy(context)
        cutoff = time.time() - policy.retention_days * 86_400
        deleted = 0
        if not body.dry_run:
            if self.audit_store is None:
                raise RuntimeError("audit retention store is not configured")
            deleted = await self.audit_store.delete_audit_events_before(context.tenant_id, context.project_id, cutoff)
        result = PurgeAuditResponse(
            deleted_count=deleted,
            cutoff_at=cutoff,
            dry_run=body.dry_run,
            executed_at=time.time(),
        )
        await self._record(
            context,
            "audit.retention.purge",
            "audit_event",
            None,
            {"deleted_count": deleted, "dry_run": body.dry_run, "reason": body.reason},
        )
        return result

    async def create_quota_plan(self, context: PrincipalContext, body: CreateQuotaPlanRequest) -> QuotaPlan:
        await self._check(context, "write", "enterprise")
        now = time.time()
        record = QuotaPlan(
            record_id=_id("quota"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_at=now,
            updated_at=now,
            **body.model_dump(),
        )
        await self._save("quota_plan", record)
        await self._record(context, "quota.plan.create", "quota_plan", record.record_id)
        return record

    async def list_quota_plans(self, context: PrincipalContext) -> list[QuotaPlan]:
        await self._check(context, "read", "enterprise")
        return await self._list("quota_plan", context.tenant_id, context.project_id, QuotaPlan)

    async def check_quota(self, context: PrincipalContext, body: QuotaCheckRequest) -> QuotaCheckResponse:
        await self._check(context, "read", "operations")
        plans = await self._list("quota_plan", context.tenant_id, context.project_id, QuotaPlan)
        plan = next((item for item in plans if item.enabled), None)
        now = time.time()
        window = plan.window_seconds if plan else 86400
        existing = await self.store.get("quota_usage", context.tenant_id, context.project_id, body.metric)
        started = float(existing.get("window_started_at", now)) if existing else now
        used = int(existing.get("used", 0)) if existing else 0
        if now >= started + window:
            started, used = now, 0
        limit = plan.limits.get(body.metric) if plan else None
        usage = QuotaUsage(
            metric=body.metric,
            used=used + body.amount,
            limit=limit,
            window_started_at=started,
            window_ends_at=started + window,
        )
        allowed = limit is None or usage.used <= limit
        if allowed:
            await self.store.put(
                "quota_usage",
                context.tenant_id,
                context.project_id,
                body.metric,
                usage.model_dump(mode="json") | {"record_id": body.metric, "updated_at": now},
            )
        return QuotaCheckResponse(allowed=allowed, usage=usage)

    async def create_billing_account(
        self, context: PrincipalContext, body: CreateBillingAccountRequest
    ) -> BillingAccount:
        await self._check(context, "write", "enterprise")
        now = time.time()
        account = BillingAccount(
            record_id=_id("billing"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            period_started_at=now,
            period_ends_at=now + body.period_seconds,
            created_at=now,
            updated_at=now,
            **body.model_dump(exclude={"period_seconds"}),
        )
        await self._save("billing_account", account)
        await self._record(context, "billing.account.create", "billing_account", account.record_id)
        return account

    async def list_billing_accounts(self, context: PrincipalContext) -> list[BillingAccount]:
        await self._check(context, "read", "enterprise")
        return await self._list("billing_account", context.tenant_id, context.project_id, BillingAccount)

    async def record_meter_event(self, context: PrincipalContext, body: RecordMeterEventRequest) -> MeterEvent:
        await self._check(context, "write", "enterprise")
        account = await self._get(
            "billing_account", context.tenant_id, context.project_id, body.account_id, BillingAccount
        )
        if account is None or account.status != "active":
            raise ValueError("billing account is unavailable")
        existing = await self._get(
            "meter_event", context.tenant_id, context.project_id, body.idempotency_key, MeterEvent
        )
        if existing is not None:
            if (
                existing.account_id != body.account_id
                or existing.metric != body.metric
                or existing.amount != body.amount
                or existing.metadata != body.metadata
            ):
                raise ValueError("meter idempotency key was already used with a different event")
            return existing
        now = time.time()
        event = MeterEvent(
            record_id=body.idempotency_key,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_at=now,
            **body.model_dump(),
        )
        await self._save("meter_event", event)
        usage_key = f"{account.record_id}:{body.metric}"
        usage = await self._get("billing_usage", context.tenant_id, context.project_id, usage_key, BillingUsage)
        period_started = account.period_started_at if now < account.period_ends_at else now
        period_ends = account.period_ends_at if now < account.period_ends_at else now + 2_592_000
        updated_usage = BillingUsage(
            record_id=usage_key,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            account_id=account.record_id,
            metric=body.metric,
            amount=(usage.amount if usage and usage.period_ends_at > now else 0) + body.amount,
            period_started_at=period_started,
            period_ends_at=period_ends,
            updated_at=now,
        )
        await self._save("billing_usage", updated_usage)
        await self._record(
            context,
            "billing.meter.record",
            "meter_event",
            event.record_id,
            {"metric": event.metric, "amount": event.amount},
        )
        return event

    async def list_billing_usage(self, context: PrincipalContext, account_id: str | None = None) -> list[BillingUsage]:
        await self._check(context, "read", "enterprise")
        rows = await self._list("billing_usage", context.tenant_id, context.project_id, BillingUsage)
        return [item for item in rows if account_id is None or item.account_id == account_id]

    async def assign_billing_seat(self, context: PrincipalContext, body: AssignSeatRequest) -> SeatAssignment:
        await self._check(context, "write", "enterprise")
        account = await self._get(
            "billing_account", context.tenant_id, context.project_id, body.account_id, BillingAccount
        )
        if account is None or account.status != "active":
            raise ValueError("billing account is unavailable")
        existing = await self._list("seat_assignment", context.tenant_id, context.project_id, SeatAssignment)
        current = next(
            (
                item
                for item in existing
                if item.account_id == account.record_id and item.user_id == body.user_id and item.status == "active"
            ),
            None,
        )
        if current is not None:
            return current
        active_count = sum(1 for item in existing if item.account_id == account.record_id and item.status == "active")
        if active_count >= account.seat_limit:
            raise ValueError("billing seat limit exceeded")
        seat = SeatAssignment(
            record_id=_id("seat"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            account_id=account.record_id,
            user_id=body.user_id,
            assigned_by=context.principal_id,
            created_at=time.time(),
        )
        await self._save("seat_assignment", seat)
        await self._record(context, "billing.seat.assign", "seat_assignment", seat.record_id, {"user_id": body.user_id})
        return seat

    async def list_billing_seats(
        self, context: PrincipalContext, account_id: str | None = None
    ) -> list[SeatAssignment]:
        await self._check(context, "read", "enterprise")
        rows = await self._list("seat_assignment", context.tenant_id, context.project_id, SeatAssignment)
        return [item for item in rows if account_id is None or item.account_id == account_id]

    async def create_annotation_task(
        self, context: PrincipalContext, body: CreateAnnotationTaskRequest
    ) -> AnnotationTask:
        await self._check(context, "write", "data")
        now = time.time()
        record = AnnotationTask(
            record_id=_id("annotation"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_by=context.principal_id,
            created_at=now,
            updated_at=now,
            **body.model_dump(),
        )
        await self._save("annotation_task", record)
        await self._record(
            context,
            "data.annotation.create",
            "annotation_task",
            record.record_id,
            {"asset_count": len(record.asset_ids)},
        )
        return record

    async def list_annotation_tasks(self, context: PrincipalContext) -> list[AnnotationTask]:
        await self._check(context, "read", "data")
        return await self._list("annotation_task", context.tenant_id, context.project_id, AnnotationTask)

    async def register_annotation_provider(
        self, context: PrincipalContext, body: CreateAnnotationProviderRequest
    ) -> AnnotationProvider:
        await self._check(context, "write", "data")
        now = time.time()
        provider = AnnotationProvider(
            record_id=_id("annotation-provider"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_at=now,
            updated_at=now,
            **body.model_dump(),
        )
        await self._save("annotation_provider", provider)
        await self._record(context, "data.annotation_provider.register", "annotation_provider", provider.record_id)
        return provider

    async def list_annotation_providers(self, context: PrincipalContext) -> list[AnnotationProvider]:
        await self._check(context, "read", "data")
        return await self._list("annotation_provider", context.tenant_id, context.project_id, AnnotationProvider)

    async def probe_annotation_provider(self, context: PrincipalContext, provider_id: str) -> AnnotationProvider:
        await self._check(context, "write", "data")
        provider = await self._get(
            "annotation_provider", context.tenant_id, context.project_id, provider_id, AnnotationProvider
        )
        if provider is None:
            raise ValueError("annotation provider not found")
        updated = provider.model_copy(update={"last_health": "configured", "updated_at": time.time()})
        await self._save("annotation_provider", updated)
        await self._record(context, "data.annotation_provider.probe", "annotation_provider", provider_id)
        return updated

    async def review_annotation_task(
        self, context: PrincipalContext, task_id: str, body: ReviewAnnotationTaskRequest
    ) -> AnnotationTask:
        await self._check(context, "write", "data")
        task = await self._get("annotation_task", context.tenant_id, context.project_id, task_id, AnnotationTask)
        if task is None or task.status in {AnnotationTaskStatus.APPROVED, AnnotationTaskStatus.REJECTED}:
            raise ValueError("annotation task is unavailable")
        updated = task.model_copy(
            update={
                "status": AnnotationTaskStatus.APPROVED if body.approved else AnnotationTaskStatus.REJECTED,
                "consistency_score": body.consistency_score,
                "review_comment": body.comment,
                "updated_at": time.time(),
            }
        )
        await self._save("annotation_task", updated)
        await self._record(
            context,
            "data.annotation.review",
            "annotation_task",
            task_id,
            {"approved": body.approved, "consistency_score": body.consistency_score},
        )
        return updated

    async def create_search_profile(
        self, context: PrincipalContext, body: CreateSearchRankingProfileRequest
    ) -> SearchRankingProfile:
        await self._check(context, "write", "search_index")
        if body.exact_weight + body.vector_weight <= 0:
            raise ValueError("at least one ranking weight must be positive")
        now = time.time()
        record = SearchRankingProfile(
            record_id=_id("rank"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_at=now,
            updated_at=now,
            **body.model_dump(),
        )
        await self._save("search_profile", record)
        await self._record(context, "search.profile.create", "search_profile", record.record_id)
        return record

    async def register_index_backend(self, context: PrincipalContext, body: CreateIndexBackendRequest) -> IndexBackend:
        await self._check(context, "write", "search_index")
        now = time.time()
        backend = IndexBackend(
            record_id=_id("index-backend"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_at=now,
            updated_at=now,
            **body.model_dump(),
        )
        await self._save("index_backend", backend)
        await self._record(context, "search.index_backend.register", "index_backend", backend.record_id)
        return backend

    async def list_index_backends(self, context: PrincipalContext) -> list[IndexBackend]:
        await self._check(context, "read", "search_index")
        return await self._list("index_backend", context.tenant_id, context.project_id, IndexBackend)

    async def probe_index_backend(self, context: PrincipalContext, backend_id: str) -> IndexBackend:
        await self._check(context, "write", "search_index")
        backend = await self._get("index_backend", context.tenant_id, context.project_id, backend_id, IndexBackend)
        if backend is None:
            raise ValueError("index backend not found")
        updated = backend.model_copy(update={"health": "configured", "updated_at": time.time()})
        await self._save("index_backend", updated)
        await self._record(context, "search.index_backend.probe", "index_backend", backend_id)
        return updated

    async def register_search_reranker(
        self, context: PrincipalContext, body: CreateSearchRerankerRequest
    ) -> SearchReranker:
        await self._check(context, "write", "search_index")
        now = time.time()
        reranker = SearchReranker(
            record_id=_id("reranker"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_at=now,
            updated_at=now,
            **body.model_dump(),
        )
        await self._save("search_reranker", reranker)
        await self._record(context, "search.reranker.register", "search_reranker", reranker.record_id)
        return reranker

    async def list_search_rerankers(self, context: PrincipalContext) -> list[SearchReranker]:
        await self._check(context, "read", "search_index")
        return await self._list("search_reranker", context.tenant_id, context.project_id, SearchReranker)

    async def probe_search_reranker(self, context: PrincipalContext, reranker_id: str) -> SearchReranker:
        await self._check(context, "write", "search_index")
        reranker = await self._get(
            "search_reranker", context.tenant_id, context.project_id, reranker_id, SearchReranker
        )
        if reranker is None:
            raise ValueError("search reranker not found")
        updated = reranker.model_copy(update={"health": "configured", "updated_at": time.time()})
        await self._save("search_reranker", updated)
        await self._record(context, "search.reranker.probe", "search_reranker", reranker_id)
        return updated

    async def list_search_profiles(self, context: PrincipalContext) -> list[SearchRankingProfile]:
        await self._check(context, "read", "search_index")
        return await self._list("search_profile", context.tenant_id, context.project_id, SearchRankingProfile)

    async def get_search_profile(self, context: PrincipalContext, profile_id: str) -> SearchRankingProfile | None:
        await self._check(context, "query", "search_index")
        return await self._get(
            "search_profile", context.tenant_id, context.project_id, profile_id, SearchRankingProfile
        )

    async def submit_search_feedback(
        self, context: PrincipalContext, body: CreateSearchRelevanceFeedbackRequest
    ) -> SearchRelevanceFeedback:
        await self._check(context, "write", "search_index")
        record = SearchRelevanceFeedback(
            record_id=_id("relevance"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_by=context.principal_id,
            created_at=time.time(),
            **body.model_dump(),
        )
        await self._save("search_feedback", record)
        await self._record(
            context,
            "search.feedback.create",
            "search_feedback",
            record.record_id,
            {"search_id": body.search_id, "relevant": body.relevant},
        )
        return record

    async def evaluate_search(self, context: PrincipalContext, body: CreateSearchEvaluationRequest) -> SearchEvaluation:
        await self._check(context, "write", "search_index")
        expected = set(body.expected_record_ids)
        returned = set(body.result_record_ids)
        intersection = expected & returned
        precision = len(intersection) / len(returned) if returned else 0.0
        recall = len(intersection) / len(expected) if expected else 0.0
        record = SearchEvaluation(
            record_id=_id("eval"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_by=context.principal_id,
            created_at=time.time(),
            precision=precision,
            recall=recall,
            **body.model_dump(),
        )
        await self._save("search_evaluation", record)
        await self._record(
            context,
            "search.evaluation.create",
            "search_evaluation",
            record.record_id,
            {"precision": precision, "recall": recall},
        )
        return record

    async def rebuild_index(self, context: PrincipalContext, body: CreateIndexRebuildRequest) -> IndexRebuildJob:
        await self._check(context, "write", "search_index")
        now = time.time()
        if self.indexes is None:
            raise RuntimeError("index store is not configured")
        records_seen, records_rebuilt = await self.indexes.rebuild(context.tenant_id, context.project_id, body.index_id)
        record = IndexRebuildJob(
            record_id=_id("rebuild"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            index_id=body.index_id,
            status="completed",
            records_seen=records_seen,
            records_rebuilt=records_rebuilt,
            created_by=context.principal_id,
            created_at=now,
            completed_at=now,
        )
        await self._save("index_rebuild", record)
        await self._record(
            context, "search.index.rebuild", "index_rebuild", record.record_id, {"index_id": body.index_id}
        )
        return record

    async def record_model_metric(self, context: PrincipalContext, metric: ModelMetricPoint) -> ModelMetricPoint:
        await self._check(context, "write", "model")
        if metric.tenant_id != context.tenant_id or metric.project_id != context.project_id:
            raise ValueError("metric context mismatch")
        await self._save("model_metric", metric)
        await self._record(
            context,
            "model.metric.record",
            "model_metric",
            metric.record_id,
            {"model_id": metric.model_id, "capability": metric.capability},
        )
        return metric

    async def model_health(
        self, context: PrincipalContext, model_id: str, model_version: str, capability: str
    ) -> ModelHealthSnapshot:
        await self._check(context, "read", "model")
        metrics = [
            item
            for item in await self._list("model_metric", context.tenant_id, context.project_id, ModelMetricPoint)
            if item.model_id == model_id and item.model_version == model_version and item.capability == capability
        ]
        latencies = sorted(item.latency_ms for item in metrics)
        p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else None
        error_rate = sum(item.error_rate for item in metrics) / len(metrics) if metrics else 0
        qualities = [item.quality_score for item in metrics if item.quality_score is not None]
        quality = sum(qualities) / len(qualities) if qualities else None
        degraded = error_rate > 0.05 or (p95 is not None and p95 > 1_000) or (quality is not None and quality < 0.8)
        return ModelHealthSnapshot(
            model_id=model_id,
            model_version=model_version,
            capability=capability,
            sample_count=len(metrics),
            p95_latency_ms=p95,
            error_rate=error_rate,
            quality_score=quality,
            degraded=degraded,
            rollback_recommended=degraded and len(metrics) >= 20,
            evaluated_at=time.time(),
        )

    async def create_flow(self, context: PrincipalContext, body: CreateFlowRequest) -> FlowDefinition:
        await self._check(context, "write", "flow")
        node_ids = {node.node_id for node in body.nodes}
        if body.entry_node_id not in node_ids:
            raise ValueError("flow entry node does not exist")
        if any(target not in node_ids for node in body.nodes for target in node.next_nodes):
            raise ValueError("flow references an unknown node")
        now = time.time()
        record = FlowDefinition(
            record_id=_id("flow"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_by=context.principal_id,
            created_at=now,
            updated_at=now,
            **body.model_dump(),
        )
        await self._save("flow", record)
        await self._record(context, "flow.create", "flow", record.record_id)
        return record

    async def list_flows(self, context: PrincipalContext) -> list[FlowDefinition]:
        await self._check(context, "read", "flow")
        return await self._list("flow", context.tenant_id, context.project_id, FlowDefinition)

    async def execute_flow(self, context: PrincipalContext, flow_id: str, body: ExecuteFlowRequest) -> FlowExecution:
        await self._check(context, "write", "flow")
        flow = await self._get("flow", context.tenant_id, context.project_id, flow_id, FlowDefinition)
        if flow is None:
            raise ValueError("flow not found")
        node = next(item for item in flow.nodes if item.node_id == flow.entry_node_id)
        now = time.time()
        execution = FlowExecution(
            record_id=_id("fx"),
            flow_id=flow_id,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            current_node_id=node.node_id,
            context=body.context,
            created_by=context.principal_id,
            created_at=now,
            updated_at=now,
        )
        await self._save("flow_execution", execution)
        execution = await self._advance_flow_execution(context, flow, execution, node.node_id)
        await self._record(context, "flow.execute", "flow_execution", execution.record_id, {"flow_id": flow_id})
        return execution

    async def _advance_flow_execution(
        self,
        context: PrincipalContext,
        flow: FlowDefinition,
        execution: FlowExecution,
        node_id: str,
    ) -> FlowExecution:
        """Run deterministic Flow nodes until approval or a terminal node."""
        nodes = {node.node_id: node for node in flow.nodes}
        current = execution
        visited: set[str] = set()
        while node_id:
            if node_id in visited:
                raise ValueError("flow contains a runtime cycle")
            visited.add(node_id)
            node = nodes.get(node_id)
            if node is None:
                raise ValueError("flow references an unknown node")
            now = time.time()
            if node.kind == FlowNodeKind.APPROVAL:
                approval = FlowApproval(
                    record_id=_id("approval"),
                    execution_id=current.record_id,
                    node_id=node.node_id,
                    tenant_id=context.tenant_id,
                    project_id=context.project_id,
                    created_at=now,
                    updated_at=now,
                )
                await self._save("flow_approval", approval)
                current = current.model_copy(
                    update={
                        "status": "waiting_approval",
                        "current_node_id": node_id,
                        "updated_at": now,
                        "completed_at": None,
                    }
                )
                await self._save("flow_execution", current)
                return current

            node_context = current.context.setdefault("nodes", {})
            node_context[node_id] = {"kind": node.kind.value, "status": "completed", "completed_at": now}
            output = node.config.get("output")
            if isinstance(output, dict):
                current.context.update(output)
            if node.kind == FlowNodeKind.WEBHOOK:
                # Network delivery is handled by the existing webhook subsystem;
                # Flow records the durable intent and leaves delivery retryable.
                current.context.setdefault("webhooks", []).append(
                    {"node_id": node_id, "target": node.config.get("target"), "status": "queued"}
                )

            next_node: str | None
            if node.kind == FlowNodeKind.CONDITION and len(node.next_nodes) > 1:
                field = node.config.get("field")
                if not isinstance(field, str):
                    raise ValueError(f"condition node {node_id} is missing a string field")
                expected = node.config.get("equals", True)
                next_node = node.next_nodes[0] if current.context.get(field) == expected else node.next_nodes[1]
            else:
                next_node = node.next_nodes[0] if node.next_nodes else None
            current = current.model_copy(
                update={"status": "running", "current_node_id": node_id, "context": current.context, "updated_at": now}
            )
            if next_node is None:
                current = current.model_copy(update={"status": "completed", "completed_at": now})
                await self._save("flow_execution", current)
                return current
            node_id = next_node
        return current

    async def list_flow_approvals(self, context: PrincipalContext, execution_id: str) -> list[FlowApproval]:
        await self._check(context, "read", "flow")
        approvals = await self._list("flow_approval", context.tenant_id, context.project_id, FlowApproval)
        return [item for item in approvals if item.execution_id == execution_id]

    async def decide_flow_approval(
        self, context: PrincipalContext, approval_id: str, body: DecideApprovalRequest
    ) -> FlowApproval:
        await self._check(context, "write", "flow")
        approval = await self._get("flow_approval", context.tenant_id, context.project_id, approval_id, FlowApproval)
        if approval is None or approval.status != "pending":
            raise ValueError("flow approval is unavailable")
        updated = approval.model_copy(
            update={
                "status": "approved" if body.approved else "rejected",
                "comment": body.comment,
                "decided_by": context.principal_id,
                "updated_at": time.time(),
            }
        )
        await self._save("flow_approval", updated)
        execution = await self._get(
            "flow_execution", context.tenant_id, context.project_id, approval.execution_id, FlowExecution
        )
        if execution is not None:
            next_node = None
            flow = await self._get("flow", context.tenant_id, context.project_id, execution.flow_id, FlowDefinition)
            if body.approved and flow is not None:
                node = next(item for item in flow.nodes if item.node_id == approval.node_id)
                next_node = node.next_nodes[0] if node.next_nodes else None
            if body.approved and flow is not None and next_node:
                await self._advance_flow_execution(
                    context, flow, execution.model_copy(update={"status": "running"}), next_node
                )
            else:
                now = time.time()
                await self._save(
                    "flow_execution",
                    execution.model_copy(
                        update={
                            "status": "completed" if body.approved else "rejected",
                            "current_node_id": execution.current_node_id,
                            "updated_at": now,
                            "completed_at": now,
                        }
                    ),
                )
        await self._record(context, "flow.approval.decide", "flow_approval", approval_id, {"approved": body.approved})
        return updated

    async def create_cluster(self, context: PrincipalContext, body: CreatePortraitClusterRequest) -> PortraitCluster:
        await self._check(context, "write", "portrait")
        now = time.time()
        record = PortraitCluster(
            record_id=_id("cluster"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_at=now,
            updated_at=now,
            **body.model_dump(),
        )
        await self._save("portrait_cluster", record)
        await self._record(context, "portrait.cluster.create", "portrait_cluster", record.record_id)
        return record

    async def list_clusters(self, context: PrincipalContext) -> list[PortraitCluster]:
        await self._check(context, "read", "portrait")
        return await self._list("portrait_cluster", context.tenant_id, context.project_id, PortraitCluster)

    async def create_association(
        self, context: PrincipalContext, body: CreatePortraitAssociationRequest
    ) -> PortraitAssociation:
        await self._check(context, "write", "portrait")
        record = PortraitAssociation(
            record_id=_id("assoc"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_at=time.time(),
            **body.model_dump(),
        )
        await self._save("portrait_association", record)
        await self._record(context, "portrait.association.create", "portrait_association", record.record_id)
        return record

    async def list_associations(self, context: PrincipalContext) -> list[PortraitAssociation]:
        await self._check(context, "read", "portrait")
        return await self._list("portrait_association", context.tenant_id, context.project_id, PortraitAssociation)

    async def create_event(self, context: PrincipalContext, body: CreatePortraitEventRequest) -> PortraitEvent:
        await self._check(context, "write", "portrait")
        record = PortraitEvent(
            record_id=_id("event"), tenant_id=context.tenant_id, project_id=context.project_id, **body.model_dump()
        )
        await self._save("portrait_event", record)
        await self._record(context, "portrait.event.create", "portrait_event", record.record_id)
        return record

    async def list_events(self, context: PrincipalContext) -> list[PortraitEvent]:
        await self._check(context, "read", "portrait")
        return await self._list("portrait_event", context.tenant_id, context.project_id, PortraitEvent)

    async def register_device(self, context: PrincipalContext, body: RegisterEdgeDeviceRequest) -> EdgeDevice:
        await self._check(context, "write", "edge")
        now = time.time()
        certificate = secrets.token_hex(32)
        record = EdgeDevice(
            record_id=_id("edge"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            certificate_fingerprint=hashlib.sha256(certificate.encode()).hexdigest(),
            created_at=now,
            updated_at=now,
            **body.model_dump(),
        )
        await self._save("edge_device", record)
        await self._record(context, "edge.device.register", "edge_device", record.record_id)
        return record

    async def list_devices(self, context: PrincipalContext) -> list[EdgeDevice]:
        await self._check(context, "read", "edge")
        return await self._list("edge_device", context.tenant_id, context.project_id, EdgeDevice)

    async def deploy_edge(self, context: PrincipalContext, body: CreateEdgeDeploymentRequest) -> EdgeDeployment:
        await self._check(context, "write", "edge")
        device = await self._get("edge_device", context.tenant_id, context.project_id, body.device_id, EdgeDevice)
        if device is None or device.status == EdgeDeviceStatus.REVOKED:
            raise ValueError("edge device is unavailable")
        now = time.time()
        deployment = EdgeDeployment(
            record_id=_id("edge-deploy"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_at=now,
            updated_at=now,
            **body.model_dump(),
        )
        await self._save("edge_deployment", deployment)
        await self._record(
            context,
            "edge.deployment.create",
            "edge_deployment",
            deployment.record_id,
            {"device_id": body.device_id, "artifact_sha256": body.artifact_sha256},
        )
        return deployment

    async def list_edge_deployments(self, context: PrincipalContext) -> list[EdgeDeployment]:
        await self._check(context, "read", "edge")
        return await self._list("edge_deployment", context.tenant_id, context.project_id, EdgeDeployment)

    async def acknowledge_edge_deployment(
        self, context: PrincipalContext, deployment_id: str, body: AcknowledgeEdgeDeploymentRequest
    ) -> EdgeDeployment:
        await self._check(context, "write", "edge")
        deployment = await self._get(
            "edge_deployment", context.tenant_id, context.project_id, deployment_id, EdgeDeployment
        )
        if deployment is None:
            raise ValueError("edge deployment not found")
        now = time.time()
        updated = deployment.model_copy(
            update={
                "status": "applied" if body.applied else "failed",
                "updated_at": now,
                "applied_at": now if body.applied else None,
            }
        )
        await self._save("edge_deployment", updated)
        await self._record(
            context,
            "edge.deployment.acknowledge",
            "edge_deployment",
            deployment_id,
            {"applied": body.applied, "error": body.error},
        )
        return updated

    async def edge_sync(self, context: PrincipalContext, device_id: str, object_ref: str, sha256: str) -> EdgeSyncItem:
        await self._check(context, "write", "edge")
        device = await self._get("edge_device", context.tenant_id, context.project_id, device_id, EdgeDevice)
        if device is None or device.status == EdgeDeviceStatus.REVOKED:
            raise ValueError("edge device is unavailable")
        now = time.time()
        item = EdgeSyncItem(
            record_id=_id("sync"),
            device_id=device_id,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            object_ref=object_ref,
            sha256=sha256,
            created_at=now,
        )
        await self._save("edge_sync", item)
        await self._save(
            "edge_device",
            device.model_copy(update={"status": EdgeDeviceStatus.ONLINE, "last_seen_at": now, "updated_at": now}),
        )
        await self._record(context, "edge.sync.enqueue", "edge_sync", item.record_id, {"device_id": device_id})
        return item

    async def edge_heartbeat(self, context: PrincipalContext, device_id: str, body: EdgeHeartbeatRequest) -> EdgeDevice:
        await self._check(context, "write", "edge")
        device = await self._get("edge_device", context.tenant_id, context.project_id, device_id, EdgeDevice)
        if device is None or device.status == EdgeDeviceStatus.REVOKED:
            raise ValueError("edge device is unavailable")
        now = time.time()
        updated = device.model_copy(
            update={"status": body.status, "last_seen_at": now, "metadata": body.metadata, "updated_at": now}
        )
        await self._save("edge_device", updated)
        await self._record(context, "edge.device.heartbeat", "edge_device", device_id, {"status": body.status.value})
        return updated

    async def acknowledge_edge_sync(
        self, context: PrincipalContext, item_id: str, body: AcknowledgeEdgeSyncRequest
    ) -> EdgeSyncItem:
        await self._check(context, "write", "edge")
        item = await self._get("edge_sync", context.tenant_id, context.project_id, item_id, EdgeSyncItem)
        if item is None:
            raise ValueError("edge sync item not found")
        updated = item.model_copy(
            update={
                "status": "acknowledged" if body.acknowledged else "failed",
                "acknowledged_at": time.time() if body.acknowledged else None,
            }
        )
        await self._save("edge_sync", updated)
        await self._record(context, "edge.sync.acknowledge", "edge_sync", item_id, {"acknowledged": body.acknowledged})
        return updated

    async def register_worker(self, context: PrincipalContext, body: RegisterWorkerRequest) -> WorkerLease:
        await self._check(context, "write", "operations")
        now = time.time()
        lease = WorkerLease(
            record_id=f"{body.lane}:{body.worker_id}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            worker_id=body.worker_id,
            lane=body.lane,
            capacity=body.capacity,
            last_heartbeat_at=now,
            lease_expires_at=now + body.lease_seconds,
            created_at=now,
        )
        await self._save("worker_lease", lease)
        await self._record(
            context,
            "operations.worker.register",
            "worker_lease",
            lease.record_id,
            {"lane": body.lane, "capacity": body.capacity},
        )
        return lease

    async def heartbeat_worker(
        self, context: PrincipalContext, worker_id: str, body: WorkerHeartbeatRequest
    ) -> WorkerLease:
        await self._check(context, "write", "operations")
        workers = await self._list("worker_lease", context.tenant_id, context.project_id, WorkerLease)
        lease = next((item for item in workers if item.worker_id == worker_id), None)
        if lease is None or lease.status != "active":
            raise ValueError("worker lease is unavailable")
        now = time.time()
        updated = lease.model_copy(update={"last_heartbeat_at": now, "lease_expires_at": now + body.lease_seconds})
        await self._save("worker_lease", updated)
        return updated

    async def list_workers(self, context: PrincipalContext) -> list[WorkerLease]:
        await self._check(context, "read", "operations")
        workers = await self._list("worker_lease", context.tenant_id, context.project_id, WorkerLease)
        now = time.time()
        return [
            item.model_copy(update={"status": "expired" if item.lease_expires_at <= now else item.status})
            for item in workers
        ]

    async def register_tool(self, context: PrincipalContext, body: RegisterAgentToolRequest) -> AgentTool:
        await self._check(context, "write", "agent")
        record = AgentTool(
            record_id=_id("tool"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_at=time.time(),
            **body.model_dump(),
        )
        await self._save("agent_tool", record)
        await self._record(context, "agent.tool.register", "agent_tool", record.record_id)
        return record

    async def list_tools(self, context: PrincipalContext) -> list[AgentTool]:
        await self._check(context, "read", "agent")
        return await self._list("agent_tool", context.tenant_id, context.project_id, AgentTool)

    async def propose_action(self, context: PrincipalContext, body: ProposeAgentActionRequest) -> AgentAction:
        await self._check(context, "write", "agent")
        tool = await self._get("agent_tool", context.tenant_id, context.project_id, body.tool_id, AgentTool)
        if tool is None or not tool.enabled:
            raise ValueError("agent tool is unavailable")
        if context.scopes and "*" not in context.scopes and not tool.scopes.issubset(context.scopes):
            raise PolicyDenied("agent tool scope exceeds the caller's granted scopes")
        status = AgentActionStatus.PENDING_APPROVAL if tool.requires_approval else AgentActionStatus.APPROVED
        now = time.time()
        action = AgentAction(
            record_id=_id("action"),
            tool_id=body.tool_id,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            input=body.input,
            status=status,
            created_by=context.principal_id,
            created_at=now,
            updated_at=now,
        )
        await self._save("agent_action", action)
        await self._record(
            context,
            "agent.action.propose",
            "agent_action",
            action.record_id,
            {"tool_id": body.tool_id, "requires_approval": tool.requires_approval},
        )
        return action

    async def decide_action(
        self, context: PrincipalContext, action_id: str, body: ApproveAgentActionRequest
    ) -> AgentAction:
        await self._check(context, "write", "agent")
        action = await self._get("agent_action", context.tenant_id, context.project_id, action_id, AgentAction)
        if action is None or action.status != AgentActionStatus.PENDING_APPROVAL:
            raise ValueError("agent action is unavailable")
        status = AgentActionStatus.APPROVED if body.approved else AgentActionStatus.REJECTED
        updated = action.model_copy(
            update={"status": status, "updated_at": time.time(), "output": {"approval_comment": body.comment}}
        )
        await self._save("agent_action", updated)
        await self._record(
            context,
            "agent.action.decide",
            "agent_action",
            action_id,
            {"approved": body.approved, "comment": body.comment},
        )
        return updated

    async def execute_action(self, context: PrincipalContext, action_id: str) -> AgentAction:
        await self._check(context, "write", "agent")
        action = await self._get("agent_action", context.tenant_id, context.project_id, action_id, AgentAction)
        if action is None or action.status != AgentActionStatus.APPROVED:
            raise ValueError("agent action must be approved before execution")
        tool = await self._get("agent_tool", context.tenant_id, context.project_id, action.tool_id, AgentTool)
        if tool is None or not tool.enabled:
            raise ValueError("agent tool is unavailable")
        if context.scopes and "*" not in context.scopes and not tool.scopes.issubset(context.scopes):
            raise PolicyDenied("agent tool scope exceeds the caller's granted scopes")
        input_hash = hashlib.sha256(str(sorted(action.input.items())).encode()).hexdigest()
        updated = action.model_copy(
            update={
                "status": AgentActionStatus.EXECUTED,
                "output": {"status": "accepted", "tool": tool.name, "input_sha256": input_hash},
                "updated_at": time.time(),
            }
        )
        await self._save("agent_action", updated)
        await self._record(context, "agent.action.execute", "agent_action", action_id, {"tool_id": action.tool_id})
        return updated

    async def record_agent_trace(self, context: PrincipalContext, body: CreateAgentTraceRequest) -> AgentTrace:
        await self._check(context, "write", "agent")
        trace = AgentTrace(
            record_id=_id("trace"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_by=context.principal_id,
            created_at=time.time(),
            **body.model_dump(),
        )
        await self._save("agent_trace", trace)
        await self._record(context, "agent.trace.record", "agent_trace", trace.record_id)
        return trace

    async def list_agent_traces(self, context: PrincipalContext) -> list[AgentTrace]:
        await self._check(context, "read", "agent")
        return await self._list("agent_trace", context.tenant_id, context.project_id, AgentTrace)

    async def record_agent_evaluation(
        self, context: PrincipalContext, body: CreateAgentEvaluationRequest
    ) -> AgentEvaluation:
        await self._check(context, "write", "agent")
        evaluation = AgentEvaluation(
            record_id=_id("agent-eval"),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_by=context.principal_id,
            created_at=time.time(),
            **body.model_dump(),
        )
        await self._save("agent_evaluation", evaluation)
        await self._record(context, "agent.evaluation.record", "agent_evaluation", evaluation.record_id)
        return evaluation

    async def list_agent_evaluations(self, context: PrincipalContext) -> list[AgentEvaluation]:
        await self._check(context, "read", "agent")
        return await self._list("agent_evaluation", context.tenant_id, context.project_id, AgentEvaluation)

    async def put_agent_memory(self, context: PrincipalContext, body: PutAgentMemoryRequest) -> AgentMemoryEntry:
        await self._check(context, "write", "agent")
        now = time.time()
        memory_id = f"mem_{_sha(body.namespace + ':' + body.key)[:32]}"
        record = AgentMemoryEntry(
            record_id=memory_id,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            updated_by=context.principal_id,
            updated_at=now,
            expires_at=now + body.ttl_seconds if body.ttl_seconds is not None else None,
            **body.model_dump(exclude={"ttl_seconds"}),
        )
        await self._save("agent_memory", record)
        await self._record(context, "agent.memory.put", "agent_memory", record.record_id)
        return record

    async def get_agent_memory(self, context: PrincipalContext, namespace: str, key: str) -> AgentMemoryEntry | None:
        await self._check(context, "read", "agent")
        memory_id = f"mem_{_sha(namespace + ':' + key)[:32]}"
        record = await self._get("agent_memory", context.tenant_id, context.project_id, memory_id, AgentMemoryEntry)
        if record is not None and record.expires_at is not None and record.expires_at <= time.time():
            await self.store.delete("agent_memory", context.tenant_id, context.project_id, record.record_id)
            return None
        return record

    async def topology(self, context: PrincipalContext) -> DeploymentTopology:
        await self._check(context, "read", "operations")
        existing = await self._get("topology", context.tenant_id, context.project_id, "default", DeploymentTopology)
        if existing is not None:
            return existing
        return DeploymentTopology(
            record_id="default",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            constraints=["single_node", "single_gpu", "postgresql", "redis", "minio"],
            updated_at=time.time(),
        )


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


__all__ = [name for name in globals() if not name.startswith("_")]
