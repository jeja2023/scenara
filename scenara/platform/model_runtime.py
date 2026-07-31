from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IMMUTABLE_REFERENCE = re.compile(r"(?:@sha256:|#sha256=)([0-9a-f]{64})$")


class AdapterHealth(StrEnum):
    NEW = "new"
    READY = "ready"
    DEGRADED = "degraded"
    CLOSED = "closed"


class ModelPackageManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    model_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$")
    capability: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    adapter: str = Field(min_length=2, max_length=64)
    runtime_model_id: str = Field(pattern=r"^[^/\\\s]+/[^/\\\s]+$", max_length=384)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_uri: str = Field(min_length=1, max_length=2048)
    license_id: str = Field(min_length=1, max_length=128)
    model_card: str = Field(min_length=1, max_length=2048)
    evaluation_evidence: tuple[str, ...] = Field(min_length=1, max_length=100)
    vram_mb: int = Field(ge=0, le=196_608)
    regression_samples: tuple[str, ...] = Field(min_length=1)
    production_ready: bool = False

    @field_validator("source_uri", "model_card")
    @classmethod
    def immutable_reference(cls, value: str) -> str:
        normalized = value.strip()
        if not IMMUTABLE_REFERENCE.search(normalized):
            raise ValueError("model package references must end with an immutable SHA-256 digest")
        return normalized

    @field_validator("evaluation_evidence")
    @classmethod
    def immutable_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if len(set(normalized)) != len(normalized):
            raise ValueError("model evaluation evidence references must be unique")
        if any(not item or len(item) > 2048 or not IMMUTABLE_REFERENCE.search(item) for item in normalized):
            raise ValueError("model evaluation evidence must use immutable SHA-256 references")
        return normalized

    @model_validator(mode="after")
    def artifact_digest_matches(self) -> ModelPackageManifest:
        match = IMMUTABLE_REFERENCE.search(self.source_uri)
        if match is None or match.group(1) != self.sha256:
            raise ValueError("model artifact reference digest must match sha256")
        return self


class ModelMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    version: str
    capability: str
    adapter: str
    runtime_model_id: str
    sha256: str
    source_uri: str
    license_id: str
    vram_mb: int
    production_ready: bool


class RuntimeModelBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: str
    model_id: str
    version: str
    runtime_model_id: str
    adapter: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


_ACTIVE_RUNTIME_BINDINGS: ContextVar[dict[str, RuntimeModelBinding] | None] = ContextVar(
    "scenara_active_runtime_bindings",
    default=None,
)


def current_runtime_binding(capability: str) -> RuntimeModelBinding | None:
    bindings = _ACTIVE_RUNTIME_BINDINGS.get()
    return bindings.get(capability) if bindings is not None else None


@contextmanager
def runtime_binding_scope(bindings: dict[str, RuntimeModelBinding]) -> Iterator[None]:
    reset_handle = _ACTIVE_RUNTIME_BINDINGS.set(dict(bindings))
    try:
        yield
    finally:
        _ACTIVE_RUNTIME_BINDINGS.reset(reset_handle)


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
    "RuntimeModelBinding",
    "current_runtime_binding",
    "runtime_binding_scope",
]
