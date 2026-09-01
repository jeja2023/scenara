from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml

from scenara import __version__
from scenara_data import __version__ as data_version
from scenara_sdk import __version__ as sdk_version

ROOT = Path(__file__).resolve().parents[1]


def _json(path: str) -> dict[str, object]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _toml(path: str) -> dict[str, object]:
    return tomllib.loads((ROOT / path).read_text(encoding="utf-8"))


def test_release_version_is_consistent_across_packages_and_openapi() -> None:
    npm_version = __version__.replace(".dev", "-dev.")
    assert _toml("pyproject.toml")["project"]["version"] == __version__
    assert _toml("sdk/python/pyproject.toml")["project"]["version"] == __version__
    assert sdk_version == __version__
    assert data_version == __version__
    assert f'APP_VERSION = "{__version__}"' in (ROOT / "app/settings.py").read_text(encoding="utf-8")
    assert _json("package.json")["version"] == npm_version
    assert _json("frontend/console/package.json")["version"] == npm_version
    assert _json("sdk/typescript/package.json")["version"] == npm_version
    assert _json("docs/openapi.json")["info"]["version"] == __version__


def test_release_version_is_consistent_across_deployment_and_documents() -> None:
    npm_version = __version__.replace(".dev", "-dev.")
    compose = yaml.safe_load((ROOT / "deploy/compose.yml").read_text(encoding="utf-8"))
    application_services = ("api", "batch-worker", "stream-worker", "scheduler")
    for service_name in application_services:
        assert compose["services"][service_name]["image"] == (
            f"${{SCENARA_IMAGE_REFERENCE:-scenara-api:${{SCENARA_IMAGE_TAG:-{npm_version}}}}}"
        )

    assert f"SCENARA_IMAGE_TAG={npm_version}" in (ROOT / "deploy/.env.production.example").read_text(
        encoding="utf-8"
    )
    assert npm_version in (ROOT / "deploy/scripts/build-offline-bundle.sh").read_text(encoding="utf-8")
    assert f"`{npm_version}`" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert (ROOT / f"docs/release/{npm_version}.md").is_file()


def test_release_version_is_consistent_for_all_container_entrypoints() -> None:
    npm_version = __version__.replace(".dev", "-dev.")
    assert f"ARG SCENARA_VERSION={npm_version}" in (ROOT / "Dockerfile").read_text(encoding="utf-8")

    data_compose = yaml.safe_load((ROOT / "deploy/compose.data.yml").read_text(encoding="utf-8"))
    data_service = data_compose["services"]["data"]
    assert data_service["image"] == f"scenara-data:${{SCENARA_DATA_IMAGE_TAG:-{npm_version}}}"
    assert set(data_service["environment"]) >= {"SCENARA_DATA_PLATFORM_SERVICE_TOKEN"}

    kustomization = yaml.safe_load((ROOT / "deploy/kubernetes/kustomization.yaml").read_text(encoding="utf-8"))
    assert kustomization["images"] == [{"name": "scenara-api", "newTag": npm_version}]
    for name in ("api.yaml", "migrate-job.yaml", "scheduler.yaml", "workers.yaml"):
        assert f"image: scenara-api:{npm_version}" in (ROOT / "deploy/kubernetes" / name).read_text(
            encoding="utf-8"
        )
