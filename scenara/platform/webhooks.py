from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from dataclasses import dataclass
from typing import Any

import httpx

from scenara.platform.network import validate_external_url


class WebhookDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WebhookEndpoint:
    endpoint_id: str
    url: str
    secret: str
    event_types: frozenset[str]
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class WebhookReceipt:
    endpoint_id: str
    event_id: str
    attempt: int
    status_code: int
    delivered_at: float


def sign_webhook(secret: str, timestamp: int, body: bytes) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"v1={digest}"


class WebhookDeliveryService:
    def __init__(self, *, allow_private_targets: bool = False, timeout: float = 10.0) -> None:
        self._allow_private_targets = allow_private_targets
        self._timeout = timeout

    async def deliver(
        self,
        endpoint: WebhookEndpoint,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        max_attempts: int = 5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> WebhookReceipt:
        if not endpoint.enabled or event_type not in endpoint.event_types:
            raise WebhookDeliveryError("webhook endpoint is not subscribed to this event")
        await validate_external_url(
            endpoint.url, allowed_schemes=frozenset({"https"}), allow_private=self._allow_private_targets
        )
        occurred_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        body = json.dumps(
            {
                "schema_version": "1.0",
                "event_id": event_id,
                "event_type": event_type,
                "event_version": "1.0",
                "occurred_at": occurred_at,
                "producer": "scenara",
                "tenant_id": str(payload.get("tenant_id") or "unknown"),
                "project_id": str(payload.get("project_id") or "unknown"),
                "request_id": str(payload.get("request_id") or event_id),
                "trace_id": str(payload.get("trace_id") or event_id),
                "data": payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        async with httpx.AsyncClient(timeout=self._timeout, transport=transport, follow_redirects=False) as client:
            last_status = 0
            last_error: httpx.HTTPError | None = None
            for attempt in range(1, max_attempts + 1):
                timestamp = int(time.time())
                try:
                    response = await client.post(
                        endpoint.url,
                        content=body,
                        headers={
                            "Content-Type": "application/json",
                            "Scenara-Event-Id": event_id,
                            "Scenara-Timestamp": str(timestamp),
                            "Scenara-Signature": sign_webhook(endpoint.secret, timestamp, body),
                        },
                    )
                    last_status = response.status_code
                    if 200 <= response.status_code < 300:
                        return WebhookReceipt(
                            endpoint.endpoint_id, event_id, attempt, response.status_code, time.time()
                        )
                    if 400 <= response.status_code < 500 and response.status_code not in {408, 409, 425, 429}:
                        break
                except httpx.HTTPError as exc:
                    last_error = exc
                if attempt < max_attempts:
                    await asyncio.sleep(min(30.0, 0.25 * (2 ** (attempt - 1))))
        detail = f"HTTP {last_status}" if last_status else f"{type(last_error).__name__}: {last_error}"
        raise WebhookDeliveryError(f"webhook delivery failed after {max_attempts} attempts: {detail}")


__all__ = [
    "WebhookDeliveryError",
    "WebhookDeliveryService",
    "WebhookEndpoint",
    "WebhookReceipt",
    "sign_webhook",
]
