import json
import logging
import os
import re
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from scenara.platform.log_context import (
    current_request_id as _current_request_id,
    current_tenant_id as _current_tenant_id,
    current_traceparent as _current_traceparent,
    reset_log_context as _reset_log_context,
    set_log_context as _set_log_context,
)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        traceparent = current_traceparent()
        trace_id = traceparent.split("-")[1] if traceparent and len(traceparent.split("-")) == 4 else None
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "service": "scenara",
            "module": record.name,
            "request_id": current_request_id(),
            "trace_id": trace_id,
            "message": record.getMessage(),
        }
        tenant_id = current_tenant_id()
        if tenant_id:
            payload["tenant_id"] = tenant_id
        if traceparent:
            payload["traceparent"] = traceparent
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("gpu-worker")
for handler in logging.getLogger().handlers:
    handler.setFormatter(JsonLogFormatter())
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TRACEPARENT_PATTERN = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")
REQUEST_ID_CONTEXT: ContextVar[str | None] = ContextVar("request_id", default=None)
TENANT_ID_CONTEXT: ContextVar[str | None] = ContextVar("tenant_id", default=None)
SCHEDULING_SCOPE_CONTEXT: ContextVar[str | None] = ContextVar("scheduling_scope", default=None)
TRACEPARENT_CONTEXT: ContextVar[str | None] = ContextVar("traceparent", default=None)


def now() -> float:
    return time.perf_counter()


def wall_time() -> float:
    return time.time()


def normalize_request_id(raw_request_id: str | None) -> str | None:
    if raw_request_id is None or raw_request_id == "":
        return None
    if raw_request_id.strip() != raw_request_id:
        return None
    if not REQUEST_ID_PATTERN.fullmatch(raw_request_id):
        return None
    return raw_request_id


def request_id_from_headers(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id

    request_id = normalize_request_id(request.headers.get("x-request-id")) or str(uuid.uuid4())
    request.state.request_id = request_id
    return request_id


def traceparent_from_headers(request: Request) -> str | None:
    raw_traceparent = request.headers.get("traceparent")
    if raw_traceparent and TRACEPARENT_PATTERN.fullmatch(raw_traceparent.strip().lower()):
        traceparent_value = raw_traceparent.strip().lower()
        request.state.traceparent = traceparent_value
        return traceparent_value
    traceparent = getattr(request.state, "traceparent", None)
    return traceparent if isinstance(traceparent, str) else None


def current_request_id() -> str | None:
    return _current_request_id()


def current_tenant_id() -> str | None:
    return _current_tenant_id()


def current_scheduling_scope() -> str | None:
    return SCHEDULING_SCOPE_CONTEXT.get()


def current_traceparent() -> str | None:
    return _current_traceparent()


def set_log_context(
    *,
    request_id: str | None = None,
    tenant_id: str | None = None,
    traceparent: str | None = None,
) -> tuple[Token[str | None], Token[str | None], Token[str | None]]:
    return _set_log_context(request_id=request_id, tenant_id=tenant_id, traceparent=traceparent)


def reset_log_context(tokens: tuple[Token[str | None], Token[str | None], Token[str | None]]) -> None:
    _reset_log_context(tokens)


def log_json(level: int, event: str, **fields: Any) -> None:
    payload: dict[str, Any] = {"event": event, **fields}
    payload.setdefault("request_id", current_request_id())
    payload.setdefault("tenant_id", current_tenant_id())
    payload.setdefault("traceparent", current_traceparent())
    logger.log(
        level, json.dumps({key: value for key, value in payload.items() if value is not None}, ensure_ascii=False)
    )


@contextmanager
def trace_span(name: str, **attributes: Any) -> Iterator[None]:
    try:  # pragma: no cover - 可选的生产环境依赖
        from opentelemetry import trace
    except Exception:
        yield
        return
    tracer = trace.get_tracer("portrait-hub")
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        yield
