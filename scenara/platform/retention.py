from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    raw_media_days: int = 7
    preview_days: int = 30
    structured_result_days: int = 180
    biometric_days: int | None = None
    alert_snapshot_days: int | None = 30

    def validate(self) -> None:
        for name, value in (
            ("raw_media_days", self.raw_media_days),
            ("preview_days", self.preview_days),
            ("structured_result_days", self.structured_result_days),
        ):
            if value < 1 or value > 3650:
                raise ValueError(f"{name} must be between 1 and 3650")
        if self.biometric_days is not None and not 1 <= self.biometric_days <= 3650:
            raise ValueError("biometric_days must be null or between 1 and 3650")
        if self.alert_snapshot_days is not None and not 1 <= self.alert_snapshot_days <= 3650:
            raise ValueError("alert_snapshot_days must be null or between 1 and 3650")

    def expires_at(self, category: str, *, created_at: float | None = None) -> float | None:
        self.validate()
        base = created_at if created_at is not None else time.time()
        days = {
            "raw_media": self.raw_media_days,
            "preview": self.preview_days,
            "structured_result": self.structured_result_days,
            "biometric": self.biometric_days,
            "alert_snapshot": self.alert_snapshot_days,
        }.get(category)
        if category not in {"raw_media", "preview", "structured_result", "biometric", "alert_snapshot"}:
            raise ValueError(f"unknown retention category: {category}")
        return None if days is None else base + days * 86_400


class RetentionSweepPort(Protocol):
    async def expired_object_keys(self, before: float, limit: int) -> list[str]: ...

    async def mark_objects_deleted(self, object_keys: list[str], deleted_at: float) -> None: ...


class RetentionScheduler:
    def __init__(self, state: RetentionSweepPort, objects: object) -> None:
        self._state = state
        self._objects = objects

    async def sweep(self, *, before: float | None = None, limit: int = 1000) -> int:
        if not 1 <= limit <= 10_000:
            raise ValueError("retention sweep limit must be between 1 and 10000")
        cutoff = time.time() if before is None else before
        keys = await self._state.expired_object_keys(cutoff, limit)
        deleted: list[str] = []
        for key in keys:
            if await self._objects.delete(key):  # type: ignore[attr-defined]
                deleted.append(key)
        if deleted:
            await self._state.mark_objects_deleted(deleted, time.time())
        return len(deleted)


__all__ = ["RetentionPolicy", "RetentionScheduler", "RetentionSweepPort"]
