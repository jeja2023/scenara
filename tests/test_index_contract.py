from __future__ import annotations

import pytest

from scenara.platform.index import (
    IndexDefinition,
    IndexRecord,
    IndexRecordKind,
    IndexSourceRef,
    MemoryIndexStore,
)


@pytest.mark.asyncio
async def test_memory_index_contract_supports_vector_and_text_queries_without_cross_tenant_leaks() -> None:
    store = MemoryIndexStore()
    await store.create_index(
        IndexDefinition(
            index_id="portrait.gallery",
            domain="portrait",
            record_kind=IndexRecordKind.VECTOR,
            vector_dimension=2,
            distance_metric="cosine",
            threshold=0.8,
        )
    )
    await store.upsert(
        IndexRecord(
            record_id="r_a",
            tenant_id="tenant-a",
            project_id="project-a",
            index_id="portrait.gallery",
            domain="portrait",
            kind=IndexRecordKind.VECTOR,
            source=IndexSourceRef(source_type="portrait_identity", source_id="identity-a"),
            vector=[1.0, 0.0],
        )
    )
    await store.upsert(
        IndexRecord(
            record_id="r_b",
            tenant_id="tenant-b",
            project_id="project-a",
            index_id="portrait.gallery",
            domain="portrait",
            kind=IndexRecordKind.VECTOR,
            source=IndexSourceRef(source_type="portrait_identity", source_id="identity-b"),
            vector=[1.0, 0.0],
        )
    )

    hits = await store.query_vector("tenant-a", "project-a", "portrait.gallery", [1.0, 0.0])
    assert [hit.record_id for hit in hits] == ["r_a"]
    assert hits[0].source.source_id == "identity-a"
    assert await store.list_records("tenant-a", "project-a", index_id="portrait.gallery")
    assert await store.list_records("tenant-a", "project-a", index_id="portrait.gallery", source_id="identity-b") == []


@pytest.mark.asyncio
async def test_memory_index_deletion_is_tombstoned_and_expiry_is_bounded() -> None:
    store = MemoryIndexStore()
    await store.create_index(
        IndexDefinition(index_id="result.ocr", domain="ocr", record_kind=IndexRecordKind.MULTIMODAL)
    )
    await store.upsert(
        IndexRecord(
            record_id="text-1",
            tenant_id="t",
            project_id="p",
            index_id="result.ocr",
            domain="ocr",
            kind=IndexRecordKind.MULTIMODAL,
            source=IndexSourceRef(source_type="run_result", source_id="run-1"),
            text="invoice number 2026",
            expires_at=10.0,
        )
    )
    assert len(await store.query_text("t", "p", "result.ocr", "invoice")) == 1
    assert await store.delete_source("t", "p", "run_result", "run-1") == 1
    assert await store.query_text("t", "p", "result.ocr", "invoice") == []

    await store.upsert(
        IndexRecord(
            record_id="text-2",
            tenant_id="t",
            project_id="p",
            index_id="result.ocr",
            domain="ocr",
            kind=IndexRecordKind.MULTIMODAL,
            source=IndexSourceRef(source_type="run_result", source_id="run-2"),
            text="expired",
            expires_at=10.0,
        )
    )
    assert await store.delete_expired(10.0, limit=1) == 1
