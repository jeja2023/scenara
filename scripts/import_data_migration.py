"""Import a verified Core-to-Data migration package into the Data adapter."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scenara_data.app import DataStore  # noqa: E402
from scenara_data.migration import import_package  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--state-path", type=Path, default=None)
    args = parser.parse_args()
    state_path = args.state_path or os.getenv("SCENARA_DATA_STATE_PATH") or "runtime-state/scenara-data.db"
    store = DataStore(state_path)
    try:
        print(json.dumps(import_package(args.package, store), ensure_ascii=False, sort_keys=True))
    finally:
        store.close()


if __name__ == "__main__":
    main()
