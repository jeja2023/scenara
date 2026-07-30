from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

Domain = Literal["portrait", "ocr"]
RunStatus = Literal["queued", "running", "pausing", "paused", "completed", "failed", "cancelling", "cancelled"]
FeedbackStatus = Literal["pending", "approved", "rejected"]
ModelReleaseStatus = Literal["candidate", "validated", "approved", "active", "retired"]


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
