"""视频与实时流抽帧策略、时间窗口和降采样的回归测试。"""

from __future__ import annotations

import asyncio
import threading
import time
from io import BytesIO
from typing import Any, ClassVar

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from scenara.platform.media_batch import DecodeMediaOperator, MediaInput, SamplePlan, decode_media
from scenara.platform.models import MediaKind, SampleStrategy
from scenara.platform.pipeline import ExecutionContext, ExecutionControl, PipelineError


def _solid_frame(value: int, *, width: int = 32, height: int = 24) -> NDArray[np.uint8]:
    return np.full((height, width, 3), value, dtype=np.uint8)


class _FakeCapture:
    """按固定帧率回放预置帧序列的 OpenCV 替身。"""

    frames: ClassVar[list[NDArray[np.uint8]]] = []
    fps: float = 25.0
    keyframe_every: int = 1
    seek_supported: bool = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        self.position = 0
        self.seeked_to_ms: float | None = None

    def isOpened(self) -> bool:
        return True

    def set(self, field: int, value: float) -> bool:
        if field == cv2.CAP_PROP_POS_MSEC and self.seek_supported:
            self.seeked_to_ms = value
            self.position = int(value / 1000 * self.fps)
            return True
        return False

    def get(self, field: int) -> float:
        if field == cv2.CAP_PROP_FPS:
            return self.fps
        if field == cv2.CAP_PROP_FRAME_COUNT:
            return float(len(self.frames))
        if field == cv2.CAP_PROP_FRAME_WIDTH:
            return float(self.frames[0].shape[1]) if self.frames else 0.0
        if field == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(self.frames[0].shape[0]) if self.frames else 0.0
        if field == cv2.CAP_PROP_POS_MSEC:
            return max(0, self.position - 1) / self.fps * 1000
        if field == cv2.CAP_PROP_POS_FRAMES:
            return float(self.position)
        if field == getattr(cv2, "CAP_PROP_PTS", -1):
            return float(max(0, self.position - 1))
        if field == getattr(cv2, "CAP_PROP_FRAME_TYPE", -1):
            return float(ord("I") if (self.position - 1) % self.keyframe_every == 0 else ord("P"))
        if field == cv2.CAP_PROP_LRF_HAS_KEY_FRAME:
            return 1.0
        return 0.0

    def read(self) -> tuple[bool, NDArray[np.uint8] | None]:
        if self.position >= len(self.frames):
            return False, None
        frame = self.frames[self.position]
        self.position += 1
        return True, frame

    def release(self) -> None:
        return None


@pytest.fixture
def fake_capture(monkeypatch: pytest.MonkeyPatch) -> type[_FakeCapture]:
    monkeypatch.setattr("scenara.platform.media_batch.cv2.VideoCapture", _FakeCapture)
    monkeypatch.setattr("scenara.platform.media_batch.time.sleep", lambda _: None)
    monkeypatch.setattr("scenara.platform.media_batch._sniff_video_container", lambda data, media: "mp4")
    _FakeCapture.frames = []
    _FakeCapture.fps = 25.0
    _FakeCapture.keyframe_every = 1
    _FakeCapture.seek_supported = True
    return _FakeCapture


def _video_media() -> MediaInput:
    return MediaInput(kind=MediaKind.VIDEO, content_type="video/mp4", data=b"fake-video", filename="clip.mp4")


def test_interval_strategy_samples_every_step(fake_capture: type[_FakeCapture]) -> None:
    fake_capture.frames = [_solid_frame(index * 4) for index in range(50)]
    decoded = decode_media(_video_media(), max_units=5, sample_interval_ms=400)
    assert len(decoded.units) == 5
    # 25 fps 下 400 毫秒等于 10 帧步长
    assert [unit.unit_id for unit in decoded.units] == [f"frame_{index * 10}" for index in range(5)]
    assert decoded.metadata.sample_strategy == SampleStrategy.INTERVAL
    assert decoded.metadata.sample_interval_ms == 400
    assert decoded.termination_reason == "max_units_reached"


def test_finite_video_without_unit_limit_runs_to_end_of_file(fake_capture: type[_FakeCapture]) -> None:
    fake_capture.frames = [_solid_frame(index * 4) for index in range(50)]
    decoded = decode_media(_video_media(), max_units=None, sample_interval_ms=400)

    assert [unit.unit_id for unit in decoded.units] == ["frame_0", "frame_10", "frame_20", "frame_30", "frame_40"]
    assert decoded.termination_reason == "source_ended"


def test_stream_without_unit_limit_stops_at_segment_boundary(fake_capture: type[_FakeCapture]) -> None:
    fake_capture.frames = [_solid_frame(index) for index in range(40)]
    decoded = decode_media(
        MediaInput(
            kind=MediaKind.STREAM,
            content_type="application/octet-stream",
            source_url="rtsp://1.1.1.1/live",
        ),
        max_units=None,
        sample_interval_ms=1,
        stream_segment_duration_ms=1_000,
        stream_segment_index=3,
    )

    assert decoded.units
    assert decoded.termination_reason == "segment_window_completed"
    assert decoded.metadata.stream_segment_duration_ms == 1_000
    assert decoded.metadata.stream_segment_index == 3


def test_uniform_strategy_spreads_units_across_the_clip(fake_capture: type[_FakeCapture]) -> None:
    fake_capture.frames = [_solid_frame(index) for index in range(100)]
    decoded = decode_media(
        _video_media(),
        max_units=4,
        sample_interval_ms=1000,
        sample_strategy=SampleStrategy.UNIFORM,
    )
    assert len(decoded.units) == 4
    assert [unit.unit_id for unit in decoded.units] == ["frame_0", "frame_25", "frame_50", "frame_75"]
    assert decoded.metadata.sample_strategy == SampleStrategy.UNIFORM


def test_uniform_strategy_without_unit_limit_processes_the_full_window(
    fake_capture: type[_FakeCapture],
) -> None:
    fake_capture.frames = [_solid_frame(index) for index in range(12)]
    decoded = decode_media(
        _video_media(),
        max_units=None,
        sample_interval_ms=1000,
        sample_strategy=SampleStrategy.UNIFORM,
    )

    assert len(decoded.units) == 12
    assert decoded.termination_reason == "source_ended"


def test_keyframe_strategy_only_keeps_container_keyframes(fake_capture: type[_FakeCapture]) -> None:
    fake_capture.frames = [_solid_frame(index) for index in range(40)]
    fake_capture.keyframe_every = 8
    decoded = decode_media(
        _video_media(),
        max_units=4,
        sample_interval_ms=1000,
        sample_strategy=SampleStrategy.KEYFRAME,
    )
    assert [unit.unit_id for unit in decoded.units] == ["frame_0", "frame_8", "frame_16", "frame_24"]
    assert decoded.metadata.keyframe_count == 4
    assert decoded.metadata.timestamp_source == "position_msec"


def test_keyframe_strategy_rejects_backends_without_decoded_frame_types(
    fake_capture: type[_FakeCapture],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_capture.frames = [_solid_frame(index) for index in range(4)]
    original_get = fake_capture.get

    def get_without_frame_type(self: _FakeCapture, field: int) -> float:
        if field == getattr(cv2, "CAP_PROP_FRAME_TYPE", -1):
            return float(ord("?"))
        return original_get(self, field)

    monkeypatch.setattr(fake_capture, "get", get_without_frame_type)
    with pytest.raises(PipelineError, match="does not expose decoded frame types"):
        decode_media(
            _video_media(),
            max_units=1,
            sample_interval_ms=1000,
            sample_strategy=SampleStrategy.KEYFRAME,
        )


def test_scene_change_strategy_only_keeps_visually_distinct_frames(fake_capture: type[_FakeCapture]) -> None:
    # 三段画面：黑、白、黑；同段内画面完全一致，不应重复采样
    fake_capture.frames = [_solid_frame(0)] * 6 + [_solid_frame(255)] * 6 + [_solid_frame(0)] * 6
    decoded = decode_media(
        _video_media(),
        max_units=8,
        sample_interval_ms=1000,
        sample_strategy=SampleStrategy.SCENE_CHANGE,
        scene_change_threshold=0.5,
    )
    assert [unit.unit_id for unit in decoded.units] == ["frame_0", "frame_6", "frame_12"]
    assert decoded.metadata.scene_change_count == 2
    assert decoded.metadata.sample_strategy == SampleStrategy.SCENE_CHANGE


def test_sample_window_limits_decoding_to_the_requested_range(fake_capture: type[_FakeCapture]) -> None:
    fake_capture.frames = [_solid_frame(index) for index in range(100)]
    decoded = decode_media(
        _video_media(),
        max_units=32,
        sample_interval_ms=400,
        sample_start_ms=1000,
        sample_end_ms=2000,
    )
    assert decoded.termination_reason == "sample_window_completed"
    assert decoded.metadata.sample_start_ms == 1000
    assert decoded.metadata.sample_end_ms == 2000
    assert decoded.metadata.decode_seek_used is True
    assert decoded.units[0].unit_id == "frame_25"
    assert all(unit.pts_ms is not None and 1000 <= unit.pts_ms <= 2000 for unit in decoded.units)


def test_sample_window_without_seek_support_still_skips_leading_frames(
    fake_capture: type[_FakeCapture],
) -> None:
    fake_capture.frames = [_solid_frame(index) for index in range(100)]
    fake_capture.seek_supported = False
    decoded = decode_media(
        _video_media(),
        max_units=3,
        sample_interval_ms=400,
        sample_start_ms=1000,
    )
    assert decoded.metadata.decode_seek_used is False
    assert all(unit.pts_ms is not None and unit.pts_ms >= 1000 for unit in decoded.units)


def test_frame_max_edge_downscales_sampled_frames(fake_capture: type[_FakeCapture]) -> None:
    fake_capture.frames = [_solid_frame(64, width=800, height=600) for _ in range(5)]
    decoded = decode_media(
        _video_media(),
        max_units=2,
        sample_interval_ms=40,
        frame_max_edge=200,
    )
    assert decoded.metadata.frame_max_edge == 200
    assert all(max(unit.width, unit.height) == 200 for unit in decoded.units)
    assert all(unit.width == 200 and unit.height == 150 for unit in decoded.units)


def test_video_batch_is_downscaled_to_the_memory_budget(
    fake_capture: type[_FakeCapture],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_capture.frames = [_solid_frame(64, width=800, height=600) for _ in range(4)]
    monkeypatch.setattr("scenara.platform.media_batch.DECODED_BATCH_MEMORY_BUDGET_BYTES", 360_000)
    decoded = decode_media(
        _video_media(),
        max_units=4,
        sample_interval_ms=40,
    )
    assert decoded.metadata.frame_max_edge == 200
    assert all((unit.width, unit.height) == (200, 150) for unit in decoded.units)


@pytest.mark.asyncio
async def test_decode_operator_streams_video_units_before_materialization(
    fake_capture: type[_FakeCapture],
) -> None:
    fake_capture.frames = [_solid_frame(index * 8) for index in range(20)]
    context = ExecutionContext(
        run_id="run_progressive_decode",
        tenant_id="tenant",
        project_id="project",
        pipeline_id="portrait.person-detection",
        pipeline_version="0.1.0",
        asset_id="asset",
        source_id=None,
        filename="clip.mp4",
        content_type="video/mp4",
    )

    output = await DecodeMediaOperator().execute(
        context,
        {"media": _video_media()},
        {"max_units": 5, "sample_interval_ms": 120},
    )
    decoded = output["batch"]

    assert decoded.stream is not None
    assert decoded.units == []
    batches = []
    async for batch, expected_units in decoded.iter_batches(2):
        batches.append([unit.unit_id for unit in batch])
        assert expected_units == 5

    assert batches == [["frame_0", "frame_3"], ["frame_6", "frame_9"], ["frame_12"]]
    assert decoded.metadata.sampled_units == 5
    assert decoded.termination_reason == "max_units_reached"


def test_image_decoding_honours_frame_max_edge() -> None:
    buffer = BytesIO()
    Image.new("RGB", (1000, 500), "white").save(buffer, format="PNG")
    decoded = decode_media(
        MediaInput(kind=MediaKind.IMAGE, content_type="image/png", data=buffer.getvalue()),
        max_units=1,
        sample_interval_ms=1,
        frame_max_edge=250,
    )
    assert decoded.units[0].width == 250
    assert decoded.units[0].height == 125
    assert decoded.metadata.frame_max_edge == 250


def test_stream_reconnect_count_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = _solid_frame(120)

    class _FlakyCapture:
        created = 0

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs
            self.index = _FlakyCapture.created
            _FlakyCapture.created += 1
            self.reads = 0

        def isOpened(self) -> bool:
            return True

        def set(self, field: int, value: float) -> bool:
            del field, value
            return False

        def get(self, field: int) -> float:
            return 25.0 if field == cv2.CAP_PROP_FPS else 0.0

        def read(self) -> tuple[bool, NDArray[np.uint8] | None]:
            self.reads += 1
            return (True, frame) if self.reads == 1 else (False, None)

        def release(self) -> None:
            return None

    monkeypatch.setattr("scenara.platform.media_batch.cv2.VideoCapture", _FlakyCapture)
    monkeypatch.setattr("scenara.platform.media_batch.time.sleep", lambda _: None)
    decoded = decode_media(
        MediaInput(kind=MediaKind.STREAM, content_type="video/rtsp", source_url="rtsp://example.test/live"),
        max_units=2,
        sample_interval_ms=1,
    )
    assert len(decoded.units) == 2
    assert decoded.metadata.reconnect_count == 1
    assert decoded.metadata.elapsed_ms is not None
    assert decoded.metadata.timestamp_source == "monotonic_clock"
    assert decoded.units[1].pts_ms is not None
    assert decoded.units[0].pts_ms is not None
    assert decoded.units[1].pts_ms > decoded.units[0].pts_ms


def test_stream_allows_an_initial_connection_when_reconnects_are_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _solid_frame(120)

    class _SingleCapture:
        created = 0

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs
            type(self).created += 1
            self.reads = 0

        def isOpened(self) -> bool:
            return True

        def get(self, field: int) -> float:
            return 25.0 if field == cv2.CAP_PROP_FPS else 0.0

        def read(self) -> tuple[bool, NDArray[np.uint8] | None]:
            self.reads += 1
            return (True, frame) if self.reads == 1 else (False, None)

        def release(self) -> None:
            return None

    monkeypatch.setattr("scenara.platform.media_batch.cv2.VideoCapture", _SingleCapture)
    decoded = decode_media(
        MediaInput(kind=MediaKind.STREAM, content_type="video/rtsp", source_url="rtsp://example.test/live"),
        max_units=1,
        sample_interval_ms=1,
        max_reconnect_attempts=0,
    )
    assert len(decoded.units) == 1
    assert decoded.units[0].pts_ms == 0
    assert _SingleCapture.created == 1


@pytest.mark.asyncio
async def test_decode_control_pauses_and_cancels_stream_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = _solid_frame(90)

    class _ControlledCapture:
        reads = 0
        released = threading.Event()

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

        def isOpened(self) -> bool:
            return True

        def get(self, field: int) -> float:
            return 25.0 if field == cv2.CAP_PROP_FPS else 0.0

        def read(self) -> tuple[bool, NDArray[np.uint8]]:
            type(self).reads += 1
            time.sleep(0.005)
            return True, frame

        def release(self) -> None:
            type(self).released.set()

    monkeypatch.setattr("scenara.platform.media_batch.cv2.VideoCapture", _ControlledCapture)
    control = ExecutionControl()
    task = asyncio.create_task(
        asyncio.to_thread(
            decode_media,
            MediaInput(kind=MediaKind.STREAM, content_type="video/rtsp", source_url="rtsp://example.test/live"),
            max_units=10_000,
            sample_interval_ms=1000,
            control=control,
        )
    )
    async with asyncio.timeout(1):
        while _ControlledCapture.reads < 3:
            await asyncio.sleep(0.005)

    control.pause()
    await asyncio.sleep(0.03)
    reads_while_paused = _ControlledCapture.reads
    await asyncio.sleep(0.05)
    assert _ControlledCapture.reads == reads_while_paused

    control.resume()
    async with asyncio.timeout(1):
        while _ControlledCapture.reads == reads_while_paused:
            await asyncio.sleep(0.005)
    control.cancel()
    with pytest.raises(PipelineError, match="cancelled"):
        await asyncio.wait_for(task, timeout=1)
    assert _ControlledCapture.released.is_set()


def test_unsupported_sample_strategy_is_rejected(fake_capture: type[_FakeCapture]) -> None:
    fake_capture.frames = [_solid_frame(1)]
    with pytest.raises(PipelineError, match="unsupported sample_strategy"):
        decode_media(_video_media(), max_units=1, sample_interval_ms=1000, sample_strategy="every-other-frame")


def test_sample_plan_rejects_inverted_time_windows() -> None:
    with pytest.raises(PipelineError, match="sample_end_ms must be greater"):
        SamplePlan(start_ms=5000, end_ms=1000).validate()


def test_sample_plan_rejects_out_of_range_scene_threshold() -> None:
    with pytest.raises(PipelineError, match="scene_change_threshold"):
        SamplePlan(scene_change_threshold=1.5).validate()


def test_sample_plan_rejects_out_of_range_frame_max_edge() -> None:
    with pytest.raises(PipelineError, match="frame_max_edge"):
        SamplePlan(frame_max_edge=16).validate()
