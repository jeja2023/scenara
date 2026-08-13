from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scenara.bootstrap import build_runtime  # noqa: E402
from scenara.infrastructure.object_store import S3ObjectStore  # noqa: E402
from scenara.infrastructure.postgres_state import PostgresStateStore  # noqa: E402
from scenara.infrastructure.queue import RedisRunQueue  # noqa: E402
from scenara.queue_recovery import rebuild_redis_run_queue  # noqa: E402


async def rebuild() -> dict[str, int]:
    runtime = build_runtime()
    if not isinstance(runtime.state, PostgresStateStore):
        raise RuntimeError("queue recovery requires the PostgreSQL state backend")
    if not isinstance(runtime.objects, S3ObjectStore):
        raise RuntimeError("queue recovery requires the S3/MinIO object backend")
    if not isinstance(runtime.queue, RedisRunQueue):
        raise RuntimeError("queue recovery requires the Redis queue backend")
    await runtime.open()
    try:
        return asdict(await rebuild_redis_run_queue(runtime.state, runtime.objects, runtime.queue))
    finally:
        await runtime.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild empty Redis Run streams from PostgreSQL and MinIO",
    )
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()
    if args.env_file:
        try:
            from dotenv import load_dotenv
        except ImportError as exc:  # pragma: no cover - required runtime dependency
            raise RuntimeError("python-dotenv is required when --env-file is used") from exc
        load_dotenv(args.env_file, override=False)
    print(json.dumps(asyncio.run(rebuild()), sort_keys=True))


if __name__ == "__main__":
    main()
