from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from scenara.platform.media import DecodedImage
from scenara.platform.models import (
    BoundingBox,
    MediaUnitResult,
    ModelProvenance,
    PipelineRef,
    PortraitDomainPayload,
    ResultEnvelope,
    VisionObject,
)
from scenara.platform.pipeline import DomainUnavailable, ExecutionContext, OperatorDefinition


class PortraitPersonDetectionOperator:
    definition = OperatorDefinition(
        operator_id="portrait.person-detection",
        version="1.0.0",
        domain="portrait",
        input_types={"image": "media/image"},
        output_types={"result": "result/portrait"},
        timeout_seconds=120,
        resource_class="gpu",
        batchable=True,
    )

    async def execute(
        self,
        context: ExecutionContext,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        decoded = inputs["image"]
        if not isinstance(decoded, DecodedImage):
            raise TypeError("portrait detector requires a decoded image")

        from app.inference_detection import infer_person_frames
        from app.portrait_model_runtime_capability import get_capability_runtime, runtime_output_value

        runtime = await get_capability_runtime("person_detection", {"yolo", "yolov8"})
        if runtime is None:
            raise DomainUnavailable("a production-ready person detection model is not installed")
        confidence = float(parameters.get("confidence", runtime_output_value(runtime, "confidence", 0.25)))
        iou = float(parameters.get("iou", runtime_output_value(runtime, "iou", 0.45)))
        max_detections = int(parameters.get("max_detections", runtime_output_value(runtime, "max_detections", 100)))
        frames, runtime_meta = await infer_person_frames(
            runtime.bundle,
            runtime.cache_key,
            [decoded.image],
            [context.filename],
            confidence=max(0.0, min(1.0, confidence)),
            iou=max(0.0, min(1.0, iou)),
            max_detections=max(1, min(256, max_detections)),
        )
        frame = frames[0] if frames else {}
        persons: list[VisionObject] = []
        for item in frame.get("persons", []):
            box = item.get("box", [])
            bbox = None
            if isinstance(box, list) and len(box) >= 4:
                x1, y1, x2, y2 = (float(value) for value in box[:4])
                bbox = BoundingBox(x=x1, y=y1, width=max(0.0, x2 - x1), height=max(0.0, y2 - y1))
            persons.append(
                VisionObject(
                    object_id=f"person_{uuid4().hex}",
                    object_type="person",
                    score=float(item["score"]) if item.get("score") is not None else None,
                    bbox=bbox,
                    attributes={key: value for key, value in item.items() if key not in {"box", "score", "embedding"}},
                )
            )
        timings = {key: float(value) for key, value in runtime_meta.get("timing", {}).items()}
        result = ResultEnvelope(
            run_id=context.run_id,
            domain="portrait",
            pipeline=PipelineRef(pipeline_id=context.pipeline_id, version=context.pipeline_version),
            asset_id=context.asset_id,
            source_id=context.source_id,
            units=[
                MediaUnitResult(
                    unit_id="frame_0",
                    unit_type="frame",
                    index=0,
                    pts_ms=0,
                    width=decoded.width,
                    height=decoded.height,
                    objects=persons,
                )
            ],
            domain_payload=PortraitDomainPayload(persons=persons, capabilities=["person_detection"]),
            models=[
                ModelProvenance(
                    capability="person_detection",
                    model_id=runtime.model_id,
                    version=runtime.version,
                    production_ready=True,
                )
            ],
            timings=timings,
            created_at=time.time(),
        )
        return {"result": result}
