from __future__ import annotations

from types import SimpleNamespace

import pytest

import scenara.scheduler as scheduler_module
import scenara.worker as worker_module


class FakeQueue:
    def __init__(self, calls: list[object]) -> None:
        self.calls = calls

    async def consume_forever(self, *, consumer: str, lane: str) -> None:
        self.calls.append(("consume", consumer, lane))


class FakeRuntime:
    def __init__(self, calls: list[object]) -> None:
        self.calls = calls
        self.queue = FakeQueue(calls)
        self.state = SimpleNamespace(expired_object_keys=True)
        self.objects = object()
        self.features = SimpleNamespace(delete_expired=self.delete_expired)
        self.webhooks = SimpleNamespace(deliver_due=self.deliver_due)

    async def open(self) -> None:
        self.calls.append("open")

    async def close(self) -> None:
        self.calls.append("close")

    async def delete_expired(self, before: float, limit: int) -> int:
        assert before > 0
        assert limit == 1000
        self.calls.append("features")
        return 2

    async def deliver_due(self) -> tuple[int, int]:
        self.calls.append("webhooks")
        return 3, 1


@pytest.mark.asyncio
async def test_worker_opens_consumes_and_closes_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    runtime = FakeRuntime(calls)
    monkeypatch.setattr(worker_module, "RedisRunQueue", FakeQueue)
    monkeypatch.setattr(worker_module, "build_runtime", lambda: runtime)

    await worker_module.run_worker("worker-a", "stream")

    assert calls == ["open", ("consume", "worker-a", "stream"), "close"]


@pytest.mark.asyncio
async def test_scheduler_runs_all_governance_tasks_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    runtime = FakeRuntime(calls)

    class FakeRetentionScheduler:
        def __init__(self, state: object, objects: object) -> None:
            assert state is runtime.state
            assert objects is runtime.objects

        async def sweep(self) -> int:
            calls.append("retention")
            return 4

    monkeypatch.setattr(scheduler_module, "build_runtime", lambda: runtime)
    monkeypatch.setattr(scheduler_module, "RetentionScheduler", FakeRetentionScheduler)

    assert await scheduler_module.run_once() == (4, 2, 3, 1)
    assert calls == ["open", "retention", "features", "webhooks", "close"]


@pytest.mark.asyncio
async def test_runtime_processes_close_after_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    class FailingQueue(FakeQueue):
        async def consume_forever(self, *, consumer: str, lane: str) -> None:
            del consumer, lane
            raise RuntimeError("queue failed")

    runtime = FakeRuntime(calls)
    runtime.queue = FailingQueue(calls)
    monkeypatch.setattr(worker_module, "RedisRunQueue", FakeQueue)
    monkeypatch.setattr(worker_module, "build_runtime", lambda: runtime)

    with pytest.raises(RuntimeError, match="queue failed"):
        await worker_module.run_worker("worker-a", "batch")
    assert calls == ["open", "close"]
