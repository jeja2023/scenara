from __future__ import annotations

import re
import uuid
from contextvars import ContextVar, Token
from fastapi import Request

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TRACEPARENT_PATTERN = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")
REQUEST_ID_CONTEXT: ContextVar[str | None] = ContextVar("request_id", default=None)
TENANT_ID_CONTEXT: ContextVar[str | None] = ContextVar("tenant_id", default=None)
TRACEPARENT_CONTEXT: ContextVar[str | None] = ContextVar("traceparent", default=None)


def normalize_request_id(raw: str | None) -> str | None:
    if raw is None or raw.strip() != raw or not REQUEST_ID_PATTERN.fullmatch(raw):
        return None
    return raw


def traceparent_from_headers(request: Request) -> str | None:
    raw = request.headers.get("traceparent")
    if raw and TRACEPARENT_PATTERN.fullmatch(raw.strip().lower()):
        value = raw.strip().lower()
        request.state.traceparent = value
        return value
    state_value: object = getattr(request.state, "traceparent", None)
    return state_value if isinstance(state_value, str) else None


def current_request_id() -> str | None:
    return REQUEST_ID_CONTEXT.get()


def current_tenant_id() -> str | None:
    return TENANT_ID_CONTEXT.get()


def current_traceparent() -> str | None:
    return TRACEPARENT_CONTEXT.get()


def set_log_context(*, request_id: str | None, tenant_id: str | None, traceparent: str | None) -> tuple[Token[str | None], Token[str | None], Token[str | None]]:
    return (
        REQUEST_ID_CONTEXT.set(request_id),
        TENANT_ID_CONTEXT.set(tenant_id),
        TRACEPARENT_CONTEXT.set(traceparent),
    )


def reset_log_context(tokens: tuple[Token[str | None], Token[str | None], Token[str | None]]) -> None:
    REQUEST_ID_CONTEXT.reset(tokens[0])
    TENANT_ID_CONTEXT.reset(tokens[1])
    TRACEPARENT_CONTEXT.reset(tokens[2])


def new_traceparent() -> str:
    return f"00-{uuid.uuid4().hex}-{uuid.uuid4().hex[:16]}-01"


__all__ = [
    "current_request_id", "current_tenant_id", "current_traceparent",
    "new_traceparent", "reset_log_context", "set_log_context", "traceparent_from_headers",
]
