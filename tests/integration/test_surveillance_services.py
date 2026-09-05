"""布控预警 PostgreSQL 仓储的集成校验。

`record_alert` 在真实数据库上跨 scenara_surveillance_alerts 与
scenara_surveillance_debounce 两张表加锁：折叠、幂等去重与乐观锁只有在这里
跑过，才能确认唯一约束、行锁顺序和 JSONB 往返与内存实现一致。
"""

from __future__ import annotations

import asyncio
import sys

import pytest

from scenara.infrastructure.postgres_state import PostgresStateStore
from scenara.infrastructure.postgres_surveillance import PostgresSurveillanceRepository
from tests.integration.postgres_scope import (
    POSTGRES_DSN,
    create_binding_targets,
    create_isolated_scope,
    create_portrait_identities,
)
from tests.surveillance_repository_contract import (
    assert_surveillance_repository_contract,
)

pytestmark = pytest.mark.integration

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def require_integration_services() -> None:
    import os

    if os.getenv("SCENARA_RUN_INTEGRATION") != "1":
        pytest.skip("set SCENARA_RUN_INTEGRATION=1 to run service integration tests")


@pytest.mark.asyncio
async def test_postgres_surveillance_repository_satisfies_the_shared_contract() -> None:
    state = PostgresStateStore(POSTGRES_DSN)
    await state.open()
    try:
        tenant_id, project_id = await create_isolated_scope(state, "surv")
        active, paused = await create_portrait_identities(state, tenant_id, project_id, 2)
        source_id, camera_id = await create_binding_targets(state, tenant_id, project_id)
        await assert_surveillance_repository_contract(
            PostgresSurveillanceRepository(state.pool),
            tenant_id=tenant_id,
            project_id=project_id,
            portrait_identity_ids=(active, paused),
            source_id=source_id,
            camera_id=camera_id,
        )
    finally:
        await state.close()


@pytest.mark.asyncio
async def test_postgres_surveillance_repository_declares_atomic_webhook_outbox() -> None:
    """PostgreSQL 后端与告警写入同事务投递 webhook，内存后端不具备该保证。"""

    assert PostgresSurveillanceRepository.atomic_webhook_outbox is True
