"""控制平面记录仓储的跨后端契约。

会话令牌查找决定谁能登录，配额累加决定谁被限流。两者在内存实现里是字典操作、
在 PostgreSQL 里是 JSONB 查询与 FOR UPDATE 事务，语义必须完全一致。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from scenara.platform.control_plane_store import ControlPlaneStore


async def assert_control_plane_store_contract(
    store: ControlPlaneStore,
    *,
    tenant_id: str,
    project_id: str,
) -> None:
    """跑完整套契约；任一后端不满足即抛 AssertionError。"""

    suffix = uuid4().hex[:16]
    record_id = f"rec-{suffix}"
    document: dict[str, Any] = {
        "record_id": record_id,
        "display_name": "契约记录",
        "created_at": 1_000.0,
        "updated_at": 1_000.0,
    }

    # 写入、读取与列举的往返。
    await store.put("model_release", tenant_id, project_id, record_id, document)
    stored = await store.get("model_release", tenant_id, project_id, record_id)
    assert stored is not None
    assert stored["display_name"] == "契约记录"
    listed = await store.list("model_release", tenant_id, project_id)
    assert record_id in {item["record_id"] for item in listed}

    # 同一标识重复写入是覆盖而不是报错。
    await store.put(
        "model_release",
        tenant_id,
        project_id,
        record_id,
        {**document, "display_name": "契约记录改", "updated_at": 1_100.0},
    )
    updated = await store.get("model_release", tenant_id, project_id, record_id)
    assert updated is not None
    assert updated["display_name"] == "契约记录改"

    # 记录类型互不串台。
    assert await store.get("session", tenant_id, project_id, record_id) is None

    await store.delete("model_release", tenant_id, project_id, record_id)
    assert await store.get("model_release", tenant_id, project_id, record_id) is None

    # 会话按令牌摘要检索，并按过期时间批量清理。
    live_token = f"live-{uuid4().hex}"
    stale_token = f"stale-{uuid4().hex}"
    await store.put(
        "session",
        tenant_id,
        project_id,
        f"ses-live-{suffix}",
        {
            "record_id": f"ses-live-{suffix}",
            "token_sha256": live_token,
            "expires_at": 9_000.0,
            "created_at": 1_000.0,
            "updated_at": 1_000.0,
        },
    )
    await store.put(
        "session",
        tenant_id,
        project_id,
        f"ses-stale-{suffix}",
        {
            "record_id": f"ses-stale-{suffix}",
            "token_sha256": stale_token,
            "expires_at": 2_000.0,
            "created_at": 1_000.0,
            "updated_at": 1_000.0,
        },
    )
    resolved = await store.get_by_token_sha256(live_token)
    assert resolved is not None
    assert resolved["token_sha256"] == live_token
    assert await store.get_by_token_sha256(f"absent-{uuid4().hex}") is None

    removed = await store.delete_expired_sessions(2_000.0)
    assert removed >= 1
    assert await store.get_by_token_sha256(stale_token) is None
    assert await store.get_by_token_sha256(live_token) is not None

    # 配额在窗口内累加，超限即拒绝且用量不变。
    quota_id = f"quota-{suffix}"
    first, allowed = await store.adjust_quota_usage(
        tenant_id, project_id, quota_id, window_seconds=60.0, now=1_000.0, amount=3, limit=5
    )
    assert allowed is True
    assert first["used"] == 3

    second, allowed = await store.adjust_quota_usage(
        tenant_id, project_id, quota_id, window_seconds=60.0, now=1_010.0, amount=2, limit=5
    )
    assert allowed is True
    assert second["used"] == 5
    assert second["window_started_at"] == first["window_started_at"]

    denied, allowed = await store.adjust_quota_usage(
        tenant_id, project_id, quota_id, window_seconds=60.0, now=1_020.0, amount=1, limit=5
    )
    assert allowed is False
    assert denied["used"] == 5

    # 窗口滚动后重新计数。
    rolled, allowed = await store.adjust_quota_usage(
        tenant_id, project_id, quota_id, window_seconds=60.0, now=1_200.0, amount=1, limit=5
    )
    assert allowed is True
    assert rolled["used"] == 1
    assert rolled["window_started_at"] == 1_200.0

    # 无上限时永不拒绝。
    unlimited, allowed = await store.adjust_quota_usage(
        tenant_id, project_id, quota_id, window_seconds=60.0, now=1_210.0, amount=100, limit=None
    )
    assert allowed is True
    assert unlimited["used"] == 101


__all__ = ["assert_control_plane_store_contract"]
