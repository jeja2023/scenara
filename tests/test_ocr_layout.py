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


@pytest.mark.asyncio
async def test_ocr_motion_filter_and_temporal_deduplication() -> None:
    from scenara.domains.ocr.operators import OcrDocumentOperator
    from scenara.platform.media_batch import DecodedMedia, DecodedMediaUnit
    from scenara.platform.models import MediaKind, MediaTechnicalMetadata, SampleStrategy
    from scenara.platform.pipeline import ExecutionContext

    call_count = 0

    class TrackingEngine:
        model_id = "test-ocr"
        version = "1.0.0"
        production_ready = True

        def predict(self, image: Any, **kwargs: Any) -> list[dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            return [
                {
                    "text": "静态标语",
                    "score": 0.98,
                    "polygon": [[10, 10], [90, 10], [90, 30], [10, 30]],
                }
            ]

    operator = OcrDocumentOperator(engine=TrackingEngine())
    img = Image.new("RGB", (100, 50), "white")
    units = [
        DecodedMediaUnit(
            unit_id=f"frame_{i}",
            unit_type="frame",
            index=i,
            pts_ms=i * 1000,
            image=img,
        )
        for i in range(5)
    ]
    decoded = DecodedMedia(
        kind=MediaKind.VIDEO,
        metadata=MediaTechnicalMetadata(
            width=100,
            height=50,
            duration_ms=4000,
            sample_strategy=SampleStrategy.INTERVAL,
        ),
        units=units,
    )

    class DummyContext(ExecutionContext):
        def __init__(self) -> None:
            pass
        run_id = "test_run"
        pipeline_id = "ocr.document"
        pipeline_version = "1.0.0"
        asset_id = "asset_1"
        source_id = "src_1"
        production = False
        async def publish_partial_result(self, res: Any) -> None:
            pass
        async def report_progress(self, *args: Any, **kwargs: Any) -> None:
            pass

    res = await operator.execute(
        DummyContext(),
        {"batch": decoded},
        {"motion_filter_enabled": True, "motion_threshold": 0.025, "deduplicate_text": True},
    )
    result = res["result"]

    # 5 帧完全相同的静态画面，模型推理调用次数应该为 1
    assert call_count == 1
    # 5 个单元均被完整处理并关联对象
    assert len(result.units) == 5
    for unit in result.units:
        assert len(unit.objects) == 1
        assert unit.objects[0].attributes["text"] == "静态标语"
    # 时序去重文本合并了时间跨度
    assert result.domain_payload.text == "[00:00.0 - 00:04.0] 静态标语"

