from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field


class DatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=4_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    dataset_id: str | None = Field(default=None, min_length=2, max_length=128)
    labels: list[str] = Field(default_factory=list, max_length=64)


class DatasetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=4_000)
    status: str | None = Field(default=None, pattern=r"^(draft|active|archived)$")
    metadata: dict[str, Any] | None = None


class VersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$")
    manifest_sha256: str = Field(default="", pattern=r"^(?:[0-9a-f]{64})?$")
    sample_count: int = Field(default=0, ge=0)


class VersionTransition(BaseModel):
    status: str = Field(pattern=r"^(draft|ready|published|archived|validated|retired)$")


class DataStore:
    """Tenant/project-scoped store with an explicit development persistence mode.

    The default constructor remains in-memory for unit tests.  The standalone
    process passes ``SCENARA_DATA_STATE_PATH`` and gets a small SQLite journal,
    which makes restarts and idempotent retries deterministic without sharing
    Core's database.  Production deployments can replace this adapter with the
    PostgreSQL implementation while keeping the HTTP contract unchanged.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.datasets: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.versions: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.intakes: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.annotations: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.quality: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.lineage: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.outbox: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._database: sqlite3.Connection | None = None
        self._path = Path(path) if path else None
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._database = sqlite3.connect(self._path, check_same_thread=False)
            self._database.execute(
                """CREATE TABLE IF NOT EXISTS data_records (
                    kind TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (kind, tenant_id, project_id, record_id)
                )"""
            )
            self._database.commit()
            self._load()

    @property
    def persistent(self) -> bool:
        return self._database is not None

    def _load(self) -> None:
        if self._database is None:
            return
        rows = self._database.execute(
            "SELECT kind, tenant_id, project_id, record_id, payload FROM data_records"
        ).fetchall()
        for kind, tenant_id, project_id, record_id, payload in rows:
            item = json.loads(payload)
            target = {
                "dataset": self.datasets,
                "version": self.versions,
                "intake": self.intakes,
                "annotation": self.annotations,
                "quality": self.quality,
                "lineage": self.lineage,
                "outbox": self.outbox,
            }.get(kind)
            if target is not None:
                target[(tenant_id, project_id, record_id)] = item

    def save(self, kind: str, item: dict[str, Any], record_id: str) -> None:
        tenant_id = str(item["tenant_id"])
        project_id = str(item["project_id"])
        target = {
            "dataset": self.datasets,
            "version": self.versions,
            "intake": self.intakes,
            "annotation": self.annotations,
            "quality": self.quality,
            "lineage": self.lineage,
            "outbox": self.outbox,
        }[kind]
        target[(tenant_id, project_id, record_id)] = item
        if self._database is not None:
            self._database.execute(
                """INSERT INTO data_records(kind, tenant_id, project_id, record_id, payload)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(kind, tenant_id, project_id, record_id)
                   DO UPDATE SET payload=excluded.payload""",
                (kind, tenant_id, project_id, record_id, json.dumps(item, ensure_ascii=False, sort_keys=True)),
            )
            self._database.commit()

    def emit(
        self,
        event_type: str,
        tenant_id: str,
        project_id: str,
        principal_id: str,
        request_id: str,
        trace_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "event_id": f"evt_{uuid4().hex}",
            "event_type": event_type,
            "event_version": "1.0",
            "occurred_at": utc_now(),
            "producer": "scenara-data",
            "tenant_id": tenant_id,
            "project_id": project_id,
            "request_id": request_id,
            "trace_id": trace_id,
            "data": data,
            "delivery_status": "pending",
        }
        self.save("outbox", event, event["event_id"])
        return event

    def close(self) -> None:
        if self._database is not None:
            self._database.close()


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def trace_context(request: Request) -> tuple[str, str]:
    request_id = request.headers.get("X-Request-Id") or f"data-{uuid4().hex}"
    trace_id = request.headers.get("X-Trace-Id")
    if not trace_id:
        traceparent = request.headers.get("traceparent", "")
        parts = traceparent.split("-")
        trace_id = parts[1] if len(parts) == 4 and len(parts[1]) == 32 else hashlib.sha256(request_id.encode()).hexdigest()[:32]
    return request_id, trace_id


def immutable_reference(prefix: str, identifier: str, digest: str) -> str:
    return f"data://{prefix}/{identifier}#sha256={digest}"


def validate_object_reference(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("object reference must be an object")
    checksum = str(value.get("checksum", ""))
    key = str(value.get("key", ""))
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", checksum) or not key or key.startswith(("/", "\\")) or ".." in key.split("/"):
        raise ValueError("object reference must contain a safe key and sha256 checksum")
    return value


def create_data_app(*, service_token: str = "", store: DataStore | None = None) -> FastAPI:
    state_path = os.getenv("SCENARA_DATA_STATE_PATH", "").strip()
    store = store or DataStore(state_path or None)
    app = FastAPI(title="Scenara Data", version="0.3.0.dev25")
    app.state.data_store = store

    def context(request: Request, authorization: str | None, tenant: str | None, project: str | None) -> tuple[str, str, str]:
        if service_token and authorization != f"Bearer {service_token}":
            raise error("DATA_AUTHENTICATION_FAILED", "invalid service token", 401)
        tenant_id = tenant or request.headers.get("X-Scenara-Tenant-Id")
        project_id = project or request.headers.get("X-Scenara-Project-Id")
        principal_id = request.headers.get("X-Scenara-Principal-Id", "scenara-core")
        if not tenant_id or not project_id:
            raise error("DATA_CONTEXT_REQUIRED", "tenant and project are required", 400)
        return tenant_id, project_id, principal_id

    def error(code: str, message: str, status: int) -> HTTPException:
        return HTTPException(status_code=status, detail={"code": code, "message": message})

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        detail: dict[str, Any] = exc.detail if isinstance(exc.detail, dict) else {}
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": str(detail.get("code", "DATA_PLATFORM_ERROR")),
                    "message": str(detail.get("message", "scenara-data request failed")),
                    "details": detail.get("details", {}),
                }
            },
        )

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "scenara-data"}

    @app.get("/livez", include_in_schema=False)
    async def livez() -> dict[str, str]:
        return {"status": "ok", "service": "scenara-data"}

    @app.get("/readyz", include_in_schema=False, response_model=None)
    async def readyz() -> JSONResponse | dict[str, Any]:
        if store._database is not None:
            try:
                store._database.execute("SELECT 1").fetchone()
            except sqlite3.Error as exc:
                return JSONResponse(status_code=503, content={"status": "not_ready", "reason": str(exc)})
        return {"status": "ready", "service": "scenara-data", "persistent": store.persistent}

    def request_meta(request: Request) -> tuple[str, str]:
        return trace_context(request)

    def event(
        request: Request,
        event_type: str,
        tenant_id: str,
        project_id: str,
        principal_id: str,
        data: dict[str, Any],
    ) -> None:
        request_id, trace_id = request_meta(request)
        store.emit(event_type, tenant_id, project_id, principal_id, request_id, trace_id, data)

    @app.post("/internal/v1/datasets", status_code=201)
    async def create_dataset(
        body: DatasetCreate,
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        tenant_id, project_id, principal_id = context(request, authorization, tenant, project)
        if idempotency_key:
            for item in store.datasets.values():
                if item.get("idempotency_key") == idempotency_key and item["tenant_id"] == tenant_id and item["project_id"] == project_id:
                    return item
        now = utc_now()
        item = {
            "dataset_id": body.dataset_id or f"dst_{uuid4().hex}", "tenant_id": tenant_id, "project_id": project_id,
            "name": body.name, "description": body.description, "status": "draft", "metadata": {**body.metadata, "labels": body.labels},
            "created_at": now, "updated_at": now, "created_by": principal_id, "idempotency_key": idempotency_key,
        }
        store.save("dataset", item, item["dataset_id"])
        event(request, "dataset.created", tenant_id, project_id, principal_id, {"dataset_id": item["dataset_id"]})
        return item

    @app.get("/internal/v1/datasets")
    async def list_datasets(
        request: Request,
        cursor: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        rows = [item for (t, p, _), item in store.datasets.items() if (t, p) == (tenant_id, project_id)]
        rows.sort(key=lambda item: item["created_at"])
        return {"items": rows[cursor : cursor + limit], "total": len(rows), "cursor": cursor, "limit": limit}

    @app.get("/internal/v1/datasets/{dataset_id}")
    async def get_dataset(
        dataset_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        item = store.datasets.get((tenant_id, project_id, dataset_id))
        if item is None:
            raise error("DATASET_NOT_FOUND", "dataset not found", 404)
        return item

    @app.patch("/internal/v1/datasets/{dataset_id}")
    async def update_dataset(
        dataset_id: str,
        body: DatasetUpdate,
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        item = store.datasets.get((tenant_id, project_id, dataset_id))
        if item is None:
            raise error("DATASET_NOT_FOUND", "dataset not found", 404)
        item.update({key: value for key, value in body.model_dump(exclude_unset=True).items() if value is not None})
        item["updated_at"] = utc_now()
        store.save("dataset", item, dataset_id)
        event(request, "dataset.updated", tenant_id, project_id, item.get("created_by", "scenara-data"), {"dataset_id": dataset_id})
        return item

    @app.post("/internal/v1/datasets/{dataset_id}/versions", status_code=201)
    async def create_version(
        dataset_id: str,
        body: VersionCreate,
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        tenant_id, project_id, principal_id = context(request, authorization, tenant, project)
        if (tenant_id, project_id, dataset_id) not in store.datasets:
            raise error("DATASET_NOT_FOUND", "dataset not found", 404)
        if idempotency_key:
            for item in store.versions.values():
                if item.get("idempotency_key") == idempotency_key and item["tenant_id"] == tenant_id and item["project_id"] == project_id:
                    return item
        if any(item["version"] == body.version for (t, p, d), item in store.versions.items() if (t, p, d) == (tenant_id, project_id, dataset_id)):
            raise error("DATASET_VERSION_CONFLICT", "dataset version already exists", 409)
        now = utc_now()
        checksum = body.manifest_sha256 or hashlib.sha256(f"{dataset_id}:{body.version}".encode()).hexdigest()
        item = {
            "dataset_version_id": f"dsv_{uuid4().hex}", "dataset_id": dataset_id, "tenant_id": tenant_id,
            "project_id": project_id, "version": body.version, "status": "draft", "manifest_sha256": checksum,
            "sample_count": body.sample_count, "created_by": principal_id, "created_at": now, "updated_at": now,
            "manifest_uri": immutable_reference(f"datasets/{dataset_id}/manifests", body.version, checksum),
            "lineage_refs": [immutable_reference("datasets/lineage", f"{dataset_id}/{body.version}", checksum)],
            "authorization_id": f"grant_{tenant_id}_{project_id}_{dataset_id}_{body.version}",
            "authorized_consumer_repository_ids": ["scenara-model"],
            "published_at": None,
            "idempotency_key": idempotency_key,
        }
        store.save("version", item, str(item["dataset_version_id"]))
        event(request, "dataset.version.created", tenant_id, project_id, principal_id, {"dataset_version_id": item["dataset_version_id"], "dataset_id": dataset_id})
        return item

    @app.get("/internal/v1/datasets/{dataset_id}/versions")
    async def list_versions(
        dataset_id: str,
        request: Request,
        cursor: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        rows = [item for (t, p, d), item in store.versions.items() if (t, p, d) == (tenant_id, project_id, dataset_id)]
        rows.sort(key=lambda item: item["created_at"])
        return {"items": rows[cursor : cursor + limit], "total": len(rows), "cursor": cursor, "limit": limit}

    @app.post("/internal/v1/dataset-versions/{version_id}/transition")
    async def transition_version(
        version_id: str,
        body: VersionTransition,
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        item = store.versions.get((tenant_id, project_id, version_id))
        if item is None:
            raise error("DATASET_VERSION_NOT_FOUND", "dataset version not found", 404)
        allowed = {"draft": {"ready", "validated", "archived"}, "ready": {"published", "archived"}, "validated": {"published", "archived"}, "published": {"archived"}, "archived": set()}
        if body.status not in allowed.get(item["status"], set()):
            raise error("DATASET_VERSION_TRANSITION_INVALID", "invalid dataset version transition", 409)
        item["status"] = body.status
        item["updated_at"] = utc_now()
        if body.status == "published":
            item["published_at"] = item["updated_at"]
        store.save("version", item, version_id)
        event_type = "dataset.version.published" if body.status == "published" else "dataset.version.updated"
        event(request, event_type, tenant_id, project_id, item.get("created_by", "scenara-data"), {"dataset_version_id": version_id, "dataset_id": item["dataset_id"], "status": body.status})
        return item

    @app.get("/internal/v1/dataset-versions/{version_id}/reference")
    async def version_reference(
        version_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        item = store.versions.get((tenant_id, project_id, version_id))
        if item is None or item["status"] not in {"ready", "published", "validated"}:
            raise error("DATASET_VERSION_NOT_PUBLISHED", "dataset version is not ready", 409)
        return {
            "schema_version": "1.0",
            "dataset_id": item["dataset_id"],
            "version": item["version"],
            "manifest_uri": item["manifest_uri"],
            "manifest_sha256": item["manifest_sha256"],
            "lineage_refs": item["lineage_refs"],
            "authorization_id": item["authorization_id"],
            "authorized_consumer_repository_ids": item["authorized_consumer_repository_ids"],
            "created_at": item["created_at"],
            # Kept for Core's compatibility page; the published contract
            # client ignores this non-contract convenience field.
            "sample_count": item["sample_count"],
        }

    @app.get("/internal/v1/dataset-versions/{version_id}/manifest")
    async def version_manifest(
        version_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        item = store.versions.get((tenant_id, project_id, version_id))
        if item is None or item["status"] not in {"ready", "validated", "published"}:
            raise error("DATASET_VERSION_NOT_PUBLISHED", "dataset version is not ready", 409)
        return {
            "version_id": version_id,
            "dataset_id": item["dataset_id"],
            "version": item["version"],
            "manifest_uri": item["manifest_uri"],
            "manifest_sha256": item["manifest_sha256"],
            "sample_count": item["sample_count"],
            "lineage_refs": item["lineage_refs"],
        }

    @app.post("/internal/v1/dataset-versions/{version_id}/access-grants")
    async def grant_version_access(
        version_id: str,
        body: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, principal_id = context(request, authorization, tenant, project)
        item = store.versions.get((tenant_id, project_id, version_id))
        if item is None or item["status"] not in {"ready", "validated", "published"}:
            raise error("DATASET_VERSION_NOT_PUBLISHED", "dataset version is not ready", 409)
        consumers = body.get("authorized_consumer_repository_ids") or ["scenara-model"]
        if not isinstance(consumers, list) or not consumers or any(not isinstance(value, str) or not value for value in consumers):
            raise error("DATASET_ACCESS_GRANT_INVALID", "authorized consumers are required", 422)
        item["authorized_consumer_repository_ids"] = sorted(set(consumers))
        item["authorization_id"] = str(body.get("authorization_id") or item["authorization_id"])
        store.save("version", item, version_id)
        event(request, "dataset.version.access_granted", tenant_id, project_id, principal_id, {"dataset_version_id": version_id, "consumers": item["authorized_consumer_repository_ids"]})
        return {"version_id": version_id, "authorization_id": item["authorization_id"], "authorized_consumer_repository_ids": item["authorized_consumer_repository_ids"]}

    @app.post("/internal/v1/quality/runs", status_code=202)
    async def create_quality_run(
        body: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, principal_id = context(request, authorization, tenant, project)
        run_id = str(body.get("quality_run_id") or f"qr_{uuid4().hex}")
        item = {"quality_run_id": run_id, "tenant_id": tenant_id, "project_id": project_id, "dataset_id": body.get("dataset_id", ""), "status": "queued", "rules": body.get("rules", []), "created_by": principal_id, "created_at": utc_now()}
        store.save("quality", item, run_id)
        event(request, "quality.started", tenant_id, project_id, principal_id, {"quality_run_id": run_id, "dataset_id": item["dataset_id"]})
        return item

    @app.post("/internal/v1/lineage/snapshots", status_code=201)
    async def create_lineage_snapshot(
        body: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, principal_id = context(request, authorization, tenant, project)
        snapshot_id = str(body.get("lineage_snapshot_id") or f"ls_{uuid4().hex}")
        digest = hashlib.sha256(json.dumps(body.get("edges", []), sort_keys=True).encode()).hexdigest()
        item = {"lineage_snapshot_id": snapshot_id, "tenant_id": tenant_id, "project_id": project_id, "edges": body.get("edges", []), "sha256": digest, "created_by": principal_id, "created_at": utc_now()}
        store.save("lineage", item, snapshot_id)
        event(request, "lineage.snapshot.created", tenant_id, project_id, principal_id, {"lineage_snapshot_id": snapshot_id})
        return item

    @app.get("/internal/v1/events/outbox")
    async def list_outbox_events(
        request: Request,
        limit: int = Query(default=100, ge=1, le=500),
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        items = [item for (t, p, _), item in store.outbox.items() if (t, p) == (tenant_id, project_id)]
        items.sort(key=lambda item: item["occurred_at"])
        return {"items": items[-limit:], "total": len(items)}

    @app.post("/internal/v1/hard-sample-manifests", status_code=202)
    async def hard_sample_intake(
        body: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        tenant_id, project_id, principal_id = context(request, authorization, tenant, project)
        manifest = body.get("manifest") if isinstance(body.get("manifest"), dict) else body
        if not isinstance(manifest, dict):
            raise error("HARD_SAMPLE_MANIFEST_INVALID", "manifest must be an object", 422)
        required = {"manifest_id", "tenant_id", "project_id", "dataset_id", "version", "items", "sha256", "created_by", "created_at"}
        if not required.issubset(manifest):
            raise error("HARD_SAMPLE_MANIFEST_INVALID", "manifest is missing required fields", 422)
        if manifest.get("schema_version", "1.0") != "1.0" or manifest["tenant_id"] != tenant_id or manifest["project_id"] != project_id:
            raise error("HARD_SAMPLE_MANIFEST_SCOPE_INVALID", "manifest scope or schema version is invalid", 422)
        if not re.fullmatch(r"[0-9a-f]{64}", str(manifest["sha256"])):
            raise error("HARD_SAMPLE_MANIFEST_INVALID", "manifest sha256 is invalid", 422)
        items = manifest.get("items")
        if not isinstance(items, list):
            raise error("HARD_SAMPLE_MANIFEST_INVALID", "manifest items must be a list", 422)
        for item in items:
            if not isinstance(item, dict) or item.get("authorized_for_training", True) is not True or item.get("deidentified", True) is not True:
                raise error("HARD_SAMPLE_NOT_AUTHORIZED", "all hard samples must be authorized and deidentified", 422)
        manifest_id = str(manifest["manifest_id"])
        key = (tenant_id, project_id, manifest_id)
        if key not in store.intakes:
            record = {
                "manifest_id": manifest_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "dataset_id": manifest["dataset_id"],
                "version": manifest["version"],
                "status": "accepted",
                "item_count": len(items),
                "idempotency_key": idempotency_key,
                "accepted_at": utc_now(),
            }
            store.save("intake", record, manifest_id)
            raw_sources = body.get("sources")
            sources: list[Any] = raw_sources if isinstance(raw_sources, list) else []
            for source in sources:
                if not isinstance(source, dict):
                    continue
                sample_id = str(source.get("feedback_id") or source.get("sample_id") or "")
                if sample_id:
                    try:
                        source_ref = validate_object_reference(source.get("source_ref"))
                    except ValueError as exc:
                        raise error("OBJECT_REFERENCE_INVALID", str(exc), 422) from exc
                    sample = {
                        "sample_id": sample_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "source_ref": source_ref,
                        "media_type": source.get("media_type", "application/octet-stream"),
                        "sample_metadata": {"hard_sample_manifest_id": manifest_id, "dataset_split": source.get("dataset_split", "train")},
                        "created_at": utc_now(),
                    }
                    store.save("intake", sample, sample_id)
            event(request, "hard_sample.imported", tenant_id, project_id, principal_id, {"manifest_id": manifest_id, "item_count": len(items)})
        return store.intakes[key]

    @app.post("/internal/v1/samples", status_code=201)
    async def create_sample(
        body: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        sample_id = str(body.get("sample_id", ""))
        if not sample_id:
            raise error("SAMPLE_ID_REQUIRED", "sample_id is required", 400)
        try:
            source_ref = validate_object_reference(body.get("source_ref"))
        except ValueError as exc:
            raise error("OBJECT_REFERENCE_INVALID", str(exc), 422) from exc
        key = (tenant_id, project_id, sample_id)
        if key in store.intakes:
            return store.intakes[key]
        item = {"sample_id": sample_id, "tenant_id": tenant_id, "project_id": project_id, "source_ref": source_ref, "media_type": body.get("media_type", "application/octet-stream"), "sample_metadata": body.get("sample_metadata", {}), "created_at": utc_now()}
        store.save("intake", item, sample_id)
        return item

    @app.get("/internal/v1/samples/{sample_id}")
    async def get_sample(
        sample_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        item = store.intakes.get((tenant_id, project_id, sample_id))
        if item is None:
            raise error("SAMPLE_NOT_FOUND", "sample not found", 404)
        return item

    @app.post("/internal/v1/annotation-tasks", status_code=201)
    async def create_annotation_task(
        body: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        tenant_id, project_id, principal_id = context(request, authorization, tenant, project)
        existing = next((item for item in store.annotations.values() if item.get("idempotency_key") == idempotency_key and item["tenant_id"] == tenant_id and item["project_id"] == project_id), None)
        if existing is not None:
            return existing
        now = utc_now()
        item = {"task_id": f"task_{uuid4().hex}", "tenant_id": tenant_id, "project_id": project_id, "dataset_id": body.get("dataset_id", ""), "schema_id": body.get("schema_id", ""), "sample_ids": [str(value) for value in body.get("sample_ids", [])], "status": "pending", "assigned_to": None, "task_metadata": body.get("metadata", {}), "created_by": principal_id, "created_at": now, "updated_at": now, "idempotency_key": idempotency_key, "consistency_score": None, "review_comment": ""}
        store.save("annotation", item, item["task_id"])
        event(request, "annotation.task.created", tenant_id, project_id, principal_id, {"task_id": item["task_id"], "dataset_id": item["dataset_id"]})
        return item

    @app.get("/internal/v1/annotation-tasks")
    async def list_annotation_tasks(
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> list[dict[str, Any]]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        return [item for (t, p, _), item in store.annotations.items() if (t, p) == (tenant_id, project_id) and "task_id" in item]

    @app.post("/internal/v1/annotation-tasks/{task_id}/transition")
    async def transition_annotation_task(
        task_id: str,
        body: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        item = store.annotations.get((tenant_id, project_id, task_id))
        if item is None:
            raise error("ANNOTATION_TASK_NOT_FOUND", "annotation task not found", 404)
        status = str(body.get("status", ""))
        allowed = {"pending": {"assigned", "cancelled"}, "assigned": {"in_progress", "cancelled"}, "in_progress": {"submitted", "cancelled"}, "submitted": {"approved", "rejected"}, "approved": set(), "rejected": set(), "cancelled": set()}
        if status not in allowed.get(str(item.get("status")), set()):
            raise error("ANNOTATION_TASK_STATUS_INVALID", "invalid annotation task status", 409)
        item["status"] = status
        if body.get("assignee_principal_id") is not None:
            item["assigned_to"] = body["assignee_principal_id"]
        item["updated_at"] = utc_now()
        store.save("annotation", item, task_id)
        event(request, "annotation.reviewed" if status in {"approved", "rejected"} else "annotation.updated", tenant_id, project_id, item.get("created_by", "scenara-data"), {"task_id": task_id, "status": status})
        return item

    @app.post("/internal/v1/annotations", status_code=201)
    async def create_annotation(
        body: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        annotation_id = f"annotation_{body.get('task_id', '')}_{body.get('sample_id', '')}"
        item = {"annotation_id": annotation_id, "tenant_id": tenant_id, "project_id": project_id, "task_id": body.get("task_id", ""), "sample_id": body.get("sample_id", ""), "schema_id": body.get("schema_id", ""), "payload": body.get("payload", {}), "created_at": utc_now()}
        store.save("annotation", item, annotation_id)
        return item

    @app.post("/internal/v1/annotation-tasks/{task_id}/review")
    async def review_annotation_task(
        task_id: str,
        body: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        item = await transition_annotation_task(task_id, {"status": "approved" if body.get("decision") == "approved" else "rejected"}, request, authorization, tenant, project)
        item["consistency_score"] = body.get("consistency_score")
        item["review_comment"] = body.get("comment", "")
        store.save("annotation", item, task_id)
        return item

    @app.post("/internal/v1/annotation-providers", status_code=201)
    async def create_annotation_provider(
        body: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        now = utc_now()
        item = {"provider_id": f"provider_{uuid4().hex}", "tenant_id": tenant_id, "project_id": project_id, "name": body.get("name", ""), "provider_type": body.get("provider_type", ""), "endpoint": body.get("endpoint", ""), "active": True, "health": "configured", "created_at": now, "updated_at": now}
        store.save("annotation", item, item["provider_id"])
        return item

    @app.get("/internal/v1/annotation-providers")
    async def list_annotation_providers(
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> list[dict[str, Any]]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        return [item for (t, p, _), item in store.annotations.items() if (t, p) == (tenant_id, project_id) and "provider_id" in item]

    @app.post("/internal/v1/annotation-providers/{provider_id}/probe")
    async def probe_annotation_provider(
        provider_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
    ) -> dict[str, Any]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        item = store.annotations.get((tenant_id, project_id, provider_id))
        if item is None:
            raise error("ANNOTATION_PROVIDER_NOT_FOUND", "annotation provider not found", 404)
        item["health"] = "configured"
        item["updated_at"] = utc_now()
        store.save("annotation", item, provider_id)
        return item

    return app


app = create_data_app(service_token=os.getenv("SCENARA_DATA_SERVICE_TOKEN", "").strip())

__all__ = ["DataStore", "app", "create_data_app"]
