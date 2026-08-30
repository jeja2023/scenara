from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
RetentionCategory = Literal["raw_media", "preview", "structured_result", "alert_snapshot", "pending_upload", "secret"]


class ObjectStoreError(RuntimeError):
    pass


class ObjectAlreadyExistsError(ObjectStoreError):
    """Raised when an immutable object key already contains different bytes."""


class ObjectIntegrityError(ObjectStoreError):
    """Raised when object bytes do not match their declared SHA-256 digest."""


class ObjectStoreCapabilityError(ObjectStoreError):
    """Raised when a provider does not implement an optional object capability."""


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    object_key: str
    size_bytes: int
    sha256: str
    content_type: str
    version_id: str | None = None
    retention_category: RetentionCategory | None = None


@dataclass(frozen=True, slots=True)
class PresignedObjectRequest:
    url: str
    method: Literal["GET", "PUT"]
    headers: dict[str, str]
    expires_at: float


class ObjectStore(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def health_check(self) -> None: ...

    async def put(
        self,
        object_key: str,
        data: bytes,
        content_type: str,
        *,
        sha256: str | None = None,
        overwrite: bool = False,
        retention_category: RetentionCategory | None = None,
    ) -> ObjectMetadata: ...

    async def put_file(
        self,
        object_key: str,
        path: Path,
        content_type: str,
        *,
        sha256: str | None = None,
        overwrite: bool = False,
        retention_category: RetentionCategory | None = None,
    ) -> ObjectMetadata: ...

    async def stat(self, object_key: str, *, expected_sha256: str | None = None) -> ObjectMetadata: ...

    async def get(self, object_key: str, *, expected_sha256: str | None = None) -> bytes: ...

    async def get_to_file(
        self, object_key: str, path: Path, *, expected_sha256: str | None = None
    ) -> ObjectMetadata: ...

    async def verify(self, object_key: str, expected_sha256: str) -> ObjectMetadata: ...

    async def exists(self, object_key: str) -> bool: ...

    async def delete(self, object_key: str) -> bool: ...

    async def set_retention_category(
        self, object_key: str, category: RetentionCategory
    ) -> None: ...

    async def presign_upload(
        self,
        object_key: str,
        *,
        content_type: str,
        sha256: str,
        size_bytes: int,
        expires_in: int,
        retention_category: RetentionCategory,
    ) -> PresignedObjectRequest: ...

    async def presign_download(
        self,
        object_key: str,
        *,
        expires_in: int,
        filename: str | None = None,
    ) -> PresignedObjectRequest: ...


def validate_object_key(object_key: str) -> str:
    parts = object_key.split("/")
    if not parts or any(not SAFE_COMPONENT.fullmatch(part) for part in parts):
        raise ValueError("invalid object key")
    return object_key


def validate_sha256(value: str) -> str:
    normalized = value.strip().lower()
    if not SHA256_PATTERN.fullmatch(normalized):
        raise ValueError("sha256 must contain exactly 64 lowercase hexadecimal characters")
    return normalized


__all__ = [
    "ObjectAlreadyExistsError",
    "ObjectIntegrityError",
    "ObjectMetadata",
    "ObjectStore",
    "ObjectStoreCapabilityError",
    "ObjectStoreError",
    "PresignedObjectRequest",
    "RetentionCategory",
    "validate_object_key",
    "validate_sha256",
]
