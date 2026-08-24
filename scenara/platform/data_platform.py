"""Core-side boundary for the independently deployed Scenara Data service.

The public API remains owned by Core, but Dataset and Annotation facts are
owned by ``scenara-data``.  The local adapter is deliberately a transitional
implementation for development and migration verification only.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Mapping
from datetime import UTC, datetime
import hashlib
from typing import Any, Protocol

import httpx

from scenara.platform.control_plane import (
    AnnotationTaskStatus,
    AnnotationProvider,
    AnnotationTask,
    ControlPlaneService,
    CreateAnnotationProviderRequest,
    CreateAnnotationTaskRequest,
    ReviewAnnotationTaskRequest,
)
from scenara.platform.dataset import DatasetService
from scenara.platform.feedback import HardSampleManifest
from scenara.platform.models import (
    CreateDatasetRequest,
    CreateDatasetVersionRequest,
    DatasetPage,
    DatasetRecord,
    DatasetStatus,
    DatasetVersion,
    DatasetVersionStatus,
    DatasetVersionPage,
    PrincipalContext,
    TransitionDatasetVersionRequest,
    UpdateDatasetRequest,
)
from scenara.platform.repository_contracts import DatasetVersionReference


class DataPlatformRemoteError(RuntimeError):
    """A normalized error returned by the remote Data service."""

    def __init__(self, status_code: int, code: str, message: str, details: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.details = dict(details or {})


class SourceAssetStore(Protocol):
    async def get_asset(self, tenant_id: str, project_id: str, asset_id: str) -> Any: ...


class DataPlatformClient(Protocol):
    async def create_dataset(self, context: PrincipalContext, request: CreateDatasetRequest) -> DatasetRecord: ...

    async def get_dataset(self, context: PrincipalContext, dataset_id: str) -> DatasetRecord: ...

    async def list_datasets(self, context: PrincipalContext, *, offset: int, limit: int) -> DatasetPage: ...

    async def update_dataset(
        self, context: PrincipalContext, dataset_id: str, request: UpdateDatasetRequest
    ) -> DatasetRecord: ...

    async def create_dataset_version(
        self, context: PrincipalContext, dataset_id: str, request: CreateDatasetVersionRequest
    ) -> DatasetVersion: ...

    async def list_dataset_versions(
        self, context: PrincipalContext, dataset_id: str, *, offset: int, limit: int
    ) -> DatasetVersionPage: ...

    async def transition_dataset_version(
        self, context: PrincipalContext, version_id: str, request: TransitionDatasetVersionRequest
    ) -> DatasetVersion: ...

    async def get_dataset_version_reference(
        self, context: PrincipalContext, version_id: str
    ) -> DatasetVersionReference: ...

    async def submit_hard_sample_manifest(
        self, context: PrincipalContext, manifest: HardSampleManifest
    ) -> Mapping[str, object]: ...

    async def create_annotation_task(
        self, context: PrincipalContext, request: CreateAnnotationTaskRequest
    ) -> AnnotationTask: ...

    async def list_annotation_tasks(self, context: PrincipalContext) -> list[AnnotationTask]: ...

    async def register_annotation_provider(
        self, context: PrincipalContext, request: CreateAnnotationProviderRequest
    ) -> AnnotationProvider: ...

    async def list_annotation_providers(self, context: PrincipalContext) -> list[AnnotationProvider]: ...

    async def probe_annotation_provider(self, context: PrincipalContext, provider_id: str) -> AnnotationProvider: ...

    async def review_annotation_task(
        self, context: PrincipalContext, task_id: str, request: ReviewAnnotationTaskRequest
    ) -> AnnotationTask: ...

    async def close(self) -> None: ...


class LocalDataPlatformAdapter:
    """Migration-only adapter over the legacy Core stores.

    This keeps local development and shadow-read comparisons possible without
    making Core's tables a production source of truth.
    """

    def __init__(self, datasets: DatasetService, control_plane: ControlPlaneService) -> None:
        self._datasets = datasets
        self._control_plane = control_plane

    async def create_dataset(self, context: PrincipalContext, request: CreateDatasetRequest) -> DatasetRecord:
        return await self._datasets.create(context, request)

    async def get_dataset(self, context: PrincipalContext, dataset_id: str) -> DatasetRecord:
        return await self._datasets.get(context, dataset_id)

    async def list_datasets(self, context: PrincipalContext, *, offset: int, limit: int) -> DatasetPage:
        return await self._datasets.list(context, offset=offset, limit=limit)

    async def update_dataset(
        self, context: PrincipalContext, dataset_id: str, request: UpdateDatasetRequest
    ) -> DatasetRecord:
        return await self._datasets.update(context, dataset_id, request)

    async def create_dataset_version(
        self, context: PrincipalContext, dataset_id: str, request: CreateDatasetVersionRequest
    ) -> DatasetVersion:
        return await self._datasets.create_version(context, dataset_id, request)

    async def list_dataset_versions(
        self, context: PrincipalContext, dataset_id: str, *, offset: int, limit: int
    ) -> DatasetVersionPage:
        return await self._datasets.list_versions(context, dataset_id, offset=offset, limit=limit)

    async def transition_dataset_version(
        self, context: PrincipalContext, version_id: str, request: TransitionDatasetVersionRequest
    ) -> DatasetVersion:
        return await self._datasets.transition_version(context, version_id, request)

    async def get_dataset_version_reference(
        self, context: PrincipalContext, version_id: str
    ) -> DatasetVersionReference:
        raise DataPlatformRemoteError(
            409,
            "DATA_PLATFORM_MIGRATION_REQUIRED",
            "dataset version references are published only by scenara-data",
            {"version_id": version_id},
        )

    async def submit_hard_sample_manifest(
        self, context: PrincipalContext, manifest: HardSampleManifest
    ) -> Mapping[str, object]:
        raise DataPlatformRemoteError(
            409,
            "DATA_PLATFORM_MIGRATION_REQUIRED",
            "hard-sample intake is available only after scenara-data is configured",
            {"manifest_id": manifest.manifest_id},
        )

    async def create_annotation_task(
        self, context: PrincipalContext, request: CreateAnnotationTaskRequest
    ) -> AnnotationTask:
        return await self._control_plane.create_annotation_task(context, request)

    async def list_annotation_tasks(self, context: PrincipalContext) -> list[AnnotationTask]:
        return await self._control_plane.list_annotation_tasks(context)

    async def register_annotation_provider(
        self, context: PrincipalContext, request: CreateAnnotationProviderRequest
    ) -> AnnotationProvider:
        return await self._control_plane.register_annotation_provider(context, request)

    async def list_annotation_providers(self, context: PrincipalContext) -> list[AnnotationProvider]:
        return await self._control_plane.list_annotation_providers(context)

    async def probe_annotation_provider(self, context: PrincipalContext, provider_id: str) -> AnnotationProvider:
        return await self._control_plane.probe_annotation_provider(context, provider_id)

    async def review_annotation_task(
        self, context: PrincipalContext, task_id: str, request: ReviewAnnotationTaskRequest
    ) -> AnnotationTask:
        return await self._control_plane.review_annotation_task(context, task_id, request)

    async def close(self) -> None:
        return None


class HttpDataPlatformClient:
    """Typed gateway to ``scenara-data`` internal APIs.

    It propagates the Core-issued identity, request ID and trace context.  A
    stable idempotency key is sent for all mutations so transient retries do
    not create duplicate datasets, annotations, or hard-sample imports.
    """

    def __init__(
        self,
        base_url: str,
        *,
        service_token: str = "",
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        client: httpx.AsyncClient | None = None,
        source_assets: SourceAssetStore | None = None,
        source_bucket: str = "",
    ) -> None:
        self._max_retries = max(0, max_retries)
        self._client = client or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_seconds)
        self._owns_client = client is None
        self._service_token = service_token
        self._source_assets = source_assets
        self._source_bucket = source_bucket

    def _headers(self, context: PrincipalContext, method: str, path: str) -> dict[str, str]:
        trace_id, traceparent = _trace_context(context, method, path)
        headers = {
            "X-Scenara-Tenant-Id": context.tenant_id,
            "X-Scenara-Project-Id": context.project_id,
            "X-Scenara-Principal-Id": context.principal_id,
            # These names are the published Data-service IAM context.  Do not
            # use Core's historical gateway aliases here: Data independently
            # validates the scope and product boundary.
            "X-Scenara-Principal-Type": "service_account",
            "X-Scenara-Permission-Scopes": ",".join(sorted(context.scopes)),
            "X-Scenara-Product-Entitlements": ",".join(sorted(context.product_ids)),
            "X-Request-Id": context.request_id or f"core-data-{method.lower()}-{path.rsplit('/', 1)[-1]}",
            "X-Trace-Id": trace_id,
            "traceparent": traceparent,
        }
        if self._service_token:
            headers["Authorization"] = f"Bearer {self._service_token}"
        if method in {"POST", "PATCH", "PUT", "DELETE"}:
            headers["Idempotency-Key"] = f"{headers['X-Request-Id']}:{method}:{path}"
        return headers

    async def _request(
        self,
        context: PrincipalContext,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int | float | bool | None] | None = None,
        body: Any = None,
        idempotency_suffix: str | None = None,
    ) -> object:
        for attempt in range(self._max_retries + 1):
            try:
                headers = self._headers(context, method, path)
                if idempotency_suffix is not None and "Idempotency-Key" in headers:
                    suffix = hashlib.sha256(idempotency_suffix.encode("utf-8")).hexdigest()[:16]
                    headers["Idempotency-Key"] = f"{headers['Idempotency-Key']}:{suffix}"
                response = await self._client.request(
                    method,
                    path,
                    headers=headers,
                    params=params,
                    json=body,
                )
            except httpx.RequestError as exc:
                if attempt == self._max_retries:
                    raise DataPlatformRemoteError(503, "DATA_PLATFORM_UNAVAILABLE", "scenara-data is unavailable") from exc
                await asyncio.sleep(0.05 * (2**attempt))
                continue
            if response.status_code >= 500 and attempt < self._max_retries:
                await asyncio.sleep(0.05 * (2**attempt))
                continue
            payload: object
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if response.is_error:
                error = payload.get("error", {}) if isinstance(payload, dict) else {}
                raise DataPlatformRemoteError(
                    response.status_code,
                    str(error.get("code", "DATA_PLATFORM_ERROR")),
                    str(error.get("message", "scenara-data request failed")),
                    error.get("details") if isinstance(error.get("details"), dict) else {},
                )
            # Data owns the internal API and returns a direct resource/page
            # payload.  Accept Core's legacy envelope only during a gateway
            # rollout so a proxy upgrade cannot split the control plane.
            if isinstance(payload, dict) and "data" in payload:
                return payload["data"]
            return payload
        raise AssertionError("unreachable")

    async def create_dataset(self, context: PrincipalContext, request: CreateDatasetRequest) -> DatasetRecord:
        payload = await self._request(context, "POST", "/internal/v1/datasets", body=request.model_dump(mode="json"))
        return _core_dataset(payload)

    async def get_dataset(self, context: PrincipalContext, dataset_id: str) -> DatasetRecord:
        payload = await self._request(context, "GET", f"/internal/v1/datasets/{dataset_id}")
        return _core_dataset(payload)

    async def list_datasets(self, context: PrincipalContext, *, offset: int, limit: int) -> DatasetPage:
        payload = await self._request(
            context,
            "GET",
            "/internal/v1/datasets",
            params={"cursor": _data_cursor(offset), "limit": limit},
        )
        return _core_dataset_page(payload, offset=offset, limit=limit)

    async def update_dataset(
        self, context: PrincipalContext, dataset_id: str, request: UpdateDatasetRequest
    ) -> DatasetRecord:
        payload = await self._request(
            context, "PATCH", f"/internal/v1/datasets/{dataset_id}", body=request.model_dump(exclude_unset=True, mode="json")
        )
        return _core_dataset(payload)

    async def create_dataset_version(
        self, context: PrincipalContext, dataset_id: str, request: CreateDatasetVersionRequest
    ) -> DatasetVersion:
        if request.asset_ids:
            raise DataPlatformRemoteError(
                409,
                "DATA_PLATFORM_MIGRATION_REQUIRED",
                "legacy Core asset_ids must be materialized as Data samples before creating a remote dataset version",
                {"dataset_id": dataset_id, "asset_count": len(request.asset_ids)},
            )
        payload = await self._request(
            context,
            "POST",
            f"/internal/v1/datasets/{dataset_id}/versions",
            body={"version": request.version},
        )
        return _core_dataset_version(payload, context)

    async def list_dataset_versions(
        self, context: PrincipalContext, dataset_id: str, *, offset: int, limit: int
    ) -> DatasetVersionPage:
        payload = await self._request(
            context,
            "GET",
            f"/internal/v1/datasets/{dataset_id}/versions",
            params={"cursor": _data_cursor(offset), "limit": limit},
        )
        return _core_dataset_version_page(payload, context=context, offset=offset, limit=limit)

    async def transition_dataset_version(
        self, context: PrincipalContext, version_id: str, request: TransitionDatasetVersionRequest
    ) -> DatasetVersion:
        body = request.model_dump(mode="json")
        body["status"] = {"validated": "ready", "retired": "archived"}.get(body["status"], body["status"])
        payload = await self._request(
            context,
            "POST",
            f"/internal/v1/dataset-versions/{version_id}/transition",
            body=body,
        )
        return _core_dataset_version(payload, context)

    async def get_dataset_version_reference(
        self, context: PrincipalContext, version_id: str
    ) -> DatasetVersionReference:
        payload = await self._request(context, "GET", f"/internal/v1/dataset-versions/{version_id}/reference")
        # Data keeps ``sample_count`` as a compatibility field for the Core
        # migration UI; validate only the published cross-repository shape.
        if isinstance(payload, dict):
            payload = {
                key: payload[key]
                for key in (
                    "schema_version",
                    "dataset_id",
                    "version",
                    "manifest_uri",
                    "manifest_sha256",
                    "lineage_refs",
                    "authorization_id",
                    "authorized_consumer_repository_ids",
                    "created_at",
                    "domain",
                    "annotation_schema_ids",
                )
                if key in payload
            }
        return DatasetVersionReference.model_validate(payload)

    async def submit_hard_sample_manifest(
        self, context: PrincipalContext, manifest: HardSampleManifest
    ) -> Mapping[str, object]:
        if self._source_assets is None or not self._source_bucket:
            raise DataPlatformRemoteError(
                503,
                "DATA_PLATFORM_SOURCE_RESOLUTION_UNAVAILABLE",
                "Core object metadata is required to hand off hard samples",
            )
        sources: list[dict[str, object]] = []
        split = manifest.split
        annotation_schema_ids = {
            item.annotation_schema_id for item in manifest.items if item.annotation_schema_id is not None
        }
        if len(annotation_schema_ids) > 1:
            raise DataPlatformRemoteError(
                422,
                "ANNOTATION_SCHEMA_CONFLICT",
                "hard-sample manifest cannot mix annotation schemas",
            )
        occurred_at = manifest.created_at
        for item in manifest.items:
            asset = await self._source_assets.get_asset(context.tenant_id, context.project_id, item.media_ref)
            if asset is None:
                raise DataPlatformRemoteError(
                    409,
                    "DATA_PLATFORM_SOURCE_NOT_FOUND",
                    "hard-sample media must reference an immutable Core asset",
                    {"feedback_id": item.feedback_id, "media_ref": item.media_ref},
                )
            sources.append(
                {
                    "feedback_id": item.feedback_id,
                    "source_result_id": item.feedback_id,
                    "source_ref": {
                        "bucket": self._source_bucket,
                        "key": asset.object_key,
                        "version": None,
                        "checksum": f"sha256:{asset.sha256}",
                        "size_bytes": asset.size_bytes,
                        "content_type": asset.content_type,
                    },
                    "occurred_at": occurred_at,
                    "source_resource_type": "media_asset",
                    "media_type": asset.content_type,
                    "dataset_split": split,
                }
            )
        payload = await self._request(
            _hard_sample_intake_context(context),
            "POST",
            "/internal/v1/hard-sample-manifests",
            body={
                "schema_version": "1.0",
                "manifest": manifest.model_dump(mode="json"),
                "sources": sources,
                "annotation_schema_id": next(iter(annotation_schema_ids), manifest.label_schema),
                "build_version": manifest.version,
                "publish": False,
            },
        )
        if not isinstance(payload, dict):
            raise DataPlatformRemoteError(502, "DATA_PLATFORM_PROTOCOL_ERROR", "hard-sample response must be an object")
        return payload

    async def create_annotation_task(
        self, context: PrincipalContext, request: CreateAnnotationTaskRequest
    ) -> AnnotationTask:
        if self._source_assets is None or not self._source_bucket:
            raise DataPlatformRemoteError(
                503,
                "DATA_PLATFORM_SOURCE_RESOLUTION_UNAVAILABLE",
                "Core object metadata is required to materialize annotation samples",
            )
        data_context = _annotation_materialization_context(context)
        dataset_id = "dst_core_annotations"
        try:
            await self._request(data_context, "GET", f"/internal/v1/datasets/{dataset_id}")
        except DataPlatformRemoteError as exc:
            if exc.status_code != 404:
                raise
            try:
                await self._request(
                    data_context,
                    "POST",
                    "/internal/v1/datasets",
                    body={
                        "dataset_id": dataset_id,
                        "name": "Core annotation workspace",
                        "description": "Materialized Core assets used by annotation tasks.",
                        "labels": ["core-managed"],
                        "metadata": {"source_system": "scenara-core", "purpose": "annotation"},
                    },
                    idempotency_suffix=dataset_id,
                )
            except DataPlatformRemoteError as create_exc:
                if create_exc.status_code != 409:
                    raise

        for asset_id in request.asset_ids:
            asset = await self._source_assets.get_asset(context.tenant_id, context.project_id, asset_id)
            if asset is None:
                raise DataPlatformRemoteError(
                    409,
                    "DATA_PLATFORM_SOURCE_NOT_FOUND",
                    "annotation assets must reference immutable Core media",
                    {"asset_id": asset_id},
                )
            try:
                await self._request(data_context, "GET", f"/internal/v1/samples/{asset_id}")
            except DataPlatformRemoteError as exc:
                if exc.status_code != 404:
                    raise
                try:
                    await self._request(
                        data_context,
                        "POST",
                        "/internal/v1/samples",
                        body={
                            "sample_id": asset_id,
                            "source_ref": {
                                "bucket": self._source_bucket,
                                "key": asset.object_key,
                                "version": None,
                                "checksum": f"sha256:{asset.sha256}",
                                "size_bytes": asset.size_bytes,
                                "content_type": asset.content_type,
                            },
                            "media_type": asset.content_type,
                            "source_lineage": [f"core://media-assets/{asset_id}#sha256={asset.sha256}"],
                            "sample_metadata": {"core_asset_id": asset_id},
                            "source_system": "scenara-core",
                            "source_resource_type": "media_asset",
                            "source_resource_id": asset_id,
                        },
                        idempotency_suffix=asset_id,
                    )
                except DataPlatformRemoteError as create_exc:
                    if create_exc.status_code != 409:
                        raise

        payload = await self._request(
            data_context,
            "POST",
            "/internal/v1/annotation-tasks",
            body={
                "dataset_id": dataset_id,
                "schema_id": request.schema_name,
                "sample_ids": request.asset_ids,
                "metadata": request.labels,
            },
            idempotency_suffix=f"{dataset_id}:{request.schema_name}:{','.join(request.asset_ids)}",
        )
        if not isinstance(payload, dict):
            raise DataPlatformRemoteError(502, "DATA_PLATFORM_PROTOCOL_ERROR", "annotation task must be an object")
        task_id = str(payload.get("task_id", ""))
        for asset_id in request.asset_ids:
            await self._request(
                data_context,
                "POST",
                "/internal/v1/annotations",
                body={
                    "sample_id": asset_id,
                    "schema_id": request.schema_name,
                    "payload": request.labels,
                    "task_id": task_id,
                },
                idempotency_suffix=f"{task_id}:{asset_id}",
            )
        for status, assignee in (
            ("assigned", request.assignee or context.principal_id),
            ("in_progress", None),
            ("submitted", None),
        ):
            payload = await self._request(
                data_context,
                "POST",
                f"/internal/v1/annotation-tasks/{task_id}/transition",
                body={"status": status, "assignee_principal_id": assignee},
                idempotency_suffix=status,
            )
        return _core_annotation_task(payload)

    async def list_annotation_tasks(self, context: PrincipalContext) -> list[AnnotationTask]:
        payload = await self._request(context, "GET", "/internal/v1/annotation-tasks")
        return [_core_annotation_task(item) for item in _list_payload(payload)]

    async def register_annotation_provider(
        self, context: PrincipalContext, request: CreateAnnotationProviderRequest
    ) -> AnnotationProvider:
        payload = await self._request(
            context,
            "POST",
            "/internal/v1/annotation-providers",
            body={"name": request.name, "provider_type": request.kind, "endpoint": request.endpoint},
        )
        return _core_annotation_provider(payload, context)

    async def list_annotation_providers(self, context: PrincipalContext) -> list[AnnotationProvider]:
        payload = await self._request(context, "GET", "/internal/v1/annotation-providers")
        return [_core_annotation_provider(item, context) for item in _list_payload(payload)]

    async def probe_annotation_provider(self, context: PrincipalContext, provider_id: str) -> AnnotationProvider:
        payload = await self._request(context, "POST", f"/internal/v1/annotation-providers/{provider_id}/probe")
        return _core_annotation_provider(payload, context)

    async def review_annotation_task(
        self, context: PrincipalContext, task_id: str, request: ReviewAnnotationTaskRequest
    ) -> AnnotationTask:
        payload = await self._request(
            context,
            "POST",
            f"/internal/v1/annotation-tasks/{task_id}/review",
            body={
                "decision": "approved" if request.approved else "rejected",
                "consistency_score": request.consistency_score,
                "comment": request.comment,
            },
        )
        if isinstance(payload, dict) and isinstance(payload.get("task"), dict):
            payload = payload["task"]
        return _core_annotation_task(payload)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _list_payload(payload: object) -> list[object]:
    if isinstance(payload, dict):
        payload = payload.get("items")
    if not isinstance(payload, list):
        raise DataPlatformRemoteError(502, "DATA_PLATFORM_PROTOCOL_ERROR", "scenara-data returned an invalid list payload")
    return payload


def _data_cursor(offset: int) -> str | None:
    if offset <= 0:
        return None
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii")


def _trace_context(context: PrincipalContext, method: str, path: str) -> tuple[str, str]:
    traceparent = context.traceparent
    if traceparent:
        parts = traceparent.split("-")
        if len(parts) == 4 and len(parts[1]) == 32 and all(char in "0123456789abcdef" for char in parts[1].lower()):
            return parts[1], traceparent
    seed = f"{context.request_id or ''}:{context.principal_id}:{method}:{path}".encode("utf-8")
    trace_id = hashlib.sha256(seed).hexdigest()[:32]
    span_id = hashlib.sha256(seed + b":span").hexdigest()[:16]
    return trace_id, f"00-{trace_id}-{span_id}-01"


def _epoch(value: object, *, fallback: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).timestamp()
        except ValueError:
            pass
    return fallback


def _annotation_materialization_context(context: PrincipalContext) -> PrincipalContext:
    """Authorize the internal steps implied by Core's annotation operation."""

    return context.model_copy(
        update={
            "scopes": context.scopes
            | frozenset({"data.dataset.create", "data.dataset.read", "data.sample.create", "data.annotation.create"}),
            "product_ids": context.product_ids | frozenset({"scenara-data"}),
        }
    )


def _hard_sample_intake_context(context: PrincipalContext) -> PrincipalContext:
    """Authorize Data's atomic sample, annotation, quality, and version materialization."""

    return context.model_copy(
        update={
            "scopes": context.scopes
            | frozenset(
                {
                    "data.dataset.create",
                    "data.dataset.read",
                    "data.dataset.update",
                    "data.sample.create",
                    "data.sample.read",
                    "data.annotation.create",
                    "data.quality.run",
                    "data.hard_sample.import",
                }
            ),
            "product_ids": context.product_ids | frozenset({"scenara-data"}),
        }
    )


def _core_annotation_task(payload: object) -> AnnotationTask:
    if not isinstance(payload, dict):
        raise DataPlatformRemoteError(502, "DATA_PLATFORM_PROTOCOL_ERROR", "annotation task payload must be an object")
    payload_map: dict[str, Any] = payload
    created_at = _epoch(payload_map.get("created_at"))
    status = str(payload_map.get("status", "pending"))
    return AnnotationTask(
        record_id=str(payload_map.get("task_id", "")),
        tenant_id=str(payload_map.get("tenant_id", "")),
        project_id=str(payload_map.get("project_id", "")),
        asset_ids=[str(item) for item in (payload_map.get("sample_ids") or [])],
        schema_name=str(payload_map.get("schema_id", "")),
        assignee=str(payload_map["assigned_to"]) if payload_map.get("assigned_to") is not None else None,
        status=AnnotationTaskStatus({
            "pending": "queued",
            "assigned": "in_review",
            "in_progress": "in_review",
            "submitted": "in_review",
            "approved": "approved",
            "rejected": "rejected",
            "cancelled": "rejected",
        }.get(status, "queued")),
        labels=dict(payload_map.get("task_metadata") or {}),
        consistency_score=float(payload_map["consistency_score"]) if payload_map.get("consistency_score") is not None else None,
        review_comment=str(payload_map.get("review_comment") or ""),
        created_by=str(payload_map.get("created_by", "")),
        created_at=created_at,
        updated_at=_epoch(payload_map.get("updated_at"), fallback=created_at),
    )


def _core_annotation_provider(payload: object, context: PrincipalContext) -> AnnotationProvider:
    if not isinstance(payload, dict):
        raise DataPlatformRemoteError(
            502, "DATA_PLATFORM_PROTOCOL_ERROR", "annotation provider payload must be an object"
        )
    payload_map: dict[str, Any] = payload
    created_at = _epoch(payload_map.get("created_at"))
    return AnnotationProvider(
        record_id=str(payload_map.get("provider_id", "")),
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        name=str(payload_map.get("name", "")),
        kind=str(payload_map.get("provider_type", "")),
        endpoint=str(payload_map.get("endpoint") or "unconfigured://provider"),
        enabled=bool(payload_map.get("active", True)),
        last_health=str(payload_map.get("health", "unknown")),
        created_at=created_at,
        updated_at=_epoch(payload_map.get("updated_at"), fallback=created_at),
    )


def _core_dataset(payload: object) -> DatasetRecord:
    if not isinstance(payload, dict):
        raise DataPlatformRemoteError(502, "DATA_PLATFORM_PROTOCOL_ERROR", "dataset payload must be an object")
    payload_map: dict[str, Any] = payload
    created_at = _epoch(payload_map.get("created_at"))
    return DatasetRecord(
        dataset_id=str(payload_map.get("dataset_id", "")),
        tenant_id=str(payload_map.get("tenant_id", "")),
        project_id=str(payload_map.get("project_id", "")),
        name=str(payload_map.get("name", "")),
        description=str(payload_map.get("description", "")),
        status=DatasetStatus(str(payload_map.get("status", "draft"))),
        metadata=dict(payload_map.get("dataset_metadata") or payload_map.get("metadata") or {}),
        created_at=created_at,
        updated_at=_epoch(payload_map.get("updated_at"), fallback=created_at),
    )


def _core_dataset_page(payload: object, *, offset: int, limit: int) -> DatasetPage:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise DataPlatformRemoteError(502, "DATA_PLATFORM_PROTOCOL_ERROR", "dataset page items must be a list")
    return DatasetPage(
        items=[_core_dataset(item) for item in payload["items"]],
        offset=offset,
        limit=limit,
        total=int(payload.get("total", 0)),
    )


def _core_dataset_version(payload: object, context: PrincipalContext) -> DatasetVersion:
    """Map Data's target state names back to Core's stable public DTO."""

    if not isinstance(payload, dict):
        raise DataPlatformRemoteError(502, "DATA_PLATFORM_PROTOCOL_ERROR", "dataset version payload must be an object")
    payload_map: dict[str, Any] = payload
    if isinstance(payload_map.get("dataset_version"), dict):
        payload_map = payload_map["dataset_version"]
    status_raw = str(payload_map.get("status") or "draft")
    status_value = DatasetVersionStatus({"ready": "validated", "archived": "retired"}.get(status_raw, status_raw))
    checksum = payload_map.get("manifest_sha256")
    if isinstance(checksum, str):
        checksum = checksum.removeprefix("sha256:")
    created_at = _epoch(payload_map.get("created_at"))
    return DatasetVersion(
        version_id=str(payload_map.get("dataset_version_id") or payload_map.get("version_id") or ""),
        dataset_id=str(payload_map.get("dataset_id", "")),
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        version=str(payload_map.get("version", "")),
        status=status_value,
        manifest_sha256=checksum or "0" * 64,
        asset_ids=[],
        item_count=int(payload_map.get("sample_count") or 0),
        quality_score=None,
        lineage=(
            {"lineage_snapshot_id": payload_map.get("lineage_snapshot_id")}
            if payload_map.get("lineage_snapshot_id")
            else {}
        ),
        annotation_summary=(
            {"annotation_snapshot_id": payload_map.get("annotation_snapshot_id")}
            if payload_map.get("annotation_snapshot_id")
            else {}
        ),
        created_by=str(payload_map.get("created_by") or context.principal_id or "scenara-data"),
        created_at=created_at,
        updated_at=_epoch(
            payload_map.get("published_at") or payload_map.get("archived_at"), fallback=created_at
        ),
    )


def _core_dataset_version_page(
    payload: object, *, context: PrincipalContext, offset: int, limit: int
) -> DatasetVersionPage:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise DataPlatformRemoteError(502, "DATA_PLATFORM_PROTOCOL_ERROR", "dataset version page items must be a list")
    return DatasetVersionPage(
        items=[_core_dataset_version(item, context) for item in payload["items"]],
        offset=offset,
        limit=limit,
        total=int(payload.get("total", 0)),
    )


__all__ = [
    "DataPlatformClient",
    "DataPlatformRemoteError",
    "HttpDataPlatformClient",
    "LocalDataPlatformAdapter",
]
