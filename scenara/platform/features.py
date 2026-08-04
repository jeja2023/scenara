from __future__ import annotations

import math
import time
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class DistanceMetric(StrEnum):
    COSINE = "cosine"
    L2 = "l2"
    INNER_PRODUCT = "inner_product"


class FeatureSpace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_space_id: str
    domain: str
    modality: str
    model_id: str
    model_version: str
    dimension: int = Field(gt=0, le=65_536)
    distance_metric: DistanceMetric
    threshold: float | None = None
    created_at: float = Field(default_factory=time.time)


class FeatureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_id: str
    tenant_id: str
    project_id: str
    feature_space_id: str
    subject_type: str
    subject_id: str
    embedding: list[float]
    created_at: float = Field(default_factory=time.time)
    expires_at: float | None = None


class FeatureMatch(BaseModel):
    feature_id: str
    subject_type: str
    subject_id: str
    score: float
    distance: float


class FeatureStoreError(RuntimeError):
    pass


class FeatureStore(Protocol):
    async def create_space(self, space: FeatureSpace) -> FeatureSpace: ...

    async def get_space(self, feature_space_id: str) -> FeatureSpace | None: ...

    async def add(self, feature: FeatureRecord) -> FeatureRecord: ...

    async def search(
        self,
        tenant_id: str,
        project_id: str,
        feature_space_id: str,
        embedding: list[float],
        *,
        limit: int,
        threshold: float | None = None,
    ) -> list[FeatureMatch]: ...

    async def delete_subject(self, tenant_id: str, project_id: str, subject_type: str, subject_id: str) -> int: ...

    async def delete_expired(self, before: float, limit: int) -> int: ...


def normalize_embedding(vector: list[float], dimension: int) -> list[float]:
    if len(vector) != dimension:
        raise FeatureStoreError(f"embedding dimension must be {dimension}")
    if any(not math.isfinite(value) for value in vector):
        raise FeatureStoreError("embedding contains a non-finite value")
    return [float(value) for value in vector]


def compare_embeddings(space: FeatureSpace, left: list[float], right: list[float]) -> tuple[float, float]:
    left = normalize_embedding(left, space.dimension)
    right = normalize_embedding(right, space.dimension)
    if space.distance_metric == DistanceMetric.COSINE:
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            raise FeatureStoreError("cosine comparison rejects a zero vector")
        score = sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
        score = max(-1.0, min(1.0, score))
        return score, 1.0 - score
    if space.distance_metric == DistanceMetric.L2:
        distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))
        return 1.0 / (1.0 + distance), distance
    score = sum(a * b for a, b in zip(left, right, strict=True))
    return score, -score


class MemoryFeatureStore:
    def __init__(self) -> None:
        self._spaces: dict[str, FeatureSpace] = {}
        self._features: dict[tuple[str, str, str], FeatureRecord] = {}

    async def create_space(self, space: FeatureSpace) -> FeatureSpace:
        existing = self._spaces.get(space.feature_space_id)
        if existing and existing.model_dump(exclude={"created_at"}) != space.model_dump(exclude={"created_at"}):
            raise FeatureStoreError("feature space already exists with a different contract")
        self._spaces[space.feature_space_id] = space.model_copy(deep=True)
        return space.model_copy(deep=True)

    async def get_space(self, feature_space_id: str) -> FeatureSpace | None:
        value = self._spaces.get(feature_space_id)
        return value.model_copy(deep=True) if value else None

    async def add(self, feature: FeatureRecord) -> FeatureRecord:
        space = self._spaces.get(feature.feature_space_id)
        if space is None:
            raise FeatureStoreError("feature space does not exist")
        normalize_embedding(feature.embedding, space.dimension)
        key = (feature.tenant_id, feature.project_id, feature.feature_id)
        if key in self._features:
            raise FeatureStoreError("feature already exists")
        self._features[key] = feature.model_copy(deep=True)
        return feature.model_copy(deep=True)

    async def enroll(
        self,
        tenant_id: str,
        project_id: str,
        feature_space_id: str,
        subject_type: str,
        subject_id: str,
        embedding: list[float],
        expires_at: float | None = None,
    ) -> FeatureRecord:
        return await self.add(
            FeatureRecord(
                feature_id=f"feat_{uuid4().hex}",
                tenant_id=tenant_id,
                project_id=project_id,
                feature_space_id=feature_space_id,
                subject_type=subject_type,
                subject_id=subject_id,
                embedding=embedding,
                expires_at=expires_at,
            )
        )

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
        space = self._spaces.get(feature_space_id)
        if space is None:
            raise FeatureStoreError("feature space does not exist")
        cutoff = space.threshold if threshold is None else threshold
        now = time.time()
        matches: list[FeatureMatch] = []
        for (row_tenant, row_project, _), feature in self._features.items():
            if (row_tenant, row_project, feature.feature_space_id) != (tenant_id, project_id, feature_space_id):
                continue
            if feature.expires_at is not None and feature.expires_at <= now:
                continue
            score, distance = compare_embeddings(space, embedding, feature.embedding)
            if cutoff is None or score >= cutoff:
                matches.append(
                    FeatureMatch(
                        feature_id=feature.feature_id,
                        subject_type=feature.subject_type,
                        subject_id=feature.subject_id,
                        score=score,
                        distance=distance,
                    )
                )
        return sorted(matches, key=lambda item: (-item.score, item.distance, item.feature_id))[:limit]

    async def delete_subject(self, tenant_id: str, project_id: str, subject_type: str, subject_id: str) -> int:
        keys = [
            key
            for key, item in self._features.items()
            if key[:2] == (tenant_id, project_id)
            and item.subject_type == subject_type
            and item.subject_id == subject_id
        ]
        for key in keys:
            del self._features[key]
        return len(keys)

    async def delete_expired(self, before: float, limit: int) -> int:
        if not 1 <= limit <= 10_000:
            raise FeatureStoreError("feature retention limit must be between 1 and 10000")
        keys = sorted(
            key
            for key, item in self._features.items()
            if item.expires_at is not None and item.expires_at <= before
        )[:limit]
        for key in keys:
            del self._features[key]
        return len(keys)


__all__ = [
    "DistanceMetric",
    "FeatureMatch",
    "FeatureRecord",
    "FeatureSpace",
    "FeatureStore",
    "FeatureStoreError",
    "MemoryFeatureStore",
    "compare_embeddings",
    "normalize_embedding",
]
