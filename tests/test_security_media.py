from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from scenara.platform.media_batch import MediaInput, decode_media
from scenara.platform.models import MediaKind
from scenara.platform.pipeline import PipelineError


def test_malformed_image_is_rejected_without_partial_decode() -> None:
    with pytest.raises(PipelineError, match="valid supported image"):
        decode_media(
            MediaInput(
                kind=MediaKind.IMAGE,
                content_type="image/png",
                data=b"\x89PNG\r\n\x1a\nmalformed",
            ),
            max_units=1,
            sample_interval_ms=1,
        )


def test_malformed_pdf_is_rejected_by_bounded_decoder() -> None:
    payload = b"%PDF-1.7\n1 0 obj\n<< /Length 999999999 >>\nstream\ntruncated"
    with pytest.raises(PipelineError, match="PDF could not be decoded safely"):
        decode_media(
            MediaInput(kind=MediaKind.DOCUMENT, content_type="application/pdf", data=payload),
            max_units=1,
            sample_interval_ms=1,
        )


def test_image_decompression_bomb_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    output = BytesIO()
    Image.new("RGB", (64, 64), "white").save(output, format="PNG")
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(PipelineError, match="valid supported image"):
        decode_media(
            MediaInput(kind=MediaKind.IMAGE, content_type="image/png", data=output.getvalue()),
            max_units=1,
            sample_interval_ms=1,
        )
