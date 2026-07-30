from __future__ import annotations

import httpx
import pytest

from scenara.bootstrap import build_runtime
from scenara.server import create_app


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
    assert await runtime.features.delete_expired(2.0, 100) == 1
    assert await runtime.features.delete_expired(2.0, 100) == 0
