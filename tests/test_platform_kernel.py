from __future__ import annotations

import time
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import cv2
import httpx
import numpy as np
import pytest
from PIL import Image

from scenara.bootstrap import build_runtime
from scenara.platform.models import (
    PipelineRef,
    PortraitDomainPayload,
    PrincipalContext,
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


def sample_video() -> bytes:
    path = ""
    try:
        with NamedTemporaryFile(delete=False, suffix=".avi") as handle:
            path = handle.name
        writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (64, 48))
        assert writer.isOpened()
        for index in range(10):
            writer.write(np.full((48, 64, 3), index * 20, dtype=np.uint8))
        writer.release()
        return Path(path).read_bytes()
    finally:
        if path:
            Path(path).unlink(missing_ok=True)


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
        files={"file": ("sample.avi", sample_video(), "video/x-msvideo")},
        data={"kind": "video"},
        headers={"X-Principal-Id": "operator-1"},
    )
    assert uploaded.status_code == 201, uploaded.text
    asset = uploaded.json()["data"]
    assert asset["metadata"]["width"] == 64
    assert asset["metadata"]["height"] == 48
    assert asset["metadata"]["fps"] == 5.0
    assert asset["metadata"]["duration_ms"] == 2000

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
    assert asset["metadata"]["width"] == 800
    assert asset["metadata"]["height"] == 400
    assert asset["metadata"]["format"] == "png"
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
async def test_invalid_video_is_rejected_before_asset_persistence(kernel_client) -> None:
    api, runtime = kernel_client
    response = await api.post(
        "/api/v1/media/assets",
        files={"file": ("not-video.mp4", b"not-a-video", "video/mp4")},
        data={"kind": "video"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ARGUMENT"
    assert await runtime.state.list_assets("default", "default") == []


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
    assert "secret_ref" not in source
    stored_source = (await runtime.state.list_sources("default", "default"))[0]
    assert await runtime.secrets.get(stored_source.secret_ref) == (
        "rtsp://camera-user:camera-password@1.1.1.1/live?token=private"
    )

    fetched = await api.get(f"/api/v1/media/sources/{source['source_id']}")
    assert fetched.status_code == 200
    assert "camera-password" not in fetched.text

    deleted = await api.delete(f"/api/v1/media/sources/{source['source_id']}")
    assert deleted.status_code == 204
    assert (await api.get(f"/api/v1/media/sources/{source['source_id']}")).status_code == 404


@pytest.mark.asyncio
async def test_source_probe_returns_sanitized_technical_metadata(
    kernel_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, _runtime = kernel_client
    created = await api.post(
        "/api/v1/media/sources",
        json={"name": "probe-source", "url": "rtsp://user:secret@1.1.1.1/live?token=hidden"},
    )
    source = created.json()["data"]

    def inspect(media):
        assert media.source_url == "rtsp://user:secret@1.1.1.1/live?token=hidden"
        return {"width": 1920, "height": 1080, "fps": 25.0, "codec": "h264", "sampled_units": 1}, b"jpeg"

    monkeypatch.setattr("scenara.platform.services.inspect_media", inspect)
    response = await api.post(f"/api/v1/media/sources/{source['source_id']}/probe")
    assert response.status_code == 200, response.text
    probe = response.json()["data"]
    assert probe["reachable"] is True
    assert probe["metadata"]["width"] == 1920
    assert "secret" not in response.text


@pytest.mark.asyncio
async def test_video_shortcut_runs_sampled_timeline_end_to_end(kernel_client) -> None:
    api, _runtime = kernel_client
    response = await api.post(
        "/api/v1/parse/video",
        files={"file": ("timeline.avi", sample_video(), "video/x-msvideo")},
        data={
            "domain": "ocr",
            "pipeline_id": "ocr.document",
            "sample_interval_ms": "400",
            "max_units": "3",
            "wait_ms": "2000",
        },
        headers={"Idempotency-Key": "video-shortcut"},
    )
    assert response.status_code == 202, response.text
    payload = response.json()["data"]
    assert payload["asset"]["kind"] == "video"
    assert payload["run"]["status"] == "completed"
    assert payload["run"]["pipeline"] == {"pipeline_id": "ocr.document", "version": "0.1.0"}
    result = payload["result"]
    assert len(result["units"]) > 3
    assert [unit["pts_ms"] for unit in result["units"][:3]] == [0, 400, 800]
    assert result["media_metadata"]["sampled_units"] > 3
    assert result["media_metadata"]["duration_ms"] == 2000
    assert "max_units" not in payload["run"]["parameters"]
    assert "media_termination:max_units_reached" not in result["warnings"]


@pytest.mark.asyncio
async def test_document_shortcut_has_a_document_specific_contract(kernel_client) -> None:
    api, _runtime = kernel_client
    response = await api.post(
        "/api/v1/parse/document",
        files={"file": ("pages.pdf", multipage_pdf(), "application/pdf")},
        data={"domain": "ocr", "max_units": "1", "page_scale": "1.0", "wait_ms": "2000"},
        headers={"Idempotency-Key": "document-shortcut"},
    )
    assert response.status_code == 202, response.text
    payload = response.json()["data"]
    assert payload["asset"]["kind"] == "document"
    assert payload["run"]["pipeline"] == {"pipeline_id": "ocr.document", "version": "0.1.0"}
    assert payload["run"]["status"] == "completed"
    assert "max_units" not in payload["run"]["parameters"]
    assert [unit["unit_type"] for unit in payload["result"]["units"]] == ["page", "page", "page"]

    legacy = await api.post(
        "/api/v1/runs",
        json={
            "domain": "ocr",
            "pipeline": {"pipeline_id": "ocr.document", "version": "0.1.0"},
            "asset_id": payload["asset"]["asset_id"],
            "parameters": {"max_units": 1, "page_scale": 1.0},
            "wait_ms": 2000,
        },
        headers={"Idempotency-Key": "document-legacy-max-units"},
    )
    assert legacy.status_code == 202, legacy.text
    legacy_run = legacy.json()["data"]
    assert "max_units" not in legacy_run["parameters"]
    legacy_result = (await api.get(f"/api/v1/runs/{legacy_run['run_id']}/result")).json()["data"]["result"]
    assert [unit["unit_type"] for unit in legacy_result["units"]] == ["page", "page", "page"]


@pytest.mark.asyncio
async def test_video_shortcut_rejects_unknown_sampling_strategy_before_creating_an_asset(kernel_client) -> None:
    api, runtime = kernel_client
    response = await api.post(
        "/api/v1/parse/video",
        files={"file": ("timeline.avi", sample_video(), "video/x-msvideo")},
        data={"sample_strategy": "every-other-frame"},
    )
    assert response.status_code == 422
    assert await runtime.state.list_assets("default", "default") == []


@pytest.mark.asyncio
async def test_stream_shortcut_runs_decode_and_result_end_to_end(
    kernel_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, _runtime = kernel_client
    frame = np.zeros((48, 64, 3), dtype=np.uint8)

    class Capture:
        def __init__(self, *_args: object) -> None:
            self.reads = 0

        def isOpened(self) -> bool:
            return True

        def get(self, field: int) -> float:
            if field == cv2.CAP_PROP_FPS:
                return 25.0
            if field == cv2.CAP_PROP_FRAME_WIDTH:
                return 64.0
            if field == cv2.CAP_PROP_FRAME_HEIGHT:
                return 48.0
            if field == cv2.CAP_PROP_POS_MSEC:
                return float(max(0, self.reads - 1))
            return 0.0

        def read(self):
            self.reads += 1
            if self.reads > 5:
                return False, None
            return True, frame

        def release(self) -> None:
            return None

    monkeypatch.setattr("scenara.platform.media_batch.cv2.VideoCapture", Capture)
    created = await api.post(
        "/api/v1/media/sources",
        json={"name": "stream-run", "url": "rtsp://1.1.1.1/live"},
    )
    source = created.json()["data"]
    preview = await api.get(f"/api/v1/media/sources/{source['source_id']}/preview")
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("image/jpeg")
    assert preview.content
    response = await api.post(
        "/api/v1/parse/stream",
        json={
            "source_id": source["source_id"],
            "domain": "ocr",
            "pipeline": {"pipeline_id": "ocr.document"},
            "parameters": {
                "sample_interval_ms": 1,
                "max_units": 2,
                "max_reconnect_attempts": 0,
            },
            "wait_ms": 2000,
        },
        headers={"Idempotency-Key": "stream-shortcut"},
    )
    assert response.status_code == 202, response.text
    run = response.json()["data"]
    assert run["status"] == "completed"
    assert run["pipeline"] == {"pipeline_id": "ocr.document", "version": "0.1.0"}
    result = (await api.get(f"/api/v1/runs/{run['run_id']}/result")).json()["data"]["result"]
    assert result["source_id"] == source["source_id"]
    assert len(result["units"]) > 2
    assert result["media_metadata"]["sampled_units"] > 2
    assert "max_units" not in run["parameters"]
    assert "stream_segment_duration_ms" in run["parameters"]
    assert "media_termination:max_units_reached" not in result["warnings"]


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
    stored_source = (await runtime.state.list_sources("default", "default"))[0]
    await runtime.secrets.put(
        stored_source.secret_ref,
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
        files={"file": ("sample.avi", sample_video(), "video/x-msvideo")},
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
    result_index_id = f"result.{reference.domain}"
    indexed = await runtime.indexes.list_records(
        "default", "default", index_id=result_index_id, source_id=run["run_id"]
    )
    assert indexed
    assert all(item.expires_at == pytest.approx(reference.created_at + 180 * 86_400) for item in indexed)

    result_envelope = await runtime.runs.result(
        PrincipalContext(tenant_id="default", project_id="default", principal_id="default"),
        run["run_id"],
    )
    artifact_keys = [item.object_key for item in result_envelope.artifacts]

    deleted = await RetentionScheduler(runtime.state, runtime.objects).sweep(
        before=reference.created_at + 181 * 86_400,
    )
    assert deleted == len(result_keys) + len(artifact_keys) + 2
    assert await runtime.indexes.delete_expired(reference.created_at + 181 * 86_400) == len(indexed)
    assert await runtime.indexes.list_records("default", "default", index_id=result_index_id) == []
    assert await runtime.state.get_result_reference("default", "default", run["run_id"]) is None
    for object_key in [*result_keys, *artifact_keys]:
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
            files={"file": ("sample.avi", sample_video(), "video/x-msvideo")},
            data={"kind": "video"},
            headers={"Authorization": "Bearer test-token", "X-Principal-Id": "admin"},
        )
        assert spoofed.status_code == 400
        accepted = await api.post(
            "/api/v1/media/assets",
            files={"file": ("sample.avi", sample_video(), "video/x-msvideo")},
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
