"""Create the local runtime-state layout without touching existing files."""

from __future__ import annotations

import os
from pathlib import Path

RUNTIME_DIRECTORIES = (
    "logs",
    "objects",
    "video-job-inputs",
    "task-queue",
    "stream-worker-locks",
    "delivery-evidence",
)


def prepare_runtime_state(root: Path) -> tuple[Path, ...]:
    """Create runtime directories and return the paths that were ensured."""
    paths = tuple(root / relative_path for relative_path in RUNTIME_DIRECTORIES)
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
    return paths


def main() -> None:
    root = Path(os.getenv("RUNTIME_STATE_DIR", "runtime-state")).expanduser()
    prepare_runtime_state(root)
    print(f"runtime state ready: {root.resolve()}")


if __name__ == "__main__":
    main()
