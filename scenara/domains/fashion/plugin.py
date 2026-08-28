"""
服饰风格识别插件

提供 Cosplay 角色识别、服装风格检测和配饰分析能力。
"""

from __future__ import annotations

from scenara.domains.fashion.operators import FashionEngine, FashionRecognitionOperator
from scenara.platform.models import PipelineStatus
from scenara.platform.pipeline import PipelineDefinition, PipelineNode, PipelineParameterDefinition
from scenara.platform.plugins import DomainManifest


class FashionPlugin:
    """服饰风格识别领域插件"""

    manifest = DomainManifest(
        domain_id="fashion",
        display_name="服饰风格",
        schema_version="1.0",
        console_route="/parse?domain=fashion",
        capabilities=(
            "cosplay_recognition",      # Cosplay 角色识别
            "clothing_style_detection", # 服装风格检测
            "accessory_detection",      # 配饰识别
            "fashion_attribute_analysis", # 服饰属性分析
        ),
        product_scope=("Cosplay 识别与服饰风格分析",),
        description="识别 Cosplay 角色、服装风格(JK、Lolita、汉服等)和配饰,支持二次元文化和时尚分析。",
        supported_media_kinds=("image", "video", "stream"),
        default_pipeline_id="fashion.recognition",
        navigation_order=40,
    )

    def __init__(self, engine: FashionEngine | None = None) -> None:
        self._engine = engine

    def operators(self) -> tuple[FashionRecognitionOperator, ...]:
        return (FashionRecognitionOperator(self._engine),)

    def pipelines(self) -> tuple[PipelineDefinition, ...]:
        return (
            PipelineDefinition(
                pipeline_id="fashion.recognition",
                version="0.1.0",
                domain="fashion",
                status=PipelineStatus.ACTIVE,
                nodes=[
                    PipelineNode(
                        node_id="decode",
                        operator_id="platform.media.decode",
                        inputs={"media": "$media.input"},
                    ),
                    PipelineNode(
                        node_id="fashion",
                        operator_id="fashion.style-recognition",
                        inputs={"batch": "decode.batch"},
                    ),
                ],
                output="fashion.result",
                allowed_parameters={
                    "min_confidence",
                    "filter_casual",
                    "detect_cosplay",
                    "detect_clothing",
                    "detect_accessories",
                    "roi",
                    "sample_interval_ms",
                    "max_reconnect_attempts",
                    "connect_timeout_ms",
                    "read_timeout_ms",
                    "sample_strategy",
                    "sample_start_ms",
                    "sample_end_ms",
                    "stream_segment_duration_ms",
                    "stream_segment_index",
                    "scene_change_threshold",
                    "frame_max_edge",
                    "page_scale",
                },
                parameter_schema={
                    "roi": PipelineParameterDefinition(
                        label="识别区域(ROI)",
                        control="text",
                        placeholder="[x1, y1, x2, y2] 归一化比例",
                        advanced=True,
                        description="指定感兴趣识别区域，例如 [0.1, 0.1, 0.9, 0.9]，只对圈定区域内的人员进行服饰分析",
                    ),
                    "min_confidence": PipelineParameterDefinition(
                        label="最低置信度",
                        control="number",
                        default=0.25,
                        minimum=0,
                        maximum=1,
                        step=0.05,
                        description="识别结果的最小置信度阈值,低于此值的结果将被过滤",
                    ),
                    "filter_casual": PipelineParameterDefinition(
                        label="过滤普通路人",
                        control="boolean",
                        default=True,
                        description="自动过滤日常休闲、正装西装等普通路人，仅提取 Cosplay 角色与特色服饰 (汉服/JK/Lolita等)",
                    ),
                    "detect_cosplay": PipelineParameterDefinition(
                        label="识别 Cosplay",
                        control="boolean",
                        default=True,
                        description="是否进行 Cosplay 二次元角色识别 (初音未来、艾米莉亚、蕾姆等)",
                    ),
                    "detect_clothing": PipelineParameterDefinition(
                        label="识别服装风格",
                        control="boolean",
                        default=True,
                        description="是否进行服装风格检测 (汉服、JK制服、洛丽塔、女仆装等)",
                    ),
                    "detect_accessories": PipelineParameterDefinition(
                        label="识别配饰",
                        control="boolean",
                        default=True,
                        description="是否进行配饰识别 (二次元假发、头饰、领结等)",
                    ),
                    "sample_strategy": PipelineParameterDefinition(
                        label="采样策略",
                        control="select",
                        default="interval",
                        options=["interval", "scene_change"],
                        media_kinds={"video", "stream"},
                        description="视频/视频流的帧采样策略(时间间隔或镜头切换检测)",
                    ),
                    "sample_interval_ms": PipelineParameterDefinition(
                        label="采样间隔(ms)",
                        control="number",
                        default=500,
                        minimum=100,
                        maximum=5000,
                        step=100,
                        media_kinds={"video", "stream"},
                        description="时间间隔采样的帧率控制",
                    ),
                    "scene_change_threshold": PipelineParameterDefinition(
                        label="镜头切换阈值",
                        control="number",
                        default=0.3,
                        minimum=0.05,
                        maximum=0.95,
                        step=0.05,
                        advanced=True,
                        media_kinds={"video", "stream"},
                        description="镜头变动切换判定的敏感度阈值",
                    ),
                },
                pausable=True,
            ),
        )


__all__ = ["FashionPlugin"]
