"""
行为识别插件

提供视频和流式场景下的人体动作识别、活动检测和异常行为分析能力。
"""

from __future__ import annotations

from scenara.domains.behavior.operators import BehaviorEngine, BehaviorRecognitionOperator
from scenara.platform.models import PipelineStatus
from scenara.platform.pipeline import PipelineDefinition, PipelineNode, PipelineParameterDefinition
from scenara.platform.plugins import DomainManifest


class BehaviorPlugin:
    """行为识别领域插件"""

    manifest = DomainManifest(
        domain_id="behavior",
        display_name="行为识别",
        schema_version="1.0",
        console_route="/parse?domain=behavior",
        capabilities=(
            "action_recognition",      # 动作识别
            "activity_detection",      # 活动检测
            "temporal_segmentation",   # 时序分割
            "anomaly_detection",       # 异常检测
        ),
        product_scope=("行为识别与分析",),
        description="从视频和实时流中识别人体动作、检测活动模式和发现异常行为。",
        supported_media_kinds=("video", "stream"),
        default_pipeline_id="behavior.recognition",
        navigation_order=30,
    )

    def __init__(self, engine: BehaviorEngine | None = None) -> None:
        self._engine = engine

    def operators(self) -> tuple[BehaviorRecognitionOperator, ...]:
        return (BehaviorRecognitionOperator(self._engine),)

    def pipelines(self) -> tuple[PipelineDefinition, ...]:
        return (
            PipelineDefinition(
                pipeline_id="behavior.recognition",
                version="0.1.0",
                domain="behavior",
                status=PipelineStatus.ACTIVE,
                nodes=[
                    PipelineNode(
                        node_id="decode",
                        operator_id="platform.media.decode",
                        inputs={"media": "$media.input"},
                    ),
                    PipelineNode(
                        node_id="behavior",
                        operator_id="behavior.action-recognition",
                        inputs={"batch": "decode.batch"},
                    ),
                ],
                output="behavior.result",
                allowed_parameters={
                    "temporal_window_ms",
                    "min_confidence",
                    "enable_anomaly_detection",
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
                },
                parameter_schema={
                    "roi": PipelineParameterDefinition(
                        label="识别区域(ROI)",
                        control="text",
                        placeholder="[x1, y1, x2, y2] 归一化比例",
                        advanced=True,
                        description="指定感兴趣识别区域，例如 [0.1, 0.1, 0.9, 0.9]，只对圈定区域内的人员进行行为识别",
                    ),
                    "temporal_window_ms": PipelineParameterDefinition(
                        label="时序窗口(ms)",
                        control="number",
                        default=1000,
                        minimum=500,
                        maximum=5000,
                        step=100,
                        description="行为识别的时间窗口大小,决定分析多长时间的动作序列",
                    ),
                    "min_confidence": PipelineParameterDefinition(
                        label="最低置信度",
                        control="number",
                        default=0.5,
                        minimum=0,
                        maximum=1,
                        step=0.05,
                        description="行为识别结果的最小置信度阈值,低于此值的结果将被过滤",
                    ),
                    "enable_anomaly_detection": PipelineParameterDefinition(
                        label="启用异常检测",
                        control="boolean",
                        default=False,
                        advanced=True,
                        description="是否同时检测异常行为片段",
                    ),
                    "sample_strategy": PipelineParameterDefinition(
                        label="采样策略",
                        control="select",
                        default="interval",
                        options=["interval", "scene_change"],
                        description="视频/视频流的帧采样策略(时间间隔或镜头切换检测)",
                    ),
                    "sample_interval_ms": PipelineParameterDefinition(
                        label="采样间隔(ms)",
                        control="number",
                        default=200,  # 行为识别需要更密集的采样
                        minimum=100,
                        maximum=2000,
                        step=100,
                        description="时间间隔采样的帧率控制,行为识别建议使用较小的间隔",
                    ),
                    "scene_change_threshold": PipelineParameterDefinition(
                        label="镜头切换阈值",
                        control="number",
                        default=0.3,
                        minimum=0.05,
                        maximum=0.95,
                        step=0.05,
                        advanced=True,
                        description="镜头变动切换判定的敏感度阈值",
                    ),
                },
                pausable=True,
            ),
            # 可以添加更多专门的流水线,例如:
            # - behavior.person-action: 先检测人,再识别行为
            # - behavior.anomaly: 专注于异常检测
        )


__all__ = ["BehaviorPlugin"]
