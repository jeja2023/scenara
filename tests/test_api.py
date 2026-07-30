from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from PIL import Image

from scenara import __version__
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
async def test_operational_probes_and_metrics_report_runtime_health(client) -> None:
    api, _ = client
    live = await api.get("/livez")
    assert live.status_code == 200
    assert live.json()["data"]["version"] == __version__

    ready = await api.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["data"]["components"] == {"state": "ok", "objects": "ok", "queue": "ok"}

    metrics = await api.get("/metrics")
    assert metrics.status_code == 200
    assert 'scenara_http_requests_total{method="GET",route="/livez",status="200"} 1' in metrics.text
    assert 'scenara_http_request_duration_seconds_bucket{method="GET",route="/livez",le="+Inf"} 1' in metrics.text
    assert 'scenara_http_request_duration_seconds_count{method="GET",route="/readyz"} 1' in metrics.text
    assert (await api.get("/openapi.json")).json()["info"]["version"] == __version__


@pytest.mark.asyncio
async def test_readiness_fails_when_a_required_backend_is_unavailable(client, monkeypatch: pytest.MonkeyPatch) -> None:
    api, runtime = client

    async def unavailable() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(runtime.state, "health_check", unavailable)
    response = await api.get("/readyz")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "HTTP_ERROR"


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
async def test_platform_product_catalog_exposes_matrix_boundaries(client) -> None:
    api, _ = client
    response = await api.get("/api/v1/platform/products")
    assert response.status_code == 200, response.text
    items = response.json()["data"]
    by_id = {item["product_id"]: item for item in items}
    assert set(by_id) == {
        "agent",
        "api",
        "console",
        "data",
        "edge",
        "flow",
        "index",
        "model",
        "parse",
        "sdk",
        "search",
    }
    assert by_id["parse"]["maturity"] == "available"
    assert by_id["parse"]["console_route"] == "/parse"
    assert "OCR document parsing" in by_id["parse"]["current_scope"]
    assert by_id["model"]["maturity"] == "seed"
    assert "training jobs" in by_id["model"]["not_in_scope_yet"]
    assert by_id["console"]["layer"] == "control_plane"
    assert by_id["api"]["layer"] == "developer_surface"
    assert by_id["agent"]["maturity"] == "gated"
    assert by_id["agent"]["depends_on"] == ["flow", "search", "api", "console"]


@pytest.mark.asyncio
async def test_platform_repository_topology_exposes_ownership_and_integration_boundaries(client) -> None:
    api, _ = client
    response = await api.get("/api/v1/platform/repositories")
    assert response.status_code == 200, response.text
    topology = response.json()["data"]
    assert topology["schema_version"] == "1.0"
    assert topology["current_repository_id"] == "scenara"

    by_id = {item["repository_id"]: item for item in topology["repositories"]}
    assert set(by_id) == {"scenara", "scenara-data", "scenara-model"}
    assert by_id["scenara"]["current_repository"] is True
    assert set(by_id["scenara"]["primary_product_ids"]) == {
        "agent",
        "api",
        "console",
        "edge",
        "flow",
        "index",
        "parse",
        "sdk",
        "search",
    }
    assert by_id["scenara"]["integration_product_ids"] == ["model", "data"]
    assert "model_admission_release_and_deployment" in by_id["scenara"]["responsibilities"]
    assert "model_training_jobs" in by_id["scenara"]["excluded_responsibilities"]

    assert by_id["scenara-model"]["lifecycle"] == "external_existing"
    assert "model_training_jobs" in by_id["scenara-model"]["responsibilities"]
    assert "model_admission_release_and_deployment" in by_id["scenara-model"]["excluded_responsibilities"]
    assert by_id["scenara-data"]["lifecycle"] == "planned"
    assert "dataset_catalog_and_versioning" in by_id["scenara-data"]["responsibilities"]

    contracts = {item["contract_id"]: item for item in topology["integration_contracts"]}
    assert contracts["model-package-admission"]["producer_repository_id"] == "scenara-model"
    assert contracts["model-package-admission"]["consumer_repository_id"] == "scenara"
    assert contracts["model-package-admission"]["payload_type"] == "ModelPackageManifest"
    assert contracts["hard-sample-handoff"]["payload_type"] == "HardSampleManifest"
    assert set(topology["boundary_rules"]) == {
        "immutable_artifact_references",
        "no_cross_repository_source_imports",
        "no_shared_database",
        "versioned_contracts_only",
    }


@pytest.mark.asyncio
async def test_platform_access_foundation_exposes_current_identity_boundary(client) -> None:
    api, _ = client
    response = await api.get(
        "/api/v1/platform/access-foundation",
        headers={"X-Tenant-Id": "tenant-a", "X-Project-Id": "project-a", "X-Principal-Id": "operator-a"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["auth_mode"] == "development_open"
    assert payload["principal_source"] == "header"
    assert payload["tenant_id"] == "tenant-a"
    assert payload["project_id"] == "project-a"
    assert payload["principal_id"] == "operator-a"
    assert payload["policy_provider"] == "development-open"
    by_id = {item["capability_id"]: item for item in payload["capabilities"]}
    assert by_id["tenant_project_context"]["status"] == "available"
    assert by_id["api_authentication"]["status"] == "available"
    assert by_id["policy_provider"]["status"] == "available"
    assert "service account API keys" in by_id["api_authentication"]["current_scope"]
    assert by_id["sso"]["status"] == "planned"


@pytest.mark.asyncio
async def test_iam_lifecycle_issues_scoped_service_credentials(development_settings) -> None:
    settings = replace(development_settings, auth_required=True, api_token="root-secret")
    runtime = build_runtime(settings)
    app = create_app(runtime=runtime)
    root_headers = {
        "Authorization": "Bearer root-secret",
        "X-Tenant-Id": "tenant-a",
        "X-Project-Id": "project-a",
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        organization = await api.post(
            "/api/v1/platform/organizations", json={"display_name": "Scenara Labs"}, headers=root_headers
        )
        assert organization.status_code == 201, organization.text
        assert organization.json()["data"]["tenant_id"] == "tenant-a"

        project = await api.post(
            "/api/v1/platform/projects",
            json={"project_id": "project-a", "display_name": "Vision Platform"},
            headers=root_headers,
        )
        assert project.status_code == 201, project.text
        user = await api.post(
            "/api/v1/platform/users",
            json={"user_id": "user-a", "display_name": "Platform Owner", "email": "owner@example.test"},
            headers=root_headers,
        )
        assert user.status_code == 201, user.text
        role = await api.post(
            "/api/v1/platform/roles",
            json={"role_id": "role-admin", "display_name": "Project Admin", "scopes": ["iam:*"], "product_ids": ["console"]},
            headers=root_headers,
        )
        assert role.status_code == 201, role.text
        membership = await api.post(
            "/api/v1/platform/memberships",
            json={"principal_id": "user-a", "principal_type": "user", "role_ids": ["role-admin"]},
            headers=root_headers,
        )
        assert membership.status_code == 201, membership.text
        entitlement = await api.post(
            "/api/v1/platform/product-entitlements",
            json={"product_id": "console"},
            headers=root_headers,
        )
        assert entitlement.status_code == 201, entitlement.text

        service_account = await api.post(
            "/api/v1/platform/service-accounts",
            json={
                "service_account_id": "automation-reader",
                "display_name": "Console Reader",
                "scopes": ["iam:*"],
                "product_ids": ["console"],
            },
            headers=root_headers,
        )
        assert service_account.status_code == 201, service_account.text

        escalation = await api.post(
            "/api/v1/platform/service-accounts/automation-reader/api-keys",
            json={"name": "invalid", "scopes": ["*"], "product_ids": ["console"]},
            headers=root_headers,
        )
        assert escalation.status_code == 403
        assert escalation.json()["error"]["code"] == "POLICY_DENIED"

        issued = await api.post(
            "/api/v1/platform/service-accounts/automation-reader/api-keys",
            json={"name": "console automation", "scopes": ["iam:read"], "product_ids": ["console"]},
            headers=root_headers,
        )
        assert issued.status_code == 201, issued.text
        credential = issued.json()["data"]
        api_key = credential["api_key"]
        key_id = credential["record"]["key_id"]
        assert api_key.startswith("sk_scenara_")
        assert "sha256" not in issued.text.lower()

        key_headers = {"Authorization": f"Bearer {api_key}"}
        summary = await api.get("/api/v1/platform/iam/summary", headers=key_headers)
        assert summary.status_code == 200, summary.text
        assert summary.json()["data"]["inventory"] == {
            "organizations": 1,
            "projects": 1,
            "users": 1,
            "roles": 1,
            "memberships": 1,
            "service_accounts": 1,
            "api_keys": 1,
            "product_entitlements": 1,
        }
        foundation = await api.get("/api/v1/platform/access-foundation", headers=key_headers)
        assert foundation.status_code == 200
        assert foundation.json()["data"]["principal_source"] == "service_account_api_key"
        assert foundation.json()["data"]["principal_id"] == "automation-reader"

        denied_write = await api.post(
            "/api/v1/platform/users",
            json={"display_name": "Denied User"},
            headers=key_headers,
        )
        assert denied_write.status_code == 403
        project_mismatch = await api.get(
            "/api/v1/platform/iam/summary",
            headers={**key_headers, "X-Project-Id": "project-b"},
        )
        assert project_mismatch.status_code == 403

        suspended = await api.put(
            "/api/v1/platform/product-entitlements/console",
            json={"status": "suspended"},
            headers=root_headers,
        )
        assert suspended.status_code == 200, suspended.text
        product_suspended = await api.get("/api/v1/platform/iam/summary", headers=key_headers)
        assert product_suspended.status_code == 403
        assert product_suspended.json()["error"]["message"] == "product denied: console"
        restored = await api.put(
            "/api/v1/platform/product-entitlements/console",
            json={"status": "active"},
            headers=root_headers,
        )
        assert restored.status_code == 200, restored.text
        assert (await api.get("/api/v1/platform/iam/summary", headers=key_headers)).status_code == 200

        parser_account = await api.post(
            "/api/v1/platform/service-accounts",
            json={
                "service_account_id": "automation-parser",
                "display_name": "Parser without entitlement",
                "scopes": ["*"],
                "product_ids": ["parse"],
            },
            headers=root_headers,
        )
        assert parser_account.status_code == 201, parser_account.text
        parser_key_response = await api.post(
            "/api/v1/platform/service-accounts/automation-parser/api-keys",
            json={"name": "parser", "scopes": ["*"], "product_ids": ["parse"]},
            headers=root_headers,
        )
        assert parser_key_response.status_code == 201, parser_key_response.text
        parser_key = parser_key_response.json()["data"]["api_key"]
        product_denied = await api.get(
            "/api/v1/media/assets",
            headers={"Authorization": f"Bearer {parser_key}"},
        )
        assert product_denied.status_code == 403
        assert product_denied.json()["error"]["message"] == "product denied: parse"

        revoked = await api.post(
            f"/api/v1/platform/api-keys/{key_id}/revoke", headers=root_headers
        )
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["data"]["revoked_at"] is not None
        assert (await api.get("/api/v1/platform/iam/summary", headers=key_headers)).status_code == 401


@pytest.mark.asyncio
async def test_iam_rejects_cross_project_assignments(client) -> None:
    api, _ = client
    headers = {"X-Tenant-Id": "tenant-a", "X-Project-Id": "project-a"}
    membership = await api.post(
        "/api/v1/platform/memberships",
        json={
            "project_id": "project-b",
            "principal_id": "user-a",
            "principal_type": "user",
            "role_ids": ["role-a"],
        },
        headers=headers,
    )
    assert membership.status_code == 403
    entitlement = await api.post(
        "/api/v1/platform/product-entitlements",
        json={"project_id": "project-b", "product_id": "parse"},
        headers=headers,
    )
    assert entitlement.status_code == 403


@pytest.mark.asyncio
async def test_iam_rejects_dangling_projects_principals_and_roles(client) -> None:
    api, _ = client
    headers = {"X-Tenant-Id": "tenant-a", "X-Project-Id": "project-a"}
    missing_project = await api.post(
        "/api/v1/platform/service-accounts",
        json={"display_name": "Orphan", "scopes": ["iam:read"]},
        headers=headers,
    )
    assert missing_project.status_code == 404

    assert (
        await api.post(
            "/api/v1/platform/organizations",
            json={"display_name": "Scenara Labs"},
            headers=headers,
        )
    ).status_code == 201
    assert (
        await api.post(
            "/api/v1/platform/projects",
            json={"project_id": "project-a", "display_name": "Vision"},
            headers=headers,
        )
    ).status_code == 201
    missing_principal = await api.post(
        "/api/v1/platform/memberships",
        json={"principal_id": "user-a", "principal_type": "user", "role_ids": ["role-a"]},
        headers=headers,
    )
    assert missing_principal.status_code == 404
    assert (
        await api.post(
            "/api/v1/platform/users",
            json={"user_id": "user-a", "display_name": "Owner"},
            headers=headers,
        )
    ).status_code == 201
    missing_role = await api.post(
        "/api/v1/platform/memberships",
        json={"principal_id": "user-a", "principal_type": "user", "role_ids": ["role-a"]},
        headers=headers,
    )
    assert missing_role.status_code == 404


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
