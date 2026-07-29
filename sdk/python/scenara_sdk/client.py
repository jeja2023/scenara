from __future__ import annotations

import mimetypes
import time
import uuid
from pathlib import Path
from typing import Any, cast

import httpx

from .models import Domain, MediaAsset, ResultEnvelope, Run

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
    ) -> None:
        headers = {
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "User-Agent": "scenara-sdk-python/0.1.0",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout)

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

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, path, **kwargs)
        payload = response.json()
        if response.is_error:
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            raise ScenaraError(
                response.status_code,
                str(error.get("code", "HTTP_ERROR")),
                str(error.get("message", response.reason_phrase)),
                payload.get("request_id") if isinstance(payload, dict) else None,
            )
        if not isinstance(payload, dict) or "data" not in payload:
            raise ScenaraError(502, "INVALID_RESPONSE", "Scenara API response is missing data")
        return payload["data"]
