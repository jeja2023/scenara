"""Checksum-verified Core-to-Data migration import.

The importer accepts only the versioned export produced by Core.  It never
opens a Core database and preserves the source identifiers, tenant and
project scope.  Replaying the same package is idempotent because records are
keyed by their immutable identifiers.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .app import DataStore, utc_now


class MigrationPackageError(ValueError):
    """The migration package is malformed or its checksums do not match."""


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MigrationPackageError(f"invalid JSON at {path.name}:{line_number}") from exc
        if not isinstance(value, dict):
            raise MigrationPackageError(f"migration row must be an object: {path.name}:{line_number}")
        rows.append(value)
    return rows


def verify_package(package_dir: str | Path) -> dict[str, Any]:
    root = Path(package_dir)
    manifest_path = root / "migration-manifest.json"
    checksums_path = root / "checksums.txt"
    if not manifest_path.is_file() or not checksums_path.is_file():
        raise MigrationPackageError("migration-manifest.json and checksums.txt are required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0":
        raise MigrationPackageError("unsupported migration schema version")
    declared: dict[str, str] = {}
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, separator, name = line.partition("  ")
        if not separator or len(digest) != 64:
            raise MigrationPackageError("invalid checksums.txt entry")
        declared[name] = digest
    for name, expected in declared.items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise MigrationPackageError(f"migration checksum mismatch: {name}")
    return manifest


def import_package(package_dir: str | Path, store: DataStore) -> dict[str, int | str]:
    root = Path(package_dir)
    manifest = verify_package(root)
    tenant_id = str(manifest.get("tenant_id", ""))
    project_id = str(manifest.get("project_id", ""))
    if not tenant_id or not project_id:
        raise MigrationPackageError("migration scope is required")
    imported: dict[str, Any] = {"datasets": 0, "versions": 0, "samples": 0, "annotation_tasks": 0, "providers": 0, "migration_id": str(manifest.get("migration_id", root.name))}

    for row in _jsonl(root / "datasets.jsonl"):
        row = {**row, "tenant_id": tenant_id, "project_id": project_id, "metadata": row.get("metadata", {})}
        dataset_id = str(row.get("dataset_id", ""))
        if dataset_id:
            store.save("dataset", row, dataset_id)
            imported["datasets"] += 1

    for row in _jsonl(root / "samples.jsonl"):
        row = {**row, "tenant_id": tenant_id, "project_id": project_id, "created_at": row.get("created_at") or utc_now()}
        sample_id = str(row.get("sample_id", ""))
        if sample_id:
            store.save("intake", row, sample_id)
            imported["samples"] += 1

    for row in _jsonl(root / "dataset-versions.jsonl"):
        version_id = str(row.get("version_id", ""))
        if not version_id:
            continue
        digest = str(row.get("source_manifest_sha256") or "")
        if len(digest) != 64:
            raise MigrationPackageError(f"invalid dataset version digest: {version_id}")
        item = {
            "dataset_version_id": version_id,
            "dataset_id": str(row.get("dataset_id", "")),
            "tenant_id": tenant_id,
            "project_id": project_id,
            "version": str(row.get("version", "")),
            "status": {"validated": "ready", "published": "published", "retired": "archived"}.get(str(row.get("status", "draft")), str(row.get("status", "draft"))),
            "manifest_sha256": digest,
            "sample_count": int(row.get("sample_count", 0)),
            "created_by": str(row.get("created_by", "data-migration-import")),
            "created_at": str(row.get("created_at") or utc_now()),
            "updated_at": str(row.get("published_at") or row.get("archived_at") or row.get("created_at") or utc_now()),
            "manifest_uri": f"data://migrations/{version_id}#sha256={digest}",
            "lineage_refs": [f"data://migrations/{version_id}/lineage#sha256={digest}"],
            "authorization_id": f"migration_{version_id}",
            "authorized_consumer_repository_ids": ["scenara-model"],
            "published_at": row.get("published_at"),
        }
        store.save("version", item, version_id)
        imported["versions"] += 1

    for row in _jsonl(root / "annotation-tasks.jsonl"):
        task_id = str(row.get("task_id", ""))
        if task_id:
            item = {**row, "tenant_id": tenant_id, "project_id": project_id, "task_metadata": row.get("metadata", {}), "assigned_to": row.get("assigned_to")}
            store.save("annotation", item, task_id)
            imported["annotation_tasks"] += 1

    for row in _jsonl(root / "annotation-providers.jsonl"):
        provider_id = str(row.get("provider_id", ""))
        if provider_id:
            item = {**row, "tenant_id": tenant_id, "project_id": project_id, "provider_type": row.get("provider_type", "")}
            store.save("annotation", item, provider_id)
            imported["providers"] += 1
    return imported


__all__ = ["MigrationPackageError", "import_package", "verify_package"]
