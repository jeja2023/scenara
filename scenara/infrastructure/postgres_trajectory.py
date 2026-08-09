from __future__ import annotations

from typing import Any

from scenara.domains.portrait.trajectory import (
    CameraRecord,
    CameraTransition,
    LongTermIdentity,
    TrajectorySegment,
)


def _window_clauses(
    clauses: list[str], params: list[object], since: float | None, until: float | None
) -> None:
    """时间窗按片段区间求交：last_seen >= since 且 first_seen <= until。"""

    if since is not None:
        clauses.append("last_seen_at >= to_timestamp(%s)")
        params.append(since)
    if until is not None:
        clauses.append("first_seen_at <= to_timestamp(%s)")
        params.append(until)


class PostgresTrajectoryRepository:
    """长期轨迹的 PostgreSQL 仓储。

    身份与片段各自独立成表，把租户、项目、状态、摄像头和时间提升为索引列，
    使时间窗和摄像头维度的查询可以下推到数据库，避免全表扫描后在应用层过滤。
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def put_identity(self, identity: LongTermIdentity) -> None:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                """INSERT INTO scenara_trajectory_identities
                   (tenant_id, project_id, identity_id, status, first_seen_at, last_seen_at,
                    created_at, updated_at, document)
                   VALUES (%s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s),
                           to_timestamp(%s), to_timestamp(%s), %s)
                   ON CONFLICT (tenant_id, project_id, identity_id)
                   DO UPDATE SET status = EXCLUDED.status,
                                 first_seen_at = EXCLUDED.first_seen_at,
                                 last_seen_at = EXCLUDED.last_seen_at,
                                 updated_at = EXCLUDED.updated_at,
                                 document = EXCLUDED.document""",
                (
                    identity.tenant_id,
                    identity.project_id,
                    identity.identity_id,
                    identity.status,
                    identity.first_seen_at,
                    identity.last_seen_at,
                    identity.created_at,
                    identity.updated_at,
                    Jsonb(identity.model_dump(mode="json")),
                ),
            )

    async def get_identity(self, tenant_id: str, project_id: str, identity_id: str) -> LongTermIdentity | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_trajectory_identities
                   WHERE tenant_id = %s AND project_id = %s AND identity_id = %s""",
                (tenant_id, project_id, identity_id),
            )
            row = await cursor.fetchone()
        return LongTermIdentity.model_validate(row[0]) if row else None

    async def list_identities(
        self,
        tenant_id: str,
        project_id: str,
        *,
        status: str | None = None,
        camera_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[LongTermIdentity], int]:
        clauses = ["tenant_id = %s", "project_id = %s"]
        params: list[object] = [tenant_id, project_id]
        if status is not None:
            clauses.append("status = %s")
            params.append(status)
        if camera_id is not None:
            clauses.append("document->'camera_ids' ? %s")
            params.append(camera_id)
        _window_clauses(clauses, params, since, until)
        where_sql = " AND ".join(clauses)
        async with self._pool.connection() as conn:
            total_cursor = await conn.execute(
                f"SELECT count(*) FROM scenara_trajectory_identities WHERE {where_sql}",
                tuple(params),
            )
            total_row = await total_cursor.fetchone()
            cursor = await conn.execute(
                f"""SELECT document FROM scenara_trajectory_identities WHERE {where_sql}
                    ORDER BY last_seen_at DESC, identity_id DESC OFFSET %s LIMIT %s""",
                (*params, offset, limit),
            )
            rows = await cursor.fetchall()
        return [LongTermIdentity.model_validate(row[0]) for row in rows], int(total_row[0] if total_row else 0)

    async def delete_identity(self, tenant_id: str, project_id: str, identity_id: str) -> bool:
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """DELETE FROM scenara_trajectory_identities
                   WHERE tenant_id = %s AND project_id = %s AND identity_id = %s""",
                (tenant_id, project_id, identity_id),
            )
        return int(cursor.rowcount) == 1

    async def put_segment(self, segment: TrajectorySegment) -> None:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                """INSERT INTO scenara_trajectory_segments
                   (tenant_id, project_id, segment_id, identity_id, camera_id, run_id,
                    first_seen_at, last_seen_at, created_at, document)
                   VALUES (%s, %s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s),
                           to_timestamp(%s), %s)
                   ON CONFLICT (tenant_id, project_id, segment_id)
                   DO UPDATE SET identity_id = EXCLUDED.identity_id,
                                 camera_id = EXCLUDED.camera_id,
                                 run_id = EXCLUDED.run_id,
                                 first_seen_at = EXCLUDED.first_seen_at,
                                 last_seen_at = EXCLUDED.last_seen_at,
                                 document = EXCLUDED.document""",
                (
                    segment.tenant_id,
                    segment.project_id,
                    segment.segment_id,
                    segment.identity_id,
                    segment.camera_id,
                    segment.run_id,
                    segment.first_seen_at,
                    segment.last_seen_at,
                    segment.created_at,
                    Jsonb(segment.model_dump(mode="json")),
                ),
            )

    async def get_segment(self, tenant_id: str, project_id: str, segment_id: str) -> TrajectorySegment | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_trajectory_segments
                   WHERE tenant_id = %s AND project_id = %s AND segment_id = %s""",
                (tenant_id, project_id, segment_id),
            )
            row = await cursor.fetchone()
        return TrajectorySegment.model_validate(row[0]) if row else None

    async def list_segments(
        self,
        tenant_id: str,
        project_id: str,
        *,
        identity_id: str | None = None,
        camera_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[TrajectorySegment], int]:
        clauses = ["tenant_id = %s", "project_id = %s"]
        params: list[object] = [tenant_id, project_id]
        if identity_id is not None:
            clauses.append("identity_id = %s")
            params.append(identity_id)
        if camera_id is not None:
            clauses.append("camera_id = %s")
            params.append(camera_id)
        _window_clauses(clauses, params, since, until)
        where_sql = " AND ".join(clauses)
        async with self._pool.connection() as conn:
            total_cursor = await conn.execute(
                f"SELECT count(*) FROM scenara_trajectory_segments WHERE {where_sql}",
                tuple(params),
            )
            total_row = await total_cursor.fetchone()
            cursor = await conn.execute(
                f"""SELECT document FROM scenara_trajectory_segments WHERE {where_sql}
                    ORDER BY first_seen_at ASC, segment_id ASC OFFSET %s LIMIT %s""",
                (*params, offset, limit),
            )
            rows = await cursor.fetchall()
        return [TrajectorySegment.model_validate(row[0]) for row in rows], int(total_row[0] if total_row else 0)

    async def delete_segments_for_identity(self, tenant_id: str, project_id: str, identity_id: str) -> int:
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """DELETE FROM scenara_trajectory_segments
                   WHERE tenant_id = %s AND project_id = %s AND identity_id = %s""",
                (tenant_id, project_id, identity_id),
            )
        return int(cursor.rowcount)

    async def put_camera(self, camera: CameraRecord) -> None:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                """INSERT INTO scenara_trajectory_cameras
                   (tenant_id, project_id, camera_id, created_at, updated_at, document)
                   VALUES (%s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s)
                   ON CONFLICT (tenant_id, project_id, camera_id)
                   DO UPDATE SET updated_at = EXCLUDED.updated_at, document = EXCLUDED.document""",
                (
                    camera.tenant_id,
                    camera.project_id,
                    camera.camera_id,
                    camera.created_at,
                    camera.updated_at,
                    Jsonb(camera.model_dump(mode="json")),
                ),
            )

    async def get_camera(self, tenant_id: str, project_id: str, camera_id: str) -> CameraRecord | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_trajectory_cameras
                   WHERE tenant_id = %s AND project_id = %s AND camera_id = %s""",
                (tenant_id, project_id, camera_id),
            )
            row = await cursor.fetchone()
        return CameraRecord.model_validate(row[0]) if row else None

    async def list_cameras(self, tenant_id: str, project_id: str) -> list[CameraRecord]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_trajectory_cameras
                   WHERE tenant_id = %s AND project_id = %s ORDER BY camera_id ASC""",
                (tenant_id, project_id),
            )
            rows = await cursor.fetchall()
        return [CameraRecord.model_validate(row[0]) for row in rows]

    async def delete_camera(self, tenant_id: str, project_id: str, camera_id: str) -> bool:
        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                """DELETE FROM scenara_trajectory_camera_transitions
                   WHERE tenant_id = %s AND project_id = %s
                     AND (from_camera_id = %s OR to_camera_id = %s)""",
                (tenant_id, project_id, camera_id, camera_id),
            )
            cursor = await conn.execute(
                """DELETE FROM scenara_trajectory_cameras
                   WHERE tenant_id = %s AND project_id = %s AND camera_id = %s""",
                (tenant_id, project_id, camera_id),
            )
        return int(cursor.rowcount) == 1

    async def replace_transitions(
        self, tenant_id: str, project_id: str, from_camera_id: str, transitions: list[CameraTransition]
    ) -> None:
        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                """DELETE FROM scenara_trajectory_camera_transitions
                   WHERE tenant_id = %s AND project_id = %s AND from_camera_id = %s""",
                (tenant_id, project_id, from_camera_id),
            )
            for transition in transitions:
                await conn.execute(
                    """INSERT INTO scenara_trajectory_camera_transitions
                       (tenant_id, project_id, from_camera_id, to_camera_id, min_seconds, max_seconds)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (
                        tenant_id,
                        project_id,
                        transition.from_camera_id,
                        transition.to_camera_id,
                        transition.min_seconds,
                        transition.max_seconds,
                    ),
                )

    async def list_transitions(
        self, tenant_id: str, project_id: str, *, from_camera_id: str | None = None
    ) -> list[CameraTransition]:
        clauses = ["tenant_id = %s", "project_id = %s"]
        params: list[object] = [tenant_id, project_id]
        if from_camera_id is not None:
            clauses.append("from_camera_id = %s")
            params.append(from_camera_id)
        where_sql = " AND ".join(clauses)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"""SELECT from_camera_id, to_camera_id, min_seconds, max_seconds
                    FROM scenara_trajectory_camera_transitions WHERE {where_sql}
                    ORDER BY from_camera_id ASC, to_camera_id ASC""",
                tuple(params),
            )
            rows = await cursor.fetchall()
        return [
            CameraTransition(
                from_camera_id=row[0],
                to_camera_id=row[1],
                min_seconds=float(row[2]),
                max_seconds=None if row[3] is None else float(row[3]),
            )
            for row in rows
        ]


__all__ = ["PostgresTrajectoryRepository"]
