"""控制平面记录 PostgreSQL 仓储的集成校验。

会话按 JSONB 字段查询、配额按 FOR UPDATE 事务累加，都依赖真实数据库的类型
转换与行锁行为，只有对着 PostgreSQL 跑过才能确认与内存实现一致。
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

from scenara.infrastructure.postgres_control_plane import PostgresControlPlaneStore
from scenara.infrastructure.postgres_state import PostgresStateStore
from tests.control_plane_store_contract import (
    assert_control_plane_store_contract,
)
from tests.integration.postgres_scope import POSTGRES_DSN, create_isolated_scope

pytestmark = pytest.mark.integration

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def require_integration_services() -> None:
    if os.getenv("SCENARA_RUN_INTEGRATION") != "1":
        pytest.skip("set SCENARA_RUN_INTEGRATION=1 to run service integration tests")


@pytest.mark.asyncio
async def test_postgres_control_plane_store_satisfies_the_shared_contract() -> None:
    state = PostgresStateStore(POSTGRES_DSN)
    await state.open()
    try:
        tenant_id, project_id = await create_isolated_scope(state, "ctlp")
        await assert_control_plane_store_contract(
            PostgresControlPlaneStore(state.pool),
            tenant_id=tenant_id,
            project_id=project_id,
        )
    finally:
        await state.close()
