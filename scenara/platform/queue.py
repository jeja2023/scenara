from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from scenara.platform.models import RunRecord

RunHandler = Callable[[str, str, str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class QueueLaneDepth:
    """Backlog and leased-message counts for one execution lane."""

    lag: int
    pending: int


class RunQueue(Protocol):
    def set_handler(self, handler: RunHandler) -> None: ...

    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def health_check(self) -> None: ...

    async def enqueue(self, run: RunRecord) -> None: ...

    async def depth(self) -> dict[str, QueueLaneDepth]: ...


__all__ = ["QueueLaneDepth", "RunHandler", "RunQueue"]
