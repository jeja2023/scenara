from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


class ObjectStore(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def health_check(self) -> None: ...

    async def put(self, object_key: str, data: bytes, content_type: str) -> None: ...

    async def put_file(self, object_key: str, path: Path, content_type: str) -> None: ...

    async def get(self, object_key: str) -> bytes: ...

    async def get_to_file(self, object_key: str, path: Path) -> None: ...

    async def exists(self, object_key: str) -> bool: ...

    async def delete(self, object_key: str) -> bool: ...


def validate_object_key(object_key: str) -> str:
    parts = object_key.split("/")
    if not parts or any(not SAFE_COMPONENT.fullmatch(part) for part in parts):
        raise ValueError("invalid object key")
    return object_key


__all__ = ["ObjectStore", "validate_object_key"]
