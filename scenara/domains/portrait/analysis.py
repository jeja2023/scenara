from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol
from uuid import uuid4

from PIL import Image

from scenara.platform.media_batch import DecodedMedia
from scenara.platform.models import (
    BoundingBox,
    MediaUnitResult,
    ModelProvenance,
    PipelineRef,
    Point,
    PortraitDomainPayload,
    ProvenanceEvidence,
    ResultEnvelope,
    ResultRelation,
    VisionObject,
)
from scenara.platform.pipeline import DomainUnavailable, ExecutionContext, OperatorDefinition

PORTRAIT_CAPABILITIES = frozenset(
    {
        "person_detection",
        "body_reid",
        "face_detection",
        "face_alignment",
        "face_embedding",
        "pose",
        "human_parsing",
        "apparel_attributes",
        "silhouette_segmentation",
        "gait",
        "tracking",
        "quality_fusion",
    }
)


@dataclass(slots=True)
class PortraitBackendOutput:
    units: list[dict[str, Any]]
    tracks: list[dict[str, Any]] = field(default_factory=list)
    models: list[ModelProvenance] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    development_substitutes: list[str] = field(default_factory=list)


class PortraitAnalysisBackend(Protocol):
    def production_capabilities(self) -> frozenset[str]: ...

    async def analyze(
        self,
        images: list[Image.Image],
        filenames: list[str | None],
        capabilities: frozenset[str],
    ) -> PortraitBackendOutput: ...


def _box(value: object) -> BoundingBox | None:
    if not isinstance(value, list) or len(value) < 4:
        return None
    x1, y1, x2, y2 = (float(item) for item in value[:4])
    return BoundingBox(x=x1, y=y1, width=max(0.0, x2 - x1), height=max(0.0, y2 - y1))


def _safe_attributes(value: dict[str, Any]) -> dict[str, Any]:
    def sanitize(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                key: sanitize(nested)
                for key, nested in item.items()
                if key not in {"crop", "embedding", "_tracking_embedding"}
            }
        if isinstance(item, list):
            return [sanitize(nested) for nested in item]
        return item

    return {
        key: sanitize(item)
        for key, item in value.items()
        if key not in {"box", "crop", "embedding", "_tracking_embedding"}
    }


class LegacyPortraitAnalysisBackend:
    _legacy_capabilities: ClassVar[dict[str, str]] = {
        "person_detection": "person_detection",
        "body_reid": "body_embedding",
        "face_detection": "face_detection",
        "face_alignment": "face_detection",
        "face_embedding": "face_embedding",
        "pose": "pose",
        "human_parsing": "appearance",
        "apparel_attributes": "appearance",
        "gait": "gait",
    }

    def production_capabilities(self) -> frozenset[str]:
        from app.portrait_model_capabilities import production_model_ready

        ready = {
            capability
            for capability, legacy_name in self._legacy_capabilities.items()
            if production_model_ready(legacy_name)
        }
        if {"person_detection", "body_reid"} <= ready:
            ready.add("tracking")
        if "person_detection" in ready:
            ready.add("quality_fusion")
        return frozenset(ready)

    async def analyze(
        self,
        images: list[Image.Image],
        filenames: list[str | None],
        capabilities: frozenset[str],
    ) -> PortraitBackendOutput:
        from app.media.quality import assess_image_quality
        from app.portrait_model_capabilities import capability_status
        from app.portrait_model_runtime import (
            infer_appearance_record_for_image,
            infer_body_record_for_image,
            infer_face_records_for_image,
            infer_gait_embedding_for_images,
            infer_pose_record_for_image,
        )
        from app.tracking_association import associate_person_tracks

        started = time.perf_counter()
        production_ready = self.production_capabilities()
        substitutes = sorted(capabilities - production_ready)
        rows: list[dict[str, Any]] = []
        frames: list[dict[str, Any]] = []
        for index, image in enumerate(images):
            quality = assess_image_quality(image)
            persons: list[dict[str, Any]]
            if "person_detection" in capabilities:
                persons = await self._persons(image, filenames[index] if index < len(filenames) else None)
            else:
                persons = []
            if "body_reid" in capabilities and persons:
                body = await infer_body_record_for_image(image, include_embedding=True)
                persons[0].update({f"body_{key}": item for key, item in _safe_attributes(body).items()})
            faces = (
                await infer_face_records_for_image(image, include_embeddings="face_embedding" in capabilities)
                if "face_detection" in capabilities
                else []
            )
            pose = await infer_pose_record_for_image(image) if "pose" in capabilities else None
            appearance = (
                await infer_appearance_record_for_image(image, include_embedding=True)
                if capabilities & {"human_parsing", "apparel_attributes"}
                else None
            )
            if pose and persons:
                persons[0]["pose"] = _safe_attributes(pose)
            if appearance and persons:
                persons[0]["appearance"] = _safe_attributes(appearance)
            if "quality_fusion" in capabilities:
                for person in persons:
                    detection_score = float(person.get("score", 0.0))
                    media_score = float(quality.get("score", 0.0))
                    person["quality"] = {
                        "score": round(0.65 * detection_score + 0.35 * media_score, 6),
                        "detection_score": detection_score,
                        "media_score": media_score,
                    }
            frame = {"frame_index": index, "persons": persons, "person_count": len(persons)}
            frames.append(frame)
            rows.append(
                {
                    "persons": persons,
                    "faces": faces,
                    "quality": quality,
                    "silhouettes": self._silhouettes(persons) if "silhouette_segmentation" in capabilities else [],
                }
            )

        tracks: list[dict[str, Any]] = []
        if "tracking" in capabilities and len(frames) > 1:
            tracking = associate_person_tracks(frames, include_template_embeddings=False)
            tracks = list(tracking.get("tracks", []))
        warnings: list[str] = []
        if "gait" in capabilities:
            if len(images) < 8:
                warnings.append("gait_requires_at_least_8_frames")
            else:
                gait_embedding, gait = await infer_gait_embedding_for_images(images)
                gait = _safe_attributes(gait)
                gait["embedding_available"] = gait_embedding is not None
                tracks.append({"track_id": "gait_sequence_0", "gait": gait})

        models = []
        for capability in sorted(capabilities):
            legacy_name = self._legacy_capabilities.get(capability)
            status = capability_status(legacy_name) if legacy_name else {}
            models.append(
                ModelProvenance(
                    capability=capability,
                    model_id=str(status.get("model_id") or f"scenara.development.{capability}"),
                    version=str(status.get("version") or "unversioned"),
                    production_ready=capability in production_ready,
                )
            )
        return PortraitBackendOutput(
            units=rows,
            tracks=tracks,
            models=models,
            timings={"portrait_analysis_seconds": time.perf_counter() - started},
            warnings=warnings,
            development_substitutes=substitutes,
        )

    async def _persons(self, image: Image.Image, filename: str | None) -> list[dict[str, Any]]:
        from app.inference_detection import infer_person_frames
        from app.portrait_model_runtime_capability import (
            get_capability_runtime,
            runtime_output_value,
        )

        runtime = await get_capability_runtime("person_detection", {"yolo", "yolov8"})
        if runtime is None:
            return [
                {
                    "box": [0.0, 0.0, float(image.width), float(image.height)],
                    "score": 0.0,
                    "model_status": "development_whole_image_substitute",
                }
            ]
        frames, _ = await infer_person_frames(
            runtime.bundle,
            runtime.cache_key,
            [image],
            [filename],
            confidence=float(runtime_output_value(runtime, "confidence", 0.25)),
            iou=float(runtime_output_value(runtime, "iou", 0.45)),
            max_detections=int(runtime_output_value(runtime, "max_detections", 100)),
        )
        if not frames:
            return []
        return list(frames[0].get("persons", []))

    def _silhouettes(self, persons: list[dict[str, Any]]) -> list[dict[str, Any]]:
        silhouettes = []
        for person in persons:
            bbox = _box(person.get("box"))
            if bbox is None:
                continue
            silhouettes.append(
                {
                    "polygon": [
                        [bbox.x, bbox.y],
                        [bbox.x + bbox.width, bbox.y],
                        [bbox.x + bbox.width, bbox.y + bbox.height],
                        [bbox.x, bbox.y + bbox.height],
                    ],
                    "score": person.get("score"),
                    "model_status": "development_bbox_silhouette_substitute",
                }
            )
        return silhouettes


class PortraitFullAnalysisOperator:
    definition = OperatorDefinition(
        operator_id="portrait.full-analysis",
        version="1.0.0",
        domain="portrait",
        input_types={"batch": "media/batch"},
        output_types={"result": "result/portrait"},
        timeout_seconds=600,
        resource_class="gpu",
        resource_budget={"vram_mb": 20_480, "cpu_cores": 4},
        max_batch_size=512,
        batchable=True,
        failure_policy="fail",
    )

    def __init__(self, backend: PortraitAnalysisBackend | None = None) -> None:
        self._backend = backend or LegacyPortraitAnalysisBackend()

    async def execute(
        self,
        context: ExecutionContext,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        decoded = inputs["batch"]
        if not isinstance(decoded, DecodedMedia):
            raise TypeError("portrait analysis requires a decoded media batch")
        requested_raw = parameters.get("capabilities", sorted(PORTRAIT_CAPABILITIES))
        if not isinstance(requested_raw, list) or not all(isinstance(item, str) for item in requested_raw):
            raise ValueError("portrait capabilities must be a list of strings")
        requested = frozenset(requested_raw)
        unknown = sorted(requested - PORTRAIT_CAPABILITIES)
        if unknown:
            raise ValueError("unknown portrait capabilities: " + ", ".join(unknown))
        missing = requested - self._backend.production_capabilities()
        if context.production and missing:
            raise DomainUnavailable("production portrait capabilities are unavailable: " + ", ".join(sorted(missing)))
        output = await self._backend.analyze(
            [unit.image for unit in decoded.units],
            [context.filename for _ in decoded.units],
            requested,
        )

        persons: list[VisionObject] = []
        faces: list[VisionObject] = []
        unit_results: list[MediaUnitResult] = []
        relations: list[ResultRelation] = []
        for unit, analysis in zip(decoded.units, output.units, strict=True):
            objects: list[VisionObject] = []
            unit_persons: list[VisionObject] = []
            for item in analysis.get("persons", []):
                person = VisionObject(
                    object_id=f"person_{uuid4().hex}",
                    object_type="person",
                    score=float(item["score"]) if item.get("score") is not None else None,
                    bbox=_box(item.get("box")),
                    track_id=str(item["track_id"]) if item.get("track_id") else None,
                    attributes=_safe_attributes(item),
                )
                persons.append(person)
                unit_persons.append(person)
                objects.append(person)
            for item in analysis.get("faces", []):
                face = VisionObject(
                    object_id=f"face_{uuid4().hex}",
                    object_type="face",
                    score=float(item["score"]) if item.get("score") is not None else None,
                    bbox=_box(item.get("box")),
                    attributes=_safe_attributes(item),
                )
                faces.append(face)
                objects.append(face)
                if unit_persons:
                    relations.append(
                        ResultRelation(
                            relation_type="belongs_to",
                            source_object_id=face.object_id,
                            target_object_id=unit_persons[0].object_id,
                        )
                    )
            for item in analysis.get("silhouettes", []):
                points = [Point(x=float(point[0]), y=float(point[1])) for point in item.get("polygon", [])]
                silhouette = VisionObject(
                    object_id=f"silhouette_{uuid4().hex}",
                    object_type="silhouette",
                    score=float(item["score"]) if item.get("score") is not None else None,
                    polygon=points,
                    attributes=_safe_attributes(item),
                )
                objects.append(silhouette)
                if unit_persons:
                    relations.append(
                        ResultRelation(
                            relation_type="segments",
                            source_object_id=silhouette.object_id,
                            target_object_id=unit_persons[0].object_id,
                        )
                    )
            unit_results.append(
                MediaUnitResult(
                    unit_id=unit.unit_id,
                    unit_type=unit.unit_type,
                    index=unit.index,
                    pts_ms=unit.pts_ms,
                    page_number=unit.page_number,
                    width=unit.width,
                    height=unit.height,
                    objects=objects,
                )
            )

        warnings = list(output.warnings)
        if decoded.termination_reason:
            warnings.append(f"media_termination:{decoded.termination_reason}")
        if output.development_substitutes:
            warnings.append("development_substitutes:" + ",".join(sorted(output.development_substitutes)))
        result = ResultEnvelope(
            run_id=context.run_id,
            domain="portrait",
            pipeline=PipelineRef(pipeline_id=context.pipeline_id, version=context.pipeline_version),
            asset_id=context.asset_id,
            source_id=context.source_id,
            units=unit_results,
            domain_payload=PortraitDomainPayload(
                persons=persons,
                faces=faces,
                tracks=output.tracks,
                capabilities=sorted(requested),
            ),
            relations=relations,
            models=output.models,
            timings=output.timings,
            warnings=warnings,
            provenance=ProvenanceEvidence(development_substitutes=sorted(output.development_substitutes)),
            created_at=time.time(),
        )
        return {"result": result}


__all__ = [
    "PORTRAIT_CAPABILITIES",
    "LegacyPortraitAnalysisBackend",
    "PortraitAnalysisBackend",
    "PortraitBackendOutput",
    "PortraitFullAnalysisOperator",
]
