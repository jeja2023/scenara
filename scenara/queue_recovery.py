from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from scenara.infrastructure.queue import RedisRunQueue
from scenara.platform.models import MediaAsset, MediaSource, RunRecord
from scenara.platform.objects import ObjectStore


class RecoveryState(Protocol):
    async def recoverable_runs(self) -> list[RunRecord]: ...

    async def get_asset(self, tenant_id: str, project_id: str, asset_id: str) -> MediaAsset | None: ...

    async def get_source(self, tenant_id: str, project_id: str, source_id: str) -> MediaSource | None: ...


@dataclass(frozen=True, slots=True)
class QueueRecoverySummary:
    recoverable_runs: int
    enqueued_runs: int
    assets_verified: int
    sources_verified: int


async def rebuild_redis_run_queue(
    state: RecoveryState,
    objects: ObjectStore,
    queue: RedisRunQueue,
) -> QueueRecoverySummary:
    runs = await state.recoverable_runs()
    assets_verified = 0
    sources_verified = 0
    for run in runs:
        if run.asset_id is not None:
            asset = await state.get_asset(run.tenant_id, run.project_id, run.asset_id)
            if asset is None or asset.original_deleted_at is not None:
                raise RuntimeError(f"recoverable Run {run.run_id} has no retained media asset")
            try:
                await objects.verify(asset.object_key, asset.sha256)
            except Exception as exc:
                raise RuntimeError(
                    f"recoverable Run {run.run_id} media object is missing or corrupt"
                ) from exc
            assets_verified += 1
            continue
        if run.source_id is not None:
            source = await state.get_source(run.tenant_id, run.project_id, run.source_id)
            if source is None:
                raise RuntimeError(f"recoverable Run {run.run_id} media source is missing")
            sources_verified += 1
            continue
        raise RuntimeError(f"recoverable Run {run.run_id} has no media reference")

    enqueued = await queue.rebuild_empty(runs)
    return QueueRecoverySummary(
        recoverable_runs=len(runs),
        enqueued_runs=enqueued,
        assets_verified=assets_verified,
        sources_verified=sources_verified,
    )


__all__ = ["QueueRecoverySummary", "RecoveryState", "rebuild_redis_run_queue"]
