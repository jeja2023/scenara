import httpx
import pytest

from scenara.bootstrap import build_runtime
from scenara.server import create_app


@pytest.fixture
async def saved_search_client(development_settings):
    runtime = build_runtime(development_settings)
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        yield api


@pytest.mark.asyncio
async def test_saved_text_search_lifecycle(saved_search_client) -> None:
    api = saved_search_client
    created = await api.post(
        "/api/v1/search/saved",
        json={
            "name": "合同编号查询",
            "description": "常用 OCR 查询",
            "mode": "text",
            "definition": {"query": "合同编号", "media_kinds": ["document"], "limit": 20},
        },
    )
    assert created.status_code == 201, created.text
    saved_id = created.json()["data"]["saved_search_id"]

    listed = await api.get("/api/v1/search/saved")
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1

    updated = await api.patch(
        f"/api/v1/search/saved/{saved_id}",
        json={"description": "更新后的查询"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["description"] == "更新后的查询"

    executed = await api.post(f"/api/v1/search/saved/{saved_id}/run")
    assert executed.status_code == 200, executed.text
    assert executed.json()["data"]["mode"] == "text"

    deleted = await api.delete(f"/api/v1/search/saved/{saved_id}")
    assert deleted.status_code == 204
    missing = await api.get(f"/api/v1/search/saved/{saved_id}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "SAVED_SEARCH_NOT_FOUND"


@pytest.mark.asyncio
async def test_saved_search_rejects_invalid_definition(saved_search_client) -> None:
    response = await saved_search_client.post(
        "/api/v1/search/saved",
        json={"name": "无效", "mode": "text", "definition": {"limit": 20}},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SAVED_SEARCH_CONFLICT"
