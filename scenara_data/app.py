from __future__ import annotations

import hashlib
import os
import time
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request
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

    version: str = Field(min_length=1, max_length=64)
    manifest_sha256: str = Field(default="", pattern=r"^(?:[0-9a-f]{64})?$")
    sample_count: int = Field(default=0, ge=0)


class VersionTransition(BaseModel):
    status: str = Field(pattern=r"^(draft|ready|published|archived|validated|retired)$")


class DataStore:
    """Tenant/project-scoped in-memory store used by the standalone service."""

    def __init__(self) -> None:
        self.datasets: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.versions: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.intakes: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.annotations: dict[tuple[str, str, str], dict[str, Any]] = {}


def create_data_app(*, service_token: str = "", store: DataStore | None = None) -> FastAPI:
    store = store or DataStore()
    app = FastAPI(title="Scenara Data", version="0.3.0.dev25")
    app.state.data_store = store

    def context(request: Request, authorization: str | None, tenant: str | None, project: str | None) -> tuple[str, str, str]:
        if service_token and authorization != f"Bearer {service_token}":
            raise HTTPException(status_code=401, detail={"code": "DATA_AUTHENTICATION_FAILED", "message": "invalid service token"})
        tenant_id = tenant or request.headers.get("X-Scenara-Tenant-Id")
        project_id = project or request.headers.get("X-Scenara-Project-Id")
        principal_id = request.headers.get("X-Scenara-Principal-Id", "scenara-core")
        if not tenant_id or not project_id:
            raise HTTPException(status_code=400, detail={"code": "DATA_CONTEXT_REQUIRED", "message": "tenant and project are required"})
        return tenant_id, project_id, principal_id

    def error(code: str, message: str, status: int) -> HTTPException:
        return HTTPException(status_code=status, detail={"code": code, "message": message})

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "scenara-data"}

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
        now = time.time()
        item = {
            "dataset_id": body.dataset_id or f"dst_{uuid4().hex}", "tenant_id": tenant_id, "project_id": project_id,
            "name": body.name, "description": body.description, "status": "draft", "metadata": {**body.metadata, "labels": body.labels},
            "created_at": now, "updated_at": now, "created_by": principal_id, "idempotency_key": idempotency_key,
        }
        store.datasets[(tenant_id, project_id, item["dataset_id"])] = item
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
        item["updated_at"] = time.time()
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
        if any(item["version"] == body.version for (t, p, d), item in store.versions.items() if (t, p, d) == (tenant_id, project_id, dataset_id)):
            raise error("DATASET_VERSION_CONFLICT", "dataset version already exists", 409)
        now = time.time()
        checksum = body.manifest_sha256 or hashlib.sha256(f"{dataset_id}:{body.version}".encode()).hexdigest()
        item = {
            "dataset_version_id": f"dsv_{uuid4().hex}", "dataset_id": dataset_id, "tenant_id": tenant_id,
            "project_id": project_id, "version": body.version, "status": "draft", "manifest_sha256": checksum,
            "sample_count": body.sample_count, "created_by": principal_id, "created_at": now, "updated_at": now,
            "idempotency_key": idempotency_key,
        }
        store.versions[(tenant_id, project_id, str(item["dataset_version_id"]))] = item
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
        item["updated_at"] = time.time()
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
        return {"schema_version": "1.0", "dataset_id": item["dataset_id"], "version_id": version_id, "version": item["version"], "manifest_sha256": item["manifest_sha256"], "sample_count": item["sample_count"]}

    @app.post("/internal/v1/hard-sample-manifests", status_code=202)
    async def hard_sample_intake(
        body: dict[str, Any],
        request: Request,
        authorization: str | None = Header(default=None),
        tenant: str | None = Header(default=None, alias="X-Scenara-Tenant-Id"),
        project: str | None = Header(default=None, alias="X-Scenara-Project-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        tenant_id, project_id, _ = context(request, authorization, tenant, project)
        manifest_id = str(body.get("manifest_id") or hashlib.sha256(repr(sorted(body.items())).encode()).hexdigest())
        key = (tenant_id, project_id, manifest_id)
        if key not in store.intakes:
            store.intakes[key] = {"manifest_id": manifest_id, "tenant_id": tenant_id, "project_id": project_id, "status": "accepted", "item_count": len(body.get("items") or body.get("sources") or []), "idempotency_key": idempotency_key, "accepted_at": time.time()}
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
        key = (tenant_id, project_id, sample_id)
        if key in store.intakes:
            return store.intakes[key]
        item = {"sample_id": sample_id, "tenant_id": tenant_id, "project_id": project_id, "source_ref": body.get("source_ref", {}), "media_type": body.get("media_type", "application/octet-stream"), "sample_metadata": body.get("sample_metadata", {}), "created_at": time.time()}
        store.intakes[key] = item
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
        now = time.time()
        item = {"task_id": f"task_{uuid4().hex}", "tenant_id": tenant_id, "project_id": project_id, "dataset_id": body.get("dataset_id", ""), "schema_id": body.get("schema_id", ""), "sample_ids": [str(value) for value in body.get("sample_ids", [])], "status": "pending", "assigned_to": None, "task_metadata": body.get("metadata", {}), "created_by": principal_id, "created_at": now, "updated_at": now, "idempotency_key": idempotency_key, "consistency_score": None, "review_comment": ""}
        store.annotations[(tenant_id, project_id, item["task_id"])] = item
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
        if status not in {"assigned", "in_progress", "submitted", "approved", "rejected", "cancelled"}:
            raise error("ANNOTATION_TASK_STATUS_INVALID", "invalid annotation task status", 409)
        item["status"] = status
        if body.get("assignee_principal_id") is not None:
            item["assigned_to"] = body["assignee_principal_id"]
        item["updated_at"] = time.time()
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
        item = {"annotation_id": annotation_id, "tenant_id": tenant_id, "project_id": project_id, "task_id": body.get("task_id", ""), "sample_id": body.get("sample_id", ""), "schema_id": body.get("schema_id", ""), "payload": body.get("payload", {}), "created_at": time.time()}
        store.annotations[(tenant_id, project_id, annotation_id)] = item
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
        item = {"provider_id": f"provider_{uuid4().hex}", "tenant_id": tenant_id, "project_id": project_id, "name": body.get("name", ""), "provider_type": body.get("provider_type", ""), "endpoint": body.get("endpoint", ""), "active": True, "health": "configured", "created_at": time.time(), "updated_at": time.time()}
        store.annotations[(tenant_id, project_id, item["provider_id"])] = item
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
        item["updated_at"] = time.time()
        return item

    return app


app = create_data_app(service_token=os.getenv("SCENARA_DATA_SERVICE_TOKEN", "").strip())

__all__ = ["DataStore", "app", "create_data_app"]
