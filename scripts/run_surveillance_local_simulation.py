"""Run local, non-production qualification for the surveillance alert path.

This proves the alert pipeline can handle 50 logical camera bindings together,
deduplicate repeat observations, deliver one real HTTPS webhook to a local
receiver, and replay the alert via a real local SSE connection.  It deliberately
uses the in-memory state and a synthetic face embedding: it is evidence for
software integration only, never a substitute for camera, scale, or release
approval evidence.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import socket
import ssl
import statistics
import sys
import tempfile
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scenara.bootstrap import Runtime, build_runtime
from scenara.domains.portrait.service import CreateIdentityRequest, EnrollIdentityRequest
from scenara.domains.portrait.trajectory import RegisterCameraRequest
from scenara.platform.features import DistanceMetric
from scenara.platform.models import CreateWebhookSubscriptionRequest, MediaSource, PrincipalContext
from scenara.platform.surveillance import (
    CreateSurveillanceTaskRequest,
    CreateWatchlistMemberRequest,
    CreateWatchlistRequest,
    ObservationBatch,
    ObservationEvidence,
    SurveillanceTask,
    SurveillanceTaskStatus,
    TaskBinding,
    ThresholdPolicy,
)
from scenara.platform.webhooks import sign_webhook
from scenara.server import create_app
from scenara.settings import load_settings


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runtime-state" / "qualification" / "surveillance-local-simulation.json"
CONTEXT = PrincipalContext(tenant_id="local-simulation", project_id="surveillance", principal_id="qualification")
EMBEDDING = [1.0, 0.0, 0.0]


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int((len(ordered) * fraction) + 0.999999) - 1))]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _create_certificate(directory: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    certificate_path = directory / "receiver-cert.pem"
    private_key_path = directory / "receiver-key.pem"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private_key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return certificate_path, private_key_path


def _start_https_receiver(certificate: Path, private_key: Path) -> tuple[ThreadingHTTPServer, list[dict[str, Any]]]:
    received: list[dict[str, Any]] = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            size = int(self.headers.get("Content-Length", "0"))
            received.append(
                {
                    "body": self.rfile.read(size),
                    "event_id": self.headers.get("Scenara-Event-Id", ""),
                    "timestamp": self.headers.get("Scenara-Timestamp", ""),
                    "signature": self.headers.get("Scenara-Signature", ""),
                }
            )
            self.send_response(204)
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certificate, private_key)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    asyncio.get_running_loop().run_in_executor(None, server.serve_forever)
    return server, received


async def _wait_for_listener(port: int) -> None:
    deadline = asyncio.get_running_loop().time() + 10
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError(f"local SSE listener did not start on port {port}")
            await asyncio.sleep(0.05)


async def _build_runtime(temporary_dir: Path) -> Runtime:
    settings = replace(
        load_settings(),
        profile="simulation",
        state_backend="memory",
        object_backend="local",
        queue_backend="inline",
        data_platform_mode="local",
        data_dir=temporary_dir / "data",
        qdrant_url="",
        auth_required=False,
        allow_private_webhook_targets=True,
    )
    runtime = build_runtime(settings)
    await runtime.open()
    return runtime


async def _prepare_50_camera_task(runtime: Runtime, source_count: int) -> tuple[SurveillanceTask, list[TaskBinding], str]:
    identity = await runtime.portrait.create_identity(CONTEXT, CreateIdentityRequest(display_name="模拟目标"))
    await runtime.portrait.enroll(
        CONTEXT,
        identity.identity_id,
        EnrollIdentityRequest(
            feature_space_id="portrait.face.local-simulation.v1",
            modality="face",
            model_id="synthetic-face-model",
            model_version="simulation-1",
            distance_metric=DistanceMetric.COSINE,
            threshold=0.8,
            embedding=EMBEDDING,
            quality=1.0,
        ),
    )
    watchlist = await runtime.surveillance.create_watchlist(
        CONTEXT, CreateWatchlistRequest(name="本地模拟名单", category="custom")
    )
    await runtime.surveillance.create_member(
        CONTEXT,
        watchlist.watchlist_id,
        CreateWatchlistMemberRequest(portrait_identity_id=identity.identity_id, display_label="模拟目标"),
    )
    bindings: list[TaskBinding] = []
    for index in range(source_count):
        source_id = f"src-sim-{index:02d}"
        camera_id = f"cam-sim-{index:02d}"
        await runtime.state.create_source(
            MediaSource(
                source_id=source_id,
                tenant_id=CONTEXT.tenant_id,
                project_id=CONTEXT.project_id,
                name=f"模拟摄像头 {index:02d}",
                masked_url=f"rtsp://127.0.0.1:8554/simulation-{index:02d}",
                secret_ref=f"secret://local-simulation/sources/{source_id}",
                created_at=time.time(),
            )
        )
        await runtime.trajectory.register_camera(
            CONTEXT, RegisterCameraRequest(camera_id=camera_id, display_name=f"模拟点位 {index:02d}")
        )
        bindings.append(TaskBinding(binding_id=f"bind-sim-{index:02d}", source_id=source_id, camera_id=camera_id))
    task = await runtime.surveillance.create_task(
        CONTEXT,
        CreateSurveillanceTaskRequest(
            name="50 路本地模拟布控",
            watchlist_ids=[watchlist.watchlist_id],
            bindings=bindings,
            threshold_policy=ThresholdPolicy(policy_version="local-simulation-v1", face_threshold=0.8, body_threshold=None),
            cooldown_seconds=30,
        ),
    )
    active = await runtime.surveillance._repository.save_task(
        task.model_copy(update={"status": SurveillanceTaskStatus.ACTIVE}), expected_revision=task.revision
    )
    return active, bindings, identity.identity_id


def _observation(binding: TaskBinding, *, observed_at: float) -> ObservationBatch:
    return ObservationBatch(
        run_id=f"run-local-simulation-{binding.binding_id}",
        source_id=binding.source_id,
        camera_id=binding.camera_id,
        unit_id="unit-local-simulation",
        track_id="track-local-simulation",
        first_seen_at=observed_at,
        last_seen_at=observed_at + 0.1,
        timestamp_source="processing_time",
        evidence=[
            ObservationEvidence(
                modality="face",
                embedding=EMBEDDING,
                quality=1.0,
                model_id="synthetic-face-model",
                model_version="simulation-1",
            )
        ],
        trace_id="trace-local-simulation",
    )


async def _run_pressure(runtime: Runtime, task: SurveillanceTask, bindings: list[TaskBinding]) -> dict[str, Any]:
    async def evaluate(binding: TaskBinding) -> float:
        started = time.perf_counter()
        await runtime.surveillance._evaluate_observation(CONTEXT, task, binding, _observation(binding, observed_at=1_000.0))
        return (time.perf_counter() - started) * 1_000

    first_pass = list(await asyncio.gather(*(evaluate(binding) for binding in bindings)))
    duplicate_pass = list(await asyncio.gather(*(evaluate(binding) for binding in bindings)))
    page = await runtime.surveillance.list_alerts(
        CONTEXT,
        status=None,
        task_id=task.task_id,
        camera_id=None,
        watchlist_id=None,
        portrait_identity_id=None,
        since=None,
        until=None,
        offset=0,
        limit=200,
    )
    if page.total != len(bindings) or any(item.occurrence_count != 2 for item in page.items):
        raise RuntimeError("50-source simulation did not emit exactly one debounced alert per binding")
    return {
        "logical_sources": len(bindings),
        "first_pass_alerts": page.total,
        "duplicate_pass_new_alerts": 0,
        "occurrence_count_per_alert": 2,
        "latency_ms": {
            "first_pass_p50": round(statistics.median(first_pass), 3),
            "first_pass_p95": round(_percentile(first_pass, 0.95), 3),
            "first_pass_p99": round(_percentile(first_pass, 0.99), 3),
            "duplicate_pass_p95": round(_percentile(duplicate_pass, 0.95), 3),
        },
    }


async def _run_webhook_and_sse(runtime: Runtime, task: SurveillanceTask, binding: TaskBinding, prior_events: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="scenara-webhook-simulation-") as temporary:
        certificate, private_key = _create_certificate(Path(temporary))
        receiver, received = _start_https_receiver(certificate, private_key)
        port = int(receiver.server_address[1])
        secret = "local-simulation-webhook-secret"
        original_ca = os.environ.get("SSL_CERT_FILE")
        os.environ["SSL_CERT_FILE"] = str(certificate)
        try:
            await runtime.webhooks.create(
                CONTEXT,
                CreateWebhookSubscriptionRequest(
                    name="本地 HTTPS 回调接收器",
                    url=f"https://127.0.0.1:{port}/alerts",
                    secret=secret,
                    event_types=frozenset({"alert.triggered"}),
                ),
            )
            await runtime.surveillance._evaluate_observation(
                CONTEXT, task, binding, _observation(binding, observed_at=1_065.0)
            )
            delivered, failed = await runtime.webhooks.deliver_due()
            if delivered != 1 or failed != 0 or len(received) != 1:
                raise RuntimeError("local HTTPS webhook was not delivered exactly once")
            delivered_body = received[0]["body"]
            expected_signature = sign_webhook(secret, int(received[0]["timestamp"]), delivered_body)
            if received[0]["signature"] != expected_signature:
                raise RuntimeError("local HTTPS webhook HMAC signature did not validate")

            sse_port = _free_port()
            application = create_app(runtime=runtime)
            server = uvicorn.Server(
                uvicorn.Config(application, host="127.0.0.1", port=sse_port, lifespan="off", log_level="error", access_log=False)
            )
            server_task = asyncio.create_task(server.serve())
            try:
                await _wait_for_listener(sse_port)
                async with httpx.AsyncClient(timeout=5.0) as client:
                    async with client.stream(
                        "GET",
                        f"http://127.0.0.1:{sse_port}/api/v1/surveillance/alerts/live-stream?last_event_id={prior_events}",
                        headers={
                            "X-Tenant-Id": CONTEXT.tenant_id,
                            "X-Project-Id": CONTEXT.project_id,
                            "X-Principal-Id": CONTEXT.principal_id,
                        },
                    ) as response:
                        if response.status_code != 200:
                            raise RuntimeError(f"local SSE endpoint returned HTTP {response.status_code}")
                        payload: dict[str, Any] | None = None
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                payload = json.loads(line.removeprefix("data: "))
                                break
                        if payload is None or payload.get("event_type") != "alert.triggered":
                            raise RuntimeError("local SSE endpoint did not replay the new alert event")
            finally:
                server.should_exit = True
                await asyncio.wait_for(server_task, timeout=10)
        finally:
            receiver.shutdown()
            receiver.server_close()
            if original_ca is None:
                os.environ.pop("SSL_CERT_FILE", None)
            else:
                os.environ["SSL_CERT_FILE"] = original_ca
    return {
        "https_webhook": {"deliveries": 1, "hmac_verified": True, "private_target_override": True},
        "sse": {"transport": "local_http", "replayed_event": "alert.triggered", "last_event_id": prior_events},
    }


async def _main() -> dict[str, Any]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="scenara-surveillance-simulation-") as temporary:
        runtime = await _build_runtime(Path(temporary))
        try:
            task, bindings, identity_id = await _prepare_50_camera_task(runtime, 50)
            pressure = await _run_pressure(runtime, task, bindings)
            delivery = await _run_webhook_and_sse(runtime, task, bindings[0], prior_events=len(bindings))
        finally:
            await runtime.close()
    return {
        "schema_version": "1.0",
        "status": "passed",
        "executed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "simulation_only": True,
        "not_production_evidence": [
            "Uses in-memory state and a synthetic embedding, not a physical camera or a production ANN index.",
            "The HTTPS receiver is local with a temporary self-signed certificate and private-target override.",
            "This does not certify 50 concurrent video decoders, external network reachability, or production SLA.",
        ],
        "identity_id": identity_id,
        "pressure": pressure,
        "delivery": delivery,
    }


def main() -> int:
    report = asyncio.run(_main())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
