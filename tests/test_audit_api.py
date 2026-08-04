import httpx
import pytest

from scenara.bootstrap import build_runtime
from scenara.server import create_app


@pytest.fixture
async def audit_client(development_settings):
    runtime = build_runtime(development_settings)
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        yield api


@pytest.mark.asyncio
async def test_audit_query_filters_and_exports(audit_client) -> None:
    api = audit_client
    created = await api.post("/api/v1/datasets", json={"name": "审计数据集"})
    assert created.status_code == 201, created.text

    listed = await api.get("/api/v1/audit/events", params={"action": "dataset.create"})
    assert listed.status_code == 200, listed.text
    payload = listed.json()["data"]
    assert payload["total"] == 1
    assert payload["items"][0]["action"] == "dataset.create"
    assert payload["items"][0]["resource_type"] == "dataset"

    exported_json = await api.get("/api/v1/audit/export", params={"format": "json", "action": "dataset.create"})
    assert exported_json.status_code == 200
    assert exported_json.headers["content-type"].startswith("application/json")
    assert "scenara-audit.json" in exported_json.headers["content-disposition"]
    assert exported_json.json()["items"][0]["action"] == "dataset.create"

    exported_csv = await api.get("/api/v1/audit/export", params={"format": "csv", "resource_type": "dataset"})
    assert exported_csv.status_code == 200
    assert "scenara-audit.csv" in exported_csv.headers["content-disposition"]
    assert "event_id,created_at,principal_id,action" in exported_csv.text
    assert "dataset.create" in exported_csv.text


@pytest.mark.asyncio
async def test_audit_events_are_tenant_scoped(audit_client) -> None:
    api = audit_client
    headers = {"X-Tenant-Id": "tenant-a", "X-Project-Id": "project-a", "X-Principal-Id": "operator-a"}
    created = await api.post("/api/v1/datasets", headers=headers, json={"name": "租户数据集"})
    assert created.status_code == 201

    own = await api.get("/api/v1/audit/events", headers=headers, params={"action": "dataset.create"})
    assert own.status_code == 200
    assert own.json()["data"]["total"] == 1

    other = await api.get(
        "/api/v1/audit/events",
        headers={"X-Tenant-Id": "tenant-b", "X-Project-Id": "project-b", "X-Principal-Id": "operator-b"},
        params={"action": "dataset.create"},
    )
    assert other.status_code == 200
    assert other.json()["data"]["total"] == 0
