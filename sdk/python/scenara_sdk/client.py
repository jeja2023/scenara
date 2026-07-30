from __future__ import annotations

import mimetypes
import time
import uuid
from pathlib import Path
from typing import Any, cast

import httpx

from .models import (
    Domain,
    FeedbackRecord,
    HardSampleManifest,
    MediaAsset,
    ModelDeploymentEvent,
    ModelPackage,
    ModelRelease,
    ResultEnvelope,
    Run,
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
            "User-Agent": "scenara-sdk-python/0.2.0.dev0",
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

    def parse_image(self, path: str | Path, *, domain: Domain = "portrait") -> dict[str, Any]:
        source = Path(path)
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        with source.open("rb") as handle:
            return cast(
                dict[str, Any],
                self._request(
                    "POST",
                    "/api/v1/parse/image",
                    files={"file": (source.name, handle, content_type)},
                    data={"domain": domain},
                    headers={"Idempotency-Key": f"sdk_{uuid.uuid4().hex}"},
                ),
            )

    def list_assets(self, *, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("GET", "/api/v1/media/assets", params={"offset": offset, "limit": limit}),
        )

    def delete_asset(self, asset_id: str) -> None:
        self._request("DELETE", f"/api/v1/media/assets/{asset_id}")

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
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/api/v1/media/sources",
                json={"name": name, "url": url, "metadata": metadata or {}},
            ),
        )

    def pause_run(self, run_id: str) -> Run:
        return cast(Run, self._request("POST", f"/api/v1/runs/{run_id}/pause"))

    def resume_run(self, run_id: str) -> Run:
        return cast(Run, self._request("POST", f"/api/v1/runs/{run_id}/resume"))

    def list_pipelines(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._request("GET", "/api/v1/pipelines"))

    def list_domains(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._request("GET", "/api/v1/domains"))

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

    def list_model_releases(self) -> list[ModelRelease]:
        return cast(list[ModelRelease], self._request("GET", "/api/v1/model-releases"))

    def transition_model_release(
        self, model_id: str, version: str, *, status: str, reason: str
    ) -> ModelRelease:
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
