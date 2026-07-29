from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from scenara.platform.models import RunRecord

RunHandler = Callable[[str, str, str], Awaitable[None]]


class RunQueue(Protocol):
    def set_handler(self, handler: RunHandler) -> None: ...

    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def enqueue(self, run: RunRecord) -> None: ...


__all__ = ["RunHandler", "RunQueue"]
