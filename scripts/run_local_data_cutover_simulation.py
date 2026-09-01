"""Exercise a non-production Core-to-Data cutover against local services.

The test creates the same dataset intent through Core's legacy local adapter
and through its typed HTTP Data boundary, compares the normalized records,
tests Data idempotency and reads, then archives only the remote simulation
dataset.  It never changes the configured production mode or performs a bulk
Data migration.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUTPUT = ROOT / "runtime-state" / "qualification" / "data-cutover-local-simulation.json"

from scenara.bootstrap import build_runtime  # noqa: E402
from scenara.platform.data_platform import HttpDataPlatformClient  # noqa: E402
from scenara.platform.models import CreateDatasetRequest, PrincipalContext, UpdateDatasetRequest  # noqa: E402
from scenara.settings import load_settings  # noqa: E402


SCOPES = frozenset(
    {
        "data.dataset.create",
        "data.dataset.read",
        "data.dataset.update",
        "data.dataset.archive",
    }
)


def _context(request_id: str) -> PrincipalContext:
    return PrincipalContext(
        tenant_id="local-simulation",
        project_id="data-cutover",
        principal_id="core-cutover-qualification",
        scopes=SCOPES,
        product_ids=frozenset({"scenara-data"}),
        request_id=request_id,
    )


def _local_context(request_id: str) -> PrincipalContext:
    return PrincipalContext(
        tenant_id="local-simulation",
        project_id="data-cutover",
        principal_id="core-cutover-qualification",
        request_id=request_id,
    )


async def _main() -> dict[str, object]:
    started = time.perf_counter()
    # The local Data development server uses the same inbound credential that
    # Core uses for outbound Data requests. Do not
    # read a .env file here: it may not be the environment of the running
    # process and would make this qualification misleading.
    token = os.getenv("SCENARA_DATA_PLATFORM_SERVICE_TOKEN", "scenara-data-dev-token").strip()
    if not token:
        raise RuntimeError("SCENARA_DATA_PLATFORM_SERVICE_TOKEN must not be empty")
    identifier = uuid4().hex[:12]
    intent = CreateDatasetRequest(
        name=f"Core Data cutover simulation {identifier}",
        description="local simulation only",
        metadata={"simulation_only": True, "qualification_id": identifier},
    )
    with tempfile.TemporaryDirectory(prefix="scenara-data-cutover-local-") as temporary:
        settings = replace(
            load_settings(),
            profile="simulation",
            state_backend="memory",
            object_backend="local",
            queue_backend="inline",
            data_platform_mode="local",
            data_dir=Path(temporary) / "data",
            qdrant_url="",
        )
        local_runtime = build_runtime(settings)
        await local_runtime.open()
        remote = HttpDataPlatformClient(
            "http://127.0.0.1:8081",
            service_token=token,
            timeout_seconds=10,
            max_retries=0,
        )
        remote_dataset_id = ""
        try:
            legacy = await local_runtime.data.create_dataset(_local_context(f"legacy-create-{identifier}"), intent)
            first = await remote.create_dataset(_context(f"remote-create-{identifier}"), intent)
            replay = await remote.create_dataset(_context(f"remote-create-{identifier}"), intent)
            remote_dataset_id = first.dataset_id
            read_back = await remote.get_dataset(_context(f"remote-read-{identifier}"), remote_dataset_id)
            listed = await remote.list_datasets(_context(f"remote-list-{identifier}"), offset=0, limit=200)
            updated = await remote.update_dataset(
                _context(f"remote-update-{identifier}"),
                remote_dataset_id,
                UpdateDatasetRequest(description="local simulation updated", metadata={**intent.metadata, "updated": True}),
            )
            if first.dataset_id != replay.dataset_id:
                raise RuntimeError("Data idempotency replay returned a different dataset")
            expected_shape = (intent.name, intent.description, intent.metadata, "draft")
            legacy_shape = (legacy.name, legacy.description, legacy.metadata, legacy.status.value)
            remote_shape = (read_back.name, read_back.description, read_back.metadata, read_back.status.value)
            if legacy_shape != expected_shape or remote_shape != expected_shape:
                raise RuntimeError("Core local and remote Data records do not preserve the dataset intent")
            if remote_dataset_id not in {item.dataset_id for item in listed.items}:
                raise RuntimeError("remote Data list response did not include the created dataset")
            if updated.metadata.get("updated") is not True or updated.description != "local simulation updated":
                raise RuntimeError("remote Data update did not persist")
            archive_result = await remote._request(  # noqa: SLF001 - exercises Core's authenticated gateway headers for cleanup
                _context(f"remote-archive-{identifier}"), "DELETE", f"/internal/v1/datasets/{remote_dataset_id}"
            )
            if not isinstance(archive_result, dict) or archive_result.get("status") != "archived":
                raise RuntimeError("remote simulation dataset was not archived")
        finally:
            await remote.close()
            await local_runtime.close()
    return {
        "schema_version": "1.0",
        "status": "passed",
        "executed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "simulation_only": True,
        "not_production_evidence": [
            "Uses one local Data service and one synthetic dataset; no production route or source-of-truth setting is changed.",
            "The remote test record is archived after verification; this is not a bulk migration or a restore drill.",
            "A formal cutover still requires production Data infrastructure, migration reconciliation, rollback approval, and operator sign-off.",
        ],
        "checks": {
            "core_local_adapter_shadow_record": True,
            "core_http_data_boundary": True,
            "create_idempotency_replay": True,
            "remote_read_and_list": True,
            "remote_update": True,
            "remote_archive_cleanup": True,
        },
    }


def main() -> int:
    report = asyncio.run(_main())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
