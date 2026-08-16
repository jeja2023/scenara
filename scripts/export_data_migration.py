"""Create a checksummed Core-to-Data migration package."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from scenara import __version__
from scenara.bootstrap import build_runtime
from scenara.platform.data_migration import export_data_migration_package


async def _run(args: argparse.Namespace) -> int:
    runtime = build_runtime()
    await runtime.open()
    try:
        summary = await export_data_migration_package(
            state=runtime.state,
            control_plane=runtime.control_plane,
            feedback=runtime.feedback,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            output_dir=args.output.resolve(),
            source_version=__version__,
        )
    finally:
        await runtime.close()
    print(
        json.dumps(
            {"package_path": str(summary.package_path), "record_counts": summary.record_counts, "files": summary.files},
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a checksummed scenara-data migration package")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
