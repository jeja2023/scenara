"""Core-side boundary for the independently deployed Scenara Data service.

The public API remains owned by Core, but Dataset and Annotation facts are
owned by ``scenara-data``.  The local adapter is deliberately a transitional
implementation for development and migration verification only.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, Protocol

import httpx

from scenara.platform.control_plane import (
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
    DatasetVersion,
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
    ) -> None:
        self._max_retries = max(0, max_retries)
        self._client = client or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_seconds)
        self._owns_client = client is None
        self._service_token = service_token

    def _headers(self, context: PrincipalContext, method: str, path: str) -> dict[str, str]:
        headers = {
            "X-Scenara-Tenant-Id": context.tenant_id,
            "X-Scenara-Project-Id": context.project_id,
            "X-Scenara-Principal-Id": context.principal_id,
            "X-Scenara-Scopes": ",".join(sorted(context.scopes)),
            "X-Scenara-Product-Ids": ",".join(sorted(context.product_ids)),
            "X-Request-Id": context.request_id or f"core-data-{method.lower()}-{path.rsplit('/', 1)[-1]}",
        }
        if context.traceparent:
            headers["traceparent"] = context.traceparent
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
    ) -> object:
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(
                    method,
                    path,
                    headers=self._headers(context, method, path),
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
            if not isinstance(payload, dict) or "data" not in payload:
                raise DataPlatformRemoteError(502, "DATA_PLATFORM_PROTOCOL_ERROR", "scenara-data returned an invalid envelope")
            data: object = payload["data"]
            return data
        raise AssertionError("unreachable")

    async def create_dataset(self, context: PrincipalContext, request: CreateDatasetRequest) -> DatasetRecord:
        payload = await self._request(context, "POST", "/internal/v1/datasets", body=request.model_dump(mode="json"))
        return DatasetRecord.model_validate(payload)

    async def get_dataset(self, context: PrincipalContext, dataset_id: str) -> DatasetRecord:
        payload = await self._request(context, "GET", f"/internal/v1/datasets/{dataset_id}")
        return DatasetRecord.model_validate(payload)

    async def list_datasets(self, context: PrincipalContext, *, offset: int, limit: int) -> DatasetPage:
        payload = await self._request(context, "GET", "/internal/v1/datasets", params={"offset": offset, "limit": limit})
        return DatasetPage.model_validate(payload)

    async def update_dataset(
        self, context: PrincipalContext, dataset_id: str, request: UpdateDatasetRequest
    ) -> DatasetRecord:
        payload = await self._request(
            context, "PATCH", f"/internal/v1/datasets/{dataset_id}", body=request.model_dump(exclude_unset=True, mode="json")
        )
        return DatasetRecord.model_validate(payload)

    async def create_dataset_version(
        self, context: PrincipalContext, dataset_id: str, request: CreateDatasetVersionRequest
    ) -> DatasetVersion:
        payload = await self._request(
            context,
            "POST",
            f"/internal/v1/datasets/{dataset_id}/versions",
            body=request.model_dump(mode="json"),
        )
        return _core_dataset_version(payload)

    async def list_dataset_versions(
        self, context: PrincipalContext, dataset_id: str, *, offset: int, limit: int
    ) -> DatasetVersionPage:
        payload = await self._request(
            context, "GET", f"/internal/v1/datasets/{dataset_id}/versions", params={"offset": offset, "limit": limit}
        )
        if not isinstance(payload, dict):
            raise DataPlatformRemoteError(502, "DATA_PLATFORM_PROTOCOL_ERROR", "scenara-data returned an invalid version page")
        normalized = dict(payload)
        items = normalized.get("items")
        if not isinstance(items, list):
            raise DataPlatformRemoteError(502, "DATA_PLATFORM_PROTOCOL_ERROR", "version page items must be a list")
        normalized["items"] = [_core_dataset_version(item).model_dump(mode="json") for item in items]
        return DatasetVersionPage.model_validate(normalized)

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
        return _core_dataset_version(payload)

    async def get_dataset_version_reference(
        self, context: PrincipalContext, version_id: str
    ) -> DatasetVersionReference:
        payload = await self._request(context, "GET", f"/internal/v1/dataset-versions/{version_id}/reference")
        return DatasetVersionReference.model_validate(payload)

    async def submit_hard_sample_manifest(
        self, context: PrincipalContext, manifest: HardSampleManifest
    ) -> Mapping[str, object]:
        payload = await self._request(
            context, "POST", "/internal/v1/hard-sample-manifests", body=manifest.model_dump(mode="json")
        )
        if not isinstance(payload, dict):
            raise DataPlatformRemoteError(502, "DATA_PLATFORM_PROTOCOL_ERROR", "hard-sample response must be an object")
        return payload

    async def create_annotation_task(
        self, context: PrincipalContext, request: CreateAnnotationTaskRequest
    ) -> AnnotationTask:
        payload = await self._request(context, "POST", "/internal/v1/annotation-tasks", body=request.model_dump(mode="json"))
        return AnnotationTask.model_validate(payload)

    async def list_annotation_tasks(self, context: PrincipalContext) -> list[AnnotationTask]:
        payload = await self._request(context, "GET", "/internal/v1/annotation-tasks")
        return [AnnotationTask.model_validate(item) for item in _list_payload(payload)]

    async def register_annotation_provider(
        self, context: PrincipalContext, request: CreateAnnotationProviderRequest
    ) -> AnnotationProvider:
        payload = await self._request(
            context, "POST", "/internal/v1/annotation-providers", body=request.model_dump(mode="json")
        )
        return AnnotationProvider.model_validate(payload)

    async def list_annotation_providers(self, context: PrincipalContext) -> list[AnnotationProvider]:
        payload = await self._request(context, "GET", "/internal/v1/annotation-providers")
        return [AnnotationProvider.model_validate(item) for item in _list_payload(payload)]

    async def probe_annotation_provider(self, context: PrincipalContext, provider_id: str) -> AnnotationProvider:
        payload = await self._request(context, "POST", f"/internal/v1/annotation-providers/{provider_id}/probe")
        return AnnotationProvider.model_validate(payload)

    async def review_annotation_task(
        self, context: PrincipalContext, task_id: str, request: ReviewAnnotationTaskRequest
    ) -> AnnotationTask:
        payload = await self._request(
            context,
            "POST",
            f"/internal/v1/annotation-tasks/{task_id}/review",
            body=request.model_dump(mode="json"),
        )
        return AnnotationTask.model_validate(payload)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _list_payload(payload: object) -> list[object]:
    if not isinstance(payload, list):
        raise DataPlatformRemoteError(502, "DATA_PLATFORM_PROTOCOL_ERROR", "scenara-data returned an invalid list payload")
    return payload


def _core_dataset_version(payload: object) -> DatasetVersion:
    """Map Data's target state names back to Core's stable public DTO."""

    if not isinstance(payload, dict):
        raise DataPlatformRemoteError(502, "DATA_PLATFORM_PROTOCOL_ERROR", "dataset version payload must be an object")
    normalized = dict(payload)
    status_raw = normalized.get("status")
    if isinstance(status_raw, str):
        normalized["status"] = {"ready": "validated", "archived": "retired"}.get(status_raw, status_raw)
    return DatasetVersion.model_validate(normalized)


__all__ = [
    "DataPlatformClient",
    "DataPlatformRemoteError",
    "HttpDataPlatformClient",
    "LocalDataPlatformAdapter",
]
