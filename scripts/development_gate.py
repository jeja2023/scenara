"""Fail-closed development gate for non-model P0-P2 capabilities.

This gate intentionally does not approve real model rights, model accuracy, or
target-GPU qualification.  It proves that the remaining product contracts are
present, discoverable through OpenAPI, and backed by the current migration.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scenara.server import create_app  # noqa: E402

REQUIRED_PATHS = {
    "/api/v1/platform/identity-providers",
    "/api/v1/platform/identity-providers/{provider_id}/probe",
    "/api/v1/platform/sessions",
    "/api/v1/platform/projects/lifecycle-requests",
    "/api/v1/platform/projects/lifecycle-requests/{request_id}/decide",
    "/api/v1/platform/audit/retention",
    "/api/v1/platform/audit/purge",
    "/api/v1/platform/quotas/plans",
    "/api/v1/platform/quotas/check",
    "/api/v1/platform/billing/accounts",
    "/api/v1/platform/billing/meter-events",
    "/api/v1/platform/billing/usage",
    "/api/v1/platform/billing/seats",
    "/api/v1/data/annotation-tasks",
    "/api/v1/data/annotation-providers",
    "/api/v1/data/annotation-providers/{provider_id}/probe",
    "/api/v1/search/ranking-profiles",
    "/api/v1/search/evaluations",
    "/api/v1/search/index-backends",
    "/api/v1/search/index-backends/{backend_id}/probe",
    "/api/v1/search/rerankers",
    "/api/v1/search/rerankers/{reranker_id}/probe",
    "/api/v1/indexes",
    "/api/v1/indexes/rebuild",
    "/api/v1/flows",
    "/api/v1/portrait/clusters",
    "/api/v1/portrait/associations",
    "/api/v1/portrait/events",
    "/api/v1/edge/devices",
    "/api/v1/edge/deployments",
    "/api/v1/edge/deployments/{deployment_id}/acknowledge",
    "/api/v1/agents/tools",
    "/api/v1/agents/actions",
    "/api/v1/agents/traces",
    "/api/v1/agents/evaluations",
    "/api/v1/agents/memory",
    "/api/v1/platform/workers",
    "/api/v1/platform/deployment/topology",
}


def check() -> list[str]:
    errors: list[str] = []
    migration = ROOT / "migrations/0009_control_plane_records.sql"
    if not migration.is_file():
        errors.append("missing 0009 control-plane migration")
    credential_migration = ROOT / "migrations/0010_user_credentials.sql"
    if not credential_migration.is_file():
        errors.append("missing 0010 user-credentials migration")

    app = create_app()
    paths = set(app.openapi().get("paths", {}))
    missing = sorted(REQUIRED_PATHS - paths)
    if missing:
        errors.append("missing OpenAPI paths: " + ", ".join(missing))

    product_catalog = (ROOT / "scenara/platform/product_catalog.py").read_text(encoding="utf-8")
    stale_markers = {
        '"organization administration"',
        '"role management"',
        '"product entitlements"',
        '"scoped API keys"',
    }
    for marker in sorted(stale_markers):
        if marker in product_catalog:
            errors.append(f"stale product maturity marker remains: {marker}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate non-model P0-P2 development completeness")
    parser.parse_args()
    errors = check()
    if errors:
        raise SystemExit("\n".join(errors))


if __name__ == "__main__":
    main()
