"""In-memory surveillance repository for tests and local development."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from scenara.platform.surveillance import (
    AlertCandidate,
    AlertEvent,
    AlertRecord,
    AlertStatus,
    AlertWriteResult,
    SurveillanceConflict,
    SurveillanceRepository,
    SurveillanceTask,
    Watchlist,
    WatchlistMember,
)


class MemorySurveillanceRepository(SurveillanceRepository):
    """Process-local implementation; production debounce must use PostgreSQL/Redis."""

    atomic_webhook_outbox = False

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._watchlists: dict[tuple[str, str, str], Watchlist] = {}
        self._members: dict[tuple[str, str, str], WatchlistMember] = {}
        self._tasks: dict[tuple[str, str, str], SurveillanceTask] = {}
        self._alerts: dict[tuple[str, str, str], AlertRecord] = {}
        self._events: dict[tuple[str, str], list[AlertEvent]] = defaultdict(list)
        self._debounce: dict[tuple[str, str, str], object] = {}

    @staticmethod
    def _key(tenant_id: str, project_id: str, identifier: str) -> tuple[str, str, str]:
        return tenant_id, project_id, identifier

    async def create_watchlist(self, watchlist: Watchlist) -> Watchlist:
        async with self._lock:
            key = self._key(watchlist.tenant_id, watchlist.project_id, watchlist.watchlist_id)
            if key in self._watchlists:
                raise SurveillanceConflict("watchlist already exists")
            self._watchlists[key] = watchlist.model_copy(deep=True)
            return watchlist.model_copy(deep=True)

    async def get_watchlist(self, tenant_id: str, project_id: str, watchlist_id: str) -> Watchlist | None:
        async with self._lock:
            value = self._watchlists.get(self._key(tenant_id, project_id, watchlist_id))
            return value.model_copy(deep=True) if value else None

    async def list_watchlists(self, tenant_id: str, project_id: str, *, offset: int, limit: int) -> tuple[list[Watchlist], int]:
        async with self._lock:
            rows = sorted(
                (item.model_copy(deep=True) for key, item in self._watchlists.items() if key[:2] == (tenant_id, project_id)),
                key=lambda item: (-item.updated_at, item.watchlist_id),
            )
            return rows[offset : offset + limit], len(rows)

    async def save_watchlist(self, watchlist: Watchlist, *, expected_revision: int) -> Watchlist:
        async with self._lock:
            key = self._key(watchlist.tenant_id, watchlist.project_id, watchlist.watchlist_id)
            current = self._watchlists.get(key)
            if current is None:
                raise SurveillanceConflict("watchlist does not exist")
            if current.revision != expected_revision:
                raise SurveillanceConflict("watchlist revision conflict")
            stored = watchlist.model_copy(update={"revision": expected_revision + 1}, deep=True)
            self._watchlists[key] = stored
            return stored.model_copy(deep=True)

    async def delete_watchlist(self, tenant_id: str, project_id: str, watchlist_id: str) -> bool:
        async with self._lock:
            key = self._key(tenant_id, project_id, watchlist_id)
            removed = self._watchlists.pop(key, None)
            if removed is None:
                return False
            for member_key, member in list(self._members.items()):
                if member.tenant_id == tenant_id and member.project_id == project_id and member.watchlist_id == watchlist_id:
                    del self._members[member_key]
            return True

    async def create_member(self, member: WatchlistMember) -> WatchlistMember:
        async with self._lock:
            key = self._key(member.tenant_id, member.project_id, member.member_id)
            if key in self._members:
                raise SurveillanceConflict("watchlist member already exists")
            if any(
                item.tenant_id == member.tenant_id
                and item.project_id == member.project_id
                and item.watchlist_id == member.watchlist_id
                and item.portrait_identity_id == member.portrait_identity_id
                for item in self._members.values()
            ):
                raise SurveillanceConflict("portrait identity is already a member of this watchlist")
            self._members[key] = member.model_copy(deep=True)
            return member.model_copy(deep=True)

    async def get_member(self, tenant_id: str, project_id: str, member_id: str) -> WatchlistMember | None:
        async with self._lock:
            value = self._members.get(self._key(tenant_id, project_id, member_id))
            return value.model_copy(deep=True) if value else None

    async def list_members(
        self, tenant_id: str, project_id: str, watchlist_id: str, *, offset: int, limit: int
    ) -> tuple[list[WatchlistMember], int]:
        async with self._lock:
            rows = sorted(
                (
                    item.model_copy(deep=True)
                    for item in self._members.values()
                    if (item.tenant_id, item.project_id, item.watchlist_id) == (tenant_id, project_id, watchlist_id)
                ),
                key=lambda item: (-item.updated_at, item.member_id),
            )
            return rows[offset : offset + limit], len(rows)

    async def list_active_members(
        self, tenant_id: str, project_id: str, watchlist_ids: list[str], *, at: float
    ) -> list[WatchlistMember]:
        wanted = set(watchlist_ids)
        async with self._lock:
            return [
                item.model_copy(deep=True)
                for item in self._members.values()
                if item.tenant_id == tenant_id
                and item.project_id == project_id
                and item.watchlist_id in wanted
                and item.active_at(at)
            ]

    async def save_member(self, member: WatchlistMember, *, expected_revision: int) -> WatchlistMember:
        async with self._lock:
            key = self._key(member.tenant_id, member.project_id, member.member_id)
            current = self._members.get(key)
            if current is None:
                raise SurveillanceConflict("watchlist member does not exist")
            if current.revision != expected_revision:
                raise SurveillanceConflict("watchlist member revision conflict")
            stored = member.model_copy(update={"revision": expected_revision + 1}, deep=True)
            self._members[key] = stored
            return stored.model_copy(deep=True)

    async def delete_member(self, tenant_id: str, project_id: str, member_id: str) -> bool:
        async with self._lock:
            return self._members.pop(self._key(tenant_id, project_id, member_id), None) is not None

    async def create_task(self, task: SurveillanceTask) -> SurveillanceTask:
        async with self._lock:
            key = self._key(task.tenant_id, task.project_id, task.task_id)
            if key in self._tasks:
                raise SurveillanceConflict("surveillance task already exists")
            self._tasks[key] = task.model_copy(deep=True)
            return task.model_copy(deep=True)

    async def get_task(self, tenant_id: str, project_id: str, task_id: str) -> SurveillanceTask | None:
        async with self._lock:
            value = self._tasks.get(self._key(tenant_id, project_id, task_id))
            return value.model_copy(deep=True) if value else None

    async def list_tasks(self, tenant_id: str, project_id: str, *, offset: int, limit: int) -> tuple[list[SurveillanceTask], int]:
        async with self._lock:
            rows = sorted(
                (item.model_copy(deep=True) for key, item in self._tasks.items() if key[:2] == (tenant_id, project_id)),
                key=lambda item: (-item.updated_at, item.task_id),
            )
            return rows[offset : offset + limit], len(rows)

    async def list_active_tasks_for_source(self, tenant_id: str, project_id: str, source_id: str) -> list[SurveillanceTask]:
        async with self._lock:
            return [
                item.model_copy(deep=True)
                for item in self._tasks.values()
                if item.tenant_id == tenant_id
                and item.project_id == project_id
                and item.status.value == "active"
                and any(binding.source_id == source_id for binding in item.bindings)
            ]

    async def list_active_tasks(self, tenant_id: str, project_id: str) -> list[SurveillanceTask]:
        async with self._lock:
            return [
                item.model_copy(deep=True)
                for item in self._tasks.values()
                if item.tenant_id == tenant_id and item.project_id == project_id and item.status.value == "active"
            ]

    async def list_all_active_tasks(self) -> list[SurveillanceTask]:
        async with self._lock:
            return [item.model_copy(deep=True) for item in self._tasks.values() if item.status.value == "active"]

    async def save_task(self, task: SurveillanceTask, *, expected_revision: int) -> SurveillanceTask:
        async with self._lock:
            key = self._key(task.tenant_id, task.project_id, task.task_id)
            current = self._tasks.get(key)
            if current is None:
                raise SurveillanceConflict("surveillance task does not exist")
            if current.revision != expected_revision:
                raise SurveillanceConflict("surveillance task revision conflict")
            stored = task.model_copy(update={"revision": expected_revision + 1}, deep=True)
            self._tasks[key] = stored
            return stored.model_copy(deep=True)

    async def record_alert(self, candidate: AlertCandidate) -> AlertWriteResult:
        async with self._lock:
            alert = candidate.alert
            debounce_key = self._key(alert.tenant_id, alert.project_id, candidate.debounce.debounce_key)
            current = self._debounce.get(debounce_key)
            if current is not None:
                state = candidate.debounce.__class__.model_validate(current)
                if state.cooldown_until > alert.triggered_at and state.last_alert_id is not None:
                    existing = self._alerts.get(self._key(alert.tenant_id, alert.project_id, state.last_alert_id))
                    if existing is not None:
                        updated = existing.model_copy(
                            update={
                                "last_seen_at": max(existing.last_seen_at, alert.last_seen_at),
                                "match_score": alert.match_score,
                                "max_score": max(existing.max_score, alert.max_score),
                                "occurrence_count": existing.occurrence_count + 1,
                                "updated_at": alert.updated_at,
                                "revision": existing.revision + 1,
                            }
                        )
                        self._alerts[self._key(alert.tenant_id, alert.project_id, updated.alert_id)] = updated
                        self._debounce[debounce_key] = state.model_copy(
                            update={
                                "last_seen_at": max(state.last_seen_at, alert.last_seen_at),
                                "max_score": max(state.max_score, alert.max_score),
                                "occurrence_count": state.occurrence_count + 1,
                                "revision": state.revision + 1,
                            }
                        )
                        return AlertWriteResult(alert=updated, emitted=False)

            alert_key = self._key(alert.tenant_id, alert.project_id, alert.alert_id)
            existing = self._alerts.get(alert_key)
            if existing is not None:
                return AlertWriteResult(alert=existing.model_copy(deep=True), emitted=False)
            self._alerts[alert_key] = alert.model_copy(deep=True)
            event_key = (alert.tenant_id, alert.project_id)
            event = candidate.event.model_copy(update={"event_cursor": len(self._events[event_key]) + 1}, deep=True)
            self._events[event_key].append(event)
            self._debounce[debounce_key] = candidate.debounce.model_copy(update={"last_alert_id": alert.alert_id}, deep=True)
            return AlertWriteResult(alert=alert.model_copy(deep=True), event=event.model_copy(deep=True), emitted=True)

    async def get_alert(self, tenant_id: str, project_id: str, alert_id: str) -> AlertRecord | None:
        async with self._lock:
            value = self._alerts.get(self._key(tenant_id, project_id, alert_id))
            return value.model_copy(deep=True) if value else None

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
        async with self._lock:
            rows = [
                item.model_copy(deep=True)
                for item in self._alerts.values()
                if item.tenant_id == tenant_id
                and item.project_id == project_id
                and (status is None or item.status == status)
                and (task_id is None or item.task_id == task_id)
                and (camera_id is None or item.camera_id == camera_id)
                and (watchlist_id is None or item.watchlist_id == watchlist_id)
                and (portrait_identity_id is None or item.portrait_identity_id == portrait_identity_id)
                and (since is None or item.last_seen_at >= since)
                and (until is None or item.first_seen_at <= until)
            ]
            rows.sort(key=lambda item: (-item.triggered_at, item.alert_id))
            return rows[offset : offset + limit], len(rows)

    async def triage_alert(self, alert: AlertRecord, event: AlertEvent, *, expected_revision: int) -> AlertWriteResult:
        async with self._lock:
            key = self._key(alert.tenant_id, alert.project_id, alert.alert_id)
            current = self._alerts.get(key)
            if current is None:
                raise SurveillanceConflict("alert does not exist")
            if current.revision != expected_revision:
                raise SurveillanceConflict("alert revision conflict")
            if current.status != AlertStatus.PENDING:
                raise SurveillanceConflict("alert has already been triaged")
            stored = alert.model_copy(update={"revision": expected_revision + 1}, deep=True)
            self._alerts[key] = stored
            event_key = (stored.tenant_id, stored.project_id)
            stored_event = event.model_copy(update={"event_cursor": len(self._events[event_key]) + 1}, deep=True)
            self._events[event_key].append(stored_event)
            return AlertWriteResult(alert=stored.model_copy(deep=True), event=stored_event.model_copy(deep=True), emitted=True)

    async def events_after(self, tenant_id: str, project_id: str, cursor: int, *, limit: int) -> list[AlertEvent]:
        async with self._lock:
            return [item.model_copy(deep=True) for item in self._events[(tenant_id, project_id)] if item.event_cursor > cursor][:limit]


__all__ = ["MemorySurveillanceRepository"]
