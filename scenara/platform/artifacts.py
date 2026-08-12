from __future__ import annotations

import asyncio
import hashlib
import math
from contextlib import suppress
from io import BytesIO
from typing import Literal, Protocol
from uuid import uuid4

from PIL import Image

from scenara.platform.models import BoundingBox, ObjectRetentionRecord, Point, ResultArtifact
from scenara.platform.objects import ObjectStore

ArtifactType = Literal["object_crop", "unit_frame"]

ARTIFACT_ID_PREFIX: dict[str, str] = {"object_crop": "crop", "unit_frame": "frame"}
ARTIFACT_QUOTA_WARNING = "artifact_quota_reached"
ARTIFACT_CROP_QUOTA_WARNING = "artifact_crop_quota_reached"
ARTIFACT_STORAGE_WARNING = "artifact_storage_unavailable"
CROP_PADDING_RATIO = 0.08
JPEG_QUALITY = 85


def polygon_bounds(points: list[Point]) -> BoundingBox | None:
    """Return the axis-aligned box that encloses a polygon outline."""

    if len(points) < 2:
        return None
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    return BoundingBox(x=min(xs), y=min(ys), width=max(xs) - min(xs), height=max(ys) - min(ys))


def crop_region(
    image: Image.Image,
    bbox: BoundingBox,
    *,
    padding_ratio: float = CROP_PADDING_RATIO,
) -> Image.Image | None:
    """Crop the detected region with a small margin, clamped to the image bounds."""

    if image.width <= 0 or image.height <= 0:
        return None
    padding_x = bbox.width * padding_ratio
    padding_y = bbox.height * padding_ratio
    left = max(0, math.floor(bbox.x - padding_x))
    top = max(0, math.floor(bbox.y - padding_y))
    right = min(image.width, math.ceil(bbox.x + bbox.width + padding_x))
    bottom = min(image.height, math.ceil(bbox.y + bbox.height + padding_y))
    if right - left < 1 or bottom - top < 1:
        return None
    return image.crop((left, top, right, bottom))


def encode_jpeg(image: Image.Image, *, max_edge: int, quality: int = JPEG_QUALITY) -> bytes:
    """Downscale to ``max_edge`` (never upscaling) and encode as JPEG."""

    output = BytesIO()
    prepared = image if image.mode == "RGB" else image.convert("RGB")
    if max(prepared.width, prepared.height) > max_edge:
        prepared = prepared.copy()
        prepared.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    prepared.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()


class ArtifactSink(Protocol):
    """Sink that operators use to persist derived images alongside a run result."""

    async def store_image(self, image: Image.Image, *, artifact_type: ArtifactType) -> str | None: ...


class RunArtifactSink:
    """Persist per-run crop and frame images.

    Crop production uses a bounded quota because object counts can grow much
    faster than media units. Unit frames have no count limit and follow the
    preview retention policy. Storage failures remain best effort so a missing
    image never discards a valid structured result.
    """

    def __init__(
        self,
        objects: ObjectStore,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        max_crops: int,
        crop_max_edge: int,
        frame_max_edge: int,
    ) -> None:
        self._objects = objects
        self._tenant_id = tenant_id
        self._project_id = project_id
        self._run_id = run_id
        self._max_crops = max(0, max_crops)
        self._max_edge: dict[str, int] = {"object_crop": crop_max_edge, "unit_frame": frame_max_edge}
        self._stored: dict[str, int] = {"object_crop": 0, "unit_frame": 0}
        self._artifacts: list[ResultArtifact] = []
        self._warnings: list[str] = []

    @property
    def artifacts(self) -> list[ResultArtifact]:
        return list(self._artifacts)

    @property
    def warnings(self) -> list[str]:
        return list(self._warnings)

    def _warn(self, warning: str) -> None:
        if warning not in self._warnings:
            self._warnings.append(warning)

    async def store_image(self, image: Image.Image, *, artifact_type: ArtifactType) -> str | None:
        if artifact_type == "object_crop" and self._stored[artifact_type] >= self._max_crops:
            self._warn(ARTIFACT_CROP_QUOTA_WARNING)
            return None
        artifact_id = f"{ARTIFACT_ID_PREFIX[artifact_type]}_{uuid4().hex}"
        object_key = (
            f"tenants/{self._tenant_id}/projects/{self._project_id}"
            f"/runs/{self._run_id}/artifacts/{artifact_id}.jpg"
        )
        try:
            data = await asyncio.to_thread(encode_jpeg, image, max_edge=self._max_edge[artifact_type])
            await self._objects.put(object_key, data, "image/jpeg")
        except Exception:
            self._warn(ARTIFACT_STORAGE_WARNING)
            return None
        self._stored[artifact_type] += 1
        self._artifacts.append(
            ResultArtifact(
                artifact_id=artifact_id,
                artifact_type=artifact_type,
                object_key=object_key,
                content_type="image/jpeg",
                sha256=hashlib.sha256(data).hexdigest(),
            )
        )
        return artifact_id

    def retention_records(self, *, created_at: float, expires_at: float | None) -> list[ObjectRetentionRecord]:
        return [
            ObjectRetentionRecord(
                tenant_id=self._tenant_id,
                project_id=self._project_id,
                object_key=artifact.object_key,
                category="preview",
                owner_type="run_result",
                owner_id=self._run_id,
                created_at=created_at,
                expires_at=expires_at,
            )
            for artifact in self._artifacts
        ]

    async def discard(self) -> None:
        """Delete every object written so far; used when a run does not complete."""

        for artifact in self._artifacts:
            with suppress(Exception):
                await self._objects.delete(artifact.object_key)
        self._artifacts.clear()
        self._stored = {"object_crop": 0, "unit_frame": 0}


async def store_object_crop(
    sink: ArtifactSink | None,
    image: Image.Image,
    *,
    bbox: BoundingBox | None = None,
    polygon: list[Point] | None = None,
) -> str | None:
    """Crop and persist one detected object; returns ``None`` when unavailable."""

    if sink is None:
        return None
    region = bbox if bbox is not None else polygon_bounds(polygon or [])
    if region is None or region.width <= 0 or region.height <= 0:
        return None
    cropped = crop_region(image, region)
    if cropped is None:
        return None
    return await sink.store_image(cropped, artifact_type="object_crop")


async def store_unit_frame(sink: ArtifactSink | None, image: Image.Image) -> str | None:
    """Persist the full analysis unit image used as the large view behind a crop."""

    if sink is None:
        return None
    return await sink.store_image(image, artifact_type="unit_frame")


__all__ = [
    "ARTIFACT_CROP_QUOTA_WARNING",
    "ARTIFACT_QUOTA_WARNING",
    "ARTIFACT_STORAGE_WARNING",
    "ArtifactSink",
    "ArtifactType",
    "RunArtifactSink",
    "crop_region",
    "encode_jpeg",
    "polygon_bounds",
    "store_object_crop",
    "store_unit_frame",
]
