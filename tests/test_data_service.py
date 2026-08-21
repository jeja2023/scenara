from __future__ import annotations

import httpx
import pytest

from scenara_data.app import DataStore, create_data_app
from scenara.platform.data_platform import HttpDataPlatformClient
from scenara.platform.models import (
    CreateDatasetRequest,
    CreateDatasetVersionRequest,
    PrincipalContext,
    TransitionDatasetVersionRequest,
    DatasetVersionStatus,
)


@pytest.mark.asyncio
async def test_standalone_data_service_is_tenant_scoped_and_idempotent() -> None:
    store = DataStore()
    app = create_data_app(service_token="data-secret", store=store)
    transport = httpx.ASGITransport(app=app)
    headers = {
        "Authorization": "Bearer data-secret",
        "X-Scenara-Tenant-Id": "tenant_a",
        "X-Scenara-Project-Id": "project_a",
        "X-Scenara-Principal-Id": "core",
        "Idempotency-Key": "create-dataset-1",
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://data") as client:
        first = await client.post("/internal/v1/datasets", headers=headers, json={"name": "Portrait"})
        second = await client.post("/internal/v1/datasets", headers=headers, json={"name": "Portrait changed"})
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["dataset_id"] == second.json()["dataset_id"]
        hidden = await client.get(
            "/internal/v1/datasets",
            headers={**headers, "X-Scenara-Tenant-Id": "tenant_b"},
        )
        assert hidden.status_code == 200
        assert hidden.json()["total"] == 0


@pytest.mark.asyncio
async def test_standalone_data_service_version_reference_requires_ready_transition() -> None:
    app = create_data_app(service_token="data-secret")
    headers = {
        "Authorization": "Bearer data-secret",
        "X-Scenara-Tenant-Id": "tenant_a",
        "X-Scenara-Project-Id": "project_a",
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://data") as client:
        dataset = await client.post("/internal/v1/datasets", headers=headers, json={"name": "Portrait"})
        dataset_id = dataset.json()["dataset_id"]
        version = await client.post(
            f"/internal/v1/datasets/{dataset_id}/versions",
            headers=headers,
            json={"version": "1.0.0", "sample_count": 2},
        )
        version_id = version.json()["dataset_version_id"]
        rejected = await client.get(f"/internal/v1/dataset-versions/{version_id}/reference", headers=headers)
        assert rejected.status_code == 409
        transitioned = await client.post(
            f"/internal/v1/dataset-versions/{version_id}/transition",
            headers=headers,
            json={"status": "ready"},
        )
        assert transitioned.status_code == 200
        reference = await client.get(f"/internal/v1/dataset-versions/{version_id}/reference", headers=headers)
        assert reference.status_code == 200
        assert reference.json()["sample_count"] == 2


@pytest.mark.asyncio
async def test_core_http_data_client_round_trips_against_standalone_data_app() -> None:
    app = create_data_app(service_token="data-secret")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://data") as http_client:
        client = HttpDataPlatformClient("http://data", service_token="data-secret", client=http_client)
        context = PrincipalContext(
            tenant_id="tenant_a",
            project_id="project_a",
            principal_id="core",
            request_id="req-data-e2e",
            scopes=frozenset({"data.dataset.create", "data.dataset.read", "data.dataset_version.create", "data.dataset_version.read"}),
            product_ids=frozenset({"data"}),
        )
        dataset = await client.create_dataset(context, CreateDatasetRequest(name="Portrait", metadata={"source": "test"}))
        version = await client.create_dataset_version(
            context,
            dataset.dataset_id,
            CreateDatasetVersionRequest(version="1.0.0", manifest_sha256="a" * 64),
        )
        transitioned = await client.transition_dataset_version(
            context,
            version.version_id,
            TransitionDatasetVersionRequest(status=DatasetVersionStatus.VALIDATED),
        )
        assert dataset.tenant_id == "tenant_a"
        assert transitioned.status.value == "validated"
