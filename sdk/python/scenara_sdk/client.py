from __future__ import annotations

import mimetypes
import time
import uuid
from pathlib import Path
from typing import Any, cast

import httpx

from .models import (
    AccessFoundationStatus,
    ApiKeyRecord,
    CreateApiKeyResponse,
    DatasetRecord,
    DatasetVersion,
    Domain,
    FeedbackRecord,
    HardSampleManifest,
    IamSummary,
    MediaAsset,
    MediaSource,
    MediaSourceProbe,
    Membership,
    ModelDeploymentEvent,
    ModelPackage,
    ModelRelease,
    Organization,
    ParseDocumentResponse,
    ParseImageResponse,
    ParseVideoResponse,
    PortraitIntelligenceStatus,
    ProductCatalogItem,
    ProductEntitlement,
    Project,
    RepositoryContractCatalog,
    RepositoryTopology,
    ResultEnvelope,
    Role,
    Run,
    SampleStrategy,
    SavedSearch,
    ServiceAccount,
    UserAccount,
    WebhookDelivery,
    WebhookSubscription,
)

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class ScenaraError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, request_id: str | None = None) -> None:
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        super().__init__(message)


class ScenaraClient:
    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        tenant_id: str = "default",
        project_id: str = "default",
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "User-Agent": "scenara-sdk-python/0.3.0.dev16",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    def __enter__(self) -> ScenaraClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def upload_asset(self, path: str | Path, *, kind: str = "image") -> MediaAsset:
        source = Path(path)
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        with source.open("rb") as handle:
            return cast(
                MediaAsset,
                self._request(
                    "POST",
                    "/api/v1/media/assets",
                    files={"file": (source.name, handle, content_type)},
                    data={"kind": kind},
                ),
            )

    def create_run(
        self,
        *,
        domain: Domain,
        pipeline_id: str,
        pipeline_version: str,
        asset_id: str | None = None,
        source_id: str | None = None,
        parameters: dict[str, Any] | None = None,
        priority: int = 0,
        idempotency_key: str | None = None,
        wait_ms: int = 0,
    ) -> Run:
        payload = {
            "domain": domain,
            "pipeline": {"pipeline_id": pipeline_id, "version": pipeline_version},
            "asset_id": asset_id,
            "source_id": source_id,
            "parameters": parameters or {},
            "priority": priority,
            "wait_ms": wait_ms,
        }
        key = idempotency_key or f"sdk_{uuid.uuid4().hex}"
        return cast(
            Run,
            self._request(
                "POST",
                "/api/v1/runs",
                json=payload,
                headers={"Idempotency-Key": key},
            ),
        )

    def get_run(self, run_id: str) -> Run:
        return cast(Run, self._request("GET", f"/api/v1/runs/{run_id}"))

    def list_runs(self, *, status: str | None = None, domain: Domain | None = None, limit: int = 50) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("GET", "/api/v1/runs", params={"status": status, "domain": domain, "limit": limit}),
        )

    def cancel_run(self, run_id: str) -> Run:
        return cast(Run, self._request("POST", f"/api/v1/runs/{run_id}/cancel"))

    def get_result(self, run_id: str) -> ResultEnvelope:
        page = cast(dict[str, Any], self._request("GET", f"/api/v1/runs/{run_id}/result"))
        return cast(ResultEnvelope, page["result"])

    def get_result_artifact(self, run_id: str, artifact_id: str) -> bytes:
        """Download one derived image declared by a run result.

        Feature crops are referenced by ``crop_artifact_id`` on a detected object
        and full unit images by ``frame_artifact_id`` on a media unit.
        """
        response = self._client.get(f"/api/v1/runs/{run_id}/artifacts/{artifact_id}")
        if response.is_error:
            self._raise_response_error(response)
        return response.content

    def wait_result(self, run_id: str, *, timeout: float = 300.0, poll_interval: float = 0.5) -> ResultEnvelope:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run = self.get_run(run_id)
            if run["status"] == "completed":
                return self.get_result(run_id)
            if run["status"] in TERMINAL_STATUSES:
                raise ScenaraError(
                    409,
                    run.get("error_code") or "RUN_TERMINATED",
                    run.get("termination_reason") or run["status"],
                )
            time.sleep(poll_interval)
        raise TimeoutError(f"run did not complete within {timeout} seconds: {run_id}")

    def parse_image(
        self,
        path: str | Path,
        *,
        domain: Domain = "portrait",
        pipeline_id: str | None = None,
        pipeline_version: str | None = None,
        idempotency_key: str | None = None,
    ) -> ParseImageResponse:
        source = Path(path)
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        data: dict[str, object] = {"domain": domain}
        if pipeline_id is not None:
            data["pipeline_id"] = pipeline_id
        if pipeline_version is not None:
            data["pipeline_version"] = pipeline_version
        with source.open("rb") as handle:
            return cast(
                ParseImageResponse,
                self._request(
                    "POST",
                    "/api/v1/parse/image",
                    files={"file": (source.name, handle, content_type)},
                    data=data,
                    headers={"Idempotency-Key": idempotency_key or f"sdk_{uuid.uuid4().hex}"},
                ),
            )

    def parse_video(
        self,
        path: str | Path,
        *,
        domain: Domain = "portrait",
        pipeline_id: str | None = None,
        pipeline_version: str | None = None,
        sample_interval_ms: int = 1_000,
        max_units: int = 64,
        sample_strategy: SampleStrategy = "interval",
        sample_start_ms: int = 0,
        sample_end_ms: int | None = None,
        scene_change_threshold: float = 0.35,
        frame_max_edge: int | None = None,
        page_scale: float = 1.5,
        camera_id: str | None = None,
        recording_started_at: float | None = None,
        wait_ms: int = 0,
        idempotency_key: str | None = None,
    ) -> ParseVideoResponse:
        source = Path(path)
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        data: dict[str, object] = {
            "domain": domain,
            "sample_interval_ms": sample_interval_ms,
            "max_units": max_units,
            "sample_strategy": sample_strategy,
            "sample_start_ms": sample_start_ms,
            "scene_change_threshold": scene_change_threshold,
            "page_scale": page_scale,
            "wait_ms": wait_ms,
        }
        if pipeline_id is not None:
            data["pipeline_id"] = pipeline_id
        if pipeline_version is not None:
            data["pipeline_version"] = pipeline_version
        if sample_end_ms is not None:
            data["sample_end_ms"] = sample_end_ms
        if frame_max_edge is not None:
            data["frame_max_edge"] = frame_max_edge
        if camera_id is not None:
            data["camera_id"] = camera_id
        if recording_started_at is not None:
            data["recording_started_at"] = recording_started_at
        with source.open("rb") as handle:
            return cast(
                ParseVideoResponse,
                self._request(
                    "POST",
                    "/api/v1/parse/video",
                    files={"file": (source.name, handle, content_type)},
                    data=data,
                    headers={"Idempotency-Key": idempotency_key or f"sdk_{uuid.uuid4().hex}"},
                ),
            )

    def parse_document(
        self,
        path: str | Path,
        *,
        domain: Domain = "ocr",
        pipeline_id: str | None = None,
        pipeline_version: str | None = None,
        max_units: int = 64,
        page_scale: float = 1.5,
        wait_ms: int = 0,
        idempotency_key: str | None = None,
    ) -> ParseDocumentResponse:
        source = Path(path)
        content_type = mimetypes.guess_type(source.name)[0] or "application/pdf"
        data: dict[str, object] = {
            "domain": domain,
            "max_units": max_units,
            "page_scale": page_scale,
            "wait_ms": wait_ms,
        }
        if pipeline_id is not None:
            data["pipeline_id"] = pipeline_id
        if pipeline_version is not None:
            data["pipeline_version"] = pipeline_version
        with source.open("rb") as handle:
            return cast(
                ParseDocumentResponse,
                self._request(
                    "POST",
                    "/api/v1/parse/document",
                    files={"file": (source.name, handle, content_type)},
                    data=data,
                    headers={"Idempotency-Key": idempotency_key or f"sdk_{uuid.uuid4().hex}"},
                ),
            )

    def parse_stream(
        self,
        source_id: str,
        *,
        domain: Domain = "portrait",
        pipeline_id: str | None = None,
        pipeline_version: str | None = None,
        sample_interval_ms: int = 1_000,
        max_units: int = 64,
        sample_strategy: SampleStrategy = "interval",
        sample_start_ms: int = 0,
        sample_end_ms: int | None = None,
        scene_change_threshold: float = 0.35,
        frame_max_edge: int | None = None,
        max_reconnect_attempts: int = 3,
        connect_timeout_ms: int = 10_000,
        read_timeout_ms: int = 10_000,
        priority: int = 0,
        wait_ms: int = 0,
        idempotency_key: str | None = None,
    ) -> Run:
        selected_pipeline = pipeline_id or ("portrait.person-detection" if domain == "portrait" else "ocr.document")
        parameters: dict[str, object] = {
            "sample_interval_ms": sample_interval_ms,
            "max_units": max_units,
            "sample_strategy": sample_strategy,
            "sample_start_ms": sample_start_ms,
            "scene_change_threshold": scene_change_threshold,
            "max_reconnect_attempts": max_reconnect_attempts,
            "connect_timeout_ms": connect_timeout_ms,
            "read_timeout_ms": read_timeout_ms,
        }
        if sample_end_ms is not None:
            parameters["sample_end_ms"] = sample_end_ms
        if frame_max_edge is not None:
            parameters["frame_max_edge"] = frame_max_edge
        pipeline: dict[str, object] = {"pipeline_id": selected_pipeline}
        if pipeline_version is not None:
            pipeline["version"] = pipeline_version
        return cast(
            Run,
            self._request(
                "POST",
                "/api/v1/parse/stream",
                json={
                    "source_id": source_id,
                    "domain": domain,
                    "pipeline": pipeline,
                    "parameters": parameters,
                    "priority": priority,
                    "wait_ms": wait_ms,
                },
                headers={"Idempotency-Key": idempotency_key or f"sdk_{uuid.uuid4().hex}"},
            ),
        )

    def list_assets(self, *, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("GET", "/api/v1/media/assets", params={"offset": offset, "limit": limit}),
        )

    def delete_asset(self, asset_id: str) -> None:
        self._request("DELETE", f"/api/v1/media/assets/{asset_id}")

    def list_datasets(self, *, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("GET", "/api/v1/datasets", params={"offset": offset, "limit": limit}),
        )

    def create_dataset(
        self, *, name: str, description: str = "", metadata: dict[str, Any] | None = None
    ) -> DatasetRecord:
        return cast(
            DatasetRecord,
            self._request(
                "POST",
                "/api/v1/datasets",
                json={"name": name, "description": description, "metadata": metadata or {}},
            ),
        )

    def get_dataset(self, dataset_id: str) -> DatasetRecord:
        return cast(DatasetRecord, self._request("GET", f"/api/v1/datasets/{dataset_id}"))

    def update_dataset(
        self,
        dataset_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DatasetRecord:
        values = {"name": name, "description": description, "status": status, "metadata": metadata}
        payload = {key: value for key, value in values.items() if value is not None}
        return cast(DatasetRecord, self._request("PATCH", f"/api/v1/datasets/{dataset_id}", json=payload))

    def create_dataset_version(
        self,
        dataset_id: str,
        *,
        version: str,
        manifest_sha256: str,
        asset_ids: list[str] | None = None,
        quality_score: float | None = None,
        lineage: dict[str, Any] | None = None,
        annotation_summary: dict[str, Any] | None = None,
    ) -> DatasetVersion:
        return cast(
            DatasetVersion,
            self._request(
                "POST",
                f"/api/v1/datasets/{dataset_id}/versions",
                json={
                    "version": version,
                    "manifest_sha256": manifest_sha256,
                    "asset_ids": asset_ids or [],
                    "quality_score": quality_score,
                    "lineage": lineage or {},
                    "annotation_summary": annotation_summary or {},
                },
            ),
        )

    def list_dataset_versions(self, dataset_id: str, *, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("GET", f"/api/v1/datasets/{dataset_id}/versions", params={"offset": offset, "limit": limit}),
        )

    def transition_dataset_version(self, version_id: str, status: str) -> DatasetVersion:
        return cast(
            DatasetVersion,
            self._request("POST", f"/api/v1/dataset-versions/{version_id}/transition", json={"status": status}),
        )

    def list_audit_events(self, **filters: Any) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", "/api/v1/audit/events", params=filters))

    def create_saved_search(
        self,
        *,
        name: str,
        mode: str,
        definition: dict[str, Any],
        description: str = "",
    ) -> SavedSearch:
        return cast(
            SavedSearch,
            self._request(
                "POST",
                "/api/v1/search/saved",
                json={"name": name, "description": description, "mode": mode, "definition": definition},
            ),
        )

    def list_saved_searches(self, *, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("GET", "/api/v1/search/saved", params={"offset": offset, "limit": limit}),
        )

    def get_saved_search(self, saved_search_id: str) -> SavedSearch:
        return cast(SavedSearch, self._request("GET", f"/api/v1/search/saved/{saved_search_id}"))

    def update_saved_search(
        self,
        saved_search_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        definition: dict[str, Any] | None = None,
    ) -> SavedSearch:
        payload = {
            key: value
            for key, value in {"name": name, "description": description, "definition": definition}.items()
            if value is not None
        }
        return cast(
            SavedSearch,
            self._request("PATCH", f"/api/v1/search/saved/{saved_search_id}", json=payload),
        )

    def run_saved_search(self, saved_search_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("POST", f"/api/v1/search/saved/{saved_search_id}/run"))

    def delete_saved_search(self, saved_search_id: str) -> None:
        self._request("DELETE", f"/api/v1/search/saved/{saved_search_id}")

    def export_audit(self, *, format: str = "json", **filters: Any) -> bytes:
        response = self._client.get("/api/v1/audit/export", params={"format": format, **filters})
        if response.is_error:
            self._raise_response_error(response)
        return response.content

    def get_asset_preview(self, asset_id: str) -> bytes:
        response = self._client.get(f"/api/v1/media/assets/{asset_id}/preview")
        if response.is_error:
            self._raise_response_error(response)
        return response.content

    def create_source(
        self,
        *,
        name: str,
        url: str,
        metadata: dict[str, Any] | None = None,
    ) -> MediaSource:
        return cast(
            MediaSource,
            self._request(
                "POST",
                "/api/v1/media/sources",
                json={"name": name, "url": url, "metadata": metadata or {}},
            ),
        )

    def list_sources(self, *, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("GET", "/api/v1/media/sources", params={"offset": offset, "limit": limit}),
        )

    def get_source(self, source_id: str) -> MediaSource:
        return cast(MediaSource, self._request("GET", f"/api/v1/media/sources/{source_id}"))

    def probe_source(self, source_id: str, *, timeout_ms: int = 10_000) -> MediaSourceProbe:
        return cast(
            MediaSourceProbe,
            self._request(
                "POST",
                f"/api/v1/media/sources/{source_id}/probe",
                params={"timeout_ms": timeout_ms},
            ),
        )

    def delete_source(self, source_id: str) -> None:
        self._request("DELETE", f"/api/v1/media/sources/{source_id}")

    def pause_run(self, run_id: str) -> Run:
        return cast(Run, self._request("POST", f"/api/v1/runs/{run_id}/pause"))

    def resume_run(self, run_id: str) -> Run:
        return cast(Run, self._request("POST", f"/api/v1/runs/{run_id}/resume"))

    def list_pipelines(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._request("GET", "/api/v1/pipelines"))

    def list_domains(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._request("GET", "/api/v1/domains"))

    def list_products(self) -> list[ProductCatalogItem]:
        return cast(list[ProductCatalogItem], self._request("GET", "/api/v1/platform/products"))

    def get_repository_topology(self) -> RepositoryTopology:
        return cast(RepositoryTopology, self._request("GET", "/api/v1/platform/repositories"))

    def get_repository_contracts(self) -> RepositoryContractCatalog:
        return cast(RepositoryContractCatalog, self._request("GET", "/api/v1/platform/contracts"))

    def get_access_foundation(self) -> AccessFoundationStatus:
        return cast(AccessFoundationStatus, self._request("GET", "/api/v1/platform/access-foundation"))

    def get_portrait_intelligence(self) -> PortraitIntelligenceStatus:
        """Return the Portrait Intelligence Foundation Platform contract.

        Reports the six strategic capability modules, three core assets,
        and per-capability readiness state for the portrait domain.
        """
        return cast(PortraitIntelligenceStatus, self._request("GET", "/api/v1/platform/portrait-intelligence"))

    def get_iam_summary(self) -> IamSummary:
        return cast(IamSummary, self._request("GET", "/api/v1/platform/iam/summary"))

    def create_organization(self, display_name: str) -> Organization:
        return cast(
            Organization,
            self._request("POST", "/api/v1/platform/organizations", json={"display_name": display_name}),
        )

    def list_organizations(self) -> list[Organization]:
        return cast(list[Organization], self._request("GET", "/api/v1/platform/organizations"))

    def create_project(self, display_name: str, *, project_id: str | None = None) -> Project:
        return cast(
            Project,
            self._request(
                "POST",
                "/api/v1/platform/projects",
                json={"display_name": display_name, "project_id": project_id},
            ),
        )

    def list_projects(self) -> list[Project]:
        return cast(list[Project], self._request("GET", "/api/v1/platform/projects"))

    def create_user(
        self,
        display_name: str,
        *,
        user_id: str | None = None,
        email: str | None = None,
        password: str | None = None,
    ) -> UserAccount:
        return cast(
            UserAccount,
            self._request(
                "POST",
                "/api/v1/platform/users",
                json={
                    "display_name": display_name,
                    "user_id": user_id,
                    "email": email,
                    "password": password,
                },
            ),
        )

    def list_users(self) -> list[UserAccount]:
        return cast(list[UserAccount], self._request("GET", "/api/v1/platform/users"))

    def create_role(
        self,
        display_name: str,
        *,
        scopes: list[str],
        product_ids: list[str] | None = None,
        role_id: str | None = None,
    ) -> Role:
        return cast(
            Role,
            self._request(
                "POST",
                "/api/v1/platform/roles",
                json={
                    "display_name": display_name,
                    "role_id": role_id,
                    "scopes": scopes,
                    "product_ids": product_ids or [],
                },
            ),
        )

    def list_roles(self) -> list[Role]:
        return cast(list[Role], self._request("GET", "/api/v1/platform/roles"))

    def create_membership(
        self,
        principal_id: str,
        *,
        principal_type: str,
        role_ids: list[str],
        project_id: str | None = None,
    ) -> Membership:
        return cast(
            Membership,
            self._request(
                "POST",
                "/api/v1/platform/memberships",
                json={
                    "principal_id": principal_id,
                    "principal_type": principal_type,
                    "role_ids": role_ids,
                    "project_id": project_id,
                },
            ),
        )

    def list_memberships(self) -> list[Membership]:
        return cast(list[Membership], self._request("GET", "/api/v1/platform/memberships"))

    def create_service_account(
        self,
        display_name: str,
        *,
        scopes: list[str],
        product_ids: list[str] | None = None,
        service_account_id: str | None = None,
    ) -> ServiceAccount:
        return cast(
            ServiceAccount,
            self._request(
                "POST",
                "/api/v1/platform/service-accounts",
                json={
                    "display_name": display_name,
                    "service_account_id": service_account_id,
                    "scopes": scopes,
                    "product_ids": product_ids or [],
                },
            ),
        )

    def list_service_accounts(self) -> list[ServiceAccount]:
        return cast(list[ServiceAccount], self._request("GET", "/api/v1/platform/service-accounts"))

    def create_api_key(
        self,
        service_account_id: str,
        *,
        name: str,
        scopes: list[str] | None = None,
        product_ids: list[str] | None = None,
        expires_at: float | None = None,
    ) -> CreateApiKeyResponse:
        return cast(
            CreateApiKeyResponse,
            self._request(
                "POST",
                f"/api/v1/platform/service-accounts/{service_account_id}/api-keys",
                json={
                    "name": name,
                    "scopes": scopes,
                    "product_ids": product_ids,
                    "expires_at": expires_at,
                },
            ),
        )

    def list_api_keys(self) -> list[ApiKeyRecord]:
        return cast(list[ApiKeyRecord], self._request("GET", "/api/v1/platform/api-keys"))

    def revoke_api_key(self, key_id: str) -> ApiKeyRecord:
        return cast(
            ApiKeyRecord,
            self._request("POST", f"/api/v1/platform/api-keys/{key_id}/revoke"),
        )

    def create_product_entitlement(
        self,
        product_id: str,
        *,
        status: str = "active",
        source: str = "manual",
        project_id: str | None = None,
    ) -> ProductEntitlement:
        return cast(
            ProductEntitlement,
            self._request(
                "POST",
                "/api/v1/platform/product-entitlements",
                json={
                    "product_id": product_id,
                    "status": status,
                    "source": source,
                    "project_id": project_id,
                },
            ),
        )

    def list_product_entitlements(self) -> list[ProductEntitlement]:
        return cast(
            list[ProductEntitlement],
            self._request("GET", "/api/v1/platform/product-entitlements"),
        )

    def update_product_entitlement(
        self,
        product_id: str,
        *,
        status: str,
        source: str = "manual",
    ) -> ProductEntitlement:
        return cast(
            ProductEntitlement,
            self._request(
                "PUT",
                f"/api/v1/platform/product-entitlements/{product_id}",
                json={"status": status, "source": source},
            ),
        )

    def list_models(self) -> list[ModelPackage]:
        return cast(list[ModelPackage], self._request("GET", "/api/v1/models"))

    def create_webhook_subscription(
        self,
        *,
        name: str,
        url: str,
        secret: str,
        event_types: list[str],
    ) -> WebhookSubscription:
        return cast(
            WebhookSubscription,
            self._request(
                "POST",
                "/api/v1/webhooks/subscriptions",
                json={"name": name, "url": url, "secret": secret, "event_types": event_types},
            ),
        )

    def list_webhook_subscriptions(self) -> list[WebhookSubscription]:
        return cast(
            list[WebhookSubscription],
            self._request("GET", "/api/v1/webhooks/subscriptions"),
        )

    def delete_webhook_subscription(self, endpoint_id: str) -> None:
        self._request("DELETE", f"/api/v1/webhooks/subscriptions/{endpoint_id}")

    def list_webhook_deliveries(self, *, limit: int = 100) -> list[WebhookDelivery]:
        return cast(
            list[WebhookDelivery],
            self._request("GET", "/api/v1/webhooks/deliveries", params={"limit": limit}),
        )

    def create_portrait_identity(
        self,
        display_name: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/api/v1/portrait/identities",
                json={"display_name": display_name, "metadata": metadata or {}},
            ),
        )

    def delete_portrait_identity(self, identity_id: str) -> None:
        self._request("DELETE", f"/api/v1/portrait/identities/{identity_id}")

    def enroll_portrait_identity(
        self,
        identity_id: str,
        enrollment: dict[str, Any],
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                f"/api/v1/portrait/identities/{identity_id}/enrollments",
                json=enrollment,
            ),
        )

    def search_portrait(self, query: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("POST", "/api/v1/portrait/search", json=query),
        )

    def compare_portrait(self, comparison: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("POST", "/api/v1/portrait/compare", json=comparison),
        )

    def list_long_term_identities(
        self,
        *,
        status: str | None = None,
        camera_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        for key, value in (
            ("status", status),
            ("camera_id", camera_id),
            ("since", since),
            ("until", until),
        ):
            if value is not None:
                params[key] = value
        return cast(
            dict[str, Any],
            self._request("GET", "/api/v1/portrait/trajectories/identities", params=params),
        )

    def get_long_term_identity(self, identity_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("GET", f"/api/v1/portrait/trajectories/identities/{identity_id}"),
        )

    def update_long_term_identity(self, identity_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "PATCH",
                f"/api/v1/portrait/trajectories/identities/{identity_id}",
                json=changes,
            ),
        )

    def delete_long_term_identity(self, identity_id: str) -> None:
        self._request("DELETE", f"/api/v1/portrait/trajectories/identities/{identity_id}")

    def list_long_term_identity_segments(
        self,
        identity_id: str,
        *,
        camera_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        for key, value in (("camera_id", camera_id), ("since", since), ("until", until)):
            if value is not None:
                params[key] = value
        return cast(
            dict[str, Any],
            self._request(
                "GET",
                f"/api/v1/portrait/trajectories/identities/{identity_id}/segments",
                params=params,
            ),
        )

    def get_long_term_identity_timeline(self, identity_id: str) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request(
                "GET",
                f"/api/v1/portrait/trajectories/identities/{identity_id}/timeline",
            ),
        )

    def merge_long_term_identities(
        self, target_identity_id: str, source_identity_ids: list[str]
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/api/v1/portrait/trajectories/identities/merge",
                json={
                    "target_identity_id": target_identity_id,
                    "source_identity_ids": source_identity_ids,
                },
            ),
        )

    def split_long_term_identity(
        self, identity_id: str, segment_ids: list[str], *, display_name: str = ""
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                f"/api/v1/portrait/trajectories/identities/{identity_id}/split",
                json={"segment_ids": segment_ids, "display_name": display_name},
            ),
        )

    def register_portrait_camera(
        self,
        camera_id: str,
        *,
        display_name: str = "",
        location: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/api/v1/portrait/cameras",
                json={
                    "camera_id": camera_id,
                    "display_name": display_name,
                    "location": location,
                    "metadata": metadata or {},
                },
            ),
        )

    def list_portrait_cameras(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._request("GET", "/api/v1/portrait/cameras"))

    def update_portrait_camera(self, camera_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("PATCH", f"/api/v1/portrait/cameras/{camera_id}", json=changes),
        )

    def delete_portrait_camera(self, camera_id: str) -> None:
        self._request("DELETE", f"/api/v1/portrait/cameras/{camera_id}")

    def list_portrait_camera_transitions(self, camera_id: str) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request("GET", f"/api/v1/portrait/cameras/{camera_id}/transitions"),
        )

    def set_portrait_camera_transitions(
        self, camera_id: str, transitions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request(
                "PUT",
                f"/api/v1/portrait/cameras/{camera_id}/transitions",
                json={"transitions": transitions},
            ),
        )

    def enroll_portrait_identity_image(
        self,
        identity_id: str,
        path: str | Path,
        *,
        feature_space_id: str | None = None,
        quality: float | None = None,
    ) -> dict[str, Any]:
        source = Path(path)
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        data = {"feature_space_id": feature_space_id, "quality": quality}
        with source.open("rb") as handle:
            return cast(
                dict[str, Any],
                self._request(
                    "POST",
                    f"/api/v1/portrait/identities/{identity_id}/enrollments/image",
                    files={"file": (source.name, handle, content_type)},
                    data={key: str(value) for key, value in data.items() if value is not None},
                ),
            )

    def search_portrait_image(
        self,
        path: str | Path,
        *,
        feature_space_id: str | None = None,
        limit: int = 20,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        source = Path(path)
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        data = {"feature_space_id": feature_space_id, "limit": limit, "threshold": threshold}
        with source.open("rb") as handle:
            return cast(
                dict[str, Any],
                self._request(
                    "POST",
                    "/api/v1/portrait/search/image",
                    files={"file": (source.name, handle, content_type)},
                    data={key: str(value) for key, value in data.items() if value is not None},
                ),
            )

    def compare_portrait_images(
        self,
        left_path: str | Path,
        right_path: str | Path,
        *,
        feature_space_id: str | None = None,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        left = Path(left_path)
        right = Path(right_path)
        left_type = mimetypes.guess_type(left.name)[0] or "application/octet-stream"
        right_type = mimetypes.guess_type(right.name)[0] or "application/octet-stream"
        data = {"feature_space_id": feature_space_id, "threshold": threshold}
        with left.open("rb") as left_handle, right.open("rb") as right_handle:
            return cast(
                dict[str, Any],
                self._request(
                    "POST",
                    "/api/v1/portrait/compare/images",
                    files={
                        "left": (left.name, left_handle, left_type),
                        "right": (right.name, right_handle, right_type),
                    },
                    data={key: str(value) for key, value in data.items() if value is not None},
                ),
            )

    def compare_portrait_asset_image(
        self,
        asset_id: str,
        image_path: str | Path,
        *,
        feature_space_id: str | None = None,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        source = Path(image_path)
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        data = {"asset_id": asset_id, "feature_space_id": feature_space_id, "threshold": threshold}
        with source.open("rb") as handle:
            return cast(
                dict[str, Any],
                self._request(
                    "POST",
                    "/api/v1/portrait/compare/asset-image",
                    files={"file": (source.name, handle, content_type)},
                    data={key: str(value) for key, value in data.items() if value is not None},
                ),
            )

    def compare_portrait_image_asset(
        self,
        image_path: str | Path,
        asset_id: str,
        *,
        feature_space_id: str | None = None,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        source = Path(image_path)
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        data = {"asset_id": asset_id, "feature_space_id": feature_space_id, "threshold": threshold}
        with source.open("rb") as handle:
            return cast(
                dict[str, Any],
                self._request(
                    "POST",
                    "/api/v1/portrait/compare/image-asset",
                    files={"file": (source.name, handle, content_type)},
                    data={key: str(value) for key, value in data.items() if value is not None},
                ),
            )

    def search_text(
        self,
        query: str,
        *,
        domains: list[str] | None = None,
        media_kinds: list[str] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/api/v1/search/text",
                json={
                    "query": query,
                    "domains": domains or [],
                    "media_kinds": media_kinds or [],
                    "limit": limit,
                },
            ),
        )

    def search_portrait_results(
        self,
        path: str | Path,
        *,
        feature_space_id: str | None = None,
        media_kinds: list[str] | None = None,
        limit: int = 50,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        source = Path(path)
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        data = {
            "feature_space_id": feature_space_id,
            "media_kinds": ",".join(media_kinds or []),
            "limit": limit,
            "threshold": threshold,
        }
        with source.open("rb") as handle:
            return cast(
                dict[str, Any],
                self._request(
                    "POST",
                    "/api/v1/search/image",
                    files={"file": (source.name, handle, content_type)},
                    data={key: str(value) for key, value in data.items() if value not in (None, "")},
                ),
            )

    def search_portrait_asset(
        self,
        asset_id: str,
        *,
        feature_space_id: str | None = None,
        media_kinds: list[str] | None = None,
        limit: int = 50,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/api/v1/search/asset",
                json={
                    "asset_id": asset_id,
                    "feature_space_id": feature_space_id,
                    "media_kinds": media_kinds or [],
                    "limit": limit,
                    "threshold": threshold,
                },
            ),
        )

    def list_search_indexes(self, *, domain: str | None = None) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request("GET", "/api/v1/indexes", params={"domain": domain} if domain else None),
        )

    def list_search_index_records(
        self,
        index_id: str,
        *,
        source_type: str | None = None,
        source_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request(
                "GET",
                f"/api/v1/indexes/{index_id}/records",
                params={
                    "source_type": source_type,
                    "source_id": source_id,
                    "offset": offset,
                    "limit": limit,
                },
            ),
        )

    def query_search_index_text(self, index_id: str, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request(
                "POST",
                f"/api/v1/indexes/{index_id}/query/text",
                json={"query": query, "limit": limit},
            ),
        )

    def query_search_index_vector(
        self,
        index_id: str,
        vector: list[float],
        *,
        limit: int = 20,
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request(
                "POST",
                f"/api/v1/indexes/{index_id}/query/vector",
                json={"vector": vector, "limit": limit, "threshold": threshold},
            ),
        )

    def enterprise_status(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", "/api/v1/enterprise/status"))

    def create_feedback(self, feedback: dict[str, Any]) -> FeedbackRecord:
        return cast(FeedbackRecord, self._request("POST", "/api/v1/feedback", json=feedback))

    def list_feedback(self) -> list[FeedbackRecord]:
        return cast(list[FeedbackRecord], self._request("GET", "/api/v1/feedback"))

    def review_feedback(self, feedback_id: str, *, status: str, notes: str = "") -> FeedbackRecord:
        return cast(
            FeedbackRecord,
            self._request(
                "POST",
                f"/api/v1/feedback/{feedback_id}/review",
                json={"status": status, "notes": notes},
            ),
        )

    def create_hard_sample_manifest(
        self,
        *,
        dataset_id: str,
        version: str,
        feedback_ids: list[str],
        label_schema: str = "scenara.feedback.correction.v1",
        split: str = "train",
    ) -> HardSampleManifest:
        return cast(
            HardSampleManifest,
            self._request(
                "POST",
                "/api/v1/hard-sample-manifests",
                json={
                    "dataset_id": dataset_id,
                    "version": version,
                    "label_schema": label_schema,
                    "split": split,
                    "feedback_ids": feedback_ids,
                },
            ),
        )

    def create_model_release(self, release: dict[str, Any]) -> ModelRelease:
        return cast(ModelRelease, self._request("POST", "/api/v1/model-releases", json=release))

    def admit_model_package(self, package: ModelPackage) -> ModelPackage:
        return cast(
            ModelPackage,
            self._request("POST", "/api/v1/model-packages/admissions", json=package),
        )

    def list_model_releases(self) -> list[ModelRelease]:
        return cast(list[ModelRelease], self._request("GET", "/api/v1/model-releases"))

    def transition_model_release(self, model_id: str, version: str, *, status: str, reason: str) -> ModelRelease:
        return cast(
            ModelRelease,
            self._request(
                "POST",
                f"/api/v1/model-releases/{model_id}/versions/{version}/transition",
                json={"status": status, "reason": reason},
            ),
        )

    def rollback_model_release(self, model_id: str, *, target_version: str, reason: str) -> ModelRelease:
        return cast(
            ModelRelease,
            self._request(
                "POST",
                f"/api/v1/model-releases/{model_id}/rollback",
                json={"target_version": target_version, "reason": reason},
            ),
        )

    def list_model_deployment_events(self, *, limit: int = 100) -> list[ModelDeploymentEvent]:
        return cast(
            list[ModelDeploymentEvent],
            self._request("GET", "/api/v1/model-deployment-events", params={"limit": limit}),
        )

    def control_plane_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Call a versioned post-1.0 control-plane resource.

        The generic escape hatch keeps the Python SDK usable as new product
        modules are enabled while their resource-specific types are generated
        from OpenAPI.
        """
        return self._request(method, path, json=json, params=params)

    def create_identity_provider(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any], self.control_plane_request("POST", "/api/v1/platform/identity-providers", json=body)
        )

    def list_identity_providers(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self.control_plane_request("GET", "/api/v1/platform/identity-providers"))

    def probe_identity_provider(self, provider_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", f"/api/v1/platform/identity-providers/{provider_id}/probe"),
        )

    def request_project_lifecycle(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", "/api/v1/platform/projects/lifecycle-requests", json=body),
        )

    def decide_project_lifecycle(self, request_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", f"/api/v1/platform/projects/lifecycle-requests/{request_id}/decide", json=body
            ),
        )

    def set_audit_retention(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("PUT", "/api/v1/platform/audit/retention", json=body))

    def purge_audit(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/platform/audit/purge", json=body))

    def create_billing_account(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/platform/billing/accounts", json=body))

    def record_meter_event(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", "/api/v1/platform/billing/meter-events", json=body),
        )

    def list_billing_usage(self, *, account_id: str | None = None) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self.control_plane_request("GET", "/api/v1/platform/billing/usage", params={"account_id": account_id}),
        )

    def assign_billing_seat(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/platform/billing/seats", json=body))

    def create_session(self, user_id: str, *, ttl_seconds: int = 3600) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", "/api/v1/platform/sessions", json={"user_id": user_id, "ttl_seconds": ttl_seconds}
            ),
        )

    def create_annotation_task(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/data/annotation-tasks", json=body))

    def register_annotation_provider(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/data/annotation-providers", json=body))

    def probe_annotation_provider(self, provider_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", f"/api/v1/data/annotation-providers/{provider_id}/probe"),
        )

    def review_annotation_task(self, task_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", f"/api/v1/data/annotation-tasks/{task_id}/review", json=body),
        )

    def create_flow(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/flows", json=body))

    def execute_flow(self, flow_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", f"/api/v1/flows/{flow_id}/execute", json={"context": context or {}}),
        )

    def decide_flow_approval(self, approval_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", f"/api/v1/flows/approvals/{approval_id}/decide", json=body),
        )

    def create_search_ranking_profile(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/search/ranking-profiles", json=body))

    def register_index_backend(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/search/index-backends", json=body))

    def probe_index_backend(self, backend_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any], self.control_plane_request("POST", f"/api/v1/search/index-backends/{backend_id}/probe")
        )

    def register_search_reranker(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/search/rerankers", json=body))

    def probe_search_reranker(self, reranker_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", f"/api/v1/search/rerankers/{reranker_id}/probe"))

    def evaluate_search(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/search/evaluations", json=body))

    def rebuild_index(self, index_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any], self.control_plane_request("POST", "/api/v1/indexes/rebuild", json={"index_id": index_id})
        )

    def create_index(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/indexes", json=body))

    def register_edge_device(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/edge/devices", json=body))

    def heartbeat_edge_device(self, device_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", f"/api/v1/edge/devices/{device_id}/heartbeat", json=body or {}),
        )

    def deploy_edge(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/edge/deployments", json=body))

    def acknowledge_edge_deployment(self, deployment_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", f"/api/v1/edge/deployments/{deployment_id}/acknowledge", json=body or {}
            ),
        )

    def register_agent_tool(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/agents/tools", json=body))

    def propose_agent_action(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/agents/actions", json=body))

    def decide_agent_action(self, action_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any], self.control_plane_request("POST", f"/api/v1/agents/actions/{action_id}/decide", json=body)
        )

    def execute_agent_action(self, action_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", f"/api/v1/agents/actions/{action_id}/execute"))

    def record_agent_trace(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/agents/traces", json=body))

    def record_agent_evaluation(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("POST", "/api/v1/agents/evaluations", json=body))

    def put_agent_memory(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self.control_plane_request("PUT", "/api/v1/agents/memory", json=body))

    def get_agent_memory(self, namespace: str, key: str) -> dict[str, Any] | None:
        return cast(
            dict[str, Any] | None,
            self.control_plane_request("GET", "/api/v1/agents/memory", params={"namespace": namespace, "key": key}),
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, path, **kwargs)
        if response.status_code == 204:
            return None
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.is_error:
            self._raise_response_error(response, payload)
        if not isinstance(payload, dict) or "data" not in payload:
            raise ScenaraError(502, "INVALID_RESPONSE", "Scenara API response is missing data")
        return payload["data"]

    @staticmethod
    def _raise_response_error(response: httpx.Response, payload: object | None = None) -> None:
        if payload is None:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        raise ScenaraError(
            response.status_code,
            str(error.get("code", "HTTP_ERROR")),
            str(error.get("message", response.reason_phrase)),
            payload.get("request_id") if isinstance(payload, dict) else None,
        )
