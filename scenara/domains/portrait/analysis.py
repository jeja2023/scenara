from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol
from uuid import uuid4

from PIL import Image

from scenara.platform.artifacts import store_object_crop, store_unit_frame
from scenara.platform.media_batch import DecodedMedia
from scenara.platform.model_runtime import current_runtime_binding
from scenara.platform.models import (
    BoundingBox,
    MediaKind,
    MediaUnitResult,
    ModelProvenance,
    PipelineRef,
    Point,
    PortraitDomainPayload,
    ProvenanceEvidence,
    ResultEnvelope,
    ResultIndexVector,
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
    trajectory_tracks: list[dict[str, Any]] = field(default_factory=list)
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


_SENSITIVE_KEYS = frozenset({"crop", "embedding", "_tracking_embedding", "_face_embedding"})


def _safe_attributes(value: dict[str, Any]) -> dict[str, Any]:
    def sanitize(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                key: sanitize(nested)
                for key, nested in item.items()
                if key not in _SENSITIVE_KEYS
            }
        if isinstance(item, list):
            return [sanitize(nested) for nested in item]
        return item

    return {key: sanitize(item) for key, item in value.items() if key not in _SENSITIVE_KEYS | {"box"}}


def _box_center(box: list[float]) -> tuple[float, float]:
    return ((float(box[0]) + float(box[2])) / 2.0, (float(box[1]) + float(box[3])) / 2.0)


def _contains(person_box: list[float], face_box: list[float]) -> float:
    """人脸中心落在人体框内的贴合度，用于把人脸归属到正确的人。"""

    if len(person_box) < 4 or len(face_box) < 4:
        return 0.0
    center_x, center_y = _box_center(face_box)
    left, top, right, bottom = (float(person_box[index]) for index in range(4))
    if not (left <= center_x <= right and top <= center_y <= bottom):
        return 0.0
    width = max(1e-6, right - left)
    height = max(1e-6, bottom - top)
    # 越靠近人体框上部、越居中，越可能是这个人的脸。
    horizontal = 1.0 - abs(center_x - (left + right) / 2.0) / (width / 2.0)
    vertical = 1.0 - (center_y - top) / height
    return max(0.0, min(1.0, 0.5 * horizontal + 0.5 * vertical))


def _assign_face_embeddings(persons: list[dict[str, Any]], faces: list[dict[str, Any]]) -> None:
    """把每张人脸的向量挂到最贴合的人体检测上，供跟踪层聚合人脸模板。

    多人同框时按贴合度做一对一贪心分配，避免所有人脸都落到第一个人身上。
    """

    candidates: list[tuple[float, int, int]] = []
    for face_index, face in enumerate(faces):
        if not isinstance(face, dict):
            continue
        embedding = face.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            continue
        face_box = face.get("box")
        if not isinstance(face_box, list):
            continue
        for person_index, person in enumerate(persons):
            person_box = person.get("box")
            if not isinstance(person_box, list):
                continue
            score = _contains(person_box, face_box)
            if score > 0.0:
                candidates.append((score, face_index, person_index))

    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    used_faces: set[int] = set()
    used_persons: set[int] = set()
    for _, face_index, person_index in candidates:
        if face_index in used_faces or person_index in used_persons:
            continue
        used_faces.add(face_index)
        used_persons.add(person_index)
        persons[person_index]["_face_embedding"] = [float(value) for value in faces[face_index]["embedding"]]


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
            if production_model_ready(legacy_name) or current_runtime_binding(legacy_name) is not None
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
            infer_body_records_for_persons,
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
                # Preserve the established first-person body record contract and
                # add crop-specific samples for every additional detection.
                body_records = [await infer_body_record_for_image(image, include_embedding=True)]
                if len(persons) > 1:
                    body_records.extend(
                        await infer_body_records_for_persons(image, persons[1:], include_embedding=True)
                    )
                for person, body in zip(persons, body_records, strict=False):
                    safe_body = _safe_attributes(body)
                    person.update({f"body_{key}": item for key, item in safe_body.items()})
                    embedding = body.get("embedding") if isinstance(body, dict) else None
                    if isinstance(embedding, list) and embedding:
                        person["_tracking_embedding"] = embedding
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
            _assign_face_embeddings(persons, faces)
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
        trajectory_tracks: list[dict[str, Any]] = []
        if "tracking" in capabilities and len(frames) > 1:
            tracking = associate_person_tracks(frames, include_template_embeddings=True)
            trajectory_tracks = list(tracking.get("tracks", []))
            tracks = [_safe_attributes(track) for track in trajectory_tracks]
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
            binding = current_runtime_binding(legacy_name) if legacy_name else None
            status = capability_status(legacy_name) if legacy_name else {}
            models.append(
                ModelProvenance(
                    capability=capability,
                    model_id=(
                        binding.model_id
                        if binding is not None
                        else str(status.get("model_id") or f"scenara.development.{capability}")
                    ),
                    version=(binding.version if binding is not None else str(status.get("version") or "unversioned")),
                    sha256=binding.sha256 if binding is not None else None,
                    production_ready=capability in production_ready,
                )
            )
        return PortraitBackendOutput(
            units=rows,
            tracks=tracks,
            trajectory_tracks=trajectory_tracks,
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


def _with_presentation_times(tracks: list[dict[str, Any]], units: list[Any]) -> list[dict[str, Any]]:
    """给 tracklet 附上真实的帧时间戳。

    ``frame_index`` 是解码单元在批次中的序号，与 ``decoded.units`` 一一对应，
    据此把帧序号翻译成媒体内的毫秒偏移，长期轨迹才能还原真实时间线而不是入库时刻。
    """

    pts_by_index = {
        index: unit.pts_ms for index, unit in enumerate(units) if getattr(unit, "pts_ms", None) is not None
    }
    enriched: list[dict[str, Any]] = []
    for track in tracks:
        item = dict(track)
        first = pts_by_index.get(int(item.get("first_frame_index", 0) or 0))
        last = pts_by_index.get(int(item.get("last_frame_index", 0) or 0))
        if first is not None:
            item["first_pts_ms"] = first
        if last is not None:
            item["last_pts_ms"] = last
        enriched.append(item)
    return enriched


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
        decoded = await decoded.materialize()
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
        index_vectors: list[ResultIndexVector] = []
        for unit, analysis in zip(decoded.units, output.units, strict=True):
            objects: list[VisionObject] = []
            unit_persons: list[VisionObject] = []
            for item in analysis.get("persons", []):
                person_box = _box(item.get("box"))
                person = VisionObject(
                    object_id=f"person_{uuid4().hex}",
                    object_type="person",
                    score=float(item["score"]) if item.get("score") is not None else None,
                    bbox=person_box,
                    track_id=str(item["track_id"]) if item.get("track_id") else None,
                    attributes=_safe_attributes(item),
                    crop_artifact_id=await store_object_crop(context.artifacts, unit.image, bbox=person_box),
                )
                persons.append(person)
                unit_persons.append(person)
                objects.append(person)
            for item in analysis.get("faces", []):
                face_box = _box(item.get("box"))
                face = VisionObject(
                    object_id=f"face_{uuid4().hex}",
                    object_type="face",
                    score=float(item["score"]) if item.get("score") is not None else None,
                    bbox=face_box,
                    attributes=_safe_attributes(item),
                    crop_artifact_id=await store_object_crop(context.artifacts, unit.image, bbox=face_box),
                )
                faces.append(face)
                objects.append(face)
                embedding = item.get("embedding")
                if isinstance(embedding, list) and embedding:
                    model_id = str(item.get("embedding_model_id") or item.get("model_id") or "unknown")
                    model_version = str(
                        item.get("embedding_model_version") or item.get("model_version") or "unknown"
                    )
                    quality = item.get("quality")
                    quality_score = None
                    if isinstance(quality, dict) and quality.get("score") is not None:
                        quality_score = max(0.0, min(1.0, float(quality["score"])))
                    index_vectors.append(
                        ResultIndexVector(
                            object_id=face.object_id,
                            feature_space_id=f"portrait.face.{model_id}.{model_version}",
                            model_id=model_id,
                            model_version=model_version,
                            vector=[float(value) for value in embedding],
                            quality=quality_score,
                        )
                    )
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
                    crop_artifact_id=await store_object_crop(context.artifacts, unit.image, polygon=points),
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
            if not objects and decoded.kind in {MediaKind.VIDEO, MediaKind.STREAM}:
                continue
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
                    frame_artifact_id=(
                        await store_unit_frame(context.artifacts, unit.image)
                        if any(item.crop_artifact_id for item in objects)
                        else None
                    ),
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
            media_metadata=decoded.metadata,
            warnings=warnings,
            provenance=ProvenanceEvidence(development_substitutes=sorted(output.development_substitutes)),
            created_at=time.time(),
        )
        result._index_vectors = index_vectors
        result._trajectory_tracks = _with_presentation_times(output.trajectory_tracks, decoded.units)
        return {"result": result}


__all__ = [
    "PORTRAIT_CAPABILITIES",
    "LegacyPortraitAnalysisBackend",
    "PortraitAnalysisBackend",
    "PortraitBackendOutput",
    "PortraitFullAnalysisOperator",
]
