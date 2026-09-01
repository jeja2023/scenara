"""Fail closed when a maintained source file exceeds the size budget."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_CODE_LINES = 1_500
CODE_SUFFIXES = frozenset({".js", ".jsx", ".ps1", ".py", ".sh", ".ts", ".tsx", ".vue"})
EXCLUDED_PARTS = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        "dist",
        "node_modules",
        "playwright-report",
        "runtime-state",
    }
)


def source_files(root: Path = ROOT) -> list[Path]:
    collected: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in EXCLUDED_PARTS
            and not (d.startswith(".") and d not in {".github"})
        ]
        for f in filenames:
            path = Path(dirpath) / f
            if path.suffix in CODE_SUFFIXES:
                try:
                    rel = path.relative_to(root)
                    if not any(part in EXCLUDED_PARTS for part in rel.parts):
                        collected.append(path)
                except ValueError:
                    collected.append(path)
    return sorted(collected)


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def violations(root: Path = ROOT, limit: int = MAX_CODE_LINES) -> list[str]:
    return [
        f"code size limit ({limit} lines) exceeded: {path.relative_to(root)} ({line_count(path)} lines)"
        for path in source_files(root)
        if line_count(path) > limit
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the Scenara source-file size budget"
    )
    parser.add_argument("--limit", type=int, default=MAX_CODE_LINES)
    args = parser.parse_args()
    if args.limit < 1:
        raise SystemExit("code size limit must be positive")
    errors = violations(limit=args.limit)
    if errors:
        raise SystemExit("\n".join(errors))


if __name__ == "__main__":
    main()
