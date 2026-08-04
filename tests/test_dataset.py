from io import BytesIO

import httpx
import pytest
from PIL import Image

from scenara.bootstrap import build_runtime
from scenara.server import create_app


def _image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (64, 64), (40, 120, 180)).save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
async def dataset_client(development_settings):
    runtime = build_runtime(development_settings)
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        yield api, runtime


@pytest.mark.asyncio
async def test_dataset_version_governance_tracks_assets_and_publishes(dataset_client) -> None:
    api, runtime = dataset_client
    created = await api.post(
        "/api/v1/datasets",
        json={"name": "人像训练集", "description": "人工确认后的图片集合"},
    )
    assert created.status_code == 201, created.text
    dataset = created.json()["data"]

    uploaded = await api.post(
        "/api/v1/media/assets",
        files={"file": ("sample.png", _image_bytes(), "image/png")},
        data={"kind": "image"},
    )
    assert uploaded.status_code == 201, uploaded.text
    asset_id = uploaded.json()["data"]["asset_id"]

    version = await api.post(
        f"/api/v1/datasets/{dataset['dataset_id']}/versions",
        json={
            "version": "2026.08.03",
            "manifest_sha256": "a" * 64,
            "asset_ids": [asset_id],
            "quality_score": 0.94,
            "lineage": {"source": "reviewed-assets"},
            "annotation_summary": {"reviewed": 1},
        },
    )
    assert version.status_code == 201, version.text
    version_id = version.json()["data"]["version_id"]
    assert version.json()["data"]["item_count"] == 1

    validated = await api.post(
        f"/api/v1/dataset-versions/{version_id}/transition",
        json={"status": "validated"},
    )
    assert validated.status_code == 200, validated.text
    published = await api.post(
        f"/api/v1/dataset-versions/{version_id}/transition",
        json={"status": "published"},
    )
    assert published.status_code == 200, published.text
    assert published.json()["data"]["status"] == "published"
    listed = await api.get(f"/api/v1/datasets/{dataset['dataset_id']}/versions")
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1
    current = await api.get(f"/api/v1/datasets/{dataset['dataset_id']}")
    assert current.status_code == 200
    assert current.json()["data"]["status"] == "active"
    events = await runtime.state.audit_events("default", "default")
    assert any(event.action == "dataset.version.transition" for event in events)


@pytest.mark.asyncio
async def test_dataset_version_rejects_missing_assets_and_invalid_transition(dataset_client) -> None:
    api, _ = dataset_client
    dataset = (await api.post("/api/v1/datasets", json={"name": "空数据集"})).json()["data"]
    missing = await api.post(
        f"/api/v1/datasets/{dataset['dataset_id']}/versions",
        json={"version": "1", "manifest_sha256": "b" * 64, "asset_ids": ["ast_missing"]},
    )
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "DATASET_CONFLICT"

    empty = await api.post(
        f"/api/v1/datasets/{dataset['dataset_id']}/versions",
        json={"version": "2", "manifest_sha256": "c" * 64},
    )
    assert empty.status_code == 201
    version_id = empty.json()["data"]["version_id"]
    invalid = await api.post(
        f"/api/v1/dataset-versions/{version_id}/transition",
        json={"status": "published"},
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "DATASET_CONFLICT"
