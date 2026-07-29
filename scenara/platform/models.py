from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


class ExtensibleModel(BaseModel):
    model_config = ConfigDict(extra="allow", protected_namespaces=())


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"


class SourceKind(StrEnum):
    STREAM = "stream"


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


class PrincipalContext(StrictModel):
    tenant_id: str
    project_id: str
    principal_id: str = "anonymous"


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
    temporary: bool = False
    created_at: float
    expires_at: float | None = None


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


class PipelineRef(StrictModel):
    pipeline_id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=32)


class CreateRunRequest(StrictModel):
    domain: Literal["portrait", "ocr"]
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
    domain: Literal["portrait", "ocr"]
    pipeline: PipelineRef
    asset_id: str | None = None
    source_id: str | None = None
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
    block_type: str = "text"
    reading_order: int | None = Field(default=None, ge=0)


class OcrDomainPayload(ExtensibleModel):
    domain: Literal["ocr"] = "ocr"
    schema_version: Literal["1.0"] = "1.0"
    text: str = ""
    blocks: list[OcrTextBlock] = Field(default_factory=list)
    language: str | None = None


DomainPayload = Annotated[PortraitDomainPayload | OcrDomainPayload, Field(discriminator="domain")]


class MediaUnitResult(StrictModel):
    unit_id: str
    unit_type: Literal["frame", "page"]
    index: int = Field(ge=0)
    pts_ms: int | None = Field(default=None, ge=0)
    page_number: int | None = Field(default=None, ge=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    objects: list[VisionObject] = Field(default_factory=list)


class ModelProvenance(StrictModel):
    capability: str
    model_id: str
    version: str
    sha256: str | None = None
    production_ready: bool = False


class ResultEnvelope(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    domain: Literal["portrait", "ocr"]
    pipeline: PipelineRef
    asset_id: str | None = None
    source_id: str | None = None
    units: list[MediaUnitResult] = Field(default_factory=list)
    domain_payload: DomainPayload
    models: list[ModelProvenance] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    created_at: float


class ResultReference(StrictModel):
    run_id: str
    schema_version: Literal["1.0"] = "1.0"
    object_key: str
    sha256: str = Field(min_length=64, max_length=64)
    unit_count: int = Field(ge=0)
    domain: Literal["portrait", "ocr"]
    created_at: float


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


class MediaAssetPage(StrictModel):
    items: list[MediaAsset]
    offset: int
    limit: int
    total: int


class MediaSourcePage(StrictModel):
    items: list[MediaSource]
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
    enterprise_policy_provider: Literal["not_configured"] = "not_configured"


class ApiErrorDetail(StrictModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApiErrorEnvelope(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: str
    error: ApiErrorDetail
