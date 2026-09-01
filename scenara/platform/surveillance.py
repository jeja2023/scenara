"""Shared contracts for tenant-scoped portrait surveillance.

The module intentionally contains no portrait-runtime imports.  It defines the
control-plane records, durable alert event shape, and the narrow repository
port used by the portrait-domain matcher.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime, time as clock_time, timezone
from enum import StrEnum
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SurveillanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


class WatchlistCategory(StrEnum):
    BLACKLIST = "blacklist"
    WHITELIST = "whitelist"
    CUSTOM = "custom"


class WatchlistStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class WatchlistMemberStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    REMOVED = "removed"


class SurveillanceTaskStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    EXPIRED = "expired"
    FAILED = "failed"


class MatchPolicy(StrEnum):
    ALERT_ON_MATCH = "alert_on_match"
    SUPPRESS_ON_MATCH = "suppress_on_match"
    OBSERVE_ONLY = "observe_only"


class AlertLevel(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    IGNORED = "ignored"


class AlertModality(StrEnum):
    FACE = "face"
    BODY = "body"
    FUSED = "fused"


class ScheduleWindow(SurveillanceModel):
    weekday: int = Field(ge=1, le=7)
    start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$|^24:00$")

    @model_validator(mode="after")
    def valid_window(self) -> ScheduleWindow:
        if self.start == self.end:
            raise ValueError("schedule window start and end must differ")
        if self.start == "24:00":
            raise ValueError("schedule window start cannot be 24:00")
        if self.end != "24:00" and self.start > self.end:
            raise ValueError(
                "overnight schedule windows must be split into two windows"
            )
        return self


class ScheduleException(SurveillanceModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    enabled: bool

    @field_validator("date")
    @classmethod
    def valid_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value


class SurveillanceSchedule(SurveillanceModel):
    """IANA-timezone schedule.  An empty ``weekly`` list means always active."""

    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    weekly: list[ScheduleWindow] = Field(default_factory=list, max_length=64)
    exceptions: list[ScheduleException] = Field(default_factory=list, max_length=366)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        # UTC/GMT are fixed-offset zones guaranteed by the Python runtime.
        # Some Windows installations do not ship the optional IANA tzdata
        # package, so avoid making the most common default depend on it.
        if value.upper() in {"UTC", "GMT", "ETC/UTC"}:
            return "UTC"
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("schedule timezone must be an IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def unique_exception_dates(self) -> SurveillanceSchedule:
        if len({item.date for item in self.exceptions}) != len(self.exceptions):
            raise ValueError("schedule exceptions must not contain duplicate dates")
        return self

    def is_active(self, moment: float | None = None) -> bool:
        target_zone = (
            timezone.utc if self.timezone == "UTC" else ZoneInfo(self.timezone)
        )
        local = datetime.fromtimestamp(
            time.time() if moment is None else moment, UTC
        ).astimezone(target_zone)
        exception = next(
            (item for item in self.exceptions if item.date == local.date().isoformat()),
            None,
        )
        if exception is not None:
            return exception.enabled
        if not self.weekly:
            return True
        current = local.timetz().replace(tzinfo=None)
        for window in self.weekly:
            if window.weekday != local.isoweekday():
                continue
            start = clock_time.fromisoformat(window.start)
            end = (
                clock_time.max
                if window.end == "24:00"
                else clock_time.fromisoformat(window.end)
            )
            if start <= current < end:
                return True
        return False


class ThresholdPolicy(SurveillanceModel):
    """Thresholds are versioned alongside the applicable feature contract."""

    policy_version: str = Field(min_length=1, max_length=64)
    face_threshold: float | None = Field(default=None, ge=-1, le=1)
    body_threshold: float | None = Field(default=None, ge=-1, le=1)
    min_face_quality: float = Field(default=0.0, ge=0, le=1)
    min_body_quality: float = Field(default=0.0, ge=0, le=1)
    face_weight: float = Field(default=0.65, ge=0, le=1)
    body_weight: float = Field(default=0.35, ge=0, le=1)

    @model_validator(mode="after")
    def valid_thresholds(self) -> ThresholdPolicy:
        if self.face_threshold is None and self.body_threshold is None:
            raise ValueError("at least one modality threshold is required")
        if self.face_weight + self.body_weight <= 0:
            raise ValueError("at least one fusion weight must be positive")
        return self


class TaskBinding(SurveillanceModel):
    binding_id: str = Field(min_length=2, max_length=128)
    source_id: str = Field(min_length=2, max_length=128)
    camera_id: str = Field(min_length=1, max_length=128)
    active_run_id: str | None = None
    stream_session_id: str | None = None
    last_error: str | None = Field(default=None, max_length=500)


class Watchlist(SurveillanceModel):
    watchlist_id: str = Field(min_length=2, max_length=128)
    tenant_id: str
    project_id: str
    name: str = Field(min_length=1, max_length=160)
    category: WatchlistCategory = WatchlistCategory.CUSTOM
    description: str = Field(default="", max_length=2_000)
    status: WatchlistStatus = WatchlistStatus.ACTIVE
    created_by: str
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    revision: int = Field(default=1, ge=1)


class WatchlistMember(SurveillanceModel):
    member_id: str = Field(min_length=2, max_length=128)
    tenant_id: str
    project_id: str
    watchlist_id: str = Field(min_length=2, max_length=128)
    portrait_identity_id: str = Field(min_length=2, max_length=128)
    status: WatchlistMemberStatus = WatchlistMemberStatus.ACTIVE
    display_label: str = Field(default="", max_length=200)
    valid_from: float | None = Field(default=None, ge=0)
    valid_until: float | None = Field(default=None, ge=0)
    created_by: str
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    revision: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def valid_period(self) -> WatchlistMember:
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until <= self.valid_from
        ):
            raise ValueError("member valid_until must be later than valid_from")
        return self

    def active_at(self, moment: float) -> bool:
        return (
            self.status == WatchlistMemberStatus.ACTIVE
            and (self.valid_from is None or self.valid_from <= moment)
            and (self.valid_until is None or moment < self.valid_until)
        )


class SurveillanceTask(SurveillanceModel):
    task_id: str = Field(min_length=2, max_length=128)
    tenant_id: str
    project_id: str
    name: str = Field(min_length=1, max_length=160)
    status: SurveillanceTaskStatus = SurveillanceTaskStatus.DRAFT
    watchlist_ids: list[str] = Field(min_length=1, max_length=128)
    bindings: list[TaskBinding] = Field(min_length=1, max_length=512)
    schedule: SurveillanceSchedule = Field(default_factory=SurveillanceSchedule)
    match_policy: MatchPolicy = MatchPolicy.ALERT_ON_MATCH
    threshold_policy: ThresholdPolicy
    cooldown_seconds: int = Field(default=30, ge=1, le=86_400)
    alert_level: AlertLevel = AlertLevel.WARNING
    created_by: str
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    revision: int = Field(default=1, ge=1)

    @field_validator("watchlist_ids")
    @classmethod
    def unique_watchlists(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("task watchlist_ids must be unique")
        return value

    @field_validator("bindings")
    @classmethod
    def unique_bindings(cls, value: list[TaskBinding]) -> list[TaskBinding]:
        if len({item.binding_id for item in value}) != len(value):
            raise ValueError("task binding_ids must be unique")
        if len({(item.source_id, item.camera_id) for item in value}) != len(value):
            raise ValueError("task source/camera bindings must be unique")
        return value


class AlertRecord(SurveillanceModel):
    alert_id: str = Field(min_length=2, max_length=128)
    tenant_id: str
    project_id: str
    task_id: str
    binding_id: str
    watchlist_id: str
    member_id: str
    portrait_identity_id: str
    source_id: str
    camera_id: str
    run_id: str
    unit_id: str = ""
    track_id: str = ""
    trajectory_identity_id: str | None = None
    trajectory_segment_id: str | None = None
    match_score: float = Field(ge=-1, le=1)
    max_score: float = Field(ge=-1, le=1)
    modality: AlertModality
    threshold_policy_version: str = Field(min_length=1, max_length=64)
    model_bindings: dict[str, dict[str, str]] = Field(default_factory=dict)
    snapshot_artifact_id: str | None = None
    snapshot_retention_expires_at: float | None = None
    status: AlertStatus = AlertStatus.PENDING
    first_seen_at: float
    last_seen_at: float
    triggered_at: float
    occurrence_count: int = Field(default=1, ge=1)
    idempotency_key: str = Field(min_length=8, max_length=512)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    revision: int = Field(default=1, ge=1)
    triaged_by: str | None = None
    triaged_at: float | None = None
    triage_reason: str = Field(default="", max_length=256)
    triage_notes: str = Field(default="", max_length=2_000)


class AlertEvent(SurveillanceModel):
    event_id: str = Field(min_length=2, max_length=128)
    event_cursor: int = Field(default=0, ge=0)
    event_type: Literal["alert.triggered", "alert.triaged"]
    event_version: Literal["1.0"] = "1.0"
    occurred_at: str
    producer: Literal["scenara"] = "scenara"
    tenant_id: str
    project_id: str
    trace_id: str | None = None
    alert_id: str
    task_id: str
    camera_id: str
    portrait_identity_id: str
    match_score: float = Field(ge=-1, le=1)
    modality: AlertModality
    snapshot_artifact_id: str | None = None
    deduplication_key: str
    status: AlertStatus
    created_at: float = Field(default_factory=time.time)


class DebounceState(SurveillanceModel):
    debounce_key: str = Field(min_length=8, max_length=512)
    tenant_id: str
    project_id: str
    task_id: str
    binding_id: str
    watchlist_id: str
    portrait_identity_id: str
    first_seen_at: float
    last_seen_at: float
    last_alert_id: str | None = None
    occurrence_count: int = Field(default=1, ge=1)
    max_score: float = Field(ge=-1, le=1)
    modality: AlertModality
    cooldown_until: float
    revision: int = Field(default=1, ge=1)


class ObservationEvidence(SurveillanceModel):
    modality: Literal["face", "body"]
    embedding: list[float] = Field(min_length=1, max_length=65_536)
    quality: float = Field(default=0.0, ge=0, le=1)
    model_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=64)


class ObservationBatch(SurveillanceModel):
    run_id: str
    source_id: str
    camera_id: str
    unit_id: str = ""
    track_id: str = ""
    first_seen_at: float
    last_seen_at: float
    pts_ms: int | None = Field(default=None, ge=0)
    timestamp_source: Literal["recording", "decoder_pts", "processing_time"] = (
        "processing_time"
    )
    evidence: list[ObservationEvidence] = Field(min_length=1, max_length=2)
    snapshot_artifact_id: str | None = None
    snapshot_object_key: str | None = None
    trajectory_identity_id: str | None = None
    trajectory_segment_id: str | None = None
    trace_id: str | None = None


class AlertCandidate(SurveillanceModel):
    alert: AlertRecord
    event: AlertEvent
    debounce: DebounceState


class AlertWriteResult(SurveillanceModel):
    alert: AlertRecord
    event: AlertEvent | None = None
    emitted: bool


class WatchlistPage(SurveillanceModel):
    items: list[Watchlist]
    offset: int
    limit: int
    total: int


class WatchlistMemberPage(SurveillanceModel):
    items: list[WatchlistMember]
    offset: int
    limit: int
    total: int


class SurveillanceTaskPage(SurveillanceModel):
    items: list[SurveillanceTask]
    offset: int
    limit: int
    total: int


class AlertPage(SurveillanceModel):
    items: list[AlertRecord]
    offset: int
    limit: int
    total: int


class CreateWatchlistRequest(SurveillanceModel):
    name: str = Field(min_length=1, max_length=160)
    category: WatchlistCategory = WatchlistCategory.CUSTOM
    description: str = Field(default="", max_length=2_000)


class UpdateWatchlistRequest(SurveillanceModel):
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: WatchlistCategory | None = None
    description: str | None = Field(default=None, max_length=2_000)
    status: WatchlistStatus | None = None


class CreateWatchlistMemberRequest(SurveillanceModel):
    portrait_identity_id: str = Field(min_length=2, max_length=128)
    display_label: str = Field(default="", max_length=200)
    valid_from: float | None = Field(default=None, ge=0)
    valid_until: float | None = Field(default=None, ge=0)


class UpdateWatchlistMemberRequest(SurveillanceModel):
    expected_revision: int = Field(ge=1)
    status: WatchlistMemberStatus | None = None
    display_label: str | None = Field(default=None, max_length=200)
    valid_from: float | None = Field(default=None, ge=0)
    valid_until: float | None = Field(default=None, ge=0)


class CreateSurveillanceTaskRequest(SurveillanceModel):
    name: str = Field(min_length=1, max_length=160)
    watchlist_ids: list[str] = Field(min_length=1, max_length=128)
    bindings: list[TaskBinding] = Field(min_length=1, max_length=512)
    schedule: SurveillanceSchedule = Field(default_factory=SurveillanceSchedule)
    match_policy: MatchPolicy = MatchPolicy.ALERT_ON_MATCH
    threshold_policy: ThresholdPolicy
    cooldown_seconds: int = Field(default=30, ge=1, le=86_400)
    alert_level: AlertLevel = AlertLevel.WARNING


class UpdateSurveillanceTaskRequest(SurveillanceModel):
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    watchlist_ids: list[str] | None = Field(default=None, min_length=1, max_length=128)
    bindings: list[TaskBinding] | None = Field(
        default=None, min_length=1, max_length=512
    )
    schedule: SurveillanceSchedule | None = None
    match_policy: MatchPolicy | None = None
    threshold_policy: ThresholdPolicy | None = None
    cooldown_seconds: int | None = Field(default=None, ge=1, le=86_400)
    alert_level: AlertLevel | None = None


class TriageAlertRequest(SurveillanceModel):
    expected_revision: int = Field(ge=1)
    status: Literal["confirmed", "false_positive", "ignored"]
    reason: str = Field(min_length=1, max_length=256)
    notes: str = Field(default="", max_length=2_000)


class CreateAlertFeedbackRequest(SurveillanceModel):
    """Creates a pending feedback record without granting training approval."""

    correction: dict[str, Any] = Field(default_factory=dict)


class SurveillanceNotFound(RuntimeError):
    pass


class SurveillanceConflict(RuntimeError):
    pass


class SurveillanceRepository(Protocol):
    async def create_watchlist(self, watchlist: Watchlist) -> Watchlist: ...

    async def get_watchlist(
        self, tenant_id: str, project_id: str, watchlist_id: str
    ) -> Watchlist | None: ...

    async def list_watchlists(
        self, tenant_id: str, project_id: str, *, offset: int, limit: int
    ) -> tuple[list[Watchlist], int]: ...

    async def save_watchlist(
        self, watchlist: Watchlist, *, expected_revision: int
    ) -> Watchlist: ...

    async def delete_watchlist(
        self, tenant_id: str, project_id: str, watchlist_id: str
    ) -> bool: ...

    async def create_member(self, member: WatchlistMember) -> WatchlistMember: ...

    async def get_member(
        self, tenant_id: str, project_id: str, member_id: str
    ) -> WatchlistMember | None: ...

    async def list_members(
        self,
        tenant_id: str,
        project_id: str,
        watchlist_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[WatchlistMember], int]: ...

    async def list_active_members(
        self, tenant_id: str, project_id: str, watchlist_ids: list[str], *, at: float
    ) -> list[WatchlistMember]: ...

    async def save_member(
        self, member: WatchlistMember, *, expected_revision: int
    ) -> WatchlistMember: ...

    async def delete_member(
        self, tenant_id: str, project_id: str, member_id: str
    ) -> bool: ...

    async def create_task(self, task: SurveillanceTask) -> SurveillanceTask: ...

    async def get_task(
        self, tenant_id: str, project_id: str, task_id: str
    ) -> SurveillanceTask | None: ...

    async def list_tasks(
        self, tenant_id: str, project_id: str, *, offset: int, limit: int
    ) -> tuple[list[SurveillanceTask], int]: ...

    async def list_active_tasks_for_source(
        self, tenant_id: str, project_id: str, source_id: str
    ) -> list[SurveillanceTask]: ...

    async def list_active_tasks(
        self, tenant_id: str, project_id: str
    ) -> list[SurveillanceTask]: ...

    async def save_task(
        self, task: SurveillanceTask, *, expected_revision: int
    ) -> SurveillanceTask: ...

    async def list_all_active_tasks(self) -> list[SurveillanceTask]: ...

    async def record_alert(self, candidate: AlertCandidate) -> AlertWriteResult: ...

    async def get_alert(
        self, tenant_id: str, project_id: str, alert_id: str
    ) -> AlertRecord | None: ...

    async def list_alerts(
        self,
        tenant_id: str,
        project_id: str,
        *,
        status: AlertStatus | None,
        task_id: str | None,
        camera_id: str | None,
        watchlist_id: str | None,
        portrait_identity_id: str | None,
        since: float | None,
        until: float | None,
        offset: int,
        limit: int,
    ) -> tuple[list[AlertRecord], int]: ...

    async def triage_alert(
        self, alert: AlertRecord, event: AlertEvent, *, expected_revision: int
    ) -> AlertWriteResult: ...

    async def events_after(
        self, tenant_id: str, project_id: str, cursor: int, *, limit: int
    ) -> list[AlertEvent]: ...


__all__ = [
    "AlertCandidate",
    "AlertEvent",
    "AlertLevel",
    "AlertModality",
    "AlertPage",
    "AlertRecord",
    "AlertStatus",
    "AlertWriteResult",
    "CreateSurveillanceTaskRequest",
    "CreateAlertFeedbackRequest",
    "CreateWatchlistMemberRequest",
    "CreateWatchlistRequest",
    "DebounceState",
    "MatchPolicy",
    "ObservationBatch",
    "ObservationEvidence",
    "ScheduleException",
    "ScheduleWindow",
    "SurveillanceConflict",
    "SurveillanceNotFound",
    "SurveillanceRepository",
    "SurveillanceSchedule",
    "SurveillanceTask",
    "SurveillanceTaskPage",
    "SurveillanceTaskStatus",
    "TaskBinding",
    "ThresholdPolicy",
    "TriageAlertRequest",
    "UpdateSurveillanceTaskRequest",
    "UpdateWatchlistMemberRequest",
    "UpdateWatchlistRequest",
    "Watchlist",
    "WatchlistCategory",
    "WatchlistMember",
    "WatchlistMemberPage",
    "WatchlistMemberStatus",
    "WatchlistPage",
    "WatchlistStatus",
]
