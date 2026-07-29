from __future__ import annotations

from typing import Protocol

from scenara.platform.models import MediaAsset, MediaSource, ResultReference, RunEvent, RunRecord


class StateConflict(RuntimeError):
    pass


class StateStore(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def create_asset(self, asset: MediaAsset) -> MediaAsset: ...

    async def get_asset(self, tenant_id: str, project_id: str, asset_id: str) -> MediaAsset | None: ...

    async def list_assets(self, tenant_id: str, project_id: str) -> list[MediaAsset]: ...

    async def create_source(self, source: MediaSource) -> MediaSource: ...

    async def get_source(self, tenant_id: str, project_id: str, source_id: str) -> MediaSource | None: ...

    async def list_sources(self, tenant_id: str, project_id: str) -> list[MediaSource]: ...

    async def create_run_idempotent(
        self,
        run: RunRecord,
        *,
        idempotency_key: str,
        request_hash: str,
    ) -> tuple[RunRecord, bool]: ...

    async def get_run(self, tenant_id: str, project_id: str, run_id: str) -> RunRecord | None: ...

    async def list_runs(self, tenant_id: str, project_id: str) -> list[RunRecord]: ...

    async def save_run(self, run: RunRecord, *, expected_revision: int) -> RunRecord: ...

    async def append_event(self, tenant_id: str, project_id: str, event: RunEvent) -> RunEvent: ...

    async def events_after(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        event_id: int,
    ) -> list[RunEvent]: ...

    async def save_result_reference(
        self,
        tenant_id: str,
        project_id: str,
        result: ResultReference,
    ) -> None: ...

    async def get_result_reference(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> ResultReference | None: ...


__all__ = ["StateConflict", "StateStore"]
