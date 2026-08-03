from __future__ import annotations

from typing import Any


def exception_log_summary(exc: Exception) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": type(exc).__name__}
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        payload["status_code"] = status_code
    detail = getattr(exc, "detail", None)
    if detail is not None:
        payload["detail_type"] = type(detail).__name__
    return payload


__all__ = ["exception_log_summary"]
