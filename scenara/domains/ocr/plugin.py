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
        console_route="/ocr",
        capabilities=(
            "text_detection",
            "text_recognition",
            "reading_order",
            "title",
            "paragraph",
            "image_region",
            "table_region",
        ),
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
                allowed_parameters={"layout_required", "max_units", "sample_interval_ms"},
                pausable=True,
            ),
        )
