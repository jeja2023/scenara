"""跨摄像头长期轨迹：身份归并、时空约束与人工研判闭环。"""

from __future__ import annotations

import time
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from scenara.platform.features import (
    DistanceMetric,
    FeatureRecord,
    FeatureSpace,
    FeatureStore,
)
from scenara.platform.models import PrincipalContext
from scenara.platform.policy import PolicyProvider, require_allowed

TrajectoryStatus = Literal["auto", "confirmed", "rejected"]
TrajectoryModality = Literal["body", "face"]
MatchMethod = Literal["new_identity", "reid", "manual"]

SUBJECT_TYPE = "portrait_long_term_identity"
MODALITY_MODELS: dict[str, tuple[str, str]] = {
    "body": ("person_reid_default", "v1"),
    "face": ("face_embedding_default", "v1"),
}
FUSION_WEIGHTS: dict[str, float] = {"face": 0.65, "body": 0.35}


class TrajectoryError(RuntimeError):
    """轨迹能力的通用错误。"""


class TrajectoryNotFound(TrajectoryError):
    """目标身份、片段或摄像头不存在。"""


class TrajectoryConflict(TrajectoryError):
    """请求与当前轨迹状态冲突。"""


class TrajectoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CameraTransition(TrajectoryModel):
    """两个摄像头之间的可达性约束。"""

    from_camera_id: str = Field(min_length=1, max_length=128)
    to_camera_id: str = Field(min_length=1, max_length=128)
    min_seconds: float = Field(default=0, ge=0, le=86_400)
    max_seconds: float | None = Field(default=None, ge=0, le=86_400)


class CameraRecord(TrajectoryModel):
    """摄像头一等实体，跨摄像头分析的设备锚点。"""

    camera_id: str = Field(min_length=1, max_length=128)
    tenant_id: str
    project_id: str
    display_name: str = Field(default="", max_length=256)
    location: str = Field(default="", max_length=256)
    auto_registered: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class LongTermIdentity(TrajectoryModel):
    """跨摄像头长期身份。"""

    identity_id: str
    tenant_id: str
    project_id: str
    display_name: str = Field(default="", max_length=256)
    status: TrajectoryStatus = "auto"
    modalities: list[str] = Field(default_factory=list)
    feature_space_ids: dict[str, str] = Field(default_factory=dict)
    camera_ids: list[str] = Field(default_factory=list)
    segment_count: int = 0
    first_seen_at: float
    last_seen_at: float
    last_camera_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class TrajectorySegment(TrajectoryModel):
    """一条 tracklet 在长期身份上的落点。"""

    segment_id: str
    identity_id: str
    tenant_id: str
    project_id: str
    run_id: str
    source_id: str = ""
    asset_id: str = ""
    camera_id: str = ""
    track_id: str = ""
    frame_count: int = 0
    track_quality: float = Field(default=0, ge=0, le=1)
    first_seen_at: float
    last_seen_at: float
    first_pts_ms: float | None = None
    last_pts_ms: float | None = None
    match_method: MatchMethod = "new_identity"
    match_score: float = Field(default=0, ge=-1, le=1)
    match_scores: dict[str, float] = Field(default_factory=dict)
    feature_ids: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


class ReachabilityObservation(TrajectoryModel):
    """时空可达性判定只需要邻近观测的机位与时间边界。"""

    camera_id: str
    first_seen_at: float
    last_seen_at: float


class ReachabilityProbe(TrajectoryModel):
    """候选身份在某个观测窗口前后紧邻的观测。

    `previous` 与 `following` 各取时间上最近的一条观测且不限机位：行程约束只
    在连续两次出现之间成立，所以紧邻观测落在本次机位时就没有发生转移，无需
    校验行程。`overlapping` 只统计异机位的时间重叠——同一机位内的时间重叠由
    同一 run 内的 tracklet 归属规则处理，不属于时空冲突。
    """

    overlapping: bool = False
    previous: ReachabilityObservation | None = None
    following: ReachabilityObservation | None = None


class TrajectoryIngestResult(TrajectoryModel):
    """单条 tracklet 的登记结果，未登记时给出原因。"""

    track_id: str
    registered: bool
    skip_reason: str | None = None
    created_identity: bool = False
    identity: LongTermIdentity | None = None
    segment: TrajectorySegment | None = None


class TimelineEntry(TrajectoryModel):
    """时间线上的一次出现。"""

    segment_id: str
    camera_id: str
    camera_name: str = ""
    run_id: str
    first_seen_at: float
    last_seen_at: float
    duration_seconds: float
    match_method: MatchMethod
    match_score: float
    transition_seconds: float | None = None


class IdentityPage(TrajectoryModel):
    items: list[LongTermIdentity]
    total: int
    offset: int
    limit: int


class SegmentPage(TrajectoryModel):
    items: list[TrajectorySegment]
    total: int
    offset: int
    limit: int


class RegisterCameraRequest(TrajectoryModel):
    camera_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(default="", max_length=256)
    location: str = Field(default="", max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateCameraRequest(TrajectoryModel):
    display_name: str | None = Field(default=None, max_length=256)
    location: str | None = Field(default=None, max_length=256)
    metadata: dict[str, Any] | None = None


class CameraTransitionEntry(TrajectoryModel):
    to_camera_id: str = Field(min_length=1, max_length=128)
    min_seconds: float = Field(default=0, ge=0, le=86_400)
    max_seconds: float | None = Field(default=None, ge=0, le=86_400)


class SetCameraTransitionsRequest(TrajectoryModel):
    transitions: list[CameraTransitionEntry] = Field(default_factory=list, max_length=512)


class UpdateIdentityRequest(TrajectoryModel):
    display_name: str | None = Field(default=None, max_length=256)
    status: TrajectoryStatus | None = None
    metadata: dict[str, Any] | None = None


class MergeIdentitiesRequest(TrajectoryModel):
    target_identity_id: str = Field(min_length=1, max_length=128)
    source_identity_ids: list[str] = Field(min_length=1, max_length=64)


class SplitIdentityRequest(TrajectoryModel):
    segment_ids: list[str] = Field(min_length=1, max_length=1_000)
    display_name: str = Field(default="", max_length=256)


class TrajectoryRepository(Protocol):
    """轨迹持久化协议，内存与 PostgreSQL 各自实现。"""

    async def put_identity(self, identity: LongTermIdentity) -> None: ...

    async def get_identity(self, tenant_id: str, project_id: str, identity_id: str) -> LongTermIdentity | None: ...

    async def list_identities(
        self,
        tenant_id: str,
        project_id: str,
        *,
        status: str | None = None,
        camera_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[LongTermIdentity], int]: ...

    async def delete_identity(self, tenant_id: str, project_id: str, identity_id: str) -> bool: ...

    async def put_segment(self, segment: TrajectorySegment) -> None: ...

    async def get_segment(self, tenant_id: str, project_id: str, segment_id: str) -> TrajectorySegment | None: ...

    async def list_segments(
        self,
        tenant_id: str,
        project_id: str,
        *,
        identity_id: str | None = None,
        camera_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[TrajectorySegment], int]: ...

    async def delete_segments_for_identity(self, tenant_id: str, project_id: str, identity_id: str) -> int: ...

    async def probe_reachability(
        self,
        tenant_id: str,
        project_id: str,
        *,
        identity_id: str,
        camera_id: str,
        window: tuple[float, float],
    ) -> ReachabilityProbe: ...

    async def put_camera(self, camera: CameraRecord) -> None: ...

    async def get_camera(self, tenant_id: str, project_id: str, camera_id: str) -> CameraRecord | None: ...

    async def list_cameras(self, tenant_id: str, project_id: str) -> list[CameraRecord]: ...

    async def delete_camera(self, tenant_id: str, project_id: str, camera_id: str) -> bool: ...

    async def replace_transitions(
        self, tenant_id: str, project_id: str, from_camera_id: str, transitions: list[CameraTransition]
    ) -> None: ...

    async def list_transitions(
        self, tenant_id: str, project_id: str, *, from_camera_id: str | None = None
    ) -> list[CameraTransition]: ...


def _in_window(value: float, since: float | None, until: float | None) -> bool:
    return not ((since is not None and value < since) or (until is not None and value > until))


class MemoryTrajectoryRepository:
    """开发与测试用的内存仓储，语义与 PostgreSQL 实现保持一致。"""

    def __init__(self) -> None:
        self._identities: dict[tuple[str, str, str], LongTermIdentity] = {}
        self._segments: dict[tuple[str, str, str], TrajectorySegment] = {}
        self._cameras: dict[tuple[str, str, str], CameraRecord] = {}
        self._transitions: dict[tuple[str, str, str, str], CameraTransition] = {}

    async def put_identity(self, identity: LongTermIdentity) -> None:
        key = (identity.tenant_id, identity.project_id, identity.identity_id)
        self._identities[key] = identity.model_copy(deep=True)

    async def get_identity(self, tenant_id: str, project_id: str, identity_id: str) -> LongTermIdentity | None:
        value = self._identities.get((tenant_id, project_id, identity_id))
        return value.model_copy(deep=True) if value else None

    async def list_identities(
        self,
        tenant_id: str,
        project_id: str,
        *,
        status: str | None = None,
        camera_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[LongTermIdentity], int]:
        rows = [
            item.model_copy(deep=True)
            for key, item in self._identities.items()
            if key[:2] == (tenant_id, project_id)
            and (status is None or item.status == status)
            and (camera_id is None or camera_id in item.camera_ids)
            and _in_window(item.last_seen_at, since, None)
            and _in_window(item.first_seen_at, None, until)
        ]
        rows.sort(key=lambda item: (-item.last_seen_at, item.identity_id))
        return rows[offset : offset + limit], len(rows)

    async def delete_identity(self, tenant_id: str, project_id: str, identity_id: str) -> bool:
        return self._identities.pop((tenant_id, project_id, identity_id), None) is not None

    async def put_segment(self, segment: TrajectorySegment) -> None:
        key = (segment.tenant_id, segment.project_id, segment.segment_id)
        self._segments[key] = segment.model_copy(deep=True)

    async def get_segment(self, tenant_id: str, project_id: str, segment_id: str) -> TrajectorySegment | None:
        value = self._segments.get((tenant_id, project_id, segment_id))
        return value.model_copy(deep=True) if value else None

    async def list_segments(
        self,
        tenant_id: str,
        project_id: str,
        *,
        identity_id: str | None = None,
        camera_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[TrajectorySegment], int]:
        rows = [
            item.model_copy(deep=True)
            for key, item in self._segments.items()
            if key[:2] == (tenant_id, project_id)
            and (identity_id is None or item.identity_id == identity_id)
            and (camera_id is None or item.camera_id == camera_id)
            and _in_window(item.last_seen_at, since, None)
            and _in_window(item.first_seen_at, None, until)
        ]
        rows.sort(key=lambda item: (item.first_seen_at, item.segment_id))
        return rows[offset : offset + limit], len(rows)

    async def delete_segments_for_identity(self, tenant_id: str, project_id: str, identity_id: str) -> int:
        keys = [
            key
            for key, item in self._segments.items()
            if key[:2] == (tenant_id, project_id) and item.identity_id == identity_id
        ]
        for key in keys:
            del self._segments[key]
        return len(keys)

    async def probe_reachability(
        self,
        tenant_id: str,
        project_id: str,
        *,
        identity_id: str,
        camera_id: str,
        window: tuple[float, float],
    ) -> ReachabilityProbe:
        previous: ReachabilityObservation | None = None
        following: ReachabilityObservation | None = None
        for key, item in self._segments.items():
            if key[:2] != (tenant_id, project_id) or item.identity_id != identity_id:
                continue
            if not item.camera_id:
                continue
            if _windows_overlap((item.first_seen_at, item.last_seen_at), window):
                if item.camera_id != camera_id:
                    return ReachabilityProbe(overlapping=True)
                continue
            observation = ReachabilityObservation(
                camera_id=item.camera_id,
                first_seen_at=item.first_seen_at,
                last_seen_at=item.last_seen_at,
            )
            if item.last_seen_at <= window[0]:
                if previous is None or observation.last_seen_at > previous.last_seen_at:
                    previous = observation
            elif following is None or observation.first_seen_at < following.first_seen_at:
                following = observation
        return ReachabilityProbe(previous=previous, following=following)

    async def put_camera(self, camera: CameraRecord) -> None:
        self._cameras[(camera.tenant_id, camera.project_id, camera.camera_id)] = camera.model_copy(deep=True)

    async def get_camera(self, tenant_id: str, project_id: str, camera_id: str) -> CameraRecord | None:
        value = self._cameras.get((tenant_id, project_id, camera_id))
        return value.model_copy(deep=True) if value else None

    async def list_cameras(self, tenant_id: str, project_id: str) -> list[CameraRecord]:
        rows = [
            item.model_copy(deep=True) for key, item in self._cameras.items() if key[:2] == (tenant_id, project_id)
        ]
        return sorted(rows, key=lambda item: item.camera_id)

    async def delete_camera(self, tenant_id: str, project_id: str, camera_id: str) -> bool:
        removed = self._cameras.pop((tenant_id, project_id, camera_id), None) is not None
        for key in [
            key
            for key in self._transitions
            if key[:2] == (tenant_id, project_id) and camera_id in (key[2], key[3])
        ]:
            del self._transitions[key]
        return removed

    async def replace_transitions(
        self, tenant_id: str, project_id: str, from_camera_id: str, transitions: list[CameraTransition]
    ) -> None:
        for key in [
            key for key in self._transitions if key[:3] == (tenant_id, project_id, from_camera_id)
        ]:
            del self._transitions[key]
        for transition in transitions:
            key = (tenant_id, project_id, transition.from_camera_id, transition.to_camera_id)
            self._transitions[key] = transition.model_copy(deep=True)

    async def list_transitions(
        self, tenant_id: str, project_id: str, *, from_camera_id: str | None = None
    ) -> list[CameraTransition]:
        rows = [
            item.model_copy(deep=True)
            for key, item in self._transitions.items()
            if key[:2] == (tenant_id, project_id) and (from_camera_id is None or key[2] == from_camera_id)
        ]
        return sorted(rows, key=lambda item: (item.from_camera_id, item.to_camera_id))


def _coerce_vector(value: Any) -> list[float] | None:
    if not isinstance(value, list) or not value:
        return None
    vector: list[float] = []
    for item in value:
        if not isinstance(item, int | float) or isinstance(item, bool):
            return None
        vector.append(float(item))
    return vector


def _track_embeddings(track: dict[str, Any]) -> dict[str, list[float]]:
    """从 tracklet 上取出各模态模板，只接受结构合法的向量。"""

    found: dict[str, list[float]] = {}
    for modality, key in (("body", "template"), ("face", "face_template")):
        payload = track.get(key)
        if not isinstance(payload, dict):
            continue
        vector = _coerce_vector(payload.get("embedding"))
        if vector is not None:
            found[modality] = vector
    return found


def _windows_overlap(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return left[0] <= right[1] and right[0] <= left[1]


class TrajectoryService:
    """把 tracklet 归并为跨摄像头长期身份，并提供人工研判操作。"""

    def __init__(
        self,
        repository: TrajectoryRepository,
        features: FeatureStore,
        policy: PolicyProvider,
        audit: Any,
        *,
        body_threshold: float = 0.72,
        face_threshold: float = 0.80,
        min_track_quality: float = 0.35,
        min_frame_count: int = 2,
        max_templates: int = 32,
        default_transition_seconds: float = 0.0,
    ) -> None:
        self._repository = repository
        self._features = features
        self._policy = policy
        self._audit = audit
        self._thresholds = {"body": body_threshold, "face": face_threshold}
        self._min_track_quality = min_track_quality
        self._min_frame_count = min_frame_count
        self._max_templates = max_templates
        self._default_transition_seconds = default_transition_seconds

    async def _ensure_space(self, modality: str, dimension: int) -> FeatureSpace:
        model_id, model_version = MODALITY_MODELS[modality]
        space = FeatureSpace(
            feature_space_id=f"portrait.trajectory.{modality}.{dimension}.v1",
            domain="portrait",
            modality=modality,
            model_id=model_id,
            model_version=model_version,
            dimension=dimension,
            distance_metric=DistanceMetric.COSINE,
            threshold=None,
        )
        existing = await self._features.get_space(space.feature_space_id)
        if existing is not None:
            return existing
        return await self._features.create_space(space)

    async def ensure_camera(self, context: PrincipalContext, camera_id: str) -> CameraRecord:
        """摄像头缺省自动登记，保证设备始终是可查询的一等实体。"""

        existing = await self._repository.get_camera(context.tenant_id, context.project_id, camera_id)
        if existing is not None:
            return existing
        now = time.time()
        camera = CameraRecord(
            camera_id=camera_id,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            display_name=camera_id,
            auto_registered=True,
            created_at=now,
            updated_at=now,
        )
        await self._repository.put_camera(camera)
        return camera

    async def _transition_allows(
        self,
        context: PrincipalContext,
        identity_id: str,
        camera_id: str,
        window: tuple[float, float],
    ) -> bool:
        """校验候选身份在时间上紧邻的异机位观测与本次观测是否时空可达。

        行程约束只在相邻的两次出现之间成立。一个人可以先在 A、再到 B、稍后
        仍留在 B：此时 A 与本次观测的间隔早已超出 A→B 的行程上限，却完全合乎
        物理。据此只比较紧邻的前后各一条异机位观测，而不是整段历史，否则身份
        积累的出现越多就越难被复用，最终退化成大量碎片身份。
        """

        probe = await self._repository.probe_reachability(
            context.tenant_id,
            context.project_id,
            identity_id=identity_id,
            camera_id=camera_id,
            window=window,
        )
        if probe.overlapping:
            return False
        if probe.previous is None and probe.following is None:
            return True
        transitions = await self._repository.list_transitions(
            context.tenant_id, context.project_id
        )
        bounds: dict[tuple[str, str], tuple[float, float | None]] = {}
        for transition in transitions:
            bounds[(transition.from_camera_id, transition.to_camera_id)] = (
                transition.min_seconds,
                transition.max_seconds,
            )
        previous = probe.previous
        if (
            previous is not None
            and previous.camera_id != camera_id
            and not self._gap_allows(
                bounds,
                (previous.camera_id, camera_id),
                window[0] - previous.last_seen_at,
            )
        ):
            return False
        following = probe.following
        if (
            following is not None
            and following.camera_id != camera_id
            and not self._gap_allows(
                bounds,
                (camera_id, following.camera_id),
                following.first_seen_at - window[1],
            )
        ):
            return False
        return True

    def _gap_allows(
        self,
        bounds: dict[tuple[str, str], tuple[float, float | None]],
        key: tuple[str, str],
        gap: float,
    ) -> bool:
        """单段转移的间隔是否落在配置的行程区间内。"""

        minimum, maximum = bounds.get(key, (self._default_transition_seconds, None))
        return gap >= minimum and (maximum is None or gap <= maximum)

    async def _candidates(
        self, context: PrincipalContext, embeddings: dict[str, list[float]]
    ) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
        """在各模态空间检索，返回 identity -> {modality: score} 与所用空间。"""

        per_identity: dict[str, dict[str, float]] = {}
        spaces: dict[str, str] = {}
        for modality, vector in embeddings.items():
            space = await self._ensure_space(modality, len(vector))
            spaces[modality] = space.feature_space_id
            matches = await self._features.search(
                context.tenant_id,
                context.project_id,
                space.feature_space_id,
                vector,
                limit=16,
                threshold=self._thresholds[modality],
            )
            for match in matches:
                if match.subject_type != SUBJECT_TYPE:
                    continue
                bucket = per_identity.setdefault(match.subject_id, {})
                if match.score > bucket.get(modality, -1.0):
                    bucket[modality] = match.score
        return per_identity, spaces

    def _fuse(self, scores: dict[str, float]) -> float:
        if len(scores) == 1:
            return next(iter(scores.values()))
        weight = sum(FUSION_WEIGHTS[modality] for modality in scores)
        return sum(FUSION_WEIGHTS[modality] * score for modality, score in scores.items()) / weight

    async def ingest_run_tracks(
        self,
        context: PrincipalContext,
        *,
        run_id: str,
        tracks: list[dict[str, Any]],
        source_id: str = "",
        asset_id: str = "",
        camera_id: str = "",
        recording_started_at: float | None = None,
    ) -> list[TrajectoryIngestResult]:
        """把一个 run 的全部 tracklet 归并到长期身份。"""

        await require_allowed(self._policy, context, "write", "portrait_trajectory")
        results: list[TrajectoryIngestResult] = []
        if camera_id:
            await self.ensure_camera(context, camera_id)
        base_time = recording_started_at if recording_started_at is not None else time.time()
        has_absolute_time = recording_started_at is not None
        claimed: dict[str, list[tuple[float, float]]] = {}

        for track in tracks:
            track_id = str(track.get("track_id") or "")
            skip = self._quality_gate(track)
            if skip is not None:
                results.append(TrajectoryIngestResult(track_id=track_id, registered=False, skip_reason=skip))
                continue
            embeddings = _track_embeddings(track)
            if not embeddings:
                results.append(
                    TrajectoryIngestResult(track_id=track_id, registered=False, skip_reason="missing_embedding")
                )
                continue
            window = self._observation_window(track, base_time)
            result = await self._ingest_one(
                context,
                run_id=run_id,
                track=track,
                track_id=track_id,
                embeddings=embeddings,
                window=window,
                has_absolute_time=has_absolute_time,
                claimed=claimed,
                source_id=source_id,
                asset_id=asset_id,
                camera_id=camera_id,
            )
            results.append(result)
        return results

    def _quality_gate(self, track: dict[str, Any]) -> str | None:
        quality = track.get("tracklet_quality_score")
        if (
            isinstance(quality, int | float)
            and not isinstance(quality, bool)
            and float(quality) < self._min_track_quality
        ):
            return "low_quality"
        frame_count = track.get("frame_count")
        if isinstance(frame_count, int) and not isinstance(frame_count, bool) and frame_count < self._min_frame_count:
            return "too_few_frames"
        return None

    def _observation_window(self, track: dict[str, Any], base_time: float) -> tuple[float, float]:
        """由帧内 pts_ms 还原真实观测时间窗，缺失时退化为录制起点。"""

        first_pts = track.get("first_pts_ms")
        last_pts = track.get("last_pts_ms")
        if isinstance(first_pts, int | float) and isinstance(last_pts, int | float):
            first = base_time + float(first_pts) / 1000.0
            last = base_time + float(last_pts) / 1000.0
            return (min(first, last), max(first, last))
        return (base_time, base_time)

    async def _ingest_one(
        self,
        context: PrincipalContext,
        *,
        run_id: str,
        track: dict[str, Any],
        track_id: str,
        embeddings: dict[str, list[float]],
        window: tuple[float, float],
        has_absolute_time: bool,
        claimed: dict[str, list[tuple[float, float]]],
        source_id: str,
        asset_id: str,
        camera_id: str,
    ) -> TrajectoryIngestResult:
        per_identity, spaces = await self._candidates(context, embeddings)
        ranked = sorted(
            ((identity_id, scores) for identity_id, scores in per_identity.items()),
            key=lambda item: (-self._fuse(item[1]), item[0]),
        )

        chosen_id: str | None = None
        chosen_scores: dict[str, float] = {}
        for identity_id, scores in ranked:
            identity = await self._repository.get_identity(context.tenant_id, context.project_id, identity_id)
            if identity is None or identity.status == "rejected":
                continue
            # 同一 run 内时间重叠的 tracklet 必属不同人，禁止归并到同一身份。
            if any(_windows_overlap(window, taken) for taken in claimed.get(identity_id, [])):
                continue
            # Relative PTS is enough to separate simultaneous tracklets in one
            # run, but cross-run topology must only use an authoritative media
            # start time. Processing time is not an observation timestamp.
            if (
                camera_id
                and has_absolute_time
                and not await self._transition_allows(context, identity_id, camera_id, window)
            ):
                continue
            chosen_id = identity_id
            chosen_scores = scores
            break

        now = time.time()
        created = chosen_id is None
        if chosen_id is None:
            identity_id = f"lti_{uuid4().hex}"
            identity = LongTermIdentity(
                identity_id=identity_id,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                display_name=identity_id,
                modalities=sorted(embeddings),
                feature_space_ids={modality: spaces[modality] for modality in embeddings},
                camera_ids=[camera_id] if camera_id else [],
                segment_count=0,
                first_seen_at=window[0],
                last_seen_at=window[1],
                last_camera_id=camera_id,
                created_at=now,
                updated_at=now,
            )
            match_method: MatchMethod = "new_identity"
            match_score = 1.0
        else:
            identity_id = chosen_id
            stored = await self._repository.get_identity(context.tenant_id, context.project_id, identity_id)
            if stored is None:  # pragma: no cover - 并发删除
                raise TrajectoryNotFound("long-term identity disappeared during ingest")
            identity = stored
            match_method = "reid"
            match_score = self._fuse(chosen_scores)

        feature_ids = await self._store_templates(context, identity_id, embeddings, spaces)
        segment = TrajectorySegment(
            segment_id=f"lts_{uuid4().hex}",
            identity_id=identity_id,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            run_id=run_id,
            source_id=source_id,
            asset_id=asset_id,
            camera_id=camera_id,
            track_id=track_id,
            frame_count=int(track.get("frame_count") or 0),
            track_quality=max(0.0, min(1.0, float(track.get("tracklet_quality_score") or 0.0))),
            first_seen_at=window[0],
            last_seen_at=window[1],
            first_pts_ms=track.get("first_pts_ms") if isinstance(track.get("first_pts_ms"), int | float) else None,
            last_pts_ms=track.get("last_pts_ms") if isinstance(track.get("last_pts_ms"), int | float) else None,
            match_method=match_method,
            match_score=match_score,
            match_scores=dict(chosen_scores),
            feature_ids=feature_ids,
            created_at=now,
        )
        await self._repository.put_segment(segment)

        identity = self._apply_segment(identity, segment, spaces, embeddings, now)
        await self._repository.put_identity(identity)
        await self._prune_templates(context, identity_id, identity.feature_space_ids)
        claimed.setdefault(identity_id, []).append(window)

        await self._audit.record(
            context,
            action="portrait.trajectory.ingest",
            resource_type="portrait_trajectory",
            resource_id=identity_id,
            evidence={
                "segment_id": segment.segment_id,
                "run_id": run_id,
                "camera_id": camera_id,
                "match_method": match_method,
                "match_score": round(match_score, 6),
                "modalities": sorted(embeddings),
                "created_identity": created,
            },
        )
        return TrajectoryIngestResult(
            track_id=track_id,
            registered=True,
            created_identity=created,
            identity=identity,
            segment=segment,
        )

    def _apply_segment(
        self,
        identity: LongTermIdentity,
        segment: TrajectorySegment,
        spaces: dict[str, str],
        embeddings: dict[str, list[float]],
        now: float,
    ) -> LongTermIdentity:
        camera_ids = list(identity.camera_ids)
        if segment.camera_id and segment.camera_id not in camera_ids:
            camera_ids.append(segment.camera_id)
        modalities = sorted(set(identity.modalities) | set(embeddings))
        feature_space_ids = {**identity.feature_space_ids, **{m: spaces[m] for m in embeddings}}
        last_seen_at = max(identity.last_seen_at, segment.last_seen_at)
        return identity.model_copy(
            update={
                "modalities": modalities,
                "feature_space_ids": feature_space_ids,
                "camera_ids": camera_ids,
                "segment_count": identity.segment_count + 1,
                "first_seen_at": min(identity.first_seen_at, segment.first_seen_at),
                "last_seen_at": last_seen_at,
                "last_camera_id": (
                    segment.camera_id if last_seen_at == segment.last_seen_at else identity.last_camera_id
                ),
                "updated_at": now,
            }
        )

    async def _store_templates(
        self,
        context: PrincipalContext,
        identity_id: str,
        embeddings: dict[str, list[float]],
        spaces: dict[str, str],
    ) -> dict[str, str]:
        """保留多个观测模板，让身份能适应视角与着装变化。"""

        feature_ids: dict[str, str] = {}
        for modality, vector in embeddings.items():
            record = await self._features.add(
                FeatureRecord(
                    feature_id=f"ltf_{uuid4().hex}",
                    tenant_id=context.tenant_id,
                    project_id=context.project_id,
                    feature_space_id=spaces[modality],
                    subject_type=SUBJECT_TYPE,
                    subject_id=identity_id,
                    embedding=vector,
                )
            )
            feature_ids[modality] = record.feature_id
        return feature_ids

    async def _prune_templates(
        self, context: PrincipalContext, identity_id: str, feature_space_ids: dict[str, str]
    ) -> None:
        """超出模板上限时淘汰质量最低的观测，避免向量库无界增长。"""

        for space_id in set(feature_space_ids.values()):
            stored = await self._features.list_subject_features(
                context.tenant_id, context.project_id, space_id, SUBJECT_TYPE, identity_id
            )
            if len(stored) <= self._max_templates:
                continue
            segments, _ = await self._repository.list_segments(
                context.tenant_id, context.project_id, identity_id=identity_id, limit=1_000
            )
            quality_by_feature = {
                feature_id: segment.track_quality
                for segment in segments
                for feature_id in segment.feature_ids.values()
            }
            ordered = sorted(
                stored,
                key=lambda item: (quality_by_feature.get(item.feature_id, 0.0), item.created_at),
            )
            for record in ordered[: len(stored) - self._max_templates]:
                await self._features.delete_feature(context.tenant_id, context.project_id, record.feature_id)

    # ------------------------------------------------------------------
    # 摄像头
    # ------------------------------------------------------------------

    async def register_camera(self, context: PrincipalContext, request: RegisterCameraRequest) -> CameraRecord:
        await require_allowed(self._policy, context, "write", "portrait_camera")
        now = time.time()
        existing = await self._repository.get_camera(context.tenant_id, context.project_id, request.camera_id)
        camera = CameraRecord(
            camera_id=request.camera_id,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            display_name=request.display_name or request.camera_id,
            location=request.location,
            auto_registered=False,
            metadata=request.metadata,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        await self._repository.put_camera(camera)
        await self._audit.record(
            context,
            action="portrait.camera.register",
            resource_type="portrait_camera",
            resource_id=camera.camera_id,
        )
        return camera

    async def list_cameras(self, context: PrincipalContext) -> list[CameraRecord]:
        await require_allowed(self._policy, context, "read", "portrait_camera")
        return await self._repository.list_cameras(context.tenant_id, context.project_id)

    async def get_camera(self, context: PrincipalContext, camera_id: str) -> CameraRecord:
        await require_allowed(self._policy, context, "read", "portrait_camera")
        camera = await self._repository.get_camera(context.tenant_id, context.project_id, camera_id)
        if camera is None:
            raise TrajectoryNotFound("camera not found")
        return camera

    async def update_camera(
        self, context: PrincipalContext, camera_id: str, request: UpdateCameraRequest
    ) -> CameraRecord:
        await require_allowed(self._policy, context, "write", "portrait_camera")
        camera = await self.get_camera(context, camera_id)
        updates: dict[str, Any] = {"updated_at": time.time(), "auto_registered": False}
        if request.display_name is not None:
            updates["display_name"] = request.display_name
        if request.location is not None:
            updates["location"] = request.location
        if request.metadata is not None:
            updates["metadata"] = request.metadata
        camera = camera.model_copy(update=updates)
        await self._repository.put_camera(camera)
        await self._audit.record(
            context,
            action="portrait.camera.update",
            resource_type="portrait_camera",
            resource_id=camera_id,
        )
        return camera

    async def delete_camera(self, context: PrincipalContext, camera_id: str) -> None:
        await require_allowed(self._policy, context, "delete", "portrait_camera")
        if not await self._repository.delete_camera(context.tenant_id, context.project_id, camera_id):
            raise TrajectoryNotFound("camera not found")
        await self._audit.record(
            context,
            action="portrait.camera.delete",
            resource_type="portrait_camera",
            resource_id=camera_id,
        )

    async def set_camera_transitions(
        self, context: PrincipalContext, camera_id: str, request: SetCameraTransitionsRequest
    ) -> list[CameraTransition]:
        await require_allowed(self._policy, context, "write", "portrait_camera")
        await self.ensure_camera(context, camera_id)
        transitions = [
            CameraTransition(
                from_camera_id=camera_id,
                to_camera_id=entry.to_camera_id,
                min_seconds=entry.min_seconds,
                max_seconds=entry.max_seconds,
            )
            for entry in request.transitions
        ]
        for transition in transitions:
            await self.ensure_camera(context, transition.to_camera_id)
        await self._repository.replace_transitions(
            context.tenant_id, context.project_id, camera_id, transitions
        )
        await self._audit.record(
            context,
            action="portrait.camera.transitions",
            resource_type="portrait_camera",
            resource_id=camera_id,
            evidence={"transition_count": len(transitions)},
        )
        return transitions

    async def list_camera_transitions(self, context: PrincipalContext, camera_id: str) -> list[CameraTransition]:
        await require_allowed(self._policy, context, "read", "portrait_camera")
        await self.get_camera(context, camera_id)
        return await self._repository.list_transitions(
            context.tenant_id, context.project_id, from_camera_id=camera_id
        )

    # ------------------------------------------------------------------
    # 身份查询与人工研判
    # ------------------------------------------------------------------

    async def list_identities(
        self,
        context: PrincipalContext,
        *,
        status: str | None = None,
        camera_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> IdentityPage:
        await require_allowed(self._policy, context, "read", "portrait_trajectory")
        items, total = await self._repository.list_identities(
            context.tenant_id,
            context.project_id,
            status=status,
            camera_id=camera_id,
            since=since,
            until=until,
            offset=offset,
            limit=limit,
        )
        return IdentityPage(items=items, total=total, offset=offset, limit=limit)

    async def get_identity(self, context: PrincipalContext, identity_id: str) -> LongTermIdentity:
        await require_allowed(self._policy, context, "read", "portrait_trajectory")
        identity = await self._repository.get_identity(context.tenant_id, context.project_id, identity_id)
        if identity is None:
            raise TrajectoryNotFound("long-term identity not found")
        return identity

    async def list_segments(
        self,
        context: PrincipalContext,
        identity_id: str,
        *,
        camera_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> SegmentPage:
        await self.get_identity(context, identity_id)
        items, total = await self._repository.list_segments(
            context.tenant_id,
            context.project_id,
            identity_id=identity_id,
            camera_id=camera_id,
            since=since,
            until=until,
            offset=offset,
            limit=limit,
        )
        return SegmentPage(items=items, total=total, offset=offset, limit=limit)

    async def timeline(self, context: PrincipalContext, identity_id: str) -> list[TimelineEntry]:
        """按真实时间排列的跨摄像头出现序列。"""

        await self.get_identity(context, identity_id)
        segments, _ = await self._repository.list_segments(
            context.tenant_id, context.project_id, identity_id=identity_id, limit=1_000
        )
        cameras = {
            camera.camera_id: camera.display_name
            for camera in await self._repository.list_cameras(context.tenant_id, context.project_id)
        }
        entries: list[TimelineEntry] = []
        previous_end: float | None = None
        for segment in segments:
            entries.append(
                TimelineEntry(
                    segment_id=segment.segment_id,
                    camera_id=segment.camera_id,
                    camera_name=cameras.get(segment.camera_id, segment.camera_id),
                    run_id=segment.run_id,
                    first_seen_at=segment.first_seen_at,
                    last_seen_at=segment.last_seen_at,
                    duration_seconds=max(0.0, segment.last_seen_at - segment.first_seen_at),
                    match_method=segment.match_method,
                    match_score=segment.match_score,
                    transition_seconds=(
                        None if previous_end is None else max(0.0, segment.first_seen_at - previous_end)
                    ),
                )
            )
            previous_end = segment.last_seen_at
        return entries

    async def update_identity(
        self, context: PrincipalContext, identity_id: str, request: UpdateIdentityRequest
    ) -> LongTermIdentity:
        await require_allowed(self._policy, context, "write", "portrait_trajectory")
        identity = await self.get_identity(context, identity_id)
        updates: dict[str, Any] = {"updated_at": time.time()}
        if request.display_name is not None:
            updates["display_name"] = request.display_name
        if request.status is not None:
            updates["status"] = request.status
        if request.metadata is not None:
            updates["metadata"] = request.metadata
        identity = identity.model_copy(update=updates)
        await self._repository.put_identity(identity)
        await self._audit.record(
            context,
            action="portrait.trajectory.update",
            resource_type="portrait_trajectory",
            resource_id=identity_id,
            evidence={"status": identity.status},
        )
        return identity

    async def delete_identity(self, context: PrincipalContext, identity_id: str) -> None:
        await require_allowed(self._policy, context, "delete", "portrait_trajectory")
        await self.get_identity(context, identity_id)
        await self._audit.record(
            context,
            action="portrait.trajectory.delete",
            resource_type="portrait_trajectory",
            resource_id=identity_id,
            evidence={"biometric_deletion": True},
        )
        await self._features.delete_subject(
            context.tenant_id, context.project_id, SUBJECT_TYPE, identity_id
        )
        await self._repository.delete_segments_for_identity(context.tenant_id, context.project_id, identity_id)
        if not await self._repository.delete_identity(context.tenant_id, context.project_id, identity_id):
            raise TrajectoryConflict("long-term identity changed during deletion")

    async def _move_features(
        self, context: PrincipalContext, segment: TrajectorySegment, target_identity_id: str
    ) -> dict[str, str]:
        """把片段贡献的模板改挂到目标身份，保持向量库与片段归属一致。"""

        moved: dict[str, str] = {}
        for modality, feature_id in segment.feature_ids.items():
            record = await self._features.get_feature(context.tenant_id, context.project_id, feature_id)
            if record is None:
                continue
            created = await self._features.add(
                record.model_copy(
                    update={"feature_id": f"ltf_{uuid4().hex}", "subject_id": target_identity_id}
                )
            )
            await self._features.delete_feature(context.tenant_id, context.project_id, feature_id)
            moved[modality] = created.feature_id
        return moved

    def _recompute(self, identity: LongTermIdentity, segments: list[TrajectorySegment]) -> LongTermIdentity:
        now = time.time()
        if not segments:
            return identity.model_copy(update={"segment_count": 0, "camera_ids": [], "updated_at": now})
        ordered = sorted(segments, key=lambda item: item.last_seen_at)
        camera_ids: list[str] = []
        for segment in ordered:
            if segment.camera_id and segment.camera_id not in camera_ids:
                camera_ids.append(segment.camera_id)
        return identity.model_copy(
            update={
                "segment_count": len(ordered),
                "camera_ids": camera_ids,
                "first_seen_at": min(item.first_seen_at for item in ordered),
                "last_seen_at": ordered[-1].last_seen_at,
                "last_camera_id": ordered[-1].camera_id,
                "updated_at": now,
            }
        )

    async def merge_identities(
        self, context: PrincipalContext, request: MergeIdentitiesRequest
    ) -> LongTermIdentity:
        """人工确认多个身份属于同一人时合并，源身份随之消失。"""

        await require_allowed(self._policy, context, "write", "portrait_trajectory")
        target = await self.get_identity(context, request.target_identity_id)
        sources = [sid for sid in dict.fromkeys(request.source_identity_ids) if sid != target.identity_id]
        if not sources:
            raise TrajectoryConflict("merge requires at least one distinct source identity")
        for source_id in sources:
            source = await self.get_identity(context, source_id)
            segments, _ = await self._repository.list_segments(
                context.tenant_id, context.project_id, identity_id=source_id, limit=1_000
            )
            for segment in segments:
                moved = await self._move_features(context, segment, target.identity_id)
                await self._repository.put_segment(
                    segment.model_copy(
                        update={
                            "identity_id": target.identity_id,
                            "match_method": "manual",
                            "feature_ids": moved,
                        }
                    )
                )
            await self._features.delete_subject(
                context.tenant_id, context.project_id, SUBJECT_TYPE, source_id
            )
            await self._repository.delete_identity(context.tenant_id, context.project_id, source_id)
            target = target.model_copy(
                update={"modalities": sorted(set(target.modalities) | set(source.modalities))}
            )

        segments, _ = await self._repository.list_segments(
            context.tenant_id, context.project_id, identity_id=target.identity_id, limit=1_000
        )
        target = self._recompute(target, segments)
        await self._repository.put_identity(target)
        await self._audit.record(
            context,
            action="portrait.trajectory.merge",
            resource_type="portrait_trajectory",
            resource_id=target.identity_id,
            evidence={"source_identity_ids": sources},
        )
        return target

    async def split_identity(
        self, context: PrincipalContext, identity_id: str, request: SplitIdentityRequest
    ) -> LongTermIdentity:
        """把误并入的片段拆到新身份，纠正 ReID 过合并。"""

        await require_allowed(self._policy, context, "write", "portrait_trajectory")
        identity = await self.get_identity(context, identity_id)
        segments, _ = await self._repository.list_segments(
            context.tenant_id, context.project_id, identity_id=identity_id, limit=1_000
        )
        wanted = set(request.segment_ids)
        moving = [segment for segment in segments if segment.segment_id in wanted]
        if len(moving) != len(wanted):
            raise TrajectoryNotFound("one or more segments do not belong to this identity")
        if len(moving) == len(segments):
            raise TrajectoryConflict("split must leave at least one segment on the source identity")

        now = time.time()
        new_id = f"lti_{uuid4().hex}"
        created = LongTermIdentity(
            identity_id=new_id,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            display_name=request.display_name or new_id,
            status="confirmed",
            modalities=list(identity.modalities),
            feature_space_ids=dict(identity.feature_space_ids),
            first_seen_at=min(item.first_seen_at for item in moving),
            last_seen_at=max(item.last_seen_at for item in moving),
            created_at=now,
            updated_at=now,
        )
        rehomed: list[TrajectorySegment] = []
        for segment in moving:
            moved = await self._move_features(context, segment, new_id)
            updated = segment.model_copy(
                update={"identity_id": new_id, "match_method": "manual", "feature_ids": moved}
            )
            await self._repository.put_segment(updated)
            rehomed.append(updated)

        await self._repository.put_identity(self._recompute(created, rehomed))
        remaining = [segment for segment in segments if segment.segment_id not in wanted]
        await self._repository.put_identity(self._recompute(identity, remaining))
        await self._audit.record(
            context,
            action="portrait.trajectory.split",
            resource_type="portrait_trajectory",
            resource_id=identity_id,
            evidence={"new_identity_id": new_id, "segment_ids": sorted(wanted)},
        )
        return await self.get_identity(context, new_id)


class TrajectoryRegistrar:
    """把 run 结果中的 tracklet 登记为长期轨迹，并回填身份标识。"""

    def __init__(self, service: TrajectoryService, *, enabled: bool = True) -> None:
        self._service = service
        self._enabled = enabled

    async def register_run_result(self, run: Any, result: Any) -> None:
        if not self._enabled:
            return
        domain_payload = getattr(result, "domain_payload", None)
        if domain_payload is None:
            return
        tracks = getattr(domain_payload, "tracks", None)
        if not isinstance(tracks, list) or not tracks:
            return
        raw_tracks = getattr(result, "_trajectory_tracks", None)
        if not isinstance(raw_tracks, list) or not raw_tracks:
            return

        parameters = getattr(run, "parameters", {}) or {}
        camera_id = parameters.get("camera_id")
        recording_started_at = parameters.get("recording_started_at")
        context = PrincipalContext(
            tenant_id=run.tenant_id,
            project_id=run.project_id,
            principal_id=getattr(run, "principal_id", "anonymous"),
        )

        outcomes = await self._service.ingest_run_tracks(
            context,
            run_id=getattr(run, "run_id", ""),
            tracks=raw_tracks,
            source_id=getattr(run, "source_id", "") or "",
            asset_id=getattr(run, "asset_id", "") or "",
            camera_id=str(camera_id) if isinstance(camera_id, str) else "",
            recording_started_at=(
                float(recording_started_at)
                if isinstance(recording_started_at, int | float) and not isinstance(recording_started_at, bool)
                else None
            ),
        )
        # 按 track_id 对位回填，避免部分登记失败时错位；只增字段，保留脱敏结果与非 tracklet 条目。
        by_track = {outcome.track_id: outcome for outcome in outcomes if outcome.track_id}
        for track in tracks:
            if not isinstance(track, dict):
                continue
            outcome = by_track.get(str(track.get("track_id") or ""))
            if outcome is None:
                continue
            if not outcome.registered:
                track["trajectory_skip_reason"] = outcome.skip_reason
                continue
            segment = outcome.segment
            if segment is None:  # pragma: no cover - registered 时必有片段
                continue
            track["long_term_identity_id"] = segment.identity_id
            track["trajectory_segment_id"] = segment.segment_id
            track["trajectory_match_score"] = segment.match_score
            track["trajectory_match_method"] = segment.match_method
            track["trajectory_first_seen_at"] = segment.first_seen_at
            track["trajectory_last_seen_at"] = segment.last_seen_at


__all__ = [
    "CameraRecord",
    "CameraTransition",
    "CameraTransitionEntry",
    "IdentityPage",
    "LongTermIdentity",
    "MemoryTrajectoryRepository",
    "MergeIdentitiesRequest",
    "RegisterCameraRequest",
    "SegmentPage",
    "SetCameraTransitionsRequest",
    "SplitIdentityRequest",
    "TimelineEntry",
    "TrajectoryConflict",
    "TrajectoryError",
    "TrajectoryIngestResult",
    "TrajectoryNotFound",
    "TrajectoryRegistrar",
    "TrajectoryRepository",
    "TrajectorySegment",
    "TrajectoryService",
    "TrajectoryStatus",
    "UpdateCameraRequest",
    "UpdateIdentityRequest",
]
