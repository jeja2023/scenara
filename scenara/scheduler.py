from __future__ import annotations

import argparse
import asyncio
import sys
import time

from scenara.bootstrap import build_runtime
from scenara.platform.retention import RetentionScheduler

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def run_once() -> tuple[int, int, int, int]:
    runtime = build_runtime()
    await runtime.open()
    try:
        if not hasattr(runtime.state, "expired_object_keys"):
            raise RuntimeError("当前状态后端不支持保留策略清理")
        scheduler = RetentionScheduler(runtime.state, runtime.objects)
        retained = await scheduler.sweep()
        expired_features = await runtime.features.delete_expired(time.time(), 1000)
        indexes = getattr(runtime, "indexes", None)
        if indexes is not None:
            await indexes.delete_expired(time.time(), 1000)
        delivered, failed = await runtime.webhooks.deliver_due()
        return retained, expired_features, delivered, failed
    finally:
        await runtime.close()


async def run_forever(interval_seconds: int) -> None:
    while True:
        await run_once()
        await asyncio.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scenara 治理调度器")
    parser.add_argument("--once", action="store_true", help="执行一次治理清理后退出")
    parser.add_argument("--interval-seconds", type=int, default=60)
    args = parser.parse_args()
    if args.interval_seconds < 60:
        parser.error("--interval-seconds 必须至少为 60 秒")
    asyncio.run(run_once() if args.once else run_forever(args.interval_seconds))


if __name__ == "__main__":
    main()
