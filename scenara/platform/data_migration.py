"""Auditable export of Core-owned migration inputs for ``scenara-data``.

The exporter never connects to a Data database.  It writes a self-contained,
checksummed package that Data can validate and import idempotently.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scenara.platform.control_plane import ControlPlaneService
from scenara.platform.feedback import FeedbackService
from scenara.platform.models import PrincipalContext
from scenara.platform.store import StateStore


@dataclass(frozen=True, slots=True)
class MigrationExportSummary:
    package_path: Path
    record_counts: dict[str, int]
    files: dict[str, str]


async def export_data_migration_package(
    *,
    state: StateStore,
    control_plane: ControlPlaneService,
    feedback: FeedbackService,
    tenant_id: str,
    project_id: str,
    output_dir: Path,
    source_version: str,
) -> MigrationExportSummary:
    """Export Dataset/Annotation inputs while retaining Core media ownership."""

    if output_dir.exists():
        raise ValueError(f"migration output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    context = PrincipalContext(
        tenant_id=tenant_id,
        project_id=project_id,
        principal_id="data-migration-export",
        scopes=frozenset({"*"}),
        product_ids=frozenset({"*"}),
    )
    datasets = await _all_datasets(state, tenant_id, project_id)
    versions = []
    for dataset in datasets:
        versions.extend(await _all_versions(state, tenant_id, project_id, dataset.dataset_id))
    providers = await control_plane.list_annotation_providers(context)
    tasks = await control_plane.list_annotation_tasks(context)
    manifests = await feedback.list_manifests(context)

    asset_ids = {asset_id for version in versions for asset_id in version.asset_ids}
    object_references: list[dict[str, Any]] = []
    for asset_id in sorted(asset_ids):
        asset = await state.get_asset(tenant_id, project_id, asset_id)
        if asset is None:
            object_references.append({"asset_id": asset_id, "status": "missing"})
            continue
        object_references.append(
            {
                "asset_id": asset.asset_id,
                "source_repository": "scenara",
                "source_resource_type": "media_asset",
                "object_reference": f"{asset.object_key}#sha256={asset.sha256}",
                "sha256": asset.sha256,
                "size_bytes": asset.size_bytes,
                "content_type": asset.content_type,
                "status": "available" if asset.deleted_at is None and asset.original_deleted_at is None else "unavailable",
            }
        )
    audits = await state.audit_events(tenant_id, project_id, limit=None)
    documents: dict[str, list[dict[str, Any]]] = {
        "datasets.jsonl": [item.model_dump(mode="json") for item in datasets],
        "dataset-versions.jsonl": [item.model_dump(mode="json") for item in versions],
        "annotation-providers.jsonl": [item.model_dump(mode="json") for item in providers],
        "annotation-tasks.jsonl": [item.model_dump(mode="json") for item in tasks],
        "hard-sample-manifests.jsonl": [item.model_dump(mode="json") for item in manifests],
        "object-references.jsonl": object_references,
        "audit-references.jsonl": [asdict(item) for item in audits],
    }
    file_hashes: dict[str, str] = {}
    record_counts: dict[str, int] = {}
    for name, rows in documents.items():
        encoded = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows).encode(
            "utf-8"
        )
        (output_dir / name).write_bytes(encoded)
        file_hashes[name] = hashlib.sha256(encoded).hexdigest()
        record_counts[name.removesuffix(".jsonl")] = len(rows)
    checksums = "".join(f"{digest}  {name}\n" for name, digest in sorted(file_hashes.items()))
    (output_dir / "checksums.txt").write_text(checksums, encoding="utf-8", newline="\n")
    migration_manifest = {
        "schema_version": "1.0",
        "source_repository": "scenara",
        "source_version": source_version,
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": {"tenant_id": tenant_id, "project_id": project_id},
        "record_counts": record_counts,
        "files": file_hashes,
        "exporter": "scenara.platform.data_migration",
    }
    manifest_bytes = json.dumps(migration_manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    (output_dir / "migration-manifest.json").write_bytes(manifest_bytes)
    return MigrationExportSummary(package_path=output_dir, record_counts=record_counts, files=file_hashes)


async def _all_datasets(state: StateStore, tenant_id: str, project_id: str) -> list[Any]:
    rows: list[Any] = []
    offset = 0
    while True:
        page = await state.list_datasets(tenant_id, project_id, offset=offset, limit=200)
        rows.extend(page)
        if len(page) < 200:
            return rows
        offset += len(page)


async def _all_versions(state: StateStore, tenant_id: str, project_id: str, dataset_id: str) -> list[Any]:
    rows: list[Any] = []
    offset = 0
    while True:
        page = await state.list_dataset_versions(tenant_id, project_id, dataset_id, offset=offset, limit=200)
        rows.extend(page)
        if len(page) < 200:
            return rows
        offset += len(page)


__all__ = ["MigrationExportSummary", "export_data_migration_package"]
