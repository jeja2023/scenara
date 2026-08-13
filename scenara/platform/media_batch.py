from __future__ import annotations

import asyncio
import contextlib
import math
import os
import queue
import tempfile
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Literal

import cv2
from PIL import Image, ImageOps, UnidentifiedImageError

from scenara.platform.models import MediaKind, MediaTechnicalMetadata, SampleStrategy
from scenara.platform.pipeline import ExecutionContext, ExecutionControl, OperatorDefinition, PipelineError

MAX_PIXELS = 80_000_000
SCENE_CHANGE_HISTOGRAM_BINS = 32
DECODED_BATCH_MEMORY_BUDGET_BYTES = 512 * 1024 * 1024
DECODED_QUEUE_CAPACITY_UNITS = 32
RGB_BYTES_PER_PIXEL = 3


@dataclass(slots=True)
class MediaInput:
    kind: MediaKind
    content_type: str
    data: bytes | None = None
    source_url: str | None = None
    file_path: str | None = None
    filename: str | None = None


@dataclass(frozen=True, slots=True)
class SamplePlan:
    """描述一次视频或实时流解码的抽帧计划。"""

    strategy: SampleStrategy = SampleStrategy.INTERVAL
    sample_interval_ms: int = 1000
    start_ms: int = 0
    end_ms: int | None = None
    stream_segment_duration_ms: int | None = None
    stream_segment_index: int | None = None
    scene_change_threshold: float = 0.35
    frame_max_edge: int | None = None

    def validate(self) -> None:
        if not 1 <= self.sample_interval_ms <= 3_600_000:
            raise PipelineError("sample_interval_ms is outside the supported range")
        if self.start_ms < 0:
            raise PipelineError("sample_start_ms must not be negative")
        if self.end_ms is not None:
            if self.end_ms < 0:
                raise PipelineError("sample_end_ms must not be negative")
            if self.end_ms <= self.start_ms:
                raise PipelineError("sample_end_ms must be greater than sample_start_ms")
        if self.stream_segment_duration_ms is not None and not 1_000 <= self.stream_segment_duration_ms <= 86_400_000:
            raise PipelineError("stream_segment_duration_ms must be between 1000 and 86400000")
        if self.stream_segment_index is not None and self.stream_segment_index < 0:
            raise PipelineError("stream_segment_index must not be negative")
        if not 0.0 < self.scene_change_threshold <= 1.0:
            raise PipelineError("scene_change_threshold must be between 0 and 1")
        if self.frame_max_edge is not None and not 64 <= self.frame_max_edge <= 8192:
            raise PipelineError("frame_max_edge must be between 64 and 8192")


@dataclass(slots=True)
class DecodedMediaUnit:
    unit_id: str
    unit_type: Literal["frame", "page"]
    index: int
    image: Image.Image
    pts_ms: int | None = None
    page_number: int | None = None

    @property
    def width(self) -> int:
        return self.image.width

    @property
    def height(self) -> int:
        return self.image.height


_PROGRESSIVE_MEDIA_END = object()


class ProgressiveMediaStream:
    def __init__(
        self,
        producer: Callable[[Callable[[DecodedMediaUnit, int | None], None]], DecodedMedia],
        control: ExecutionControl,
        *,
        queue_size: int = 32,
    ) -> None:
        self._control = control
        self._queue: queue.Queue[tuple[DecodedMediaUnit, int | None] | object] = queue.Queue(maxsize=queue_size)
        self._task = asyncio.create_task(asyncio.to_thread(self._produce, producer))

    def _produce(
        self,
        producer: Callable[[Callable[[DecodedMediaUnit, int | None], None]], DecodedMedia],
    ) -> DecodedMedia:
        try:
            return producer(self._emit)
        finally:
            while True:
                try:
                    self._queue.put(_PROGRESSIVE_MEDIA_END, timeout=0.1)
                    break
                except queue.Full:
                    if self._control.cancelled:
                        with contextlib.suppress(queue.Empty):
                            self._queue.get_nowait()

    def _emit(self, unit: DecodedMediaUnit, expected_units: int | None) -> None:
        while True:
            try:
                self._queue.put((unit, expected_units), timeout=0.1)
                return
            except queue.Full:
                if self._control.cancelled:
                    raise PipelineError("media decoding cancelled") from None

    async def batches(self, batch_size: int) -> AsyncIterator[tuple[list[DecodedMediaUnit], int | None]]:
        batch: list[DecodedMediaUnit] = []
        expected_units: int | None = None
        while True:
            item = await asyncio.to_thread(self._queue.get)
            if item is _PROGRESSIVE_MEDIA_END:
                if batch:
                    yield batch, expected_units
                return
            if not isinstance(item, tuple):
                raise PipelineError("progressive media queue returned an invalid item")
            unit, expected_units = item
            batch.append(unit)
            if len(batch) >= batch_size:
                yield batch, expected_units
                batch = []

    async def result(self) -> DecodedMedia:
        return await self._task

    async def close(self) -> None:
        if self._task.done():
            with contextlib.suppress(BaseException):
                await self._task
            return
        self._control.cancel()
        with contextlib.suppress(BaseException):
            await self._task


@dataclass(slots=True)
class DecodedMedia:
    kind: MediaKind
    units: list[DecodedMediaUnit]
    metadata: MediaTechnicalMetadata
    termination_reason: str | None = None
    stream: ProgressiveMediaStream | None = field(default=None, repr=False)

    async def iter_batches(self, batch_size: int) -> AsyncIterator[tuple[list[DecodedMediaUnit], int | None]]:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self.stream is None:
            expected_units: int | None = max(1, len(self.units))
            for offset in range(0, len(self.units), batch_size):
                yield self.units[offset : offset + batch_size], expected_units
            return
        stream = self.stream
        async for batch, expected_units in stream.batches(batch_size):
            yield batch, expected_units
        final = await stream.result()
        self.metadata = final.metadata
        self.termination_reason = final.termination_reason
        self.stream = None

    async def materialize(self) -> DecodedMedia:
        if self.stream is None:
            return self
        units: list[DecodedMediaUnit] = []
        async for batch, _ in self.iter_batches(32):
            units.extend(batch)
        self.units = units
        return self

    async def close(self) -> None:
        if self.stream is not None:
            await self.stream.close()
            self.stream = None


def _safe_image(data: bytes) -> tuple[Image.Image, str]:
    try:
        with Image.open(BytesIO(data)) as opened:
            opened.verify()
        with Image.open(BytesIO(data)) as opened:
            transposed = ImageOps.exif_transpose(opened)
            if transposed is None:
                raise ValueError("image orientation could not be normalized")
            image = transposed.convert("RGB")
            image_format = str(opened.format or "unknown").lower()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise PipelineError("media is not a valid supported image") from exc
    if image.width <= 0 or image.height <= 0 or image.width * image.height > MAX_PIXELS:
        raise PipelineError("image dimensions exceed the safety limit")
    return image, image_format


def _downscale(image: Image.Image, max_edge: int | None) -> Image.Image:
    if max_edge is None or max(image.width, image.height) <= max_edge:
        return image
    scale = max_edge / max(image.width, image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def _frame_signature(frame: Any) -> Any:
    """计算灰度直方图签名，用于检测镜头切换。"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    histogram = cv2.calcHist([gray], [0], None, [SCENE_CHANGE_HISTOGRAM_BINS], [0, 256])
    cv2.normalize(histogram, histogram, 0, 1, cv2.NORM_MINMAX)
    return histogram


def _signature_distance(previous: Any, current: Any) -> float:
    correlation = float(cv2.compareHist(previous, current, cv2.HISTCMP_CORREL))
    return max(0.0, min(1.0, 1.0 - correlation))


def _is_keyframe(capture: Any) -> bool | None:
    """Read the decoded frame type; None means the backend cannot report it."""

    property_id = getattr(cv2, "CAP_PROP_FRAME_TYPE", None)
    if property_id is None:
        return None
    try:
        frame_type = int(capture.get(property_id))
    except (AttributeError, TypeError, ValueError, cv2.error):
        return None
    if frame_type in {0, ord("?")}:
        return None
    return frame_type == ord("I")


def _check_control(control: ExecutionControl | None, *, delay_seconds: float = 0.0) -> None:
    if control is None:
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        return
    if not control.wait_until_runnable(delay_seconds):
        raise PipelineError("media decoding cancelled")


def _capture_position_ms(capture: Any, fps: float) -> tuple[int, Literal["decoder_pts", "position_msec"]]:
    property_id = getattr(cv2, "CAP_PROP_PTS", None)
    if property_id is not None and fps > 0:
        try:
            pts = float(capture.get(property_id))
        except (AttributeError, TypeError, ValueError, cv2.error):
            pts = 0.0
        if pts > 0:
            return max(0, round(pts * 1000 / fps)), "decoder_pts"
    try:
        position_ms = int(capture.get(cv2.CAP_PROP_POS_MSEC) or 0)
    except (AttributeError, TypeError, ValueError, cv2.error):
        position_ms = 0
    return max(0, position_ms), "position_msec"


def _capture_frame_number(capture: Any, fallback: int) -> int:
    try:
        next_frame = int(capture.get(cv2.CAP_PROP_POS_FRAMES) or 0)
    except (AttributeError, TypeError, ValueError, cv2.error):
        next_frame = 0
    return max(0, next_frame - 1) if next_frame > 0 else fallback


def _video_suffix(media: MediaInput) -> str:
    if media.filename:
        suffix = os.path.splitext(media.filename)[1].lower()
        if suffix in {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".ts", ".webm"}:
            return suffix
    return {
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/webm": ".webm",
        "video/x-matroska": ".mkv",
        "video/x-msvideo": ".avi",
        "video/mpeg": ".mpeg",
        "video/mp2t": ".ts",
    }.get(media.content_type.split(";", 1)[0].lower(), ".mp4")


def _sniff_video_container(data: bytes, media: MediaInput) -> str:
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "mp4"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"AVI ":
        return "avi"
    if data.startswith(b"\x1aE\xdf\xa3"):
        return "webm" if _video_suffix(media) == ".webm" else "matroska"
    if data.startswith((b"\x00\x00\x01\xba", b"\x00\x00\x01\xb3")):
        return "mpeg"
    if len(data) >= 188 and data[0] == 0x47 and (len(data) < 376 or data[188] == 0x47):
        return "mpeg-ts"
    raise PipelineError("media is not a supported video container")


def _capture_metadata(capture: Any) -> dict[str, Any]:
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fourcc = int(capture.get(cv2.CAP_PROP_FOURCC) or 0)
    codec = "".join(chr((fourcc >> (8 * index)) & 0xFF) for index in range(4)).strip("\x00 ")
    duration_ms = int(frame_count / fps * 1000) if frame_count > 0 and fps > 0 else 0
    return {
        "width": width or None,
        "height": height or None,
        "fps": round(fps, 6) if 0.1 <= fps <= 240 else None,
        "frame_count": frame_count if frame_count > 0 else None,
        "duration_ms": duration_ms if duration_ms > 0 else None,
        "codec": codec or None,
    }


def _estimated_sample_count(
    plan: SamplePlan,
    *,
    frame_count: int,
    duration_ms: int,
    fps: float,
    is_stream: bool,
) -> int | None:
    if is_stream or plan.strategy in {SampleStrategy.KEYFRAME, SampleStrategy.SCENE_CHANGE}:
        return None
    if plan.strategy == SampleStrategy.UNIFORM and frame_count > 0:
        window_start = min(frame_count - 1, max(0, round(plan.start_ms / 1000 * fps)))
        window_end = frame_count if plan.end_ms is None else min(frame_count, round(plan.end_ms / 1000 * fps))
        span = max(1, window_end - window_start)
        return span
    if duration_ms > 0:
        window_end_ms = duration_ms if plan.end_ms is None else min(duration_ms, plan.end_ms)
        window_ms = max(0, window_end_ms - plan.start_ms)
        estimated = max(1, window_ms // plan.sample_interval_ms + 1)
        return estimated
    return None


def _effective_frame_max_edge(
    plan: SamplePlan,
    *,
    width: int,
    height: int,
    estimated_units: int | None,
) -> int | None:
    if width <= 0 or height <= 0:
        return plan.frame_max_edge
    natural_edge = max(width, height)
    requested_edge = min(natural_edge, plan.frame_max_edge or natural_edge)
    pixels_per_unit = max(
        64 * 64,
        DECODED_BATCH_MEMORY_BUDGET_BYTES
        // (
            RGB_BYTES_PER_PIXEL
            * min(DECODED_QUEUE_CAPACITY_UNITS, max(1, estimated_units or DECODED_QUEUE_CAPACITY_UNITS))
        ),
    )
    aspect_ratio = max(width, height) / min(width, height)
    budget_edge = max(64, math.floor(math.sqrt(pixels_per_unit * aspect_ratio)))
    effective_edge = min(requested_edge, budget_edge)
    return effective_edge if effective_edge < natural_edge or plan.frame_max_edge is not None else None


def _decode_video(
    media: MediaInput,
    *,
    plan: SamplePlan,
    max_reconnect_attempts: int = 3,
    connect_timeout_ms: int = 10_000,
    read_timeout_ms: int = 10_000,
    control: ExecutionControl | None = None,
    unit_callback: Callable[[DecodedMediaUnit, int | None], None] | None = None,
    retain_units: bool = True,
    preview_only: bool = False,
) -> DecodedMedia:
    plan.validate()
    _check_control(control)
    started = time.monotonic()
    path: str | None = None
    container: str | None = None
    if media.file_path is not None:
        target = media.file_path
    elif media.data is not None:
        container = _sniff_video_container(media.data, media)
        with tempfile.NamedTemporaryFile(prefix="scenara-media-", suffix=_video_suffix(media), delete=False) as handle:
            handle.write(media.data)
            path = handle.name
        target = path
    elif media.source_url:
        target = media.source_url
    else:
        raise PipelineError("video or stream input is empty")
    is_stream = media.source_url is not None and media.data is None and media.file_path is None

    def open_capture(attempts: int) -> Any | None:
        for attempt in range(attempts):
            _check_control(control)
            try:
                candidate = cv2.VideoCapture(
                    target,
                    cv2.CAP_ANY,
                    [
                        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                        connect_timeout_ms,
                        cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                        read_timeout_ms,
                    ],
                )
            except (TypeError, cv2.error):
                candidate = cv2.VideoCapture(target)
            if candidate.isOpened():
                return candidate
            candidate.release()
            if attempt + 1 < attempts:
                _check_control(control, delay_seconds=min(1.0, 0.1 * (2**attempt)))
        return None

    capture = open_capture(max(1, max_reconnect_attempts) if is_stream else 1)
    if capture is None:
        raise PipelineError("video or stream could not be opened")
    try:
        metadata = _capture_metadata(capture)
        if container is not None:
            metadata.update({"format": container, "container": container})
        fps = float(metadata.get("fps") or 25.0)
        frame_count = int(metadata.get("frame_count") or 0)
        duration_ms = int(metadata.get("duration_ms") or 0)
        estimated_units = _estimated_sample_count(
            plan,
            frame_count=frame_count,
            duration_ms=duration_ms,
            fps=fps,
            is_stream=is_stream,
        )
        effective_frame_max_edge = _effective_frame_max_edge(
            plan,
            width=int(metadata.get("width") or 0),
            height=int(metadata.get("height") or 0),
            estimated_units=estimated_units,
        )
        step = max(1, round(plan.sample_interval_ms / 1000 * fps))
        uniform_step = step
        if plan.strategy == SampleStrategy.UNIFORM:
            uniform_step = 1

        seek_used = False
        if plan.start_ms > 0 and not is_stream:
            seek_used = bool(capture.set(cv2.CAP_PROP_POS_MSEC, float(plan.start_ms)))

        units: list[DecodedMediaUnit] = []
        frame_index = 0
        consecutive_failures = 0
        reconnects = 0
        keyframe_count = 0
        scene_change_count = 0
        previous_signature: Any | None = None
        last_stream_pts_ms: int | None = None
        last_output_pts_ms = -1
        timestamp_source: Literal["decoder_pts", "position_msec", "monotonic_clock"] = (
            "monotonic_clock" if is_stream else "position_msec"
        )
        next_interval_ms = plan.start_ms
        termination_reason = "source_ended"
        sampled_units = 0
        while True:
            _check_control(control)
            ok, frame = capture.read()
            _check_control(control)
            if not ok:
                consecutive_failures += 1
                if not is_stream:
                    break
                if consecutive_failures < 3:
                    continue
                if reconnects >= max_reconnect_attempts:
                    termination_reason = "reconnect_exhausted"
                    break
                capture.release()
                _check_control(control)
                replacement = open_capture(1)
                reconnects += 1
                if replacement is None:
                    continue
                capture = replacement
                consecutive_failures = 0
                continue
            consecutive_failures = 0
            frame_index += 1
            frame_number = _capture_frame_number(capture, frame_index - 1) if not is_stream else frame_index - 1
            if is_stream:
                frame_duration_ms = max(1, round(1000 / fps))
                wall_clock_ms = int((time.monotonic() - started) * 1000)
                position_ms = (
                    wall_clock_ms
                    if last_stream_pts_ms is None
                    else max(
                        wall_clock_ms,
                        last_stream_pts_ms + frame_duration_ms,
                    )
                )
                last_stream_pts_ms = position_ms
                elapsed_ms = position_ms
            else:
                position_ms, detected_timestamp_source = _capture_position_ms(capture, fps)
                if detected_timestamp_source == "decoder_pts":
                    timestamp_source = detected_timestamp_source
                elapsed_ms = position_ms
            if not seek_used and plan.start_ms > 0 and elapsed_ms < plan.start_ms:
                continue
            if plan.end_ms is not None and elapsed_ms > plan.end_ms:
                termination_reason = "sample_window_completed"
                break
            if is_stream and plan.stream_segment_duration_ms is not None and elapsed_ms >= plan.stream_segment_duration_ms:
                termination_reason = "segment_window_completed"
                break

            selected = False
            if plan.strategy == SampleStrategy.KEYFRAME:
                is_keyframe = _is_keyframe(capture)
                if is_keyframe is None:
                    raise PipelineError("video backend does not expose decoded frame types for keyframe sampling")
                if is_keyframe:
                    keyframe_count += 1
                selected = is_keyframe
            elif plan.strategy == SampleStrategy.SCENE_CHANGE:
                signature = _frame_signature(frame)
                if previous_signature is None:
                    selected = True
                else:
                    distance = _signature_distance(previous_signature, signature)
                    selected = distance >= plan.scene_change_threshold
                    if selected:
                        scene_change_count += 1
                if selected:
                    previous_signature = signature
            elif plan.strategy == SampleStrategy.UNIFORM:
                selected = (frame_index - 1) % uniform_step == 0
            else:
                selected = elapsed_ms >= next_interval_ms
                if selected:
                    while next_interval_ms <= elapsed_ms:
                        next_interval_ms += plan.sample_interval_ms

            if not selected:
                continue
            height, width = frame.shape[:2]
            if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
                raise PipelineError("video frame dimensions exceed the safety limit")
            image = _downscale(
                Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)),
                effective_frame_max_edge,
            )
            output_pts_ms = max(position_ms, last_output_pts_ms + 1)
            last_output_pts_ms = output_pts_ms
            unit = DecodedMediaUnit(
                unit_id=f"frame_{frame_number}",
                unit_type="frame",
                index=sampled_units,
                pts_ms=output_pts_ms,
                image=image,
            )
            sampled_units += 1
            if retain_units:
                units.append(unit)
            if unit_callback is not None:
                unit_callback(unit, estimated_units)
            if preview_only:
                termination_reason = "preview_completed"
                break
        if sampled_units == 0:
            raise PipelineError("video or stream did not yield a decodable frame")
        metadata.update(
            {
                "sampled_units": sampled_units,
                "frames_read": frame_index,
                "sample_interval_ms": plan.sample_interval_ms,
                "sample_strategy": plan.strategy.value,
                "sample_start_ms": plan.start_ms,
                "sample_end_ms": plan.end_ms,
                "stream_segment_duration_ms": plan.stream_segment_duration_ms,
                "stream_segment_index": plan.stream_segment_index,
                "decode_seek_used": seek_used,
                "reconnect_count": reconnects,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "timestamp_source": timestamp_source,
            }
        )
        if effective_frame_max_edge is not None:
            metadata["frame_max_edge"] = effective_frame_max_edge
        if plan.strategy == SampleStrategy.KEYFRAME:
            metadata["keyframe_count"] = keyframe_count
        if plan.strategy == SampleStrategy.SCENE_CHANGE:
            metadata["scene_change_count"] = scene_change_count
        if duration_ms <= 0 and not is_stream and last_output_pts_ms >= 0:
            metadata["duration_ms"] = last_output_pts_ms
        return DecodedMedia(
            kind=media.kind,
            units=units,
            metadata=MediaTechnicalMetadata.model_validate(
                {key: value for key, value in metadata.items() if value is not None}
            ),
            termination_reason=termination_reason,
        )
    finally:
        capture.release()
        if path:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(path)


def _decode_pdf(
    data: bytes,
    *,
    page_scale: float = 1.5,
    control: ExecutionControl | None = None,
    preview_only: bool = False,
) -> DecodedMedia:
    if not data.startswith(b"%PDF-"):
        raise PipelineError("document is not a PDF")
    if not 0.5 <= page_scale <= 4.0:
        raise PipelineError("page_scale must be between 0.5 and 4.0")
    try:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(data)
        page_count = len(document)
        if page_count <= 0:
            raise PipelineError("PDF page count exceeds the safety limit")
        units: list[DecodedMediaUnit] = []
        page_indexes = range(min(page_count, 1)) if preview_only else range(page_count)
        for index in page_indexes:
            _check_control(control)
            page = document[index]
            bitmap = page.render(scale=page_scale)
            image = bitmap.to_pil().convert("RGB")
            if image.width * image.height > MAX_PIXELS:
                raise PipelineError("PDF page dimensions exceed the safety limit")
            units.append(
                DecodedMediaUnit(
                    unit_id=f"page_{index + 1}",
                    unit_type="page",
                    index=index,
                    page_number=index + 1,
                    image=image,
                )
            )
        document.close()
    except PipelineError:
        raise
    except Exception as exc:
        raise PipelineError("PDF could not be decoded safely") from exc
    first = units[0] if units else None
    return DecodedMedia(
        kind=MediaKind.DOCUMENT,
        units=units,
        metadata=MediaTechnicalMetadata(
            format="pdf",
            container="pdf",
            page_count=page_count,
            sampled_units=len(units),
            width=first.width if first else None,
            height=first.height if first else None,
        ),
    )


def decode_media(
    media: MediaInput,
    *,
    sample_interval_ms: int,
    max_reconnect_attempts: int = 3,
    connect_timeout_ms: int = 10_000,
    read_timeout_ms: int = 10_000,
    sample_strategy: SampleStrategy | str = SampleStrategy.INTERVAL,
    sample_start_ms: int = 0,
    sample_end_ms: int | None = None,
    stream_segment_duration_ms: int | None = None,
    stream_segment_index: int | None = None,
    scene_change_threshold: float = 0.35,
    frame_max_edge: int | None = None,
    page_scale: float = 1.5,
    control: ExecutionControl | None = None,
    unit_callback: Callable[[DecodedMediaUnit, int | None], None] | None = None,
    retain_units: bool = True,
) -> DecodedMedia:
    _check_control(control)
    if media.kind == MediaKind.IMAGE:
        if media.data is None:
            raise PipelineError("image input is empty")
        image, image_format = _safe_image(media.data)
        image = _downscale(image, frame_max_edge)
        return DecodedMedia(
            kind=media.kind,
            units=[DecodedMediaUnit(unit_id="frame_0", unit_type="frame", index=0, pts_ms=0, image=image)],
            metadata=MediaTechnicalMetadata(
                format=image_format,
                width=image.width,
                height=image.height,
                sampled_units=1,
                frame_max_edge=frame_max_edge,
            ),
        )
    if media.kind == MediaKind.DOCUMENT:
        if media.data is None:
            raise PipelineError("document input is empty")
        return _decode_pdf(media.data, page_scale=page_scale, control=control)
    try:
        strategy = SampleStrategy(sample_strategy)
    except ValueError as exc:
        raise PipelineError(f"unsupported sample_strategy: {sample_strategy}") from exc
    return _decode_video(
        media,
        plan=SamplePlan(
            strategy=strategy,
            sample_interval_ms=sample_interval_ms,
            start_ms=sample_start_ms,
            end_ms=sample_end_ms,
            stream_segment_duration_ms=stream_segment_duration_ms,
            stream_segment_index=stream_segment_index,
            scene_change_threshold=scene_change_threshold,
            frame_max_edge=frame_max_edge,
        ),
        max_reconnect_attempts=max_reconnect_attempts,
        connect_timeout_ms=connect_timeout_ms,
        read_timeout_ms=read_timeout_ms,
        control=control,
        unit_callback=unit_callback,
        retain_units=retain_units,
    )


def _decode_media_preview(media: MediaInput) -> DecodedMedia:
    if media.kind == MediaKind.DOCUMENT:
        if media.data is None:
            raise PipelineError("document input is empty")
        return _decode_pdf(media.data, preview_only=True)
    if media.kind == MediaKind.IMAGE:
        return decode_media(media, sample_interval_ms=1)
    return _decode_video(
        media,
        plan=SamplePlan(sample_interval_ms=1),
        preview_only=True,
    )


def inspect_media(media: MediaInput) -> tuple[dict[str, Any], bytes]:
    decoded = _decode_media_preview(media)
    image = decoded.units[0].image.copy()
    image.thumbnail((640, 640), Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format="JPEG", quality=85, optimize=True)
    return decoded.metadata.model_dump(exclude_none=True), output.getvalue()


def create_media_preview(media: MediaInput, *, max_edge: int = 640) -> bytes:
    if not 64 <= max_edge <= 2048:
        raise ValueError("preview max_edge must be between 64 and 2048")
    decoded = _decode_media_preview(media)
    if not decoded.units:
        raise PipelineError("media did not yield a previewable unit")
    image = decoded.units[0].image.copy()
    image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format="JPEG", quality=85, optimize=True)
    return output.getvalue()


class DecodeMediaOperator:
    definition = OperatorDefinition(
        operator_id="platform.media.decode",
        version="1.2.0",
        input_types={"media": "media/input"},
        output_types={"batch": "media/batch"},
        timeout_seconds=3600,
        resource_class="cpu",
        batchable=True,
        failure_policy="fail",
    )

    async def execute(
        self,
        context: ExecutionContext,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        media = inputs.get("media")
        if not isinstance(media, MediaInput):
            raise PipelineError("decode-media requires MediaInput")
        sample_interval_ms = int(parameters.get("sample_interval_ms", 1000))
        max_reconnect_attempts = int(parameters.get("max_reconnect_attempts", 3))
        connect_timeout_ms = int(parameters.get("connect_timeout_ms", 10_000))
        read_timeout_ms = int(parameters.get("read_timeout_ms", 10_000))
        sample_strategy = str(parameters.get("sample_strategy", SampleStrategy.INTERVAL))
        sample_start_ms = int(parameters.get("sample_start_ms", 0))
        sample_end_ms_raw = parameters.get("sample_end_ms")
        sample_end_ms = int(sample_end_ms_raw) if sample_end_ms_raw is not None else None
        stream_segment_duration_ms_raw = parameters.get("stream_segment_duration_ms")
        stream_segment_duration_ms = (
            int(stream_segment_duration_ms_raw) if stream_segment_duration_ms_raw is not None else None
        )
        stream_segment_index_raw = parameters.get("stream_segment_index")
        stream_segment_index = int(stream_segment_index_raw) if stream_segment_index_raw is not None else None
        scene_change_threshold = float(parameters.get("scene_change_threshold", 0.35))
        frame_max_edge_raw = parameters.get("frame_max_edge")
        frame_max_edge = int(frame_max_edge_raw) if frame_max_edge_raw is not None else None
        page_scale = float(parameters.get("page_scale", 1.5))
        if sample_interval_ms < 1 or sample_interval_ms > 3_600_000:
            raise PipelineError("sample_interval_ms is outside the supported range")
        if not 0 <= max_reconnect_attempts <= 20:
            raise PipelineError("max_reconnect_attempts is outside the supported range")
        if not 100 <= connect_timeout_ms <= 120_000 or not 100 <= read_timeout_ms <= 120_000:
            raise PipelineError("media timeout is outside the supported range")
        decode_arguments: dict[str, Any] = {
            "sample_interval_ms": sample_interval_ms,
            "max_reconnect_attempts": max_reconnect_attempts,
            "connect_timeout_ms": connect_timeout_ms,
            "read_timeout_ms": read_timeout_ms,
            "sample_strategy": sample_strategy,
            "sample_start_ms": sample_start_ms,
            "sample_end_ms": sample_end_ms,
            "stream_segment_duration_ms": stream_segment_duration_ms,
            "stream_segment_index": stream_segment_index,
            "scene_change_threshold": scene_change_threshold,
            "frame_max_edge": frame_max_edge,
            "page_scale": page_scale,
            "control": context.control,
        }
        if media.kind in {MediaKind.VIDEO, MediaKind.STREAM}:
            stream = ProgressiveMediaStream(
                lambda callback: decode_media(
                    media,
                    **decode_arguments,
                    unit_callback=callback,
                    retain_units=False,
                ),
                context.control,
            )
            return {
                "batch": DecodedMedia(
                    kind=media.kind,
                    units=[],
                    metadata=MediaTechnicalMetadata(
                        sampled_units=0,
                        sample_interval_ms=sample_interval_ms,
                        sample_strategy=SampleStrategy(sample_strategy),
                        sample_start_ms=sample_start_ms,
                        sample_end_ms=sample_end_ms,
                        stream_segment_duration_ms=stream_segment_duration_ms,
                        stream_segment_index=stream_segment_index,
                    ),
                    stream=stream,
                )
            }
        decoded = await asyncio.to_thread(decode_media, media, **decode_arguments)
        return {"batch": decoded}


__all__ = [
    "DecodeMediaOperator",
    "DecodedMedia",
    "DecodedMediaUnit",
    "MediaInput",
    "ProgressiveMediaStream",
    "SamplePlan",
    "SampleStrategy",
    "create_media_preview",
    "decode_media",
    "inspect_media",
]
