from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Literal

import cv2
from PIL import Image, ImageOps, UnidentifiedImageError

from scenara.platform.models import MediaKind
from scenara.platform.pipeline import ExecutionContext, OperatorDefinition, PipelineError


@dataclass(slots=True)
class MediaInput:
    kind: MediaKind
    content_type: str
    data: bytes | None = None
    source_url: str | None = None


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


@dataclass(slots=True)
class DecodedMedia:
    kind: MediaKind
    units: list[DecodedMediaUnit]
    termination_reason: str | None = None


def _safe_image(data: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(data)) as opened:
            opened.verify()
        with Image.open(BytesIO(data)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise PipelineError("media is not a valid supported image") from exc
    if image.width <= 0 or image.height <= 0 or image.width * image.height > 80_000_000:
        raise PipelineError("image dimensions exceed the safety limit")
    return image


def _decode_video(
    data: bytes | None,
    source_url: str | None,
    *,
    max_units: int,
    sample_interval_ms: int,
    max_reconnect_attempts: int = 3,
) -> DecodedMedia:
    path: str | None = None
    if data is not None:
        with tempfile.NamedTemporaryFile(prefix="scenara-media-", suffix=".video", delete=False) as handle:
            handle.write(data)
            path = handle.name
        target = path
    elif source_url:
        target = source_url
    else:
        raise PipelineError("video or stream input is empty")
    def open_capture(attempts: int) -> Any | None:
        for attempt in range(attempts):
            candidate = cv2.VideoCapture(target)
            if candidate.isOpened():
                return candidate
            candidate.release()
            if attempt + 1 < attempts:
                time.sleep(min(1.0, 0.1 * (2**attempt)))
        return None

    capture = open_capture(max_reconnect_attempts if data is None else 1)
    if capture is None:
        raise PipelineError("video or stream could not be opened")
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        fps = fps if 0.1 <= fps <= 240 else 25.0
        step = max(1, round(sample_interval_ms / 1000 * fps))
        units: list[DecodedMediaUnit] = []
        frame_index = 0
        consecutive_failures = 0
        termination_reason = "source_ended"
        while len(units) < max_units:
            ok, frame = capture.read()
            if not ok:
                consecutive_failures += 1
                if data is not None:
                    break
                if consecutive_failures < 3:
                    continue
                capture.release()
                replacement = open_capture(max_reconnect_attempts)
                if replacement is None:
                    termination_reason = "reconnect_exhausted"
                    break
                capture = replacement
                consecutive_failures = 0
                continue
            consecutive_failures = 0
            if frame_index % step == 0:
                height, width = frame.shape[:2]
                if width <= 0 or height <= 0 or width * height > 80_000_000:
                    raise PipelineError("video frame dimensions exceed the safety limit")
                image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                pts_ms = int(capture.get(cv2.CAP_PROP_POS_MSEC))
                units.append(
                    DecodedMediaUnit(
                        unit_id=f"frame_{frame_index}",
                        unit_type="frame",
                        index=len(units),
                        pts_ms=max(0, pts_ms),
                        image=image,
                    )
                )
            frame_index += 1
        if not units:
            raise PipelineError("video or stream did not yield a decodable frame")
        reason = "max_units_reached" if len(units) == max_units else termination_reason
        return DecodedMedia(kind=MediaKind.VIDEO, units=units, termination_reason=reason)
    finally:
        capture.release()
        if path:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(path)


def _decode_pdf(data: bytes, *, max_units: int) -> DecodedMedia:
    if not data.startswith(b"%PDF-"):
        raise PipelineError("document is not a PDF")
    try:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(data)
        page_count = len(document)
        if page_count <= 0 or page_count > 1000:
            raise PipelineError("PDF page count exceeds the safety limit")
        units: list[DecodedMediaUnit] = []
        for index in range(min(page_count, max_units)):
            page = document[index]
            bitmap = page.render(scale=1.5)
            image = bitmap.to_pil().convert("RGB")
            if image.width * image.height > 80_000_000:
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
    return DecodedMedia(kind=MediaKind.DOCUMENT, units=units)


def decode_media(media: MediaInput, *, max_units: int, sample_interval_ms: int) -> DecodedMedia:
    if not 1 <= max_units <= 10_000:
        raise PipelineError("max_units must be between 1 and 10000")
    if media.kind == MediaKind.IMAGE:
        if media.data is None:
            raise PipelineError("image input is empty")
        image = _safe_image(media.data)
        return DecodedMedia(
            kind=media.kind,
            units=[DecodedMediaUnit(unit_id="frame_0", unit_type="frame", index=0, pts_ms=0, image=image)],
        )
    if media.kind == MediaKind.DOCUMENT:
        if media.data is None:
            raise PipelineError("document input is empty")
        return _decode_pdf(media.data, max_units=max_units)
    return _decode_video(media.data, media.source_url, max_units=max_units, sample_interval_ms=sample_interval_ms)


def create_media_preview(media: MediaInput, *, max_edge: int = 640) -> bytes:
    if not 64 <= max_edge <= 2048:
        raise ValueError("preview max_edge must be between 64 and 2048")
    decoded = decode_media(media, max_units=1, sample_interval_ms=1)
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
        version="1.0.0",
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
        del context
        media = inputs.get("media")
        if not isinstance(media, MediaInput):
            raise PipelineError("decode-media requires MediaInput")
        max_units = int(parameters.get("max_units", 64))
        sample_interval_ms = int(parameters.get("sample_interval_ms", 1000))
        if sample_interval_ms < 1 or sample_interval_ms > 3_600_000:
            raise PipelineError("sample_interval_ms is outside the supported range")
        decoded = await asyncio.to_thread(
            decode_media,
            media,
            max_units=max_units,
            sample_interval_ms=sample_interval_ms,
        )
        return {"batch": decoded}


__all__ = [
    "DecodeMediaOperator",
    "DecodedMedia",
    "DecodedMediaUnit",
    "MediaInput",
    "create_media_preview",
    "decode_media",
]
