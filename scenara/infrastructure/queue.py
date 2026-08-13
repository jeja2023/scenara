from __future__ import annotations

import asyncio
from collections.abc import Sequence
from importlib import import_module
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

    async def health_check(self) -> None:
        return None

    async def enqueue(self, run: RunRecord) -> None:
        if self._handler is None:
            raise RuntimeError("inline run queue handler is not configured")

        async def invoke() -> None:
            assert self._handler is not None
            await self._handler(run.tenant_id, run.project_id, run.run_id)

        task: asyncio.Task[None] = asyncio.create_task(invoke(), name=f"scenara:{run.run_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


class RedisRunQueue:
    def __init__(
        self,
        redis_url: str,
        *,
        stream: str = "scenara:runs",
        group: str = "scenara-workers",
        visibility_timeout_ms: int = 60_000,
    ) -> None:
        self._url = redis_url
        self._stream = stream
        self._group = group
        self._visibility_timeout_ms = max(1, visibility_timeout_ms)
        self._client: Any = None
        self._handler: RunHandler | None = None

    def set_handler(self, handler: RunHandler) -> None:
        self._handler = handler

    async def open(self) -> None:
        try:
            redis: Any = import_module("redis.asyncio")
        except ImportError as exc:  # pragma: no cover - optional production dependency
            raise RuntimeError("redis is required for the Redis run queue") from exc
        self._client = redis.from_url(self._url, decode_responses=True)
        for lane in ("batch", "stream"):
            try:
                await self._client.xgroup_create(
                    f"{self._stream}:{lane}",
                    f"{self._group}:{lane}",
                    id="0",
                    mkstream=True,
                )
            except Exception as exc:
                if "BUSYGROUP" not in str(exc):
                    raise

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> None:
        if self._client is None:
            raise RuntimeError("Redis run queue is not open")
        if not await self._client.ping():
            raise RuntimeError("Redis run queue ping failed")

    async def enqueue(self, run: RunRecord) -> None:
        if self._client is None:
            raise RuntimeError("Redis run queue is not open")
        await self._client.xadd(
            f"{self._stream}:{'stream' if run.source_id else 'batch'}",
            {
                "tenant_id": run.tenant_id,
                "project_id": run.project_id,
                "run_id": run.run_id,
                "priority": str(run.priority),
            },
            maxlen=100_000,
            approximate=True,
        )

    async def rebuild_empty(self, runs: Sequence[RunRecord]) -> int:
        """Atomically repopulate empty Run streams after verified Redis data loss."""
        if self._client is None:
            raise RuntimeError("Redis run queue is not open")
        streams = (f"{self._stream}:batch", f"{self._stream}:stream")
        pipeline = self._client.pipeline()
        try:
            await pipeline.watch(*streams)
            lengths = [await pipeline.xlen(stream) for stream in streams]
            if any(lengths):
                raise RuntimeError("Redis run streams must be empty before queue recovery")
            pipeline.multi()
            for run in runs:
                lane = "stream" if run.source_id else "batch"
                pipeline.xadd(
                    f"{self._stream}:{lane}",
                    {
                        "tenant_id": run.tenant_id,
                        "project_id": run.project_id,
                        "run_id": run.run_id,
                        "priority": str(run.priority),
                    },
                    maxlen=100_000,
                    approximate=True,
                )
            await pipeline.execute()
        except Exception as exc:
            if exc.__class__.__name__ == "WatchError":
                raise RuntimeError("Redis run streams changed during queue recovery") from exc
            raise
        finally:
            await pipeline.reset()
        return len(runs)

    async def _renew_lease(
        self,
        *,
        stream: str,
        group: str,
        consumer: str,
        message_id: str,
    ) -> None:
        delay_seconds = max(0.001, self._visibility_timeout_ms / 3_000)
        while True:
            await asyncio.sleep(delay_seconds)
            renewed = await self._client.xclaim(
                stream,
                group,
                consumer,
                0,
                [message_id],
                justid=True,
            )
            if message_id not in renewed:
                raise RuntimeError("Redis run queue lease was lost")

    async def _handle_message(
        self,
        *,
        stream: str,
        group: str,
        consumer: str,
        message_id: str,
        fields: dict[str, str],
    ) -> None:
        handler = self._handler
        if handler is None:
            raise RuntimeError("Redis run queue handler is not configured")
        lease_task = asyncio.create_task(
            self._renew_lease(
                stream=stream,
                group=group,
                consumer=consumer,
                message_id=message_id,
            ),
            name=f"scenara:lease:{message_id}",
        )
        try:
            await handler(fields["tenant_id"], fields["project_id"], fields["run_id"])
        except BaseException:
            lease_task.cancel()
            await asyncio.gather(lease_task, return_exceptions=True)
            raise
        lease_task.cancel()
        try:
            await lease_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            raise RuntimeError("Redis run queue lease renewal failed") from exc
        await self._client.xack(stream, group, message_id)

    async def consume_forever(
        self,
        *,
        consumer: str,
        lane: str = "batch",
        block_ms: int = 5_000,
    ) -> None:
        if self._client is None:
            raise RuntimeError("Redis run queue is not open")
        if self._handler is None:
            raise RuntimeError("Redis run queue handler is not configured")
        if lane not in {"batch", "stream"}:
            raise ValueError("queue lane must be batch or stream")
        stream = f"{self._stream}:{lane}"
        group = f"{self._group}:{lane}"
        while True:
            claimed = await self._client.xautoclaim(
                stream,
                group,
                consumer,
                self._visibility_timeout_ms,
                start_id="0-0",
                count=1,
            )
            claimed_entries = claimed[1] if len(claimed) > 1 else []
            if claimed_entries:
                messages = [(stream, claimed_entries)]
            else:
                messages = await self._client.xreadgroup(
                    group,
                    consumer,
                    {stream: ">"},
                    count=1,
                    block=block_ms,
                )
            for _stream_name, entries in messages:
                for message_id, fields in entries:
                    await self._handle_message(
                        stream=stream,
                        group=group,
                        consumer=consumer,
                        message_id=message_id,
                        fields=fields,
                    )


__all__ = ["InlineRunQueue", "RedisRunQueue"]
