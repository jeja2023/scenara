from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from PIL import Image

from scenara.bootstrap import build_runtime
from scenara.server import create_app


class FixedOcrEngine:
    model_id = "test-ocr"
    version = "1.0.0"

    def predict(self, image: Any) -> list[dict[str, Any]]:
        assert image.size == (32, 24)
        return [
            {
                "text": "Scenara 景枢",
                "score": 0.99,
                "polygon": [[1, 1], [30, 1], [30, 10], [1, 10]],
            }
        ]


def image_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (32, 24), "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
async def client(development_settings):
    runtime = build_runtime(development_settings, ocr_engine=FixedOcrEngine())
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        yield api, runtime


async def upload_image(api: httpx.AsyncClient) -> str:
    response = await api.post(
        "/api/v1/media/assets",
        files={"file": ("sample.png", image_bytes(), "image/png")},
        data={"kind": "image"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["asset_id"]


@pytest.mark.asyncio
async def test_ocr_run_is_idempotent_and_returns_typed_result(client) -> None:
    api, _ = client
    asset_id = await upload_image(api)
    body = {
        "domain": "ocr",
        "pipeline": {"pipeline_id": "ocr.document", "version": "0.1.0"},
        "asset_id": asset_id,
        "wait_ms": 2000,
    }
    first = await api.post("/api/v1/runs", json=body, headers={"Idempotency-Key": "ocr-1"})
    assert first.status_code == 202, first.text
    first_run = first.json()["data"]
    assert first_run["status"] == "completed"

    replay = await api.post("/api/v1/runs", json=body, headers={"Idempotency-Key": "ocr-1"})
    assert replay.status_code == 200
    assert replay.json()["data"]["run_id"] == first_run["run_id"]

    result = await api.get(f"/api/v1/runs/{first_run['run_id']}/result")
    assert result.status_code == 200
    payload = result.json()["data"]["result"]["domain_payload"]
    assert payload["domain"] == "ocr"
    assert payload["text"] == "Scenara 景枢"
    assert payload["blocks"][0]["reading_order"] == 0


@pytest.mark.asyncio
async def test_idempotency_key_rejects_different_request(client) -> None:
    api, _ = client
    asset_id = await upload_image(api)
    body = {
        "domain": "ocr",
        "pipeline": {"pipeline_id": "ocr.document", "version": "0.1.0"},
        "asset_id": asset_id,
        "wait_ms": 2000,
    }
    assert (await api.post("/api/v1/runs", json=body, headers={"Idempotency-Key": "same"})).status_code == 202
    body["priority"] = 10
    conflict = await api.post("/api/v1/runs", json=body, headers={"Idempotency-Key": "same"})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "STATE_CONFLICT"


@pytest.mark.asyncio
async def test_portrait_pipeline_uses_production_model_adapter(client, monkeypatch: pytest.MonkeyPatch) -> None:
    api, _ = client

    async def fake_runtime(capability: str, adapters: set[str]):
        assert capability == "person_detection"
        assert "yolo" in adapters
        return SimpleNamespace(
            bundle={},
            cache_key="models/test-person",
            model_id="models/test-person",
            version="1.2.3",
            capability={},
            config={},
        )

    async def fake_infer(*args: Any, **kwargs: Any):
        del args, kwargs
        return (
            [{"persons": [{"box": [2, 3, 22, 20], "score": 0.98}], "person_count": 1}],
            {"timing": {"inference_seconds": 0.01}},
        )

    monkeypatch.setattr("app.portrait_model_runtime_capability.get_capability_runtime", fake_runtime)
    monkeypatch.setattr("app.inference_detection.infer_person_frames", fake_infer)
    asset_id = await upload_image(api)
    body = {
        "domain": "portrait",
        "pipeline": {"pipeline_id": "portrait.person-detection", "version": "0.1.0"},
        "asset_id": asset_id,
        "wait_ms": 2000,
    }
    created = await api.post("/api/v1/runs", json=body, headers={"Idempotency-Key": "portrait-1"})
    assert created.status_code == 202, created.text
    run = created.json()["data"]
    assert run["status"] == "completed", run
    result = await api.get(f"/api/v1/runs/{run['run_id']}/result")
    person = result.json()["data"]["result"]["domain_payload"]["persons"][0]
    assert person["bbox"] == {"x": 2.0, "y": 3.0, "width": 20.0, "height": 17.0}


@pytest.mark.asyncio
async def test_tenant_scope_hides_assets(client) -> None:
    api, _ = client
    asset_id = await upload_image(api)
    response = await api.get(f"/api/v1/media/assets/{asset_id}", headers={"X-Tenant-Id": "another"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_console_bundle_is_served_with_spa_fallback(
    development_settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import scenara.server as server_module

    console_dist = tmp_path / "console"
    (console_dist / "assets").mkdir(parents=True)
    (console_dist / "index.html").write_text(
        "<!doctype html><html><head><title>Scenara 景枢</title></head><body>控制台</body></html>",
        encoding="utf-8",
    )
    (console_dist / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    monkeypatch.setattr(server_module, "CONSOLE_DIST", console_dist)
    app = create_app(runtime=build_runtime(development_settings))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as api:
        redirect = await api.get("/")
        assert redirect.status_code == 307
        assert redirect.headers["location"] == "/console/"
        console = await api.get("/console/media")
        assert console.status_code == 200
        assert "Scenara 景枢" in console.text
        assert "frame-ancestors 'none'" in console.headers["content-security-policy"]
        assert (await api.get("/console/favicon.svg")).status_code == 200


def test_openapi_exposes_domain_union(development_settings) -> None:
    schema = create_app(runtime=build_runtime(development_settings, ocr_engine=FixedOcrEngine())).openapi()
    components = schema["components"]["schemas"]
    result_schema = components["ResultEnvelope"]
    domain_payload = result_schema["properties"]["domain_payload"]
    assert domain_payload["discriminator"]["propertyName"] == "domain"
    assert len(domain_payload["oneOf"]) == 2


@pytest.mark.asyncio
async def test_pipeline_and_model_catalog_endpoints_use_state_store(client) -> None:
    api, runtime = client
    pipelines = await api.get("/api/v1/pipelines")
    assert pipelines.status_code == 200
    assert {item["pipeline_id"] for item in pipelines.json()["data"]} == {
        "ocr.document",
        "portrait.analysis",
        "portrait.person-detection",
    }
    assert len(await runtime.state.list_pipeline_definitions()) == 3
    models = await api.get("/api/v1/models")
    assert models.status_code == 200
    assert models.json()["data"] == []


@pytest.mark.asyncio
async def test_webhook_subscription_outbox_delivery_and_secret_cleanup(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, runtime = client

    async def allow_target(url: str, **kwargs: object) -> str:
        del kwargs
        return url

    monkeypatch.setattr("scenara.platform.webhook_service.validate_external_url", allow_target)
    created = await api.post(
        "/api/v1/webhooks/subscriptions",
        json={
            "name": "result sink",
            "url": "https://events.example.test/scenara",
            "secret": "webhook-test-secret-1234",
            "event_types": ["result.available"],
        },
    )
    assert created.status_code == 201, created.text
    endpoint = created.json()["data"]
    assert "secret" not in created.text
    stored_endpoint = await runtime.state.get_webhook_subscription(
        "default", "default", endpoint["endpoint_id"]
    )
    assert stored_endpoint is not None

    asset_id = await upload_image(api)
    run = await api.post(
        "/api/v1/runs",
        json={
            "domain": "ocr",
            "pipeline": {"pipeline_id": "ocr.document", "version": "0.1.0"},
            "asset_id": asset_id,
            "wait_ms": 2000,
        },
        headers={"Idempotency-Key": "webhook-outbox"},
    )
    assert run.status_code == 202
    pending = await api.get("/api/v1/webhooks/deliveries")
    assert pending.json()["data"][0]["status"] == "pending"

    sent: list[tuple[str, str, str]] = []

    class Sender:
        async def deliver(self, target, event_id, event_type, payload, *, max_attempts=5):
            del payload, max_attempts
            sent.append((target.secret, event_id, event_type))
            return SimpleNamespace(status_code=204)

    runtime.webhooks._sender = Sender()
    assert await runtime.webhooks.deliver_due() == (1, 0)
    delivered = await api.get("/api/v1/webhooks/deliveries")
    assert delivered.json()["data"][0]["status"] == "delivered"
    assert sent[0][0] == "webhook-test-secret-1234"
    assert sent[0][2] == "result.available"

    deleted = await api.delete(f"/api/v1/webhooks/subscriptions/{endpoint['endpoint_id']}")
    assert deleted.status_code == 204
    from scenara.platform.secrets import SecretNotFound

    with pytest.raises(SecretNotFound):
        await runtime.secrets.get(stored_endpoint.secret_ref)


@pytest.mark.asyncio
async def test_pipeline_transition_is_persisted_and_retired_version_rejects_new_run(client) -> None:
    api, runtime = client
    retired = await api.post(
        "/api/v1/pipelines/ocr.document/versions/0.1.0/transition",
        json={"status": "retired"},
    )
    assert retired.status_code == 200, retired.text
    assert retired.json()["data"]["status"] == "retired"
    persisted = await runtime.state.get_pipeline_definition("ocr.document", "0.1.0")
    assert persisted is not None and persisted.status.value == "retired"

    asset_id = await upload_image(api)
    rejected = await api.post(
        "/api/v1/runs",
        json={
            "domain": "ocr",
            "pipeline": {"pipeline_id": "ocr.document", "version": "0.1.0"},
            "asset_id": asset_id,
        },
        headers={"Idempotency-Key": "retired-pipeline"},
    )
    assert rejected.status_code == 422
    assert "pipeline is not active" in rejected.text
