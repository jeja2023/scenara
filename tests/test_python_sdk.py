from __future__ import annotations

import json
from pathlib import Path

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
        if request.url.path.endswith("/platform/products"):
            return httpx.Response(
                200,
                content=envelope([{"product_id": "parse", "name": "Scenara Parse", "maturity": "available"}]),
            )
        if request.url.path.endswith("/platform/repositories"):
            return httpx.Response(
                200,
                content=envelope(
                    {
                        "schema_version": "1.0",
                        "current_repository_id": "scenara",
                        "repositories": [{"repository_id": "scenara", "current_repository": True}],
                        "integration_contracts": [],
                        "boundary_rules": ["versioned_contracts_only"],
                    }
                ),
            )
        if request.url.path.endswith("/platform/contracts"):
            return httpx.Response(
                200,
                content=envelope(
                    {
                        "schema_version": "1.0",
                        "release_version": "1.2.0",
                        "package_name": "@scenara/repository-contracts",
                        "contracts": [],
                    }
                ),
            )
        if request.url.path.endswith("/platform/access-foundation"):
            return httpx.Response(
                200,
                content=envelope(
                    {
                        "auth_mode": "single_bearer_token",
                        "principal_source": "api_token",
                        "tenant_id": "tenant-a",
                        "project_id": "project-a",
                        "principal_id": "api-token",
                        "policy_provider": "development-open",
                        "capabilities": [],
                    }
                ),
            )
        if request.url.path.endswith("/platform/portrait-intelligence"):
            return httpx.Response(
                200,
                content=envelope(
                    {
                        "schema_version": "1.0",
                        "positioning": "portrait_intelligence_foundation_platform",
                        "modules": [
                            {
                                "module_id": "algorithms",
                                "name": "Portrait Algorithms",
                                "maturity": "partial",
                                "summary": "Complete portrait AI capability matrix.",
                                "owner_repository_id": "scenara-model",
                                "current_scope": ["person_detection — ready"],
                                "not_in_scope_yet": ["face_detection"],
                                "next_gate": "Submit ONNX artifacts.",
                            }
                        ],
                        "assets": [
                            {
                                "asset_id": "intelligence_engine",
                                "name": "Portrait Intelligence Engine",
                                "maturity": "seed",
                                "summary": "Fuses retrieval and clustering.",
                                "depends_on_modules": ["algorithms"],
                                "next_gate": "Ship multi-modal fusion search.",
                            }
                        ],
                        "capabilities": [
                            {
                                "capability_id": "person_detection",
                                "readiness": "ready",
                                "production_ready": True,
                                "current_model": "yolov8n.onnx",
                                "target_model": None,
                                "embedding_dimension": None,
                                "target_embedding_dimension": None,
                            }
                        ],
                    }
                ),
            )
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
        assert client.get_asset_preview("asset-1") == b"jpeg-preview"
        assert client.list_products()[0]["product_id"] == "parse"
        assert client.get_repository_topology()["current_repository_id"] == "scenara"
        assert client.get_repository_contracts()["release_version"] == "1.2.0"
        assert client.get_access_foundation()["auth_mode"] == "single_bearer_token"
        portrait_intelligence = client.get_portrait_intelligence()
        assert portrait_intelligence["positioning"] == "portrait_intelligence_foundation_platform"
        assert portrait_intelligence["modules"][0]["module_id"] == "algorithms"
        assert portrait_intelligence["capabilities"][0]["readiness"] == "ready"
        assert client.list_models() == []
        assert (
            client.create_webhook_subscription(
                name="sink",
                url="https://events.example/scenara",
                secret="webhook-secret-1234",
                event_types=["result.available"],
            )["endpoint_id"]
            == "whk-1"
        )
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
            client.list_assets()
    assert caught.value.status_code == 403
    assert caught.value.code == "POLICY_DENIED"
    assert caught.value.request_id == "req-denied"


def test_python_sdk_reads_complete_results_and_exposes_delta_pages() -> None:
    offsets: list[int] = []
    total = 1_201

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("unit_offset", "0"))
        limit = int(request.url.params.get("unit_limit", "100"))
        offsets.append(offset)
        units = [{"unit_id": f"frame_{index}"} for index in range(offset, min(total, offset + limit))]
        result = {
            "schema_version": "1.0",
            "run_id": "run-large",
            "domain": "ocr",
            "pipeline": {"pipeline_id": "ocr.document", "version": "0.1.0"},
            "asset_id": "asset-large",
            "source_id": None,
            "units": units,
            "domain_payload": {},
            "relations": [],
            "artifacts": [],
            "models": [],
            "timings": {},
            "media_metadata": {},
            "warnings": [],
            "provenance": {},
            "created_at": 1.0,
        }
        return httpx.Response(
            200,
            content=envelope(
                {"result": result, "unit_offset": offset, "unit_limit": limit, "unit_total": total}
            ),
        )

    with ScenaraClient("https://scenara.example", transport=httpx.MockTransport(handler)) as client:
        page = client.get_result_page("run-large", unit_offset=500, unit_limit=2)
        assert [unit["unit_id"] for unit in page["result"]["units"]] == ["frame_500", "frame_501"]
        result = client.get_result("run-large")

    assert len(result["units"]) == total
    assert result["units"][-1]["unit_id"] == "frame_1200"
    assert offsets == [500, 0, 1000]


def test_python_sdk_iam_administration_methods() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path.endswith("/iam/summary"):
            return httpx.Response(200, content=envelope({"inventory": {"service_accounts": 1}}))
        if path.endswith("/organizations"):
            data: object = [] if request.method == "GET" else {"tenant_id": "tenant-a"}
        elif path.endswith("/projects"):
            data = [] if request.method == "GET" else {"project_id": "project-a"}
        elif path.endswith("/users"):
            data = [] if request.method == "GET" else {"user_id": "user-a"}
        elif path.endswith("/roles"):
            data = [] if request.method == "GET" else {"role_id": "role-a"}
        elif path.endswith("/memberships"):
            data = [] if request.method == "GET" else {"principal_id": "user-a"}
        elif path.endswith("/service-accounts"):
            data = [] if request.method == "GET" else {"service_account_id": "svc-a"}
        elif path.endswith("/api-keys") and "/service-accounts/" in path:
            data = {"record": {"key_id": "key-a"}, "api_key": "sk_scenara_secret"}
        elif path.endswith("/api-keys"):
            data = []
        elif path.endswith("/revoke"):
            data = {"key_id": "key-a", "revoked_at": 1.0}
        elif "/product-entitlements/" in path:
            data = {"product_id": "console", "status": "suspended"}
        elif path.endswith("/product-entitlements"):
            data = [] if request.method == "GET" else {"product_id": "console", "status": "active"}
        else:
            raise AssertionError(f"unexpected SDK request: {request.method} {path}")
        return httpx.Response(200, content=envelope(data))

    with ScenaraClient("https://scenara.example", transport=httpx.MockTransport(handler)) as client:
        assert client.get_iam_summary()["inventory"]["service_accounts"] == 1
        assert client.create_organization("Scenara Labs")["tenant_id"] == "tenant-a"
        assert client.list_organizations() == []
        assert client.create_project("Vision", project_id="project-a")["project_id"] == "project-a"
        assert client.list_projects() == []
        assert client.create_user("Owner", user_id="user-a")["user_id"] == "user-a"
        assert client.list_users() == []
        assert (
            client.create_role("Admin", role_id="role-a", scopes=["iam:*"], product_ids=["console"])["role_id"]
            == "role-a"
        )
        assert client.list_roles() == []
        assert (
            client.create_membership("user-a", principal_type="user", role_ids=["role-a"])["principal_id"] == "user-a"
        )
        assert client.list_memberships() == []
        assert (
            client.create_service_account(
                "Automation",
                service_account_id="svc-a",
                scopes=["iam:read"],
                product_ids=["console"],
            )["service_account_id"]
            == "svc-a"
        )
        assert client.list_service_accounts() == []
        assert (
            client.create_api_key("svc-a", name="CI", scopes=["iam:read"], product_ids=["console"])["record"]["key_id"]
            == "key-a"
        )
        assert client.list_api_keys() == []
        assert client.revoke_api_key("key-a")["revoked_at"] == 1.0
        assert client.create_product_entitlement("console")["status"] == "active"
        assert client.list_product_entitlements() == []
        assert client.update_product_entitlement("console", status="suspended")["status"] == "suspended"

    key_request = next(request for request in requests if request.url.path.endswith("/service-accounts/svc-a/api-keys"))
    assert json.loads(key_request.content) == {
        "name": "CI",
        "scopes": ["iam:read"],
        "product_ids": ["console"],
        "expires_at": None,
    }
    assert any(request.url.path.endswith("/api-keys/key-a/revoke") for request in requests)
    assert any(
        request.method == "PUT" and request.url.path.endswith("/product-entitlements/console") for request in requests
    )


def test_python_sdk_feedback_and_model_release_methods() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path.endswith("/hard-sample-manifests"):
            return httpx.Response(201, content=envelope({"manifest_id": "hsm-1", "sha256": "a" * 64}))
        if path.endswith("/model-deployment-events"):
            return httpx.Response(200, content=envelope([]))
        if path.endswith("/model-packages/admissions"):
            return httpx.Response(201, content=envelope(json.loads(request.content)))
        if path.endswith("/model-releases") and request.method == "GET":
            return httpx.Response(200, content=envelope([]))
        if "/model-releases/" in path:
            return httpx.Response(
                200, content=envelope({"model_id": "portrait", "version": "1.0.0", "status": "active"})
            )
        if path.endswith("/model-releases"):
            return httpx.Response(
                201, content=envelope({"model_id": "portrait", "version": "1.0.0", "status": "candidate"})
            )
        if path.endswith("/review"):
            return httpx.Response(200, content=envelope({"feedback_id": "fbk-1", "status": "approved"}))
        if path.endswith("/feedback") and request.method == "GET":
            return httpx.Response(200, content=envelope([]))
        return httpx.Response(201, content=envelope({"feedback_id": "fbk-1", "status": "pending"}))

    with ScenaraClient("https://scenara.example", transport=httpx.MockTransport(handler)) as client:
        package = {
            "schema_version": "1.0",
            "model_id": "scenara.portrait.detector",
            "version": "1.0.0",
            "capability": "person_detection",
            "adapter": "yolo",
            "runtime_model_id": "scenara.portrait/detector_v1",
            "sha256": "a" * 64,
            "source_uri": f"oci://registry.example/detector@sha256:{'a' * 64}",
            "license_id": "LicenseRef-Proprietary-Approved",
            "model_card": f"https://artifacts.example/card.json#sha256={'b' * 64}",
            "evaluation_evidence": [f"https://artifacts.example/eval.json#sha256={'c' * 64}"],
            "vram_mb": 4096,
            "regression_samples": ["portrait-v1"],
            "production_ready": True,
        }
        assert client.admit_model_package(package)["runtime_model_id"] == "scenara.portrait/detector_v1"
        assert client.create_feedback({"kind": "false_negative"})["feedback_id"] == "fbk-1"
        assert client.list_feedback() == []
        assert client.review_feedback("fbk-1", status="approved")["status"] == "approved"
        assert (
            client.create_hard_sample_manifest(
                dataset_id="portrait.hard-samples",
                version="1.0.0",
                feedback_ids=["fbk-1"],
            )["manifest_id"]
            == "hsm-1"
        )
        assert (
            client.create_model_release({"model_id": "portrait", "version": "1.0.0", "package_sha256": "a" * 64})[
                "status"
            ]
            == "candidate"
        )
        assert client.list_model_releases() == []
        assert (
            client.transition_model_release("portrait", "1.0.0", status="active", reason="approved")["status"]
            == "active"
        )
        assert (
            client.rollback_model_release("portrait", target_version="1.0.0", reason="regression")["status"] == "active"
        )
        assert client.list_model_deployment_events() == []

    assert any(request.url.path.endswith("/review") for request in requests)
    assert any(request.url.path.endswith("/rollback") for request in requests)


def test_python_sdk_media_file_and_stream_shortcuts(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    media_file = tmp_path / "sample.mp4"
    media_file.write_bytes(b"\x00\x00\x00\x18ftypisom-sdk-test")
    image_file = tmp_path / "sample.png"
    image_file.write_bytes(b"\x89PNG\r\n\x1a\n")
    document_file = tmp_path / "sample.pdf"
    document_file.write_bytes(b"%PDF-1.7\n%%EOF")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path.endswith("/probe"):
            return httpx.Response(
                200,
                content=envelope(
                    {
                        "source_id": "src-1",
                        "reachable": True,
                        "latency_ms": 12,
                        "metadata": {"width": 1920, "height": 1080},
                        "checked_at": 1.0,
                    }
                ),
            )
        if request.url.path.endswith("/parse/stream"):
            return httpx.Response(202, content=envelope({"run_id": "run-stream", "status": "queued"}))
        if request.url.path.endswith("/parse/image"):
            return httpx.Response(
                200,
                content=envelope(
                    {
                        "asset": {"asset_id": "asset-image", "metadata": {"format": "png"}},
                        "run": {"run_id": "run-image", "status": "completed"},
                        "result": None,
                    }
                ),
            )
        if request.url.path.endswith("/parse/video"):
            return httpx.Response(
                202,
                content=envelope(
                    {
                        "asset": {"asset_id": "asset-video", "metadata": {"container": "mp4"}},
                        "run": {"run_id": "run-video", "status": "queued"},
                        "result": None,
                    }
                ),
            )
        if request.url.path.endswith("/parse/document"):
            return httpx.Response(
                202,
                content=envelope(
                    {
                        "asset": {"asset_id": "asset-document", "metadata": {"container": "pdf"}},
                        "run": {"run_id": "run-document", "status": "queued"},
                        "result": None,
                    }
                ),
            )
        if request.url.path.endswith("/media/sources") and request.method == "POST":
            return httpx.Response(
                201,
                content=envelope(
                    {
                        "source_id": "src-1",
                        "kind": "stream",
                        "name": "camera-a",
                        "masked_url": "rtsp://1.1.1.1/live",
                        "metadata": {},
                        "created_at": 1.0,
                    }
                ),
            )
        if request.url.path.endswith("/media/sources/src-1"):
            return httpx.Response(200, content=envelope({"source_id": "src-1", "kind": "stream"}))
        return httpx.Response(200, content=envelope({"items": [], "offset": 0, "limit": 50, "total": 0}))

    with ScenaraClient("https://scenara.example", transport=httpx.MockTransport(handler)) as client:
        source = client.create_source(name="camera-a", url="rtsp://1.1.1.1/live")
        assert "secret_ref" not in source
        assert client.list_sources()["total"] == 0
        assert client.get_source("src-1")["source_id"] == "src-1"
        assert client.probe_source("src-1", timeout_ms=2_000)["metadata"]["width"] == 1920
        assert client.parse_image(
            image_file,
            domain="ocr",
            pipeline_id="ocr.document",
            pipeline_version="1.2.3",
            idempotency_key="image-idempotency",
        )["asset"]["asset_id"] == "asset-image"
        assert client.parse_video(
            media_file,
            domain="ocr",
            sample_interval_ms=400,
            sample_strategy="scene_change",
            sample_start_ms=500,
            sample_end_ms=2_500,
            scene_change_threshold=0.2,
            frame_max_edge=1_280,
            page_scale=2.0,
            camera_id="camera-a",
            recording_started_at=1_700_000_000.25,
            wait_ms=2_000,
            idempotency_key="video-idempotency",
        )["asset"]["asset_id"] == "asset-video"
        assert client.parse_document(
            document_file,
            page_scale=2.5,
            idempotency_key="document-idempotency",
        )["asset"]["asset_id"] == "asset-document"
        assert client.parse_stream(
            "src-1",
            domain="ocr",
            sample_interval_ms=500,
            sample_strategy="keyframe",
            sample_start_ms=250,
            sample_end_ms=5_000,
            scene_change_threshold=0.4,
            frame_max_edge=720,
            max_reconnect_attempts=5,
            connect_timeout_ms=3_000,
            read_timeout_ms=2_000,
            idempotency_key="stream-idempotency",
        )["run_id"] == "run-stream"
        client.delete_source("src-1")

    video_request = next(item for item in requests if item.url.path.endswith("/parse/video"))
    assert video_request.headers["Idempotency-Key"] == "video-idempotency"
    assert b'name="sample_interval_ms"' in video_request.content
    assert b"400" in video_request.content
    assert b'name="max_units"' not in video_request.content
    for field in (
        b'sample_strategy',
        b'sample_start_ms',
        b'sample_end_ms',
        b'scene_change_threshold',
        b'frame_max_edge',
        b'page_scale',
        b'camera_id',
        b'recording_started_at',
    ):
        assert b'name="' + field + b'"' in video_request.content
    assert b'name="pipeline_version"' not in video_request.content
    image_request = next(item for item in requests if item.url.path.endswith("/parse/image"))
    assert image_request.headers["Idempotency-Key"] == "image-idempotency"
    assert b'name="pipeline_id"' in image_request.content
    assert b"ocr.document" in image_request.content
    assert b'name="pipeline_version"' in image_request.content
    assert b"1.2.3" in image_request.content
    document_request = next(item for item in requests if item.url.path.endswith("/parse/document"))
    assert document_request.headers["Idempotency-Key"] == "document-idempotency"
    assert b'name="page_scale"' in document_request.content
    assert b"2.5" in document_request.content
    assert b'name="max_units"' not in document_request.content
    stream_request = next(item for item in requests if item.url.path.endswith("/parse/stream"))
    assert stream_request.headers["Idempotency-Key"] == "stream-idempotency"
    assert json.loads(stream_request.content)["parameters"] == {
        "sample_interval_ms": 500,
        "sample_strategy": "keyframe",
        "sample_start_ms": 250,
        "sample_end_ms": 5_000,
        "scene_change_threshold": 0.4,
        "frame_max_edge": 720,
        "max_reconnect_attempts": 5,
        "connect_timeout_ms": 3_000,
        "read_timeout_ms": 2_000,
    }
    assert json.loads(stream_request.content)["pipeline"] == {"pipeline_id": "ocr.document"}
    probe_request = next(item for item in requests if item.url.path.endswith("/probe"))
    assert probe_request.url.params["timeout_ms"] == "2000"
