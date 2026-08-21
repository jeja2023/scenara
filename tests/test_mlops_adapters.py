from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import httpx
import pytest

from scenara.infrastructure.mlflow_tracking import MlflowRunTracker
from scenara.infrastructure.triton_model import TritonModelAdapter
from scenara.platform.model_runtime import AdapterHealth, ModelPackageManifest


def _package() -> ModelPackageManifest:
    digest = hashlib.sha256(b"artifact").hexdigest()
    return ModelPackageManifest(
        model_id="scenara.test",
        version="1.0.0",
        capability="person_detection",
        adapter="triton",
        runtime_model_id="scenara.test/1",
        sha256=digest,
        source_uri=f"internal://artifact#sha256={digest}",
        license_id="Proprietary",
        model_card=f"internal://card#sha256={'b' * 64}",
        evaluation_evidence=(f"internal://eval#sha256={'c' * 64}",),
        vram_mb=1024,
        regression_samples=("sample-1",),
        production_ready=True,
    )


@pytest.mark.asyncio
async def test_triton_adapter_health_predict_and_metadata(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/infer"):
            return httpx.Response(200, json={"outputs": [{"name": "boxes", "data": [1]}]})
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://triton")
    adapter = TritonModelAdapter("http://triton", model_name="scenara.test", client=client)
    package = _package()
    await adapter.load(package, tmp_path / "unused")
    assert await adapter.health() == AdapterHealth.READY
    assert await adapter.predict({"inputs": []}) == {"outputs": [{"name": "boxes", "data": [1]}]}
    assert adapter.metadata().sha256 == package.sha256
    assert calls[-1] == ("POST", "/v2/models/scenara.test/versions/1.0.0/infer")
    await adapter.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_mlflow_tracker_binds_package_to_run() -> None:
    class RecordingTransport(httpx.AsyncBaseTransport):
        def __init__(self) -> None:
            self.requests: list[tuple[str, dict[str, object]]] = []

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            path = request.url.path
            body = json.loads(request.content.decode("utf-8"))
            self.requests.append((path, body))
            if path.endswith("runs/create"):
                return httpx.Response(200, json={"run": {"info": {"run_id": "run-123"}}})
            return httpx.Response(200, json={})

    transport = RecordingTransport()
    client = httpx.AsyncClient(transport=transport, base_url="http://mlflow")
    tracker = MlflowRunTracker("http://mlflow", experiment_id="exp-1", client=client)
    assert await tracker.log_model_package(_package()) == "run-123"
    assert transport.requests[1][0].endswith("runs/log-batch")
    tags = cast(list[dict[str, str]], transport.requests[1][1]["tags"])
    assert any(item["key"] == "scenara.package_sha256" for item in tags)
    await tracker.close()
    await client.aclose()
