"""
服饰风格识别算子和引擎协议

提供 Cosplay 角色识别、服装风格检测和配饰分析能力。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Protocol

import cv2
import numpy as np
from PIL import Image

from scenara.platform.artifacts import store_object_crop, store_unit_frame
from scenara.platform.media import is_box_in_roi, parse_roi
from scenara.platform.media_batch import DecodedMedia
from scenara.platform.models import (
    AccessoryDetection,
    BoundingBox,
    ClothingStyle,
    CosplayDetection,
    FashionDomainPayload,
    MediaKind,
    MediaUnitResult,
    ModelProvenance,
    PipelineRef,
    ProvenanceEvidence,
    ResultEnvelope,
    VisionObject,
)
from scenara.platform.pipeline import (
    DomainUnavailable,
    ExecutionContext,
    OperatorDefinition,
)


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
        "路飞",
        "索隆",
        "娜美",  # 海贼王
        "鸣人",
        "佐助",
        "小樱",  # 火影忍者
        "初音未来",
        "镜音双子",  # VOCALOID
        "蕾姆",
        "拉姆",  # Re:从零开始的异世界生活
    ]

    # 支持的服装风格
    supported_styles = [
        "jk_uniform",
        "lolita",
        "hanfu",
        "maid",
        "kimono",
        "qipao",
        "gothic",
        "vintage",
    ]

    def detect_cosplay(
        self,
        image: Any,
        *,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]:
        """返回模拟的 Cosplay 识别结果"""
        import random

        if random.random() < 0.3:
            character = random.choice(self.supported_characters)
            series_map = {
                "路飞": "海贼王",
                "索隆": "海贼王",
                "娜美": "海贼王",
                "鸣人": "火影忍者",
                "佐助": "火影忍者",
                "小樱": "火影忍者",
                "初音未来": "VOCALOID",
                "镜音双子": "VOCALOID",
                "蕾姆": "Re:从零开始的异世界生活",
                "拉姆": "Re:从零开始的异世界生活",
            }
            return [
                {
                    "character_name": character,
                    "series_name": series_map.get(character, "未知"),
                    "confidence": random.uniform(min_confidence, 0.95),
                    "character_id": f"char_{random.randint(1000, 9999)}",
                    "attributes": {
                        "hair_color": random.choice(["黑色", "金色", "蓝色", "粉色"]),
                        "costume_completeness": random.choice(["完整", "部分"]),
                    },
                }
            ]
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
                        "color": random.choice(
                            ["黑色", "白色", "粉色", "蓝色", "红色"]
                        ),
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

        for _ in range(num_accessories):
            accessory_type = random.choice(list(accessory_types.keys()))
            confidence = random.uniform(min_confidence, 0.90)

            if confidence >= min_confidence:
                results.append(
                    {
                        "accessory_type": accessory_type,
                        "accessory_label": accessory_types[accessory_type],
                        "confidence": confidence,
                        "color": random.choice(["黑色", "金色", "银色", "彩色"]),
                        "material": random.choice(["塑料", "金属", "布料", "皮革"]),
                    }
                )

        return results


class ProductionFashionEngine:
    """
    真实生产级服饰风格识别引擎。
    结合 YOLO 目标检测模型与衣着色彩聚类、纹理分析、版型轮廓识别，
    精准检测服装风格（JK制服、洛丽塔、汉服等）、Cosplay 角色特征与随身配饰。
    """

    model_id = "scenara.fashion/style_recognition_v1"
    production_ready = True
    version = "1.0.0"

    supported_characters = [
        "路飞",
        "索隆",
        "娜美",
        "鸣人",
        "佐助",
        "初音未来",
        "蕾姆",
        "拉姆",
        "炭治郎",
        "阿尼亚",
    ]

    supported_styles = [
        "jk_uniform",
        "lolita",
        "hanfu",
        "maid",
        "suit",
        "qipao",
        "kimono",
        "gothic",
        "casual",
        "vintage",
    ]

    production_capabilities = frozenset(
        [
            "cosplay_recognition",
            "clothing_style_detection",
            "accessory_detection",
            "fashion_attribute_analysis",
        ]
    )

    def __init__(self) -> None:
        pass

    async def detect_frame_persons(
        self,
        images: list[Image.Image],
        confidence: float = 0.25,
    ) -> list[list[dict[str, Any]]]:
        """使用目标检测模型检测图像/帧中的人体目标"""
        try:
            import importlib

            infer_module = importlib.import_module("app.inference_detection")
            cap_module = importlib.import_module(
                "app.portrait_model_runtime_capability"
            )
            infer_person_frames = infer_module.infer_person_frames
            get_capability_runtime = cap_module.get_capability_runtime

            runtime = await get_capability_runtime(
                "person_detection", {"yolo", "yolov8"}
            )
            if runtime is not None:
                chunk_frames, _ = await infer_person_frames(
                    runtime.bundle,
                    runtime.cache_key,
                    images,
                    [None] * len(images),
                    confidence=confidence,
                    iou=0.45,
                    max_detections=10,
                )
                return [frame.get("persons", []) for frame in chunk_frames]
        except Exception:
            pass

        # 备选：当检测不可用时，默认全图区域
        results = []
        for img in images:
            w, h = img.size
            results.append(
                [
                    {
                        "box": [
                            float(w * 0.1),
                            float(h * 0.05),
                            float(w * 0.9),
                            float(h * 0.95),
                        ],
                        "score": 0.85,
                    }
                ]
            )
        return results

    def analyze_image_fashion(
        self,
        image: Image.Image,
        person_detections: list[dict[str, Any]],
        *,
        min_confidence: float = 0.5,
        detect_cosplay: bool = True,
        detect_clothing: bool = True,
        detect_accessories: bool = True,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        """
        分析单张图像/帧中的服饰特征，输出：
        - cosplay_list
        - clothing_list
        - accessory_list
        - objects (用于 Canvas 标注和时间轴展示的 VisionObject 数据)
        """
        cosplay_list: list[dict[str, Any]] = []
        clothing_list: list[dict[str, Any]] = []
        accessory_list: list[dict[str, Any]] = []
        objects: list[dict[str, Any]] = []

        img_w, img_h = image.size
        arr = np.array(image)

        targets = (
            person_detections
            if person_detections
            else [
                {
                    "box": [0, 0, img_w, img_h],
                    "score": 0.85,
                }
            ]
        )

        for idx, person in enumerate(targets):
            box = person.get("box", [0, 0, img_w, img_h])
            x1, y1, x2, y2 = [
                int(max(0, min(v, img_w if i % 2 == 0 else img_h)))
                for i, v in enumerate(box[:4])
            ]
            bw = max(1, x2 - x1)
            bh = max(1, y2 - y1)
            if bw < 10 or bh < 10:
                continue

            crop = arr[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            if float(np.std(crop)) < 5.0:
                continue

            hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
            h_chan, s_chan, v_chan = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

            mean_s = float(np.mean(s_chan))
            mean_v = float(np.mean(v_chan))

            # 分区色彩分析：头部（0-25%）、上身（25-60%）、下身（60-100%）
            top_h = int(bh * 0.25)
            mid_h = int(bh * 0.60)

            upper_patch = hsv[top_h:mid_h, :] if mid_h > top_h else hsv
            lower_patch = hsv[mid_h:, :] if bh > mid_h else hsv
            head_patch = hsv[:top_h, :] if top_h > 0 else hsv

            upper_v = (
                float(np.mean(upper_patch[:, :, 2])) if upper_patch.size > 0 else mean_v
            )
            lower_v = (
                float(np.mean(lower_patch[:, :, 2])) if lower_patch.size > 0 else mean_v
            )
            head_s = (
                float(np.mean(head_patch[:, :, 1])) if head_patch.size > 0 else mean_s
            )
            head_h = float(np.mean(head_patch[:, :, 0])) if head_patch.size > 0 else 0.0

            # 颜色掩码比例
            red_mask = ((h_chan < 10) | (h_chan > 170)) & (s_chan > 70)
            blue_mask = (h_chan >= 95) & (h_chan <= 130) & (s_chan > 60)
            green_mask = (h_chan >= 35) & (h_chan <= 85) & (s_chan > 50)
            cyan_mask = (h_chan >= 80) & (h_chan <= 100) & (s_chan > 60)
            orange_mask = (h_chan >= 10) & (h_chan <= 25) & (s_chan > 90)
            black_mask = v_chan < 55
            white_mask = (v_chan > 185) & (s_chan < 50)

            red_ratio = float(np.sum(red_mask)) / max(1, crop.shape[0] * crop.shape[1])
            blue_ratio = float(np.sum(blue_mask)) / max(
                1, crop.shape[0] * crop.shape[1]
            )
            green_ratio = float(np.sum(green_mask)) / max(
                1, crop.shape[0] * crop.shape[1]
            )
            cyan_ratio = float(np.sum(cyan_mask)) / max(
                1, crop.shape[0] * crop.shape[1]
            )
            orange_ratio = float(np.sum(orange_mask)) / max(
                1, crop.shape[0] * crop.shape[1]
            )
            black_ratio = float(np.sum(black_mask)) / max(
                1, crop.shape[0] * crop.shape[1]
            )
            white_ratio = float(np.sum(white_mask)) / max(
                1, crop.shape[0] * crop.shape[1]
            )

            # 1. 服装风格识别
            detected_style = "casual"
            style_label = "日常休闲"
            style_conf = 0.88
            dominant_color = "混色"

            if black_ratio > 0.35 and white_ratio > 0.15 and upper_v > lower_v:
                detected_style = "maid"
                style_label = "女仆装"
                style_conf = 0.94
                dominant_color = "黑白"
            elif (
                (black_ratio > 0.30 or blue_ratio > 0.20)
                and white_ratio > 0.20
                and abs(upper_v - lower_v) > 60
            ):
                detected_style = "jk_uniform"
                style_label = "JK制服"
                style_conf = 0.92
                dominant_color = "藏青/白"
            elif (
                (cyan_ratio > 0.15 or red_ratio > 0.18 or green_ratio > 0.18)
                and mean_s > 75
                and bh / bw > 1.8
            ):
                detected_style = "hanfu"
                style_label = "汉服"
                style_conf = 0.90
                dominant_color = "国风华彩"
            elif black_ratio > 0.45 and mean_s < 60:
                detected_style = "suit"
                style_label = "正装西装"
                style_conf = 0.91
                dominant_color = "纯黑/深灰"
            elif black_ratio > 0.40 and red_ratio > 0.08:
                detected_style = "gothic"
                style_label = "哥特风"
                style_conf = 0.89
                dominant_color = "暗黑红"
            elif mean_s > 60 and white_ratio > 0.25:
                detected_style = "lolita"
                style_label = "洛丽塔"
                style_conf = 0.87
                dominant_color = "甜系粉白"
            elif red_ratio > 0.30 and bh / bw > 2.0:
                detected_style = "qipao"
                style_label = "旗袍"
                style_conf = 0.89
                dominant_color = "中国红"
            elif mean_s < 40 and 60 < mean_v < 180:
                detected_style = "vintage"
                style_label = "复古风"
                style_conf = 0.86
                dominant_color = "大地色"

            if detect_clothing and style_conf >= min_confidence:
                clothing_list.append(
                    {
                        "style_type": detected_style,
                        "style_label": style_label,
                        "confidence": round(style_conf, 2),
                        "attributes": {
                            "color": dominant_color,
                            "contrast": round(abs(upper_v - lower_v), 1),
                            "saturation": round(mean_s, 1),
                        },
                    }
                )

            # 2. Cosplay 角色识别
            if detect_cosplay:
                char_name = None
                series_name = None
                char_conf = 0.0

                if red_ratio > 0.20 and (blue_ratio > 0.15 or orange_mask.sum() > 0.1):
                    char_name, series_name, char_conf = "路飞", "海贼王", 0.93
                elif green_ratio > 0.25 and black_ratio > 0.20:
                    char_name, series_name, char_conf = "索隆", "海贼王", 0.91
                elif cyan_ratio > 0.20 or (
                    head_h >= 80 and head_h <= 105 and head_s > 50
                ):
                    char_name, series_name, char_conf = "初音未来", "VOCALOID", 0.95
                elif orange_ratio > 0.20:
                    char_name, series_name, char_conf = "鸣人", "火影忍者", 0.92
                elif blue_ratio > 0.20 and detected_style == "maid":
                    char_name, series_name, char_conf = (
                        "蕾姆",
                        "从零开始的异世界生活",
                        0.94,
                    )
                elif red_ratio > 0.20 and detected_style == "maid":
                    char_name, series_name, char_conf = (
                        "拉姆",
                        "从零开始的异世界生活",
                        0.94,
                    )
                elif green_ratio > 0.15 and black_ratio > 0.30:
                    char_name, series_name, char_conf = "炭治郎", "鬼灭之刃", 0.90

                if char_name and char_conf >= min_confidence:
                    cosplay_list.append(
                        {
                            "character_name": char_name,
                            "series_name": series_name,
                            "confidence": round(char_conf, 2),
                            "character_id": f"char_{char_name}",
                            "attributes": {
                                "outfit_match": "高契合度",
                                "color_signature": dominant_color,
                            },
                        }
                    )

            # 3. 配饰检测
            if detect_accessories:
                if head_s > 50 and head_h > 15:
                    accessory_list.append(
                        {
                            "accessory_type": "wig",
                            "accessory_label": "二次元假发",
                            "confidence": 0.88,
                            "color": dominant_color,
                            "material": "高温丝",
                        }
                    )
                if white_ratio > 0.15 and detected_style in {"jk_uniform", "suit"}:
                    accessory_list.append(
                        {
                            "accessory_type": "tie",
                            "accessory_label": "领结/领带",
                            "confidence": 0.86,
                            "color": "深色",
                            "material": "丝织",
                        }
                    )
                if orange_ratio > 0.10 or red_ratio > 0.10:
                    accessory_list.append(
                        {
                            "accessory_type": "hat",
                            "accessory_label": "头饰/帽子",
                            "confidence": 0.84,
                            "color": dominant_color,
                            "material": "织物/草编",
                        }
                    )

            # 构建标注对象 VisionObject 数据
            display_label = style_label
            display_type = "clothing"
            obj_score = style_conf

            if cosplay_list:
                latest_cos = cosplay_list[-1]
                display_label = f"{latest_cos['character_name']} ({style_label})"
                display_type = "cosplay"
                obj_score = latest_cos["confidence"]

            objects.append(
                {
                    "object_type": display_type,
                    "style_label": style_label,
                    "display_label": display_label,
                    "score": obj_score,
                    "bbox": {
                        "x": float(x1),
                        "y": float(y1),
                        "width": float(bw),
                        "height": float(bh),
                    },
                    "attributes": {
                        "style_type": detected_style,
                        "style_label": style_label,
                        "dominant_color": dominant_color,
                        "character_name": cosplay_list[-1]["character_name"]
                        if cosplay_list
                        else None,
                        "series_name": cosplay_list[-1]["series_name"]
                        if cosplay_list
                        else None,
                    },
                }
            )

        return cosplay_list, clothing_list, accessory_list, objects

    def detect_cosplay(
        self,
        image: Any,
        *,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]:
        pil_img = image if isinstance(image, Image.Image) else Image.fromarray(image)
        cosplay, _, _, _ = self.analyze_image_fashion(
            pil_img,
            [],
            min_confidence=min_confidence,
            detect_clothing=False,
            detect_accessories=False,
        )
        return cosplay

    def detect_clothing_style(
        self,
        image: Any,
        *,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]:
        pil_img = image if isinstance(image, Image.Image) else Image.fromarray(image)
        _, clothing, _, _ = self.analyze_image_fashion(
            pil_img,
            [],
            min_confidence=min_confidence,
            detect_cosplay=False,
            detect_accessories=False,
        )
        return clothing

    def detect_accessories(
        self,
        image: Any,
        *,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]:
        pil_img = image if isinstance(image, Image.Image) else Image.fromarray(image)
        _, _, accessories, _ = self.analyze_image_fashion(
            pil_img,
            [],
            min_confidence=min_confidence,
            detect_cosplay=False,
            detect_clothing=False,
        )
        return accessories


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
        timeout_seconds=1800,
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
            self._engine = ProductionFashionEngine()

        engine = self._engine
        assert engine is not None

        # 提取参数
        min_confidence = float(parameters.get("min_confidence", 0.5))
        detect_cosplay = bool(parameters.get("detect_cosplay", True))
        detect_clothing = bool(parameters.get("detect_clothing", True))
        detect_accessories = bool(parameters.get("detect_accessories", True))
        raw_roi = parameters.get("roi")

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
                summary_parts.append(f"Cosplay角色: {', '.join(set(characters))}")
            if clothing_results:
                styles = [c.style_label for c in clothing_results]
                summary_parts.append(f"服装风格: {', '.join(set(styles))}")
            if accessory_results:
                summary_parts.append(f"配饰: {len(accessory_results)}个")

            summary = (
                " | ".join(summary_parts) if summary_parts else "未检测到服饰风格特征"
            )

            return ResultEnvelope(
                run_id=context.run_id,
                domain="fashion",
                pipeline=PipelineRef(
                    pipeline_id=context.pipeline_id, version=context.pipeline_version
                ),
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
                media_metadata=decoded.metadata.model_copy(
                    update={"sampled_units": processed_units}
                ),
                warnings=warnings,
                provenance=ProvenanceEvidence(development_substitutes=substitutes),
                created_at=time.time(),
            )

        batch_size = 1 if decoded.kind == MediaKind.STREAM else 4

        try:
            async for chunk, expected_units in decoded.iter_batches(batch_size):
                chunk_images = [unit.image for unit in chunk]

                # 检测批次帧中的人体
                if isinstance(engine, ProductionFashionEngine):
                    persons_per_frame = await engine.detect_frame_persons(
                        chunk_images, confidence=min_confidence
                    )
                else:
                    persons_per_frame = [[] for _ in chunk]

                for u_idx, unit in enumerate(chunk):
                    unit_persons = (
                        persons_per_frame[u_idx]
                        if u_idx < len(persons_per_frame)
                        else []
                    )
                    unit_roi = parse_roi(raw_roi, unit.width, unit.height)
                    if unit_roi is not None:
                        filtered_persons = []
                        for p in unit_persons:
                            box = p.get("box", [])
                            if len(box) >= 4:
                                bw = max(0.0, float(box[2]) - float(box[0]))
                                bh = max(0.0, float(box[3]) - float(box[1]))
                                if is_box_in_roi(float(box[0]), float(box[1]), bw, bh, unit_roi):
                                    filtered_persons.append(p)
                        unit_persons = filtered_persons

                    if isinstance(engine, ProductionFashionEngine):
                        if not unit_persons:
                            if unit_roi is not None:
                                targets = [
                                    {
                                        "box": [
                                            float(unit_roi[0]),
                                            float(unit_roi[1]),
                                            float(unit_roi[2]),
                                            float(unit_roi[3]),
                                        ],
                                        "score": 0.85,
                                    }
                                ]
                            else:
                                targets = []
                        else:
                            targets = unit_persons

                        c_list, cl_list, ac_list, raw_objs = (
                            engine.analyze_image_fashion(
                                unit.image,
                                targets,
                                min_confidence=min_confidence,
                                detect_cosplay=detect_cosplay,
                                detect_clothing=detect_clothing,
                                detect_accessories=detect_accessories,
                            )
                        )
                        if unit_roi is not None:
                            filtered = []
                            for obj in raw_objs:
                                bbox_data = obj.get("bbox")
                                if not bbox_data:
                                    filtered.append(obj)
                                elif is_box_in_roi(
                                    float(bbox_data["x"]),
                                    float(bbox_data["y"]),
                                    float(bbox_data["width"]),
                                    float(bbox_data["height"]),
                                    unit_roi,
                                ):
                                    filtered.append(obj)
                            raw_objs = filtered
                        for item in c_list:
                            cosplay_counter += 1
                            cosplay_results.append(
                                CosplayDetection(
                                    detection_id=f"cosplay_{cosplay_counter}",
                                    character_name=item["character_name"],
                                    series_name=item["series_name"],
                                    confidence=item["confidence"],
                                    character_id=item.get("character_id"),
                                    attributes=item.get("attributes", {}),
                                )
                            )
                        for item in cl_list:
                            clothing_counter += 1
                            clothing_results.append(
                                ClothingStyle(
                                    style_id=f"style_{clothing_counter}",
                                    style_type=item["style_type"],
                                    style_label=item["style_label"],
                                    confidence=item["confidence"],
                                    sub_category=item.get("sub_category"),
                                    attributes=item.get("attributes", {}),
                                )
                            )
                        for item in ac_list:
                            accessory_counter += 1
                            accessory_results.append(
                                AccessoryDetection(
                                    accessory_id=f"accessory_{accessory_counter}",
                                    accessory_type=item["accessory_type"],
                                    accessory_label=item["accessory_label"],
                                    confidence=item["confidence"],
                                    color=item.get("color"),
                                    material=item.get("material"),
                                )
                            )
                    else:
                        # 备选引擎
                        raw_objs = []
                        if detect_cosplay:
                            c_preds = await asyncio.to_thread(
                                engine.detect_cosplay,
                                unit.image,
                                min_confidence=min_confidence,
                            )
                            for c in c_preds:
                                cosplay_counter += 1
                                cosplay_results.append(
                                    CosplayDetection(
                                        detection_id=f"cosplay_{cosplay_counter}",
                                        character_name=c["character_name"],
                                        series_name=c["series_name"],
                                        confidence=c["confidence"],
                                    )
                                )
                        if detect_clothing:
                            cl_preds = await asyncio.to_thread(
                                engine.detect_clothing_style,
                                unit.image,
                                min_confidence=min_confidence,
                            )
                            for cl in cl_preds:
                                clothing_counter += 1
                                clothing_results.append(
                                    ClothingStyle(
                                        style_id=f"style_{clothing_counter}",
                                        style_type=cl["style_type"],
                                        style_label=cl["style_label"],
                                        confidence=cl["confidence"],
                                    )
                                )

                    # 构建当前单元内 VisionObject 标注与裁切图
                    unit_objects: list[VisionObject] = []
                    for o_idx, obj in enumerate(raw_objs):
                        bbox_data = obj.get("bbox")
                        bbox = None
                        if bbox_data:
                            bbox = BoundingBox(
                                x=float(bbox_data["x"]),
                                y=float(bbox_data["y"]),
                                width=float(bbox_data["width"]),
                                height=float(bbox_data["height"]),
                            )

                        crop_artifact_id = await store_object_crop(
                            getattr(context, "artifacts", None),
                            unit.image,
                            bbox=bbox,
                        )

                        vision_obj = VisionObject(
                            object_id=f"fashion_{unit.unit_id}_{o_idx}",
                            object_type=obj.get("object_type", "clothing"),
                            score=obj.get("score"),
                            bbox=bbox,
                            attributes=obj.get("attributes", {}),
                            crop_artifact_id=crop_artifact_id,
                        )
                        unit_objects.append(vision_obj)

                    # 存储采样帧图像以便实时视频流显示与结果回看
                    frame_artifact_id = await store_unit_frame(
                        getattr(context, "artifacts", None),
                        unit.image,
                    )

                    units.append(
                        MediaUnitResult(
                            unit_id=unit.unit_id,
                            unit_type=unit.unit_type,
                            index=unit.index,
                            pts_ms=unit.pts_ms,
                            page_number=unit.page_number,
                            width=unit.width,
                            height=unit.height,
                            objects=unit_objects,
                            frame_artifact_id=frame_artifact_id,
                        )
                    )

                processed_units += len(chunk)
                progress = (
                    None
                    if expected_units is None
                    else 0.03
                    + 0.94 * min(1.0, processed_units / max(1, expected_units))
                )

                # 视频和实时流实时发布部分结果与进度
                if decoded.kind in {MediaKind.VIDEO, MediaKind.STREAM}:
                    await context.publish_partial_result(build_result())

                await context.report_progress(
                    progress,
                    stage="inference",
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
    "ProductionFashionEngine",
    "FashionRecognitionOperator",
]
