"""Verify the local RTSP and RTMP ingest path without Docker or a camera.

FFmpeg produces a synthetic live test pattern, MediaMTX relays it on loopback,
and Scenara's OpenCV decoder samples a two-second stream segment.  This is a
protocol integration simulation only; it does not certify a physical camera,
network loss, or multi-decoder capacity.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


OUTPUT = ROOT / "runtime-state" / "qualification" / "stream-protocol-local-simulation.json"
MEDIAMTX = ROOT / "runtime-state" / "mediamtx-1.20.1" / "mediamtx.exe"
FFMPEG = ROOT / "runtime-state" / "ffmpeg-master-latest-win64-gpl" / "ffmpeg-master-latest-win64-gpl" / "bin" / "ffmpeg.exe"
DECODE_PROGRAM = """
import json
import sys
from scenara.platform.media_batch import MediaInput, decode_media
from scenara.platform.models import MediaKind
decoded = decode_media(
    MediaInput(kind=MediaKind.STREAM, content_type='video/h264', source_url=sys.argv[1]),
    sample_interval_ms=300,
    connect_timeout_ms=5000,
    read_timeout_ms=5000,
    stream_segment_duration_ms=2000,
    frame_max_edge=320,
)
print(json.dumps({
    'sampled_units': len(decoded.units),
    'termination_reason': decoded.termination_reason,
    'metadata': decoded.metadata.model_dump(mode='json'),
}, sort_keys=True))
"""


def _wait_for_port(port: int, *, timeout_seconds: float = 10) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"MediaMTX did not listen on port {port}")
            time.sleep(0.05)


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _tail(path: Path, *, characters: int = 2_000) -> str:
    if not path.is_file():
        return "<no log output>"
    return path.read_text(encoding="utf-8", errors="replace")[-characters:]


def _publisher(url: str, protocol: str) -> subprocess.Popen[bytes]:
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-loglevel",
        "error",
        "-re",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=320x240:rate=10",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "baseline",
        "-preset",
        "ultrafast",
        "-tune",
        "zerolatency",
        "-g",
        "10",
        "-x264-params",
        "repeat-headers=1",
    ]
    if protocol == "rtsp":
        command.extend(["-f", "rtsp", "-rtsp_transport", "tcp", url])
    else:
        command.extend(["-f", "flv", url])
    return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _decode(protocol: str, url: str) -> dict[str, Any]:
    publisher = _publisher(url, protocol)
    try:
        time.sleep(1.5)
        if publisher.poll() is not None:
            output = publisher.stdout.read().decode("utf-8", errors="replace") if publisher.stdout else ""
            raise RuntimeError(f"FFmpeg {protocol} publisher terminated early: {output[-1_000:]}")
        started = time.perf_counter()
        environment = os.environ.copy()
        if protocol == "rtsp":
            # Windows loopback UDP can be filtered by endpoint security software.
            # This must be set before cv2 imports, so invoke the product decoder
            # in a fresh local Python process over RTSP interleaved TCP.
            environment["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        decoded_process = subprocess.run(
            [sys.executable, "-c", DECODE_PROGRAM, url],
            cwd=ROOT,
            env=environment,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=90,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1_000, 3)
        if decoded_process.returncode != 0:
            raise RuntimeError(f"Scenara {protocol} decoder failed: {decoded_process.stderr[-2_000:]}")
        decoded = json.loads(decoded_process.stdout.strip().splitlines()[-1])
        if not decoded["sampled_units"]:
            raise RuntimeError(f"Scenara decoder read no {protocol} frames")
        return {
            "url_scheme": protocol,
            "sampled_units": decoded["sampled_units"],
            "decoder_elapsed_ms": elapsed_ms,
            "termination_reason": decoded["termination_reason"],
            "metadata": decoded["metadata"],
        }
    finally:
        _stop(publisher)
        if publisher.stdout is not None:
            publisher.stdout.close()


def main() -> int:
    if not MEDIAMTX.is_file() or not FFMPEG.is_file():
        raise RuntimeError(
            "local MediaMTX/FFmpeg binaries are missing; install the checksum-verified runtime-state copies before running"
        )
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="scenara-stream-protocol-") as temporary:
        config = Path(temporary) / "mediamtx.yml"
        config.write_text(
            "\n".join(
                [
                    "logLevel: debug",
                    "logDestinations: [stdout]",
                    "rtsp: true",
                    "rtspAddress: 127.0.0.1:18554",
                    "rtspTransports: [udp, tcp]",
                    "rtmp: true",
                    "rtmpAddress: 127.0.0.1:11935",
                    "hls: false",
                    "webrtc: false",
                    "srt: false",
                    "paths:",
                    "  all: {}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        relay_log_path = Path(temporary) / "mediamtx.log"
        with relay_log_path.open("wb") as relay_log:
            relay = subprocess.Popen(
                [str(MEDIAMTX), str(config)],
                cwd=temporary,
                stdout=relay_log,
                stderr=subprocess.STDOUT,
            )
            try:
                _wait_for_port(18_554)
                _wait_for_port(11_935)
                protocols = {
                    "rtsp": _decode("rtsp", "rtsp://127.0.0.1:18554/local-simulation-rtsp"),
                    "rtmp": _decode("rtmp", "rtmp://127.0.0.1:11935/local-simulation-rtmp"),
                }
            except Exception as exc:
                raise RuntimeError(f"stream protocol simulation failed; MediaMTX log:\n{_tail(relay_log_path)}") from exc
            finally:
                _stop(relay)
    report = {
        "schema_version": "1.0",
        "status": "passed",
        "executed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "simulation_only": True,
        "not_production_evidence": [
            "The publisher is a local FFmpeg test pattern, not a physical RTSP/RTMP camera.",
            "The relay and decoder communicate only through loopback; WAN/NAT, packet loss, and camera firmware are not exercised.",
            "This uses one decoder per protocol and does not certify the 50-source capacity target.",
        ],
        "protocols": protocols,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
