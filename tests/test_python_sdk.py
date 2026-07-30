from __future__ import annotations

import json

import httpx
import pytest
from scenara_sdk import ScenaraClient, ScenaraError


def envelope(data: object) -> bytes:
    return json.dumps({"schema_version": "1.0", "request_id": "req-sdk", "data": data}).encode()


def test_python_sdk_context_lifecycle_and_domain_methods() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path.endswith("/preview"):
            return httpx.Response(200, content=b"jpeg-preview", headers={"Content-Type": "image/jpeg"})
        if request.url.path.endswith("/models"):
            return httpx.Response(200, content=envelope([]))
        if request.url.path.endswith("/webhooks/subscriptions") and request.method == "POST":
            return httpx.Response(201, content=envelope({"endpoint_id": "whk-1", "name": "sink"}))
        if request.url.path.endswith("/webhooks/subscriptions"):
            return httpx.Response(200, content=envelope([]))
        if request.url.path.endswith("/webhooks/deliveries"):
            return httpx.Response(200, content=envelope([]))
        if request.url.path.endswith("/pause"):
            return httpx.Response(200, content=envelope({"run_id": "run-1", "status": "pausing"}))
        if request.url.path.endswith("/portrait/search"):
            return httpx.Response(200, content=envelope({"feature_space_id": "face-v1", "matches": []}))
        if request.url.path.endswith("/enterprise/status"):
            return httpx.Response(200, content=envelope({"license_id": "lic-1"}))
        return httpx.Response(200, content=envelope({"items": [], "total": 0}))

    with ScenaraClient(
        "https://scenara.example",
        token="secret",
        tenant_id="tenant-a",
        project_id="project-a",
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.list_assets()["total"] == 0
        assert client.pause_run("run-1")["status"] == "pausing"
        assert client.search_portrait({"feature_space_id": "face-v1", "embedding": [1.0, 0.0]})["matches"] == []
        assert client.enterprise_status()["license_id"] == "lic-1"
        assert client.get_asset_preview("asset-1") == b"jpeg-preview"
        assert client.list_models() == []
        assert client.create_webhook_subscription(
            name="sink",
            url="https://events.example/scenara",
            secret="webhook-secret-1234",
            event_types=["result.available"],
        )["endpoint_id"] == "whk-1"
        assert client.list_webhook_subscriptions() == []
        assert client.list_webhook_deliveries() == []
        client.delete_asset("asset-1")
        client.delete_portrait_identity("identity-1")
        client.delete_webhook_subscription("whk-1")

    assert {request.method for request in requests} == {"GET", "POST", "DELETE"}
    for request in requests:
        assert request.headers["X-Tenant-Id"] == "tenant-a"
        assert request.headers["X-Project-Id"] == "project-a"
        assert request.headers["Authorization"] == "Bearer secret"


def test_python_sdk_preserves_api_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            403,
            json={
                "request_id": "req-denied",
                "error": {"code": "POLICY_DENIED", "message": "denied"},
            },
        )

    with (
        ScenaraClient(
            "https://scenara.example",
            transport=httpx.MockTransport(handler),
        ) as client,
        pytest.raises(ScenaraError) as caught,
    ):
        client.enterprise_status()
    assert caught.value.status_code == 403
    assert caught.value.code == "POLICY_DENIED"
    assert caught.value.request_id == "req-denied"


def test_python_sdk_feedback_and_model_release_methods() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path.endswith("/hard-sample-manifests"):
            return httpx.Response(201, content=envelope({"manifest_id": "hsm-1", "sha256": "a" * 64}))
        if path.endswith("/model-deployment-events"):
            return httpx.Response(200, content=envelope([]))
        if path.endswith("/model-releases") and request.method == "GET":
            return httpx.Response(200, content=envelope([]))
        if "/model-releases/" in path:
            return httpx.Response(200, content=envelope({"model_id": "portrait", "version": "1.0.0", "status": "active"}))
        if path.endswith("/model-releases"):
            return httpx.Response(201, content=envelope({"model_id": "portrait", "version": "1.0.0", "status": "candidate"}))
        if path.endswith("/review"):
            return httpx.Response(200, content=envelope({"feedback_id": "fbk-1", "status": "approved"}))
        if path.endswith("/feedback") and request.method == "GET":
            return httpx.Response(200, content=envelope([]))
        return httpx.Response(201, content=envelope({"feedback_id": "fbk-1", "status": "pending"}))

    with ScenaraClient("https://scenara.example", transport=httpx.MockTransport(handler)) as client:
        assert client.create_feedback({"kind": "false_negative"})["feedback_id"] == "fbk-1"
        assert client.list_feedback() == []
        assert client.review_feedback("fbk-1", status="approved")["status"] == "approved"
        assert client.create_hard_sample_manifest(
            dataset_id="portrait.hard-samples",
            version="1.0.0",
            feedback_ids=["fbk-1"],
        )["manifest_id"] == "hsm-1"
        assert client.create_model_release(
            {"model_id": "portrait", "version": "1.0.0", "package_sha256": "a" * 64}
        )["status"] == "candidate"
        assert client.list_model_releases() == []
        assert client.transition_model_release(
            "portrait", "1.0.0", status="active", reason="approved"
        )["status"] == "active"
        assert client.rollback_model_release(
            "portrait", target_version="1.0.0", reason="regression"
        )["status"] == "active"
        assert client.list_model_deployment_events() == []

    assert any(request.url.path.endswith("/review") for request in requests)
    assert any(request.url.path.endswith("/rollback") for request in requests)
