from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scenara.server import create_app  # noqa: E402


def render() -> str:
    document = create_app().openapi()
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export or verify the Scenara OpenAPI contract")
    parser.add_argument("--output", type=Path, default=Path("docs/openapi.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != expected:
            raise SystemExit(f"OpenAPI contract drifted; run {Path(__file__).as_posix()}")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(expected, encoding="utf-8")


if __name__ == "__main__":
    main()
