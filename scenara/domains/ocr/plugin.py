from __future__ import annotations

from scenara.domains.ocr.operators import OcrDocumentOperator, OcrEngine
from scenara.platform.models import PipelineStatus
from scenara.platform.pipeline import PipelineDefinition, PipelineNode, PipelineParameterDefinition
from scenara.platform.plugins import DomainManifest


class OcrPlugin:
    manifest = DomainManifest(
        domain_id="ocr",
        display_name="OCR 文档",
        schema_version="1.0",
        console_route="/parse?domain=ocr",
        capabilities=(
            "text_detection",
            "text_recognition",
            "reading_order",
            "title",
            "paragraph",
            "image_region",
            "table_region",
        ),
        product_scope=("OCR 文档解析",),
        description="从文档、图片、视频和网络流中提取文字、版面结构与阅读顺序。",
        supported_media_kinds=("document", "image", "video", "stream"),
        default_pipeline_id="ocr.document",
        navigation_order=20,
    )

    def __init__(self, engine: OcrEngine | None = None) -> None:
        self._engine = engine

    def operators(self) -> tuple[OcrDocumentOperator, ...]:
        return (OcrDocumentOperator(self._engine),)

    def pipelines(self) -> tuple[PipelineDefinition, ...]:
        return (
            PipelineDefinition(
                pipeline_id="ocr.document",
                version="0.1.0",
                domain="ocr",
                status=PipelineStatus.ACTIVE,
                nodes=[
                    PipelineNode(
                        node_id="decode",
                        operator_id="platform.media.decode",
                        inputs={"media": "$media.input"},
                    ),
                    PipelineNode(
                        node_id="ocr",
                        operator_id="ocr.document-recognition",
                        inputs={"batch": "decode.batch"},
                    ),
                ],
                output="ocr.result",
                allowed_parameters={
                    "layout_required",
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
                    "min_score",
                    "language_hint",
                },
                parameter_schema={
                    "layout_required": PipelineParameterDefinition(
                        label="版面分析",
                        control="boolean",
                        default=False,
                        description="是否对识别结果进行版面类型划分（段落、表格、标题等）",
                    ),
                    "sample_strategy": PipelineParameterDefinition(
                        label="采样策略",
                        control="select",
                        default="interval",
                        options=["interval", "scene_change"],
                        media_kinds=["video", "stream"],
                        description="视频/视频流文字识别的帧采样策略（时间间隔或镜头切页检测）",
                    ),
                    "sample_interval_ms": PipelineParameterDefinition(
                        label="采样间隔(ms)",
                        control="number",
                        default=1000,
                        minimum=100,
                        maximum=60000,
                        step=100,
                        media_kinds=["video", "stream"],
                        description="时间间隔采样的帧率控制",
                    ),
                    "scene_change_threshold": PipelineParameterDefinition(
                        label="镜头切页阈值",
                        control="number",
                        default=0.3,
                        minimum=0.05,
                        maximum=0.95,
                        step=0.05,
                        advanced=True,
                        media_kinds=["video", "stream"],
                        description="镜头变动切页判定的敏感度阈值",
                    ),
                    "max_units": PipelineParameterDefinition(
                        label="最大解析单元数",
                        control="number",
                        default=20,
                        minimum=1,
                        maximum=1000,
                        step=1,
                        description="单次解析允许处理的最大页面数或视频采样帧数",
                    ),
                    "min_score": PipelineParameterDefinition(
                        label="最低置信度",
                        control="number",
                        default=0.5,
                        minimum=0,
                        maximum=1,
                        step=0.05,
                        advanced=True,
                        description="文本框识别筛选的最小置信度门限",
                    ),
                    "language_hint": PipelineParameterDefinition(
                        label="语言提示",
                        control="text",
                        placeholder="例如 zh、en",
                        advanced=True,
                        description="文本识别模型的优先语言指示",
                    ),
                },
                pausable=True,
            ),
        )
