from __future__ import annotations

import math
import time
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class IndexRecordKind(StrEnum):
    VECTOR = "vector"
    TEXT = "text"
    MULTIMODAL = "multimodal"


class IndexRecordStatus(StrEnum):
    READY = "ready"
    PENDING = "pending"
    FAILED = "failed"
    DELETED = "deleted"


class IndexDefinition(BaseModel):
    """Stable contract shared by result, biometric and future search indexes."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    index_id: str = Field(min_length=2, max_length=128)
    schema_version: str = Field(default="1.0", min_length=1, max_length=32)
    domain: str = Field(min_length=1, max_length=64)
    record_kind: IndexRecordKind
    vector_dimension: int | None = Field(default=None, gt=0, le=65_536)
    vector_model_id: str | None = Field(default=None, max_length=128)
    vector_model_version: str | None = Field(default=None, max_length=64)
    distance_metric: str | None = Field(default=None, max_length=32)
    threshold: float | None = Field(default=None, ge=-1, le=1)
    text_analyzer: str | None = Field(default=None, max_length=128)
    created_at: float = Field(default_factory=time.time)


class IndexSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    source_type: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=256)
    asset_id: str | None = None
    run_id: str | None = None
    unit_id: str | None = None
    object_id: str | None = None
    artifact_id: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    pts_ms: int | None = Field(default=None, ge=0)


class IndexRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    record_id: str = Field(default_factory=lambda: f"idxr_{uuid4().hex}")
    tenant_id: str
    project_id: str
    index_id: str
    domain: str
    kind: IndexRecordKind
    source: IndexSourceRef
    feature_id: str | None = None
    text: str | None = Field(default=None, max_length=1_000_000)
    vector: list[float] | None = Field(default=None, max_length=65_536)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: IndexRecordStatus = IndexRecordStatus.READY
    created_at: float = Field(default_factory=time.time)
    expires_at: float | None = None
    deleted_at: float | None = None


class IndexHit(BaseModel):
    record_id: str
    index_id: str
    domain: str
    source: IndexSourceRef
    feature_id: str | None = None
    score: float | None = None
    distance: float | None = None
    text_snippet: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexRecordView(BaseModel):
    """Public projection. Raw vectors never cross the API boundary."""

    record_id: str
    index_id: str
    domain: str
    kind: IndexRecordKind
    source: IndexSourceRef
    feature_id: str | None = None
    has_vector: bool = False
    text_snippet: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: IndexRecordStatus
    created_at: float
    expires_at: float | None = None
    deleted_at: float | None = None


class IndexTextQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    query: str = Field(min_length=1, max_length=10_000)
    limit: int = Field(default=20, ge=1, le=200)


class IndexVectorQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    vector: list[float] = Field(min_length=1, max_length=65_536)
    limit: int = Field(default=20, ge=1, le=200)
    threshold: float | None = Field(default=None, ge=-1, le=1)


class IndexStoreError(RuntimeError):
    pass


class IndexStore(Protocol):
    async def create_index(self, definition: IndexDefinition) -> IndexDefinition: ...

    async def get_index(self, index_id: str) -> IndexDefinition | None: ...

    async def list_indexes(
        self, tenant_id: str, project_id: str, *, domain: str | None = None
    ) -> list[IndexDefinition]: ...

    async def upsert(self, record: IndexRecord) -> IndexRecord: ...

    async def upsert_many(self, records: list[IndexRecord]) -> list[IndexRecord]: ...

    async def get(self, tenant_id: str, project_id: str, record_id: str) -> IndexRecord | None: ...

    async def list_records(
        self,
        tenant_id: str,
        project_id: str,
        *,
        index_id: str | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[IndexRecord]: ...

    async def query_vector(
        self,
        tenant_id: str,
        project_id: str,
        index_id: str,
        vector: list[float],
        *,
        limit: int = 20,
        threshold: float | None = None,
    ) -> list[IndexHit]: ...

    async def query_text(
        self,
        tenant_id: str,
        project_id: str,
        index_id: str,
        query: str,
        *,
        limit: int = 20,
    ) -> list[IndexHit]: ...

    async def delete_source(self, tenant_id: str, project_id: str, source_type: str, source_id: str) -> int: ...

    async def delete_asset(self, tenant_id: str, project_id: str, asset_id: str) -> int: ...

    async def delete_expired(self, before: float, limit: int = 10_000) -> int: ...

    async def rebuild(self, tenant_id: str, project_id: str, index_id: str) -> tuple[int, int]: ...


def _score(definition: IndexDefinition, query: list[float], candidate: list[float]) -> tuple[float, float]:
    if definition.vector_dimension != len(query) or definition.vector_dimension != len(candidate):
        raise IndexStoreError("vector dimension does not match index contract")
    if any(not math.isfinite(value) for value in (*query, *candidate)):
        raise IndexStoreError("vector contains a non-finite value")
    metric = definition.distance_metric or "cosine"
    if metric == "cosine":
        query_norm = math.sqrt(sum(value * value for value in query))
        candidate_norm = math.sqrt(sum(value * value for value in candidate))
        if query_norm == 0 or candidate_norm == 0:
            raise IndexStoreError("cosine query rejects a zero vector")
        score = sum(a * b for a, b in zip(query, candidate, strict=True)) / (query_norm * candidate_norm)
        score = max(-1.0, min(1.0, score))
        return score, 1.0 - score
    if metric == "l2":
        distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(query, candidate, strict=True)))
        return 1.0 / (1.0 + distance), distance
    if metric == "inner_product":
        score = sum(a * b for a, b in zip(query, candidate, strict=True))
        return score, -score
    raise IndexStoreError(f"unsupported index distance metric: {metric}")


def _validate_vector(definition: IndexDefinition, vector: list[float]) -> None:
    if definition.vector_dimension != len(vector):
        raise IndexStoreError("index vector dimension does not match its contract")
    if any(not math.isfinite(value) for value in vector):
        raise IndexStoreError("index vector contains a non-finite value")


class MemoryIndexStore:
    def __init__(self) -> None:
        self._indexes: dict[str, IndexDefinition] = {}
        self._records: dict[tuple[str, str, str], IndexRecord] = {}

    async def create_index(self, definition: IndexDefinition) -> IndexDefinition:
        existing = self._indexes.get(definition.index_id)
        if existing and existing.model_dump(exclude={"created_at"}) != definition.model_dump(exclude={"created_at"}):
            raise IndexStoreError("index contract conflicts with an existing definition")
        self._indexes[definition.index_id] = definition.model_copy(deep=True)
        return definition.model_copy(deep=True)

    async def get_index(self, index_id: str) -> IndexDefinition | None:
        value = self._indexes.get(index_id)
        return value.model_copy(deep=True) if value else None

    async def list_indexes(
        self, tenant_id: str, project_id: str, *, domain: str | None = None
    ) -> list[IndexDefinition]:
        del tenant_id, project_id
        rows = [item for item in self._indexes.values() if domain is None or item.domain == domain]
        return [item.model_copy(deep=True) for item in sorted(rows, key=lambda item: item.index_id)]

    async def upsert(self, record: IndexRecord) -> IndexRecord:
        definition = self._indexes.get(record.index_id)
        if definition is None:
            raise IndexStoreError("index definition does not exist")
        if record.domain != definition.domain or record.kind != definition.record_kind:
            raise IndexStoreError("index record does not match its contract")
        if definition.vector_dimension is not None:
            if record.vector is not None:
                _validate_vector(definition, record.vector)
            if definition.record_kind == IndexRecordKind.VECTOR and record.vector is None and record.feature_id is None:
                raise IndexStoreError("vector index records require a vector or feature reference")
        if definition.record_kind == IndexRecordKind.TEXT and not (record.text or "").strip():
            raise IndexStoreError("text index records require text")
        key = (record.tenant_id, record.project_id, record.record_id)
        self._records[key] = record.model_copy(deep=True)
        return record.model_copy(deep=True)

    async def upsert_many(self, records: list[IndexRecord]) -> list[IndexRecord]:
        upserted: list[IndexRecord] = []
        for record in records:
            upserted.append(await self.upsert(record))
        return upserted

    async def get(self, tenant_id: str, project_id: str, record_id: str) -> IndexRecord | None:
        value = self._records.get((tenant_id, project_id, record_id))
        return value.model_copy(deep=True) if value else None

    async def list_records(self, tenant_id: str, project_id: str, *, index_id: str | None = None,
                           source_type: str | None = None, source_id: str | None = None,
                           offset: int = 0, limit: int = 100) -> list[IndexRecord]:
        if offset < 0 or not 1 <= limit <= 1000:
            raise IndexStoreError("invalid index pagination")
        rows = [
            item for (row_tenant, row_project, _), item in self._records.items()
            if (row_tenant, row_project) == (tenant_id, project_id)
            and item.status != IndexRecordStatus.DELETED
            and (index_id is None or item.index_id == index_id)
            and (source_type is None or item.source.source_type == source_type)
            and (source_id is None or item.source.source_id == source_id)
        ]
        rows.sort(key=lambda item: (item.created_at, item.record_id), reverse=True)
        return [item.model_copy(deep=True) for item in rows[offset : offset + limit]]

    async def query_vector(self, tenant_id: str, project_id: str, index_id: str, vector: list[float], *,
                           limit: int = 20, threshold: float | None = None) -> list[IndexHit]:
        if not 1 <= limit <= 200:
            raise IndexStoreError("index query limit must be between 1 and 200")
        definition = self._indexes.get(index_id)
        if definition is None or definition.vector_dimension is None:
            raise IndexStoreError("vector index definition does not exist")
        rows: list[IndexRecord] = []
        offset = 0
        while True:
            page = await self.list_records(
                tenant_id, project_id, index_id=index_id, offset=offset, limit=1000
            )
            rows.extend(page)
            if len(page) < 1000:
                break
            offset += len(page)
        hits: list[IndexHit] = []
        for record in rows:
            if record.vector is None:
                continue
            score, distance = _score(definition, vector, record.vector)
            cutoff = definition.model_dump().get("threshold") if threshold is None else threshold
            if cutoff is None or score >= cutoff:
                hits.append(IndexHit(record_id=record.record_id, index_id=index_id, domain=record.domain,
                                     source=record.source, feature_id=record.feature_id, score=score, distance=distance,
                                     metadata=record.metadata))
        return sorted(
            hits,
            key=lambda item: (-float(item.score or 0), float(item.distance or 0), item.record_id),
        )[:limit]

    async def query_text(
        self, tenant_id: str, project_id: str, index_id: str, query: str, *, limit: int = 20
    ) -> list[IndexHit]:
        if not query.strip():
            return []
        definition = self._indexes.get(index_id)
        if definition is None or definition.record_kind == IndexRecordKind.VECTOR:
            raise IndexStoreError("text index definition does not exist")
        rows: list[IndexRecord] = []
        offset = 0
        while True:
            page = await self.list_records(
                tenant_id, project_id, index_id=index_id, offset=offset, limit=1000
            )
            rows.extend(page)
            if len(page) < 1000:
                break
            offset += len(page)
        terms = {term.casefold() for term in query.split() if term.strip()}
        hits: list[IndexHit] = []
        for record in rows:
            text = (record.text or "").casefold()
            matched = sum(1 for term in terms if term in text)
            if matched:
                hits.append(IndexHit(record_id=record.record_id, index_id=index_id, domain=record.domain,
                                     source=record.source, feature_id=record.feature_id,
                                     score=matched / max(1, len(terms)),
                                     text_snippet=(record.text or "")[:240], metadata=record.metadata))
        return sorted(hits, key=lambda item: (-float(item.score or 0), item.record_id))[:limit]

    async def delete_source(self, tenant_id: str, project_id: str, source_type: str, source_id: str) -> int:
        keys = [key for key, item in self._records.items() if key[:2] == (tenant_id, project_id)
                and item.source.source_type == source_type and item.source.source_id == source_id]
        for key in keys:
            self._records[key] = self._records[key].model_copy(update={"status": IndexRecordStatus.DELETED,
                                                                         "deleted_at": time.time()})
        return len(keys)

    async def delete_asset(self, tenant_id: str, project_id: str, asset_id: str) -> int:
        keys = [
            key
            for key, item in self._records.items()
            if key[:2] == (tenant_id, project_id)
            and item.source.asset_id == asset_id
            and item.status != IndexRecordStatus.DELETED
        ]
        for key in keys:
            self._records[key] = self._records[key].model_copy(
                update={"status": IndexRecordStatus.DELETED, "deleted_at": time.time()}
            )
        return len(keys)

    async def delete_expired(self, before: float, limit: int = 10_000) -> int:
        if not 1 <= limit <= 10_000:
            raise IndexStoreError("index retention limit must be between 1 and 10000")
        keys = sorted((key for key, item in self._records.items()
                       if item.status != IndexRecordStatus.DELETED
                       and item.expires_at is not None and item.expires_at <= before),
                      key=lambda key: (self._records[key].expires_at or 0, key))[:limit]
        for key in keys:
            self._records[key] = self._records[key].model_copy(update={"status": IndexRecordStatus.DELETED,
                                                                         "deleted_at": before})
        return len(keys)

    async def rebuild(self, tenant_id: str, project_id: str, index_id: str) -> tuple[int, int]:
        """Validate and refresh the in-memory projection for an index.

        Memory search is computed directly from records, so rebuilding is a
        consistency pass.  Returning both counts keeps the contract identical
        to a persistent ANN/text backend that materializes a separate index.
        """
        if index_id not in self._indexes:
            raise IndexStoreError("index definition does not exist")
        records: list[IndexRecord] = []
        offset = 0
        while True:
            page = await self.list_records(tenant_id, project_id, index_id=index_id, offset=offset, limit=1000)
            records.extend(page)
            if len(page) < 1000:
                break
            offset += len(page)
        rebuilt = 0
        for record in records:
            definition = self._indexes[index_id]
            if record.vector is not None and definition.vector_dimension is not None:
                _validate_vector(definition, record.vector)
            rebuilt += 1
        return len(records), rebuilt


__all__ = [
    "IndexDefinition",
    "IndexHit",
    "IndexRecord",
    "IndexRecordKind",
    "IndexRecordStatus",
    "IndexRecordView",
    "IndexSourceRef",
    "IndexStore",
    "IndexStoreError",
    "IndexTextQueryRequest",
    "IndexVectorQueryRequest",
    "MemoryIndexStore",
]
