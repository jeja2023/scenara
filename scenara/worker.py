from __future__ import annotations

import argparse
import asyncio
import socket

from scenara.bootstrap import build_runtime
from scenara.infrastructure.queue import RedisRunQueue


async def run_worker(consumer: str, lane: str) -> None:
    runtime = build_runtime()
    if not isinstance(runtime.queue, RedisRunQueue):
        raise RuntimeError("worker requires SCENARA_QUEUE_BACKEND=redis")
    await runtime.open()
    try:
        await runtime.queue.consume_forever(consumer=consumer, lane=lane)
    finally:
        await runtime.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Scenara run worker")
    parser.add_argument("--consumer", default=socket.gethostname())
    parser.add_argument("--lane", choices=("batch", "stream"), default="batch")
    args = parser.parse_args()
    asyncio.run(run_worker(args.consumer, args.lane))


if __name__ == "__main__":
    main()
