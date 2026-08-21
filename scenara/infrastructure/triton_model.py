"""Triton HTTP model adapter behind the platform ModelAdapter port."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from scenara.platform.model_runtime import (
    AdapterHealth,
    ModelMetadata,
    ModelPackageManifest,
    ModelRegistryError,
)


class TritonModelAdapter:
    """JSON inference adapter for a Triton Inference Server deployment.

    The adapter deliberately keeps Triton's wire format at the infrastructure
    boundary. Domain operators continue to consume the existing ModelAdapter
    protocol and can therefore be tested without a GPU or a Triton process.
    """

    def __init__(
        self,
        base_url: str,
        *,
        model_name: str,
        api_key: str = "",
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip() or not model_name.strip():
            raise ValueError("Triton URL and model name are required")
        if timeout_seconds <= 0:
            raise ValueError("Triton timeout must be positive")
        self._client = client or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_seconds)
        self._owns_client = client is None
        self._model_name = model_name.strip()
        self._api_key = api_key
        self._metadata: ModelMetadata | None = None
        self._version = ""

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    async def _request(self, method: str, path: str, *, body: Any = None) -> httpx.Response:
        try:
            response = await self._client.request(method, path, headers=self._headers(), json=body)
        except httpx.RequestError as exc:
            raise ModelRegistryError("Triton is unavailable") from exc
        if response.status_code >= 400:
            raise ModelRegistryError(f"Triton request failed ({response.status_code})")
        return response

    async def load(self, package: ModelPackageManifest, artifact: Path) -> None:
        del artifact
        self._metadata = ModelMetadata(
            model_id=package.model_id,
            version=package.version,
            capability=package.capability,
            adapter=package.adapter,
            runtime_model_id=package.runtime_model_id,
            sha256=package.sha256,
            source_uri=package.source_uri,
            license_id=package.license_id,
            vram_mb=package.vram_mb,
            production_ready=package.production_ready,
        )
        self._version = package.version

    async def predict(self, inputs: Any) -> Any:
        if self._metadata is None:
            raise ModelRegistryError("Triton model adapter is not loaded")
        response = await self._request(
            "POST",
            f"/v2/models/{self._model_name}/versions/{self._version}/infer",
            body=inputs,
        )
        try:
            return response.json()
        except ValueError as exc:
            raise ModelRegistryError("Triton returned invalid inference JSON") from exc

    async def health(self) -> AdapterHealth:
        try:
            await self._request("GET", "/v2/health/ready")
            await self._request("GET", f"/v2/models/{self._model_name}/ready")
        except ModelRegistryError:
            return AdapterHealth.DEGRADED
        return AdapterHealth.READY

    def metadata(self) -> ModelMetadata:
        if self._metadata is None:
            raise ModelRegistryError("Triton model adapter is not loaded")
        return self._metadata

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


__all__ = ["TritonModelAdapter"]
