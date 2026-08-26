import pytest
from PIL import Image, ImageDraw
from uuid import uuid4

from scenara.domains.behavior.operators import (
    BehaviorRecognitionOperator,
    ProductionBehaviorEngine,
)
from scenara.domains.fashion.operators import (
    FashionRecognitionOperator,
    ProductionFashionEngine,
)
from scenara.platform.media_batch import DecodedMedia, DecodedMediaUnit
from scenara.platform.models import MediaKind, MediaTechnicalMetadata
from scenara.platform.pipeline import ExecutionContext


class DummyArtifacts:
    def __init__(self) -> None:
        self.stored: dict[str, Image.Image] = {}

    async def store_image(
        self, image: Image.Image, *, artifact_type: str
    ) -> str | None:
        art_id = f"{artifact_type}_{uuid4().hex[:8]}"
        self.stored[art_id] = image
        return art_id


@pytest.mark.asyncio
async def test_behavior_operator_real_execution() -> None:
    artifacts = DummyArtifacts()
    context = ExecutionContext(
        run_id="run_behavior_test_1",
        tenant_id="tenant_default",
        project_id="project_default",
        pipeline_id="behavior.recognition",
        pipeline_version="1.0.0",
        asset_id="asset_test_1",
        source_id=None,
        filename="test_video.mp4",
        content_type="video/mp4",
        artifacts=artifacts,
    )

    # 创建 4 帧测试视频序列，模拟人形移动
    images = []
    for i in range(4):
        img = Image.new("RGB", (320, 240), (220, 220, 220))
        draw = ImageDraw.Draw(img)
        # 绘制人形区域
        x = 50 + i * 15
        draw.rectangle([x, 40, x + 50, 180], fill=(50, 100, 200))
        images.append(img)

    units = [
        DecodedMediaUnit(
            unit_id=f"unit_{i}",
            unit_type="frame",
            index=i,
            pts_ms=i * 250,
            image=img,
        )
        for i, img in enumerate(images)
    ]

    decoded = DecodedMedia(
        kind=MediaKind.VIDEO,
        units=units,
        metadata=MediaTechnicalMetadata(
            width=320,
            height=240,
            duration_ms=1000,
            sampled_units=4,
        ),
    )

    operator = BehaviorRecognitionOperator(ProductionBehaviorEngine())
    output = await operator.execute(
        context, {"batch": decoded}, {"min_confidence": 0.3}
    )

    result = output["result"]
    assert result.domain == "behavior"
    assert len(result.units) == 4
    # 验证每帧均持久化采样帧与检测对象
    for unit in result.units:
        assert unit.frame_artifact_id is not None
        assert len(unit.objects) >= 1
        obj = unit.objects[0]
        assert obj.bbox is not None
        assert obj.score is not None
        assert "action_label" in obj.attributes
    # 验证无开发替代警告
    assert not any("development_substitute" in w for w in result.warnings)
    assert len(result.domain_payload.actions) >= 1


@pytest.mark.asyncio
async def test_fashion_operator_real_execution() -> None:
    artifacts = DummyArtifacts()
    context = ExecutionContext(
        run_id="run_fashion_test_1",
        tenant_id="tenant_default",
        project_id="project_default",
        pipeline_id="fashion.recognition",
        pipeline_version="1.0.0",
        asset_id="asset_test_2",
        source_id=None,
        filename="test_image.jpg",
        content_type="image/jpeg",
        artifacts=artifacts,
    )

    # 创建测试服装图像（模拟 JK 制服黑白对比）
    img = Image.new("RGB", (320, 400), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    # 上身白色衬衫
    draw.rectangle([80, 80, 240, 220], fill=(255, 255, 255))
    # 下身深蓝裙子
    draw.rectangle([80, 220, 240, 360], fill=(20, 30, 60))

    units = [
        DecodedMediaUnit(
            unit_id="unit_fashion_0",
            unit_type="frame",
            index=0,
            pts_ms=0,
            image=img,
        )
    ]

    decoded = DecodedMedia(
        kind=MediaKind.IMAGE,
        units=units,
        metadata=MediaTechnicalMetadata(
            width=320,
            height=400,
            sampled_units=1,
        ),
    )

    operator = FashionRecognitionOperator(ProductionFashionEngine())
    output = await operator.execute(
        context, {"batch": decoded}, {"min_confidence": 0.3}
    )

    result = output["result"]
    assert result.domain == "fashion"
    assert len(result.units) == 1
    unit = result.units[0]
    assert unit.frame_artifact_id is not None
    assert len(unit.objects) >= 1
    obj = unit.objects[0]
    assert obj.bbox is not None
    assert obj.score is not None
    assert "style_label" in obj.attributes
    # 验证无开发替代警告
    assert not any("development_substitute" in w for w in result.warnings)
    assert len(result.domain_payload.clothing_styles) >= 1


@pytest.mark.asyncio
async def test_fashion_roi_filtering() -> None:
    artifacts = DummyArtifacts()
    context = ExecutionContext(
        run_id="run_fashion_roi_test",
        tenant_id="tenant_default",
        project_id="project_default",
        pipeline_id="fashion.recognition",
        pipeline_version="1.0.0",
        asset_id="asset_test_roi",
        source_id=None,
        filename="test_image.jpg",
        content_type="image/jpeg",
        artifacts=artifacts,
    )

    img = Image.new("RGB", (320, 400), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle([80, 80, 240, 220], fill=(255, 255, 255))
    draw.rectangle([80, 220, 240, 360], fill=(20, 30, 60))

    units = [
        DecodedMediaUnit(
            unit_id="unit_fashion_0",
            unit_type="frame",
            index=0,
            pts_ms=0,
            image=img,
        )
    ]
    decoded = DecodedMedia(
        kind=MediaKind.IMAGE,
        units=units,
        metadata=MediaTechnicalMetadata(width=320, height=400, sampled_units=1),
    )
    operator = FashionRecognitionOperator(ProductionFashionEngine())

    # 1. 圈选包含人体的区域：应检测到目标
    output_inside = await operator.execute(
        context,
        {"batch": decoded},
        {"min_confidence": 0.3, "roi": [0.1, 0.1, 0.9, 0.9]},
    )
    assert len(output_inside["result"].units[0].objects) >= 1

    # 2. 圈选与人体不相交的极小角落区域：应全部过滤，对象数为 0
    output_outside = await operator.execute(
        context,
        {"batch": decoded},
        {"min_confidence": 0.3, "roi": [0.0, 0.0, 0.1, 0.1]},
    )
    assert len(output_outside["result"].units[0].objects) == 0


@pytest.mark.asyncio
async def test_behavior_roi_filtering() -> None:
    artifacts = DummyArtifacts()
    context = ExecutionContext(
        run_id="run_behavior_roi_test",
        tenant_id="tenant_default",
        project_id="project_default",
        pipeline_id="behavior.recognition",
        pipeline_version="1.0.0",
        asset_id="asset_test_roi",
        source_id=None,
        filename="test_video.mp4",
        content_type="video/mp4",
        artifacts=artifacts,
    )

    img = Image.new("RGB", (320, 240), (200, 200, 200))
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 40, 220, 200], fill=(255, 0, 0))

    units = [
        DecodedMediaUnit(
            unit_id="unit_b_0",
            unit_type="frame",
            index=0,
            pts_ms=0,
            image=img,
        )
    ]
    decoded = DecodedMedia(
        kind=MediaKind.VIDEO,
        units=units,
        metadata=MediaTechnicalMetadata(width=320, height=240, sampled_units=1),
    )
    operator = BehaviorRecognitionOperator(ProductionBehaviorEngine())

    # 1. 圈选与人体不相交的区域：应过滤，帧对象数为 0
    output_outside = await operator.execute(
        context,
        {"batch": decoded},
        {"min_confidence": 0.3, "roi": [0.0, 0.0, 0.1, 0.1]},
    )
    # 因为 objects 为空且是视频模式，无检测对象的单元不生成空 unit_result
    assert len(output_outside["result"].units) == 0 or len(output_outside["result"].units[0].objects) == 0

    # 2. 圈选覆盖整图的区域：应检测出人体并保留
    output_inside = await operator.execute(
        context,
        {"batch": decoded},
        {"min_confidence": 0.3, "roi": [0.0, 0.0, 1.0, 1.0]},
    )
    assert len(output_inside["result"].units) >= 1
    assert len(output_inside["result"].units[0].objects) >= 1
