from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = ROOT / "sdk" / "python"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from scenara_sdk import ScenaraClient  # noqa: E402 - local SDK path is resolved above


def _client() -> ScenaraClient:
    return ScenaraClient(
        os.getenv("SCENARA_BASE_URL", "http://127.0.0.1:8000"),
        token=os.getenv("SCENARA_API_TOKEN") or None,
        tenant_id=os.getenv("SCENARA_TENANT_ID", "default"),
        project_id=os.getenv("SCENARA_PROJECT_ID", "default"),
        timeout=float(os.getenv("SCENARA_TIMEOUT", "30")),
    )


def run_demo(args: argparse.Namespace) -> dict[str, Any]:
    base_url = os.getenv("SCENARA_BASE_URL", "http://127.0.0.1:8000")
    planned = ["list_domains", "list_pipelines"]
    if args.image:
        planned.append(f"parse_image:{args.domain}")
    if args.dry_run:
        return {"dry_run": True, "base_url": base_url, "planned_steps": planned}

    with _client() as client:
        payload: dict[str, Any] = {
            "dry_run": False,
            "domains": client.list_domains(),
            "pipelines": client.list_pipelines(),
        }
        if args.image:
            payload["parse"] = client.parse_image(args.image, domain=args.domain)
        return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Scenara Python SDK example.")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--domain", choices=("portrait", "ocr"), default="portrait")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_demo(args), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
