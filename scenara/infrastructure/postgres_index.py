from __future__ import annotations

from typing import Any

from scenara.platform.index import (
    IndexDefinition,
    IndexHit,
    IndexRecord,
    IndexStoreError,
    MemoryIndexStore,
    _validate_vector,
)


class PostgresIndexStore:
    """PostgreSQL implementation of the index contract.

    Vector scoring deliberately stays behind the contract. Deployments can replace
    the JSONB scan with pgvector or an external index without changing callers.
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def create_index(self, definition: IndexDefinition) -> IndexDefinition:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn:
            await conn.execute(
                """INSERT INTO scenara_indexes
                (index_id, schema_version, domain, record_kind, vector_dimension,
                 vector_model_id, vector_model_version, distance_metric, threshold,
                 text_analyzer, created_at, document)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), %s)
                ON CONFLICT (index_id) DO NOTHING""",
                (
                    definition.index_id,
                    definition.schema_version,
                    definition.domain,
                    definition.record_kind,
                    definition.vector_dimension,
                    definition.vector_model_id,
                    definition.vector_model_version,
                    definition.distance_metric,
                    definition.threshold,
                    definition.text_analyzer,
                    definition.created_at,
                    Jsonb(definition.model_dump(mode="json")),
                ),
            )
        stored = await self.get_index(definition.index_id)
        if stored is None or stored.model_dump(exclude={"created_at"}) != definition.model_dump(exclude={"created_at"}):
            raise IndexStoreError("index contract conflicts with an existing definition")
        return stored

    async def get_index(self, index_id: str) -> IndexDefinition | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute("SELECT document FROM scenara_indexes WHERE index_id = %s", (index_id,))
            row = await cursor.fetchone()
        return IndexDefinition.model_validate(row[0]) if row else None

    async def list_indexes(
        self, tenant_id: str, project_id: str, *, domain: str | None = None
    ) -> list[IndexDefinition]:
        del tenant_id, project_id
        query = "SELECT document FROM scenara_indexes"
        args: tuple[Any, ...] = ()
        if domain is not None:
            query += " WHERE domain = %s"
            args = (domain,)
        query += " ORDER BY index_id"
        async with self._pool.connection() as conn:
            cursor = await conn.execute(query, args)
            rows = await cursor.fetchall()
        return [IndexDefinition.model_validate(row[0]) for row in rows]

    async def upsert(self, record: IndexRecord) -> IndexRecord:
        upserted = await self.upsert_many([record])
        return upserted[0]

    async def upsert_many(self, records: list[IndexRecord]) -> list[IndexRecord]:
        from psycopg.types.json import Jsonb

        definitions: dict[str, IndexDefinition] = {}
        for record in records:
            definition = definitions.get(record.index_id)
            if definition is None:
                fetched = await self.get_index(record.index_id)
                if fetched is None:
                    raise IndexStoreError("index definition does not exist")
                definitions[record.index_id] = fetched
                definition = fetched
            if record.domain != definition.domain or record.kind != definition.record_kind:
                raise IndexStoreError("index record does not match its contract")
            if definition.vector_dimension is not None and record.vector is not None:
                _validate_vector(definition, record.vector)
            if definition.record_kind.value == "vector" and record.vector is None and record.feature_id is None:
                raise IndexStoreError("vector index records require a vector or feature reference")
            if definition.record_kind.value == "text" and not (record.text or "").strip():
                raise IndexStoreError("text index records require text")
        if not records:
            return []
        async with self._pool.connection() as conn, conn.transaction():
            for record in records:
                await conn.execute(
                    """INSERT INTO scenara_index_records
                    (tenant_id, project_id, record_id, index_id, domain, kind,
                     source_type, source_id, asset_id, run_id, unit_id, object_id,
                     artifact_id, page_number, pts_ms, feature_id, text, vector,
                     metadata, status, created_at, expires_at, deleted_at, document)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), to_timestamp(%s), %s)
                    ON CONFLICT (tenant_id, project_id, record_id) DO UPDATE SET
                      index_id = EXCLUDED.index_id, domain = EXCLUDED.domain, kind = EXCLUDED.kind,
                      source_type = EXCLUDED.source_type, source_id = EXCLUDED.source_id,
                      asset_id = EXCLUDED.asset_id, run_id = EXCLUDED.run_id, unit_id = EXCLUDED.unit_id,
                      object_id = EXCLUDED.object_id, artifact_id = EXCLUDED.artifact_id,
                      page_number = EXCLUDED.page_number, pts_ms = EXCLUDED.pts_ms,
                      feature_id = EXCLUDED.feature_id, text = EXCLUDED.text, vector = EXCLUDED.vector,
                      metadata = EXCLUDED.metadata, status = EXCLUDED.status, created_at = EXCLUDED.created_at,
                      expires_at = EXCLUDED.expires_at, deleted_at = EXCLUDED.deleted_at,
                      document = EXCLUDED.document""",
                    (
                        record.tenant_id, record.project_id, record.record_id, record.index_id, record.domain,
                        record.kind, record.source.source_type, record.source.source_id, record.source.asset_id,
                        record.source.run_id, record.source.unit_id, record.source.object_id, record.source.artifact_id,
                        record.source.page_number, record.source.pts_ms, record.feature_id, record.text,
                        Jsonb(record.vector) if record.vector is not None else None, Jsonb(record.metadata), record.status,
                        record.created_at, record.expires_at, record.deleted_at, Jsonb(record.model_dump(mode="json")),
                    ),
                )
        return [record.model_copy(deep=True) for record in records]

    async def get(self, tenant_id: str, project_id: str, record_id: str) -> IndexRecord | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                "SELECT document FROM scenara_index_records "
                "WHERE tenant_id = %s AND project_id = %s AND record_id = %s",
                (tenant_id, project_id, record_id),
            )
            row = await cursor.fetchone()
        return IndexRecord.model_validate(row[0]) if row else None

    async def list_records(self, tenant_id: str, project_id: str, *, index_id: str | None = None,
                           source_type: str | None = None, source_id: str | None = None,
                           offset: int = 0, limit: int = 100) -> list[IndexRecord]:
        if offset < 0 or not 1 <= limit <= 1000:
            raise IndexStoreError("invalid index pagination")
        clauses = ["tenant_id = %s", "project_id = %s", "status <> 'deleted'"]
        args: list[Any] = [tenant_id, project_id]
        for column, value in (("index_id", index_id), ("source_type", source_type), ("source_id", source_id)):
            if value is not None:
                clauses.append(f"{column} = %s")
                args.append(value)
        args.extend([limit, offset])
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"SELECT document FROM scenara_index_records WHERE {' AND '.join(clauses)} "
                "ORDER BY created_at DESC, record_id DESC LIMIT %s OFFSET %s",
                tuple(args),
            )
            rows = await cursor.fetchall()
        return [IndexRecord.model_validate(row[0]) for row in rows]

    async def query_vector(self, tenant_id: str, project_id: str, index_id: str, vector: list[float], *,
                           limit: int = 20, threshold: float | None = None) -> list[IndexHit]:
        definition = await self.get_index(index_id)
        if definition is None:
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
        memory = MemoryIndexStore()
        await memory.create_index(definition)
        for row in rows:
            await memory.upsert(row)
        return await memory.query_vector(tenant_id, project_id, index_id, vector, limit=limit, threshold=threshold)

    async def query_text(
        self, tenant_id: str, project_id: str, index_id: str, query: str, *, limit: int = 20
    ) -> list[IndexHit]:
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
        definition = await self.get_index(index_id)
        if definition is None:
            raise IndexStoreError("text index definition does not exist")
        memory = MemoryIndexStore()
        await memory.create_index(definition)
        for row in rows:
            await memory.upsert(row)
        return await memory.query_text(tenant_id, project_id, index_id, query, limit=limit)

    async def delete_source(self, tenant_id: str, project_id: str, source_type: str, source_id: str) -> int:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """UPDATE scenara_index_records
                   SET status = 'deleted', deleted_at = now(),
                       document = document || jsonb_build_object(
                           'status', 'deleted', 'deleted_at', extract(epoch from now()))
                   WHERE tenant_id = %s AND project_id = %s AND source_type = %s AND source_id = %s
                   AND status <> 'deleted'""",
                (tenant_id, project_id, source_type, source_id),
            )
        return int(cursor.rowcount)

    async def delete_asset(self, tenant_id: str, project_id: str, asset_id: str) -> int:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """UPDATE scenara_index_records
                   SET status = 'deleted', deleted_at = now(),
                       document = document || jsonb_build_object(
                           'status', 'deleted', 'deleted_at', extract(epoch from now()))
                   WHERE tenant_id = %s AND project_id = %s AND asset_id = %s
                   AND status <> 'deleted'""",
                (tenant_id, project_id, asset_id),
            )
        return int(cursor.rowcount)

    async def delete_expired(self, before: float, limit: int = 10_000) -> int:
        if not 1 <= limit <= 10_000:
            raise IndexStoreError("index retention limit must be between 1 and 10000")
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """WITH stale AS (
                     SELECT tenant_id, project_id, record_id FROM scenara_index_records
                     WHERE expires_at IS NOT NULL AND expires_at <= to_timestamp(%s)
                       AND status <> 'deleted' ORDER BY expires_at, record_id LIMIT %s
                   )
                   UPDATE scenara_index_records target
                   SET status = 'deleted', deleted_at = to_timestamp(%s),
                       document = document || jsonb_build_object(
                           'status', 'deleted', 'deleted_at', %s)
                   FROM stale WHERE target.tenant_id = stale.tenant_id
                     AND target.project_id = stale.project_id AND target.record_id = stale.record_id""",
                (before, limit, before, before),
            )
        return int(cursor.rowcount)

    async def rebuild(self, tenant_id: str, project_id: str, index_id: str) -> tuple[int, int]:
        """Run a consistency pass over records for the current scan backend.

        The PostgreSQL adapter currently evaluates queries through the shared
        contract, so no secondary ANN structure needs rebuilding.  The method
        still validates that the index exists and reports durable work counts;
        a pgvector/remote backend can replace this implementation without an
        API change.
        """
        if await self.get_index(index_id) is None:
            raise IndexStoreError("index definition does not exist")
        offset = 0
        seen = 0
        while True:
            page = await self.list_records(tenant_id, project_id, index_id=index_id, offset=offset, limit=1000)
            seen += len(page)
            if len(page) < 1000:
                break
            offset += len(page)
        return seen, seen


__all__ = ["PostgresIndexStore"]
