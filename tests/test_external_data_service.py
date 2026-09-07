from __future__ import annotations

import os

import pytest

from scenara.platform.data_platform import HttpDataPlatformClient
from scenara.platform.models import CreateDatasetRequest, PrincipalContext


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_core_reaches_independent_data_service_with_signed_context() -> None:
    base_url = os.environ.get("SCENARA_EXTERNAL_DATA_URL")
    service_token = os.environ.get("SCENARA_DATA_PLATFORM_SERVICE_TOKEN")
    signing_key = os.environ.get("SCENARA_DATA_CONTEXT_SIGNING_KEY")
    if not base_url or not service_token or not signing_key:
        pytest.skip("independent Data service integration variables are not configured")

    client = HttpDataPlatformClient(
        base_url,
        service_token=service_token,
        context_signing_key=signing_key,
        timeout_seconds=5,
        max_retries=0,
    )
    try:
        context = PrincipalContext(
            tenant_id="tenant-external-e2e",
            project_id="project-external-e2e",
            principal_id="core-e2e-user",
            scopes=frozenset({"data.dataset.create", "data.dataset.read"}),
            product_ids=frozenset({"data"}),
            request_id="req-external-data-e2e",
        )
        dataset = await client.create_dataset(context, CreateDatasetRequest(name="external-data-e2e"))
        assert dataset.tenant_id == context.tenant_id
        assert dataset.project_id == context.project_id
    finally:
        await client.close()
