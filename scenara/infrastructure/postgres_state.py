from __future__ import annotations

from typing import Any

from scenara.platform.models import MediaAsset, MediaSource, ResultReference, RunEvent, RunRecord
from scenara.platform.store import StateConflict


class PostgresStateStore:
    """PostgreSQL adapter. Documents retain contract fidelity; columns support operational queries."""

    def __init__(self, dsn: str) -> None:
        try:
            from psycopg_pool import AsyncConnectionPool
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("psycopg-pool is required for the PostgreSQL state backend") from exc
        self._pool: Any = AsyncConnectionPool(dsn, open=False, min_size=1, max_size=10)

    async def open(self) -> None:
        await self._pool.open()

    async def close(self) -> None:
        await self._pool.close()

    async def create_asset(self, asset: MediaAsset) -> MediaAsset:
        await self._insert_document("scenara_media_assets", "asset_id", asset.asset_id, asset)
        return asset.model_copy(deep=True)

    async def get_asset(self, tenant_id: str, project_id: str, asset_id: str) -> MediaAsset | None:
        row = await self._get_document("scenara_media_assets", "asset_id", tenant_id, project_id, asset_id)
        return MediaAsset.model_validate(row) if row else None

    async def list_assets(self, tenant_id: str, project_id: str) -> list[MediaAsset]:
        rows = await self._list_documents("scenara_media_assets", "asset_id", tenant_id, project_id)
        return [MediaAsset.model_validate(row) for row in rows]

    async def create_source(self, source: MediaSource) -> MediaSource:
        await self._insert_document("scenara_media_sources", "source_id", source.source_id, source)
        return source.model_copy(deep=True)

    async def get_source(self, tenant_id: str, project_id: str, source_id: str) -> MediaSource | None:
        row = await self._get_document("scenara_media_sources", "source_id", tenant_id, project_id, source_id)
        return MediaSource.model_validate(row) if row else None

    async def list_sources(self, tenant_id: str, project_id: str) -> list[MediaSource]:
        rows = await self._list_documents("scenara_media_sources", "source_id", tenant_id, project_id)
        return [MediaSource.model_validate(row) for row in rows]

    async def create_run_idempotent(
        self,
        run: RunRecord,
        *,
        idempotency_key: str,
        request_hash: str,
    ) -> tuple[RunRecord, bool]:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """SELECT request_hash, run_id FROM scenara_idempotency_keys
                   WHERE tenant_id = %s AND project_id = %s AND idempotency_key = %s FOR UPDATE""",
                (run.tenant_id, run.project_id, idempotency_key),
            )
            existing = await cursor.fetchone()
            if existing is not None:
                if existing[0] != request_hash:
                    raise StateConflict("idempotency key was already used for a different request")
                cursor = await conn.execute(
                    """SELECT document FROM scenara_runs
                       WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
                    (run.tenant_id, run.project_id, existing[1]),
                )
                stored = await cursor.fetchone()
                if stored is None:
                    raise StateConflict("idempotent run is missing")
                return RunRecord.model_validate(stored[0]), False
            try:
                await conn.execute(
                    """INSERT INTO scenara_runs
                       (tenant_id, project_id, run_id, domain, status, revision, priority, created_at, updated_at, document)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s)""",
                    (
                        run.tenant_id,
                        run.project_id,
                        run.run_id,
                        run.domain,
                        run.status,
                        run.revision,
                        run.priority,
                        run.created_at,
                        run.updated_at,
                        Jsonb(run.model_dump(mode="json")),
                    ),
                )
                await conn.execute(
                    """INSERT INTO scenara_idempotency_keys
                       (tenant_id, project_id, idempotency_key, request_hash, run_id, created_at)
                       VALUES (%s, %s, %s, %s, %s, now())""",
                    (run.tenant_id, run.project_id, idempotency_key, request_hash, run.run_id),
                )
            except Exception as exc:
                if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                    raise StateConflict("run already exists") from exc
                raise
            return run.model_copy(deep=True), True

    async def get_run(self, tenant_id: str, project_id: str, run_id: str) -> RunRecord | None:
        row = await self._get_document("scenara_runs", "run_id", tenant_id, project_id, run_id)
        return RunRecord.model_validate(row) if row else None

    async def list_runs(self, tenant_id: str, project_id: str) -> list[RunRecord]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_runs
                   WHERE tenant_id = %s AND project_id = %s
                   ORDER BY created_at DESC, run_id DESC""",
                (tenant_id, project_id),
            )
            rows = await cursor.fetchall()
        return [RunRecord.model_validate(row[0]) for row in rows]

    async def save_run(self, run: RunRecord, *, expected_revision: int) -> RunRecord:
        from psycopg.types.json import Jsonb

        saved = run.model_copy(update={"revision": expected_revision + 1}, deep=True)
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """UPDATE scenara_runs
                   SET status = %s, revision = %s, updated_at = to_timestamp(%s), document = %s
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s AND revision = %s""",
                (
                    saved.status,
                    saved.revision,
                    saved.updated_at,
                    Jsonb(saved.model_dump(mode="json")),
                    saved.tenant_id,
                    saved.project_id,
                    saved.run_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise StateConflict("run revision conflict")
        return saved

    async def append_event(self, tenant_id: str, project_id: str, event: RunEvent) -> RunEvent:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                """SELECT revision FROM scenara_runs
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s FOR UPDATE""",
                (tenant_id, project_id, event.run_id),
            )
            cursor = await conn.execute(
                """SELECT COALESCE(MAX(event_id), 0) + 1 FROM scenara_run_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
                (tenant_id, project_id, event.run_id),
            )
            next_id = int((await cursor.fetchone())[0])
            stored = event.model_copy(update={"event_id": next_id}, deep=True)
            await conn.execute(
                """INSERT INTO scenara_run_events
                   (tenant_id, project_id, run_id, event_id, event_type, status, created_at, payload, document)
                   VALUES (%s, %s, %s, %s, %s, %s, to_timestamp(%s), %s, %s)""",
                (
                    tenant_id,
                    project_id,
                    stored.run_id,
                    stored.event_id,
                    stored.event_type,
                    stored.status,
                    stored.created_at,
                    Jsonb(stored.payload),
                    Jsonb(stored.model_dump(mode="json")),
                ),
            )
        return stored

    async def events_after(self, tenant_id: str, project_id: str, run_id: str, event_id: int) -> list[RunEvent]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_run_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s AND event_id > %s
                   ORDER BY event_id ASC""",
                (tenant_id, project_id, run_id, event_id),
            )
            rows = await cursor.fetchall()
        return [RunEvent.model_validate(row[0]) for row in rows]

    async def save_result_reference(self, tenant_id: str, project_id: str, result: ResultReference) -> None:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                """INSERT INTO scenara_run_results
                   (tenant_id, project_id, run_id, domain, schema_version, object_key, sha256, unit_count, created_at, summary)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), %s)
                   ON CONFLICT (tenant_id, project_id, run_id) DO UPDATE SET
                     domain = EXCLUDED.domain, schema_version = EXCLUDED.schema_version,
                     object_key = EXCLUDED.object_key, sha256 = EXCLUDED.sha256,
                     unit_count = EXCLUDED.unit_count, created_at = EXCLUDED.created_at, summary = EXCLUDED.summary""",
                (
                    tenant_id,
                    project_id,
                    result.run_id,
                    result.domain,
                    result.schema_version,
                    result.object_key,
                    result.sha256,
                    result.unit_count,
                    result.created_at,
                    Jsonb(result.model_dump(mode="json")),
                ),
            )

    async def get_result_reference(self, tenant_id: str, project_id: str, run_id: str) -> ResultReference | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT summary FROM scenara_run_results
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
                (tenant_id, project_id, run_id),
            )
            row = await cursor.fetchone()
        return ResultReference.model_validate(row[0]) if row else None

    async def _insert_document(self, table: str, id_column: str, value_id: str, model: Any) -> None:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            try:
                await conn.execute(
                    f"""INSERT INTO {table} (tenant_id, project_id, {id_column}, created_at, document)
                        VALUES (%s, %s, %s, to_timestamp(%s), %s)""",
                    (model.tenant_id, model.project_id, value_id, model.created_at, Jsonb(model.model_dump(mode="json"))),
                )
            except Exception as exc:
                if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                    raise StateConflict("record already exists") from exc
                raise

    async def _get_document(
        self,
        table: str,
        id_column: str,
        tenant_id: str,
        project_id: str,
        value_id: str,
    ) -> dict[str, Any] | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"""SELECT document FROM {table}
                    WHERE tenant_id = %s AND project_id = %s AND {id_column} = %s""",
                (tenant_id, project_id, value_id),
            )
            row = await cursor.fetchone()
        return row[0] if row else None

    async def _list_documents(
        self,
        table: str,
        id_column: str,
        tenant_id: str,
        project_id: str,
    ) -> list[dict[str, Any]]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"""SELECT document FROM {table}
                    WHERE tenant_id = %s AND project_id = %s ORDER BY created_at DESC, {id_column} DESC""",
                (tenant_id, project_id),
            )
            rows = await cursor.fetchall()
        return [row[0] for row in rows]


__all__ = ["PostgresStateStore"]
