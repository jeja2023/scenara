from __future__ import annotations

import asyncio
import time
from typing import Any, Literal, Protocol, cast

from scenara.platform.media_batch import DecodedMedia
from scenara.platform.models import (
    MediaKind,
    MediaUnitResult,
    ModelProvenance,
    OcrDomainPayload,
    OcrTextBlock,
    PipelineRef,
    Point,
    ProvenanceEvidence,
    ResultEnvelope,
)
from scenara.platform.pipeline import DomainUnavailable, ExecutionContext, OperatorDefinition


class OcrEngine(Protocol):
    model_id: str
    production_ready: bool
    version: str

    def predict(self, image: Any) -> list[dict[str, Any]]: ...


class PaddleOcrEngine:
    model_id = "paddleocr"
    production_ready = False

    def __init__(self) -> None:
        try:
            import paddleocr
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise DomainUnavailable("PaddleOCR is not installed") from exc
        self.version = str(getattr(paddleocr, "__version__", "unknown"))
        self._engine = PaddleOCR(
            use_doc_orientation_classify=True, use_doc_unwarping=False, use_textline_orientation=True
        )

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


OCR_BLOCK_TYPES = {"text", "title", "paragraph", "image", "table"}


def _polygon(value: object) -> list[list[float]]:
    if not isinstance(value, (list, tuple)):
        return []
    points: list[list[float]] = []
    for point in value:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            points.append([float(point[0]), float(point[1])])
    return points


def _bounds(item: dict[str, Any]) -> tuple[float, float, float, float]:
    points = _polygon(item.get("polygon"))
    if not points:
        return (float("inf"), float("inf"), float("inf"), float("inf"))
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _contains(region: dict[str, Any], block: dict[str, Any]) -> bool:
    left, top, right, bottom = _bounds(region)
    block_left, block_top, block_right, block_bottom = _bounds(block)
    if block_left == float("inf"):
        return False
    center_x = (block_left + block_right) / 2
    center_y = (block_top + block_bottom) / 2
    return left <= center_x <= right and top <= center_y <= bottom


def _merge_layout(
    raw_blocks: list[dict[str, Any]],
    regions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_regions = [
        {
            **region,
            "polygon": _polygon(region.get("polygon")),
            "block_type": (
                str(region.get("block_type")) if str(region.get("block_type")) in OCR_BLOCK_TYPES else "text"
            ),
        }
        for region in regions
    ]
    merged: list[dict[str, Any]] = []
    used_regions: set[int] = set()
    for block in raw_blocks:
        normalized = {**block, "polygon": _polygon(block.get("polygon"))}
        explicit_type = str(normalized.get("block_type", ""))
        if explicit_type not in OCR_BLOCK_TYPES:
            candidates = [
                (index, region) for index, region in enumerate(normalized_regions) if _contains(region, normalized)
            ]
            if candidates:
                index, region = min(
                    candidates,
                    key=lambda pair: (
                        (_bounds(pair[1])[2] - _bounds(pair[1])[0]) * (_bounds(pair[1])[3] - _bounds(pair[1])[1])
                    ),
                )
                normalized["block_type"] = region["block_type"]
                used_regions.add(index)
            else:
                normalized["block_type"] = "text"
        merged.append(normalized)
    for index, region in enumerate(normalized_regions):
        if index not in used_regions and region["block_type"] in {"image", "table"}:
            merged.append({**region, "text": "", "score": region.get("score")})
    return sorted(merged, key=lambda item: (_bounds(item)[1], _bounds(item)[0]))


class OcrDocumentOperator:
    definition = OperatorDefinition(
        operator_id="ocr.document-recognition",
        version="1.0.0",
        domain="ocr",
        input_types={"batch": "media/batch"},
        resource_budget={"vram_mb": 4096, "cpu_cores": 2},
        max_batch_size=256,
        output_types={"result": "result/ocr"},
        timeout_seconds=3600,
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
        decoded = inputs["batch"]
        if not isinstance(decoded, DecodedMedia):
            raise TypeError("OCR requires a decoded media batch")
        if self._engine is None:
            loaded_engine = await asyncio.to_thread(lambda: PaddleOcrEngine())
            self._engine = loaded_engine
        engine = self._engine
        assert engine is not None
        production_ready = bool(getattr(engine, "production_ready", False))
        layout_predictor = getattr(engine, "predict_layout", None)
        layout_capabilities = frozenset(getattr(engine, "production_capabilities", ()))
        layout_ready = callable(layout_predictor) and "layout_analysis" in layout_capabilities
        layout_required = bool(parameters.get("layout_required", True))
        if context.production and not production_ready:
            raise DomainUnavailable("OCR engine is not approved for production")
        if context.production and layout_required and not layout_ready:
            raise DomainUnavailable("OCR layout engine is not approved for production")

        substitutes: list[str] = []
        if not production_ready:
            substitutes.append("ocr_engine")
        if layout_required and not layout_ready:
            substitutes.append("ocr_layout")
        models = [
            ModelProvenance(
                capability="ocr_recognition",
                model_id=engine.model_id,
                version=engine.version,
                production_ready=production_ready,
            )
        ]
        if callable(layout_predictor):
            models.append(
                ModelProvenance(
                    capability="ocr_layout",
                    model_id=str(getattr(engine, "layout_model_id", engine.model_id)),
                    version=str(getattr(engine, "layout_version", engine.version)),
                    production_ready=layout_ready,
                )
            )

        blocks: list[OcrTextBlock] = []
        units: list[MediaUnitResult] = []
        reading_order = 0
        processed_units = 0

        def build_result(*, final: bool = False) -> ResultEnvelope:
            warnings = [f"development_substitute:{item}" for item in substitutes]
            if final and decoded.termination_reason:
                warnings.append(f"media_termination:{decoded.termination_reason}")
            return ResultEnvelope(
                run_id=context.run_id,
                domain="ocr",
                pipeline=PipelineRef(pipeline_id=context.pipeline_id, version=context.pipeline_version),
                asset_id=context.asset_id,
                source_id=context.source_id,
                units=list(units),
                domain_payload=OcrDomainPayload(
                    text="\n".join(block.text for block in blocks if block.text),
                    blocks=list(blocks),
                ),
                models=models,
                media_metadata=decoded.metadata.model_copy(update={"sampled_units": processed_units}),
                warnings=warnings,
                provenance=ProvenanceEvidence(development_substitutes=substitutes),
                created_at=time.time(),
            )

        batch_size = 1 if decoded.kind == MediaKind.STREAM else 4
        try:
            async for chunk, expected_units in decoded.iter_batches(batch_size):
                for unit in chunk:
                    raw_blocks = await asyncio.to_thread(engine.predict, unit.image)
                    regions: list[dict[str, Any]] = []
                    if callable(layout_predictor):
                        predicted = await asyncio.to_thread(layout_predictor, unit.image)
                        if not isinstance(predicted, list):
                            raise TypeError("OCR layout engine must return a list")
                        regions = [item for item in predicted if isinstance(item, dict)]
                    ordered_blocks = _merge_layout(raw_blocks, regions)
                    for block_index, item in enumerate(ordered_blocks):
                        points = [Point(x=point[0], y=point[1]) for point in _polygon(item.get("polygon"))]
                        block_type = str(item.get("block_type", "text"))
                        if block_type not in OCR_BLOCK_TYPES:
                            block_type = "text"
                        blocks.append(
                            OcrTextBlock(
                                block_id=f"{unit.unit_id}_block_{block_index}",
                                text=str(item.get("text", "")),
                                score=item.get("score"),
                                polygon=points,
                                block_type=cast(
                                    Literal["text", "title", "paragraph", "image", "table"], block_type
                                ),
                                reading_order=reading_order,
                            )
                        )
                        reading_order += 1
                    units.append(
                        MediaUnitResult(
                            unit_id=unit.unit_id,
                            unit_type=unit.unit_type,
                            index=unit.index,
                            pts_ms=unit.pts_ms,
                            page_number=unit.page_number,
                            width=unit.width,
                            height=unit.height,
                        )
                    )
                processed_units += len(chunk)
                progress = (
                    None
                    if expected_units is None
                    else 0.03 + 0.94 * min(1.0, processed_units / max(1, expected_units))
                )
                if decoded.kind in {MediaKind.VIDEO, MediaKind.STREAM}:
                    await context.publish_partial_result(build_result())
                await context.report_progress(
                    progress,
                    stage="ocr",
                    processed_units=processed_units,
                    expected_units=expected_units,
                    latest_pts_ms=chunk[-1].pts_ms if chunk else None,
                )
        except BaseException:
            await decoded.close()
            raise
        return {"result": build_result(final=True)}
