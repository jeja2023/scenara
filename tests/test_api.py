from __future__ import annotations

from io import BytesIO
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
                "text": "Scenara 景析",
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
    assert payload["text"] == "Scenara 景析"
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


def test_openapi_exposes_domain_union(development_settings) -> None:
    schema = create_app(runtime=build_runtime(development_settings, ocr_engine=FixedOcrEngine())).openapi()
    components = schema["components"]["schemas"]
    result_schema = components["ResultEnvelope"]
    domain_payload = result_schema["properties"]["domain_payload"]
    assert domain_payload["discriminator"]["propertyName"] == "domain"
    assert len(domain_payload["oneOf"]) == 2
