"""Auditable export of Core-owned migration inputs for ``scenara-data``.

The exporter never connects to a Data database.  It writes a self-contained,
checksummed package that Data can validate and import idempotently.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
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
    source_bucket: str = "scenara-media",
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
    asset_ids.update(asset_id for task in tasks for asset_id in task.asset_ids)
    asset_ids.update(item.media_ref for manifest in manifests for item in manifest.items)
    object_references: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    for asset_id in sorted(asset_ids):
        asset = await state.get_asset(tenant_id, project_id, asset_id)
        if asset is None:
            raise ValueError(f"migration asset is missing: {asset_id}")
        if asset.deleted_at is not None or asset.original_deleted_at is not None:
            raise ValueError(f"migration asset is unavailable: {asset_id}")
        reference = {
            "bucket": source_bucket,
            "key": asset.object_key,
            "version": None,
            "checksum": f"sha256:{asset.sha256}",
            "size_bytes": asset.size_bytes,
            "content_type": asset.content_type,
        }
        object_references.append(
            {
                "entity_type": "sample",
                "entity_id": asset.asset_id,
                "reference": reference,
            }
        )
        samples.append(
            {
                "sample_id": asset.asset_id,
                "source_ref": reference,
                "media_type": asset.content_type,
                "source_lineage": [f"core://media-assets/{asset.asset_id}#sha256={asset.sha256}"],
                "metadata": {"core_asset_id": asset.asset_id, "filename": asset.filename},
                "source_system": "scenara",
                "source_resource_type": "media_asset",
                "source_resource_id": asset.asset_id,
                "created_by": "data-migration-export",
                "created_at": _iso(asset.created_at),
            }
        )
    audits = await state.audit_events(tenant_id, project_id, limit=None)
    dataset_rows = [
        {
            "dataset_id": item.dataset_id,
            "name": item.name,
            "description": item.description,
            "status": item.status,
            "created_by": "data-migration-export",
            "created_at": _iso(item.created_at),
            "owner_principal_id": "data-migration-export",
            "labels": [],
            "metadata": item.metadata,
            "updated_at": _iso(item.updated_at),
        }
        for item in datasets
    ]
    if tasks and all(item["dataset_id"] != "dst_core_annotations" for item in dataset_rows):
        generated_at = datetime.now(UTC).isoformat()
        dataset_rows.append(
            {
                "dataset_id": "dst_core_annotations",
                "name": "Core annotation workspace",
                "description": "Migrated Core annotation task assets.",
                "status": "active",
                "created_by": "data-migration-export",
                "created_at": generated_at,
                "owner_principal_id": "data-migration-export",
                "labels": ["core-managed"],
                "metadata": {"source_system": "scenara-core", "purpose": "annotation"},
                "updated_at": generated_at,
            }
        )

    manifest_documents: dict[str, bytes] = {}
    version_rows: list[dict[str, Any]] = []
    object_by_asset = {item["entity_id"]: item["reference"] for item in object_references}
    for value in versions:
        manifest_file = f"dataset-manifests/{value.version_id}.json"
        manifest_payload = {
            "schema_version": "1.0",
            "source_repository": "scenara",
            "dataset_id": value.dataset_id,
            "dataset_version_id": value.version_id,
            "version": value.version,
            "source_manifest_sha256": value.manifest_sha256,
            "samples": [
                {"sample_id": asset_id, "source_ref": object_by_asset[asset_id]}
                for asset_id in value.asset_ids
            ],
            "lineage": value.lineage,
            "annotation_summary": value.annotation_summary,
        }
        manifest_documents[manifest_file] = _json_bytes(manifest_payload)
        version_rows.append(
            {
                "version_id": value.version_id,
                "dataset_id": value.dataset_id,
                "version": value.version,
                "status": value.status,
                "created_by": value.created_by,
                "created_at": _iso(value.created_at),
                "manifest_file": manifest_file,
                "source_manifest_sha256": value.manifest_sha256,
                "sample_ids": value.asset_ids,
                "sample_count": value.item_count,
                "published_at": _iso(value.updated_at) if str(value.status) == "published" else None,
                "archived_at": _iso(value.updated_at) if str(value.status) == "retired" else None,
            }
        )
    documents: dict[str, list[dict[str, Any]]] = {
        "datasets.jsonl": dataset_rows,
        "samples.jsonl": samples,
        "dataset-versions.jsonl": version_rows,
        "annotation-providers.jsonl": [
            {
                "provider_id": item.record_id,
                "name": item.name,
                "provider_type": item.kind,
                "endpoint": item.endpoint,
                "active": item.enabled,
                "health": item.last_health,
                "created_at": _iso(item.created_at),
                "updated_at": _iso(item.updated_at),
            }
            for item in providers
        ],
        "annotation-tasks.jsonl": [
            {
                "task_id": item.record_id,
                "dataset_id": "dst_core_annotations",
                "schema_id": item.schema_name,
                "sample_ids": item.asset_ids,
                "status": {"queued": "pending", "in_review": "submitted"}.get(str(item.status), str(item.status)),
                "created_by": item.created_by,
                "created_at": _iso(item.created_at),
                "updated_at": _iso(item.updated_at),
                "assigned_to": item.assignee,
                "metadata": item.labels,
                "consistency_score": item.consistency_score,
                "review_comment": item.review_comment,
            }
            for item in tasks
        ],
        "hard-sample-manifests.jsonl": [
            {
                "manifest_id": item.manifest_id,
                "source_result_ids": [entry.result_ref for entry in item.items],
                "generated_at": _iso(item.created_at),
            }
            for item in manifests
        ],
        "object-references.jsonl": object_references,
        "audit-references.jsonl": [
            {
                "audit_id": item.event_id,
                "action": item.action,
                "entity_type": item.resource_type,
                "entity_id": item.resource_id or "unknown",
                "occurred_at": _iso(item.created_at),
            }
            for item in audits
        ],
    }
    file_hashes: dict[str, str] = {}
    record_counts: dict[str, int] = {}
    for name, rows in documents.items():
        encoded = b"".join(_json_bytes(row) for row in rows)
        (output_dir / name).write_bytes(encoded)
        file_hashes[name] = hashlib.sha256(encoded).hexdigest()
        record_counts[name.removesuffix(".jsonl")] = len(rows)
    for name, encoded in manifest_documents.items():
        path = output_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded)
        file_hashes[name] = hashlib.sha256(encoded).hexdigest()
        record_counts[name] = 1
    checksums = "".join(f"{digest}  {name}\n" for name, digest in sorted(file_hashes.items()))
    (output_dir / "checksums.txt").write_text(checksums, encoding="utf-8", newline="\n")
    migration_manifest = {
        "schema_version": "1.0",
        "source_repository": "scenara",
        "source_version": source_version,
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "project_id": project_id,
        "files": [
            {"file": name, "record_count": record_counts[name.removesuffix(".jsonl")], "sha256": digest}
            for name, digest in sorted(file_hashes.items())
        ],
        "exporter_version": "1.0.0",
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


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


__all__ = ["MigrationExportSummary", "export_data_migration_package"]
