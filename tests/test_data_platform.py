from __future__ import annotations

import base64
import json
from dataclasses import replace

import httpx
import pytest

from scenara.bootstrap import build_runtime
from scenara.platform.data_migration import export_data_migration_package
from scenara.platform.data_platform import DataPlatformRemoteError, HttpDataPlatformClient
from scenara.platform.models import (
    CreateDatasetRequest,
    DatasetVersionStatus,
    PrincipalContext,
    TransitionDatasetVersionRequest,
)
from scenara.platform.feedback import FeedbackKind, HardSampleItem, HardSampleManifest
from scenara.settings import load_settings


@pytest.mark.asyncio
async def test_http_data_client_forwards_identity_trace_and_idempotency() -> None:
    received: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        received["path"] = request.url.path
        received["headers"] = dict(request.headers)
        received["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "schema_version": "1.0",
                "request_id": "data-request",
                "data": {
                    "dataset_id": "dst_1",
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                    "name": "训练集",
                    "description": "",
                    "status": "draft",
                    "metadata": {},
                    "created_at": 1.0,
                    "updated_at": 1.0,
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://data.example")
    gateway = HttpDataPlatformClient("https://ignored.example", service_token="service-token", client=client)
    context = PrincipalContext(
        tenant_id="tenant-a",
        project_id="project-a",
        principal_id="user-a",
        scopes=frozenset({"data.dataset.create"}),
        product_ids=frozenset({"scenara-data"}),
        request_id="req_123",
        traceparent="00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
    )
    dataset = await gateway.create_dataset(context, CreateDatasetRequest(name="训练集"))
    assert dataset.dataset_id == "dst_1"
    assert received["path"] == "/internal/v1/datasets"
    headers = received["headers"]
    assert isinstance(headers, dict)
    assert headers["x-scenara-tenant-id"] == "tenant-a"
    assert headers["x-request-id"] == "req_123"
    assert headers["idempotency-key"] == "req_123:POST:/internal/v1/datasets"
    assert headers["traceparent"].startswith("00-")
    await gateway.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_http_data_client_preserves_remote_error_code() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "request_id": "data-request",
                "error": {"code": "DATASET_CONFLICT", "message": "version already exists", "details": {}},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://data.example")
    gateway = HttpDataPlatformClient("https://ignored.example", client=client, max_retries=0)
    with pytest.raises(DataPlatformRemoteError, match="version already exists") as captured:
        await gateway.get_dataset(PrincipalContext(tenant_id="t", project_id="p"), "dst_1")
    assert captured.value.status_code == 409
    assert captured.value.code == "DATASET_CONFLICT"
    await client.aclose()


@pytest.mark.asyncio
async def test_http_data_client_maps_legacy_dataset_version_states() -> None:
    received: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        received["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "request_id": "data-request",
                "data": {
                    "version_id": "dsv_1",
                    "dataset_id": "dst_1",
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                    "version": "1.0.0",
                    "status": "ready",
                    "manifest_sha256": "a" * 64,
                    "asset_ids": [],
                    "item_count": 0,
                    "created_by": "user-a",
                    "created_at": 1.0,
                    "updated_at": 1.0,
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://data.example")
    gateway = HttpDataPlatformClient("https://ignored.example", client=client)
    result = await gateway.transition_dataset_version(
        PrincipalContext(tenant_id="tenant-a", project_id="project-a", principal_id="user-a"),
        "dsv_1",
        TransitionDatasetVersionRequest(status=DatasetVersionStatus.VALIDATED),
    )
    assert received["body"] == {"status": "ready"}
    assert result.status == DatasetVersionStatus.VALIDATED
    await client.aclose()


@pytest.mark.asyncio
async def test_http_data_client_pages_through_data_service_limit_for_core_page() -> None:
    requests: list[dict[str, str]] = []
    rows = [
        {
            "dataset_id": f"dst_{index:03d}",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "name": f"dataset {index}",
            "description": "",
            "status": "draft",
            "dataset_metadata": {},
            "created_at": "2026-08-30T00:00:00Z",
            "updated_at": "2026-08-30T00:00:00Z",
        }
        for index in range(150)
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(dict(request.url.params))
        cursor = request.url.params.get("cursor")
        offset = 0 if cursor is None else int(base64.urlsafe_b64decode(cursor).decode("ascii"))
        limit = int(request.url.params["limit"])
        return httpx.Response(200, json={"items": rows[offset : offset + limit], "total": len(rows)})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://data.example")
    gateway = HttpDataPlatformClient("https://ignored.example", client=client)
    page = await gateway.list_datasets(
        PrincipalContext(tenant_id="tenant-a", project_id="project-a", principal_id="user-a"), offset=0, limit=200
    )
    assert len(page.items) == 150
    assert page.total == 150
    assert [request["limit"] for request in requests] == ["100", "100"]
    assert requests[0].get("cursor") is None
    assert requests[1]["cursor"] == "MTAw"
    await client.aclose()


@pytest.mark.asyncio
async def test_migration_export_contains_checksums_and_scoped_records(development_settings, tmp_path) -> None:
    runtime = build_runtime(development_settings)
    await runtime.open()
    try:
        context = PrincipalContext(tenant_id="default", project_id="default", principal_id="migration-test")
        await runtime.data.create_dataset(context, CreateDatasetRequest(name="迁移数据集"))
        output = tmp_path / "scenara-data-migration"
        summary = await export_data_migration_package(
            state=runtime.state,
            control_plane=runtime.control_plane,
            feedback=runtime.feedback,
            tenant_id="default",
            project_id="default",
            output_dir=output,
            source_version="0.3.0.dev22",
        )
    finally:
        await runtime.close()
    manifest = json.loads((output / "migration-manifest.json").read_text(encoding="utf-8"))
    assert summary.record_counts["datasets"] == 1
    assert (manifest["tenant_id"], manifest["project_id"]) == ("default", "default")
    declared_files = {item["file"] for item in manifest["files"]}
    assert declared_files >= {"datasets.jsonl", "samples.jsonl", "dataset-versions.jsonl", "object-references.jsonl"}
    assert (output / "checksums.txt").read_text(encoding="utf-8").count("\n") == len(summary.files)


def test_production_requires_remote_data_platform() -> None:
    settings = replace(load_settings(), profile="production", data_platform_mode="local")
    with pytest.raises(RuntimeError, match="DATA_PLATFORM_MODE"):
        settings.validate()


@pytest.mark.asyncio
async def test_core_delivers_approved_hard_sample_to_remote_data_platform(development_settings) -> None:
    delivered: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        delivered.append(json.loads(request.content))
        return httpx.Response(201, json={"request_id": "data", "data": {"import_id": "hsi_1"}})

    data_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://data.example")
    runtime = build_runtime(
        replace(
            development_settings,
            data_platform_mode="http",
            data_platform_url="https://data.example",
        )
    )
    class FakeSourceAssets:
        async def get_asset(self, tenant_id: str, project_id: str, asset_id: str):
            assert (tenant_id, project_id, asset_id) == (
                "default",
                "default",
                "media#sha256=" + "a" * 64,
            )
            return type(
                "Asset",
                (),
                {
                    "object_key": "media/example.jpg",
                    "sha256": "a" * 64,
                    "size_bytes": 123,
                    "content_type": "image/jpeg",
                },
            )()

    runtime.data = HttpDataPlatformClient(
        "https://data.example",
        client=data_client,
        source_assets=FakeSourceAssets(),
        source_bucket="scenara-media",
    )
    from scenara.server import create_app

    class FakeFeedbackService:
        async def create_manifest(self, context, body):
            return HardSampleManifest(
                manifest_id="hsm_1",
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                dataset_id=body.dataset_id,
                version=body.version,
                items=(
                    HardSampleItem(
                        feedback_id="fb_1",
                        kind=FeedbackKind.FALSE_POSITIVE,
                        media_ref="media#sha256=" + "a" * 64,
                        result_ref="result#sha256=" + "b" * 64,
                        model_id="person-reid",
                        model_version="1.0.0",
                        pipeline_id="portrait.pipeline",
                        pipeline_version="1.0.0",
                        correction={"label": "hard"},
                    ),
                ),
                sha256="c" * 64,
                created_by=context.principal_id,
                created_at="2026-08-18T00:00:00Z",
            )

    runtime.feedback = FakeFeedbackService()  # type: ignore[assignment]

    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://core") as api:
        manifest = await api.post(
            "/api/v1/hard-sample-manifests",
            json={"dataset_id": "dataset-1", "version": "1.0.0", "feedback_ids": ["fb_1"]},
        )
    assert manifest.status_code == 201, manifest.text
    assert len(delivered) == 1
    assert delivered[0]["manifest"]["manifest_id"] == manifest.json()["data"]["manifest_id"]
    assert delivered[0]["sources"][0]["source_ref"]["key"] == "media/example.jpg"
    await runtime.close()
    await data_client.aclose()
