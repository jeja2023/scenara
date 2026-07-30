from __future__ import annotations

import hashlib
import os
import time
from uuid import uuid4

import pytest

from scenara.infrastructure.postgres_access import PostgresAccessRepository
from scenara.infrastructure.postgres_state import PostgresStateStore
from scenara.platform.models import (
    ApiKeyRecord,
    EntitlementStatus,
    Membership,
    Organization,
    PrincipalType,
    ProductEntitlement,
    Project,
    Role,
    ServiceAccount,
    UserAccount,
)

pytestmark = pytest.mark.integration

POSTGRES_DSN = os.getenv(
    "SCENARA_INTEGRATION_POSTGRES_DSN",
    "postgresql://scenara:scenara-integration@127.0.0.1:55432/scenara",
)


@pytest.fixture(autouse=True)
def require_integration_services() -> None:
    if os.getenv("SCENARA_RUN_INTEGRATION") != "1":
        pytest.skip("set SCENARA_RUN_INTEGRATION=1 to run service integration tests")


@pytest.mark.asyncio
async def test_postgres_access_repository_persists_iam_and_api_key_state() -> None:
    suffix = uuid4().hex
    tenant_id = f"iam_{suffix}"
    project_id = "qualification"
    user_id = f"usr-{suffix[:24]}"
    role_id = f"role-{suffix[:24]}"
    service_account_id = f"svc-{suffix[:24]}"
    key_id = f"key-{suffix[:24]}"
    token_sha256 = hashlib.sha256(f"integration-{suffix}".encode()).hexdigest()
    now = time.time()
    state = PostgresStateStore(POSTGRES_DSN)
    await state.open()
    repository = PostgresAccessRepository(state.pool)
    try:
        await repository.create_organization(
            Organization(tenant_id=tenant_id, display_name="IAM Integration", created_at=now, updated_at=now)
        )
        await repository.create_project(
            Project(
                tenant_id=tenant_id,
                project_id=project_id,
                display_name="Qualification",
                created_at=now,
                updated_at=now,
            )
        )
        await repository.create_user(
            UserAccount(
                tenant_id=tenant_id,
                user_id=user_id,
                display_name="Integration User",
                created_at=now,
                updated_at=now,
            )
        )
        await repository.create_role(
            Role(
                tenant_id=tenant_id,
                role_id=role_id,
                display_name="Reader",
                scopes=frozenset({"iam:read"}),
                product_ids=frozenset({"console"}),
                created_at=now,
                updated_at=now,
            )
        )
        await repository.create_membership(
            Membership(
                tenant_id=tenant_id,
                project_id=project_id,
                principal_id=user_id,
                principal_type=PrincipalType.USER,
                role_ids=frozenset({role_id}),
                created_at=now,
                updated_at=now,
            )
        )
        await repository.create_service_account(
            ServiceAccount(
                tenant_id=tenant_id,
                project_id=project_id,
                service_account_id=service_account_id,
                display_name="Integration Automation",
                scopes=frozenset({"iam:read"}),
                product_ids=frozenset({"console"}),
                created_at=now,
                updated_at=now,
            )
        )
        api_key = ApiKeyRecord(
            tenant_id=tenant_id,
            project_id=project_id,
            key_id=key_id,
            service_account_id=service_account_id,
            name="Integration Key",
            token_prefix="sk_scenara_integration",
            scopes=frozenset({"iam:read"}),
            product_ids=frozenset({"console"}),
            created_at=now,
        )
        await repository.create_api_key(api_key, token_sha256=token_sha256)
        await repository.create_product_entitlement(
            ProductEntitlement(
                tenant_id=tenant_id,
                project_id=project_id,
                product_id="console",
                created_at=now,
                updated_at=now,
            )
        )

        assert (await repository.list_organizations(tenant_id))[0].tenant_id == tenant_id
        assert (await repository.list_projects(tenant_id))[0].project_id == project_id
        assert (await repository.list_users(tenant_id))[0].user_id == user_id
        assert (await repository.list_roles(tenant_id))[0].scopes == frozenset({"iam:read"})
        assert (await repository.list_memberships(tenant_id, project_id))[0].role_ids == frozenset({role_id})
        assert (await repository.list_service_accounts(tenant_id, project_id))[
            0
        ].service_account_id == service_account_id
        found_key = await repository.get_api_key_by_sha256(token_sha256)
        assert found_key is not None and found_key.key_id == key_id
        assert (await repository.list_product_entitlements(tenant_id, project_id))[0].product_id == "console"
        entitlement = await repository.get_product_entitlement(tenant_id, project_id, "console")
        assert entitlement is not None
        suspended = await repository.save_product_entitlement(
            entitlement.model_copy(
                update={"status": EntitlementStatus.SUSPENDED, "updated_at": time.time()}
            )
        )
        assert suspended.status == EntitlementStatus.SUSPENDED

        used_at = time.time()
        await repository.record_api_key_used(tenant_id, project_id, key_id, used_at)
        used = (await repository.list_api_keys(tenant_id, project_id))[0]
        assert used.last_used_at == pytest.approx(used_at)
        revoked = await repository.revoke_api_key(tenant_id, project_id, key_id, time.time())
        assert revoked.revoked_at is not None
    finally:
        async with state.pool.connection() as connection, connection.transaction():
            for table in (
                "scenara_api_keys",
                "scenara_product_entitlements",
                "scenara_memberships",
                "scenara_service_accounts",
                "scenara_projects",
                "scenara_roles",
                "scenara_users",
                "scenara_organizations",
            ):
                await connection.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (tenant_id,))
        await state.close()
