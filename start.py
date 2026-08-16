"""Start the Scenara local development services."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

from scripts.prepare_runtime_state import prepare_runtime_state

ROOT = Path(__file__).resolve().parent


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="启动 Scenara 本地开发 API，可选同时启动 Console 开发服务器。"
    )
    parser.add_argument("--env-file", default=".env", help="环境文件路径，默认使用仓库根目录的 .env")
    parser.add_argument(
        "--no-create-env",
        action="store_true",
        help="环境文件不存在时不从 .env.example 自动创建，而是直接报错",
    )
    parser.add_argument("--host", default="127.0.0.1", help="API 监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000, help="API 监听端口，默认 8000")
    parser.add_argument("--reload", action="store_true", help="启用 Uvicorn 自动重载")
    parser.add_argument(
        "--local",
        action="store_true",
        help="临时使用 memory + local + inline 后端，不连接 PostgreSQL、Redis 或 S3",
    )
    parser.add_argument(
        "--with-console",
        action="store_true",
        help="同时启动 Console Vite 开发服务器",
    )
    parser.add_argument(
        "--console-port",
        type=int,
        default=5173,
        help="Console 开发服务器端口，默认 5173",
    )
    return parser


def _resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


def _ensure_env_file(env_file: Path, *, create: bool) -> bool:
    if env_file.exists():
        return False
    if not create:
        raise FileNotFoundError(
            f"环境文件不存在：{env_file}；请复制 .env.example，或移除 --no-create-env"
        )
    template = ROOT / ".env.example"
    if not template.exists():
        raise FileNotFoundError(f"环境模板不存在：{template}")
    env_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, env_file)
    return True


def _dotenv_value(env_file: Path, key: str) -> str | None:
    """Read one dotenv value for local directory preparation without overriding the process env."""

    value = os.environ.get(key)
    if value:
        return value
    try:
        from dotenv import dotenv_values
    except ImportError:
        return None
    parsed = dotenv_values(env_file)
    candidate = parsed.get(key)
    return candidate if isinstance(candidate, str) and candidate else None


def _dotenv_environment(env_file: Path) -> dict[str, str]:
    """Load string-valued dotenv entries for child processes.

    The API receives ``--env-file`` through Uvicorn, but worker subprocesses
    are started directly and otherwise would silently fall back to inline
    queue/memory defaults.
    """

    try:
        from dotenv import dotenv_values
    except ImportError:
        return {}
    return {
        key: value
        for key, value in dotenv_values(env_file).items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _api_command(args: argparse.Namespace, env_file: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "scenara.dev_server",
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--env-file",
        str(env_file),
    ]
    if args.reload:
        command.append("--reload")
    return command


def _console_command(args: argparse.Namespace) -> list[str]:
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if npm is None:
        raise RuntimeError("未找到 npm；不使用 --with-console 即可只启动 Python API")
    return [
        npm,
        "run",
        "dev",
        "-w",
        "@scenara/console",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        str(args.console_port),
    ]


def _worker_command(env_file: Path, *, lane: str, consumer: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "scenara.worker",
        "--consumer",
        consumer,
        "--lane",
        lane,
        "--env-file",
        str(env_file),
    ]


def _worker_specs(queue_backend: str) -> tuple[tuple[str, str], ...]:
    if queue_backend.strip().lower() != "redis":
        return ()
    return (
        ("batch", "local-batch"),
        ("stream", "local-stream"),
    )


def _tcp_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def _redis_server_path(runtime_root: Path) -> Path | None:
    executable = "redis-server.exe" if os.name == "nt" else "redis-server"
    bundled = sorted(runtime_root.glob(f"redis-*/**/{executable}"), reverse=True)
    if bundled:
        return bundled[0]
    installed = shutil.which(executable)
    return Path(installed) if installed else None


def _minio_server_path(runtime_root: Path) -> Path | None:
    executable = "minio.exe" if os.name == "nt" else "minio"
    bundled = sorted(runtime_root.glob(f"minio-*/**/{executable}"), reverse=True)
    if bundled:
        return bundled[0]
    installed = shutil.which(executable)
    return Path(installed) if installed else None


def _start_local_minio(env_file: Path, runtime_root: Path) -> subprocess.Popen[bytes] | None:
    if (_dotenv_value(env_file, "SCENARA_OBJECT_BACKEND") or "local").lower() != "s3":
        return None

    s3_url = _dotenv_value(env_file, "SCENARA_S3_ENDPOINT_URL") or "http://127.0.0.1:9000"
    parsed = urlsplit(s3_url)
    host = parsed.hostname
    if host is None:
        raise RuntimeError(f"S3 端点地址无效：{s3_url}")
    try:
        port = parsed.port or 9000
    except ValueError as exc:
        raise RuntimeError(f"S3 端点端口无效：{s3_url}") from exc

    if _tcp_open(host, port):
        return None
    if host.lower() not in {"127.0.0.1", "localhost", "::1"}:
        return None

    executable = _minio_server_path(runtime_root)
    if executable is None:
        raise RuntimeError(
            f"MinIO 未运行：{host}:{port}；未找到本地 minio，可使用 --local 跳过 S3"
        )

    data_dir = runtime_root / "minio-data"
    logs_dir = runtime_root / "logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    access_key = _dotenv_value(env_file, "SCENARA_S3_ACCESS_KEY") or "minioadmin"
    secret_key = _dotenv_value(env_file, "SCENARA_S3_SECRET_KEY") or "minioadmin"
    minio_env = os.environ.copy()
    minio_env["MINIO_ROOT_USER"] = access_key
    minio_env["MINIO_ROOT_PASSWORD"] = secret_key

    log_path = logs_dir / f"minio-{port}.log"
    log_file = open(log_path, "a", encoding="utf-8")
    command = [
        str(executable),
        "server",
        str(data_dir),
        "--address",
        f":{port}",
        "--console-address",
        f":{port + 1}",
    ]
    process = subprocess.Popen(
        command,
        cwd=executable.parent,
        env=minio_env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if _tcp_open(host, port):
            print(f"MinIO 已自动启动：{host}:{port}（进程 {process.pid}）")
            return process
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(
                f"MinIO 启动失败，状态码：{exit_code}；日志：{log_path}"
            )
        time.sleep(0.1)

    _stop(process)
    raise RuntimeError(f"MinIO 启动超时：{host}:{port}；日志：{log_path}")


def _start_local_redis(env_file: Path, runtime_root: Path) -> subprocess.Popen[bytes] | None:
    if (_dotenv_value(env_file, "SCENARA_QUEUE_BACKEND") or "inline").lower() != "redis":
        return None

    redis_url = _dotenv_value(env_file, "SCENARA_REDIS_URL") or "redis://127.0.0.1:6379/0"
    parsed = urlsplit(redis_url)
    host = parsed.hostname
    if host is None:
        raise RuntimeError(f"Redis 地址无效：{redis_url}")
    try:
        port = parsed.port or 6379
    except ValueError as exc:
        raise RuntimeError(f"Redis 地址端口无效：{redis_url}") from exc

    if _tcp_open(host, port):
        return None
    if host.lower() not in {"127.0.0.1", "localhost", "::1"}:
        return None
    if parsed.password:
        raise RuntimeError("本地 Redis 未运行，启动器暂不自动创建带密码的 Redis 实例")

    executable = _redis_server_path(runtime_root)
    if executable is None:
        raise RuntimeError(
            f"Redis 未运行：{host}:{port}；未找到本地 redis-server，可使用 --local 跳过 Redis"
        )

    data_dir = runtime_root / "redis-data"
    logs_dir = runtime_root / "logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    bind_host = "127.0.0.1" if host.lower() == "localhost" else host
    command = [
        str(executable),
        "--bind",
        bind_host,
        "--port",
        str(port),
        "--dir",
        str(data_dir),
        "--dbfilename",
        f"dump-{port}.rdb",
        "--appendonly",
        "yes",
        "--appendfilename",
        f"appendonly-{port}.aof",
        "--maxmemory-policy",
        "noeviction",
        "--protected-mode",
        "yes",
        "--logfile",
        str(logs_dir / f"redis-{port}.log"),
    ]
    process = subprocess.Popen(
        command,
        cwd=executable.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if _tcp_open(host, port):
            print(f"Redis 已自动启动：{host}:{port}（进程 {process.pid}）")
            return process
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(
                f"Redis 启动失败，状态码：{exit_code}；日志：{logs_dir / f'redis-{port}.log'}"
            )
        time.sleep(0.1)

    _stop(process)
    raise RuntimeError(f"Redis 启动超时：{host}:{port}；日志：{logs_dir / f'redis-{port}.log'}")


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _run(args: argparse.Namespace) -> int:
    env_file = _resolve_path(args.env_file)
    created = _ensure_env_file(env_file, create=not args.no_create_env)
    if created:
        print(f"已从 .env.example 创建环境文件：{env_file}")

    runtime_state = _dotenv_value(env_file, "SCENARA_DATA_DIR") or "runtime-state"
    runtime_root = _resolve_path(runtime_state)
    prepared = prepare_runtime_state(runtime_root)
    print(f"运行目录已准备：{prepared[0].parent}")

    child_env = _dotenv_environment(env_file)
    child_env.update(os.environ)
    if args.local:
        child_env.update(
            {
                "SCENARA_PROFILE": "development",
                "SCENARA_STATE_BACKEND": "memory",
                "SCENARA_OBJECT_BACKEND": "local",
                "SCENARA_QUEUE_BACKEND": "inline",
            }
        )
    child_env.setdefault("SCENARA_DEV_API_URL", f"http://127.0.0.1:{args.port}")
    console_command = _console_command(args) if args.with_console else None
    queue_backend = child_env.get("SCENARA_QUEUE_BACKEND", "inline").strip().lower()
    worker_specs = tuple(
        (lane, f"{consumer}-{args.port}")
        for lane, consumer in _worker_specs(queue_backend)
    )
    processes: list[subprocess.Popen[bytes]] = []
    console: subprocess.Popen[bytes] | None = None
    workers: list[tuple[str, subprocess.Popen[bytes]]] = []
    try:
        if not args.local:
            minio = _start_local_minio(env_file, runtime_root)
            if minio is not None:
                processes.append(minio)
            redis = _start_local_redis(env_file, runtime_root)
            if redis is not None:
                processes.append(redis)

        api = subprocess.Popen(_api_command(args, env_file), cwd=ROOT, env=child_env)
        processes.append(api)
        for lane, consumer in worker_specs:
            worker = subprocess.Popen(
                _worker_command(env_file, lane=lane, consumer=consumer),
                cwd=ROOT,
                env=child_env,
            )
            workers.append((lane, worker))
            processes.append(worker)
        if console_command is not None:
            console = subprocess.Popen(console_command, cwd=ROOT, env=child_env)
            processes.append(console)
    except BaseException:
        for process in reversed(processes):
            _stop(process)
        raise

    print(f"API: http://{args.host}:{args.port}")
    if args.local:
        print("后端：memory + local + inline（未连接外部服务）")
    elif workers:
        print("Worker：batch + stream（Redis 队列消费者已启动）")
    print(f"Console: http://127.0.0.1:{args.console_port}/console/" if console else "Console: /console/")
    print("按 Ctrl+C 停止本地开发服务。")
    try:
        while True:
            api_code = api.poll()
            if api_code is not None:
                if console is not None:
                    _stop(console)
                return api_code
            if console is not None:
                console_code = console.poll()
                if console_code is not None:
                    print(f"Console 已退出，状态码：{console_code}", file=sys.stderr)
                    _stop(api)
                    return console_code or 1
            for lane, worker in workers:
                worker_code = worker.poll()
                if worker_code is not None:
                    print(f"{lane} worker 已退出，状态码：{worker_code}", file=sys.stderr)
                    _stop(api)
                    if console is not None:
                        _stop(console)
                    return worker_code or 1
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n正在停止本地开发服务……")
        return 0
    finally:
        for process in reversed(processes):
            _stop(process)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
