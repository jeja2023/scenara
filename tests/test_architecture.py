from __future__ import annotations

import ast
from pathlib import Path


def test_platform_does_not_import_domains_or_legacy_app() -> None:
    platform_root = Path("scenara/platform")
    violations: list[str] = []
    for path in platform_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name == "app" or name.startswith(("app.", "scenara.domains")):
                    violations.append(f"{path}:{node.lineno}:{name}")
    assert violations == []


def test_infrastructure_boundary_exists_in_source_manifest() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "platform" in readme.lower()
    assert "domains" in readme.lower()
    assert "infrastructure" in readme.lower()
