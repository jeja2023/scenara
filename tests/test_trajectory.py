from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, ClassVar

import cv2
import httpx
import numpy as np
import pytest

from app.tracking_association import associate_person_tracks
from scenara.bootstrap import build_runtime
from scenara.domains.portrait.analysis import PORTRAIT_CAPABILITIES, PortraitBackendOutput
from scenara.domains.portrait.trajectory import (
    CameraTransitionEntry,
    MemoryTrajectoryRepository,
    MergeIdentitiesRequest,
    RegisterCameraRequest,
    SetCameraTransitionsRequest,
    SplitIdentityRequest,
    TrajectoryConflict,
    TrajectoryRegistrar,
    TrajectoryService,
    UpdateIdentityRequest,
)
from scenara.infrastructure.memory_state import MemoryStateStore
from scenara.platform.audit import AuditLogger
from scenara.platform.features import MemoryFeatureStore
from scenara.platform.models import PrincipalContext
from scenara.platform.policy import DevelopmentPolicyProvider
from scenara.server import create_app

CONTEXT = PrincipalContext(tenant_id="tenant", project_id="project", principal_id="test")


def _sample_video() -> bytes:
    path = ""
    try:
        with NamedTemporaryFile(delete=False, suffix=".avi") as handle:
            path = handle.name
        writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (64, 48))
        assert writer.isOpened()
        for index in range(10):
            writer.write(np.full((48, 64, 3), index * 20, dtype=np.uint8))
        writer.release()
        return Path(path).read_bytes()
    finally:
        if path:
            Path(path).unlink(missing_ok=True)


class _CrossVideoPortraitBackend:
    def production_capabilities(self) -> frozenset[str]:
        return PORTRAIT_CAPABILITIES

    async def analyze(
        self,
        images: list[Any],
        filenames: list[str | None],
        capabilities: frozenset[str],
    ) -> PortraitBackendOutput:
        del filenames, capabilities
        units = [
            {
                "persons": [{"box": [4, 4, 40, 44], "score": 0.95, "track_id": "trk_0001"}],
                "faces": [],
                "silhouettes": [],
            }
            for _ in images
        ]
        raw_track = {
            "track_id": "trk_0001",
            "frame_count": len(images),
            "first_frame_index": 0,
            "last_frame_index": len(images) - 1,
            "tracklet_quality_score": 0.95,
            "template": {"embedding": [1.0, 0.0, 0.0]},
        }
        return PortraitBackendOutput(
            units=units,
            tracks=[
                {
                    "track_id": "trk_0001",
                    "frame_count": len(images),
                    "tracklet_quality_score": 0.95,
                }
            ],
            trajectory_tracks=[raw_track],
        )


async def _service(**overrides) -> TrajectoryService:
    state = MemoryStateStore()
    await state.open()
    return TrajectoryService(
        MemoryTrajectoryRepository(),
        MemoryFeatureStore(),
        DevelopmentPolicyProvider(),
        AuditLogger(state),
        **overrides,
    )


def _track(
    track_id: str,
    body: list[float] | None = None,
    *,
    face: list[float] | None = None,
    first_pts_ms: float = 0.0,
    last_pts_ms: float = 4_000.0,
    quality: float = 0.9,
    frame_count: int = 5,
) -> dict:
    track: dict = {
        "track_id": track_id,
        "frame_count": frame_count,
        "tracklet_quality_score": quality,
        "first_pts_ms": first_pts_ms,
        "last_pts_ms": last_pts_ms,
    }
    if body is not None:
        track["template"] = {"embedding": body}
    if face is not None:
        track["face_template"] = {"embedding": face}
    return track


# ---------------------------------------------------------------------------
# 视频内串联
# ---------------------------------------------------------------------------


def test_tracking_uses_embedding_to_reconnect_a_fragment() -> None:
    frames = [
        {"frame_index": 0, "persons": [{"box": [0, 0, 10, 20], "score": 0.95, "_tracking_embedding": [1.0, 0.0]}]},
        {"frame_index": 1, "persons": [{"box": [1, 0, 11, 20], "score": 0.95, "_tracking_embedding": [1.0, 0.0]}]},
        {"frame_index": 5, "persons": [{"box": [80, 0, 90, 20], "score": 0.95, "_tracking_embedding": [1.0, 0.0]}]},
    ]
    result = associate_person_tracks(frames, max_age=1, max_fragment_merge_gap=5, include_template_embeddings=True)
    assert result["track_count"] == 1
    assert [person["track_id"] for frame in frames for person in frame["persons"]] == ["trk_0001"] * 3
    assert result["tracks"][0]["template"]["embedding"]


def test_tracking_aggregates_a_face_template_alongside_the_body_template() -> None:
    frames = [
        {
            "frame_index": index,
            "persons": [
                {
                    "box": [index, 0, 10 + index, 20],
                    "score": 0.95,
                    "_tracking_embedding": [1.0, 0.0],
                    "_face_embedding": [0.0, 1.0],
                }
            ],
        }
        for index in range(3)
    ]
    result = associate_person_tracks(frames, include_template_embeddings=True)
    track = result["tracks"][0]
    assert track["template"]["embedding"]
    assert track["face_template"]["embedding"]
    # 私有向量不得泄漏回帧内检测结果。
    assert all("_face_embedding" not in person for frame in frames for person in frame["persons"])


# ---------------------------------------------------------------------------
# 归并、时间轴与时空约束
# ---------------------------------------------------------------------------


def test_long_term_trajectory_reid_links_two_runs() -> None:
    async def scenario() -> None:
        service = await _service()
        first = await service.ingest_run_tracks(
            CONTEXT, run_id="run-a", tracks=[_track("trk_1", [1.0, 0.0, 0.0])], camera_id="camera-a"
        )
        second = await service.ingest_run_tracks(
            CONTEXT, run_id="run-b", tracks=[_track("trk_2", [0.99, 0.01, 0.0])], camera_id="camera-b"
        )
        assert first[0].created_identity is True
        assert second[0].created_identity is False
        assert first[0].identity.identity_id == second[0].identity.identity_id
        assert second[0].segment.match_method == "reid"
        page = await service.list_segments(CONTEXT, first[0].identity.identity_id)
        assert page.total == 2

    asyncio.run(scenario())


def test_segment_times_come_from_frame_timestamps_not_ingest_time() -> None:
    async def scenario() -> None:
        service = await _service()
        results = await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-a",
            tracks=[_track("trk_1", [1.0, 0.0], first_pts_ms=2_000, last_pts_ms=8_000)],
            camera_id="camera-a",
            recording_started_at=1_000.0,
        )
        segment = results[0].segment
        assert segment.first_seen_at == 1_002.0
        assert segment.last_seen_at == 1_008.0
        assert segment.first_seen_at != segment.last_seen_at

    asyncio.run(scenario())


def test_overlapping_tracks_in_one_run_never_share_an_identity() -> None:
    async def scenario() -> None:
        service = await _service()
        results = await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-a",
            tracks=[
                _track("trk_1", [1.0, 0.0], first_pts_ms=0, last_pts_ms=4_000),
                _track("trk_2", [0.999, 0.001], first_pts_ms=1_000, last_pts_ms=5_000),
            ],
            camera_id="camera-a",
            recording_started_at=1_000.0,
        )
        assert all(item.registered for item in results)
        assert results[0].segment.identity_id != results[1].segment.identity_id

    asyncio.run(scenario())


def test_camera_transition_time_blocks_a_physically_impossible_match() -> None:
    async def scenario() -> None:
        service = await _service()
        await service.set_camera_transitions(
            CONTEXT,
            "camera-a",
            SetCameraTransitionsRequest(
                transitions=[CameraTransitionEntry(to_camera_id="camera-b", min_seconds=600)]
            ),
        )
        first = await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-a",
            tracks=[_track("trk_1", [1.0, 0.0], first_pts_ms=0, last_pts_ms=1_000)],
            camera_id="camera-a",
            recording_started_at=1_000.0,
        )
        # 仅隔 10 秒就出现在 B 机位，物理上不可达，必须另立身份。
        blocked = await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-b",
            tracks=[_track("trk_2", [1.0, 0.0], first_pts_ms=0, last_pts_ms=1_000)],
            camera_id="camera-b",
            recording_started_at=1_011.0,
        )
        assert blocked[0].segment.identity_id != first[0].segment.identity_id

    asyncio.run(scenario())


def test_camera_transition_allows_a_reachable_gap() -> None:
    async def scenario() -> None:
        service = await _service()
        await service.set_camera_transitions(
            CONTEXT,
            "camera-a",
            SetCameraTransitionsRequest(
                transitions=[CameraTransitionEntry(to_camera_id="camera-b", min_seconds=600)]
            ),
        )
        first = await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-a",
            tracks=[_track("trk_1", [1.0, 0.0], first_pts_ms=0, last_pts_ms=1_000)],
            camera_id="camera-a",
            recording_started_at=1_000.0,
        )
        allowed = await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-c",
            tracks=[_track("trk_3", [1.0, 0.0], first_pts_ms=0, last_pts_ms=1_000)],
            camera_id="camera-b",
            recording_started_at=5_000.0,
        )
        assert allowed[0].segment.identity_id == first[0].segment.identity_id

    asyncio.run(scenario())


def test_camera_transition_maximum_blocks_an_implausibly_late_match() -> None:
    async def scenario() -> None:
        service = await _service()
        await service.set_camera_transitions(
            CONTEXT,
            "camera-a",
            SetCameraTransitionsRequest(
                transitions=[CameraTransitionEntry(to_camera_id="camera-b", min_seconds=10, max_seconds=60)]
            ),
        )
        first = await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-a",
            tracks=[_track("trk_1", [1.0, 0.0], first_pts_ms=0, last_pts_ms=1_000)],
            camera_id="camera-a",
            recording_started_at=1_000.0,
        )
        too_late = await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-b",
            tracks=[_track("trk_2", [1.0, 0.0], first_pts_ms=0, last_pts_ms=1_000)],
            camera_id="camera-b",
            recording_started_at=1_120.0,
        )
        assert too_late[0].segment.identity_id != first[0].segment.identity_id

    asyncio.run(scenario())


def test_face_evidence_outranks_body_only_similarity() -> None:
    async def scenario() -> None:
        service = await _service()
        await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-a",
            tracks=[_track("trk_1", [1.0, 0.0], face=[1.0, 0.0])],
            camera_id="camera-a",
        )
        matched = await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-b",
            tracks=[_track("trk_2", [1.0, 0.0], face=[0.999, 0.001])],
            camera_id="camera-b",
        )
        assert matched[0].created_identity is False
        assert set(matched[0].segment.match_scores) == {"body", "face"}
        assert "face" in matched[0].identity.modalities

    asyncio.run(scenario())


def test_body_only_tracks_still_associate_when_no_face_is_available() -> None:
    async def scenario() -> None:
        service = await _service()
        await service.ingest_run_tracks(CONTEXT, run_id="run-a", tracks=[_track("trk_1", [1.0, 0.0])])
        matched = await service.ingest_run_tracks(CONTEXT, run_id="run-b", tracks=[_track("trk_2", [1.0, 0.0])])
        assert matched[0].created_identity is False
        assert set(matched[0].segment.match_scores) == {"body"}

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# 质量门禁与模板上限
# ---------------------------------------------------------------------------


def test_low_quality_and_short_tracks_are_skipped_with_a_reason() -> None:
    async def scenario() -> None:
        service = await _service()
        results = await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-a",
            tracks=[
                _track("low", [1.0, 0.0], quality=0.10),
                _track("short", [0.0, 1.0], frame_count=1),
                _track("blind", None),
                _track("good", [0.5, 0.5]),
            ],
        )
        outcomes = {item.track_id: item for item in results}
        assert outcomes["low"].skip_reason == "low_quality"
        assert outcomes["short"].skip_reason == "too_few_frames"
        assert outcomes["blind"].skip_reason == "missing_embedding"
        assert outcomes["good"].registered is True

    asyncio.run(scenario())


def test_template_count_is_capped_and_drops_the_weakest_observation() -> None:
    async def scenario() -> None:
        service = await _service(max_templates=3)
        identity_id = ""
        for index in range(6):
            results = await service.ingest_run_tracks(
                CONTEXT,
                run_id=f"run-{index}",
                tracks=[_track(f"trk_{index}", [1.0, 0.0], quality=0.4 + index * 0.05)],
                camera_id="camera-a",
                recording_started_at=1_000.0 + index * 10_000,
            )
            identity_id = results[0].segment.identity_id
        space_id = "portrait.trajectory.body.2.v1"
        stored = await service._features.list_subject_features(
            CONTEXT.tenant_id, CONTEXT.project_id, space_id, "portrait_long_term_identity", identity_id
        )
        assert len(stored) == 3

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# 人工研判闭环
# ---------------------------------------------------------------------------


def test_identity_can_be_confirmed_renamed_and_deleted() -> None:
    async def scenario() -> None:
        service = await _service()
        created = await service.ingest_run_tracks(CONTEXT, run_id="run-a", tracks=[_track("trk_1", [1.0, 0.0])])
        identity_id = created[0].segment.identity_id

        updated = await service.update_identity(
            CONTEXT, identity_id, UpdateIdentityRequest(display_name="张三", status="confirmed")
        )
        assert updated.display_name == "张三"
        assert updated.status == "confirmed"

        await service.delete_identity(CONTEXT, identity_id)
        page = await service.list_identities(CONTEXT)
        assert page.total == 0
        stored = await service._features.list_subject_features(
            CONTEXT.tenant_id,
            CONTEXT.project_id,
            "portrait.trajectory.body.2.v1",
            "portrait_long_term_identity",
            identity_id,
        )
        assert stored == []

    asyncio.run(scenario())


def test_rejected_identities_are_never_reused_for_new_matches() -> None:
    async def scenario() -> None:
        service = await _service()
        created = await service.ingest_run_tracks(CONTEXT, run_id="run-a", tracks=[_track("trk_1", [1.0, 0.0])])
        identity_id = created[0].segment.identity_id
        await service.update_identity(CONTEXT, identity_id, UpdateIdentityRequest(status="rejected"))
        again = await service.ingest_run_tracks(CONTEXT, run_id="run-b", tracks=[_track("trk_2", [1.0, 0.0])])
        assert again[0].segment.identity_id != identity_id

    asyncio.run(scenario())


def test_merge_moves_segments_and_removes_the_source_identity() -> None:
    async def scenario() -> None:
        service = await _service()
        left = await service.ingest_run_tracks(CONTEXT, run_id="run-a", tracks=[_track("trk_1", [1.0, 0.0])])
        right = await service.ingest_run_tracks(CONTEXT, run_id="run-b", tracks=[_track("trk_2", [0.0, 1.0])])
        target_id = left[0].segment.identity_id
        source_id = right[0].segment.identity_id
        assert target_id != source_id

        merged = await service.merge_identities(
            CONTEXT, MergeIdentitiesRequest(target_identity_id=target_id, source_identity_ids=[source_id])
        )
        assert merged.segment_count == 2
        page = await service.list_identities(CONTEXT)
        assert [item.identity_id for item in page.items] == [target_id]
        segments = await service.list_segments(CONTEXT, target_id)
        assert {item.match_method for item in segments.items} == {"new_identity", "manual"}

    asyncio.run(scenario())


def test_split_extracts_segments_into_a_new_identity() -> None:
    async def scenario() -> None:
        service = await _service()
        first = await service.ingest_run_tracks(
            CONTEXT, run_id="run-a", tracks=[_track("trk_1", [1.0, 0.0])], camera_id="camera-a"
        )
        identity_id = first[0].segment.identity_id
        second = await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-b",
            tracks=[_track("trk_2", [1.0, 0.0])],
            camera_id="camera-b",
            recording_started_at=9_000.0,
        )
        assert second[0].segment.identity_id == identity_id

        created = await service.split_identity(
            CONTEXT,
            identity_id,
            SplitIdentityRequest(segment_ids=[second[0].segment.segment_id], display_name="李四"),
        )
        assert created.identity_id != identity_id
        assert created.display_name == "李四"
        assert created.segment_count == 1
        remaining = await service.list_segments(CONTEXT, identity_id)
        assert remaining.total == 1

    asyncio.run(scenario())


def test_split_refuses_to_empty_the_source_identity() -> None:
    async def scenario() -> None:
        service = await _service()
        created = await service.ingest_run_tracks(CONTEXT, run_id="run-a", tracks=[_track("trk_1", [1.0, 0.0])])
        segment_id = created[0].segment.segment_id
        with pytest.raises(TrajectoryConflict):
            await service.split_identity(
                CONTEXT, created[0].segment.identity_id, SplitIdentityRequest(segment_ids=[segment_id])
            )

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# 时间线、摄像头与查询
# ---------------------------------------------------------------------------


def test_timeline_orders_appearances_and_reports_transition_gaps() -> None:
    async def scenario() -> None:
        service = await _service()
        first = await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-a",
            tracks=[_track("trk_1", [1.0, 0.0], first_pts_ms=0, last_pts_ms=1_000)],
            camera_id="camera-a",
            recording_started_at=1_000.0,
        )
        await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-b",
            tracks=[_track("trk_2", [1.0, 0.0], first_pts_ms=0, last_pts_ms=1_000)],
            camera_id="camera-b",
            recording_started_at=2_000.0,
        )
        entries = await service.timeline(CONTEXT, first[0].segment.identity_id)
        assert [entry.camera_id for entry in entries] == ["camera-a", "camera-b"]
        assert entries[0].transition_seconds is None
        assert entries[1].transition_seconds == 999.0

    asyncio.run(scenario())


def test_cameras_are_auto_registered_and_can_be_curated() -> None:
    async def scenario() -> None:
        service = await _service()
        await service.ingest_run_tracks(
            CONTEXT, run_id="run-a", tracks=[_track("trk_1", [1.0, 0.0])], camera_id="lobby"
        )
        cameras = await service.list_cameras(CONTEXT)
        assert [camera.camera_id for camera in cameras] == ["lobby"]
        assert cameras[0].auto_registered is True

        curated = await service.register_camera(
            CONTEXT, RegisterCameraRequest(camera_id="lobby", display_name="一楼大堂", location="A 座")
        )
        assert curated.display_name == "一楼大堂"
        assert curated.auto_registered is False

    asyncio.run(scenario())


def test_identity_listing_supports_status_camera_and_time_filters() -> None:
    async def scenario() -> None:
        service = await _service()
        first = await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-a",
            tracks=[_track("trk_1", [1.0, 0.0], first_pts_ms=0, last_pts_ms=1_000)],
            camera_id="camera-a",
            recording_started_at=1_000.0,
        )
        await service.ingest_run_tracks(
            CONTEXT,
            run_id="run-b",
            tracks=[_track("trk_2", [0.0, 1.0], first_pts_ms=0, last_pts_ms=1_000)],
            camera_id="camera-b",
            recording_started_at=50_000.0,
        )
        await service.update_identity(
            CONTEXT, first[0].segment.identity_id, UpdateIdentityRequest(status="confirmed")
        )

        assert (await service.list_identities(CONTEXT)).total == 2
        assert (await service.list_identities(CONTEXT, status="confirmed")).total == 1
        assert (await service.list_identities(CONTEXT, camera_id="camera-b")).total == 1
        assert (await service.list_identities(CONTEXT, since=40_000.0)).total == 1
        assert (await service.list_identities(CONTEXT, until=2_000.0)).total == 1
        page = await service.list_identities(CONTEXT, offset=1, limit=1)
        assert len(page.items) == 1 and page.total == 2

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# 结果回填
# ---------------------------------------------------------------------------


class _Run:
    run_id = "run-a"
    tenant_id = CONTEXT.tenant_id
    project_id = CONTEXT.project_id
    principal_id = "test"
    source_id = "source-a"
    asset_id = "asset-a"
    parameters: ClassVar[dict[str, object]] = {"camera_id": "camera-a", "recording_started_at": 1_000.0}


class _Payload:
    def __init__(self, tracks: list[dict]) -> None:
        self.tracks = tracks


class _Result:
    def __init__(self, tracks: list[dict], raw: list[dict]) -> None:
        self.domain_payload = _Payload(tracks)
        self._trajectory_tracks = raw


def test_registrar_backfills_by_track_id_without_leaking_embeddings() -> None:
    async def scenario() -> None:
        service = await _service()
        registrar = TrajectoryRegistrar(service)
        # 中间一条没有向量，登记会跳过；两侧的身份标识必须仍然各归其位。
        raw = [
            _track("trk_1", [1.0, 0.0]),
            _track("trk_2", None),
            _track("trk_3", [0.0, 1.0]),
        ]
        sanitized = [
            {"track_id": "trk_1", "frame_count": 5},
            {"track_id": "trk_2", "frame_count": 5},
            {"track_id": "trk_3", "frame_count": 5},
            {"track_id": "gait_sequence_0", "gait": {"embedding_available": True}},
        ]
        await registrar.register_run_result(_Run(), _Result(sanitized, raw))

        assert sanitized[0]["long_term_identity_id"] != sanitized[2]["long_term_identity_id"]
        assert sanitized[1]["trajectory_skip_reason"] == "missing_embedding"
        assert "long_term_identity_id" not in sanitized[1]
        # 非 tracklet 条目必须原样保留。
        assert sanitized[3] == {"track_id": "gait_sequence_0", "gait": {"embedding_available": True}}
        # 脱敏结果里不允许出现任何向量。
        assert all("template" not in track and "embedding" not in track for track in sanitized)

    asyncio.run(scenario())


def test_registrar_records_real_observation_times_from_run_parameters() -> None:
    async def scenario() -> None:
        service = await _service()
        registrar = TrajectoryRegistrar(service)
        sanitized = [{"track_id": "trk_1"}]
        await registrar.register_run_result(
            _Run(), _Result(sanitized, [_track("trk_1", [1.0, 0.0], first_pts_ms=2_000, last_pts_ms=6_000)])
        )
        assert sanitized[0]["trajectory_first_seen_at"] == 1_002.0
        assert sanitized[0]["trajectory_last_seen_at"] == 1_006.0

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_video_runs_form_one_long_term_trajectory(development_settings) -> None:
    runtime = build_runtime(development_settings, portrait_backend=_CrossVideoPortraitBackend())
    app = create_app(runtime=runtime)
    video = _sample_video()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        asset_ids: list[str] = []
        for index in range(2):
            uploaded = await api.post(
                "/api/v1/media/assets",
                files={"file": (f"camera-{index}.avi", video, "video/x-msvideo")},
                data={"kind": "video"},
            )
            assert uploaded.status_code == 201, uploaded.text
            asset_ids.append(uploaded.json()["data"]["asset_id"])

        results: list[dict[str, Any]] = []
        run_ids: list[str] = []
        for index, asset_id in enumerate(asset_ids):
            created = await api.post(
                "/api/v1/runs",
                json={
                    "domain": "portrait",
                    "pipeline": {"pipeline_id": "portrait.analysis", "version": "0.4.0"},
                    "asset_id": asset_id,
                    "parameters": {
                        "capabilities": ["person_detection", "body_reid", "tracking"],
                        "camera_id": f"camera-{index}",
                        "recording_started_at": 1_000.0 + index * 1_000.0,
                        "sample_interval_ms": 200,
                        "max_units": 10,
                    },
                    "wait_ms": 5_000,
                },
                headers={"Idempotency-Key": f"cross-video-run-{index}"},
            )
            assert created.status_code == 202, created.text
            run = created.json()["data"]
            assert run["status"] == "completed", created.text
            run_ids.append(run["run_id"])

            response = await api.get(f"/api/v1/runs/{run['run_id']}/result")
            assert response.status_code == 200, response.text
            results.append(response.json()["data"]["result"])

        first_track = results[0]["domain_payload"]["tracks"][0]
        second_track = results[1]["domain_payload"]["tracks"][0]
        assert first_track["long_term_identity_id"] == second_track["long_term_identity_id"]
        assert first_track["trajectory_match_method"] == "new_identity"
        assert second_track["trajectory_match_method"] == "reid"
        assert "embedding" not in str(results)

        identities = await api.get("/api/v1/portrait/trajectories/identities")
        assert identities.status_code == 200, identities.text
        identity_page = identities.json()["data"]
        assert identity_page["total"] == 1
        identity = identity_page["items"][0]
        assert set(identity["camera_ids"]) == {"camera-0", "camera-1"}
        assert identity["segment_count"] == 2

        segments = await api.get(
            f"/api/v1/portrait/trajectories/identities/{identity['identity_id']}/segments"
        )
        assert segments.status_code == 200, segments.text
        segment_page = segments.json()["data"]
        assert segment_page["total"] == 2
        assert {item["run_id"] for item in segment_page["items"]} == set(run_ids)
        assert {item["camera_id"] for item in segment_page["items"]} == {"camera-0", "camera-1"}


@pytest.mark.asyncio
async def test_parse_video_shortcut_carries_trajectory_metadata(development_settings) -> None:
    runtime = build_runtime(development_settings, portrait_backend=_CrossVideoPortraitBackend())
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        response = await api.post(
            "/api/v1/parse/video",
            files={"file": ("shortcut.avi", _sample_video(), "video/x-msvideo")},
            data={
                "domain": "portrait",
                "pipeline_id": "portrait.analysis",
                "pipeline_version": "0.4.0",
                "sample_interval_ms": "200",
                "max_units": "10",
                "camera_id": "camera-shortcut",
                "recording_started_at": "1700000000.25",
                "wait_ms": "5000",
            },
            headers={"Idempotency-Key": "trajectory-shortcut"},
        )
        assert response.status_code == 202, response.text
        payload = response.json()["data"]
        assert payload["run"]["status"] == "completed", response.text
        assert payload["run"]["parameters"]["camera_id"] == "camera-shortcut"
        assert payload["run"]["parameters"]["recording_started_at"] == 1_700_000_000.25
        assert payload["result"]["domain_payload"]["tracks"][0]["trajectory_match_method"] == "new_identity"


def test_trajectory_api_exposes_query_and_adjudication(development_settings) -> None:
    async def scenario() -> None:
        runtime = build_runtime(development_settings)
        app = create_app(runtime=runtime)
        context = PrincipalContext(tenant_id="default", project_id="default", principal_id="test")
        first = await runtime.trajectory.ingest_run_tracks(
            context,
            run_id="run-api",
            tracks=[_track("trk_api", [1.0, 0.0], first_pts_ms=0, last_pts_ms=2_000)],
            source_id="source-api",
            asset_id="asset-api",
            camera_id="camera-api",
            recording_started_at=1_000.0,
        )
        identity_id = first[0].segment.identity_id

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
            listing = await api.get("/api/v1/portrait/trajectories/identities")
            assert listing.status_code == 200
            assert listing.json()["data"]["total"] == 1

            detail = await api.get(f"/api/v1/portrait/trajectories/identities/{identity_id}")
            assert detail.status_code == 200

            segments = await api.get(f"/api/v1/portrait/trajectories/identities/{identity_id}/segments")
            assert segments.json()["data"]["items"][0]["run_id"] == "run-api"

            timeline = await api.get(f"/api/v1/portrait/trajectories/identities/{identity_id}/timeline")
            assert timeline.json()["data"][0]["camera_id"] == "camera-api"

            patched = await api.patch(
                f"/api/v1/portrait/trajectories/identities/{identity_id}",
                json={"status": "confirmed", "display_name": "王五"},
            )
            assert patched.json()["data"]["status"] == "confirmed"

            cameras = await api.get("/api/v1/portrait/cameras")
            assert cameras.json()["data"][0]["camera_id"] == "camera-api"

            transitions = await api.put(
                "/api/v1/portrait/cameras/camera-api/transitions",
                json={"transitions": [{"to_camera_id": "camera-b", "min_seconds": 120}]},
            )
            assert transitions.json()["data"][0]["min_seconds"] == 120

            missing = await api.get("/api/v1/portrait/trajectories/identities/lti_missing")
            assert missing.status_code == 404

            removed = await api.delete(f"/api/v1/portrait/trajectories/identities/{identity_id}")
            assert removed.status_code == 204
            assert (await api.get("/api/v1/portrait/trajectories/identities")).json()["data"]["total"] == 0

    asyncio.run(scenario())
