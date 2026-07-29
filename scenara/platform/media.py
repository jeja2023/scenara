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
            image = ImageOps.exif_transpose(opened).convert("RGB")
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > 80_000_000:
                raise PipelineError("image dimensions exceed the configured safety limit")
            return DecodedImage(image=image, width=width, height=height, format=str(opened.format or "unknown").lower())
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


__all__ = ["DecodeImageOperator", "DecodedImage"]
