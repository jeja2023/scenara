"""长期轨迹 PostgreSQL 仓储的集成校验。

生产环境跑的是这个适配器，开发环境跑的是内存实现。可达性探针与分页语义只有
对着真实数据库跑过，才能确认索引列、时间戳精度与内存实现一致。
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from uuid import uuid4

import pytest

from scenara.domains.portrait.trajectory import TrajectorySegment
from scenara.infrastructure.postgres_state import PostgresStateStore
from scenara.infrastructure.postgres_trajectory import PostgresTrajectoryRepository
from tests.integration.postgres_scope import POSTGRES_DSN, create_isolated_scope
from tests.trajectory_repository_contract import assert_trajectory_repository_contract

pytestmark = pytest.mark.integration

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def require_integration_services() -> None:
    if os.getenv("SCENARA_RUN_INTEGRATION") != "1":
        pytest.skip("set SCENARA_RUN_INTEGRATION=1 to run service integration tests")


@pytest.mark.asyncio
async def test_postgres_trajectory_repository_satisfies_the_shared_contract() -> None:
    state = PostgresStateStore(POSTGRES_DSN)
    await state.open()
    try:
        tenant_id, project_id = await create_isolated_scope(state, "traj")
        await assert_trajectory_repository_contract(
            PostgresTrajectoryRepository(state.pool),
            tenant_id=tenant_id,
            project_id=project_id,
        )
    finally:
        await state.close()


@pytest.mark.asyncio
async def test_postgres_trajectory_segments_page_and_intersect_time_windows() -> None:
    state = PostgresStateStore(POSTGRES_DSN)
    await state.open()
    try:
        tenant_id, project_id = await create_isolated_scope(state, "traj")
        repository = PostgresTrajectoryRepository(state.pool)
        identity_id = f"lti_{uuid4().hex}"
        for index in range(5):
            await repository.put_segment(
                TrajectorySegment(
                    segment_id=f"lts_{uuid4().hex}",
                    identity_id=identity_id,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=f"run_{index}",
                    camera_id="camera-a" if index % 2 == 0 else "camera-b",
                    first_seen_at=float(index * 100),
                    last_seen_at=float(index * 100 + 50),
                    created_at=time.time(),
                )
            )
        page, total = await repository.list_segments(
            tenant_id, project_id, identity_id=identity_id, offset=1, limit=2
        )
        assert total == 5
        assert [item.first_seen_at for item in page] == [100.0, 200.0]

        # 时间窗按区间求交：与 [120, 260] 相交的是 [100,150]、[200,250]。
        intersecting, matched = await repository.list_segments(
            tenant_id, project_id, identity_id=identity_id, since=120.0, until=260.0
        )
        assert matched == 2
        assert [item.first_seen_at for item in intersecting] == [100.0, 200.0]

        by_camera, camera_total = await repository.list_segments(
            tenant_id, project_id, identity_id=identity_id, camera_id="camera-b"
        )
        assert camera_total == 2
        assert {item.camera_id for item in by_camera} == {"camera-b"}
    finally:
        await state.close()
