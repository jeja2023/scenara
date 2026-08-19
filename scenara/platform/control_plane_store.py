"""Persistence contracts and the in-memory control-plane implementation."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from scenara.platform.models import PrincipalContext


class ControlPlaneStore(Protocol):
    async def get(self, kind: str, tenant_id: str, project_id: str, record_id: str) -> dict[str, Any] | None: ...

    async def list(self, kind: str, tenant_id: str, project_id: str) -> list[dict[str, Any]]: ...

    async def get_by_token_sha256(self, token_sha256: str) -> dict[str, Any] | None: ...

    async def delete_expired_sessions(self, now: float) -> int: ...

    async def put(
        self, kind: str, tenant_id: str, project_id: str, record_id: str, document: dict[str, Any]
    ) -> None: ...

    async def delete(self, kind: str, tenant_id: str, project_id: str, record_id: str) -> None: ...

    async def adjust_quota_usage(
        self,
        tenant_id: str,
        project_id: str,
        record_id: str,
        *,
        window_seconds: float,
        now: float,
        amount: int,
        limit: int | None,
    ) -> tuple[dict[str, Any], bool]:
        """Atomically add ``amount`` to a quota usage record inside its window.

        Returns the resulting usage document and whether the increment was
        allowed.  A denied increment leaves the stored usage unchanged, so
        concurrent requests can never overshoot the configured limit.
        """


class SessionAccessResolver(Protocol):
    async def resolve_user_context(self, tenant_id: str, project_id: str, user_id: str) -> PrincipalContext | None: ...


class AuditRetentionStore(Protocol):
    async def delete_audit_events_before(self, tenant_id: str, project_id: str, before: float) -> int: ...


class MemoryControlPlaneStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self._session_tokens: dict[str, tuple[str, str, str, str]] = {}
        self._quota_lock = asyncio.Lock()

    async def get(self, kind: str, tenant_id: str, project_id: str, record_id: str) -> dict[str, Any] | None:
        value = self._records.get((kind, tenant_id, project_id, record_id))
        return dict(value) if value is not None else None

    async def list(self, kind: str, tenant_id: str, project_id: str) -> list[dict[str, Any]]:
        values = [
            dict(value)
            for (row_kind, row_tenant, row_project, _), value in self._records.items()
            if row_kind == kind
            and (tenant_id == "*" or row_tenant == tenant_id)
            and (project_id == "*" or row_project == project_id)
        ]
        return sorted(
            values, key=lambda item: (float(item.get("updated_at", 0)), str(item.get("record_id", ""))), reverse=True
        )

    async def get_by_token_sha256(self, token_sha256: str) -> dict[str, Any] | None:
        key = self._session_tokens.get(token_sha256)
        value = self._records.get(key) if key is not None else None
        return dict(value) if value is not None else None

    async def delete_expired_sessions(self, now: float) -> int:
        expired = [
            (kind, tenant_id, project_id, record_id)
            for (kind, tenant_id, project_id, record_id), document in self._records.items()
            if kind == "session" and float(document.get("expires_at", 0)) <= now
        ]
        for key in expired:
            await self.delete(*key)
        return len(expired)

    async def put(self, kind: str, tenant_id: str, project_id: str, record_id: str, document: dict[str, Any]) -> None:
        previous = self._records.get((kind, tenant_id, project_id, record_id))
        if kind == "session" and previous is not None:
            previous_digest = previous.get("token_sha256")
            if isinstance(previous_digest, str):
                self._session_tokens.pop(previous_digest, None)
        self._records[(kind, tenant_id, project_id, record_id)] = dict(document)
        if kind == "session":
            digest = document.get("token_sha256")
            if isinstance(digest, str):
                self._session_tokens[digest] = (kind, tenant_id, project_id, record_id)

    async def delete(self, kind: str, tenant_id: str, project_id: str, record_id: str) -> None:
        removed = self._records.pop((kind, tenant_id, project_id, record_id), None)
        if kind == "session" and removed is not None:
            digest = removed.get("token_sha256")
            if isinstance(digest, str):
                self._session_tokens.pop(digest, None)

    async def adjust_quota_usage(
        self,
        tenant_id: str,
        project_id: str,
        record_id: str,
        *,
        window_seconds: float,
        now: float,
        amount: int,
        limit: int | None,
    ) -> tuple[dict[str, Any], bool]:
        key = ("quota_usage", tenant_id, project_id, record_id)
        async with self._quota_lock:
            existing = self._records.get(key)
            started = now
            used = 0
            if existing is not None:
                existing_started = float(existing.get("window_started_at", now))
                if now < existing_started + window_seconds:
                    started = existing_started
                    used = int(existing.get("used", 0))
            next_used = used + amount
            allowed = limit is None or next_used <= limit
            if allowed:
                document = {"record_id": record_id, "used": next_used, "window_started_at": started, "updated_at": now}
                self._records[key] = dict(document)
                return document, True
            return {"record_id": record_id, "used": used, "window_started_at": started, "updated_at": now}, False


__all__ = [
    "AuditRetentionStore",
    "ControlPlaneStore",
    "MemoryControlPlaneStore",
    "SessionAccessResolver",
]
