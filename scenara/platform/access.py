from __future__ import annotations

import hashlib
import secrets
import time
from typing import Protocol
from uuid import uuid4

from scenara.platform.audit import AuditLogger
from scenara.platform.credentials import hash_password, verify_password
from scenara.platform.models import (
    ApiKeyRecord,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    CreateMembershipRequest,
    CreateOrganizationRequest,
    CreateProductEntitlementRequest,
    CreateProjectRequest,
    CreateRoleRequest,
    CreateServiceAccountRequest,
    CreateUserRequest,
    IamInventory,
    IamSummary,
    Membership,
    Organization,
    PrincipalContext,
    PrincipalType,
    ProductEntitlement,
    Project,
    Role,
    ServiceAccount,
    UpdateProductEntitlementRequest,
    UserAccount,
    UserCredential,
)
from scenara.platform.policy import PolicyDenied, PolicyProvider, require_allowed
from scenara.platform.store import StateConflict

ADMIN_SCOPES = frozenset({"*", "iam:*", "platform:*"})
ADMIN_PRODUCT_IDS = frozenset(
    {"agent", "api", "console", "data", "edge", "flow", "index", "model", "parse", "sdk", "search"}
)


class AccessNotFound(RuntimeError):
    pass


class AccessRepository(Protocol):
    async def create_organization(self, record: Organization) -> Organization: ...

    async def list_organizations(self, tenant_id: str) -> list[Organization]: ...

    async def create_project(self, record: Project) -> Project: ...

    async def list_projects(self, tenant_id: str) -> list[Project]: ...

    async def create_user(self, record: UserAccount) -> UserAccount: ...

    async def list_users(self, tenant_id: str) -> list[UserAccount]: ...

    async def save_user(self, record: UserAccount) -> UserAccount: ...

    async def create_user_credential(self, record: UserCredential) -> UserCredential: ...

    async def get_user_credential(self, tenant_id: str, user_id: str) -> UserCredential | None: ...

    async def create_role(self, record: Role) -> Role: ...

    async def list_roles(self, tenant_id: str) -> list[Role]: ...

    async def create_membership(self, record: Membership) -> Membership: ...

    async def list_memberships(self, tenant_id: str, project_id: str) -> list[Membership]: ...

    async def create_service_account(self, record: ServiceAccount) -> ServiceAccount: ...

    async def get_service_account(
        self, tenant_id: str, project_id: str, service_account_id: str
    ) -> ServiceAccount | None: ...

    async def list_service_accounts(self, tenant_id: str, project_id: str) -> list[ServiceAccount]: ...

    async def save_service_account(self, record: ServiceAccount) -> ServiceAccount: ...

    async def create_api_key(self, record: ApiKeyRecord, *, token_sha256: str) -> ApiKeyRecord: ...

    async def get_api_key_by_sha256(self, token_sha256: str) -> ApiKeyRecord | None: ...

    async def list_api_keys(self, tenant_id: str, project_id: str) -> list[ApiKeyRecord]: ...

    async def record_api_key_used(self, tenant_id: str, project_id: str, key_id: str, used_at: float) -> None: ...

    async def revoke_api_key(self, tenant_id: str, project_id: str, key_id: str, revoked_at: float) -> ApiKeyRecord: ...

    async def create_product_entitlement(self, record: ProductEntitlement) -> ProductEntitlement: ...

    async def get_product_entitlement(
        self, tenant_id: str, project_id: str, product_id: str
    ) -> ProductEntitlement | None: ...

    async def save_product_entitlement(self, record: ProductEntitlement) -> ProductEntitlement: ...

    async def list_product_entitlements(self, tenant_id: str, project_id: str) -> list[ProductEntitlement]: ...


class MemoryAccessRepository:
    def __init__(self) -> None:
        self._organizations: dict[str, Organization] = {}
        self._projects: dict[tuple[str, str], Project] = {}
        self._users: dict[tuple[str, str], UserAccount] = {}
        self._user_credentials: dict[tuple[str, str], UserCredential] = {}
        self._roles: dict[tuple[str, str], Role] = {}
        self._memberships: dict[tuple[str, str, str], Membership] = {}
        self._service_accounts: dict[tuple[str, str, str], ServiceAccount] = {}
        self._api_keys: dict[tuple[str, str, str], ApiKeyRecord] = {}
        self._api_key_hashes: dict[str, tuple[str, str, str]] = {}
        self._product_entitlements: dict[tuple[str, str, str], ProductEntitlement] = {}

    async def create_organization(self, record: Organization) -> Organization:
        if record.tenant_id in self._organizations:
            raise StateConflict("organization already exists")
        self._organizations[record.tenant_id] = record.model_copy(deep=True)
        return record.model_copy(deep=True)

    async def list_organizations(self, tenant_id: str) -> list[Organization]:
        record = self._organizations.get(tenant_id)
        return [record.model_copy(deep=True)] if record else []

    async def create_project(self, record: Project) -> Project:
        key = (record.tenant_id, record.project_id)
        if key in self._projects:
            raise StateConflict("project already exists")
        self._projects[key] = record.model_copy(deep=True)
        return record.model_copy(deep=True)

    async def list_projects(self, tenant_id: str) -> list[Project]:
        return sorted(
            (item.model_copy(deep=True) for (row_tenant, _), item in self._projects.items() if row_tenant == tenant_id),
            key=lambda item: (item.created_at, item.project_id),
            reverse=True,
        )

    async def create_user(self, record: UserAccount) -> UserAccount:
        key = (record.tenant_id, record.user_id)
        if key in self._users:
            raise StateConflict("user already exists")
        self._users[key] = record.model_copy(deep=True)
        return record.model_copy(deep=True)

    async def list_users(self, tenant_id: str) -> list[UserAccount]:
        return sorted(
            (item.model_copy(deep=True) for (row_tenant, _), item in self._users.items() if row_tenant == tenant_id),
            key=lambda item: (item.created_at, item.user_id),
            reverse=True,
        )

    async def save_user(self, record: UserAccount) -> UserAccount:
        key = (record.tenant_id, record.user_id)
        if key not in self._users:
            raise AccessNotFound("user not found")
        self._users[key] = record.model_copy(deep=True)
        return record.model_copy(deep=True)

    async def create_user_credential(self, record: UserCredential) -> UserCredential:
        key = (record.tenant_id, record.user_id)
        if key in self._user_credentials:
            raise StateConflict("user credential already exists")
        self._user_credentials[key] = record.model_copy(deep=True)
        return record.model_copy(deep=True)

    async def get_user_credential(self, tenant_id: str, user_id: str) -> UserCredential | None:
        record = self._user_credentials.get((tenant_id, user_id))
        return record.model_copy(deep=True) if record else None

    async def create_role(self, record: Role) -> Role:
        key = (record.tenant_id, record.role_id)
        if key in self._roles:
            raise StateConflict("role already exists")
        self._roles[key] = record.model_copy(deep=True)
        return record.model_copy(deep=True)

    async def list_roles(self, tenant_id: str) -> list[Role]:
        return sorted(
            (item.model_copy(deep=True) for (row_tenant, _), item in self._roles.items() if row_tenant == tenant_id),
            key=lambda item: (item.created_at, item.role_id),
            reverse=True,
        )

    async def create_membership(self, record: Membership) -> Membership:
        key = (record.tenant_id, record.project_id, record.principal_id)
        if key in self._memberships:
            raise StateConflict("membership already exists")
        self._memberships[key] = record.model_copy(deep=True)
        return record.model_copy(deep=True)

    async def list_memberships(self, tenant_id: str, project_id: str) -> list[Membership]:
        return sorted(
            (
                item.model_copy(deep=True)
                for key, item in self._memberships.items()
                if key[:2] == (tenant_id, project_id)
            ),
            key=lambda item: (item.created_at, item.principal_id),
            reverse=True,
        )

    async def create_service_account(self, record: ServiceAccount) -> ServiceAccount:
        key = (record.tenant_id, record.project_id, record.service_account_id)
        if key in self._service_accounts:
            raise StateConflict("service account already exists")
        self._service_accounts[key] = record.model_copy(deep=True)
        return record.model_copy(deep=True)

    async def get_service_account(
        self, tenant_id: str, project_id: str, service_account_id: str
    ) -> ServiceAccount | None:
        record = self._service_accounts.get((tenant_id, project_id, service_account_id))
        return record.model_copy(deep=True) if record else None

    async def list_service_accounts(self, tenant_id: str, project_id: str) -> list[ServiceAccount]:
        return sorted(
            (
                item.model_copy(deep=True)
                for key, item in self._service_accounts.items()
                if key[:2] == (tenant_id, project_id)
            ),
            key=lambda item: (item.created_at, item.service_account_id),
            reverse=True,
        )

    async def save_service_account(self, record: ServiceAccount) -> ServiceAccount:
        key = (record.tenant_id, record.project_id, record.service_account_id)
        if key not in self._service_accounts:
            raise AccessNotFound("service account not found")
        self._service_accounts[key] = record.model_copy(deep=True)
        return record.model_copy(deep=True)

    async def create_api_key(self, record: ApiKeyRecord, *, token_sha256: str) -> ApiKeyRecord:
        key = (record.tenant_id, record.project_id, record.key_id)
        if key in self._api_keys or token_sha256 in self._api_key_hashes:
            raise StateConflict("API key already exists")
        self._api_keys[key] = record.model_copy(deep=True)
        self._api_key_hashes[token_sha256] = key
        return record.model_copy(deep=True)

    async def get_api_key_by_sha256(self, token_sha256: str) -> ApiKeyRecord | None:
        key = self._api_key_hashes.get(token_sha256)
        if key is None:
            return None
        record = self._api_keys.get(key)
        return record.model_copy(deep=True) if record else None

    async def list_api_keys(self, tenant_id: str, project_id: str) -> list[ApiKeyRecord]:
        return sorted(
            (item.model_copy(deep=True) for key, item in self._api_keys.items() if key[:2] == (tenant_id, project_id)),
            key=lambda item: (item.created_at, item.key_id),
            reverse=True,
        )

    async def record_api_key_used(self, tenant_id: str, project_id: str, key_id: str, used_at: float) -> None:
        key = (tenant_id, project_id, key_id)
        record = self._api_keys.get(key)
        if record is not None:
            self._api_keys[key] = record.model_copy(update={"last_used_at": used_at})

    async def revoke_api_key(self, tenant_id: str, project_id: str, key_id: str, revoked_at: float) -> ApiKeyRecord:
        key = (tenant_id, project_id, key_id)
        record = self._api_keys.get(key)
        if record is None:
            raise AccessNotFound("API key not found")
        updated = record.model_copy(update={"revoked_at": revoked_at})
        self._api_keys[key] = updated
        return updated.model_copy(deep=True)

    async def create_product_entitlement(self, record: ProductEntitlement) -> ProductEntitlement:
        key = (record.tenant_id, record.project_id, record.product_id)
        if key in self._product_entitlements:
            raise StateConflict("product entitlement already exists")
        self._product_entitlements[key] = record.model_copy(deep=True)
        return record.model_copy(deep=True)

    async def get_product_entitlement(
        self, tenant_id: str, project_id: str, product_id: str
    ) -> ProductEntitlement | None:
        record = self._product_entitlements.get((tenant_id, project_id, product_id))
        return record.model_copy(deep=True) if record else None

    async def save_product_entitlement(self, record: ProductEntitlement) -> ProductEntitlement:
        key = (record.tenant_id, record.project_id, record.product_id)
        if key not in self._product_entitlements:
            raise AccessNotFound("product entitlement not found")
        self._product_entitlements[key] = record.model_copy(deep=True)
        return record.model_copy(deep=True)

    async def list_product_entitlements(self, tenant_id: str, project_id: str) -> list[ProductEntitlement]:
        return sorted(
            (
                item.model_copy(deep=True)
                for key, item in self._product_entitlements.items()
                if key[:2] == (tenant_id, project_id)
            ),
            key=lambda item: (item.created_at, item.product_id),
            reverse=True,
        )


class AccessService:
    def __init__(self, repository: AccessRepository, audit: AuditLogger, policy: PolicyProvider) -> None:
        self.repository = repository
        self._audit = audit
        self._policy = policy

    async def authenticate_api_key(self, token: str) -> PrincipalContext | None:
        record = await self.repository.get_api_key_by_sha256(_token_sha256(token))
        now = time.time()
        if record is None or record.revoked_at is not None:
            return None
        if record.expires_at is not None and record.expires_at <= now:
            return None
        service_account = await self.repository.get_service_account(
            record.tenant_id, record.project_id, record.service_account_id
        )
        if service_account is None or service_account.disabled:
            return None
        await self.repository.record_api_key_used(record.tenant_id, record.project_id, record.key_id, now)
        scopes = frozenset(
            scope for scope in record.scopes if _scopes_within(frozenset({scope}), service_account.scopes)
        )
        entitlements = await self.repository.list_product_entitlements(record.tenant_id, record.project_id)
        active_product_ids = frozenset(item.product_id for item in entitlements if item.status.value == "active")
        product_ids = record.product_ids & service_account.product_ids & active_product_ids
        if not scopes:
            return None
        return PrincipalContext(
            tenant_id=record.tenant_id,
            project_id=record.project_id,
            principal_id=record.service_account_id,
            scopes=scopes,
            product_ids=product_ids,
        )

    async def ensure_bootstrap_admin(
        self,
        *,
        tenant_id: str,
        project_id: str,
        username: str,
        password: str,
    ) -> None:
        if not username or not password:
            return
        now = time.time()
        if not await self.repository.list_organizations(tenant_id):
            await self.repository.create_organization(
                Organization(
                    tenant_id=tenant_id,
                    display_name="Scenara",
                    created_at=now,
                    updated_at=now,
                )
            )
        if not any(item.project_id == project_id for item in await self.repository.list_projects(tenant_id)):
            await self.repository.create_project(
                Project(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    display_name="Scenara Console",
                    created_at=now,
                    updated_at=now,
                )
            )
        users = await self.repository.list_users(tenant_id)
        if not any(item.user_id == username for item in users):
            await self.repository.create_user(
                UserAccount(
                    tenant_id=tenant_id,
                    user_id=username,
                    display_name=username,
                    created_at=now,
                    updated_at=now,
                )
            )
        if await self.repository.get_user_credential(tenant_id, username) is None:
            await self.repository.create_user_credential(
                UserCredential(
                    tenant_id=tenant_id,
                    user_id=username,
                    password_hash=hash_password(password),
                    created_at=now,
                    updated_at=now,
                )
            )
        role_id = "console-admin"
        roles = await self.repository.list_roles(tenant_id)
        if not any(item.role_id == role_id for item in roles):
            await self.repository.create_role(
                Role(
                    tenant_id=tenant_id,
                    role_id=role_id,
                    display_name="Console Administrator",
                    scopes=ADMIN_SCOPES,
                    product_ids=ADMIN_PRODUCT_IDS,
                    created_at=now,
                    updated_at=now,
                )
            )
        memberships = await self.repository.list_memberships(tenant_id, project_id)
        if not any(item.principal_id == username for item in memberships):
            await self.repository.create_membership(
                Membership(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    principal_id=username,
                    principal_type=PrincipalType.USER,
                    role_ids=frozenset({role_id}),
                    created_at=now,
                    updated_at=now,
                )
            )

    async def is_user_disabled(self, tenant_id: str, user_id: str) -> bool:
        """Return the current lifecycle flag for session authentication."""
        users = await self.repository.list_users(tenant_id)
        user = next((item for item in users if item.user_id == user_id), None)
        return bool(user and user.disabled)

    async def authenticate_user(
        self, username: str, password: str, tenant_id: str, project_id: str
    ) -> PrincipalContext | None:
        users = await self.repository.list_users(tenant_id)
        user = next((item for item in users if item.user_id == username), None)
        if user is None or user.disabled:
            return None
        credential = await self.repository.get_user_credential(tenant_id, username)
        if credential is None or not verify_password(password, credential.password_hash):
            return None
        return await self.resolve_user_context(tenant_id, project_id, username)

    async def resolve_user_context(self, tenant_id: str, project_id: str, user_id: str) -> PrincipalContext | None:
        """Resolve a user's effective scopes from project memberships and roles."""
        users = await self.repository.list_users(tenant_id)
        user = next((item for item in users if item.user_id == user_id), None)
        if user is None or user.disabled:
            return None
        memberships = await self.repository.list_memberships(tenant_id, project_id)
        membership = (
            next(
                item
                for item in memberships
                if item.principal_id == user_id and item.principal_type == PrincipalType.USER
            )
            if memberships
            else None
        )
        if membership is None:
            return None
        roles = {item.role_id: item for item in await self.repository.list_roles(tenant_id)}
        scopes = frozenset(
            scope for role_id in membership.role_ids for scope in (roles[role_id].scopes if role_id in roles else ())
        )
        products = frozenset(
            product
            for role_id in membership.role_ids
            for product in (roles[role_id].product_ids if role_id in roles else ())
        )
        return PrincipalContext(
            tenant_id=tenant_id,
            project_id=project_id,
            principal_id=user_id,
            scopes=scopes,
            product_ids=products,
        )

    async def create_organization(self, context: PrincipalContext, body: CreateOrganizationRequest) -> Organization:
        await self._authorize(context, "create")
        now = time.time()
        record = Organization(
            tenant_id=context.tenant_id, display_name=body.display_name, created_at=now, updated_at=now
        )
        created = await self.repository.create_organization(record)
        await self._record(context, "iam.organization.create", "organization", created.tenant_id)
        return created

    async def list_organizations(self, context: PrincipalContext) -> list[Organization]:
        await self._authorize(context, "read")
        return await self.repository.list_organizations(context.tenant_id)

    async def create_project(self, context: PrincipalContext, body: CreateProjectRequest) -> Project:
        await self._authorize(context, "create")
        await self._require_organization(context.tenant_id)
        now = time.time()
        record = Project(
            tenant_id=context.tenant_id,
            project_id=body.project_id or context.project_id,
            display_name=body.display_name,
            created_at=now,
            updated_at=now,
        )
        created = await self.repository.create_project(record)
        await self._record(context, "iam.project.create", "project", created.project_id)
        return created

    async def list_projects(self, context: PrincipalContext) -> list[Project]:
        await self._authorize(context, "read")
        return await self.repository.list_projects(context.tenant_id)

    async def create_user(self, context: PrincipalContext, body: CreateUserRequest) -> UserAccount:
        await self._authorize(context, "create")
        await self._require_organization(context.tenant_id)
        now = time.time()
        record = UserAccount(
            tenant_id=context.tenant_id,
            user_id=body.user_id or _new_id("usr"),
            display_name=body.display_name,
            email=body.email,
            created_at=now,
            updated_at=now,
        )
        created = await self.repository.create_user(record)
        if body.password:
            now = time.time()
            await self.repository.create_user_credential(
                UserCredential(
                    tenant_id=created.tenant_id,
                    user_id=created.user_id,
                    password_hash=hash_password(body.password),
                    created_at=now,
                    updated_at=now,
                )
            )
        await self._record(context, "iam.user.create", "user", created.user_id)
        return created

    async def list_users(self, context: PrincipalContext) -> list[UserAccount]:
        await self._authorize(context, "read")
        return await self.repository.list_users(context.tenant_id)

    async def set_user_disabled(self, context: PrincipalContext, user_id: str, disabled: bool) -> UserAccount:
        await self._authorize(context, "write")
        users = await self.repository.list_users(context.tenant_id)
        user = next((item for item in users if item.user_id == user_id), None)
        if user is None:
            raise AccessNotFound("user not found")
        updated = user.model_copy(update={"disabled": disabled, "updated_at": time.time()})
        result = await self.repository.save_user(updated)
        await self._record(context, "iam.user.disable" if disabled else "iam.user.restore", "user", user_id)
        return result

    async def create_role(self, context: PrincipalContext, body: CreateRoleRequest) -> Role:
        await self._authorize(context, "create")
        await self._require_organization(context.tenant_id)
        now = time.time()
        record = Role(
            tenant_id=context.tenant_id,
            role_id=body.role_id or _new_id("role"),
            display_name=body.display_name,
            scopes=body.scopes,
            product_ids=body.product_ids,
            created_at=now,
            updated_at=now,
        )
        created = await self.repository.create_role(record)
        await self._record(context, "iam.role.create", "role", created.role_id)
        return created

    async def list_roles(self, context: PrincipalContext) -> list[Role]:
        await self._authorize(context, "read")
        return await self.repository.list_roles(context.tenant_id)

    async def create_membership(self, context: PrincipalContext, body: CreateMembershipRequest) -> Membership:
        await self._authorize(context, "create")
        now = time.time()
        project_id = _context_project_id(context, body.project_id)
        await self._require_project(context.tenant_id, project_id)
        if body.principal_type.value == "user":
            users = await self.repository.list_users(context.tenant_id)
            principal_exists = any(item.user_id == body.principal_id for item in users)
        else:
            principal_exists = (
                await self.repository.get_service_account(context.tenant_id, project_id, body.principal_id) is not None
            )
        if not principal_exists:
            raise AccessNotFound("membership principal not found")
        roles = await self.repository.list_roles(context.tenant_id)
        known_role_ids = {item.role_id for item in roles}
        if not body.role_ids.issubset(known_role_ids):
            raise AccessNotFound("membership role not found")
        record = Membership(
            tenant_id=context.tenant_id,
            project_id=project_id,
            principal_id=body.principal_id,
            principal_type=body.principal_type,
            role_ids=body.role_ids,
            created_at=now,
            updated_at=now,
        )
        created = await self.repository.create_membership(record)
        await self._record(context, "iam.membership.create", "membership", created.principal_id)
        return created

    async def list_memberships(self, context: PrincipalContext) -> list[Membership]:
        await self._authorize(context, "read")
        return await self.repository.list_memberships(context.tenant_id, context.project_id)

    async def create_service_account(
        self, context: PrincipalContext, body: CreateServiceAccountRequest
    ) -> ServiceAccount:
        await self._authorize(context, "create")
        await self._require_project(context.tenant_id, context.project_id)
        now = time.time()
        record = ServiceAccount(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            service_account_id=body.service_account_id or _new_id("svc"),
            display_name=body.display_name,
            scopes=body.scopes,
            product_ids=body.product_ids,
            created_at=now,
            updated_at=now,
        )
        created = await self.repository.create_service_account(record)
        await self._record(context, "iam.service-account.create", "service_account", created.service_account_id)
        return created

    async def list_service_accounts(self, context: PrincipalContext) -> list[ServiceAccount]:
        await self._authorize(context, "read")
        return await self.repository.list_service_accounts(context.tenant_id, context.project_id)

    async def set_service_account_disabled(
        self, context: PrincipalContext, service_account_id: str, disabled: bool
    ) -> ServiceAccount:
        await self._authorize(context, "write")
        service_account = await self.repository.get_service_account(
            context.tenant_id, context.project_id, service_account_id
        )
        if service_account is None:
            raise AccessNotFound("service account not found")
        updated = service_account.model_copy(update={"disabled": disabled, "updated_at": time.time()})
        result = await self.repository.save_service_account(updated)
        await self._record(
            context,
            "iam.service-account.disable" if disabled else "iam.service-account.restore",
            "service_account",
            service_account_id,
        )
        return result

    async def create_api_key(
        self, context: PrincipalContext, service_account_id: str, body: CreateApiKeyRequest
    ) -> CreateApiKeyResponse:
        await self._authorize(context, "create")
        service_account = await self.repository.get_service_account(
            context.tenant_id, context.project_id, service_account_id
        )
        if service_account is None:
            raise AccessNotFound("service account not found")
        now = time.time()
        key_id = _new_id("key")
        token = f"sk_scenara_{key_id}_{secrets.token_urlsafe(32)}"
        scopes = body.scopes or service_account.scopes
        product_ids = body.product_ids if body.product_ids is not None else service_account.product_ids
        if not _scopes_within(scopes, service_account.scopes):
            raise PolicyDenied("API key scopes must be a subset of service account scopes")
        if not product_ids.issubset(service_account.product_ids):
            raise PolicyDenied("API key products must be a subset of service account products")
        record = ApiKeyRecord(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            key_id=key_id,
            service_account_id=service_account_id,
            name=body.name,
            token_prefix=token[:24],
            scopes=scopes,
            product_ids=product_ids,
            expires_at=body.expires_at,
            created_at=now,
        )
        created = await self.repository.create_api_key(record, token_sha256=_token_sha256(token))
        await self._record(context, "iam.api-key.create", "api_key", created.key_id)
        return CreateApiKeyResponse(record=created, api_key=token)

    async def list_api_keys(self, context: PrincipalContext) -> list[ApiKeyRecord]:
        await self._authorize(context, "read")
        return await self.repository.list_api_keys(context.tenant_id, context.project_id)

    async def revoke_api_key(self, context: PrincipalContext, key_id: str) -> ApiKeyRecord:
        await self._authorize(context, "delete")
        revoked = await self.repository.revoke_api_key(context.tenant_id, context.project_id, key_id, time.time())
        await self._record(context, "iam.api-key.revoke", "api_key", revoked.key_id)
        return revoked

    async def create_product_entitlement(
        self, context: PrincipalContext, body: CreateProductEntitlementRequest
    ) -> ProductEntitlement:
        await self._authorize(context, "create")
        now = time.time()
        project_id = _context_project_id(context, body.project_id)
        await self._require_project(context.tenant_id, project_id)
        record = ProductEntitlement(
            tenant_id=context.tenant_id,
            project_id=project_id,
            product_id=body.product_id,
            status=body.status,
            source=body.source,
            created_at=now,
            updated_at=now,
        )
        created = await self.repository.create_product_entitlement(record)
        await self._record(context, "iam.product-entitlement.create", "product_entitlement", created.product_id)
        return created

    async def list_product_entitlements(self, context: PrincipalContext) -> list[ProductEntitlement]:
        await self._authorize(context, "read")
        return await self.repository.list_product_entitlements(context.tenant_id, context.project_id)

    async def update_product_entitlement(
        self,
        context: PrincipalContext,
        product_id: str,
        body: UpdateProductEntitlementRequest,
    ) -> ProductEntitlement:
        await self._authorize(context, "update")
        current = await self.repository.get_product_entitlement(context.tenant_id, context.project_id, product_id)
        if current is None:
            raise AccessNotFound("product entitlement not found")
        updated = current.model_copy(update={"status": body.status, "source": body.source, "updated_at": time.time()})
        saved = await self.repository.save_product_entitlement(updated)
        await self._record(
            context,
            "iam.product-entitlement.update",
            "product_entitlement",
            saved.product_id,
        )
        return saved

    async def summary(self, context: PrincipalContext) -> IamSummary:
        await self._authorize(context, "read")
        organizations = await self.repository.list_organizations(context.tenant_id)
        projects = await self.repository.list_projects(context.tenant_id)
        users = await self.repository.list_users(context.tenant_id)
        roles = await self.repository.list_roles(context.tenant_id)
        memberships = await self.repository.list_memberships(context.tenant_id, context.project_id)
        service_accounts = await self.repository.list_service_accounts(context.tenant_id, context.project_id)
        api_keys = await self.repository.list_api_keys(context.tenant_id, context.project_id)
        product_entitlements = await self.repository.list_product_entitlements(context.tenant_id, context.project_id)
        return IamSummary(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            inventory=IamInventory(
                organizations=len(organizations),
                projects=len(projects),
                users=len(users),
                roles=len(roles),
                memberships=len(memberships),
                service_accounts=len(service_accounts),
                api_keys=len(api_keys),
                product_entitlements=len(product_entitlements),
            ),
            default_admin_scopes=ADMIN_SCOPES,
        )

    async def _authorize(self, context: PrincipalContext, action: str) -> None:
        await require_allowed(self._policy, context, action, "iam")

    async def _require_organization(self, tenant_id: str) -> None:
        if not await self.repository.list_organizations(tenant_id):
            raise AccessNotFound("organization not found")

    async def _require_project(self, tenant_id: str, project_id: str) -> None:
        projects = await self.repository.list_projects(tenant_id)
        if not any(item.project_id == project_id for item in projects):
            raise AccessNotFound("project not found")

    async def _record(
        self, context: PrincipalContext, action: str, resource_type: str, resource_id: str | None
    ) -> None:
        await self._audit.record(context, action=action, resource_type=resource_type, resource_id=resource_id)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:24]}"


def _token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _context_project_id(context: PrincipalContext, requested_project_id: str | None) -> str:
    if requested_project_id is not None and requested_project_id != context.project_id:
        raise PolicyDenied("resource project must match the credential project")
    return context.project_id


def _scopes_within(requested: frozenset[str], granted: frozenset[str]) -> bool:
    if "*" in granted:
        return True
    for scope in requested:
        resource, separator, _ = scope.partition(":")
        if scope not in granted and (not separator or f"{resource}:*" not in granted):
            return False
    return True


__all__ = [
    "ADMIN_PRODUCT_IDS",
    "ADMIN_SCOPES",
    "AccessNotFound",
    "AccessRepository",
    "AccessService",
    "MemoryAccessRepository",
]
