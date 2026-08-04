from __future__ import annotations

import httpx
import pytest
from PIL import Image

from scenara.bootstrap import build_runtime
from scenara.domains.portrait.encoder import decode_portrait_image
from scenara.platform.features import DistanceMetric, FeatureSpace
from scenara.server import create_app


def _image_bytes(color: tuple[int, int, int]) -> bytes:
    from io import BytesIO

    output = BytesIO()
    Image.new("RGB", (128, 128), color).save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
async def portrait_client(development_settings):
    runtime = build_runtime(development_settings)
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        yield api, runtime


@pytest.mark.asyncio
async def test_portrait_identity_enroll_search_compare_and_delete(portrait_client) -> None:
    api, runtime = portrait_client
    created = await api.post(
        "/api/v1/portrait/identities",
        json={"display_name": "subject-a", "metadata": {"case": "approved-test"}},
        headers={"X-Principal-Id": "biometric-operator"},
    )
    assert created.status_code == 201, created.text
    identity = created.json()["data"]
    identity_id = identity["identity_id"]

    enrollment_body = {
        "feature_space_id": "portrait.face.arcface.v1",
        "modality": "face",
        "model_id": "arcface",
        "model_version": "1.0.0",
        "distance_metric": "cosine",
        "threshold": 0.8,
        "embedding": [1.0, 0.0, 0.0],
        "quality": 0.97,
    }
    enrolled = await api.post(
        f"/api/v1/portrait/identities/{identity_id}/enrollments",
        json=enrollment_body,
        headers={"X-Principal-Id": "biometric-operator"},
    )
    assert enrolled.status_code == 201, enrolled.text
    assert "embedding" not in enrolled.text
    assert enrolled.json()["data"]["identity_id"] == identity_id

    search = await api.post(
        "/api/v1/portrait/search",
        json={
            "feature_space_id": "portrait.face.arcface.v1",
            "embedding": [0.99, 0.01, 0.0],
            "limit": 10,
        },
    )
    assert search.status_code == 200, search.text
    assert "embedding" not in search.text
    assert search.json()["data"]["matches"][0]["identity"]["identity_id"] == identity_id

    comparison = await api.post(
        "/api/v1/portrait/compare",
        json={
            "feature_space_id": "portrait.face.arcface.v1",
            "left": [1.0, 0.0, 0.0],
            "right": [0.99, 0.01, 0.0],
        },
    )
    assert comparison.status_code == 200
    assert comparison.json()["data"]["matched"] is True

    hidden = await api.get(
        f"/api/v1/portrait/identities/{identity_id}",
        headers={"X-Tenant-Id": "other-tenant"},
    )
    assert hidden.status_code == 404

    deleted = await api.delete(
        f"/api/v1/portrait/identities/{identity_id}",
        headers={"X-Principal-Id": "biometric-operator"},
    )
    assert deleted.status_code == 204
    assert (
        await runtime.features.search(
            "default",
            "default",
            "portrait.face.arcface.v1",
            [1.0, 0.0, 0.0],
            limit=10,
        )
        == []
    )
    events = await runtime.state.audit_events("default", "default")
    deletion = next(event for event in events if event.action == "portrait.identity.delete")
    assert deletion.evidence["biometric_deletion"] is True


@pytest.mark.asyncio
async def test_feature_spaces_reject_cross_model_vectors(portrait_client) -> None:
    api, _ = portrait_client
    identity = (await api.post("/api/v1/portrait/identities", json={"display_name": "subject-b"})).json()["data"]
    first = await api.post(
        f"/api/v1/portrait/identities/{identity['identity_id']}/enrollments",
        json={
            "feature_space_id": "portrait.body.osnet.v1",
            "modality": "body",
            "model_id": "osnet",
            "model_version": "1.0.0",
            "distance_metric": "cosine",
            "embedding": [1.0, 0.0],
            "quality": 0.9,
        },
    )
    assert first.status_code == 201
    conflict = await api.post(
        f"/api/v1/portrait/identities/{identity['identity_id']}/enrollments",
        json={
            "feature_space_id": "portrait.body.osnet.v1",
            "modality": "body",
            "model_id": "different-model",
            "model_version": "2.0.0",
            "distance_metric": "cosine",
            "embedding": [1.0, 0.0],
            "quality": 0.9,
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "FEATURE_SPACE_CONFLICT"


@pytest.mark.asyncio
async def test_portrait_image_enrollment_search_and_compare_redact_embeddings(portrait_client) -> None:
    api, runtime = portrait_client
    identity = (await api.post("/api/v1/portrait/identities", json={"display_name": "image-subject"})).json()["data"]
    image = _image_bytes((180, 120, 80))
    enrolled = await api.post(
        f"/api/v1/portrait/identities/{identity['identity_id']}/enrollments/image",
        files={"file": ("subject.png", image, "image/png")},
    )
    assert enrolled.status_code == 201, enrolled.text
    assert "embedding" not in enrolled.text

    search = await api.post(
        "/api/v1/portrait/search/image",
        files={"file": ("query.png", image, "image/png")},
    )
    assert search.status_code == 200, search.text
    assert search.json()["data"]["matches"][0]["identity"]["identity_id"] == identity["identity_id"]
    compare = await api.post(
        "/api/v1/portrait/compare/images",
        files={"left": ("left.png", image, "image/png"), "right": ("right.png", image, "image/png")},
    )
    assert compare.status_code == 200, compare.text
    payload = compare.json()["data"]
    assert payload["matched"] is True
    assert payload["left"]["embedding_dimension"] > 0
    assert '"embedding":' not in compare.text

    uploaded = await api.post(
        "/api/v1/media/assets",
        files={"file": ("reference.png", image, "image/png")},
        data={"kind": "image"},
    )
    assert uploaded.status_code == 201, uploaded.text
    asset_id = uploaded.json()["data"]["asset_id"]
    mixed = await api.post(
        "/api/v1/portrait/compare/asset-image",
        files={"file": ("right.png", image, "image/png")},
        data={"asset_id": asset_id},
    )
    assert mixed.status_code == 200, mixed.text
    assert mixed.json()["data"]["mode"] == "mixed"
    reverse_mixed = await api.post(
        "/api/v1/portrait/compare/image-asset",
        files={"file": ("left.png", image, "image/png")},
        data={"asset_id": asset_id},
    )
    assert reverse_mixed.status_code == 200, reverse_mixed.text
    assert reverse_mixed.json()["data"]["mode"] == "mixed"

    indexes = await api.get("/api/v1/indexes")
    assert indexes.status_code == 200
    index_definition = indexes.json()["data"][0]
    index_id = index_definition["index_id"]
    records = await api.get(f"/api/v1/indexes/{index_id}/records")
    assert records.status_code == 200
    assert records.json()["data"][0]["has_vector"] is True
    assert '"vector":' not in records.text
    vector_hits = await api.post(
        f"/api/v1/indexes/{index_id}/query/vector",
        json={"vector": [1.0] + [0.0] * (index_definition["vector_dimension"] - 1)},
    )
    assert vector_hits.status_code == 200, vector_hits.text
    assert '"vector":' not in vector_hits.text
    events = await runtime.state.audit_events("default", "default")
    assert any(event.action == "portrait.compare.image" for event in events)
    assert any(event.action == "index.query.vector" for event in events)


@pytest.mark.asyncio
async def test_portrait_image_operations_enforce_model_contract(portrait_client) -> None:
    api, runtime = portrait_client
    image = _image_bytes((90, 140, 210))
    encoded = await runtime.portrait.encoder.encode(decode_portrait_image(image))
    await runtime.features.create_space(
        FeatureSpace(
            feature_space_id="portrait.face.other-model.v1",
            domain="portrait",
            modality="face",
            model_id="other-model",
            model_version="1.0.0",
            dimension=len(encoded.embedding),
            distance_metric=DistanceMetric.COSINE,
            threshold=0.8,
        )
    )

    search = await api.post(
        "/api/v1/portrait/search/image",
        files={"file": ("query.png", image, "image/png")},
        data={"feature_space_id": "portrait.face.other-model.v1"},
    )
    assert search.status_code == 409, search.text
    assert search.json()["error"]["code"] == "PORTRAIT_CONFLICT"

    compare = await api.post(
        "/api/v1/portrait/compare/images",
        files={
            "left": ("left.png", image, "image/png"),
            "right": ("right.png", image, "image/png"),
        },
        data={"feature_space_id": "portrait.face.other-model.v1"},
    )
    assert compare.status_code == 409, compare.text
    assert compare.json()["error"]["code"] == "PORTRAIT_CONFLICT"


@pytest.mark.asyncio
async def test_expired_biometric_features_are_physically_removed(portrait_client) -> None:
    api, runtime = portrait_client
    identity = (await api.post("/api/v1/portrait/identities", json={"display_name": "expiring"})).json()["data"]
    enrollment = await api.post(
        f"/api/v1/portrait/identities/{identity['identity_id']}/enrollments",
        json={
            "feature_space_id": "portrait.face.expiring.v1",
            "modality": "face",
            "model_id": "expiring-model",
            "model_version": "1.0.0",
            "distance_metric": "cosine",
            "embedding": [1.0, 0.0],
            "quality": 0.9,
            "expires_at": 1.0,
        },
    )
    assert enrollment.status_code == 201
    enrollment_payload = enrollment.json()["data"]
    assert enrollment_payload["expires_at"] == 1.0
    indexed = await api.get("/api/v1/indexes/portrait.identity.portrait.face.expiring.v1/records")
    assert indexed.status_code == 200
    assert indexed.json()["data"][0]["expires_at"] == 1.0
    assert await runtime.features.delete_expired(2.0, 100) == 1
    assert await runtime.indexes.delete_expired(2.0, 100) == 1
    assert (
        await runtime.indexes.list_records(
            "default",
            "default",
            index_id="portrait.identity.portrait.face.expiring.v1",
        )
        == []
    )
    assert (
        await runtime.indexes.list_records(
            "default",
            "default",
            index_id="portrait.identity.portrait.face.arcface.v1",
        )
        == []
    )
    assert await runtime.features.delete_expired(2.0, 100) == 0
