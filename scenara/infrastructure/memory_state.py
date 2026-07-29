from __future__ import annotations

import asyncio
from collections.abc import Iterable

from scenara.platform.models import MediaAsset, MediaSource, ResultReference, RunEvent, RunRecord
from scenara.platform.store import StateConflict


class MemoryStateStore:
    """Development store. Production startup rejects this backend."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._assets: dict[tuple[str, str, str], MediaAsset] = {}
        self._sources: dict[tuple[str, str, str], MediaSource] = {}
        self._runs: dict[tuple[str, str, str], RunRecord] = {}
        self._events: dict[tuple[str, str, str], list[RunEvent]] = {}
        self._results: dict[tuple[str, str, str], ResultReference] = {}
        self._idempotency: dict[tuple[str, str, str], tuple[str, str]] = {}

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    @staticmethod
    def _key(tenant_id: str, project_id: str, value_id: str) -> tuple[str, str, str]:
        return tenant_id, project_id, value_id

    async def create_asset(self, asset: MediaAsset) -> MediaAsset:
        async with self._lock:
            key = self._key(asset.tenant_id, asset.project_id, asset.asset_id)
            if key in self._assets:
                raise StateConflict("media asset already exists")
            self._assets[key] = asset.model_copy(deep=True)
        return asset.model_copy(deep=True)

    async def get_asset(self, tenant_id: str, project_id: str, asset_id: str) -> MediaAsset | None:
        async with self._lock:
            asset = self._assets.get(self._key(tenant_id, project_id, asset_id))
            return asset.model_copy(deep=True) if asset else None

    async def list_assets(self, tenant_id: str, project_id: str) -> list[MediaAsset]:
        async with self._lock:
            rows = [
                item.model_copy(deep=True)
                for (row_tenant, row_project, _), item in self._assets.items()
                if row_tenant == tenant_id and row_project == project_id
            ]
        return sorted(rows, key=lambda item: (item.created_at, item.asset_id), reverse=True)

    async def create_source(self, source: MediaSource) -> MediaSource:
        async with self._lock:
            key = self._key(source.tenant_id, source.project_id, source.source_id)
            if key in self._sources:
                raise StateConflict("media source already exists")
            self._sources[key] = source.model_copy(deep=True)
        return source.model_copy(deep=True)

    async def get_source(self, tenant_id: str, project_id: str, source_id: str) -> MediaSource | None:
        async with self._lock:
            source = self._sources.get(self._key(tenant_id, project_id, source_id))
            return source.model_copy(deep=True) if source else None

    async def list_sources(self, tenant_id: str, project_id: str) -> list[MediaSource]:
        async with self._lock:
            rows = [
                item.model_copy(deep=True)
                for (row_tenant, row_project, _), item in self._sources.items()
                if row_tenant == tenant_id and row_project == project_id
            ]
        return sorted(rows, key=lambda item: (item.created_at, item.source_id), reverse=True)

    async def create_run_idempotent(
        self,
        run: RunRecord,
        *,
        idempotency_key: str,
        request_hash: str,
    ) -> tuple[RunRecord, bool]:
        async with self._lock:
            idem_key = self._key(run.tenant_id, run.project_id, idempotency_key)
            existing = self._idempotency.get(idem_key)
            if existing is not None:
                existing_hash, existing_run_id = existing
                if existing_hash != request_hash:
                    raise StateConflict("idempotency key was already used for a different request")
                existing_run = self._runs[self._key(run.tenant_id, run.project_id, existing_run_id)]
                return existing_run.model_copy(deep=True), False
            key = self._key(run.tenant_id, run.project_id, run.run_id)
            if key in self._runs:
                raise StateConflict("run already exists")
            self._runs[key] = run.model_copy(deep=True)
            self._events[key] = []
            self._idempotency[idem_key] = (request_hash, run.run_id)
            return run.model_copy(deep=True), True

    async def get_run(self, tenant_id: str, project_id: str, run_id: str) -> RunRecord | None:
        async with self._lock:
            run = self._runs.get(self._key(tenant_id, project_id, run_id))
            return run.model_copy(deep=True) if run else None

    async def list_runs(self, tenant_id: str, project_id: str) -> list[RunRecord]:
        async with self._lock:
            rows = [
                item.model_copy(deep=True)
                for (row_tenant, row_project, _), item in self._runs.items()
                if row_tenant == tenant_id and row_project == project_id
            ]
        return sorted(rows, key=lambda item: (item.created_at, item.run_id), reverse=True)

    async def save_run(self, run: RunRecord, *, expected_revision: int) -> RunRecord:
        async with self._lock:
            key = self._key(run.tenant_id, run.project_id, run.run_id)
            current = self._runs.get(key)
            if current is None:
                raise StateConflict("run does not exist")
            if current.revision != expected_revision:
                raise StateConflict("run revision conflict")
            saved = run.model_copy(update={"revision": expected_revision + 1}, deep=True)
            self._runs[key] = saved
            return saved.model_copy(deep=True)

    async def append_event(self, tenant_id: str, project_id: str, event: RunEvent) -> RunEvent:
        async with self._lock:
            key = self._key(tenant_id, project_id, event.run_id)
            rows = self._events.get(key)
            if rows is None:
                raise StateConflict("run does not exist")
            stored = event.model_copy(update={"event_id": len(rows) + 1}, deep=True)
            rows.append(stored)
            return stored.model_copy(deep=True)

    async def events_after(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        event_id: int,
    ) -> list[RunEvent]:
        async with self._lock:
            rows: Iterable[RunEvent] = self._events.get(self._key(tenant_id, project_id, run_id), [])
            return [item.model_copy(deep=True) for item in rows if item.event_id > event_id]

    async def save_result_reference(
        self,
        tenant_id: str,
        project_id: str,
        result: ResultReference,
    ) -> None:
        async with self._lock:
            self._results[self._key(tenant_id, project_id, result.run_id)] = result.model_copy(deep=True)

    async def get_result_reference(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> ResultReference | None:
        async with self._lock:
            result = self._results.get(self._key(tenant_id, project_id, run_id))
            return result.model_copy(deep=True) if result else None


__all__ = ["MemoryStateStore"]
