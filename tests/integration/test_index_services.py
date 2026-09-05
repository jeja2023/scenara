"""结果索引 PostgreSQL 仓储的集成校验。

向量近邻走 pgvector、全文命中走 tsquery、墓碑删除与过期清理走批量 UPDATE：
这些语义只有对着真实数据库跑过，才能确认与内存实现一致。
"""

from __future__ import annotations

import asyncio
import os
import sys
from uuid import uuid4

import pytest

from scenara.infrastructure.postgres_index import PostgresIndexStore
from scenara.infrastructure.postgres_state import PostgresStateStore
from tests.index_store_contract import assert_index_store_contract
from tests.integration.postgres_scope import POSTGRES_DSN

pytestmark = pytest.mark.integration

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def require_integration_services() -> None:
    if os.getenv("SCENARA_RUN_INTEGRATION") != "1":
        pytest.skip("set SCENARA_RUN_INTEGRATION=1 to run service integration tests")


@pytest.mark.asyncio
async def test_postgres_index_store_satisfies_the_shared_contract() -> None:
    state = PostgresStateStore(POSTGRES_DSN)
    await state.open()
    try:
        suffix = uuid4().hex[:16]
        await assert_index_store_contract(
            PostgresIndexStore(state.pool),
            tenant_id=f"idx_{suffix}",
            project_id="qualification",
            other_tenant_id=f"idx_{suffix}_other",
        )
    finally:
        await state.close()
