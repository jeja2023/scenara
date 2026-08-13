from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release_gate import REQUIRED_EVIDENCE_TYPES, validate_entry  # noqa: E402

REPORT_FIELDS = {
    "schema_version",
    "evidence_type",
    "status",
    "executed_at",
    "target",
    "release_identity",
    "metadata",
}


def _read_object(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{description} must be readable UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{description} must be a JSON object: {path}")
    return value


def _render(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def record_evidence(
    input_path: Path,
    manifest_path: Path,
    *,
    root: Path = ROOT,
) -> Path:
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    report = _read_object(input_path.resolve(), "release evidence report")
    manifest = _read_object(manifest_path, "release evidence manifest")

    if set(report) != REPORT_FIELDS:
        missing = sorted(REPORT_FIELDS - set(report))
        extra = sorted(set(report) - REPORT_FIELDS)
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if extra:
            details.append("unexpected: " + ", ".join(extra))
        raise ValueError(
            "report must contain exactly the release evidence fields (" + "; ".join(details) + ")"
        )
    if report.get("schema_version") != "1.0":
        raise ValueError("report schema_version must be 1.0")
    evidence_type = report.get("evidence_type")
    if evidence_type not in REQUIRED_EVIDENCE_TYPES:
        raise ValueError(f"unknown evidence type: {evidence_type}")
    if report.get("status") != "passed":
        raise ValueError("only completed passed evidence can be recorded")
    release_identity = manifest.get("release_identity")
    if report.get("release_identity") != release_identity:
        raise ValueError("report release identity does not match the manifest")

    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("release evidence manifest entries must be a list")
    matching = [
        index
        for index, entry in enumerate(entries)
        if isinstance(entry, dict) and entry.get("evidence_type") == evidence_type
    ]
    if len(matching) != 1:
        raise ValueError(f"manifest must contain exactly one {evidence_type} entry")
    current_entry = entries[matching[0]]
    if not isinstance(current_entry, dict) or current_entry.get("status") != "pending":
        raise ValueError(f"{evidence_type} evidence is already completed")

    report_relative = Path("docs/release/evidence/reports") / (
        f"{str(evidence_type).replace('_', '-')}.json"
    )
    report_path = root / report_relative
    report_content = _render(report)
    entry = {key: value for key, value in report.items() if key != "schema_version"}
    entry["report"] = report_relative.as_posix()
    entry["sha256"] = hashlib.sha256(report_content).hexdigest()

    previous_report = report_path.read_bytes() if report_path.is_file() else None
    _atomic_write(report_path, report_content)
    errors = validate_entry(entry, release_identity=release_identity, root=root)
    if errors:
        if previous_report is None:
            report_path.unlink(missing_ok=True)
        else:
            _atomic_write(report_path, previous_report)
        raise ValueError("invalid release evidence:\n" + "\n".join(errors))

    entries[matching[0]] = entry
    _atomic_write(manifest_path, _render(manifest))
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record a completed objective release evidence report"
    )
    parser.add_argument(
        "input",
        type=Path,
        help="UTF-8 JSON report produced by the qualification run",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "docs/release/evidence/manifest.json",
    )
    args = parser.parse_args()
    try:
        path = record_evidence(args.input, args.manifest)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(path.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
