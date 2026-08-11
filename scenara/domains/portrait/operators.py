from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from scenara.platform.artifacts import store_object_crop, store_unit_frame
from scenara.platform.media_batch import DecodedMedia
from scenara.platform.models import (
    BoundingBox,
    MediaKind,
    MediaTechnicalMetadata,
    MediaUnitResult,
    ModelProvenance,
    PipelineRef,
    PortraitDomainPayload,
    ResultEnvelope,
    VisionObject,
)
from scenara.platform.pipeline import DomainUnavailable, ExecutionContext, OperatorDefinition

PERSON_DETECTION_BATCH_SIZE = 16
PERSON_DETECTION_PROGRESS_BATCH_SIZE = 8
PERSON_DETECTION_STREAM_BATCH_SIZE = 1


class PortraitPersonDetectionOperator:
    definition = OperatorDefinition(
        operator_id="portrait.person-detection",
        version="1.1.0",
        domain="portrait",
        input_types={"batch": "media/batch"},
        output_types={"result": "result/portrait"},
        timeout_seconds=3600,
        resource_class="gpu",
        resource_budget={"vram_mb": 4096, "cpu_cores": 2},
        max_batch_size=PERSON_DETECTION_BATCH_SIZE,
        batchable=True,
    )

    async def execute(
        self,
        context: ExecutionContext,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        decoded = inputs["batch"]
        if not isinstance(decoded, DecodedMedia):
            raise TypeError("portrait detector requires a decoded media batch")

        from app.inference_detection import infer_person_frames
        from app.portrait_model_runtime_capability import get_capability_runtime, runtime_output_value

        try:
            runtime = await get_capability_runtime("person_detection", {"yolo", "yolov8"})
            if runtime is None:
                raise DomainUnavailable("a production-ready person detection model is not installed")
            confidence = float(parameters.get("confidence", runtime_output_value(runtime, "confidence", 0.25)))
            iou = float(parameters.get("iou", runtime_output_value(runtime, "iou", 0.45)))
            max_detections = int(parameters.get("max_detections", runtime_output_value(runtime, "max_detections", 100)))
        except BaseException:
            await decoded.close()
            raise
        persons: list[VisionObject] = []
        units: list[MediaUnitResult] = []
        processed_units = 0
        timing_totals: dict[str, float] = {}
        models = [
            ModelProvenance(
                capability="person_detection",
                model_id=runtime.model_id,
                version=runtime.version,
                production_ready=True,
            )
        ]
        batch_size = (
            PERSON_DETECTION_STREAM_BATCH_SIZE
            if decoded.kind == MediaKind.STREAM
            else PERSON_DETECTION_PROGRESS_BATCH_SIZE
            if decoded.stream is not None
            else PERSON_DETECTION_BATCH_SIZE
        )
        try:
            async for chunk, expected_units in decoded.iter_batches(batch_size):
                chunk_frames, runtime_meta = await infer_person_frames(
                    runtime.bundle,
                    runtime.cache_key,
                    [unit.image for unit in chunk],
                    [context.filename for _ in chunk],
                    confidence=max(0.0, min(1.0, confidence)),
                    iou=max(0.0, min(1.0, iou)),
                    max_detections=max(1, min(256, max_detections)),
                )
                for key, value in runtime_meta.get("timing", {}).items():
                    timing_totals[key] = timing_totals.get(key, 0.0) + float(value)
                for unit_index, unit in enumerate(chunk):
                    frame = chunk_frames[unit_index] if unit_index < len(chunk_frames) else {}
                    unit_persons: list[VisionObject] = []
                    for item in frame.get("persons", []):
                        box = item.get("box", [])
                        bbox = None
                        if isinstance(box, list) and len(box) >= 4:
                            x1, y1, x2, y2 = (float(value) for value in box[:4])
                            bbox = BoundingBox(
                                x=x1,
                                y=y1,
                                width=max(0.0, x2 - x1),
                                height=max(0.0, y2 - y1),
                            )
                        person = VisionObject(
                            object_id=f"person_{uuid4().hex}",
                            object_type="person",
                            score=float(item["score"]) if item.get("score") is not None else None,
                            bbox=bbox,
                            track_id=str(item["track_id"]) if item.get("track_id") else None,
                            attributes={
                                key: value for key, value in item.items() if key not in {"box", "score", "embedding"}
                            },
                            crop_artifact_id=await store_object_crop(context.artifacts, unit.image, bbox=bbox),
                        )
                        unit_persons.append(person)
                        persons.append(person)
                    frame_artifact_id = (
                        await store_unit_frame(context.artifacts, unit.image)
                        if any(person.crop_artifact_id for person in unit_persons)
                        else None
                    )
                    if unit_persons or decoded.kind not in {MediaKind.VIDEO, MediaKind.STREAM}:
                        units.append(
                            MediaUnitResult(
                                unit_id=unit.unit_id,
                                unit_type=unit.unit_type,
                                index=unit.index,
                                pts_ms=unit.pts_ms,
                                page_number=unit.page_number,
                                width=unit.width,
                                height=unit.height,
                                objects=unit_persons,
                                frame_artifact_id=frame_artifact_id,
                            )
                        )
                processed_units += len(chunk)
                progress = (
                    None
                    if expected_units is None
                    else 0.03 + 0.94 * min(1.0, processed_units / max(1, expected_units))
                )
                if decoded.kind in {MediaKind.VIDEO, MediaKind.STREAM}:
                    await context.publish_partial_result(
                        self._result(
                            context,
                            units,
                            persons,
                            models,
                            timing_totals,
                            decoded.metadata.model_copy(update={"sampled_units": processed_units}),
                        )
                    )
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
        warnings = [f"media_termination:{decoded.termination_reason}"] if decoded.termination_reason else []
        return {
            "result": self._result(
                context,
                units,
                persons,
                models,
                timing_totals,
                decoded.metadata,
                warnings=warnings,
            )
        }

    @staticmethod
    def _result(
        context: ExecutionContext,
        units: list[MediaUnitResult],
        persons: list[VisionObject],
        models: list[ModelProvenance],
        timings: dict[str, float],
        metadata: MediaTechnicalMetadata,
        *,
        warnings: list[str] | None = None,
    ) -> ResultEnvelope:
        return ResultEnvelope(
            run_id=context.run_id,
            domain="portrait",
            pipeline=PipelineRef(pipeline_id=context.pipeline_id, version=context.pipeline_version),
            warnings=warnings or [],
            asset_id=context.asset_id,
            source_id=context.source_id,
            units=list(units),
            domain_payload=PortraitDomainPayload(persons=list(persons), capabilities=["person_detection"]),
            models=models,
            timings=dict(timings),
            media_metadata=metadata,
            created_at=time.time(),
        )
