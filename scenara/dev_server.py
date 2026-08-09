"""Run the local API with an event loop compatible with psycopg on Windows."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from typing import Any

import uvicorn


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动 Scenara 本地开发 API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--reload", action="store_true")
    return parser


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """Create the selector loop required by psycopg async connections on Windows."""

    return asyncio.SelectorEventLoop()


def main(argv: Sequence[str] | None = None) -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    args = _parser().parse_args(argv)
    loop: Any = "scenara.dev_server:selector_loop_factory" if sys.platform == "win32" else "auto"
    uvicorn.run(
        "scenara.server:app",
        host=args.host,
        port=args.port,
        env_file=args.env_file,
        reload=args.reload,
        loop=loop,
    )


if __name__ == "__main__":
    main()
