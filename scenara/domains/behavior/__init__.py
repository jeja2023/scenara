"""
Behavior Recognition Domain

行为识别领域,提供视频和流式场景下的人体动作识别、活动检测和异常行为分析能力。
"""

from __future__ import annotations

from typing import Any

__all__ = ["BehaviorPlugin"]


def __getattr__(name: str) -> Any:
    if name == "BehaviorPlugin":
        from scenara.domains.behavior.plugin import BehaviorPlugin

        return BehaviorPlugin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
