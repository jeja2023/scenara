from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from scenara.bootstrap import build_runtime
from scenara.server import create_app


def event_payload() -> dict[str, object]:
    return {
        "event_id": "evt_data_1",
        "event_type": "dataset.version.published",
        "event_version": "1.0",
        "occurred_at": "2026-08-16T04:00:00Z",
        "producer": "scenara-data",
        "tenant_id": "default",
        "project_id": "default",
        "request_id": "req-data-event",
        "trace_id": "0123456789abcdef0123456789abcdef",
        "data": {"dataset_id": "dst_1", "dataset_version_id": "dsv_1"},
    }


def event_headers(token: str = "data-event-token") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": "evt_data_1",
        "X-Scenara-Tenant-Id": "default",
        "X-Scenara-Project-Id": "default",
        "X-Request-Id": "req-data-event",
    }


@pytest.mark.asyncio
async def test_data_event_receiver_is_authenticated_audited_and_idempotent(development_settings) -> None:
    runtime = build_runtime(replace(development_settings, data_event_service_token="data-event-token"))
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://core") as api:
        rejected = await api.post(
            "/internal/v1/data/events", json=event_payload(), headers=event_headers("wrong-token")
        )
        accepted = await api.post(
            "/internal/v1/data/events", json=event_payload(), headers=event_headers()
        )
        replay = await api.post(
            "/internal/v1/data/events", json=event_payload(), headers=event_headers()
        )
        changed = event_payload()
        changed["data"] = {"dataset_id": "dst_changed"}
        conflict = await api.post(
            "/internal/v1/data/events", json=changed, headers=event_headers()
        )

    assert rejected.status_code == 401
    assert accepted.status_code == 202
    assert accepted.json() == {"accepted": True, "event_id": "evt_data_1"}
    assert replay.status_code == 200
    assert replay.json() == {"accepted": False, "event_id": "evt_data_1"}
    assert conflict.status_code == 409
    audits = await runtime.state.audit_events("default", "default", limit=None)
    received = [item for item in audits if item.action == "data.event.dataset.version.published"]
    assert len(received) == 1
    assert received[0].evidence["event_id"] == "evt_data_1"
    assert received[0].resource_id == "dsv_1"
    await runtime.close()


@pytest.mark.asyncio
async def test_data_event_receiver_rejects_header_scope_mismatch(development_settings) -> None:
    runtime = build_runtime(replace(development_settings, data_event_service_token="data-event-token"))
    app = create_app(runtime=runtime)
    headers = event_headers()
    headers["X-Scenara-Tenant-Id"] = "other"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://core") as api:
        response = await api.post("/internal/v1/data/events", json=event_payload(), headers=headers)
    assert response.status_code == 400
    await runtime.close()
