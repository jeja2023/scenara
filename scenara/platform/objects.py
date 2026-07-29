from __future__ import annotations

import re
from typing import Protocol

SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


class ObjectStore(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def put(self, object_key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, object_key: str) -> bytes: ...

    async def delete(self, object_key: str) -> bool: ...


def validate_object_key(object_key: str) -> str:
    parts = object_key.split("/")
    if not parts or any(not SAFE_COMPONENT.fullmatch(part) for part in parts):
        raise ValueError("invalid object key")
    return object_key


__all__ = ["ObjectStore", "validate_object_key"]
