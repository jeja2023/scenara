from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from scenara.platform.pipeline import ExecutionContext, OperatorDefinition, PipelineError


@dataclass(slots=True)
class DecodedImage:
    image: Any
    width: int
    height: int
    format: str


def _decode_image(data: bytes) -> DecodedImage:
    try:
        with Image.open(BytesIO(data)) as opened:
            opened.verify()
        with Image.open(BytesIO(data)) as opened:
            transposed = ImageOps.exif_transpose(opened)
            image = (transposed if transposed is not None else opened).convert("RGB")
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > 80_000_000:
                raise PipelineError("image dimensions exceed the configured safety limit")
            return DecodedImage(image=image, width=width, height=height, format=(opened.format or "unknown").lower())
    except PipelineError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise PipelineError("media is not a valid supported image") from exc


class DecodeImageOperator:
    definition = OperatorDefinition(
        operator_id="platform.media.decode-image",
        version="1.0.0",
        input_types={"data": "bytes"},
        output_types={"image": "media/image"},
        timeout_seconds=15,
        resource_class="cpu",
        batchable=True,
    )

    async def execute(
        self,
        context: ExecutionContext,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        del context, parameters
        data = inputs.get("data")
        if not isinstance(data, bytes):
            raise PipelineError("decode-image requires byte input")
        return {"image": await asyncio.to_thread(_decode_image, data)}


def parse_roi(
    raw_roi: Any, img_w: int, img_h: int
) -> tuple[int, int, int, int] | None:
    """解析 ROI 归一化或像素坐标 [x1, y1, x2, y2] 为合法的整数像素边界 (x1, y1, x2, y2)"""
    if not raw_roi:
        return None
    coords: list[float] = []
    if isinstance(raw_roi, (list, tuple)):
        coords = [float(v) for v in raw_roi if isinstance(v, (int, float))]
    elif isinstance(raw_roi, str):
        import re

        parts = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", raw_roi)
        coords = [float(p) for p in parts]
    if len(coords) != 4:
        return None
    x1, y1, x2, y2 = coords
    # 如果全为归一化比例 (<= 1.0)
    if max(x1, y1, x2, y2) <= 1.0:
        x1 = x1 * img_w
        x2 = x2 * img_w
        y1 = y1 * img_h
        y2 = y2 * img_h
    ix1 = max(0, min(img_w - 1, round(min(x1, x2))))
    iy1 = max(0, min(img_h - 1, round(min(y1, y2))))
    ix2 = max(ix1 + 1, min(img_w, round(max(x1, x2))))
    iy2 = max(iy1 + 1, min(img_h, round(max(y1, y2))))
    if ix2 <= ix1 or iy2 <= iy1:
        return None
    return (ix1, iy1, ix2, iy2)


def is_box_in_roi(
    box_x: float,
    box_y: float,
    box_w: float,
    box_h: float,
    roi_box: tuple[int, int, int, int],
) -> bool:
    """判断给定的边界框中心是否落在 ROI 范围内"""
    rx1, ry1, rx2, ry2 = roi_box
    cx = box_x + box_w / 2.0
    cy = box_y + box_h / 2.0
    return rx1 <= cx <= rx2 and ry1 <= cy <= ry2


__all__ = ["DecodeImageOperator", "DecodedImage", "is_box_in_roi", "parse_roi"]
