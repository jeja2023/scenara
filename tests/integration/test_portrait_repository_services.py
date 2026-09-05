"""人像身份 PostgreSQL 仓储的集成校验。

身份与注册记录分表存放，删除身份时注册记录必须一并清理，否则会留下指向已删
身份的特征模板。这条语义只有对着真实数据库跑过才算确认。
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

from scenara.infrastructure.postgres_portrait import PostgresPortraitRepository
from scenara.infrastructure.postgres_state import PostgresStateStore
from tests.integration.postgres_scope import (
    POSTGRES_DSN,
    create_feature,
    create_isolated_scope,
)
from tests.portrait_repository_contract import assert_portrait_repository_contract

pytestmark = pytest.mark.integration

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def require_integration_services() -> None:
    if os.getenv("SCENARA_RUN_INTEGRATION") != "1":
        pytest.skip("set SCENARA_RUN_INTEGRATION=1 to run service integration tests")


@pytest.mark.asyncio
async def test_postgres_portrait_repository_satisfies_the_shared_contract() -> None:
    state = PostgresStateStore(POSTGRES_DSN)
    await state.open()
    try:
        tenant_id, project_id = await create_isolated_scope(state, "port")
        feature_id, feature_space_id = await create_feature(
            state, tenant_id, project_id, "contract-subject"
        )
        await assert_portrait_repository_contract(
            PostgresPortraitRepository(state.pool),
            tenant_id=tenant_id,
            project_id=project_id,
            feature_id=feature_id,
            feature_space_id=feature_space_id,
        )
    finally:
        await state.close()
