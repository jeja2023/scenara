"""结果索引仓储的跨后端契约。

索引承担跨领域结果检索：向量近邻、全文命中、墓碑删除和过期清理的语义一旦在
内存与 PostgreSQL 之间漂移，开发环境查得到的结果在生产就可能查不到，或者已
删除的记录在生产仍被检出。
"""

from __future__ import annotations

from uuid import uuid4

from scenara.platform.index import (
    IndexDefinition,
    IndexRecord,
    IndexRecordKind,
    IndexSourceRef,
    IndexStore,
)


async def assert_index_store_contract(
    store: IndexStore,
    *,
    tenant_id: str,
    project_id: str,
    other_tenant_id: str,
) -> None:
    """跑完整套契约；任一后端不满足即抛 AssertionError。"""

    suffix = uuid4().hex[:16]
    vector_index = f"portrait.gallery.{suffix}"
    text_index = f"result.ocr.{suffix}"

    definition = await store.create_index(
        IndexDefinition(
            index_id=vector_index,
            domain="portrait",
            record_kind=IndexRecordKind.VECTOR,
            vector_dimension=2,
            distance_metric="cosine",
            threshold=0.8,
        )
    )
    assert definition.index_id == vector_index
    stored_definition = await store.get_index(vector_index)
    assert stored_definition is not None
    assert stored_definition.vector_dimension == 2
    assert stored_definition.distance_metric == "cosine"
    await store.create_index(
        IndexDefinition(
            index_id=text_index, domain="ocr", record_kind=IndexRecordKind.MULTIMODAL
        )
    )
    portrait_indexes = await store.list_indexes(tenant_id, project_id, domain="portrait")
    assert vector_index in {item.index_id for item in portrait_indexes}
    assert text_index not in {item.index_id for item in portrait_indexes}

    def vector_record(record_id: str, tenant: str, source_id: str) -> IndexRecord:
        return IndexRecord(
            record_id=record_id,
            tenant_id=tenant,
            project_id=project_id,
            index_id=vector_index,
            domain="portrait",
            kind=IndexRecordKind.VECTOR,
            source=IndexSourceRef(source_type="portrait_identity", source_id=source_id),
            vector=[1.0, 0.0],
        )

    mine = f"idxr_{uuid4().hex}"
    theirs = f"idxr_{uuid4().hex}"
    await store.upsert(vector_record(mine, tenant_id, "identity-mine"))
    await store.upsert(vector_record(theirs, other_tenant_id, "identity-theirs"))

    # 记录往返：向量不出边界，但源引用与元数据必须完整保留。
    fetched = await store.get(tenant_id, project_id, mine)
    assert fetched is not None
    assert fetched.source.source_type == "portrait_identity"
    assert fetched.source.source_id == "identity-mine"

    # 向量近邻不得跨租户泄漏。
    hits = await store.query_vector(tenant_id, project_id, vector_index, [1.0, 0.0])
    assert [hit.record_id for hit in hits] == [mine]
    assert hits[0].source.source_id == "identity-mine"

    # 源过滤按 source_id 精确收敛。
    assert await store.list_records(tenant_id, project_id, index_id=vector_index)
    assert (
        await store.list_records(
            tenant_id, project_id, index_id=vector_index, source_id="identity-theirs"
        )
        == []
    )

    # 批量写入与单条写入语义一致。
    batch = await store.upsert_many(
        [
            vector_record(f"idxr_{uuid4().hex}", tenant_id, f"identity-batch-{index}")
            for index in range(3)
        ]
    )
    assert len(batch) == 3
    paged = await store.list_records(
        tenant_id, project_id, index_id=vector_index, offset=1, limit=2
    )
    assert len(paged) == 2

    # 全文命中可检索，删除后立即不可见（墓碑而非物理删除）。
    text_record_id = f"idxr_{uuid4().hex}"
    run_id = f"run-{suffix}"
    await store.upsert(
        IndexRecord(
            record_id=text_record_id,
            tenant_id=tenant_id,
            project_id=project_id,
            index_id=text_index,
            domain="ocr",
            kind=IndexRecordKind.MULTIMODAL,
            source=IndexSourceRef(source_type="run_result", source_id=run_id),
            text="invoice number 2026",
            expires_at=10.0,
        )
    )
    assert len(await store.query_text(tenant_id, project_id, text_index, "invoice")) == 1
    assert await store.delete_source(tenant_id, project_id, "run_result", run_id) == 1
    assert await store.query_text(tenant_id, project_id, text_index, "invoice") == []

    # 按资产删除覆盖同一资产下的全部记录。
    asset_id = f"ast_{uuid4().hex}"
    for _ in range(2):
        await store.upsert(
            IndexRecord(
                record_id=f"idxr_{uuid4().hex}",
                tenant_id=tenant_id,
                project_id=project_id,
                index_id=text_index,
                domain="ocr",
                kind=IndexRecordKind.MULTIMODAL,
                source=IndexSourceRef(
                    source_type="run_result", source_id=f"run-{uuid4().hex[:8]}", asset_id=asset_id
                ),
                text="asset scoped",
            )
        )
    assert await store.delete_asset(tenant_id, project_id, asset_id) == 2

    # 过期清理受 limit 约束，避免一次删除拖垮数据库。
    for _ in range(2):
        await store.upsert(
            IndexRecord(
                record_id=f"idxr_{uuid4().hex}",
                tenant_id=tenant_id,
                project_id=project_id,
                index_id=text_index,
                domain="ocr",
                kind=IndexRecordKind.MULTIMODAL,
                source=IndexSourceRef(source_type="run_result", source_id=f"run-{uuid4().hex[:8]}"),
                text="expired",
                expires_at=10.0,
            )
        )
    assert await store.delete_expired(10.0, limit=1) == 1

    # 重建返回 (总数, 就绪数) 而不是抛错。
    total, ready = await store.rebuild(tenant_id, project_id, vector_index)
    assert total >= ready >= 0


__all__ = ["assert_index_store_contract"]
