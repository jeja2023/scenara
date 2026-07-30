from __future__ import annotations

import base64
import os
from pathlib import Path

import cv2
import httpx
import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from scenara.infrastructure.object_store import LocalObjectStore
from scenara.platform.audit import AuditLogger, AuditUnavailable
from scenara.platform.media_batch import MediaInput, decode_media
from scenara.platform.model_runtime import AdapterHealth, ModelMetadata, ModelPackageManifest, ModelRegistry
from scenara.platform.models import MediaKind, PipelineStatus, PrincipalContext
from scenara.platform.network import UnsafeNetworkTarget, validate_external_url
from scenara.platform.pipeline import PipelineDefinition, PipelineError, PipelineNode, PipelineRegistry
from scenara.platform.policy import DenyUnavailablePolicyProvider, PolicyUnavailable
from scenara.platform.secrets import EncryptedObjectSecretStore
from scenara.platform.webhooks import WebhookDeliveryError, WebhookDeliveryService, WebhookEndpoint


def test_image_media_batch() -> None:
    from io import BytesIO

    output = BytesIO()
    Image.new("RGB", (8, 6), (10, 20, 30)).save(output, format="PNG")
    decoded = decode_media(
        MediaInput(kind=MediaKind.IMAGE, content_type="image/png", data=output.getvalue()),
        max_units=1,
        sample_interval_ms=1000,
    )
    assert [(unit.width, unit.height, unit.unit_id) for unit in decoded.units] == [(8, 6, "frame_0")]


def test_stream_reconnects_after_consecutive_read_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = np.zeros((8, 12, 3), dtype=np.uint8)

    class Capture:
        created = 0

        def __init__(self, target: str) -> None:
            del target
            self.index = Capture.created
            Capture.created += 1
            self.reads = 0

        def isOpened(self) -> bool:
            return True

        def get(self, field: int) -> float:
            return 25.0 if field == cv2.CAP_PROP_FPS else 0.0

        def read(self) -> tuple[bool, NDArray[np.uint8] | None]:
            self.reads += 1
            if self.index == 0 and self.reads == 1:
                return True, frame
            if self.index == 0:
                return False, None
            return (True, frame) if self.reads == 1 else (False, None)

        def release(self) -> None:
            return None

    monkeypatch.setattr("scenara.platform.media_batch.cv2.VideoCapture", Capture)
    monkeypatch.setattr("scenara.platform.media_batch.time.sleep", lambda _: None)
    decoded = decode_media(
        MediaInput(kind=MediaKind.STREAM, content_type="video/rtsp", source_url="rtsp://example.test/live"),
        max_units=2,
        sample_interval_ms=1,
    )
    assert len(decoded.units) == 2
    assert decoded.termination_reason == "max_units_reached"
    assert Capture.created == 2


@pytest.mark.asyncio
async def test_encrypted_secret_store(tmp_path: Path) -> None:
    objects = LocalObjectStore(tmp_path)
    await objects.open()
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    store = EncryptedObjectSecretStore(objects, key)
    await store.put("secret://media-sources/source-1", "rtsp://camera.example/live")
    assert await store.get("secret://media-sources/source-1") == "rtsp://camera.example/live"
    raw = await objects.get("system/secrets/media-sources/source-1.enc")
    assert b"camera.example" not in raw


@pytest.mark.asyncio
async def test_ssrf_private_literal_is_rejected() -> None:
    with pytest.raises(UnsafeNetworkTarget):
        await validate_external_url(
            "http://127.0.0.1/internal",
            allowed_schemes=frozenset({"http", "https"}),
        )


class _BrokenAuditSink:
    async def append_audit(self, event: object) -> None:
        del event
        raise OSError("offline")


@pytest.mark.asyncio
async def test_audit_fails_closed() -> None:
    logger = AuditLogger(_BrokenAuditSink())
    with pytest.raises(AuditUnavailable):
        await logger.record(
            PrincipalContext(tenant_id="t", project_id="p"),
            action="run.create",
            resource_type="run",
        )


@pytest.mark.asyncio
async def test_enterprise_policy_fails_closed_when_required() -> None:
    provider = DenyUnavailablePolicyProvider()
    with pytest.raises(PolicyUnavailable):
        await provider.authorize(PrincipalContext(tenant_id="t", project_id="p"), "read", "feature")


@pytest.mark.asyncio
async def test_webhook_failure_preserves_transport_error() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    endpoint = WebhookEndpoint("hook", "https://1.1.1.1/events", "secret", frozenset({"run.completed"}))
    with pytest.raises(WebhookDeliveryError, match="ConnectError: connection refused"):
        await WebhookDeliveryService().deliver(
            endpoint,
            "evt-1",
            "run.completed",
            {"run_id": "run-1"},
            max_attempts=1,
            transport=httpx.MockTransport(fail),
        )


def test_pipeline_lifecycle_is_strict() -> None:
    registry = PipelineRegistry()
    pipeline = PipelineDefinition(
        pipeline_id="test.lifecycle",
        version="1.0.0",
        domain="test",
        status=PipelineStatus.DRAFT,
        nodes=[PipelineNode(node_id="node", operator_id="missing", inputs={})],
        output="node.output",
    )
    with pytest.raises(PipelineError, match="unknown operator"):
        registry.register_pipeline(pipeline)


class _Adapter:
    def __init__(self) -> None:
        self.package: ModelPackageManifest | None = None

    async def load(self, package: ModelPackageManifest, artifact: Path) -> None:
        del artifact
        self.package = package

    async def predict(self, inputs: object) -> object:
        return inputs

    async def health(self) -> AdapterHealth:
        return AdapterHealth.READY

    def metadata(self) -> ModelMetadata:
        assert self.package is not None
        return ModelMetadata(**self.package.model_dump(exclude={"model_card", "regression_samples"}))

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_production_model_registry_rejects_unapproved(tmp_path: Path) -> None:
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"model")
    import hashlib

    package = ModelPackageManifest(
        model_id="test.model",
        version="1.0.0",
        capability="test",
        adapter="test",
        sha256=hashlib.sha256(b"model").hexdigest(),
        source_uri="internal://approved",
        license_id="Proprietary",
        model_card="model-card.yml",
        vram_mb=1024,
        regression_samples=("sample-1",),
        production_ready=False,
    )
    with pytest.raises(Exception, match="not approved"):
        await ModelRegistry(production=True).install(package, artifact, _Adapter())


@pytest.mark.asyncio
async def test_model_registry_persists_verified_package_in_catalog(tmp_path: Path) -> None:
    from scenara.infrastructure.memory_state import MemoryStateStore

    artifact = tmp_path / "approved-model.bin"
    artifact.write_bytes(b"approved-model")
    import hashlib

    package = ModelPackageManifest(
        model_id="test.approved-model",
        version="1.0.0",
        capability="test-approved",
        adapter="test",
        sha256=hashlib.sha256(b"approved-model").hexdigest(),
        source_uri="internal://approved-model",
        license_id="Proprietary",
        model_card="model-card.yml",
        vram_mb=1024,
        regression_samples=("sample-1",),
        production_ready=True,
    )
    catalog = MemoryStateStore()
    registry = ModelRegistry(production=True, catalog=catalog)
    await registry.install(package, artifact, _Adapter())
    assert await catalog.list_model_packages() == [package]
