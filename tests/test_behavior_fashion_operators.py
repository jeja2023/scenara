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


@pytest.mark.asyncio
async def test_fashion_cosplay_vs_casual_accuracy() -> None:
    """测试二次元 Cosplay 精确识别与普通人日常休闲风格区分"""
    from scenara.domains.fashion.operators import ProductionFashionEngine

    engine = ProductionFashionEngine()

    # 1. 模拟普通人：黑色头发 (RGB 20, 20, 20) + 白色 T 恤 (RGB 240, 240, 240) + 灰色裤子 (RGB 80, 80, 80)
    casual_img = Image.new("RGB", (200, 400), (220, 220, 220))
    draw_c = ImageDraw.Draw(casual_img)
    draw_c.rectangle([50, 10, 150, 90], fill=(20, 20, 20))  # 黑发
    draw_c.rectangle([40, 90, 160, 240], fill=(240, 240, 240))  # 白T恤
    draw_c.rectangle([50, 240, 150, 390], fill=(80, 80, 80))  # 灰裤

    # 1. 默认 filter_casual=True: 普通路人不生成目标对象
    cosplay_list, clothing_list, _, objs = engine.analyze_image_fashion(
        casual_img,
        [{"box": [0, 0, 200, 400], "score": 0.9}],
        filter_casual=True,
    )
    assert len(cosplay_list) == 0
    assert len(objs) == 0  # 普通人被成功过滤

    # 2. filter_casual=False: 保留普通路人但严格分类为日常休闲，不误判初音未来
    _, cl_list_unfiltered, _, objs_unfiltered = engine.analyze_image_fashion(
        casual_img,
        [{"box": [0, 0, 200, 400], "score": 0.9}],
        filter_casual=False,
    )
    assert any(c["style_type"] == "casual" for c in cl_list_unfiltered)
    assert objs_unfiltered[0]["object_type"] == "clothing"
    assert objs_unfiltered[0]["attributes"]["is_cosplay"] is False
    assert objs_unfiltered[0]["attributes"]["character_name"] is None

    # 3. 模拟二次元银白发 Cosplay (如艾米莉亚/白发角色)
    silver_cosplay_img = Image.new("RGB", (200, 400), (220, 220, 220))
    draw_s = ImageDraw.Draw(silver_cosplay_img)
    draw_s.rectangle([50, 10, 150, 90], fill=(245, 245, 250))  # 银白发
    draw_s.rectangle([40, 90, 160, 240], fill=(200, 180, 230))  # 浅紫二次元服
    draw_s.rectangle([50, 240, 150, 390], fill=(255, 255, 255))

    cos_list_s, _, acc_list_s, objs_s = engine.analyze_image_fashion(
        silver_cosplay_img,
        [{"box": [0, 0, 200, 400], "score": 0.9}],
        filter_casual=True,
    )
    assert len(cos_list_s) >= 1
    assert "白发" in cos_list_s[0]["character_name"] or "艾米莉亚" in cos_list_s[0]["character_name"]
    assert objs_s[0]["object_type"] == "cosplay"
    assert objs_s[0]["attributes"]["is_cosplay"] is True
    assert any("假发" in acc["accessory_label"] for acc in acc_list_s)


@pytest.mark.asyncio
async def test_fashion_no_false_positive_gothic_or_lolita() -> None:
    """测试普通黑色外套不被误判为哥特风，普通白衬衫不被误判为洛丽塔"""
    engine = ProductionFashionEngine()

    # 1. 普通人穿普通黑色外套 + 牛仔裤 + 黑发
    black_jacket_img = Image.new("RGB", (200, 400), (220, 220, 220))
    draw_bj = ImageDraw.Draw(black_jacket_img)
    draw_bj.rectangle([50, 10, 150, 80], fill=(25, 25, 25))  # 黑发
    draw_bj.rectangle([40, 80, 160, 220], fill=(20, 20, 25))  # 黑外套
    draw_bj.rectangle([50, 220, 150, 390], fill=(50, 70, 120))  # 蓝牛仔裤

    _, cl_bj, _, _ = engine.analyze_image_fashion(
        black_jacket_img,
        [{"box": [0, 0, 200, 400], "score": 0.9}],
        filter_casual=False,
    )
    assert any(c["style_type"] == "casual" for c in cl_bj)
    assert not any(c["style_type"] == "gothic" for c in cl_bj)

    # 2. 普通人穿白色T恤 + 浅蓝牛仔裤 + 黑发
    white_tshirt_img = Image.new("RGB", (200, 400), (220, 220, 220))
    draw_wt = ImageDraw.Draw(white_tshirt_img)
    draw_wt.rectangle([50, 10, 150, 80], fill=(30, 25, 20))  # 黑发
    draw_wt.rectangle([40, 80, 160, 220], fill=(250, 250, 250))  # 白T恤
    draw_wt.rectangle([50, 220, 150, 390], fill=(100, 140, 200))  # 牛仔裤

    _, cl_wt, _, _ = engine.analyze_image_fashion(
        white_tshirt_img,
        [{"box": [0, 0, 200, 400], "score": 0.9}],
        filter_casual=False,
    )
    assert any(c["style_type"] == "casual" for c in cl_wt)
    assert not any(c["style_type"] == "lolita" for c in cl_wt)


@pytest.mark.asyncio
async def test_fashion_purple_and_gold_cosplay_recognition() -> None:
    """测试紫发与金发等全谱系二次元 Cosplay 精准识别"""
    engine = ProductionFashionEngine()

    # 1. 紫发 Cosplay (雷电将军/刻晴)
    purple_cos_img = Image.new("RGB", (200, 400), (220, 220, 220))
    draw_p = ImageDraw.Draw(purple_cos_img)
    draw_p.rectangle([50, 10, 150, 90], fill=(160, 60, 220))  # 紫发
    draw_p.rectangle([40, 90, 160, 240], fill=(140, 50, 190))  # 紫色战袍
    draw_p.rectangle([50, 240, 150, 390], fill=(40, 30, 60))

    cos_p, _, acc_p, objs_p = engine.analyze_image_fashion(
        purple_cos_img,
        [{"box": [0, 0, 200, 400], "score": 0.9}],
        filter_casual=True,
    )
    assert len(cos_p) >= 1
    assert "紫发" in cos_p[0]["character_name"] or "雷电将军" in cos_p[0]["character_name"]
    assert objs_p[0]["object_type"] == "cosplay"
    assert any("紫" in a["accessory_label"] for a in acc_p)

    # 2. 金发 Cosplay (Saber / 金发二次元)
    gold_cos_img = Image.new("RGB", (200, 400), (220, 220, 220))
    draw_g = ImageDraw.Draw(gold_cos_img)
    draw_g.rectangle([50, 10, 150, 90], fill=(255, 215, 0))  # 金发
    draw_g.rectangle([40, 90, 160, 240], fill=(20, 50, 160))  # 蓝铠甲
    draw_g.rectangle([50, 240, 150, 390], fill=(240, 240, 250))

    cos_g, _, acc_g, objs_g = engine.analyze_image_fashion(
        gold_cos_img,
        [{"box": [0, 0, 200, 400], "score": 0.9}],
        filter_casual=True,
    )
    assert len(cos_g) >= 1
    assert "Saber" in cos_g[0]["character_name"] or "金发" in cos_g[0]["character_name"]
    assert objs_g[0]["object_type"] == "cosplay"
    assert any("金" in a["accessory_label"] for a in acc_g)


@pytest.mark.asyncio
async def test_fashion_blue_polo_and_safety_vest_not_cosplay() -> None:
    """测试蓝色条纹Polo衫不被误判为蓝发，黄色反光背心保安不被误判为金发魔法少女"""
    engine = ProductionFashionEngine()

    # 1. 穿蓝色条纹 Polo 衫的黑发男士（肩膀胸口有蓝色条纹）
    polo_img = Image.new("RGB", (200, 400), (220, 220, 220))
    draw_polo = ImageDraw.Draw(polo_img)
    # 顶部中心是正常黑发
    draw_polo.rectangle([70, 5, 130, 55], fill=(20, 20, 20))
    # 上身 Polo 衫是蓝色横条纹 (从 y=60 开始)
    draw_polo.rectangle([40, 60, 160, 220], fill=(40, 80, 180))
    draw_polo.rectangle([50, 220, 150, 390], fill=(30, 30, 30))  # 黑裤

    cos_polo, cl_polo, _, objs_polo = engine.analyze_image_fashion(
        polo_img,
        [{"box": [0, 0, 200, 400], "score": 0.9}],
        filter_casual=True,
    )
    # 默认 filter_casual=True: 普通路人被干净过滤，不产生误判
    assert len(cos_polo) == 0
    assert len(objs_polo) == 0

    # 2. 穿黄色反光背心的黑发保安（肩膀胸口有高亮荧光黄）
    vest_img = Image.new("RGB", (200, 400), (220, 220, 220))
    draw_vest = ImageDraw.Draw(vest_img)
    # 顶部中心是正常黑发戴大檐帽
    draw_vest.rectangle([70, 5, 130, 55], fill=(30, 30, 35))
    # 上身是高亮荧光黄反光背心 (从 y=60 开始)
    draw_vest.rectangle([40, 60, 160, 220], fill=(240, 230, 30))
    draw_vest.rectangle([50, 220, 150, 390], fill=(30, 30, 30))

    cos_vest, cl_vest, _, objs_vest = engine.analyze_image_fashion(
        vest_img,
        [{"box": [0, 0, 200, 400], "score": 0.9}],
        filter_casual=True,
    )
    assert len(cos_vest) == 0
    assert len(objs_vest) == 0


@pytest.mark.asyncio
async def test_fashion_white_shirt_black_shorts_not_maid() -> None:
    """测试白T恤黑短裤普通女士不被误判为女仆Cosplay角色"""
    engine = ProductionFashionEngine()

    girl_img = Image.new("RGB", (200, 400), (220, 220, 220))
    draw_g = ImageDraw.Draw(girl_img)
    draw_g.rectangle([70, 5, 130, 55], fill=(40, 30, 25))  # 黑发/深褐发
    draw_g.rectangle([40, 60, 160, 200], fill=(245, 245, 245))  # 白短袖
    draw_g.rectangle([50, 200, 150, 300], fill=(20, 20, 20))  # 黑短裤
    draw_g.rectangle([60, 300, 140, 390], fill=(220, 190, 170))  # 腿部

    cos_g, cl_g, _, objs_g = engine.analyze_image_fashion(
        girl_img,
        [{"box": [0, 0, 200, 400], "score": 0.9}],
        filter_casual=True,
    )
    assert len(cos_g) == 0
    assert len(objs_g) == 0


@pytest.mark.asyncio
async def test_fashion_dark_haired_anime_warrior_and_white_lolita_recognition() -> None:
    """测试黑发/深发二次元战袍（如商场监控中的蓝黑ACG战袍）与白色洛丽塔精准识别"""
    engine = ProductionFashionEngine()

    # 1. 穿蓝黑交领战袍的黑发 Cosplayer（黑发 + 蓝色上衣 + 黑色长裤）
    warrior_img = Image.new("RGB", (200, 400), (220, 220, 220))
    draw_w = ImageDraw.Draw(warrior_img)
    draw_w.rectangle([70, 5, 130, 55], fill=(25, 25, 30))  # 黑发假发
    draw_w.rectangle([40, 60, 160, 200], fill=(20, 60, 160))  # 宝蓝战袍上装
    draw_w.rectangle([50, 200, 150, 225], fill=(245, 245, 250))  # 白色腰封/束带
    draw_w.rectangle([50, 225, 150, 390], fill=(25, 25, 30))  # 黑色战靴裤装

    cos_w, cl_w, acc_w, objs_w = engine.analyze_image_fashion(
        warrior_img,
        [{"box": [0, 0, 200, 400], "score": 0.9}],
        filter_casual=True,
    )
    assert len(cos_w) >= 1 or len(cl_w) >= 1
    assert len(objs_w) >= 1
    assert any("二次元" in c["character_name"] or "战袍" in c["character_name"] for c in cos_w)
    assert objs_w[0]["attributes"]["is_cosplay"] is True

    # 2. 穿白色洛丽塔连衣裙的女生（黑发/发箍 + 纯白蕾丝长裙）
    lolita_img = Image.new("RGB", (200, 400), (220, 220, 220))
    draw_l = ImageDraw.Draw(lolita_img)
    draw_l.rectangle([70, 5, 130, 55], fill=(30, 25, 25))  # 黑发
    draw_l.rectangle([40, 60, 160, 360], fill=(245, 245, 250))  # 纯白蓬蓬裙

    cos_l, cl_l, acc_l, objs_l = engine.analyze_image_fashion(
        lolita_img,
        [{"box": [0, 0, 200, 400], "score": 0.9}],
        filter_casual=True,
    )
    assert len(cl_l) >= 1
    assert any(c["style_type"] == "lolita" for c in cl_l)
    assert len(objs_l) >= 1




