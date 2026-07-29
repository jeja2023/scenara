from __future__ import annotations

import asyncio
from typing import Any

from scenara.platform.models import RunRecord
from scenara.platform.queue import RunHandler


class InlineRunQueue:
    def __init__(self) -> None:
        self._handler: RunHandler | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    def set_handler(self, handler: RunHandler) -> None:
        self._handler = handler

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def enqueue(self, run: RunRecord) -> None:
        if self._handler is None:
            raise RuntimeError("inline run queue handler is not configured")
        task = asyncio.create_task(
            self._handler(run.tenant_id, run.project_id, run.run_id),
            name=f"scenara:{run.run_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


class RedisRunQueue:
    def __init__(self, redis_url: str, *, stream: str = "scenara:runs", group: str = "scenara-workers") -> None:
        try:
            import redis.asyncio as redis
        except ImportError as exc:  # pragma: no cover - optional production dependency
            raise RuntimeError("redis is required for the Redis run queue") from exc
        self._redis_module = redis
        self._url = redis_url
        self._stream = stream
        self._group = group
        self._client: Any = None
        self._handler: RunHandler | None = None

    def set_handler(self, handler: RunHandler) -> None:
        self._handler = handler

    async def open(self) -> None:
        self._client = self._redis_module.from_url(self._url, decode_responses=True)
        try:
            await self._client.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def enqueue(self, run: RunRecord) -> None:
        if self._client is None:
            raise RuntimeError("Redis run queue is not open")
        await self._client.xadd(
            self._stream,
            {
                "tenant_id": run.tenant_id,
                "project_id": run.project_id,
                "run_id": run.run_id,
                "priority": str(run.priority),
            },
            maxlen=100_000,
            approximate=True,
        )

    async def consume_forever(self, *, consumer: str, block_ms: int = 5_000) -> None:
        if self._client is None:
            raise RuntimeError("Redis run queue is not open")
        if self._handler is None:
            raise RuntimeError("Redis run queue handler is not configured")
        while True:
            messages = await self._client.xreadgroup(
                self._group,
                consumer,
                {self._stream: ">"},
                count=1,
                block=block_ms,
            )
            for _stream_name, entries in messages:
                for message_id, fields in entries:
                    try:
                        await self._handler(fields["tenant_id"], fields["project_id"], fields["run_id"])
                    except Exception:
                        # Keep the message pending for explicit operational replay.
                        raise
                    else:
                        await self._client.xack(self._stream, self._group, message_id)


__all__ = ["InlineRunQueue", "RedisRunQueue"]
