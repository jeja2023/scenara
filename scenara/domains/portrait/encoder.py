from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Protocol

from PIL import Image, UnidentifiedImageError


class PortraitEncodingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PortraitEmbedding:
    embedding: list[float]
    feature_space_id: str
    model_id: str
    model_version: str
    face_count: int
    selected_face_index: int
    selected_face_box: list[float] | None
    quality_score: float | None
    fallback: bool
    metadata: dict[str, Any]


class PortraitImageEncoder(Protocol):
    async def encode(self, image: Image.Image) -> PortraitEmbedding: ...


def decode_portrait_image(data: bytes) -> Image.Image:
    if not data:
        raise PortraitEncodingError("image is empty")
    try:
        with Image.open(BytesIO(data)) as decoded:
            decoded.verify()
        with Image.open(BytesIO(data)) as decoded:
            return decoded.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise PortraitEncodingError("image could not be decoded") from exc


def _quality_score(face: dict[str, Any]) -> float | None:
    quality = face.get("quality")
    if isinstance(quality, dict) and quality.get("score") is not None:
        return float(quality["score"])
    if face.get("score") is not None:
        return float(face["score"])
    return None


class RuntimePortraitImageEncoder:
    """Domain adapter around the installed face detection/embedding runtime."""

    def __init__(self, *, production: bool = False) -> None:
        self.production = production

    async def encode(self, image: Image.Image) -> PortraitEmbedding:
        from app.portrait_model_runtime import infer_face_records_for_image

        records = await infer_face_records_for_image(
            image.convert("RGB"),
            include_embeddings=True,
            fallback=not self.production,
        )
        if not records:
            raise PortraitEncodingError("no face was detected in the image")
        selected_index = max(range(len(records)), key=lambda index: _quality_score(records[index]) or 0.0)
        selected = records[selected_index]
        embedding = selected.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise PortraitEncodingError("face embedding is unavailable")
        model_id = str(selected.get("embedding_model_id") or selected.get("model_id") or "unknown")
        model_version = str(selected.get("embedding_model_version") or selected.get("model_version") or "unknown")
        status = str(selected.get("embedding_model_status") or selected.get("model_status") or "unknown")
        return PortraitEmbedding(
            embedding=[float(value) for value in embedding],
            feature_space_id=f"portrait.face.{model_id}.{model_version}",
            model_id=model_id,
            model_version=model_version,
            face_count=len(records),
            selected_face_index=selected_index,
            selected_face_box=[float(value) for value in selected.get("box", [])] or None,
            quality_score=_quality_score(selected),
            fallback="fallback" in status or "fingerprint" in status,
            metadata={
                "detector_model_id": selected.get("model_id"),
                "detector_model_version": selected.get("model_version"),
                "embedding_model_status": status,
                "detection_strategy": selected.get("detection_strategy"),
            },
        )


__all__ = [
    "PortraitEmbedding",
    "PortraitEncodingError",
    "PortraitImageEncoder",
    "RuntimePortraitImageEncoder",
    "decode_portrait_image",
]
