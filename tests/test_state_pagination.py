from __future__ import annotations

import hashlib

import pytest

from scenara.infrastructure.memory_state import MemoryStateStore
from scenara.platform.models import MediaAsset, MediaKind, MediaSource, PipelineRef, RunRecord, RunStatus


def _asset(identifier: str, created_at: float, *, deleted: bool = False) -> MediaAsset:
    return MediaAsset(
        asset_id=f"ast_{identifier}",
        tenant_id="tenant",
        project_id="project",
        kind=MediaKind.IMAGE,
        content_type="image/png",
        size_bytes=3,
        sha256=hashlib.sha256(identifier.encode()).hexdigest(),
        object_key=f"objects/{identifier}.png",
        created_at=created_at,
        deleted_at=created_at + 1 if deleted else None,
    )


def _source(identifier: str, created_at: float) -> MediaSource:
    return MediaSource(
        source_id=f"src_{identifier}",
        tenant_id="tenant",
        project_id="project",
        name=identifier,
        masked_url=f"https://media.example/{identifier}",
        secret_ref=f"secret://sources/{identifier}",
        created_at=created_at,
    )


def _run(
    identifier: str,
    created_at: float,
    *,
    domain: str = "portrait",
    status: RunStatus = RunStatus.QUEUED,
    asset_id: str | None = None,
    source_id: str | None = None,
) -> RunRecord:
    return RunRecord(
        run_id=f"run_{identifier}",
        tenant_id="tenant",
        project_id="project",
        domain=domain,
        pipeline=PipelineRef(pipeline_id=f"{domain}.default", version="1.0.0"),
        asset_id=asset_id,
        source_id=source_id,
        status=status,
        created_at=created_at,
        updated_at=created_at,
    )


@pytest.mark.asyncio
async def test_state_lists_apply_filters_and_pagination_before_returning_rows() -> None:
    state = MemoryStateStore()
    for asset in (_asset("old", 1), _asset("deleted", 2, deleted=True), _asset("new", 3)):
        await state.create_asset(asset)
    for source in (_source("old", 1), _source("new", 2)):
        await state.create_source(source)

    assets = await state.list_assets("tenant", "project", include_deleted=False, offset=1, limit=1)
    sources = await state.list_sources("tenant", "project", offset=1, limit=1)

    assert [item.asset_id for item in assets] == ["ast_old"]
    assert await state.count_assets("tenant", "project", include_deleted=False) == 2
    assert [item.source_id for item in sources] == ["src_old"]
    assert await state.count_sources("tenant", "project") == 2


@pytest.mark.asyncio
async def test_run_queries_filter_count_and_check_active_references() -> None:
    runs = (
        _run("portrait_old", 1, asset_id="ast_target"),
        _run("ocr_done", 2, domain="ocr", status=RunStatus.COMPLETED, source_id="src_target"),
        _run("portrait_new", 3, asset_id="ast_target"),
    )
    state = MemoryStateStore()
    for index, run in enumerate(runs):
        await state.create_run_idempotent(run, idempotency_key=f"idem_{index}", request_hash=str(index))

    page = await state.list_runs("tenant", "project", domain="portrait", offset=1, limit=1)

    assert [item.run_id for item in page] == ["run_portrait_old"]
    assert await state.count_runs("tenant", "project", domain="portrait") == 2
    assert await state.count_runs("tenant", "project", status=RunStatus.COMPLETED) == 1
    assert [item.run_id for item in await state.recoverable_runs()] == [
        "run_portrait_old",
        "run_portrait_new",
    ]
    assert await state.has_non_terminal_run("tenant", "project", asset_id="ast_target") is True
    assert await state.has_non_terminal_run("tenant", "project", source_id="src_target") is False
    with pytest.raises(ValueError, match="exactly one"):
        await state.has_non_terminal_run("tenant", "project")
