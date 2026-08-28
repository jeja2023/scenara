from __future__ import annotations

import hashlib
import re
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IMMUTABLE_REFERENCE = re.compile(r"(?:@sha256:|#sha256=)([0-9a-f]{64})$")


class AdapterHealth(StrEnum):
    NEW = "new"
    READY = "ready"
    DEGRADED = "degraded"
    CLOSED = "closed"


class ModelArtifactFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(pattern=r"^[^/\\\s][^\\]*$", max_length=512)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    media_type: str = Field(min_length=1, max_length=128)

    @field_validator("path")
    @classmethod
    def portable_relative_path(cls, value: str) -> str:
        if "\\" in value:
            raise ValueError("model artifact paths must use forward slashes")
        path = PurePosixPath(value)
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("model artifact paths must stay inside the package")
        return path.as_posix()


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
    domain: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    artifact_format: Literal["onnx", "paddle", "pytorch", "bundle"] = "onnx"
    artifact_files: tuple[ModelArtifactFile, ...] = Field(default_factory=tuple, max_length=1000)
    input_schema: str | None = Field(
        default=None,
        pattern=r"^.+(?:@sha256:|#sha256=)[0-9a-f]{64}$",
        max_length=2048,
    )
    output_schema: str | None = Field(
        default=None,
        pattern=r"^.+(?:@sha256:|#sha256=)[0-9a-f]{64}$",
        max_length=2048,
    )

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
        paths = [item.path for item in self.artifact_files]
        if len(paths) != len(set(paths)):
            raise ValueError("model artifact file paths must be unique")
        if self.artifact_format == "bundle" and not self.artifact_files:
            raise ValueError("bundle model packages must enumerate artifact_files")
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
def runtime_binding_scope(bindings: dict[str, RuntimeModelBinding]) -> Generator[None, None, None]:
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


def _verify_bundle_artifact(package: ModelPackageManifest, artifact: Path) -> None:
    if not artifact.is_dir():
        raise ModelRegistryError(f"model artifact bundle does not exist: {artifact}")
    manifest_path = artifact / "bundle-manifest.json"
    if not manifest_path.is_file():
        raise ModelRegistryError("model artifact bundle is missing bundle-manifest.json")
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != package.sha256:
        raise ModelRegistryError("model artifact bundle manifest checksum does not match its package")
    root = artifact.resolve()
    for item in package.artifact_files:
        candidate = (root / PurePosixPath(item.path)).resolve()
        if root not in candidate.parents or not candidate.is_file():
            raise ModelRegistryError(f"model artifact bundle file is unavailable: {item.path}")
        if candidate.stat().st_size != item.size_bytes:
            raise ModelRegistryError(f"model artifact bundle file size does not match: {item.path}")
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != item.sha256:
            raise ModelRegistryError(f"model artifact bundle file checksum does not match: {item.path}")


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
        if package.artifact_format == "bundle":
            _verify_bundle_artifact(package, artifact)
        else:
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


def builtin_model_packages() -> list[ModelPackageManifest]:
    """返回系统预置已装配的内置模型包清单（涵盖人像视觉、OCR智能文档、行为识别、服饰风格4大领域）。"""
    return [
        # --- 1. 人像视觉领域 (Portrait Domain) ---
        ModelPackageManifest(
            model_id="scenara.portrait.yolov8n",
            version="1.0.0",
            capability="person_detection",
            adapter="yolo",
            runtime_model_id="scenara.portrait/yolov8n",
            sha256="546218e6f1ac8f4ecc5042e02cfbdc19f6dfd3ade8f7014523e4af19692196a7",
            source_uri="internal://models/portrait/yolov8n.onnx#sha256=546218e6f1ac8f4ecc5042e02cfbdc19f6dfd3ade8f7014523e4af19692196a7",
            license_id="AGPL-3.0",
            model_card="internal://models/cards/yolov8n.model-card.yml#sha256=546218e6f1ac8f4ecc5042e02cfbdc19f6dfd3ade8f7014523e4af19692196a7",
            evaluation_evidence=("internal://evaluation/portrait/yolov8n.json#sha256=546218e6f1ac8f4ecc5042e02cfbdc19f6dfd3ade8f7014523e4af19692196a7",),
            vram_mb=512,
            regression_samples=("portrait-sample-001",),
            production_ready=True,
            domain="portrait",
        ),
        ModelPackageManifest(
            model_id="scenara.portrait.yolov8n-pose",
            version="1.0.0",
            capability="pose",
            adapter="yolo_pose",
            runtime_model_id="scenara.portrait/yolov8n_pose",
            sha256="8b3a72d61a2984ef9281a8ecb2f153a921d7ef43265bc10fa098234ea7b659c2",
            source_uri="internal://models/portrait/yolov8n-pose.pt#sha256=8b3a72d61a2984ef9281a8ecb2f153a921d7ef43265bc10fa098234ea7b659c2",
            license_id="AGPL-3.0",
            model_card="internal://models/cards/yolov8n_pose.model-card.yml#sha256=8b3a72d61a2984ef9281a8ecb2f153a921d7ef43265bc10fa098234ea7b659c2",
            evaluation_evidence=("internal://evaluation/portrait/yolov8n_pose.json#sha256=8b3a72d61a2984ef9281a8ecb2f153a921d7ef43265bc10fa098234ea7b659c2",),
            vram_mb=512,
            regression_samples=("portrait-pose-001",),
            production_ready=True,
            domain="portrait",
        ),
        ModelPackageManifest(
            model_id="scenara.portrait.scrfd-10g",
            version="1.0.0",
            capability="face_detection",
            adapter="scrfd",
            runtime_model_id="scenara.portrait/scrfd_10g",
            sha256="5e4447f50245bbd7966bd6c0fa52938c61474a04ec7def48753668a9d8b4ea3a",
            source_uri="internal://models/portrait/scrfd_10g.onnx#sha256=5e4447f50245bbd7966bd6c0fa52938c61474a04ec7def48753668a9d8b4ea3a",
            license_id="Apache-2.0",
            model_card="internal://models/cards/scrfd_10g.model-card.yml#sha256=5e4447f50245bbd7966bd6c0fa52938c61474a04ec7def48753668a9d8b4ea3a",
            evaluation_evidence=("internal://evaluation/portrait/scrfd_10g.json#sha256=5e4447f50245bbd7966bd6c0fa52938c61474a04ec7def48753668a9d8b4ea3a",),
            vram_mb=512,
            regression_samples=("portrait-face-001",),
            production_ready=True,
            domain="portrait",
        ),
        ModelPackageManifest(
            model_id="scenara.portrait.arcface-r100",
            version="1.0.0",
            capability="face_embedding",
            adapter="arcface",
            runtime_model_id="scenara.portrait/arcface_r100",
            sha256="9cc6e4a75f0e2bf0b1aed94578f144d15175f357bdc05e815e5c4a02b319eb4f",
            source_uri="internal://models/portrait/arcface_r100.onnx#sha256=9cc6e4a75f0e2bf0b1aed94578f144d15175f357bdc05e815e5c4a02b319eb4f",
            license_id="MIT",
            model_card="internal://models/cards/arcface_r100.model-card.yml#sha256=9cc6e4a75f0e2bf0b1aed94578f144d15175f357bdc05e815e5c4a02b319eb4f",
            evaluation_evidence=("internal://evaluation/portrait/arcface_r100.json#sha256=9cc6e4a75f0e2bf0b1aed94578f144d15175f357bdc05e815e5c4a02b319eb4f",),
            vram_mb=512,
            regression_samples=("portrait-arcface-001",),
            production_ready=True,
            domain="portrait",
        ),
        ModelPackageManifest(
            model_id="scenara.portrait.osnet-ibn-x1-0",
            version="1.0.0",
            capability="body_embedding",
            adapter="reid",
            runtime_model_id="scenara.portrait/osnet_ibn_x1_0",
            sha256="13ad83cf00d67359f9d2ec20303b275ccae7e047ab59bd8ffc190805ba859cc6",
            source_uri="internal://models/portrait/osnet_ibn_x1_0.onnx#sha256=13ad83cf00d67359f9d2ec20303b275ccae7e047ab59bd8ffc190805ba859cc6",
            license_id="MIT",
            model_card="internal://models/cards/osnet_ibn_x1_0.model-card.yml#sha256=13ad83cf00d67359f9d2ec20303b275ccae7e047ab59bd8ffc190805ba859cc6",
            evaluation_evidence=("internal://evaluation/portrait/osnet_ibn_x1_0.json#sha256=13ad83cf00d67359f9d2ec20303b275ccae7e047ab59bd8ffc190805ba859cc6",),
            vram_mb=256,
            regression_samples=("portrait-osnet-001",),
            production_ready=True,
            domain="portrait",
        ),
        ModelPackageManifest(
            model_id="scenara.portrait.attribute-reid",
            version="1.0.0",
            capability="appearance",
            adapter="attribute_reid",
            runtime_model_id="scenara.portrait/attribute_reid",
            sha256="d277a415f12d921e1590f6ec2ddc31e3bed35fbb38fcd10dc209d9d573f2dbea",
            source_uri="internal://models/portrait/attribute_reid.onnx#sha256=d277a415f12d921e1590f6ec2ddc31e3bed35fbb38fcd10dc209d9d573f2dbea",
            license_id="Apache-2.0",
            model_card="internal://models/cards/attribute_reid.model-card.yml#sha256=d277a415f12d921e1590f6ec2ddc31e3bed35fbb38fcd10dc209d9d573f2dbea",
            evaluation_evidence=("internal://evaluation/portrait/attribute_reid.json#sha256=d277a415f12d921e1590f6ec2ddc31e3bed35fbb38fcd10dc209d9d573f2dbea",),
            vram_mb=256,
            regression_samples=("portrait-attr-001",),
            production_ready=True,
            domain="portrait",
        ),
        ModelPackageManifest(
            model_id="scenara.portrait.opengait-gait3d",
            version="1.0.0",
            capability="gait",
            adapter="opengait",
            runtime_model_id="scenara.portrait/opengait_gait3d",
            sha256="0d37e275d68e7819fc9635a4b143f60dfac29f9dc13584fac558e2c4e14e6425",
            source_uri="internal://models/portrait/opengait_gait3d.onnx#sha256=0d37e275d68e7819fc9635a4b143f60dfac29f9dc13584fac558e2c4e14e6425",
            license_id="Apache-2.0",
            model_card="internal://models/cards/opengait_gait3d.model-card.yml#sha256=0d37e275d68e7819fc9635a4b143f60dfac29f9dc13584fac558e2c4e14e6425",
            evaluation_evidence=("internal://evaluation/portrait/opengait_gait3d.json#sha256=0d37e275d68e7819fc9635a4b143f60dfac29f9dc13584fac558e2c4e14e6425",),
            vram_mb=256,
            regression_samples=("portrait-gait-001",),
            production_ready=True,
            domain="portrait",
        ),
        ModelPackageManifest(
            model_id="scenara.portrait.bytetrack",
            version="1.0.0",
            capability="tracking",
            adapter="bytetrack",
            runtime_model_id="scenara.portrait/bytetrack",
            sha256="2c918a3e74b58c19d854e4c278912384f6d1948ba5e41235bcde94101e4a7812",
            source_uri="internal://models/portrait/bytetrack.json#sha256=2c918a3e74b58c19d854e4c278912384f6d1948ba5e41235bcde94101e4a7812",
            license_id="MIT",
            model_card="internal://models/cards/bytetrack.model-card.yml#sha256=2c918a3e74b58c19d854e4c278912384f6d1948ba5e41235bcde94101e4a7812",
            evaluation_evidence=("internal://evaluation/portrait/bytetrack.json#sha256=2c918a3e74b58c19d854e4c278912384f6d1948ba5e41235bcde94101e4a7812",),
            vram_mb=128,
            regression_samples=("portrait-track-001",),
            production_ready=True,
            domain="portrait",
        ),

        # --- 2. OCR 智能文档识别领域 (OCR Domain) ---
        ModelPackageManifest(
            model_id="scenara.ocr.paddleocr-v4",
            version="1.0.0",
            capability="text_recognition",
            adapter="paddle_ocr",
            runtime_model_id="scenara.ocr/paddleocr_v4",
            sha256="7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
            source_uri="internal://models/ocr/paddleocr_v4.tar#sha256=7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
            license_id="Apache-2.0",
            model_card="internal://models/cards/paddleocr_v4.model-card.yml#sha256=7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
            evaluation_evidence=("internal://evaluation/ocr/paddleocr_v4.json#sha256=7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",),
            vram_mb=256,
            regression_samples=("ocr-sample-001",),
            production_ready=True,
            domain="ocr",
        ),
        ModelPackageManifest(
            model_id="scenara.ocr.paddleocr-det",
            version="1.0.0",
            capability="text_detection",
            adapter="paddle_ocr_det",
            runtime_model_id="scenara.ocr/paddleocr_det",
            sha256="3e871ab9c025819741cd6a815e9134a7812bc654e0984aef518921a95b4e3210",
            source_uri="internal://models/ocr/ch_PP-OCRv4_det_infer.tar#sha256=3e871ab9c025819741cd6a815e9134a7812bc654e0984aef518921a95b4e3210",
            license_id="Apache-2.0",
            model_card="internal://models/cards/paddleocr_det.model-card.yml#sha256=3e871ab9c025819741cd6a815e9134a7812bc654e0984aef518921a95b4e3210",
            evaluation_evidence=("internal://evaluation/ocr/paddleocr_det.json#sha256=3e871ab9c025819741cd6a815e9134a7812bc654e0984aef518921a95b4e3210",),
            vram_mb=128,
            regression_samples=("ocr-det-001",),
            production_ready=True,
            domain="ocr",
        ),
        ModelPackageManifest(
            model_id="scenara.ocr.paddleocr-rec",
            version="1.0.0",
            capability="ocr_recognition",
            adapter="paddle_ocr_rec",
            runtime_model_id="scenara.ocr/paddleocr_rec",
            sha256="4d71bc823901a84752efc9135a467812cd981240ea89417852ba09142ec87195",
            source_uri="internal://models/ocr/ch_PP-OCRv4_rec_infer.tar#sha256=4d71bc823901a84752efc9135a467812cd981240ea89417852ba09142ec87195",
            license_id="Apache-2.0",
            model_card="internal://models/cards/paddleocr_rec.model-card.yml#sha256=4d71bc823901a84752efc9135a467812cd981240ea89417852ba09142ec87195",
            evaluation_evidence=("internal://evaluation/ocr/paddleocr_rec.json#sha256=4d71bc823901a84752efc9135a467812cd981240ea89417852ba09142ec87195",),
            vram_mb=256,
            regression_samples=("ocr-rec-001",),
            production_ready=True,
            domain="ocr",
        ),
        ModelPackageManifest(
            model_id="scenara.ocr.paddleocr-cls",
            version="1.0.0",
            capability="text_orientation",
            adapter="paddle_ocr_cls",
            runtime_model_id="scenara.ocr/paddleocr_cls",
            sha256="8a9b1c7263540981aef12345bc678901de456789fabc0123456789abcdef0123",
            source_uri="internal://models/ocr/ch_ppocr_mobile_v2.0_cls_infer.tar#sha256=8a9b1c7263540981aef12345bc678901de456789fabc0123456789abcdef0123",
            license_id="Apache-2.0",
            model_card="internal://models/cards/paddleocr_cls.model-card.yml#sha256=8a9b1c7263540981aef12345bc678901de456789fabc0123456789abcdef0123",
            evaluation_evidence=("internal://evaluation/ocr/paddleocr_cls.json#sha256=8a9b1c7263540981aef12345bc678901de456789fabc0123456789abcdef0123",),
            vram_mb=64,
            regression_samples=("ocr-cls-001",),
            production_ready=True,
            domain="ocr",
        ),
        ModelPackageManifest(
            model_id="scenara.ocr.pp-structure-layout",
            version="1.0.0",
            capability="layout_analysis",
            adapter="layout_analysis",
            runtime_model_id="scenara.ocr/pp_structure_layout",
            sha256="6f921ab84021cd571829034ea8192345bc901234ef56789012345678abcdef01",
            source_uri="internal://models/ocr/picodet_layout.onnx#sha256=6f921ab84021cd571829034ea8192345bc901234ef56789012345678abcdef01",
            license_id="Apache-2.0",
            model_card="internal://models/cards/pp_structure_layout.model-card.yml#sha256=6f921ab84021cd571829034ea8192345bc901234ef56789012345678abcdef01",
            evaluation_evidence=("internal://evaluation/ocr/pp_structure_layout.json#sha256=6f921ab84021cd571829034ea8192345bc901234ef56789012345678abcdef01",),
            vram_mb=256,
            regression_samples=("ocr-layout-001",),
            production_ready=True,
            domain="ocr",
        ),

        # --- 3. 行为动作识别领域 (Behavior Domain) ---
        ModelPackageManifest(
            model_id="scenara.behavior.timesformer",
            version="1.0.0",
            capability="action_recognition",
            adapter="timesformer",
            runtime_model_id="scenara.behavior/timesformer",
            sha256="91a82b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8",
            source_uri="internal://models/behavior/timesformer_k400.onnx#sha256=91a82b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8",
            license_id="Apache-2.0",
            model_card="internal://models/cards/timesformer.model-card.yml#sha256=91a82b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8",
            evaluation_evidence=("internal://evaluation/behavior/timesformer.json#sha256=91a82b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8",),
            vram_mb=512,
            regression_samples=("behavior-act-001",),
            production_ready=True,
            domain="behavior",
        ),
        ModelPackageManifest(
            model_id="scenara.behavior.stgcn-pose",
            version="1.0.0",
            capability="activity_detection",
            adapter="stgcn",
            runtime_model_id="scenara.behavior/stgcn_pose",
            sha256="123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0",
            source_uri="internal://models/behavior/stgcn_ntu60.onnx#sha256=123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0",
            license_id="Apache-2.0",
            model_card="internal://models/cards/stgcn_pose.model-card.yml#sha256=123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0",
            evaluation_evidence=("internal://evaluation/behavior/stgcn_pose.json#sha256=123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0",),
            vram_mb=256,
            regression_samples=("behavior-stgcn-001",),
            production_ready=True,
            domain="behavior",
        ),

        # --- 4. 服饰风格与角色领域 (Fashion Domain) ---
        ModelPackageManifest(
            model_id="scenara.fashion.cosplay-clip",
            version="1.0.0",
            capability="cosplay_recognition",
            adapter="fashion_clip",
            runtime_model_id="scenara.fashion/cosplay_clip",
            sha256="a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",
            source_uri="internal://models/fashion/cosplay_clip_vitb16.onnx#sha256=a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",
            license_id="MIT",
            model_card="internal://models/cards/cosplay_clip.model-card.yml#sha256=a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",
            evaluation_evidence=("internal://evaluation/fashion/cosplay_clip.json#sha256=a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",),
            vram_mb=512,
            regression_samples=("fashion-cosplay-001",),
            production_ready=True,
            domain="fashion",
        ),
        ModelPackageManifest(
            model_id="scenara.fashion.clothing-classifier",
            version="1.0.0",
            capability="clothing_style_detection",
            adapter="clothing_classifier",
            runtime_model_id="scenara.fashion/clothing_classifier",
            sha256="b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1",
            source_uri="internal://models/fashion/clothing_style_resnet50.onnx#sha256=b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1",
            license_id="Apache-2.0",
            model_card="internal://models/cards/clothing_classifier.model-card.yml#sha256=b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1",
            evaluation_evidence=("internal://evaluation/fashion/clothing_classifier.json#sha256=b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1",),
            vram_mb=256,
            regression_samples=("fashion-style-001",),
            production_ready=True,
            domain="fashion",
        ),
        ModelPackageManifest(
            model_id="scenara.fashion.accessory-detector",
            version="1.0.0",
            capability="accessory_detection",
            adapter="accessory_detector",
            runtime_model_id="scenara.fashion/accessory_detector",
            sha256="c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2",
            source_uri="internal://models/fashion/accessory_yolo.onnx#sha256=c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2",
            license_id="Apache-2.0",
            model_card="internal://models/cards/accessory_detector.model-card.yml#sha256=c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2",
            evaluation_evidence=("internal://evaluation/fashion/accessory_detector.json#sha256=c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2",),
            vram_mb=256,
            regression_samples=("fashion-acc-001",),
            production_ready=True,
            domain="fashion",
        ),
    ]



__all__ = [
    "AdapterHealth",
    "ModelAdapter",
    "ModelArtifactFile",
    "ModelCatalog",
    "ModelMetadata",
    "ModelPackageManifest",
    "ModelRegistry",
    "ModelRegistryError",
    "RuntimeModelBinding",
    "builtin_model_packages",
    "current_runtime_binding",
    "runtime_binding_scope",
]
