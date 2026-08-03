from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from scenara.platform.model_runtime import ModelPackageManifest
from scenara.platform.pipeline import Operator, PipelineDefinition, PipelineRegistry


@dataclass(frozen=True, slots=True)
class DomainManifest:
    domain_id: str
    display_name: str
    schema_version: str
    console_route: str
    capabilities: tuple[str, ...]
    product_scope: tuple[str, ...] = ()
    description: str = ""
    supported_media_kinds: tuple[str, ...] = ("image", "video", "document", "stream")
    default_pipeline_id: str | None = None
    navigation_order: int = 100


class DomainPlugin(Protocol):
    manifest: DomainManifest

    def operators(self) -> tuple[Operator, ...]: ...

    def pipelines(self) -> tuple[PipelineDefinition, ...]: ...


class DomainPluginRegistry:
    def __init__(self, pipelines: PipelineRegistry) -> None:
        self._pipelines = pipelines
        self._plugins: dict[str, DomainPlugin] = {}

    def register(self, plugin: DomainPlugin) -> None:
        domain_id = plugin.manifest.domain_id
        if domain_id in self._plugins:
            raise ValueError(f"domain plugin already registered: {domain_id}")
        for operator in plugin.operators():
            self._pipelines.register_operator(operator)
        for pipeline in plugin.pipelines():
            if pipeline.domain != domain_id:
                raise ValueError(f"pipeline domain mismatch for plugin: {domain_id}")
            self._pipelines.register_pipeline(pipeline)
        self._plugins[domain_id] = plugin

    def manifests(self) -> list[DomainManifest]:
        return [plugin.manifest for plugin in self._plugins.values()]

    def default_pipeline_id(self, domain_id: str) -> str:
        plugin = self._plugins.get(domain_id)
        if plugin is None:
            raise ValueError(f"domain plugin is not registered: {domain_id}")
        pipelines = plugin.pipelines()
        if not pipelines:
            raise ValueError(f"domain plugin has no pipelines: {domain_id}")
        return pipelines[0].pipeline_id

    def qualification_evidence_type(self, package: ModelPackageManifest) -> str | None:
        for plugin in self._plugins.values():
            manifest = plugin.manifest
            if package.capability in manifest.capabilities or f".{manifest.domain_id}." in package.model_id:
                return f"{manifest.domain_id}_evaluation"
        return None


__all__ = ["DomainManifest", "DomainPlugin", "DomainPluginRegistry"]
