from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.model_config import config_value, configured_input_size, model_config
from app.model_config_resolver import resolve_model_reference
from app.model_package import get_model_path
from app.portrait_model_capabilities import capability_status, production_model_ready
from app.runtime_registry import get_or_load_model
from app.schemas import ModelBundle, ModelConfig
from scenara.platform.model_runtime import current_runtime_binding


@dataclass(frozen=True)
class CapabilityRuntime:
    capability_name: str
    model_id: str
    cache_key: str
    adapter: str
    capability: dict[str, Any]
    config: ModelConfig
    bundle: ModelBundle
    cold_loaded: bool = False
    load_seconds: float = 0.0

    @property
    def version(self) -> str:
        return str(self.config.get("version") or self.capability.get("version") or "")


async def get_capability_runtime(capability_name: str, adapters: Iterable[str]) -> CapabilityRuntime | None:
    capability = capability_status(capability_name)
    binding = current_runtime_binding(capability_name)
    adapter = (
        binding.adapter.strip().lower() if binding is not None else str(capability.get("adapter") or "").strip().lower()
    )
    if adapter not in {item.lower() for item in adapters}:
        return None
    if binding is None and not production_model_ready(capability_name):
        return None
    model_id = binding.runtime_model_id if binding is not None else str(capability.get("model_id") or "").strip()
    project_name, model_name, cache_key_value, _ = resolve_model_reference(model_id, None, None)
    config = model_config(cache_key_value)
    if binding is not None:
        if not config:
            raise RuntimeError(f"active model runtime is not configured: {binding.runtime_model_id}")
        if str(config.get("version") or "") != binding.version:
            raise RuntimeError("active model release version does not match its runtime configuration")
    model_path = get_model_path(project_name, model_name)
    bundle, cold_loaded, load_seconds = await get_or_load_model(cache_key_value, model_path)
    if binding is not None and bundle["model_hash"] != binding.sha256:
        raise RuntimeError("active model release digest does not match the loaded runtime artifact")
    return CapabilityRuntime(
        capability_name=capability_name,
        model_id=binding.model_id if binding is not None else cache_key_value,
        cache_key=cache_key_value,
        adapter=adapter,
        capability=capability,
        config=config,
        bundle=bundle,
        cold_loaded=cold_loaded,
        load_seconds=load_seconds,
    )


def runtime_input_size(runtime: CapabilityRuntime, default: tuple[int, int]) -> tuple[int, int]:
    configured = runtime.capability.get("input_size")
    if isinstance(configured, list) and len(configured) == 2:
        try:
            height, width = int(configured[0]), int(configured[1])
            if height > 0 and width > 0:
                default = (height, width)
        except (TypeError, ValueError):
            pass
    if runtime.adapter == "opengait":
        shape = runtime.bundle["session"].get_inputs()[0].shape
        if (
            len(shape) >= 5
            and isinstance(shape[-2], int)
            and isinstance(shape[-1], int)
            and shape[-2] > 0
            and shape[-1] > 0
        ):
            return int(shape[-2]), int(shape[-1])
    return configured_input_size(runtime.cache_key, runtime.bundle["session"], default)


def runtime_input_value(runtime: CapabilityRuntime, key: str, default: Any = None) -> Any:
    capability_input = runtime.capability.get("input")
    capability_default = (
        capability_input.get(key)
        if isinstance(capability_input, dict) and key in capability_input
        else runtime.capability.get(key, default)
    )
    return config_value(runtime.config, "input", key, capability_default)


def runtime_output_value(runtime: CapabilityRuntime, key: str, default: Any = None) -> Any:
    capability_output = runtime.capability.get("output")
    capability_default = (
        capability_output.get(key)
        if isinstance(capability_output, dict) and key in capability_output
        else runtime.capability.get(key, default)
    )
    return config_value(runtime.config, "output", key, capability_default)
