"""Qdrant HTTP adapter for the platform ``FeatureStore`` port.

The adapter keeps Qdrant-specific collection and payload details behind the
existing feature contract.  Tenant and project are always stored in the
payload and repeated in every filter, so a collection is never treated as a
security boundary by itself.
"""

from __future__ import annotations

from collections.abc import Mapping
import time
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx

from scenara.platform.features import (
    FeatureMatch,
    FeatureRecord,
    FeatureSpace,
    FeatureStoreError,
    DistanceMetric,
    normalize_embedding,
)


class QdrantFeatureStore:
    """FeatureStore implementation using Qdrant's REST API.

    ``client`` is injectable for contract tests and for deployments that
    already own an HTTP client with tracing and authentication middleware.
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
        collection_prefix: str = "scenara_features",
    ) -> None:
        if not base_url.strip():
            raise ValueError("Qdrant base URL is required")
        if timeout_seconds <= 0:
            raise ValueError("Qdrant timeout must be positive")
        self._client = client or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_seconds)
        self._owns_client = client is None
        self._api_key = api_key
        self._prefix = collection_prefix.strip() or "scenara_features"
        self._spaces: dict[str, FeatureSpace] = {}

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        return {"api-key": self._api_key} if self._api_key else {}

    @staticmethod
    def _collection(space: FeatureSpace, prefix: str) -> str:
        # Feature-space IDs are already platform identifiers.  Keep the name
        # deterministic and avoid exposing tenant IDs in collection names.
        from urllib.parse import quote

        return quote(f"{prefix}_{space.feature_space_id}"[:255], safe="")

    @staticmethod
    def _space_point_id(feature_space_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"scenara-feature-space:{feature_space_id}"))

    @staticmethod
    def _point_id(feature_id: str) -> str:
        # Qdrant point IDs are UUIDs or uint64 values; Scenara IDs are opaque
        # prefixed strings, so retain the original ID in payload and use a
        # deterministic UUID at the provider boundary.
        return str(uuid5(NAMESPACE_URL, f"scenara-feature:{feature_id}"))

    async def _request(self, method: str, path: str, *, body: Mapping[str, Any] | None = None) -> Any:
        try:
            response = await self._client.request(method, path, headers=self._headers(), json=body)
        except httpx.RequestError as exc:
            raise FeatureStoreError("Qdrant is unavailable") from exc
        if response.status_code >= 400:
            detail = response.text[:500]
            raise FeatureStoreError(f"Qdrant request failed ({response.status_code}): {detail}")
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise FeatureStoreError("Qdrant returned invalid JSON") from exc

    async def create_space(self, space: FeatureSpace) -> FeatureSpace:
        # Recover persisted metadata before attempting a collection mutation.
        # The in-process cache is intentionally only a cache: a restarted
        # worker must not be allowed to change a feature space's dimension or
        # distance metric by recreating its metadata point.
        existing = await self.get_space(space.feature_space_id)
        if existing is not None:
            if existing.model_dump(exclude={"created_at"}) != space.model_dump(exclude={"created_at"}):
                raise FeatureStoreError("feature space already exists with a different contract")
            return existing
        collection = self._collection(space, self._prefix)
        # Qdrant uses a collection per vector dimension/metric contract.  The
        # local cache prevents an accidental destructive recreation on startup.
        distance = {"cosine": "Cosine", "l2": "Euclid", "inner_product": "Dot"}[space.distance_metric.value]
        try:
            await self._request(
                "PUT",
                f"/collections/{collection}",
                body={"vectors": {"size": space.dimension, "distance": distance}},
            )
        except FeatureStoreError as exc:
            if "(409)" not in str(exc):
                raise
            existing = await self.get_space(space.feature_space_id)
            if existing is None:
                raise FeatureStoreError("feature space collection exists without a Scenara contract") from exc
            if existing.model_dump(exclude={"created_at"}) != space.model_dump(exclude={"created_at"}):
                raise FeatureStoreError("feature space already exists with a different contract") from exc
            return existing
        # Qdrant has no portable arbitrary collection metadata API.  Keep a
        # deterministic metadata point so a new process can recover the full
        # FeatureSpace contract before serving queries.
        await self._request(
            "PUT",
            f"/collections/{collection}/points",
            body={
                "points": [
                    {
                        "id": self._space_point_id(space.feature_space_id),
                        "vector": [0.0] * space.dimension,
                        "payload": {
                            "_scenara_feature_space": True,
                            "feature_space": space.model_dump(mode="json"),
                        },
                    }
                ]
            },
        )
        self._spaces[space.feature_space_id] = space.model_copy(deep=True)
        return space.model_copy(deep=True)

    async def get_space(self, feature_space_id: str) -> FeatureSpace | None:
        space = self._spaces.get(feature_space_id)
        if space is not None:
            return space.model_copy(deep=True)
        probe = FeatureSpace(
            feature_space_id=feature_space_id,
            domain="unknown",
            modality="unknown",
            model_id="unknown",
            model_version="0.0.0",
            dimension=1,
            distance_metric=DistanceMetric.COSINE,
        )
        try:
            result = await self._request(
                "POST",
                f"/collections/{self._collection(probe, self._prefix)}/points",
                body={"ids": [self._space_point_id(feature_space_id)], "with_payload": True},
            )
        except FeatureStoreError as exc:
            if "(404)" in str(exc):
                return None
            raise
        rows = result.get("result", []) if isinstance(result, dict) else []
        if not rows or not isinstance(rows[0], dict):
            return None
        payload = rows[0].get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("feature_space"), dict):
            return None
        space = FeatureSpace.model_validate(payload["feature_space"])
        self._spaces[space.feature_space_id] = space
        return space.model_copy(deep=True)

    async def _all_spaces(self) -> list[FeatureSpace]:
        """Return cached spaces and recover metadata for spaces after restart."""
        try:
            result = await self._request("GET", "/collections")
        except FeatureStoreError:
            # A provider that does not expose collection listing can still
            # serve explicitly requested spaces from the local cache.
            return list(self._spaces.values())
        collections = result.get("result", {}).get("collections", []) if isinstance(result, dict) else []
        if not isinstance(collections, list):
            return list(self._spaces.values())
        from urllib.parse import unquote

        prefix = f"{self._prefix}_"
        for item in collections:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            name = unquote(item["name"])
            if not name.startswith(prefix):
                continue
            await self.get_space(name[len(prefix) :])
        return list(self._spaces.values())

    async def add(self, feature: FeatureRecord) -> FeatureRecord:
        space = await self.get_space(feature.feature_space_id)
        if space is None:
            raise FeatureStoreError("feature space does not exist")
        vector = normalize_embedding(feature.embedding, space.dimension)
        await self._request(
            "PUT",
            f"/collections/{self._collection(space, self._prefix)}/points?wait=true",
            body={
                "points": [
                    {
                        "id": self._point_id(feature.feature_id),
                        "vector": vector,
                        "payload": {
                            "tenant_id": feature.tenant_id,
                            "project_id": feature.project_id,
                            "feature_space_id": feature.feature_space_id,
                            "feature_id": feature.feature_id,
                            "subject_type": feature.subject_type,
                            "subject_id": feature.subject_id,
                            "created_at": feature.created_at,
                            "expires_at": feature.expires_at,
                        },
                    }
                ]
            },
        )
        return feature.model_copy(deep=True)

    async def search(
        self,
        tenant_id: str,
        project_id: str,
        feature_space_id: str,
        embedding: list[float],
        *,
        limit: int,
        threshold: float | None = None,
    ) -> list[FeatureMatch]:
        if not 1 <= limit <= 1000:
            raise FeatureStoreError("feature search limit must be between 1 and 1000")
        space = await self.get_space(feature_space_id)
        if space is None:
            raise FeatureStoreError("feature space does not exist")
        query = normalize_embedding(embedding, space.dimension)
        cutoff = space.threshold if threshold is None else threshold
        result = await self._request(
            "POST",
            f"/collections/{self._collection(space, self._prefix)}/points/search",
            body={
                "vector": query,
                "limit": limit,
                "with_payload": True,
                "filter": {
                    "must": [
                        {"key": "tenant_id", "match": {"value": tenant_id}},
                        {"key": "project_id", "match": {"value": project_id}},
                        {"key": "feature_space_id", "match": {"value": feature_space_id}},
                    ],
                    "must_not": [{"key": "expires_at", "range": {"lte": time.time()}}],
                },
            },
        )
        rows = result.get("result", []) if isinstance(result, dict) else []
        matches: list[FeatureMatch] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            payload = row.get("payload")
            if not isinstance(payload, dict):
                payload = {}
            provider_score = float(row.get("score", 0.0))
            if space.distance_metric == DistanceMetric.L2:
                distance = provider_score
                score = 1.0 / (1.0 + distance)
            elif space.distance_metric == DistanceMetric.COSINE:
                score = provider_score
                distance = 1.0 - score
            else:
                score = provider_score
                distance = -score
            if cutoff is not None and score < cutoff:
                continue
            matches.append(
                FeatureMatch(
                    feature_id=str(payload.get("feature_id") or row.get("id", "")),
                    subject_type=str(payload.get("subject_type", "")),
                    subject_id=str(payload.get("subject_id", "")),
                    score=score,
                    distance=distance,
                )
            )
        return matches

    async def delete_subject(self, tenant_id: str, project_id: str, subject_type: str, subject_id: str) -> int:
        # Qdrant does not return deleted counts for a filter delete.  Scroll
        # first, then delete exact IDs so the port can preserve its count.
        ids = await self._scroll_ids(tenant_id, project_id, subject_type=subject_type, subject_id=subject_id)
        if not ids:
            return 0
        await self._delete_ids(ids)
        return len(ids)

    async def get_feature(self, tenant_id: str, project_id: str, feature_id: str) -> FeatureRecord | None:
        for space in await self._all_spaces():
            result = await self._request(
                "POST",
                f"/collections/{self._collection(space, self._prefix)}/points",
                body={"ids": [self._point_id(feature_id)], "with_payload": True, "with_vector": True},
            )
            rows = result.get("result", []) if isinstance(result, dict) else []
            if rows and isinstance(rows[0], dict):
                record = self._record(rows[0], space)
                if record.tenant_id == tenant_id and record.project_id == project_id:
                    return record
        return None

    async def list_subject_features(
        self, tenant_id: str, project_id: str, feature_space_id: str, subject_type: str, subject_id: str
    ) -> list[FeatureRecord]:
        space = await self.get_space(feature_space_id)
        if space is None:
            raise FeatureStoreError("feature space does not exist")
        rows = await self._scroll(
            space,
            [
                {"key": "tenant_id", "match": {"value": tenant_id}},
                {"key": "project_id", "match": {"value": project_id}},
                {"key": "subject_type", "match": {"value": subject_type}},
                {"key": "subject_id", "match": {"value": subject_id}},
            ],
        )
        return sorted((self._record(row, space) for row in rows), key=lambda item: (item.created_at, item.feature_id))

    async def delete_feature(self, tenant_id: str, project_id: str, feature_id: str) -> bool:
        record = await self.get_feature(tenant_id, project_id, feature_id)
        if record is None:
            return False
        space = await self.get_space(record.feature_space_id)
        if space is None:
            return False
        await self._delete_ids([self._point_id(feature_id)], space=space)
        return True

    async def delete_expired(self, before: float, limit: int) -> int:
        if not 1 <= limit <= 10_000:
            raise FeatureStoreError("feature retention limit must be between 1 and 10000")
        expired: list[tuple[FeatureSpace, str]] = []
        for space in await self._all_spaces():
            rows = await self._scroll(space, [{"key": "expires_at", "range": {"lte": before}}], limit=limit)
            expired.extend((space, str(row.get("id"))) for row in rows if isinstance(row, dict))
        expired = expired[:limit]
        for space, feature_id in expired:
            await self._delete_ids([feature_id], space=space)
        return len(expired)

    async def _scroll_ids(self, tenant_id: str, project_id: str, **extra: str) -> list[str]:
        ids: list[str] = []
        for space in await self._all_spaces():
            must = [
                {"key": "tenant_id", "match": {"value": tenant_id}},
                {"key": "project_id", "match": {"value": project_id}},
                *({"key": key, "match": {"value": value}} for key, value in extra.items()),
            ]
            ids.extend(str(row.get("id")) for row in await self._scroll(space, must, with_vector=False))
        return ids

    async def _scroll(
        self, space: FeatureSpace, must: list[dict[str, Any]], *, with_vector: bool = True, limit: int = 10_000
    ) -> list[dict[str, Any]]:
        result = await self._request(
            "POST",
            f"/collections/{self._collection(space, self._prefix)}/points/scroll",
            body={"limit": limit, "with_payload": True, "with_vector": with_vector, "filter": {"must": must}},
        )
        payload = result.get("result") if isinstance(result, dict) else None
        # Qdrant <= 1.17 returned ``[points, next_page_offset]`` while
        # 1.18 returns ``{"points": [...], "next_page_offset": ...}``.
        # Accept both forms so provider upgrades do not break deletion,
        # retention sweeps, or subject cleanup.
        if isinstance(payload, list):
            rows = payload[0] if payload else []
        elif isinstance(payload, dict):
            rows = payload.get("points", [])
        else:
            rows = []
        return [row for row in rows if isinstance(row, dict)]

    async def _delete_ids(self, ids: list[str], *, space: FeatureSpace | None = None) -> None:
        spaces = [space] if space is not None else list(self._spaces.values())
        for item in spaces:
            await self._request(
                "POST",
                f"/collections/{self._collection(item, self._prefix)}/points/delete?wait=true",
                body={"points": ids},
            )

    @staticmethod
    def _record(row: dict[str, Any], space: FeatureSpace) -> FeatureRecord:
        payload = row.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        return FeatureRecord(
            feature_id=str(payload.get("feature_id") or row.get("id", "")),
            tenant_id=str(payload.get("tenant_id", "")),
            project_id=str(payload.get("project_id", "")),
            feature_space_id=space.feature_space_id,
            subject_type=str(payload.get("subject_type", "")),
            subject_id=str(payload.get("subject_id", "")),
            embedding=normalize_embedding([float(item) for item in row.get("vector", [])], space.dimension),
            created_at=float(payload.get("created_at", time.time())),
            expires_at=float(payload["expires_at"]) if payload.get("expires_at") is not None else None,
        )


__all__ = ["QdrantFeatureStore"]
