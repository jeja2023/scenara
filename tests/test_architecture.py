from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from pydantic import TypeAdapter

from scenara.platform.models import DomainPayload
from scenara.platform.error_codes import REGISTERED_ERROR_CODES


def test_non_domain_modules_do_not_import_legacy_app() -> None:
    violations: list[str] = []
    for path in Path("scenara").rglob("*.py"):
        if path.parts[:3] == ("scenara", "domains", "portrait"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name == "app" or name.startswith("app."):
                    violations.append(f"{path}:{node.lineno}:{name}")
    assert violations == []


def test_infrastructure_boundary_exists_in_source_manifest() -> None:
    manifest = json.loads(Path("source-manifest.json").read_text(encoding="utf-8"))
    selection = set(manifest["selection"])
    assert "app" in selection
    assert "requirements" in selection
    assert "generated clients" in manifest["excluded"]


def test_public_error_codes_are_registered() -> None:
    server = Path("scenara/server.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'error_response\([^\n]*"([A-Z][A-Z0-9_]+)"', server))
    assert emitted <= REGISTERED_ERROR_CODES


def test_core_api_domains_are_owned_by_dedicated_routers() -> None:
    server = Path("scenara/server.py").read_text(encoding="utf-8")
    expected = {
        "access.py": ("build_access_router", "/api/v1/platform/organizations"),
        "agents.py": ("build_agents_router", "/api/v1/agents/tools"),
        "data_governance.py": (
            "build_data_governance_router",
            "/api/v1/data/annotation-tasks",
        ),
        "datasets.py": ("build_datasets_router", "/api/v1/datasets"),
        "edge.py": ("build_edge_router", "/api/v1/edge/devices"),
        "enterprise.py": ("build_enterprise_router", "/api/v1/enterprise/status"),
        "feedback.py": ("build_feedback_router", "/api/v1/feedback"),
        "flows.py": ("build_flows_router", "/api/v1/flows"),
        "iam.py": ("build_iam_router", "/api/v1/platform/identity-providers"),
        "media.py": ("build_media_router", "/api/v1/media/assets"),
        "operations.py": ("build_operations_router", "/api/v1/system/status"),
        "parse.py": ("build_parse_router", "/api/v1/parse/image"),
        "portrait.py": ("build_portrait_router", "/api/v1/portrait/identities"),
        "portrait_intelligence.py": (
            "build_portrait_intelligence_router",
            "/api/v1/portrait/clusters",
        ),
        "runs.py": ("build_runs_router", "/api/v1/runs"),
        "search.py": ("build_search_router", "/api/v1/search/text"),
        "surveillance.py": ("build_surveillance_router", "/api/v1/surveillance/watchlists"),
    }
    for filename, (factory, endpoint) in expected.items():
        router = Path("scenara/api/routers") / filename
        source = router.read_text(encoding="utf-8")
        assert factory in source
        assert endpoint in source
        assert endpoint not in server


def test_access_view_uses_domain_tabs_and_dialog_components() -> None:
    view = Path("frontend/console/src/views/AccessView.vue").read_text(encoding="utf-8")
    assert '<section class="page access-page">' in view
    assert "<style scoped>" not in view
    for component in (
        "FoundationTab",
        "IdentityTab",
        "CredentialsTab",
        "ProductsTab",
        "EventsTab",
        "IdentityDialogs",
        "CredentialsDialogs",
        "ProductsDialog",
        "EventsDialog",
        "IssuedKeyDialog",
    ):
        assert f"{component}.vue" in view
        assert f"<{component}" in view


def test_connection_settings_live_in_the_application_shell() -> None:
    """连接设置自 0.3.0-dev.43 起由全局外壳承载，不再是接入页的一个标签。"""
    shell = Path("frontend/console/src/App.vue").read_text(encoding="utf-8")
    for marker in ("loadConnection", "saveConnection", 'title="连接设置"'):
        assert marker in shell
    for module in ("views/AccessView.vue", "views/access/config.ts", "views/access/types.ts"):
        source = Path("frontend/console/src") / module
        assert "ConnectionTab" not in source.read_text(encoding="utf-8")


def test_parse_view_delegates_history_roi_and_styles() -> None:
    view = Path("frontend/console/src/views/ParseView.vue").read_text(
        encoding="utf-8"
    )
    assert "ParseHistoryPanel.vue" in view
    assert "useRoiSelection" in view
    assert 'src="./parse/parse-workbench.css"' in view
    for filename in (
        "ParseHistoryPanel.vue",
        "ParseInputControls.vue",
        "ParseMediaPreview.vue",
        "ParseWorkspaceToolbar.vue",
        "parse-workbench.css",
        "useParseMediaInput.ts",
        "useParseParameters.ts",
        "useRoiSelection.ts",
        "useResultPreview.ts",
        "useRunTracker.ts",
    ):
        assert (Path("frontend/console/src/views/parse") / filename).is_file()
    for module in (
        "ParseHistoryPanel",
        "ParseInputControls",
        "ParseMediaPreview",
        "ParseWorkspaceToolbar",
        "useParseMediaInput",
        "useParseParameters",
        "useResultPreview",
        "useRunTracker",
    ):
        assert module in view


def test_feedback_view_owns_no_embedded_page_styles() -> None:
    view = Path("frontend/console/src/views/FeedbackView.vue").read_text(
        encoding="utf-8"
    )
    assert 'src="./feedback/feedback-workbench.css"' in view
    assert (Path("frontend/console/src/views/feedback/feedback-workbench.css")).is_file()


def test_platform_kernel_has_no_domain_id_branching() -> None:
    violations: list[str] = []
    for path in Path("scenara/platform").glob("*.py"):
        if path.name == "portrait_intelligence.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.If, ast.IfExp)):
                continue
            domain_literals = {
                item.value
                for item in ast.walk(node.test)
                if isinstance(item, ast.Constant) and item.value in {"portrait", "ocr"}
            }
            if domain_literals:
                violations.append(f"{path}:{node.lineno}:{','.join(sorted(domain_literals))}")
    assert violations == []


def test_result_payload_union_accepts_new_domain_shapes() -> None:
    payload = TypeAdapter(DomainPayload).validate_python(
        {"domain": "thermal", "schema_version": "1.0", "heatmap": {"max": 0.92}}
    )
    assert payload.domain == "thermal"


def _app_module_name(path: Path) -> str:
    relative = path.with_suffix("").as_posix().replace("/", ".")
    return relative.removesuffix(".__init__")


def _resolve_app_module(reference: str, modules: set[str]) -> str | None:
    candidate = reference
    while candidate.startswith("app"):
        if candidate in modules:
            return candidate
        candidate, separator, _ = candidate.rpartition(".")
        if not separator:
            break
    return None


def _app_references(path: Path, modules: set[str]) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    references: set[str] = set()
    current = _app_module_name(path)
    package = current if path.name == "__init__.py" else current.rpartition(".")[0]
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1])
                names = [".".join(part for part in (base, node.module or "") if part)]
            elif node.module:
                names = [node.module]
            if names:
                names.extend(f"{names[0]}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names = re.findall(r"(?<![A-Za-z0-9_])(app(?:\.[A-Za-z_][A-Za-z0-9_]*)+)", node.value)
        for name in names:
            resolved = _resolve_app_module(name, modules)
            if resolved is not None:
                references.add(resolved)
    return references


def test_legacy_app_contains_no_unreachable_modules() -> None:
    app_paths = list(Path("app").rglob("*.py"))
    modules = {_app_module_name(path) for path in app_paths}
    graph = {_app_module_name(path): _app_references(path, modules) for path in app_paths}
    roots: set[str] = set()
    for source_root in (Path("scenara"), Path("tests"), Path("sdk/python"), Path("scripts")):
        for path in source_root.rglob("*.py"):
            roots.update(_app_references(path, modules))
    deployment_paths = [Path("Dockerfile"), *Path("deploy").rglob("*"), *Path(".github").rglob("*")]
    for path in deployment_paths:
        if not path.is_file():
            continue
        for reference in re.findall(
            r"(?<![A-Za-z0-9_])(app(?:\.[A-Za-z_][A-Za-z0-9_]*)+)",
            path.read_text(encoding="utf-8", errors="ignore"),
        ):
            resolved = _resolve_app_module(reference, modules)
            if resolved is not None:
                roots.add(resolved)

    reachable: set[str] = set()
    pending = list(roots)
    while pending:
        module = pending.pop()
        if module in reachable:
            continue
        reachable.add(module)
        parts = module.split(".")
        pending.extend(
            package
            for index in range(1, len(parts))
            if (package := ".".join(parts[:index])) in modules and package not in reachable
        )
        pending.extend(graph[module] - reachable)

    unreachable = sorted(modules - reachable)
    assert unreachable == [], "unreachable migration modules:\n" + "\n".join(unreachable)
