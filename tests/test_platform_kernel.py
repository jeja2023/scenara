from __future__ import annotations

import time
from dataclasses import replace
from io import BytesIO
from typing import Any

import httpx
import pytest
from PIL import Image

from scenara.bootstrap import build_runtime
from scenara.platform.models import (
    PipelineRef,
    PortraitDomainPayload,
    ResultEnvelope,
)
from scenara.platform.retention import RetentionScheduler
from scenara.server import create_app


class PageOcrEngine:
    model_id = "test-layout-ocr"
    version = "1.0.0"
    production_ready = True

    def predict(self, image: Any) -> list[dict[str, Any]]:
        return [
            {
                "text": f"page-{image.width}x{image.height}",
                "score": 0.99,
                "polygon": [[0, 0], [image.width, 0], [image.width, image.height], [0, image.height]],
                "block_type": "paragraph",
            }
        ]


def multipage_pdf() -> bytes:
    output = BytesIO()
    pages = [
        Image.new("RGB", (32, 24), "white"),
        Image.new("RGB", (40, 30), "white"),
        Image.new("RGB", (48, 36), "white"),
    ]
    pages[0].save(output, format="PDF", save_all=True, append_images=pages[1:])
    return output.getvalue()


def sample_png(width: int = 800, height: int = 400) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "teal").save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
async def kernel_client(development_settings):
    settings = replace(development_settings, result_shard_units=1)
    runtime = build_runtime(settings, ocr_engine=PageOcrEngine())
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        yield api, runtime


@pytest.mark.asyncio
async def test_pdf_result_units_are_sharded_and_reassembled(kernel_client) -> None:
    api, runtime = kernel_client
    uploaded = await api.post(
        "/api/v1/media/assets",
        files={"file": ("pages.pdf", multipage_pdf(), "application/pdf")},
        data={"kind": "document"},
    )
    assert uploaded.status_code == 201, uploaded.text
    asset_id = uploaded.json()["data"]["asset_id"]
    created = await api.post(
        "/api/v1/runs",
        json={
            "domain": "ocr",
            "pipeline": {"pipeline_id": "ocr.document", "version": "0.1.0"},
            "asset_id": asset_id,
            "wait_ms": 2000,
        },
        headers={"Idempotency-Key": "pdf-shards"},
    )
    assert created.status_code == 202, created.text
    run_id = created.json()["data"]["run_id"]
    assert created.json()["data"]["status"] == "completed", created.text

    reference = await runtime.state.get_result_reference("default", "default", run_id)
    assert reference is not None
    assert reference.unit_count == 3
    assert len(reference.shard_keys) == 3
    assert len(reference.shard_sha256) == 3

    response = await api.get(f"/api/v1/runs/{run_id}/result", params={"unit_offset": 1, "unit_limit": 1})
    assert response.status_code == 200, response.text
    page = response.json()["data"]
    assert page["unit_total"] == 3
    assert len(page["result"]["units"]) == 1
    assert page["result"]["units"][0]["page_number"] == 2


@pytest.mark.asyncio
async def test_asset_deletion_removes_object_and_records_audit(kernel_client) -> None:
    api, runtime = kernel_client
    uploaded = await api.post(
        "/api/v1/media/assets",
        files={"file": ("sample.png", b"image-bytes", "application/octet-stream")},
        data={"kind": "video"},
        headers={"X-Principal-Id": "operator-1"},
    )
    assert uploaded.status_code == 201, uploaded.text
    asset = uploaded.json()["data"]

    deleted = await api.delete(
        f"/api/v1/media/assets/{asset['asset_id']}",
        headers={"X-Principal-Id": "operator-1"},
    )
    assert deleted.status_code == 204
    assert await runtime.state.get_asset("default", "default", asset["asset_id"]) is None
    with pytest.raises(FileNotFoundError):
        await runtime.objects.get(asset["object_key"])

    events = await runtime.state.audit_events("default", "default")
    actions = [(event.action, event.principal_id) for event in events]
    assert ("media.asset.create", "operator-1") in actions
    assert ("media.asset.delete", "operator-1") in actions


@pytest.mark.asyncio
async def test_asset_preview_is_generated_served_and_deleted_independently(kernel_client) -> None:
    api, runtime = kernel_client
    uploaded = await api.post(
        "/api/v1/media/assets",
        files={"file": ("sample.png", sample_png(), "image/png")},
        data={"kind": "image"},
    )
    assert uploaded.status_code == 201, uploaded.text
    asset = uploaded.json()["data"]
    assert asset["preview_object_key"].endswith("/preview.jpg")
    assert len(asset["preview_sha256"]) == 64

    response = await api.get(f"/api/v1/media/assets/{asset['asset_id']}/preview")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    with Image.open(BytesIO(response.content)) as preview:
        assert max(preview.size) == 640

    raw_deleted = await RetentionScheduler(runtime.state, runtime.objects).sweep(
        before=float(asset["expires_at"]) + 1,
    )
    assert raw_deleted == 1
    retained = await api.get(f"/api/v1/media/assets/{asset['asset_id']}")
    assert retained.status_code == 200
    assert retained.json()["data"]["original_deleted_at"] is not None
    assert (await api.get(f"/api/v1/media/assets/{asset['asset_id']}/preview")).status_code == 200
    rejected = await api.post(
        "/api/v1/runs",
        json={
            "domain": "ocr",
            "pipeline": {"pipeline_id": "ocr.document", "version": "0.1.0"},
            "asset_id": asset["asset_id"],
        },
        headers={"Idempotency-Key": "expired-original"},
    )
    assert rejected.status_code == 404
    assert await runtime.objects.get(asset["preview_object_key"]) == response.content

    preview_deleted = await RetentionScheduler(runtime.state, runtime.objects).sweep(
        before=float(asset["created_at"]) + 31 * 86_400,
    )
    assert preview_deleted == 1
    stored = await runtime.state.get_asset("default", "default", asset["asset_id"])
    assert stored is not None and stored.preview_object_key is None and stored.deleted_at is not None
    with pytest.raises(FileNotFoundError):
        await runtime.objects.get(asset["preview_object_key"])


@pytest.mark.asyncio
async def test_source_credentials_are_not_returned(kernel_client) -> None:
    api, runtime = kernel_client
    response = await api.post(
        "/api/v1/media/sources",
        json={
            "name": "camera-a",
            "url": "rtsp://camera-user:camera-password@1.1.1.1/live?token=private",
        },
    )
    assert response.status_code == 201, response.text
    source = response.json()["data"]
    assert source["masked_url"] == "rtsp://1.1.1.1/live"
    assert "camera-password" not in response.text
    assert await runtime.secrets.get(source["secret_ref"]) == (
        "rtsp://camera-user:camera-password@1.1.1.1/live?token=private"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/internal",
        "http://10.0.0.1/internal",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/internal",
    ],
)
async def test_private_media_source_is_rejected_by_default(kernel_client, url: str) -> None:
    api, runtime = kernel_client
    response = await api.post(
        "/api/v1/media/sources",
        json={"name": "metadata-probe", "url": url},
    )
    assert response.status_code == 400
    assert await runtime.state.list_sources("default", "default") == []


@pytest.mark.asyncio
async def test_media_source_is_revalidated_immediately_before_fetch(kernel_client) -> None:
    api, runtime = kernel_client
    response = await api.post(
        "/api/v1/media/sources",
        json={"name": "camera-a", "url": "rtsp://1.1.1.1/live"},
    )
    assert response.status_code == 201
    source = response.json()["data"]
    await runtime.secrets.put(
        source["secret_ref"],
        "http://169.254.169.254/latest/meta-data",
    )
    created = await api.post(
        "/api/v1/runs",
        json={
            "domain": "ocr",
            "pipeline": {"pipeline_id": "ocr.document", "version": "0.1.0"},
            "source_id": source["source_id"],
            "wait_ms": 2_000,
        },
        headers={"Idempotency-Key": "source-revalidation"},
    )
    assert created.status_code == 202
    run = created.json()["data"]
    assert run["status"] == "failed"
    assert run["error_code"] == "PIPELINE_EXECUTION_FAILED"
    assert "private or special-use" in run["termination_reason"]


@pytest.mark.asyncio
async def test_retention_sweep_deletes_expired_media(kernel_client) -> None:
    api, runtime = kernel_client
    uploaded = await api.post(
        "/api/v1/media/assets",
        files={"file": ("sample.bin", b"video", "application/octet-stream")},
        data={"kind": "video"},
    )
    assert uploaded.status_code == 201
    asset = uploaded.json()["data"]

    deleted = await RetentionScheduler(runtime.state, runtime.objects).sweep(
        before=float(asset["expires_at"]) + 1,
    )
    assert deleted == 1
    stored = await runtime.state.get_asset("default", "default", asset["asset_id"])
    assert stored is not None
    assert stored.original_deleted_at is not None
    with pytest.raises(FileNotFoundError):
        await runtime.objects.get(asset["object_key"])


@pytest.mark.asyncio
async def test_retention_sweep_expires_result_index_and_shards(kernel_client) -> None:
    api, runtime = kernel_client
    uploaded = await api.post(
        "/api/v1/media/assets",
        files={"file": ("pages.pdf", multipage_pdf(), "application/pdf")},
        data={"kind": "document"},
    )
    asset = uploaded.json()["data"]
    created = await api.post(
        "/api/v1/runs",
        json={
            "domain": "ocr",
            "pipeline": {"pipeline_id": "ocr.document", "version": "0.1.0"},
            "asset_id": asset["asset_id"],
            "wait_ms": 2_000,
        },
        headers={"Idempotency-Key": "result-retention"},
    )
    run = created.json()["data"]
    assert run["status"] == "completed"
    reference = await runtime.state.get_result_reference("default", "default", run["run_id"])
    assert reference is not None
    result_keys = [reference.object_key, *reference.shard_keys]

    deleted = await RetentionScheduler(runtime.state, runtime.objects).sweep(
        before=reference.created_at + 181 * 86_400,
    )
    assert deleted == len(result_keys) + 2
    assert await runtime.state.get_result_reference("default", "default", run["run_id"]) is None
    for object_key in result_keys:
        with pytest.raises(FileNotFoundError):
            await runtime.objects.get(object_key)


@pytest.mark.asyncio
async def test_authenticated_principal_cannot_be_spoofed(development_settings) -> None:
    settings = replace(development_settings, auth_required=True, api_token="test-token")
    runtime = build_runtime(settings)
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        spoofed = await api.post(
            "/api/v1/media/assets",
            files={"file": ("sample.bin", b"video", "application/octet-stream")},
            data={"kind": "video"},
            headers={"Authorization": "Bearer test-token", "X-Principal-Id": "admin"},
        )
        assert spoofed.status_code == 400
        accepted = await api.post(
            "/api/v1/media/assets",
            files={"file": ("sample.bin", b"video", "application/octet-stream")},
            data={"kind": "video"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert accepted.status_code == 201

    events = await runtime.state.audit_events("default", "default")
    assert any(event.action == "media.asset.create" and event.principal_id == "api-token" for event in events)


@pytest.mark.asyncio
async def test_completed_stream_run_records_termination_reason(
    kernel_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, runtime = kernel_client
    source_response = await api.post(
        "/api/v1/media/sources",
        json={"name": "qualification-stream", "url": "rtsp://1.1.1.1/live"},
    )
    assert source_response.status_code == 201
    source = source_response.json()["data"]

    async def execute(*args: Any, **kwargs: Any) -> ResultEnvelope:
        context = args[1]
        del kwargs
        return ResultEnvelope(
            run_id=context.run_id,
            domain="portrait",
            pipeline=PipelineRef(pipeline_id="portrait.person-detection", version="0.1.0"),
            source_id=source["source_id"],
            domain_payload=PortraitDomainPayload(),
            warnings=["media_termination:source_ended"],
            created_at=time.time(),
        )

    monkeypatch.setattr(runtime.pipelines, "execute", execute)
    response = await api.post(
        "/api/v1/runs",
        json={
            "domain": "portrait",
            "pipeline": {"pipeline_id": "portrait.person-detection", "version": "0.1.0"},
            "source_id": source["source_id"],
            "wait_ms": 2_000,
        },
        headers={"Idempotency-Key": "stream-termination"},
    )
    assert response.status_code == 202
    run = response.json()["data"]
    assert run["status"] == "completed"
    assert run["termination_reason"] == "source_ended"
