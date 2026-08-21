from __future__ import annotations

import httpx
import pytest

from scenara.infrastructure.qdrant_features import QdrantFeatureStore
from scenara.platform.features import DistanceMetric, FeatureRecord, FeatureSpace


class FakeQdrant:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, object] | None]] = []
        self.collections: set[str] = set()
        self.metadata: dict[str, dict[str, object]] = {}
        self.metadata_ids: dict[str, object] = {}

    async def request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        body = kwargs.get("json")
        assert body is None or isinstance(body, dict)
        self.requests.append((method, path, body))
        if method == "PUT" and path.startswith("/collections/") and path.endswith("/points"):
            collection = path.removeprefix("/collections/").removesuffix("/points")
            self.collections.add(collection)
            points = body.get("points", []) if body else []
            if points and isinstance(points[0], dict):
                payload = points[0].get("payload")
                if isinstance(payload, dict) and payload.get("_scenara_feature_space"):
                    self.metadata[collection] = payload
                    self.metadata_ids[collection] = points[0].get("id")
            return httpx.Response(200, json={"result": {"status": "ok"}})
        if method == "GET" and path == "/collections":
            return httpx.Response(200, json={"result": {"collections": [{"name": item} for item in self.collections]}})
        if method == "POST" and path.endswith("/points/search"):
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "id": "feat_a",
                            "score": 0.97,
                            "payload": {"subject_type": "person", "subject_id": "person_a"},
                        }
                    ]
                },
            )
        if method == "POST" and path.endswith("/points/scroll"):
            return httpx.Response(
                200,
                json={
                    "result": [
                        [
                            {
                                "id": "feat_a",
                                "vector": [1.0, 0.0],
                                "payload": {
                                    "tenant_id": "tenant_a",
                                    "project_id": "project_a",
                                    "feature_space_id": "person/body/reid",
                                    "subject_type": "person",
                                    "subject_id": "person_a",
                                    "created_at": 10.0,
                                    "expires_at": 20.0,
                                },
                            }
                        ],
                        None,
                    ]
                },
            )
        if method == "POST" and path.endswith("/points"):
            collection = path.removeprefix("/collections/").removesuffix("/points")
            metadata = self.metadata.get(collection)
            ids = body.get("ids", []) if body else []
            if metadata is not None and ids and ids[0] == self.metadata_ids.get(collection):
                return httpx.Response(
                    200,
                    json={"result": [{"id": "metadata", "payload": metadata}]},
                )
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "id": "feat_a",
                            "vector": [1.0, 0.0],
                            "payload": {
                                "tenant_id": "tenant_a",
                                "project_id": "project_a",
                                "feature_space_id": "person/body/reid",
                                "feature_id": "feat_a",
                                "subject_type": "person",
                                "subject_id": "person_a",
                                "created_at": 10.0,
                            },
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"result": {"status": "ok"}})


@pytest.mark.asyncio
async def test_qdrant_feature_store_preserves_feature_contract_and_scope() -> None:
    fake = FakeQdrant()
    store = QdrantFeatureStore("https://qdrant.example", client=fake)  # type: ignore[arg-type]
    space = FeatureSpace(
        feature_space_id="person/body/reid",
        domain="portrait",
        modality="body",
        model_id="osnet",
        model_version="1.0.0",
        dimension=2,
        distance_metric=DistanceMetric.COSINE,
        threshold=0.8,
    )
    await store.create_space(space)
    feature = FeatureRecord(
        feature_id="feat_a",
        tenant_id="tenant_a",
        project_id="project_a",
        feature_space_id=space.feature_space_id,
        subject_type="person",
        subject_id="person_a",
        embedding=[1.0, 0.0],
        created_at=10.0,
    )
    assert await store.add(feature) == feature
    matches = await store.search("tenant_a", "project_a", space.feature_space_id, [1.0, 0.0], limit=5)
    assert matches[0].subject_id == "person_a"
    assert matches[0].score == pytest.approx(0.97)
    search = next(body for method, path, body in fake.requests if method == "POST" and path.endswith("/points/search"))
    assert search is not None
    assert {item["key"] for item in search["filter"]["must"]} == {"tenant_id", "project_id", "feature_space_id"}
    assert "must_not" in search["filter"]


@pytest.mark.asyncio
async def test_qdrant_feature_store_maps_provider_distance_and_feature_id() -> None:
    fake = FakeQdrant()
    store = QdrantFeatureStore("https://qdrant.example", client=fake)  # type: ignore[arg-type]
    space = FeatureSpace(
        feature_space_id="person/body/reid",
        domain="portrait",
        modality="body",
        model_id="osnet",
        model_version="1.0.0",
        dimension=2,
        distance_metric=DistanceMetric.L2,
    )
    await store.create_space(space)
    record = await store.get_feature("tenant_a", "project_a", "feat_a")
    assert record is not None
    assert record.feature_id == "feat_a"
    fake.requests.clear()
    matches = await store.search("tenant_a", "project_a", space.feature_space_id, [1.0, 0.0], limit=5)
    assert matches[0].score == pytest.approx(1.0 / 1.97)
    assert matches[0].distance == pytest.approx(0.97)


@pytest.mark.asyncio
async def test_qdrant_feature_store_recovers_spaces_after_process_restart() -> None:
    fake = FakeQdrant()
    first = QdrantFeatureStore("https://qdrant.example", client=fake)  # type: ignore[arg-type]
    space = FeatureSpace(
        feature_space_id="person/body/reid",
        domain="portrait",
        modality="body",
        model_id="osnet",
        model_version="1.0.0",
        dimension=2,
        distance_metric=DistanceMetric.COSINE,
    )
    await first.create_space(space)
    restarted = QdrantFeatureStore("https://qdrant.example", client=fake)  # type: ignore[arg-type]
    recovered = await restarted.get_space(space.feature_space_id)
    assert recovered is not None
    assert recovered.model_id == "osnet"


@pytest.mark.asyncio
async def test_qdrant_feature_store_deletes_expired_and_subject_records() -> None:
    fake = FakeQdrant()
    store = QdrantFeatureStore("https://qdrant.example", client=fake)  # type: ignore[arg-type]
    space = FeatureSpace(
        feature_space_id="person/body/reid",
        domain="portrait",
        modality="body",
        model_id="osnet",
        model_version="1.0.0",
        dimension=2,
        distance_metric=DistanceMetric.COSINE,
    )
    await store.create_space(space)
    assert await store.delete_subject("tenant_a", "project_a", "person", "person_a") == 1
    assert await store.delete_expired(30.0, 10) == 1
    deletes = [body for method, path, body in fake.requests if method == "POST" and path.endswith("/points/delete")]
    assert len(deletes) == 2
    assert all(body and len(body["points"]) == 1 for body in deletes)
