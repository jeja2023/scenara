from __future__ import annotations

import pytest

from scenara.platform.index import MemoryIndexStore
from tests.index_store_contract import assert_index_store_contract


@pytest.mark.asyncio
async def test_memory_index_store_satisfies_the_shared_contract() -> None:
    """内存实现与 PostgreSQL 实现共用同一套索引契约。"""

    await assert_index_store_contract(
        MemoryIndexStore(),
        tenant_id="tenant-a",
        project_id="project-a",
        other_tenant_id="tenant-b",
    )
