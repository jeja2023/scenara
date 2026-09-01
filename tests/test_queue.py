from __future__ import annotations

import asyncio
from typing import Any

import pytest

from scenara.infrastructure.queue import RedisRunQueue
from scenara.platform.queue import QueueLaneDepth


class _QueueDrained(RuntimeError):
    pass


class _RecoveredRedis:
    def __init__(self) -> None:
        self.acked: list[tuple[str, str, str]] = []
        self.renewals: list[tuple[str, str, str, str]] = []
        self.renewed = asyncio.Event()

    async def xautoclaim(
        self,
        stream: str,
        group: str,
        consumer: str,
        min_idle_time: int,
        *,
        start_id: str,
        count: int,
    ) -> tuple[str, list[tuple[str, dict[str, str]]], list[str]]:
        assert (stream, group, consumer, min_idle_time, start_id, count) == (
            "scenara:runs:batch",
            "scenara-workers:batch",
            "worker-restarted",
            30,
            "0-0",
            1,
        )
        return "0-0", [("17-0", {"tenant_id": "t", "project_id": "p", "run_id": "run-1"})], []

    async def xclaim(
        self,
        stream: str,
        group: str,
        consumer: str,
        min_idle_time: int,
        message_ids: list[str],
        *,
        justid: bool,
    ) -> list[str]:
        assert min_idle_time == 0
        assert justid is True
        self.renewals.append((stream, group, consumer, message_ids[0]))
        self.renewed.set()
        return message_ids

    async def xreadgroup(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise AssertionError("new messages must not be read before recovered pending work")

    async def xack(self, stream: str, group: str, message_id: str) -> None:
        self.acked.append((stream, group, message_id))
        raise _QueueDrained


@pytest.mark.asyncio
async def test_redis_worker_recovers_stale_pending_message() -> None:
    queue = RedisRunQueue("redis://unused", visibility_timeout_ms=30)
    client = _RecoveredRedis()
    queue._client = client
    calls: list[tuple[str, str, str]] = []

    async def handler(tenant_id: str, project_id: str, run_id: str) -> None:
        await client.renewed.wait()
        calls.append((tenant_id, project_id, run_id))

    queue.set_handler(handler)
    with pytest.raises(_QueueDrained):
        await queue.consume_forever(consumer="worker-restarted")
    assert calls == [("t", "p", "run-1")]
    assert client.renewals == [("scenara:runs:batch", "scenara-workers:batch", "worker-restarted", "17-0")]
    assert client.acked == [("scenara:runs:batch", "scenara-workers:batch", "17-0")]


@pytest.mark.asyncio
async def test_redis_queue_exposes_lag_and_pending_by_lane() -> None:
    class MetricsRedis:
        async def xinfo_groups(self, stream: str) -> list[dict[str, object]]:
            lane = stream.rsplit(":", 1)[-1]
            return [{"name": f"scenara-workers:{lane}", "pending": 2, "lag": 7}]

    queue = RedisRunQueue("redis://unused")
    queue._client = MetricsRedis()
    assert await queue.depth() == {
        "batch": QueueLaneDepth(lag=7, pending=2),
        "stream": QueueLaneDepth(lag=7, pending=2),
    }
