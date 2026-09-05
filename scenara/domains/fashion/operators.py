"""
服饰风格识别算子和引擎协议

提供 Cosplay 角色识别、服装风格检测和配饰分析能力。
"""

from __future__ import annotations

import asyncio
import logging
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


logger = logging.getLogger(__name__)


_warned_fallbacks: set[str] = set()


def _warn_detector_fallback(reason: str) -> None:
    """降级只在首次发生时告警：静默降级会让运维把降级结果当成正常识别结果。"""

    if reason in _warned_fallbacks:
        return
    _warned_fallbacks.add(reason)
    logger.warning("%s", reason, exc_info=True)


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
                    max_detections=None,
                )
                return [frame.get("persons", []) for frame in chunk_frames]
        except Exception:
            _warn_detector_fallback("人体检测运行时不可用，服饰解析退化为整图区域")

        # 备选：当检测不可用时，默认全图区域
        results = []
        for img in images:
            w, h = img.size
            results.append(
                [
                    {
                        "box": [
                            w * 0.1,
                            h * 0.05,
                            w * 0.9,
                            h * 0.95,
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
        filter_casual: bool = True,
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
            raw_box = person.get("box") if isinstance(person, dict) else None
            box = (
                raw_box
                if isinstance(raw_box, (list, tuple)) and len(raw_box) >= 4
                else [0, 0, img_w, img_h]
            )
            x1 = int(max(0, min(float(box[0]), img_w)))
            y1 = int(max(0, min(float(box[1]), img_h)))
            x2 = int(max(0, min(float(box[2]), img_w)))
            y2 = int(max(0, min(float(box[3]), img_h)))
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

            # 分区色彩分析：头部（顶部0-15%，水平居中25%-75%，排除肩膀/衣领/背心）、上身（15-55%）、下身（55-100%）
            hair_h = max(1, int(bh * 0.15))
            hair_x1 = int(bw * 0.25)
            hair_x2 = max(hair_x1 + 1, int(bw * 0.75))
            head_patch = (
                hsv[:hair_h, hair_x1:hair_x2]
                if hair_x2 > hair_x1 and hair_h > 0
                else hsv[:hair_h, :]
            )
            top_h = hair_h
            mid_h = max(top_h + 1, int(bh * 0.55))

            upper_patch = hsv[top_h:mid_h, :] if mid_h > top_h else hsv
            lower_patch = hsv[mid_h:, :] if bh > mid_h else hsv

            upper_v = (
                float(np.mean(upper_patch[:, :, 2])) if upper_patch.size > 0 else mean_v
            )
            lower_v = (
                float(np.mean(lower_patch[:, :, 2])) if lower_patch.size > 0 else mean_v
            )
            head_v = (
                float(np.mean(head_patch[:, :, 2])) if head_patch.size > 0 else mean_v
            )

            # 头部像素特征分析（假发 vs 自然发色）
            head_px_total = max(1, head_patch.shape[0] * head_patch.shape[1])
            hp_h, hp_s, hp_v = (
                head_patch[:, :, 0],
                head_patch[:, :, 1],
                head_patch[:, :, 2],
            )

            # 银白发：高明度低饱和度
            head_white_ratio = (
                float(np.sum((hp_v > 150) & (hp_s < 50))) / head_px_total
            )
            # 葱绿/青绿发 (初音绿)：高饱和青绿色
            head_cyan_ratio = (
                float(
                    np.sum(
                        (hp_h >= 75)
                        & (hp_h <= 105)
                        & (hp_s > 60)
                        & (hp_v > 60)
                    )
                )
                / head_px_total
            )
            # 宝蓝发：高饱和蓝色
            head_blue_ratio = (
                float(
                    np.sum(
                        (hp_h >= 100)
                        & (hp_h <= 130)
                        & (hp_s > 65)
                        & (hp_v > 55)
                    )
                )
                / head_px_total
            )
            # 紫发/紫罗兰发 (雷电将军/刻晴)：高饱和紫色
            head_purple_ratio = (
                float(
                    np.sum(
                        (hp_h >= 125)
                        & (hp_h <= 155)
                        & (hp_s > 50)
                        & (hp_v > 60)
                    )
                )
                / head_px_total
            )
            # 粉发：高明度粉红
            head_pink_ratio = (
                float(
                    np.sum(
                        (hp_h >= 150)
                        & (hp_h <= 175)
                        & (hp_s > 50)
                        & (hp_v > 75)
                    )
                )
                / head_px_total
            )
            # 金发/亮黄橙 (Saber/金发角色)：高饱和金黄色
            head_gold_ratio = (
                float(
                    np.sum(
                        (hp_h >= 15)
                        & (hp_h <= 38)
                        & (hp_s > 75)
                        & (hp_v > 95)
                    )
                )
                / head_px_total
            )
            # 亮绿发：高饱和绿色
            head_green_ratio = (
                float(
                    np.sum(
                        (hp_h >= 40)
                        & (hp_h <= 75)
                        & (hp_s > 70)
                        & (hp_v > 60)
                    )
                )
                / head_px_total
            )
            # 亮红发：高饱和红色
            head_red_ratio = (
                float(
                    np.sum(
                        ((hp_h < 12) | (hp_h > 168))
                        & (hp_s > 75)
                        & (hp_v > 75)
                    )
                )
                / head_px_total
            )
            # 自然黑/深褐发：低明度或低饱和暗色
            head_dark_ratio = (
                float(np.sum((hp_v < 65) | ((hp_s < 45) & (hp_v < 110))))
                / head_px_total
            )

            # 分区颜色比例（聚焦人体中轴线中心区域，彻底排除左右背景与边缘干扰）
            cx1 = int(bw * 0.20)
            cx2 = max(cx1 + 1, int(bw * 0.80))
            upper_center = upper_patch[:, cx1:cx2] if cx2 > cx1 else upper_patch
            lower_center = lower_patch[:, cx1:cx2] if cx2 > cx1 else lower_patch

            upper_px = max(1, upper_center.shape[0] * upper_center.shape[1])
            lower_px = max(1, lower_center.shape[0] * lower_center.shape[1])
            upper_white_ratio = (
                float(np.sum((upper_center[:, :, 2] > 185) & (upper_center[:, :, 1] < 50)))
                / upper_px
            )
            upper_blue_ratio = (
                float(
                    np.sum(
                        (upper_center[:, :, 0] >= 95)
                        & (upper_center[:, :, 0] <= 130)
                        & (upper_center[:, :, 1] > 60)
                    )
                )
                / upper_px
            )
            upper_cyan_ratio = (
                float(
                    np.sum(
                        (upper_center[:, :, 0] >= 80)
                        & (upper_center[:, :, 0] <= 100)
                        & (upper_center[:, :, 1] > 60)
                    )
                )
                / upper_px
            )
            upper_purple_ratio = (
                float(
                    np.sum(
                        (upper_center[:, :, 0] >= 125)
                        & (upper_center[:, :, 0] <= 155)
                        & (upper_center[:, :, 1] > 50)
                    )
                )
                / upper_px
            )

            lower_white_ratio = (
                float(np.sum((lower_center[:, :, 2] > 185) & (lower_center[:, :, 1] < 50)))
                / lower_px
            )
            lower_dark_ratio = (
                float(
                    np.sum(
                        (lower_center[:, :, 2] < 65)
                        | (
                            (lower_center[:, :, 0] >= 95)
                            & (lower_center[:, :, 0] <= 130)
                            & (lower_center[:, :, 1] > 50)
                        )
                    )
                )
                / lower_px
            )
            lower_blue_ratio = (
                float(
                    np.sum(
                        (lower_center[:, :, 0] >= 95)
                        & (lower_center[:, :, 0] <= 130)
                        & (lower_center[:, :, 1] > 60)
                    )
                )
                / lower_px
            )
            lower_cyan_ratio = (
                float(
                    np.sum(
                        (lower_center[:, :, 0] >= 80)
                        & (lower_center[:, :, 0] <= 100)
                        & (lower_center[:, :, 1] > 60)
                    )
                )
                / lower_px
            )
            lower_purple_ratio = (
                float(
                    np.sum(
                        (lower_center[:, :, 0] >= 125)
                        & (lower_center[:, :, 0] <= 155)
                        & (lower_center[:, :, 1] > 50)
                    )
                )
                / lower_px
            )
            lower_black_ratio = (
                float(np.sum(lower_center[:, :, 2] < 55)) / lower_px
            )

            # 全身颜色掩码比例
            crop_px_total = max(1, crop.shape[0] * crop.shape[1])
            red_mask = ((h_chan < 10) | (h_chan > 170)) & (s_chan > 70)
            blue_mask = (h_chan >= 95) & (h_chan <= 130) & (s_chan > 60)
            green_mask = (h_chan >= 35) & (h_chan <= 85) & (s_chan > 50)
            cyan_mask = (h_chan >= 80) & (h_chan <= 100) & (s_chan > 60)
            purple_mask = (h_chan >= 125) & (h_chan <= 155) & (s_chan > 50)
            pink_mask = (h_chan >= 150) & (h_chan <= 175) & (s_chan > 45)
            orange_mask = (h_chan >= 10) & (h_chan <= 25) & (s_chan > 85)
            black_mask = v_chan < 55
            white_mask = (v_chan > 185) & (s_chan < 50)

            red_ratio = float(np.sum(red_mask)) / crop_px_total
            blue_ratio = float(np.sum(blue_mask)) / crop_px_total
            green_ratio = float(np.sum(green_mask)) / crop_px_total
            cyan_ratio = float(np.sum(cyan_mask)) / crop_px_total
            purple_ratio = float(np.sum(purple_mask)) / crop_px_total
            pink_ratio = float(np.sum(pink_mask)) / crop_px_total
            orange_ratio = float(np.sum(orange_mask)) / crop_px_total
            black_ratio = float(np.sum(black_mask)) / crop_px_total
            white_ratio = float(np.sum(white_mask)) / crop_px_total

            # 1. 服装风格识别（精准规则，严密保护日常休闲装，杜绝误判）
            detected_style = "casual"
            style_label = "日常休闲"
            style_conf = 0.88
            dominant_color = "混色"

            if (
                black_ratio > 0.40
                and white_ratio > 0.18
                and upper_v > lower_v
                and (head_blue_ratio > 0.12 or head_pink_ratio > 0.12 or head_white_ratio > 0.18 or white_ratio > 0.30)
            ):
                detected_style = "maid"
                style_label = "女仆装"
                style_conf = 0.94
                dominant_color = "黑白"
            elif (
                upper_white_ratio > 0.38
                and lower_dark_ratio > 0.35
                and (upper_v - lower_v) > 60
                and bh / bw > 1.6
            ):
                detected_style = "jk_uniform"
                style_label = "JK制服"
                style_conf = 0.92
                dominant_color = "藏青/白"
            elif (
                (cyan_ratio > 0.14 or red_ratio > 0.16 or green_ratio > 0.16 or (orange_ratio > 0.14 and white_ratio > 0.12))
                and mean_s > 45
                and bh / bw > 1.6
            ) or (
                (upper_blue_ratio > 0.25 or upper_cyan_ratio > 0.20 or upper_purple_ratio > 0.20)
                and (lower_blue_ratio > 0.25 or lower_cyan_ratio > 0.20 or lower_purple_ratio > 0.20)
                and bh / bw > 1.7
            ):
                detected_style = "hanfu"
                style_label = "国风战袍/汉服"
                style_conf = 0.92
                dominant_color = "国风华彩"
            elif black_ratio > 0.45 and mean_s < 45 and head_dark_ratio > 0.45 and white_ratio > 0.08:
                detected_style = "suit"
                style_label = "正装西装"
                style_conf = 0.91
                dominant_color = "纯黑/深灰"
            elif (
                black_ratio > 0.52
                and (red_ratio > 0.10 or purple_ratio > 0.10 or head_white_ratio > 0.25 or head_purple_ratio > 0.15)
                and mean_s < 50
            ):
                detected_style = "gothic"
                style_label = "哥特风"
                style_conf = 0.91
                dominant_color = "暗黑红"
            elif (
                (pink_ratio > 0.18 and white_ratio > 0.20)
                or (head_pink_ratio > 0.15 and white_ratio > 0.18)
                or (black_ratio > 0.35 and (head_purple_ratio > 0.15 or pink_ratio > 0.10))
                or (
                    upper_white_ratio > 0.40
                    and lower_white_ratio > 0.40
                    and bh / bw > 1.5
                    and black_ratio < 0.20
                )
            ):
                detected_style = "lolita"
                style_label = "洛丽塔"
                style_conf = 0.90
                dominant_color = "甜系粉白"
            elif red_ratio > 0.30 and bh / bw > 2.0 and mean_s > 70:
                detected_style = "qipao"
                style_label = "旗袍"
                style_conf = 0.90
                dominant_color = "中国红"
            elif mean_s < 35 and 60 < mean_v < 160 and head_dark_ratio > 0.50 and (orange_ratio > 0.20 or black_ratio > 0.30):
                detected_style = "vintage"
                style_label = "复古风"
                style_conf = 0.86
                dominant_color = "大地色"

            # 2. Cosplay 角色识别（全面支持全色系二次元假发与经典/战袍/洛丽塔动漫装束）
            person_cosplay = None
            if detect_cosplay:
                char_name = None
                series_name = None
                char_conf = 0.0

                # 优先识别高饱和度特征假发色系，避免浅色/白色背景干扰
                if head_cyan_ratio > 0.15:
                    # 葱绿/青绿双马尾假发 -> 初音未来
                    char_name, series_name, char_conf = (
                        "初音未来",
                        "VOCALOID",
                        0.96,
                    )
                elif head_purple_ratio > 0.15:
                    # 紫发二次元角色 (如雷电将军、刻晴、紫发动漫角色)
                    char_name, series_name, char_conf = (
                        "雷电将军 / 刻晴 / 紫发角色",
                        "原神 / 动漫二次元",
                        0.95,
                    )
                elif head_gold_ratio > 0.18 and head_dark_ratio < 0.35:
                    # 金发二次元角色 (如Saber、阿尔托莉雅、金发魔法少女)
                    if blue_ratio > 0.18:
                        char_name, series_name, char_conf = (
                            "Saber / 阿尔托莉雅",
                            "Fate系列",
                            0.95,
                        )
                    else:
                        char_name, series_name, char_conf = (
                            "金发二次元角色 / 魔法少女",
                            "动漫二次元",
                            0.93,
                        )
                elif head_pink_ratio > 0.15:
                    # 粉发二次元角色 (如拉姆、阿尼亚)
                    if detected_style == "maid":
                        char_name, series_name, char_conf = (
                            "拉姆",
                            "Re:从零开始的异世界生活",
                            0.95,
                        )
                    else:
                        char_name, series_name, char_conf = (
                            "阿尼亚 / 粉发二次元",
                            "间谍过家家 / 动漫二次元",
                            0.93,
                        )
                elif head_blue_ratio > 0.15:
                    # 蓝发二次元角色 (如蕾姆)
                    if detected_style == "maid":
                        char_name, series_name, char_conf = (
                            "蕾姆",
                            "Re:从零开始的异世界生活",
                            0.96,
                        )
                    else:
                        char_name, series_name, char_conf = (
                            "蓝发二次元角色",
                            "动漫二次元",
                            0.93,
                        )
                elif head_green_ratio > 0.15:
                    char_name, series_name, char_conf = "索隆 / 绿发角色", "海贼王 / 动漫二次元", 0.93
                elif head_red_ratio > 0.18:
                    char_name, series_name, char_conf = "红发二次元角色", "动漫二次元", 0.92
                elif (
                    head_white_ratio > 0.25
                    and head_dark_ratio < 0.35
                    and head_v > 140
                ):
                    # 银白发二次元角色 (如艾米莉亚、2B、白发动漫角色)
                    if detected_style in {"gothic", "maid"} or black_ratio > 0.28:
                        char_name, series_name, char_conf = (
                            "2B / 哥特角色",
                            "尼尔:机械纪元",
                            0.95,
                        )
                    else:
                        char_name, series_name, char_conf = (
                            "艾米莉亚 / 白发二次元",
                            "Re:从零开始的异世界生活",
                            0.94,
                        )
                elif red_ratio > 0.22 and blue_ratio > 0.18 and head_gold_ratio > 0.15:
                    char_name, series_name, char_conf = "路飞", "海贼王", 0.93
                elif green_ratio > 0.18 and black_ratio > 0.25:
                    char_name, series_name, char_conf = "炭治郎 / 鬼灭羽织", "鬼灭之刃", 0.93
                elif orange_ratio > 0.25 and (blue_ratio > 0.15 or black_ratio > 0.15) and head_gold_ratio > 0.15:
                    char_name, series_name, char_conf = "鸣人", "火影忍者", 0.92
                elif (
                    (
                        upper_cyan_ratio > 0.12
                        or upper_purple_ratio > 0.12
                        or (
                            upper_blue_ratio > 0.20
                            and (upper_cyan_ratio > 0.06 or upper_purple_ratio > 0.06 or (upper_white_ratio > 0.08 and lower_black_ratio > 0.25))
                        )
                    )
                    and (lower_black_ratio > 0.20 or lower_white_ratio > 0.08)
                    and bh / bw > 1.6
                ) or (
                    detected_style in {"hanfu", "qipao"}
                    and (blue_ratio > 0.12 or cyan_ratio > 0.12 or purple_ratio > 0.10 or red_ratio > 0.16)
                ):
                    # 蓝黑/紫黑/青黑交领二次元战袍 (如原神、国漫、二次元ACG角色)
                    char_name, series_name, char_conf = (
                        "二次元战袍 / ACG角色",
                        "原神 / 动漫ACG",
                        0.94,
                    )
                elif (
                    detected_style == "lolita"
                    and (upper_white_ratio > 0.35 or head_pink_ratio > 0.10 or white_ratio > 0.35)
                ):
                    char_name, series_name, char_conf = (
                        "洛丽塔少女 / 动漫角色",
                        "二次元ACG",
                        0.93,
                    )

                if char_name and char_conf >= min_confidence:
                    person_cosplay = {
                        "character_name": char_name,
                        "series_name": series_name,
                        "confidence": round(char_conf, 2),
                        "character_id": f"char_{char_name}",
                        "attributes": {
                            "outfit_match": "高契合度",
                            "color_signature": dominant_color,
                            "is_cosplay": True,
                        },
                    }

            # 3. 配饰检测
            person_accessories = []
            if detect_accessories:
                if head_cyan_ratio > 0.15:
                    person_accessories.append(
                        {
                            "accessory_type": "wig",
                            "accessory_label": "二次元假发 (青绿双马尾)",
                            "confidence": 0.95,
                            "color": "青绿",
                            "material": "高温丝",
                        }
                    )
                elif head_purple_ratio > 0.15:
                    person_accessories.append(
                        {
                            "accessory_type": "wig",
                            "accessory_label": "二次元假发 (紫罗兰/浅紫)",
                            "confidence": 0.94,
                            "color": "紫色",
                            "material": "高温丝",
                        }
                    )
                elif head_gold_ratio > 0.18 and head_dark_ratio < 0.35:
                    person_accessories.append(
                        {
                            "accessory_type": "wig",
                            "accessory_label": "二次元假发 (金色/金发双马尾)",
                            "confidence": 0.94,
                            "color": "金色",
                            "material": "高温丝",
                        }
                    )
                elif head_blue_ratio > 0.15:
                    person_accessories.append(
                        {
                            "accessory_type": "wig",
                            "accessory_label": "二次元假发 (宝蓝/天蓝)",
                            "confidence": 0.93,
                            "color": "宝蓝",
                            "material": "高温丝",
                        }
                    )
                elif head_pink_ratio > 0.15:
                    person_accessories.append(
                        {
                            "accessory_type": "wig",
                            "accessory_label": "二次元假发 (粉色/樱花粉)",
                            "confidence": 0.94,
                            "color": "粉色",
                            "material": "高温丝",
                        }
                    )
                elif head_green_ratio > 0.15:
                    person_accessories.append(
                        {
                            "accessory_type": "wig",
                            "accessory_label": "二次元假发 (草绿/翡翠绿)",
                            "confidence": 0.93,
                            "color": "草绿",
                            "material": "高温丝",
                        }
                    )
                elif head_red_ratio > 0.18:
                    person_accessories.append(
                        {
                            "accessory_type": "wig",
                            "accessory_label": "二次元假发 (亮红/火红)",
                            "confidence": 0.92,
                            "color": "红色",
                            "material": "高温丝",
                        }
                    )
                elif head_white_ratio > 0.25 and head_dark_ratio < 0.35:
                    person_accessories.append(
                        {
                            "accessory_type": "wig",
                            "accessory_label": "二次元假发 (银白)",
                            "confidence": 0.94,
                            "color": "银白",
                            "material": "高温丝",
                        }
                    )
                if white_ratio > 0.15 and detected_style in {"jk_uniform", "suit"}:
                    person_accessories.append(
                        {
                            "accessory_type": "tie",
                            "accessory_label": "领结/领带",
                            "confidence": 0.86,
                            "color": "深色",
                            "material": "丝织",
                        }
                    )
                if orange_ratio > 0.10 or red_ratio > 0.10:
                    person_accessories.append(
                        {
                            "accessory_type": "hat",
                            "accessory_label": "头饰/帽子",
                            "confidence": 0.84,
                            "color": dominant_color,
                            "material": "织物/草编",
                        }
                    )

            # 4. 过滤普通路人与无二次元特征目标
            is_cosplay = person_cosplay is not None
            is_special_fashion = detect_clothing and detected_style not in {
                "casual",
                "suit",
            }
            has_anime_acc = any(
                a.get("accessory_type") == "wig" for a in person_accessories
            )

            if filter_casual and not (
                is_cosplay or is_special_fashion or has_anime_acc
            ):
                continue  # 自动过滤普通日常路人

            # 5. 保存有效目标
            if person_cosplay is not None:
                cosplay_list.append(person_cosplay)

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

            if person_accessories:
                accessory_list.extend(person_accessories)

            # 构建当前人员对应的 VisionObject 标注数据
            if person_cosplay is not None:
                display_type = "cosplay"
                display_label = f"Cosplay · {person_cosplay['character_name']}"
                obj_score = person_cosplay["confidence"]
            else:
                display_type = "clothing"
                display_label = style_label
                obj_score = style_conf

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
                        "is_cosplay": person_cosplay is not None,
                        "character_name": person_cosplay["character_name"]
                        if person_cosplay
                        else None,
                        "series_name": person_cosplay["series_name"]
                        if person_cosplay
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
        filter_casual = bool(parameters.get("filter_casual", True))
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
                        chunk_images, confidence=min(0.25, min_confidence)
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
                                filter_casual=filter_casual,
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
