from __future__ import annotations

import asyncio
import time
from typing import Any, Protocol

from scenara.platform.media import DecodedImage
from scenara.platform.models import (
    MediaUnitResult,
    ModelProvenance,
    OcrDomainPayload,
    OcrTextBlock,
    PipelineRef,
    Point,
    ResultEnvelope,
)
from scenara.platform.pipeline import DomainUnavailable, ExecutionContext, OperatorDefinition


class OcrEngine(Protocol):
    model_id: str
    version: str

    def predict(self, image: Any) -> list[dict[str, Any]]: ...


class PaddleOcrEngine:
    model_id = "paddleocr"

    def __init__(self) -> None:
        try:
            import paddleocr
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise DomainUnavailable("PaddleOCR is not installed") from exc
        self.version = str(getattr(paddleocr, "__version__", "unknown"))
        self._engine = PaddleOCR(use_doc_orientation_classify=True, use_doc_unwarping=False, use_textline_orientation=True)

    def predict(self, image: Any) -> list[dict[str, Any]]:
        import numpy as np

        predictions = self._engine.predict(np.asarray(image))
        blocks: list[dict[str, Any]] = []
        for prediction in predictions:
            payload = prediction.json if hasattr(prediction, "json") else prediction
            payload = payload.get("res", payload) if isinstance(payload, dict) else {}
            texts = payload.get("rec_texts", [])
            scores = payload.get("rec_scores", [])
            polygons = payload.get("rec_polys", [])
            for index, text in enumerate(texts):
                blocks.append(
                    {
                        "text": str(text),
                        "score": float(scores[index]) if index < len(scores) else None,
                        "polygon": polygons[index] if index < len(polygons) else [],
                    }
                )
        return blocks


class OcrDocumentOperator:
    definition = OperatorDefinition(
        operator_id="ocr.document-recognition",
        version="1.0.0",
        domain="ocr",
        input_types={"image": "media/image"},
        output_types={"result": "result/ocr"},
        timeout_seconds=120,
        resource_class="gpu",
        batchable=True,
    )

    def __init__(self, engine: OcrEngine | None = None) -> None:
        self._engine = engine

    async def execute(
        self,
        context: ExecutionContext,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        del parameters
        decoded = inputs["image"]
        if not isinstance(decoded, DecodedImage):
            raise TypeError("OCR requires a decoded image")
        engine = self._engine
        if engine is None:
            engine = await asyncio.to_thread(PaddleOcrEngine)
            self._engine = engine
        raw_blocks = await asyncio.to_thread(engine.predict, decoded.image)
        blocks: list[OcrTextBlock] = []
        for index, item in enumerate(raw_blocks):
            points = [Point(x=float(point[0]), y=float(point[1])) for point in item.get("polygon", []) if len(point) >= 2]
            blocks.append(
                OcrTextBlock(
                    block_id=f"text_{index}",
                    text=str(item.get("text", "")),
                    score=item.get("score"),
                    polygon=points,
                    reading_order=index,
                )
            )
        result = ResultEnvelope(
            run_id=context.run_id,
            domain="ocr",
            pipeline=PipelineRef(pipeline_id=context.pipeline_id, version=context.pipeline_version),
            asset_id=context.asset_id,
            source_id=context.source_id,
            units=[
                MediaUnitResult(
                    unit_id="page_1",
                    unit_type="page",
                    index=0,
                    page_number=1,
                    width=decoded.width,
                    height=decoded.height,
                )
            ],
            domain_payload=OcrDomainPayload(text="\n".join(block.text for block in blocks), blocks=blocks),
            models=[
                ModelProvenance(
                    capability="ocr_recognition",
                    model_id=engine.model_id,
                    version=engine.version,
                    production_ready=True,
                )
            ],
            created_at=time.time(),
        )
        return {"result": result}
