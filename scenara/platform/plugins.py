from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from scenara.platform.pipeline import Operator, PipelineDefinition, PipelineRegistry


@dataclass(frozen=True, slots=True)
class DomainManifest:
    domain_id: str
    display_name: str
    schema_version: str
    console_route: str
    capabilities: tuple[str, ...]


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


__all__ = ["DomainManifest", "DomainPlugin", "DomainPluginRegistry"]
