"""
Fashion Recognition Domain

服饰风格识别领域,提供 Cosplay 角色识别、服装风格检测和配饰分析能力。
"""

from __future__ import annotations

from typing import Any

__all__ = ["FashionPlugin"]


def __getattr__(name: str) -> Any:
    if name == "FashionPlugin":
        from scenara.domains.fashion.plugin import FashionPlugin

        return FashionPlugin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
