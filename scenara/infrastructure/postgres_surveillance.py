"""PostgreSQL persistence for surveillance control-plane records and alerts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from scenara.platform.models import WebhookDeliveryRecord
from scenara.platform.surveillance import (
    AlertCandidate,
    AlertEvent,
    AlertRecord,
    AlertStatus,
    AlertWriteResult,
    DebounceState,
    SurveillanceConflict,
    SurveillanceRepository,
    SurveillanceTask,
    Watchlist,
    WatchlistMember,
)


def _utc_rfc3339(value: float) -> str:
    return datetime.fromtimestamp(value, UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class PostgresSurveillanceRepository(SurveillanceRepository):
    """Repository whose alert/outbox write is a single database transaction."""

    atomic_webhook_outbox = True

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @staticmethod
    async def _replace_bindings(conn: Any, task: SurveillanceTask) -> None:
        from psycopg.types.json import Jsonb

        await conn.execute(
            "DELETE FROM scenara_surveillance_task_bindings WHERE tenant_id = %s AND project_id = %s AND task_id = %s",
            (task.tenant_id, task.project_id, task.task_id),
        )
        for binding in task.bindings:
            await conn.execute(
                """INSERT INTO scenara_surveillance_task_bindings
                   (tenant_id, project_id, binding_id, task_id, source_id, camera_id, active_run_id, stream_session_id, document)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    task.tenant_id,
                    task.project_id,
                    binding.binding_id,
                    task.task_id,
                    binding.source_id,
                    binding.camera_id,
                    binding.active_run_id,
                    binding.stream_session_id,
                    Jsonb(binding.model_dump(mode="json")),
                ),
            )

    async def create_watchlist(self, watchlist: Watchlist) -> Watchlist:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            try:
                await conn.execute(
                    """INSERT INTO scenara_surveillance_watchlists
                       (tenant_id, project_id, watchlist_id, status, created_at, updated_at, revision, document)
                       VALUES (%s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s, %s)""",
                    (
                        watchlist.tenant_id,
                        watchlist.project_id,
                        watchlist.watchlist_id,
                        watchlist.status,
                        watchlist.created_at,
                        watchlist.updated_at,
                        watchlist.revision,
                        Jsonb(watchlist.model_dump(mode="json")),
                    ),
                )
            except Exception as exc:
                if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                    raise SurveillanceConflict("watchlist already exists") from exc
                raise
        return watchlist.model_copy(deep=True)

    async def get_watchlist(self, tenant_id: str, project_id: str, watchlist_id: str) -> Watchlist | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_surveillance_watchlists
                   WHERE tenant_id = %s AND project_id = %s AND watchlist_id = %s""",
                (tenant_id, project_id, watchlist_id),
            )
            row = await cursor.fetchone()
        return Watchlist.model_validate(row[0]) if row else None

    async def list_watchlists(self, tenant_id: str, project_id: str, *, offset: int, limit: int) -> tuple[list[Watchlist], int]:
        async with self._pool.connection() as conn:
            count_cursor = await conn.execute(
                "SELECT count(*) FROM scenara_surveillance_watchlists WHERE tenant_id = %s AND project_id = %s",
                (tenant_id, project_id),
            )
            count_row = await count_cursor.fetchone()
            cursor = await conn.execute(
                """SELECT document FROM scenara_surveillance_watchlists
                   WHERE tenant_id = %s AND project_id = %s
                   ORDER BY updated_at DESC, watchlist_id ASC OFFSET %s LIMIT %s""",
                (tenant_id, project_id, offset, limit),
            )
            rows = await cursor.fetchall()
        return [Watchlist.model_validate(row[0]) for row in rows], int(count_row[0] if count_row else 0)

    async def save_watchlist(self, watchlist: Watchlist, *, expected_revision: int) -> Watchlist:
        from psycopg.types.json import Jsonb

        stored = watchlist.model_copy(update={"revision": expected_revision + 1}, deep=True)
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """UPDATE scenara_surveillance_watchlists
                   SET status = %s, updated_at = to_timestamp(%s), revision = %s, document = %s
                   WHERE tenant_id = %s AND project_id = %s AND watchlist_id = %s AND revision = %s""",
                (
                    stored.status,
                    stored.updated_at,
                    stored.revision,
                    Jsonb(stored.model_dump(mode="json")),
                    stored.tenant_id,
                    stored.project_id,
                    stored.watchlist_id,
                    expected_revision,
                ),
            )
        if cursor.rowcount != 1:
            raise SurveillanceConflict("watchlist revision conflict")
        return stored

    async def delete_watchlist(self, tenant_id: str, project_id: str, watchlist_id: str) -> bool:
        async with self._pool.connection() as conn, conn.transaction():
            used = await conn.execute(
                """SELECT 1 FROM scenara_surveillance_tasks
                   WHERE tenant_id = %s AND project_id = %s AND document->'watchlist_ids' ? %s LIMIT 1""",
                (tenant_id, project_id, watchlist_id),
            )
            if await used.fetchone():
                raise SurveillanceConflict("watchlist is referenced by a surveillance task")
            cursor = await conn.execute(
                """DELETE FROM scenara_surveillance_watchlists
                   WHERE tenant_id = %s AND project_id = %s AND watchlist_id = %s""",
                (tenant_id, project_id, watchlist_id),
            )
        return int(cursor.rowcount) == 1

    async def create_member(self, member: WatchlistMember) -> WatchlistMember:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            try:
                await conn.execute(
                    """INSERT INTO scenara_surveillance_watchlist_members
                       (tenant_id, project_id, member_id, watchlist_id, portrait_identity_id, status,
                        valid_from, valid_until, created_at, updated_at, revision, document)
                       VALUES (%s, %s, %s, %s, %s, %s, to_timestamp(%s::double precision),
                               to_timestamp(%s::double precision), to_timestamp(%s), to_timestamp(%s), %s, %s)""",
                    (
                        member.tenant_id,
                        member.project_id,
                        member.member_id,
                        member.watchlist_id,
                        member.portrait_identity_id,
                        member.status,
                        member.valid_from,
                        member.valid_until,
                        member.created_at,
                        member.updated_at,
                        member.revision,
                        Jsonb(member.model_dump(mode="json")),
                    ),
                )
            except Exception as exc:
                if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                    raise SurveillanceConflict("portrait identity is already a member of this watchlist") from exc
                raise
        return member.model_copy(deep=True)

    async def get_member(self, tenant_id: str, project_id: str, member_id: str) -> WatchlistMember | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_surveillance_watchlist_members
                   WHERE tenant_id = %s AND project_id = %s AND member_id = %s""",
                (tenant_id, project_id, member_id),
            )
            row = await cursor.fetchone()
        return WatchlistMember.model_validate(row[0]) if row else None

    async def list_members(
        self, tenant_id: str, project_id: str, watchlist_id: str, *, offset: int, limit: int
    ) -> tuple[list[WatchlistMember], int]:
        async with self._pool.connection() as conn:
            count_cursor = await conn.execute(
                """SELECT count(*) FROM scenara_surveillance_watchlist_members
                   WHERE tenant_id = %s AND project_id = %s AND watchlist_id = %s""",
                (tenant_id, project_id, watchlist_id),
            )
            count_row = await count_cursor.fetchone()
            cursor = await conn.execute(
                """SELECT document FROM scenara_surveillance_watchlist_members
                   WHERE tenant_id = %s AND project_id = %s AND watchlist_id = %s
                   ORDER BY updated_at DESC, member_id ASC OFFSET %s LIMIT %s""",
                (tenant_id, project_id, watchlist_id, offset, limit),
            )
            rows = await cursor.fetchall()
        return [WatchlistMember.model_validate(row[0]) for row in rows], int(count_row[0] if count_row else 0)

    async def list_active_members(
        self, tenant_id: str, project_id: str, watchlist_ids: list[str], *, at: float
    ) -> list[WatchlistMember]:
        if not watchlist_ids:
            return []
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_surveillance_watchlist_members
                   WHERE tenant_id = %s AND project_id = %s AND watchlist_id = ANY(%s)
                     AND status = 'active'
                     AND (valid_from IS NULL OR valid_from <= to_timestamp(%s))
                     AND (valid_until IS NULL OR valid_until > to_timestamp(%s))
                   ORDER BY watchlist_id, member_id""",
                (tenant_id, project_id, watchlist_ids, at, at),
            )
            rows = await cursor.fetchall()
        return [WatchlistMember.model_validate(row[0]) for row in rows]

    async def save_member(self, member: WatchlistMember, *, expected_revision: int) -> WatchlistMember:
        from psycopg.types.json import Jsonb

        stored = member.model_copy(update={"revision": expected_revision + 1}, deep=True)
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """UPDATE scenara_surveillance_watchlist_members
                   SET status = %s, valid_from = to_timestamp(%s::double precision),
                       valid_until = to_timestamp(%s::double precision), updated_at = to_timestamp(%s),
                       revision = %s, document = %s
                   WHERE tenant_id = %s AND project_id = %s AND member_id = %s AND revision = %s""",
                (
                    stored.status,
                    stored.valid_from,
                    stored.valid_until,
                    stored.updated_at,
                    stored.revision,
                    Jsonb(stored.model_dump(mode="json")),
                    stored.tenant_id,
                    stored.project_id,
                    stored.member_id,
                    expected_revision,
                ),
            )
        if cursor.rowcount != 1:
            raise SurveillanceConflict("watchlist member revision conflict")
        return stored

    async def delete_member(self, tenant_id: str, project_id: str, member_id: str) -> bool:
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """DELETE FROM scenara_surveillance_watchlist_members
                   WHERE tenant_id = %s AND project_id = %s AND member_id = %s""",
                (tenant_id, project_id, member_id),
            )
        return int(cursor.rowcount) == 1

    async def create_task(self, task: SurveillanceTask) -> SurveillanceTask:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            try:
                await conn.execute(
                    """INSERT INTO scenara_surveillance_tasks
                       (tenant_id, project_id, task_id, status, created_at, updated_at, revision, document)
                       VALUES (%s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s, %s)""",
                    (
                        task.tenant_id,
                        task.project_id,
                        task.task_id,
                        task.status,
                        task.created_at,
                        task.updated_at,
                        task.revision,
                        Jsonb(task.model_dump(mode="json")),
                    ),
                )
                await self._replace_bindings(conn, task)
            except Exception as exc:
                if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                    raise SurveillanceConflict("surveillance task already exists") from exc
                raise
        return task.model_copy(deep=True)

    async def get_task(self, tenant_id: str, project_id: str, task_id: str) -> SurveillanceTask | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_surveillance_tasks
                   WHERE tenant_id = %s AND project_id = %s AND task_id = %s""",
                (tenant_id, project_id, task_id),
            )
            row = await cursor.fetchone()
        return SurveillanceTask.model_validate(row[0]) if row else None

    async def list_tasks(self, tenant_id: str, project_id: str, *, offset: int, limit: int) -> tuple[list[SurveillanceTask], int]:
        async with self._pool.connection() as conn:
            count_cursor = await conn.execute(
                "SELECT count(*) FROM scenara_surveillance_tasks WHERE tenant_id = %s AND project_id = %s",
                (tenant_id, project_id),
            )
            count_row = await count_cursor.fetchone()
            cursor = await conn.execute(
                """SELECT document FROM scenara_surveillance_tasks
                   WHERE tenant_id = %s AND project_id = %s
                   ORDER BY updated_at DESC, task_id ASC OFFSET %s LIMIT %s""",
                (tenant_id, project_id, offset, limit),
            )
            rows = await cursor.fetchall()
        return [SurveillanceTask.model_validate(row[0]) for row in rows], int(count_row[0] if count_row else 0)

    async def list_active_tasks_for_source(self, tenant_id: str, project_id: str, source_id: str) -> list[SurveillanceTask]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                # 半连接而不是 JOIN + DISTINCT：PostgreSQL 不允许 SELECT DISTINCT
                # 按未出现在选择列表里的列排序，EXISTS 同时省掉一次去重。
                """SELECT task.document FROM scenara_surveillance_tasks task
                   WHERE task.tenant_id = %s AND task.project_id = %s
                     AND task.status = 'active'
                     AND EXISTS (
                       SELECT 1 FROM scenara_surveillance_task_bindings binding
                       WHERE binding.tenant_id = task.tenant_id
                         AND binding.project_id = task.project_id
                         AND binding.task_id = task.task_id
                         AND binding.source_id = %s
                     )
                   ORDER BY task.task_id""",
                (tenant_id, project_id, source_id),
            )
            rows = await cursor.fetchall()
        return [SurveillanceTask.model_validate(row[0]) for row in rows]

    async def list_active_tasks(self, tenant_id: str, project_id: str) -> list[SurveillanceTask]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_surveillance_tasks
                   WHERE tenant_id = %s AND project_id = %s AND status = 'active'
                   ORDER BY task_id""",
                (tenant_id, project_id),
            )
            rows = await cursor.fetchall()
        return [SurveillanceTask.model_validate(row[0]) for row in rows]

    async def list_all_active_tasks(self) -> list[SurveillanceTask]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                "SELECT document FROM scenara_surveillance_tasks WHERE status = 'active' ORDER BY task_id"
            )
            rows = await cursor.fetchall()
        return [SurveillanceTask.model_validate(row[0]) for row in rows]

    async def save_task(self, task: SurveillanceTask, *, expected_revision: int) -> SurveillanceTask:
        from psycopg.types.json import Jsonb

        stored = task.model_copy(update={"revision": expected_revision + 1}, deep=True)
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """UPDATE scenara_surveillance_tasks
                   SET status = %s, updated_at = to_timestamp(%s), revision = %s, document = %s
                   WHERE tenant_id = %s AND project_id = %s AND task_id = %s AND revision = %s""",
                (
                    stored.status,
                    stored.updated_at,
                    stored.revision,
                    Jsonb(stored.model_dump(mode="json")),
                    stored.tenant_id,
                    stored.project_id,
                    stored.task_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount == 1:
                await self._replace_bindings(conn, stored)
        if cursor.rowcount != 1:
            raise SurveillanceConflict("surveillance task revision conflict")
        return stored

    async def _enqueue_outbox(self, conn: Any, event: AlertEvent) -> None:
        from psycopg.types.json import Jsonb

        cursor = await conn.execute(
            """SELECT endpoint_id FROM scenara_webhook_subscriptions
               WHERE tenant_id = %s AND project_id = %s AND enabled AND %s = ANY(event_types)""",
            (event.tenant_id, event.project_id, event.event_type),
        )
        for (endpoint_id,) in await cursor.fetchall():
            now = event.created_at
            delivery = WebhookDeliveryRecord(
                delivery_id=f"whd_{uuid4().hex}",
                tenant_id=event.tenant_id,
                project_id=event.project_id,
                endpoint_id=endpoint_id,
                event_id=event.event_id,
                event_type=event.event_type,
                payload=event.model_dump(mode="json"),
                next_attempt_at=now,
                created_at=now,
                updated_at=now,
            )
            await conn.execute(
                """INSERT INTO scenara_webhook_deliveries
                   (tenant_id, project_id, delivery_id, endpoint_id, event_id, event_type, status,
                    attempts, next_attempt_at, created_at, updated_at, document)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), to_timestamp(%s), %s)
                   ON CONFLICT (tenant_id, project_id, endpoint_id, event_id) DO NOTHING""",
                (
                    delivery.tenant_id,
                    delivery.project_id,
                    delivery.delivery_id,
                    delivery.endpoint_id,
                    delivery.event_id,
                    delivery.event_type,
                    delivery.status,
                    delivery.attempts,
                    delivery.next_attempt_at,
                    delivery.created_at,
                    delivery.updated_at,
                    Jsonb(delivery.model_dump(mode="json")),
                ),
            )

    async def _insert_event(self, conn: Any, event: AlertEvent) -> AlertEvent:
        from psycopg.types.json import Jsonb

        cursor = await conn.execute(
            """INSERT INTO scenara_surveillance_alert_events
               (event_id, tenant_id, project_id, alert_id, event_type, occurred_at, created_at, document)
               VALUES (%s, %s, %s, %s, %s, %s, to_timestamp(%s), %s)
               RETURNING event_cursor""",
            (
                event.event_id,
                event.tenant_id,
                event.project_id,
                event.alert_id,
                event.event_type,
                event.occurred_at,
                event.created_at,
                Jsonb(event.model_dump(mode="json")),
            ),
        )
        row = await cursor.fetchone()
        stored = event.model_copy(update={"event_cursor": int(row[0])}, deep=True)
        await conn.execute(
            "UPDATE scenara_surveillance_alert_events SET document = %s WHERE event_id = %s",
            (Jsonb(stored.model_dump(mode="json")), stored.event_id),
        )
        await self._enqueue_outbox(conn, stored)
        return stored

    async def record_alert(self, candidate: AlertCandidate) -> AlertWriteResult:
        from psycopg.types.json import Jsonb

        alert = candidate.alert
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """SELECT document FROM scenara_surveillance_debounce
                   WHERE tenant_id = %s AND project_id = %s AND debounce_key = %s FOR UPDATE""",
                (alert.tenant_id, alert.project_id, candidate.debounce.debounce_key),
            )
            row = await cursor.fetchone()
            if row is not None:
                current = DebounceState.model_validate(row[0])
                if current.cooldown_until > alert.triggered_at and current.last_alert_id:
                    alert_cursor = await conn.execute(
                        """SELECT document FROM scenara_surveillance_alerts
                           WHERE tenant_id = %s AND project_id = %s AND alert_id = %s FOR UPDATE""",
                        (alert.tenant_id, alert.project_id, current.last_alert_id),
                    )
                    alert_row = await alert_cursor.fetchone()
                    if alert_row is not None:
                        existing = AlertRecord.model_validate(alert_row[0])
                        stored = existing.model_copy(
                            update={
                                "last_seen_at": max(existing.last_seen_at, alert.last_seen_at),
                                "match_score": alert.match_score,
                                "max_score": max(existing.max_score, alert.max_score),
                                "occurrence_count": existing.occurrence_count + 1,
                                "updated_at": alert.updated_at,
                                "revision": existing.revision + 1,
                            }
                        )
                        await conn.execute(
                            """UPDATE scenara_surveillance_alerts
                               SET last_seen_at = to_timestamp(%s), match_score = %s, max_score = %s,
                                   occurrence_count = %s, updated_at = to_timestamp(%s), revision = %s, document = %s
                               WHERE tenant_id = %s AND project_id = %s AND alert_id = %s""",
                            (
                                stored.last_seen_at,
                                stored.match_score,
                                stored.max_score,
                                stored.occurrence_count,
                                stored.updated_at,
                                stored.revision,
                                Jsonb(stored.model_dump(mode="json")),
                                stored.tenant_id,
                                stored.project_id,
                                stored.alert_id,
                            ),
                        )
                        debounce = current.model_copy(
                            update={
                                "last_seen_at": max(current.last_seen_at, alert.last_seen_at),
                                "max_score": max(current.max_score, alert.max_score),
                                "occurrence_count": current.occurrence_count + 1,
                                "revision": current.revision + 1,
                            }
                        )
                        await conn.execute(
                            """UPDATE scenara_surveillance_debounce
                               SET last_seen_at = to_timestamp(%s), max_score = %s, occurrence_count = %s,
                                   revision = %s, document = %s
                               WHERE tenant_id = %s AND project_id = %s AND debounce_key = %s""",
                            (
                                debounce.last_seen_at,
                                debounce.max_score,
                                debounce.occurrence_count,
                                debounce.revision,
                                Jsonb(debounce.model_dump(mode="json")),
                                debounce.tenant_id,
                                debounce.project_id,
                                debounce.debounce_key,
                            ),
                        )
                        return AlertWriteResult(alert=stored, emitted=False)

            duplicate_cursor = await conn.execute(
                """SELECT document FROM scenara_surveillance_alerts
                   WHERE tenant_id = %s AND project_id = %s AND idempotency_key = %s""",
                (alert.tenant_id, alert.project_id, alert.idempotency_key),
            )
            duplicate = await duplicate_cursor.fetchone()
            if duplicate is not None:
                return AlertWriteResult(alert=AlertRecord.model_validate(duplicate[0]), emitted=False)
            await conn.execute(
                """INSERT INTO scenara_surveillance_alerts
                   (tenant_id, project_id, alert_id, task_id, binding_id, watchlist_id, member_id,
                    portrait_identity_id, camera_id, status, triggered_at, first_seen_at, last_seen_at,
                    match_score, max_score, occurrence_count, created_at, updated_at, revision, idempotency_key, document)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s),
                            to_timestamp(%s), %s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s, %s, %s)""",
                (
                    alert.tenant_id,
                    alert.project_id,
                    alert.alert_id,
                    alert.task_id,
                    alert.binding_id,
                    alert.watchlist_id,
                    alert.member_id,
                    alert.portrait_identity_id,
                    alert.camera_id,
                    alert.status,
                    alert.triggered_at,
                    alert.first_seen_at,
                    alert.last_seen_at,
                    alert.match_score,
                    alert.max_score,
                    alert.occurrence_count,
                    alert.created_at,
                    alert.updated_at,
                    alert.revision,
                    alert.idempotency_key,
                    Jsonb(alert.model_dump(mode="json")),
                ),
            )
            debounce = candidate.debounce.model_copy(update={"last_alert_id": alert.alert_id}, deep=True)
            await conn.execute(
                """INSERT INTO scenara_surveillance_debounce
                   (tenant_id, project_id, debounce_key, task_id, binding_id, watchlist_id,
                    portrait_identity_id, cooldown_until, last_seen_at, max_score, occurrence_count, revision, document)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s, %s, %s, %s)
                   ON CONFLICT (tenant_id, project_id, debounce_key)
                   DO UPDATE SET cooldown_until = EXCLUDED.cooldown_until, last_seen_at = EXCLUDED.last_seen_at,
                                  max_score = EXCLUDED.max_score, occurrence_count = EXCLUDED.occurrence_count,
                                  revision = EXCLUDED.revision, document = EXCLUDED.document""",
                (
                    debounce.tenant_id,
                    debounce.project_id,
                    debounce.debounce_key,
                    debounce.task_id,
                    debounce.binding_id,
                    debounce.watchlist_id,
                    debounce.portrait_identity_id,
                    debounce.cooldown_until,
                    debounce.last_seen_at,
                    debounce.max_score,
                    debounce.occurrence_count,
                    debounce.revision,
                    Jsonb(debounce.model_dump(mode="json")),
                ),
            )
            event = await self._insert_event(conn, candidate.event)
        return AlertWriteResult(alert=alert.model_copy(deep=True), event=event, emitted=True)

    async def get_alert(self, tenant_id: str, project_id: str, alert_id: str) -> AlertRecord | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_surveillance_alerts
                   WHERE tenant_id = %s AND project_id = %s AND alert_id = %s""",
                (tenant_id, project_id, alert_id),
            )
            row = await cursor.fetchone()
        return AlertRecord.model_validate(row[0]) if row else None

    async def list_alerts(
        self,
        tenant_id: str,
        project_id: str,
        *,
        status: AlertStatus | None,
        task_id: str | None,
        camera_id: str | None,
        watchlist_id: str | None,
        portrait_identity_id: str | None,
        since: float | None,
        until: float | None,
        offset: int,
        limit: int,
    ) -> tuple[list[AlertRecord], int]:
        clauses = ["tenant_id = %s", "project_id = %s"]
        params: list[object] = [tenant_id, project_id]
        for column, value in (
            ("status", status),
            ("task_id", task_id),
            ("camera_id", camera_id),
            ("watchlist_id", watchlist_id),
            ("portrait_identity_id", portrait_identity_id),
        ):
            if value is not None:
                clauses.append(f"{column} = %s")
                params.append(value)
        if since is not None:
            clauses.append("last_seen_at >= to_timestamp(%s)")
            params.append(since)
        if until is not None:
            clauses.append("first_seen_at <= to_timestamp(%s)")
            params.append(until)
        where_sql = " AND ".join(clauses)
        async with self._pool.connection() as conn:
            count_cursor = await conn.execute(f"SELECT count(*) FROM scenara_surveillance_alerts WHERE {where_sql}", tuple(params))
            count_row = await count_cursor.fetchone()
            cursor = await conn.execute(
                f"""SELECT document FROM scenara_surveillance_alerts WHERE {where_sql}
                    ORDER BY triggered_at DESC, alert_id ASC OFFSET %s LIMIT %s""",
                (*params, offset, limit),
            )
            rows = await cursor.fetchall()
        return [AlertRecord.model_validate(row[0]) for row in rows], int(count_row[0] if count_row else 0)

    async def triage_alert(self, alert: AlertRecord, event: AlertEvent, *, expected_revision: int) -> AlertWriteResult:
        from psycopg.types.json import Jsonb

        stored = alert.model_copy(update={"revision": expected_revision + 1}, deep=True)
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """UPDATE scenara_surveillance_alerts
                   SET status = %s, updated_at = to_timestamp(%s), revision = %s, document = %s
                   WHERE tenant_id = %s AND project_id = %s AND alert_id = %s
                     AND revision = %s AND status = 'pending'""",
                (
                    stored.status,
                    stored.updated_at,
                    stored.revision,
                    Jsonb(stored.model_dump(mode="json")),
                    stored.tenant_id,
                    stored.project_id,
                    stored.alert_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise SurveillanceConflict("alert revision or status conflict")
            stored_event = await self._insert_event(conn, event)
        return AlertWriteResult(alert=stored, event=stored_event, emitted=True)

    async def events_after(self, tenant_id: str, project_id: str, cursor: int, *, limit: int) -> list[AlertEvent]:
        async with self._pool.connection() as conn:
            event_cursor = await conn.execute(
                """SELECT document FROM scenara_surveillance_alert_events
                   WHERE tenant_id = %s AND project_id = %s AND event_cursor > %s
                   ORDER BY event_cursor ASC LIMIT %s""",
                (tenant_id, project_id, cursor, limit),
            )
            rows = await event_cursor.fetchall()
        return [AlertEvent.model_validate(row[0]) for row in rows]


__all__ = ["PostgresSurveillanceRepository"]
