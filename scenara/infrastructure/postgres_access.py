from __future__ import annotations

from typing import Any

from scenara.platform.access import AccessNotFound
from scenara.platform.models import (
    ApiKeyRecord,
    Membership,
    Organization,
    ProductEntitlement,
    Project,
    Role,
    ServiceAccount,
    UserAccount,
)
from scenara.platform.store import StateConflict


class PostgresAccessRepository:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def create_organization(self, record: Organization) -> Organization:
        await self._insert_document(
            "scenara_organizations",
            ("tenant_id", "display_name", "created_at", "updated_at"),
            (record.tenant_id, record.display_name, record.created_at, record.updated_at),
            record,
            "organization already exists",
        )
        return record.model_copy(deep=True)

    async def list_organizations(self, tenant_id: str) -> list[Organization]:
        rows = await self._list_documents("scenara_organizations", "tenant_id = %s", (tenant_id,))
        return [Organization.model_validate(row) for row in rows]

    async def create_project(self, record: Project) -> Project:
        await self._insert_document(
            "scenara_projects",
            ("tenant_id", "project_id", "display_name", "created_at", "updated_at"),
            (record.tenant_id, record.project_id, record.display_name, record.created_at, record.updated_at),
            record,
            "project already exists",
        )
        return record.model_copy(deep=True)

    async def list_projects(self, tenant_id: str) -> list[Project]:
        rows = await self._list_documents("scenara_projects", "tenant_id = %s", (tenant_id,))
        return [Project.model_validate(row) for row in rows]

    async def create_user(self, record: UserAccount) -> UserAccount:
        await self._insert_document(
            "scenara_users",
            ("tenant_id", "user_id", "display_name", "email", "disabled", "created_at", "updated_at"),
            (
                record.tenant_id,
                record.user_id,
                record.display_name,
                record.email,
                record.disabled,
                record.created_at,
                record.updated_at,
            ),
            record,
            "user already exists",
        )
        return record.model_copy(deep=True)

    async def list_users(self, tenant_id: str) -> list[UserAccount]:
        rows = await self._list_documents("scenara_users", "tenant_id = %s", (tenant_id,))
        return [UserAccount.model_validate(row) for row in rows]

    async def create_role(self, record: Role) -> Role:
        await self._insert_document(
            "scenara_roles",
            ("tenant_id", "role_id", "display_name", "scopes", "product_ids", "created_at", "updated_at"),
            (
                record.tenant_id,
                record.role_id,
                record.display_name,
                sorted(record.scopes),
                sorted(record.product_ids),
                record.created_at,
                record.updated_at,
            ),
            record,
            "role already exists",
        )
        return record.model_copy(deep=True)

    async def list_roles(self, tenant_id: str) -> list[Role]:
        rows = await self._list_documents("scenara_roles", "tenant_id = %s", (tenant_id,))
        return [Role.model_validate(row) for row in rows]

    async def create_membership(self, record: Membership) -> Membership:
        await self._insert_document(
            "scenara_memberships",
            ("tenant_id", "project_id", "principal_id", "principal_type", "role_ids", "created_at", "updated_at"),
            (
                record.tenant_id,
                record.project_id,
                record.principal_id,
                record.principal_type.value,
                sorted(record.role_ids),
                record.created_at,
                record.updated_at,
            ),
            record,
            "membership already exists",
        )
        return record.model_copy(deep=True)

    async def list_memberships(self, tenant_id: str, project_id: str) -> list[Membership]:
        rows = await self._list_documents(
            "scenara_memberships", "tenant_id = %s AND project_id = %s", (tenant_id, project_id)
        )
        return [Membership.model_validate(row) for row in rows]

    async def create_service_account(self, record: ServiceAccount) -> ServiceAccount:
        await self._insert_document(
            "scenara_service_accounts",
            (
                "tenant_id",
                "project_id",
                "service_account_id",
                "display_name",
                "scopes",
                "product_ids",
                "disabled",
                "created_at",
                "updated_at",
            ),
            (
                record.tenant_id,
                record.project_id,
                record.service_account_id,
                record.display_name,
                sorted(record.scopes),
                sorted(record.product_ids),
                record.disabled,
                record.created_at,
                record.updated_at,
            ),
            record,
            "service account already exists",
        )
        return record.model_copy(deep=True)

    async def get_service_account(
        self, tenant_id: str, project_id: str, service_account_id: str
    ) -> ServiceAccount | None:
        row = await self._get_document(
            "scenara_service_accounts",
            "tenant_id = %s AND project_id = %s AND service_account_id = %s",
            (tenant_id, project_id, service_account_id),
        )
        return ServiceAccount.model_validate(row) if row else None

    async def list_service_accounts(self, tenant_id: str, project_id: str) -> list[ServiceAccount]:
        rows = await self._list_documents(
            "scenara_service_accounts", "tenant_id = %s AND project_id = %s", (tenant_id, project_id)
        )
        return [ServiceAccount.model_validate(row) for row in rows]

    async def create_api_key(self, record: ApiKeyRecord, *, token_sha256: str) -> ApiKeyRecord:
        await self._insert_document(
            "scenara_api_keys",
            (
                "tenant_id",
                "project_id",
                "key_id",
                "service_account_id",
                "token_sha256",
                "token_prefix",
                "scopes",
                "product_ids",
                "expires_at",
                "revoked_at",
                "last_used_at",
                "created_at",
            ),
            (
                record.tenant_id,
                record.project_id,
                record.key_id,
                record.service_account_id,
                token_sha256,
                record.token_prefix,
                sorted(record.scopes),
                sorted(record.product_ids),
                record.expires_at,
                record.revoked_at,
                record.last_used_at,
                record.created_at,
            ),
            record,
            "API key already exists",
        )
        return record.model_copy(deep=True)

    async def get_api_key_by_sha256(self, token_sha256: str) -> ApiKeyRecord | None:
        row = await self._get_document("scenara_api_keys", "token_sha256 = %s", (token_sha256,))
        return ApiKeyRecord.model_validate(row) if row else None

    async def list_api_keys(self, tenant_id: str, project_id: str) -> list[ApiKeyRecord]:
        rows = await self._list_documents(
            "scenara_api_keys", "tenant_id = %s AND project_id = %s", (tenant_id, project_id)
        )
        return [ApiKeyRecord.model_validate(row) for row in rows]

    async def record_api_key_used(self, tenant_id: str, project_id: str, key_id: str, used_at: float) -> None:
        await self._update_api_key_times(tenant_id, project_id, key_id, last_used_at=used_at)

    async def revoke_api_key(self, tenant_id: str, project_id: str, key_id: str, revoked_at: float) -> ApiKeyRecord:
        return await self._update_api_key_times(tenant_id, project_id, key_id, revoked_at=revoked_at)

    async def create_product_entitlement(self, record: ProductEntitlement) -> ProductEntitlement:
        await self._insert_document(
            "scenara_product_entitlements",
            ("tenant_id", "project_id", "product_id", "status", "source", "created_at", "updated_at"),
            (
                record.tenant_id,
                record.project_id,
                record.product_id,
                record.status.value,
                record.source,
                record.created_at,
                record.updated_at,
            ),
            record,
            "product entitlement already exists",
        )
        return record.model_copy(deep=True)

    async def get_product_entitlement(
        self, tenant_id: str, project_id: str, product_id: str
    ) -> ProductEntitlement | None:
        row = await self._get_document(
            "scenara_product_entitlements",
            "tenant_id = %s AND project_id = %s AND product_id = %s",
            (tenant_id, project_id, product_id),
        )
        return ProductEntitlement.model_validate(row) if row else None

    async def save_product_entitlement(self, record: ProductEntitlement) -> ProductEntitlement:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """UPDATE scenara_product_entitlements
                   SET status = %s,
                       source = %s,
                       updated_at = to_timestamp(%s::double precision),
                       document = %s
                   WHERE tenant_id = %s AND project_id = %s AND product_id = %s""",
                (
                    record.status.value,
                    record.source,
                    record.updated_at,
                    Jsonb(record.model_dump(mode="json")),
                    record.tenant_id,
                    record.project_id,
                    record.product_id,
                ),
            )
            if cursor.rowcount == 0:
                raise AccessNotFound("product entitlement not found")
        return record.model_copy(deep=True)

    async def list_product_entitlements(self, tenant_id: str, project_id: str) -> list[ProductEntitlement]:
        rows = await self._list_documents(
            "scenara_product_entitlements", "tenant_id = %s AND project_id = %s", (tenant_id, project_id)
        )
        return [ProductEntitlement.model_validate(row) for row in rows]

    async def _insert_document(
        self,
        table: str,
        columns: tuple[str, ...],
        values: tuple[object, ...],
        model: object,
        conflict_message: str,
    ) -> None:
        from psycopg.types.json import Jsonb

        placeholders = [_placeholder(column) for column in columns]
        column_sql = ", ".join((*columns, "document"))
        placeholder_sql = ", ".join((*placeholders, "%s"))
        payload = model.model_dump(mode="json")  # type: ignore[attr-defined]
        async with self._pool.connection() as conn, conn.transaction():
            try:
                await conn.execute(
                    f"INSERT INTO {table} ({column_sql}) VALUES ({placeholder_sql})",
                    (*values, Jsonb(payload)),
                )
            except Exception as exc:
                if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                    raise StateConflict(conflict_message) from exc
                raise

    async def _get_document(self, table: str, where_sql: str, params: tuple[object, ...]) -> dict[str, Any] | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(f"SELECT document FROM {table} WHERE {where_sql}", params)
            row = await cursor.fetchone()
        return row[0] if row else None

    async def _list_documents(self, table: str, where_sql: str, params: tuple[object, ...]) -> list[dict[str, Any]]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"SELECT document FROM {table} WHERE {where_sql} ORDER BY created_at DESC", params
            )
            rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def _update_api_key_times(
        self,
        tenant_id: str,
        project_id: str,
        key_id: str,
        *,
        last_used_at: float | None = None,
        revoked_at: float | None = None,
    ) -> ApiKeyRecord:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """SELECT document FROM scenara_api_keys
                   WHERE tenant_id = %s AND project_id = %s AND key_id = %s FOR UPDATE""",
                (tenant_id, project_id, key_id),
            )
            row = await cursor.fetchone()
            if row is None:
                raise AccessNotFound("API key not found")
            record = ApiKeyRecord.model_validate(row[0])
            updates: dict[str, float] = {}
            if last_used_at is not None:
                updates["last_used_at"] = last_used_at
            if revoked_at is not None:
                updates["revoked_at"] = revoked_at
            updated = record.model_copy(update=updates)
            await conn.execute(
                """UPDATE scenara_api_keys
                   SET last_used_at = to_timestamp(%s::double precision),
                       revoked_at = to_timestamp(%s::double precision),
                       document = %s
                   WHERE tenant_id = %s AND project_id = %s AND key_id = %s""",
                (
                    updated.last_used_at,
                    updated.revoked_at,
                    Jsonb(updated.model_dump(mode="json")),
                    tenant_id,
                    project_id,
                    key_id,
                ),
            )
        return updated.model_copy(deep=True)


def _placeholder(column: str) -> str:
    if column in {"created_at", "updated_at", "expires_at", "revoked_at", "last_used_at"}:
        return "to_timestamp(%s::double precision)"
    return "%s"


__all__ = ["PostgresAccessRepository"]
