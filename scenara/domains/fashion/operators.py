"""
服饰风格识别算子和引擎协议

提供 Cosplay 角色识别、服装风格检测和配饰分析能力。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Protocol

from scenara.platform.media_batch import DecodedMedia
from scenara.platform.models import (
    AccessoryDetection,
    ClothingStyle,
    CosplayDetection,
    FashionDomainPayload,
    MediaKind,
    MediaUnitResult,
    ModelProvenance,
    PipelineRef,
    ProvenanceEvidence,
    ResultEnvelope,
)
from scenara.platform.pipeline import DomainUnavailable, ExecutionContext, OperatorDefinition


class FashionEngine(Protocol):
    """服饰风格识别引擎协议"""

    model_id: str
    production_ready: bool
    version: str
    supported_characters: list[str]  # 支持的角色列表
    supported_styles: list[str]  # 支持的风格列表

    def detect_cosplay(
        self,
        image: Any,
        *,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]: ...

    def detect_clothing_style(
        self,
        image: Any,
        *,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]: ...

    def detect_accessories(
        self,
        image: Any,
        *,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]: ...


class DevelopmentFashionEngine:
    """开发环境服饰识别适配器,返回模拟结果"""

    model_id = "fashion-dev"
    production_ready = False
    version = "0.1.0"

    # 支持的 Cosplay 角色
    supported_characters = [
        "路飞", "索隆", "娜美",  # 海贼王
        "鸣人", "佐助", "小樱",  # 火影忍者
        "初音未来", "镜音双子",  # VOCALOID
        "蕾姆", "拉姆",  # Re:从零开始的异世界生活
    ]

    # 支持的服装风格
    supported_styles = [
        "jk_uniform", "lolita", "hanfu", "maid",
        "kimono", "qipao", "gothic", "vintage",
    ]

    def detect_cosplay(
        self,
        image: Any,
        *,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]:
        """返回模拟的 Cosplay 识别结果"""
        import random

        if random.random() < 0.3:  # 30% 概率检测到 Cosplay
            character = random.choice(self.supported_characters)
            series_map = {
                "路飞": "海贼王", "索隆": "海贼王", "娜美": "海贼王",
                "鸣人": "火影忍者", "佐助": "火影忍者", "小樱": "火影忍者",
                "初音未来": "VOCALOID", "镜音双子": "VOCALOID",
                "蕾姆": "Re:从零开始的异世界生活", "拉姆": "Re:从零开始的异世界生活",
            }
            return [{
                "character_name": character,
                "series_name": series_map.get(character, "未知"),
                "confidence": random.uniform(min_confidence, 0.95),
                "character_id": f"char_{random.randint(1000, 9999)}",
                "attributes": {
                    "hair_color": random.choice(["黑色", "金色", "蓝色", "粉色"]),
                    "costume_completeness": random.choice(["完整", "部分"]),
                },
            }]
        return []

    def detect_clothing_style(
        self,
        image: Any,
        *,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]:
        """返回模拟的服装风格识别结果"""
        import random

        style_labels = {
            "jk_uniform": "JK制服",
            "lolita": "洛丽塔",
            "hanfu": "汉服",
            "maid": "女仆装",
            "kimono": "和服",
            "qipao": "旗袍",
            "gothic": "哥特风",
            "vintage": "复古风",
        }

        sub_categories = {
            "jk_uniform": ["水手服", "西式", "中间服"],
            "lolita": ["甜系", "古典", "哥特"],
            "hanfu": ["唐制", "宋制", "明制"],
        }

        results = []
        num_styles = random.randint(0, 2)

        for _ in range(num_styles):
            style_type = random.choice(self.supported_styles)
            style_label = style_labels.get(style_type, style_type)
            confidence = random.uniform(min_confidence, 0.95)

            if confidence >= min_confidence:
                result = {
                    "style_type": style_type,
                    "style_label": style_label,
                    "confidence": confidence,
                    "attributes": {
                        "color": random.choice(["黑色", "白色", "粉色", "蓝色", "红色"]),
                        "pattern": random.choice(["纯色", "格纹", "印花", "刺绣"]),
                    },
                }

                if style_type in sub_categories:
                    result["sub_category"] = random.choice(sub_categories[style_type])

                results.append(result)

        return results

    def detect_accessories(
        self,
        image: Any,
        *,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]:
        """返回模拟的配饰识别结果"""
        import random

        accessory_types = {
            "wig": "假发",
            "prop": "道具",
            "jewelry": "首饰",
            "hat": "帽子",
            "bag": "包包",
        }

        results = []
        num_accessories = random.randint(0, 3)

        for i in range(num_accessories):
            accessory_type = random.choice(list(accessory_types.keys()))
            confidence = random.uniform(min_confidence, 0.90)

            if confidence >= min_confidence:
                results.append({
                    "accessory_type": accessory_type,
                    "accessory_label": accessory_types[accessory_type],
                    "confidence": confidence,
                    "color": random.choice(["黑色", "金色", "银色", "彩色"]),
                    "material": random.choice(["塑料", "金属", "布料", "皮革"]),
                })

        return results


class FashionRecognitionOperator:
    """服饰风格识别算子"""

    definition = OperatorDefinition(
        operator_id="fashion.style-recognition",
        version="1.0.0",
        domain="fashion",
        input_types={"batch": "media/batch"},
        resource_budget={"vram_mb": 4096, "cpu_cores": 2},
        max_batch_size=32,
        output_types={"result": "result/fashion"},
        timeout_seconds=1800,  # 30分钟
        resource_class="gpu",
        batchable=True,
    )

    def __init__(self, engine: FashionEngine | None = None) -> None:
        self._engine = engine

    async def execute(
        self,
        context: ExecutionContext,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        decoded = inputs["batch"]
        if not isinstance(decoded, DecodedMedia):
            raise TypeError("Fashion recognition requires a decoded media batch")

        # 初始化引擎
        if self._engine is None:
            loaded_engine = await asyncio.to_thread(lambda: DevelopmentFashionEngine())
            self._engine = loaded_engine

        engine = self._engine
        assert engine is not None

        # 提取参数
        min_confidence = float(parameters.get("min_confidence", 0.5))
        detect_cosplay = bool(parameters.get("detect_cosplay", True))
        detect_clothing = bool(parameters.get("detect_clothing", True))
        detect_accessories = bool(parameters.get("detect_accessories", True))

        # 检查生产就绪状态
        production_ready = bool(getattr(engine, "production_ready", False))
        if context.production and not production_ready:
            raise DomainUnavailable("Fashion engine is not approved for production")

        substitutes: list[str] = []
        if not production_ready:
            substitutes.append("fashion_engine")

        models = [
            ModelProvenance(
                capability="fashion_recognition",
                model_id=engine.model_id,
                version=engine.version,
                production_ready=production_ready,
            )
        ]

        # 收集结果
        cosplay_results: list[CosplayDetection] = []
        clothing_results: list[ClothingStyle] = []
        accessory_results: list[AccessoryDetection] = []
        units: list[MediaUnitResult] = []
        processed_units = 0

        cosplay_counter = 0
        clothing_counter = 0
        accessory_counter = 0

        def build_result(*, final: bool = False) -> ResultEnvelope:
            warnings = [f"development_substitute:{item}" for item in substitutes]
            if final and decoded.termination_reason:
                warnings.append(f"media_termination:{decoded.termination_reason}")

            # 生成摘要
            summary_parts = []
            if cosplay_results:
                characters = [c.character_name for c in cosplay_results]
                summary_parts.append(f"Cosplay角色: {', '.join(characters)}")
            if clothing_results:
                styles = [c.style_label for c in clothing_results]
                summary_parts.append(f"服装风格: {', '.join(set(styles))}")
            if accessory_results:
                summary_parts.append(f"配饰: {len(accessory_results)}个")

            summary = " | ".join(summary_parts) if summary_parts else "未检测到服饰风格特征"

            return ResultEnvelope(
                run_id=context.run_id,
                domain="fashion",
                pipeline=PipelineRef(pipeline_id=context.pipeline_id, version=context.pipeline_version),
                asset_id=context.asset_id,
                source_id=context.source_id,
                units=list(units),
                domain_payload=FashionDomainPayload(
                    cosplay=list(cosplay_results),
                    clothing_styles=list(clothing_results),
                    accessories=list(accessory_results),
                    summary=summary,
                ),
                models=models,
                media_metadata=decoded.metadata.model_copy(update={"sampled_units": processed_units}),
                warnings=warnings,
                provenance=ProvenanceEvidence(development_substitutes=substitutes),
                created_at=time.time(),
            )

        batch_size = 4 if decoded.kind == MediaKind.STREAM else 8

        try:
            async for chunk, expected_units in decoded.iter_batches(batch_size):
                for unit in chunk:
                    # Cosplay 识别
                    if detect_cosplay:
                        cosplay_detections = await asyncio.to_thread(
                            engine.detect_cosplay,
                            unit.image,
                            min_confidence=min_confidence,
                        )

                        for detection in cosplay_detections:
                            cosplay_counter += 1
                            cosplay_results.append(
                                CosplayDetection(
                                    detection_id=f"cosplay_{cosplay_counter}",
                                    character_name=detection["character_name"],
                                    series_name=detection["series_name"],
                                    confidence=detection["confidence"],
                                    character_id=detection.get("character_id"),
                                    attributes=detection.get("attributes", {}),
                                )
                            )

                    # 服装风格识别
                    if detect_clothing:
                        clothing_detections = await asyncio.to_thread(
                            engine.detect_clothing_style,
                            unit.image,
                            min_confidence=min_confidence,
                        )

                        for detection in clothing_detections:
                            clothing_counter += 1
                            clothing_results.append(
                                ClothingStyle(
                                    style_id=f"style_{clothing_counter}",
                                    style_type=detection["style_type"],
                                    style_label=detection["style_label"],
                                    confidence=detection["confidence"],
                                    sub_category=detection.get("sub_category"),
                                    attributes=detection.get("attributes", {}),
                                )
                            )

                    # 配饰识别
                    if detect_accessories:
                        accessory_detections = await asyncio.to_thread(
                            engine.detect_accessories,
                            unit.image,
                            min_confidence=min_confidence,
                        )

                        for detection in accessory_detections:
                            accessory_counter += 1
                            accessory_results.append(
                                AccessoryDetection(
                                    accessory_id=f"accessory_{accessory_counter}",
                                    accessory_type=detection["accessory_type"],
                                    accessory_label=detection["accessory_label"],
                                    confidence=detection["confidence"],
                                    color=detection.get("color"),
                                    material=detection.get("material"),
                                )
                            )

                    # 记录处理单元
                    units.append(
                        MediaUnitResult(
                            unit_id=unit.unit_id,
                            unit_type=unit.unit_type,
                            index=unit.index,
                            pts_ms=unit.pts_ms,
                            page_number=unit.page_number,
                            width=unit.width,
                            height=unit.height,
                        )
                    )

                processed_units += len(chunk)
                progress = (
                    None
                    if expected_units is None
                    else 0.03 + 0.94 * min(1.0, processed_units / max(1, expected_units))
                )

                # 流式发布部分结果
                if decoded.kind == MediaKind.STREAM:
                    await context.publish_partial_result(build_result())

                await context.report_progress(
                    progress,
                    stage="fashion",
                    processed_units=processed_units,
                    expected_units=expected_units,
                    latest_pts_ms=chunk[-1].pts_ms if chunk else None,
                )

        except BaseException:
            await decoded.close()
            raise

        return {"result": build_result(final=True)}


__all__ = [
    "FashionEngine",
    "DevelopmentFashionEngine",
    "FashionRecognitionOperator",
]
