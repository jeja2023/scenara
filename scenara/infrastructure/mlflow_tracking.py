"""Minimal MLflow REST client for immutable model-package provenance."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from scenara.platform.model_runtime import ModelPackageManifest, ModelRegistryError


class MlflowRunTracker:
    """Record a ModelPackageManifest in an MLflow run using REST only."""

    def __init__(
        self,
        base_url: str,
        *,
        experiment_id: str,
        token: str = "",
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip() or not experiment_id.strip():
            raise ValueError("MLflow URL and experiment ID are required")
        if timeout_seconds <= 0:
            raise ValueError("MLflow timeout must be positive")
        self._client = client or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_seconds)
        self._owns_client = client is None
        self._experiment_id = experiment_id
        self._token = token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    async def _request(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(path, headers=self._headers(), json=body)
        except httpx.RequestError as exc:
            raise ModelRegistryError("MLflow is unavailable") from exc
        if response.status_code >= 400:
            raise ModelRegistryError(f"MLflow request failed ({response.status_code})")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ModelRegistryError("MLflow returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ModelRegistryError("MLflow returned an invalid response")
        return payload

    async def log_model_package(self, package: ModelPackageManifest, *, run_id: str | None = None) -> str:
        if run_id is None:
            created = await self._request(
                "/api/2.0/mlflow/runs/create",
                {
                    "experiment_id": self._experiment_id,
                    "start_time": int(datetime.now(UTC).timestamp() * 1000),
                    "run_name": f"{package.model_id}@{package.version}",
                },
            )
            run = created.get("run", {})
            run_info = run.get("info", {}) if isinstance(run, dict) else {}
            run_id = str(run_info.get("run_id", ""))
        if not run_id:
            raise ModelRegistryError("MLflow did not return a run ID")
        await self._request(
            "/api/2.0/mlflow/runs/log-batch",
            {
                "run_id": run_id,
                "params": [
                    {"key": "model_id", "value": package.model_id},
                    {"key": "model_version", "value": package.version},
                    {"key": "artifact_sha256", "value": package.sha256},
                ],
                "tags": [
                    {"key": "scenara.capability", "value": package.capability},
                    {"key": "scenara.package_sha256", "value": package.sha256},
                    {"key": "scenara.evaluation_evidence", "value": ",".join(package.evaluation_evidence)},
                ],
            },
        )
        return run_id

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


__all__ = ["MlflowRunTracker"]
