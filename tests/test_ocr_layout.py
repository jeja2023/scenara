from __future__ import annotations

from io import BytesIO
from typing import Any

import httpx
import pytest
from PIL import Image

from scenara.bootstrap import build_runtime
from scenara.server import create_app


class LayoutOcrEngine:
    model_id = "approved-ocr"
    version = "1.0.0"
    production_ready = True
    production_capabilities = frozenset({"text_detection", "text_recognition", "layout_analysis"})
    layout_model_id = "approved-layout"
    layout_version = "2.0.0"

    def predict(self, image: Any) -> list[dict[str, Any]]:
        assert image.size == (120, 100)
        return [
            {
                "text": "Body",
                "score": 0.98,
                "polygon": [[5, 50], [100, 50], [100, 65], [5, 65]],
            },
            {
                "text": "Scenara",
                "score": 0.99,
                "polygon": [[5, 8], [80, 8], [80, 24], [5, 24]],
            },
        ]

    def predict_layout(self, image: Any) -> list[dict[str, Any]]:
        assert image.size == (120, 100)
        return [
            {
                "block_type": "paragraph",
                "polygon": [[0, 45], [110, 45], [110, 70], [0, 70]],
                "score": 0.95,
            },
            {
                "block_type": "table",
                "polygon": [[0, 75], [55, 75], [55, 98], [0, 98]],
                "score": 0.93,
            },
            {
                "block_type": "title",
                "polygon": [[0, 0], [100, 0], [100, 28], [0, 28]],
                "score": 0.97,
            },
            {
                "block_type": "image",
                "polygon": [[60, 75], [118, 75], [118, 98], [60, 98]],
                "score": 0.92,
            },
        ]


def document_image() -> bytes:
    output = BytesIO()
    Image.new("RGB", (120, 100), "white").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_ocr_layout_regions_and_reading_order(development_settings) -> None:
    runtime = build_runtime(development_settings, ocr_engine=LayoutOcrEngine())
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        uploaded = await api.post(
            "/api/v1/media/assets",
            files={"file": ("document.png", document_image(), "image/png")},
            data={"kind": "image"},
        )
        run = await api.post(
            "/api/v1/runs",
            json={
                "domain": "ocr",
                "pipeline": {"pipeline_id": "ocr.document", "version": "0.1.0"},
                "asset_id": uploaded.json()["data"]["asset_id"],
                "parameters": {"layout_required": True},
                "wait_ms": 2000,
            },
            headers={"Idempotency-Key": "ocr-layout"},
        )
        assert run.status_code == 202, run.text
        assert run.json()["data"]["status"] == "completed"
        response = await api.get(f"/api/v1/runs/{run.json()['data']['run_id']}/result")
        result = response.json()["data"]["result"]
        blocks = result["domain_payload"]["blocks"]
        assert [block["block_type"] for block in blocks] == [
            "title",
            "paragraph",
            "table",
            "image",
        ]
        assert [block["reading_order"] for block in blocks] == [0, 1, 2, 3]
        assert result["domain_payload"]["text"] == "Scenara\nBody"
        assert result["provenance"]["development_substitutes"] == []
        assert {model["capability"] for model in result["models"]} == {
            "ocr_recognition",
            "ocr_layout",
        }
