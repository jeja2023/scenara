from __future__ import annotations

from typing import Any

from scenara.platform.control_plane import ControlPlaneStore


class PostgresControlPlaneStore(ControlPlaneStore):
    """Document store for control-plane records.

    Keeping product-specific fields in a JSONB document lets the modular
    monolith add governed resources without adding a new persistence adapter
    for every product.  The indexed identity columns still enforce tenant and
    project isolation and deterministic replacement.
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def get(self, kind: str, tenant_id: str, project_id: str, record_id: str) -> dict[str, Any] | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_control_plane_records
                   WHERE record_type = %s AND tenant_id = %s AND project_id = %s AND record_id = %s""",
                (kind, tenant_id, project_id, record_id),
            )
            row = await cursor.fetchone()
        return dict(row[0]) if row else None

    async def list(self, kind: str, tenant_id: str, project_id: str) -> list[dict[str, Any]]:
        clauses = ["record_type = %s"]
        params_list: list[object] = [kind]
        if tenant_id != "*":
            clauses.append("tenant_id = %s")
            params_list.append(tenant_id)
        if project_id != "*":
            clauses.append("project_id = %s")
            params_list.append(project_id)
        where_sql = " AND ".join(clauses)
        params = tuple(params_list)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"""SELECT document FROM scenara_control_plane_records
                   WHERE {where_sql}
                   ORDER BY updated_at DESC, record_id DESC""",
                params,
            )
            rows = await cursor.fetchall()
        return [dict(row[0]) for row in rows]

    async def put(self, kind: str, tenant_id: str, project_id: str, record_id: str, document: dict[str, Any]) -> None:
        from psycopg.types.json import Jsonb

        now = float(document.get("updated_at", document.get("created_at", 0)))
        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                """INSERT INTO scenara_control_plane_records
                   (record_type, tenant_id, project_id, record_id, created_at, updated_at, document)
                   VALUES (%s, %s, %s, %s, to_timestamp(%s::double precision),
                           to_timestamp(%s::double precision), %s)
                   ON CONFLICT (record_type, tenant_id, project_id, record_id)
                   DO UPDATE SET updated_at = EXCLUDED.updated_at, document = EXCLUDED.document""",
                (kind, tenant_id, project_id, record_id, float(document.get("created_at", now)), now, Jsonb(document)),
            )

    async def delete(self, kind: str, tenant_id: str, project_id: str, record_id: str) -> None:
        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                """DELETE FROM scenara_control_plane_records
                   WHERE record_type = %s AND tenant_id = %s AND project_id = %s AND record_id = %s""",
                (kind, tenant_id, project_id, record_id),
            )


__all__ = ["PostgresControlPlaneStore"]
