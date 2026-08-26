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
    production_capabilities = frozenset(
        {"text_detection", "text_recognition", "layout_analysis"}
    )
    layout_model_id = "approved-layout"
    layout_version = "2.0.0"

    def predict(
        self,
        image: Any,
        *,
        min_score: float = 0.0,
        language_hint: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
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
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as api:
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
    from scenara.platform.models import (
        MediaKind,
        MediaTechnicalMetadata,
        SampleStrategy,
    )
    from scenara.platform.pipeline import ExecutionContext

    call_count = 0

    class TrackingEngine:
        model_id = "test-ocr"
        version = "1.0.0"
        production_ready = True

        def predict(
            self,
            image: Any,
            *,
            min_score: float = 0.0,
            language_hint: str | None = None,
            **kwargs: Any,
        ) -> list[dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            return [
                {
                    "text": "静态标语",
                    "score": 0.98,
                    "polygon": [[10, 10], [90, 10], [90, 30], [10, 30]],
                }
            ]

        def predict_layout(self, image: Any) -> list[dict[str, Any]]:
            return []

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
        {
            "motion_filter_enabled": True,
            "motion_threshold": 0.025,
            "deduplicate_text": True,
        },
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


@pytest.mark.asyncio
async def test_ocr_roi_and_compliance_and_html_layout() -> None:
    from scenara.domains.ocr.operators import OcrDocumentOperator
    from scenara.platform.media_batch import DecodedMedia, DecodedMediaUnit
    from scenara.platform.models import (
        MediaKind,
        MediaTechnicalMetadata,
        SampleStrategy,
    )
    from scenara.platform.pipeline import ExecutionContext

    class MockEngine:
        model_id = "test-ocr-roi"
        version = "1.0.0"
        production_ready = True

        def predict(
            self,
            image: Any,
            *,
            min_score: float = 0.0,
            language_hint: str | None = None,
            **kwargs: Any,
        ) -> list[dict[str, Any]]:
            # 确认传入的是裁剪后的局部 ROI 图像
            assert image.size == (80, 40)
            return [
                {
                    "text": "本商场行业第一，顶级品牌",
                    "score": 0.96,
                    "polygon": [[5, 5], [75, 5], [75, 25], [5, 25]],
                    "block_type": "title",
                }
            ]

        def predict_layout(self, image: Any) -> list[dict[str, Any]]:
            return []

    operator = OcrDocumentOperator(engine=MockEngine())
    # 原图尺寸 200 x 100
    img = Image.new("RGB", (200, 100), "white")
    unit = DecodedMediaUnit(
        unit_id="frame_0",
        unit_type="frame",
        index=0,
        pts_ms=0,
        image=img,
    )
    decoded = DecodedMedia(
        kind=MediaKind.IMAGE,
        metadata=MediaTechnicalMetadata(
            width=200,
            height=100,
            sample_strategy=SampleStrategy.INTERVAL,
        ),
        units=[unit],
    )

    class DummyContext(ExecutionContext):
        def __init__(self) -> None:
            pass

        run_id = "test_run_roi"
        pipeline_id = "ocr.document"
        pipeline_version = "1.0.0"
        asset_id = "asset_roi"
        source_id = "src_roi"
        production = False

        async def publish_partial_result(self, res: Any) -> None:
            pass

        async def report_progress(self, *args: Any, **kwargs: Any) -> None:
            pass

    # 传入 ROI 区域 [x1=20, y1=10, x2=100, y2=50] -> 宽80 高40
    res = await operator.execute(
        DummyContext(),
        {"batch": decoded},
        {
            "roi": [20, 10, 100, 50],
            "enable_compliance": True,
            "layout_reconstruction": True,
        },
    )
    result = res["result"]
    payload = result.domain_payload

    # 1. 验证坐标逆映射：原本在局部图像中的 [5, 5] 应被正确逆映射为原图全画幅坐标 [25, 15]
    obj = result.units[0].objects[0]
    assert obj.bbox.x == 25.0
    assert obj.bbox.y == 15.0

    # 2. 验证合规审查报告：命中极限词“第一”、“顶级” -> status 应为 "block"
    assert payload.compliance_report is not None
    assert payload.compliance_report["status"] == "block"
    hit_words = [h["word"] for h in payload.compliance_report["hits"]]
    assert any("第一" in w for w in hit_words)
    assert any("顶级" in w for w in hit_words)

    # 3. 验证 HTML 排版还原：包含自适应容器与百分比绝对定位
    assert payload.html_layout is not None
    assert "ocr-visual-container" in payload.html_layout
    assert "本商场" in payload.html_layout
    assert "品牌" in payload.html_layout


@pytest.mark.asyncio
async def test_ocr_slides_carousel_deduplication() -> None:
    from scenara.domains.ocr.operators import OcrDocumentOperator
    from scenara.platform.media_batch import DecodedMedia, DecodedMediaUnit
    from scenara.platform.models import (
        MediaKind,
        MediaTechnicalMetadata,
        SampleStrategy,
    )
    from scenara.platform.pipeline import ExecutionContext

    class SlideEngine:
        model_id = "test-slide-engine"
        version = "1.0.0"
        production_ready = True

        def predict(
            self,
            image: Any,
            *,
            min_score: float = 0.0,
            language_hint: str | None = None,
            **kwargs: Any,
        ) -> list[dict[str, Any]]:
            # 根据像素颜色或自定义逻辑返回不同文字
            # 这里简单返回特定文本
            text = getattr(image, "_test_text", "海报A")
            return [
                {
                    "text": text,
                    "score": 0.95,
                    "polygon": [[10, 10], [90, 10], [90, 30], [10, 30]],
                }
            ]

        def predict_layout(self, image: Any) -> list[dict[str, Any]]:
            return []

    operator = OcrDocumentOperator(engine=SlideEngine())

    # 模拟户外大屏轮播序列：海报A (0s, 1s) -> 海报B (2s, 3s) -> 再次回到海报A (4s, 5s)
    schedule = [
        ("海报A-夏季特惠", 0),
        ("海报A-夏季特惠", 1000),
        ("海报B-新品上市", 2000),
        ("海报B-新品上市", 3000),
        ("海报A-夏季特惠", 4000),
        ("海报A-夏季特惠", 5000),
    ]

    units = []
    for i, (text, pts) in enumerate(schedule):
        img = Image.new("RGB", (100, 50), "white")
        setattr(img, "_test_text", text)  # 附带测试文本
        units.append(
            DecodedMediaUnit(
                unit_id=f"frame_{i}",
                unit_type="frame",
                index=i,
                pts_ms=pts,
                image=img,
            )
        )

    decoded = DecodedMedia(
        kind=MediaKind.STREAM,
        metadata=MediaTechnicalMetadata(
            width=100,
            height=50,
            duration_ms=6000,
            sample_strategy=SampleStrategy.INTERVAL,
        ),
        units=units,
    )

    class DummyContext(ExecutionContext):
        def __init__(self) -> None:
            pass

        run_id = "test_run_slides"
        pipeline_id = "ocr.document"
        pipeline_version = "1.0.0"
        asset_id = "asset_slides"
        source_id = "src_slides"
        production = False

        async def publish_partial_result(self, res: Any) -> None:
            pass

        async def report_progress(self, *args: Any, **kwargs: Any) -> None:
            pass

    res = await operator.execute(
        DummyContext(),
        {"batch": decoded},
        {
            "motion_filter_enabled": False,  # 禁用简易动静态帧跳过以测试海报聚类
            "deduplicate_slides": True,
            "layout_reconstruction": True,
        },
    )
    result = res["result"]
    payload = result.domain_payload

    # 6 帧画面（A, A, B, B, A, A）应被成功聚类为 2 张独立的大屏海报卡片
    assert len(payload.slides) == 2
    slide_a = payload.slides[0]
    slide_b = payload.slides[1]

    assert slide_a["text"] == "海报A-夏季特惠"
    # 海报A累计轮播出现 4 次
    assert slide_a["display_count"] == 4
    # 海报A的最后一次展示时间戳为 5000ms
    assert slide_a["last_pts_ms"] == 5000

    assert slide_b["text"] == "海报B-新品上市"
    # 海报B累计轮播出现 2 次
    assert slide_b["display_count"] == 2


@pytest.mark.asyncio
async def test_ocr_roi_filtering() -> None:
    from PIL import ImageDraw
    from scenara.domains.ocr.operators import OcrDocumentOperator
    from scenara.platform.media_batch import DecodedMedia, DecodedMediaUnit
    from scenara.platform.models import MediaKind, MediaTechnicalMetadata
    from scenara.platform.pipeline import ExecutionContext

    class RoiEngine:
        model_id = "test-roi-engine"
        version = "1.0.0"
        production_ready = True

        def predict(
            self,
            image: Any,
            *,
            min_score: float = 0.0,
            language_hint: str | None = None,
            **kwargs: Any,
        ) -> list[dict[str, Any]]:
            r, g, b = image.getpixel((50, image.height // 2))
            if r > 200:
                # 顶部红色区域
                return [
                    {
                        "text": "TopText",
                        "score": 0.95,
                        "polygon": [[10, 10], [90, 10], [90, 30], [10, 30]],
                    },
                ]
            else:
                # 底部蓝色区域（局部坐标为 y: 20..40）
                return [
                    {
                        "text": "BottomText",
                        "score": 0.95,
                        "polygon": [[10, 20], [90, 20], [90, 40], [10, 40]],
                    },
                ]

        def predict_layout(self, image: Any) -> list[dict[str, Any]]:
            return []

    operator = OcrDocumentOperator(engine=RoiEngine())
    image = Image.new("RGB", (100, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, 100, 50], fill=(255, 0, 0))
    draw.rectangle([0, 50, 100, 100], fill=(0, 0, 255))

    units = [
        DecodedMediaUnit(
            unit_id="page_1",
            unit_type="page",
            index=0,
            image=image,
            page_number=1,
        )
    ]
    decoded = DecodedMedia(
        kind=MediaKind.DOCUMENT,
        metadata=MediaTechnicalMetadata(width=100, height=100, sampled_units=1),
        units=units,
    )

    class DummyContext(ExecutionContext):
        def __init__(self) -> None:
            pass

        run_id = "test_run_roi"
        tenant_id = "default"
        project_id = "default"
        filename = "test.png"
        content_type = "image/png"
        pipeline_id = "ocr.document"
        pipeline_version = "1.0.0"
        asset_id = "asset_roi"
        source_id = "src_roi"
        production = False

        async def publish_partial_result(self, res: Any) -> None:
            pass

        async def report_progress(self, *args: Any, **kwargs: Any) -> None:
            pass

    # 测试圈选上半部分 ROI：只识别上半部分文字，且坐标正确映射
    res_top = await operator.execute(
        DummyContext(),
        {"batch": decoded},
        {"roi": [0.0, 0.0, 1.0, 0.5]},
    )
    blocks_top = res_top["result"].domain_payload.blocks
    assert len(blocks_top) == 1
    assert blocks_top[0].text == "TopText"
    assert blocks_top[0].polygon[0].y == 10.0

    # 测试圈选下半部分 ROI：只识别下半部分文字，且局部 y:20..40 成功映射为全局 y:70..90
    res_bottom = await operator.execute(
        DummyContext(),
        {"batch": decoded},
        {"roi": [0.0, 0.5, 1.0, 1.0]},
    )
    blocks_bottom = res_bottom["result"].domain_payload.blocks
    assert len(blocks_bottom) == 1
    assert blocks_bottom[0].text == "BottomText"
    assert blocks_bottom[0].polygon[0].y == 70.0
