import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import start


def _redis_env(path: Path, *, url: str = "redis://127.0.0.1:6380/0") -> None:
    path.write_text(
        f"SCENARA_QUEUE_BACKEND=redis\nSCENARA_REDIS_URL={url}\n",
        encoding="utf-8",
    )


def _minio_env(path: Path, *, endpoint: str = "http://127.0.0.1:9000") -> None:
    path.write_text(
        f"SCENARA_OBJECT_BACKEND=s3\nSCENARA_S3_ENDPOINT_URL={endpoint}\n",
        encoding="utf-8",
    )


def _qdrant_env(path: Path, *, endpoint: str = "http://127.0.0.1:6333") -> None:
    path.write_text(f"SCENARA_QDRANT_URL={endpoint}\n", encoding="utf-8")


def test_existing_minio_is_reused(tmp_path: Path, monkeypatch: Any) -> None:
    env_file = tmp_path / ".env"
    _minio_env(env_file)
    monkeypatch.delenv("SCENARA_OBJECT_BACKEND", raising=False)
    monkeypatch.delenv("SCENARA_S3_ENDPOINT_URL", raising=False)
    monkeypatch.setattr(start, "_tcp_open", lambda _host, _port: True)

    assert start._start_local_minio(env_file, tmp_path) is None


def test_bundled_minio_is_started_for_local_endpoint(tmp_path: Path, monkeypatch: Any) -> None:
    env_file = tmp_path / ".env"
    _minio_env(env_file)
    binary_name = "minio.exe" if os.name == "nt" else "minio"
    executable = tmp_path / "minio-native" / binary_name
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.delenv("SCENARA_OBJECT_BACKEND", raising=False)
    monkeypatch.delenv("SCENARA_S3_ENDPOINT_URL", raising=False)
    connectivity = iter((False, True))
    monkeypatch.setattr(start, "_tcp_open", lambda _host, _port: next(connectivity))
    captured: dict[str, Any] = {}
    process = SimpleNamespace(pid=43, poll=lambda: None)

    def popen(command: list[str], **kwargs: Any) -> Any:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return process

    monkeypatch.setattr(start.subprocess, "Popen", popen)

    assert start._start_local_minio(env_file, tmp_path) is process
    assert captured["command"][:3] == [
        str(executable),
        "server",
        str(tmp_path / "minio-data"),
    ]
    assert "--address" in captured["command"]
    assert "--console-address" in captured["command"]
    assert captured["kwargs"]["cwd"] == executable.parent


def test_existing_redis_is_reused(tmp_path: Path, monkeypatch: Any) -> None:
    env_file = tmp_path / ".env"
    _redis_env(env_file)
    monkeypatch.delenv("SCENARA_QUEUE_BACKEND", raising=False)
    monkeypatch.delenv("SCENARA_REDIS_URL", raising=False)
    monkeypatch.setattr(start, "_tcp_open", lambda _host, _port: True)

    assert start._start_local_redis(env_file, tmp_path) is None


def test_bundled_redis_is_started_for_local_endpoint(tmp_path: Path, monkeypatch: Any) -> None:
    env_file = tmp_path / ".env"
    _redis_env(env_file)
    binary_name = "redis-server.exe" if os.name == "nt" else "redis-server"
    executable = tmp_path / "redis-7.4.10" / "bin" / binary_name
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.delenv("SCENARA_QUEUE_BACKEND", raising=False)
    monkeypatch.delenv("SCENARA_REDIS_URL", raising=False)
    connectivity = iter((False, True))
    monkeypatch.setattr(start, "_tcp_open", lambda _host, _port: next(connectivity))
    captured: dict[str, Any] = {}
    process = SimpleNamespace(pid=42, poll=lambda: None)

    def popen(command: list[str], **kwargs: Any) -> Any:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return process

    monkeypatch.setattr(start.subprocess, "Popen", popen)

    assert start._start_local_redis(env_file, tmp_path) is process
    assert captured["command"][:5] == [
        str(executable),
        "--bind",
        "127.0.0.1",
        "--port",
        "6380",
    ]
    assert "--appendonly" in captured["command"]
    assert captured["kwargs"]["cwd"] == executable.parent


def test_bundled_qdrant_is_started_for_local_endpoint(tmp_path: Path, monkeypatch: Any) -> None:
    env_file = tmp_path / ".env"
    _qdrant_env(env_file)
    binary_name = "qdrant.exe" if os.name == "nt" else "qdrant"
    executable = tmp_path / "qdrant-1.18.2" / binary_name
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.delenv("SCENARA_QDRANT_URL", raising=False)
    connectivity = iter((False, True))
    monkeypatch.setattr(start, "_tcp_open", lambda _host, _port: next(connectivity))
    captured: dict[str, Any] = {}
    process = SimpleNamespace(pid=44, poll=lambda: None)

    def popen(command: list[str], **kwargs: Any) -> Any:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return process

    monkeypatch.setattr(start.subprocess, "Popen", popen)

    assert start._start_local_qdrant(env_file, tmp_path) is process
    assert captured["command"][:2] == [str(executable), "--config-path"]
    assert "--disable-telemetry" in captured["command"]
    assert captured["kwargs"]["cwd"] == executable.parent


def test_dotenv_environment_preserves_string_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SCENARA_QUEUE_BACKEND=redis\nSCENARA_REDIS_URL=redis://127.0.0.1:6380/0\n", encoding="utf-8")

    assert start._dotenv_environment(env_file) == {
        "SCENARA_QUEUE_BACKEND": "redis",
        "SCENARA_REDIS_URL": "redis://127.0.0.1:6380/0",
    }


def test_worker_command_passes_env_file_and_lane(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"

    command = start._worker_command(env_file, lane="batch", consumer="local-batch-8000")

    assert command[-4:] == [
        "--lane",
        "batch",
        "--env-file",
        str(env_file),
    ]


def test_worker_specs_follow_queue_backend() -> None:
    assert start._worker_specs("redis") == (("batch", "local-batch"), ("stream", "local-stream"))
    assert start._worker_specs("inline") == ()
