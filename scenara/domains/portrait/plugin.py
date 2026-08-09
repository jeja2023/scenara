from __future__ import annotations

from scenara.domains.portrait.analysis import (
    PORTRAIT_CAPABILITIES,
    PortraitAnalysisBackend,
    PortraitFullAnalysisOperator,
)
from scenara.domains.portrait.operators import PortraitPersonDetectionOperator
from scenara.platform.models import PipelineStatus
from scenara.platform.pipeline import Operator, PipelineDefinition, PipelineNode, PipelineParameterDefinition
from scenara.platform.plugins import DomainManifest


class PortraitPlugin:
    manifest = DomainManifest(
        domain_id="portrait",
        display_name="人像",
        schema_version="1.0",
        console_route="/parse?domain=portrait",
        capabilities=tuple(sorted(PORTRAIT_CAPABILITIES)),
        product_scope=("人像分析", "检测对象特征裁剪图"),
        description="检测人员并分析人像相关的视觉特征。",
        supported_media_kinds=("image", "video", "stream"),
        default_pipeline_id="portrait.person-detection",
        navigation_order=10,
    )

    def __init__(self, backend: PortraitAnalysisBackend | None = None) -> None:
        self._backend = backend

    def operators(self) -> tuple[Operator, ...]:
        return (
            PortraitPersonDetectionOperator(),
            PortraitFullAnalysisOperator(self._backend),
        )

    def pipelines(self) -> tuple[PipelineDefinition, ...]:
        decode = PipelineNode(
            node_id="decode",
            operator_id="platform.media.decode",
            inputs={"media": "$media.input"},
        )
        return (
            PipelineDefinition(
                pipeline_id="portrait.person-detection",
                version="0.1.0",
                domain="portrait",
                status=PipelineStatus.ACTIVE,
                nodes=[
                    decode,
                    PipelineNode(
                        node_id="detect",
                        operator_id="portrait.person-detection",
                        inputs={"batch": "decode.batch"},
                    ),
                ],
                output="detect.result",
                allowed_parameters={
                    "confidence",
                    "iou",
                    "max_detections",
                    "max_units",
                    "sample_interval_ms",
                    "max_reconnect_attempts",
                    "connect_timeout_ms",
                    "read_timeout_ms",
                    "sample_strategy",
                    "sample_start_ms",
                    "sample_end_ms",
                    "scene_change_threshold",
                    "frame_max_edge",
                    "page_scale",
                },
                parameter_schema={
                    "confidence": PipelineParameterDefinition(
                        label="最低置信度", control="number", default=0.5, minimum=0, maximum=1, step=0.05
                    ),
                    "iou": PipelineParameterDefinition(
                        label="重叠阈值",
                        control="number",
                        default=0.45,
                        minimum=0,
                        maximum=1,
                        step=0.05,
                        advanced=True,
                    ),
                    "max_detections": PipelineParameterDefinition(
                        label="最大目标数",
                        control="integer",
                        default=300,
                        minimum=1,
                        maximum=10000,
                        step=1,
                        advanced=True,
                    ),
                },
                pausable=True,
            ),
            PipelineDefinition(
                pipeline_id="portrait.analysis",
                version="0.4.0",
                domain="portrait",
                status=PipelineStatus.ACTIVE,
                nodes=[
                    decode.model_copy(deep=True),
                    PipelineNode(
                        node_id="analyze",
                        operator_id="portrait.full-analysis",
                        inputs={"batch": "decode.batch"},
                    ),
                ],
                output="analyze.result",
                allowed_parameters={
                    "capabilities",
                    "camera_id",
                    "max_units",
                    "recording_started_at",
                    "sample_interval_ms",
                    "max_reconnect_attempts",
                    "connect_timeout_ms",
                    "read_timeout_ms",
                    "sample_strategy",
                    "sample_start_ms",
                    "sample_end_ms",
                    "scene_change_threshold",
                    "frame_max_edge",
                    "page_scale",
                },
                parameter_schema={
                    "camera_id": PipelineParameterDefinition(
                        label="摄像头 ID",
                        control="text",
                        placeholder="例如 camera-lobby-01",
                        advanced=True,
                        media_kinds={"video", "stream"},
                    ),
                    "recording_started_at": PipelineParameterDefinition(
                        label="拍摄开始时间（Unix 秒）",
                        control="number",
                        minimum=0,
                        step=0.001,
                        advanced=True,
                        media_kinds={"video"},
                    ),
                },
                pausable=True,
            ),
        )
