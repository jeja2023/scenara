from __future__ import annotations

import importlib
import re
from typing import cast

from scenara.domains.fashion.operators import FashionEngine

FACTORY_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")


def load_fashion_engine(factory_path: str) -> FashionEngine:
    if not FACTORY_PATH.fullmatch(factory_path):
        raise RuntimeError("SCENARA_FASHION_ENGINE_FACTORY must use module.path:factory_name")
    module_name, factory_name = factory_path.split(":", 1)
    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, factory_name)
        engine = factory()
    except (ImportError, AttributeError, TypeError) as exc:
        raise RuntimeError("approved fashion engine factory could not be loaded") from exc
    if not callable(getattr(engine, "detect_cosplay", None)):
        raise RuntimeError("approved fashion engine must implement detect_cosplay")
    if not all(getattr(engine, name, None) for name in ("model_id", "version")):
        raise RuntimeError("approved fashion engine must declare model_id and version")
    if not bool(getattr(engine, "production_ready", False)):
        raise RuntimeError("configured fashion engine is not approved for production")
    return cast(FashionEngine, engine)


__all__ = ["load_fashion_engine"]
