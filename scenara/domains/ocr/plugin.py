from __future__ import annotations

from scenara.domains.ocr.operators import OcrDocumentOperator, OcrEngine
from scenara.platform.models import PipelineStatus
from scenara.platform.pipeline import (
    PipelineDefinition,
    PipelineNode,
    PipelineParameterDefinition,
)
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
                    "min_score",
                    "language_hint",
                    "max_pages",
                    "extract_native_text",
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
                    "roi",
                    "enable_compliance",
                    "deduplicate_slides",
                    "layout_reconstruction",
                },
                parameter_schema={
                    "layout_required": PipelineParameterDefinition(
                        label="版面分析",
                        control="boolean",
                        default=False,
                        description="是否对识别结果进行版面类型划分(段落、表格、标题等)",
                    ),
                    "enable_compliance": PipelineParameterDefinition(
                        label="文本合规审查",
                        control="boolean",
                        default=True,
                        description="开启《广告法》极限词、虚假承诺、不良导向与隐蔽引流等合规性检测",
                    ),
                    "layout_reconstruction": PipelineParameterDefinition(
                        label="HTML排版还原",
                        control="boolean",
                        default=True,
                        description="按画面真实坐标生成 1:1 自适应 HTML 视觉仿真排版",
                    ),
                    "deduplicate_slides": PipelineParameterDefinition(
                        label="海报/版面去重",
                        control="boolean",
                        default=True,
                        media_kinds={"video", "stream", "document"},
                        description="感知大屏海报轮播切换，自动聚类去重并统计展示频次与累计时长",
                    ),
                    "roi": PipelineParameterDefinition(
                        label="识别区域(ROI)",
                        control="text",
                        placeholder="[x1, y1, x2, y2] 归一化比例",
                        advanced=True,
                        description="指定感兴趣识别区域，例如 [0.1, 0.1, 0.9, 0.9]，只对圈定区域进行文字识别",
                    ),
                    "min_score": PipelineParameterDefinition(
                        label="最低置信度",
                        control="number",
                        default=0.5,
                        minimum=0,
                        maximum=1,
                        step=0.05,
                        advanced=True,
                        description="文本框识别筛选的最小置信度阈值,低于此值的结果将被过滤",
                    ),
                    "language_hint": PipelineParameterDefinition(
                        label="语言提示",
                        control="text",
                        placeholder="例如 zh、en、ja、ko",
                        advanced=True,
                        description="文本识别模型的优先语言指示,支持中文(zh)、英文(en)、日文(ja)、韩文(ko)等",
                    ),
                    "max_pages": PipelineParameterDefinition(
                        label="最大页数",
                        control="number",
                        default=100,
                        minimum=1,
                        maximum=1000,
                        step=1,
                        advanced=True,
                        media_kinds={"document"},
                        description="PDF 文档最大处理页数,超出部分将被截断以控制内存和处理时间",
                    ),
                    "extract_native_text": PipelineParameterDefinition(
                        label="提取原生文本",
                        control="boolean",
                        default=True,
                        advanced=True,
                        media_kinds={"document"},
                        description="是否尝试提取 PDF 原生文本层(而非 OCR),如果 PDF 包含可选择的文本会显著提升速度和准确性",
                    ),
                    "sample_strategy": PipelineParameterDefinition(
                        label="采样策略",
                        control="select",
                        default="interval",
                        options=["interval", "scene_change"],
                        media_kinds={"video", "stream"},
                        description="视频/视频流文字识别的帧采样策略(时间间隔或镜头切换检测)",
                    ),
                    "sample_interval_ms": PipelineParameterDefinition(
                        label="采样间隔(ms)",
                        control="number",
                        default=1000,
                        minimum=100,
                        maximum=60000,
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
