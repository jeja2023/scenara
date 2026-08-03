from __future__ import annotations

from scenara.domains.ocr.operators import OcrDocumentOperator, OcrEngine
from scenara.platform.models import PipelineStatus
from scenara.platform.pipeline import PipelineDefinition, PipelineNode
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
        product_scope=("OCR document parsing",),
        description="Extract text, layout, and reading order from visual media and documents.",
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
                    "layout_required": {
                        "label": "版面分析",
                        "control": "boolean",
                        "default": False,
                    },
                    "min_score": {
                        "label": "最低置信度",
                        "control": "number",
                        "default": 0.5,
                        "minimum": 0,
                        "maximum": 1,
                        "step": 0.05,
                        "advanced": True,
                    },
                    "language_hint": {
                        "label": "语言提示",
                        "control": "text",
                        "placeholder": "例如 zh、en",
                        "advanced": True,
                    },
                },
                pausable=True,
            ),
        )
