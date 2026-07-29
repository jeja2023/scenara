from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

Domain = Literal["portrait", "ocr"]
RunStatus = Literal["queued", "running", "pausing", "paused", "completed", "failed", "cancelling", "cancelled"]


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
    temporary: bool
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
