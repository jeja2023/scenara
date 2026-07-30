from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class AdapterHealth(StrEnum):
    NEW = "new"
    READY = "ready"
    DEGRADED = "degraded"
    CLOSED = "closed"


class ModelPackageManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$")
    capability: str = Field(min_length=2, max_length=128)
    adapter: str = Field(min_length=2, max_length=64)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_uri: str = Field(min_length=1, max_length=2048)
    license_id: str = Field(min_length=1, max_length=128)
    model_card: str = Field(min_length=1, max_length=1024)
    vram_mb: int = Field(ge=0, le=196_608)
    regression_samples: tuple[str, ...] = Field(min_length=1)
    production_ready: bool = False


class ModelMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    version: str
    capability: str
    adapter: str
    sha256: str
    source_uri: str
    license_id: str
    vram_mb: int
    production_ready: bool


class ModelAdapter(Protocol):
    async def load(self, package: ModelPackageManifest, artifact: Path) -> None: ...

    async def predict(self, inputs: Any) -> Any: ...

    async def health(self) -> AdapterHealth: ...

    def metadata(self) -> ModelMetadata: ...

    async def close(self) -> None: ...


class ModelCatalog(Protocol):
    async def register_model_package(self, package: ModelPackageManifest) -> None: ...

    async def list_model_packages(self) -> list[ModelPackageManifest]: ...


class ModelRegistryError(RuntimeError):
    pass


class ModelRegistry:
    def __init__(self, *, production: bool, catalog: ModelCatalog | None = None) -> None:
        self.production = production
        self._catalog = catalog
        self._adapters: dict[tuple[str, str], ModelAdapter] = {}

    async def install(
        self,
        package: ModelPackageManifest,
        artifact: Path,
        adapter: ModelAdapter,
    ) -> ModelMetadata:
        if not artifact.is_file():
            raise ModelRegistryError(f"model artifact does not exist: {artifact}")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if digest != package.sha256:
            raise ModelRegistryError("model artifact checksum does not match its manifest")
        if self.production and not package.production_ready:
            raise ModelRegistryError("production rejects a model package that is not approved")
        if self.production and (package.license_id.lower() in {"unknown", "unreviewed"}):
            raise ModelRegistryError("production rejects an unreviewed model license")
        key = (package.capability, package.version)
        if key in self._adapters:
            raise ModelRegistryError(f"model capability version already installed: {key[0]}@{key[1]}")
        await adapter.load(package, artifact)
        if await adapter.health() != AdapterHealth.READY:
            await adapter.close()
            raise ModelRegistryError("model adapter did not become ready after load")
        metadata = adapter.metadata()
        if (metadata.model_id, metadata.version, metadata.sha256) != (
            package.model_id,
            package.version,
            package.sha256,
        ):
            await adapter.close()
            raise ModelRegistryError("model adapter metadata does not match its package")
        if self._catalog is not None:
            try:
                await self._catalog.register_model_package(package)
            except Exception:
                await adapter.close()
                raise
        self._adapters[key] = adapter
        return metadata

    def resolve(self, capability: str, version: str | None = None) -> ModelAdapter:
        candidates = [
            (key, adapter)
            for key, adapter in self._adapters.items()
            if key[0] == capability and (version is None or key[1] == version)
        ]
        if not candidates:
            raise ModelRegistryError(f"model capability is not installed: {capability}")
        return sorted(candidates, key=lambda item: item[0][1])[-1][1]

    def metadata(self) -> list[ModelMetadata]:
        return [adapter.metadata() for _, adapter in sorted(self._adapters.items())]

    async def close(self) -> None:
        for adapter in self._adapters.values():
            await adapter.close()
        self._adapters.clear()


__all__ = [
    "AdapterHealth",
    "ModelAdapter",
    "ModelCatalog",
    "ModelMetadata",
    "ModelPackageManifest",
    "ModelRegistry",
    "ModelRegistryError",
]
