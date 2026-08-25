from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from typing import Any

import httpx
import pytest
from PIL import Image

from scenara.bootstrap import build_runtime
from scenara.domains.portrait.analysis import PORTRAIT_CAPABILITIES, PortraitBackendOutput
from scenara.infrastructure.object_store import LocalObjectStore
from scenara.platform.artifacts import RunArtifactSink, crop_region, encode_jpeg, polygon_bounds
from scenara.platform.models import BoundingBox, Point
from scenara.server import create_app

PERSON_BOX = [4.0, 6.0, 60.0, 44.0]
FACE_BOX = [16.0, 8.0, 38.0, 30.0]


class TwoPersonPortraitBackend:
    """Deterministic backend that reports two people, one face, and one silhouette."""

    def production_capabilities(self) -> frozenset[str]:
        return PORTRAIT_CAPABILITIES

    async def analyze(
        self,
        images: list[Image.Image],
        filenames: list[str | None],
        capabilities: frozenset[str],
    ) -> PortraitBackendOutput:
        del filenames, capabilities
        return PortraitBackendOutput(
            units=[
                {
                    "persons": [
                        {"box": PERSON_BOX, "score": 0.95},
                        {"box": [70.0, 10.0, 118.0, 70.0], "score": 0.81},
                    ],
                    "faces": [{"box": FACE_BOX, "score": 0.9}],
                    "silhouettes": [{"polygon": [[4, 6], [60, 6], [60, 44], [4, 44]], "score": 0.88}],
                }
                for _ in images
            ],
        )


def portrait_image() -> bytes:
    output = BytesIO()
    Image.new("RGB", (128, 96), "white").save(output, format="PNG")
    return output.getvalue()


def build_client(settings: Any) -> tuple[Any, Any]:
    runtime = build_runtime(settings, portrait_backend=TwoPersonPortraitBackend())
    return create_app(runtime=runtime), runtime


async def parse_portrait_image(api: httpx.AsyncClient) -> dict[str, Any]:
    response = await api.post(
        "/api/v1/parse/image",
        files={"file": ("portrait.png", portrait_image(), "image/png")},
        data={"domain": "portrait", "pipeline_id": "portrait.analysis"},
        headers={"Idempotency-Key": "artifact-parse"},
    )
    assert response.status_code == 200, response.text
    payload: dict[str, Any] = response.json()["data"]
    assert payload["run"]["status"] == "completed", payload["run"]
    return payload


@pytest.mark.asyncio
async def test_parsed_objects_expose_crop_and_frame_artifacts(development_settings) -> None:
    app, _ = build_client(development_settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        parsed = await parse_portrait_image(api)
        result = parsed["result"]

        unit = result["units"][0]
        assert unit["frame_artifact_id"], "the analysed unit must expose its full frame image"
        crop_ids = [item["crop_artifact_id"] for item in unit["objects"]]
        assert all(crop_ids), "every detected object with a region must expose a crop image"
        assert len(crop_ids) == 4  # two persons, one face, one silhouette
        assert len(set(crop_ids)) == 4

        declared = {item["artifact_id"]: item for item in result["artifacts"]}
        assert set(crop_ids) | {unit["frame_artifact_id"]} == set(declared)
        assert {item["artifact_type"] for item in declared.values()} == {"object_crop", "unit_frame"}
        assert all(item["content_type"] == "image/jpeg" for item in declared.values())

        run_id = parsed["run"]["run_id"]
        crop = await api.get(f"/api/v1/runs/{run_id}/artifacts/{crop_ids[0]}")
        assert crop.status_code == 200
        assert crop.headers["content-type"] == "image/jpeg"
        assert crop.headers["etag"] == f'"sha256:{declared[crop_ids[0]]["sha256"]}"'
        with Image.open(BytesIO(crop.content)) as decoded:
            # The first person box is 56x38 plus padding, well inside the crop edge cap.
            assert decoded.format == "JPEG"
            assert 56 <= decoded.width <= 66
            assert 38 <= decoded.height <= 48

        frame = await api.get(f"/api/v1/runs/{run_id}/artifacts/{unit['frame_artifact_id']}")
        assert frame.status_code == 200
        with Image.open(BytesIO(frame.content)) as decoded:
            assert (decoded.width, decoded.height) == (128, 96)


@pytest.mark.asyncio
async def test_artifact_read_rejects_unknown_ids_and_other_tenants(development_settings) -> None:
    app, _ = build_client(development_settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        parsed = await parse_portrait_image(api)
        run_id = parsed["run"]["run_id"]
        artifact_id = parsed["result"]["units"][0]["frame_artifact_id"]

        unknown = await api.get(f"/api/v1/runs/{run_id}/artifacts/frame_00000000000000000000000000000000")
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "NOT_FOUND"

        # A forged identifier must never be turned into an object store lookup.
        traversal = await api.get(f"/api/v1/runs/{run_id}/artifacts/..%2F..%2Fresult.json")
        assert traversal.status_code == 404

        other_tenant = await api.get(
            f"/api/v1/runs/{run_id}/artifacts/{artifact_id}",
            headers={"X-Tenant-Id": "other"},
        )
        assert other_tenant.status_code == 404


@pytest.mark.asyncio
async def test_artifacts_can_be_disabled(development_settings) -> None:
    app, _ = build_client(replace(development_settings, run_artifacts_enabled=False))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        result = (await parse_portrait_image(api))["result"]
        assert result["artifacts"] == []
        assert result["units"][0]["frame_artifact_id"] is None
        assert all(item["crop_artifact_id"] is None for item in result["units"][0]["objects"])


@pytest.mark.asyncio
async def test_unit_frames_are_not_limited_by_a_per_run_quota(tmp_path) -> None:
    sink = RunArtifactSink(
        LocalObjectStore(tmp_path / "objects"),
        tenant_id="tenant",
        project_id="project",
        run_id="run_unlimited_frames",
        crop_max_edge=256,
        frame_max_edge=1920,
    )
    frame = Image.new("RGB", (16, 12), "white")

    frame_ids = [await sink.store_image(frame, artifact_type="unit_frame") for _ in range(65)]

    assert all(frame_ids)
    assert len(sink.artifacts) == 65
    assert sink.warnings == []


@pytest.mark.asyncio
async def test_object_crops_are_not_limited_by_any_quota(tmp_path) -> None:
    sink = RunArtifactSink(
        LocalObjectStore(tmp_path / "objects"),
        tenant_id="tenant",
        project_id="project",
        run_id="run_unlimited_crops",
        crop_max_edge=256,
        frame_max_edge=1920,
    )
    crop = Image.new("RGB", (16, 12), "white")

    crop_ids = [await sink.store_image(crop, artifact_type="object_crop") for _ in range(250)]

    assert all(crop_ids)
    assert len(sink.artifacts) == 250
    assert sink.warnings == []


@pytest.mark.asyncio
async def test_failed_run_does_not_leave_artifact_objects(development_settings, monkeypatch) -> None:
    app, runtime = build_client(development_settings)
    deleted: list[str] = []
    original_delete = runtime.objects.delete

    async def failing_store_result(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise RuntimeError("result storage is unavailable")

    async def tracking_delete(object_key: str) -> bool:
        deleted.append(object_key)
        return await original_delete(object_key)

    monkeypatch.setattr(runtime.runs, "_store_result", failing_store_result)
    monkeypatch.setattr(runtime.objects, "delete", tracking_delete)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        response = await api.post(
            "/api/v1/parse/image",
            files={"file": ("portrait.png", portrait_image(), "image/png")},
            data={"domain": "portrait", "pipeline_id": "portrait.analysis"},
            headers={"Idempotency-Key": "artifact-failure"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["run"]["status"] == "failed"
    assert [key for key in deleted if "/artifacts/" in key], "artifact objects must be cleaned up on failure"


def test_crop_region_clamps_to_the_image_and_skips_empty_boxes() -> None:
    image = Image.new("RGB", (40, 30), "white")
    clamped = crop_region(image, BoundingBox(x=-20, y=-20, width=200, height=200))
    assert clamped is not None
    assert clamped.size == (40, 30)
    assert crop_region(image, BoundingBox(x=5, y=5, width=0, height=0)) is None


def test_polygon_bounds_returns_the_enclosing_box() -> None:
    bounds = polygon_bounds([Point(x=4, y=6), Point(x=30, y=6), Point(x=30, y=22)])
    assert bounds is not None
    assert (bounds.x, bounds.y, bounds.width, bounds.height) == (4, 6, 26, 16)
    assert polygon_bounds([Point(x=1, y=1)]) is None


def test_encode_jpeg_downscales_without_upscaling() -> None:
    with Image.open(BytesIO(encode_jpeg(Image.new("RGB", (800, 400)), max_edge=200))) as large:
        assert (large.width, large.height) == (200, 100)
    with Image.open(BytesIO(encode_jpeg(Image.new("RGB", (48, 32)), max_edge=200))) as small:
        assert (small.width, small.height) == (48, 32)
