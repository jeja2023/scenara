from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from scenara.bootstrap import Runtime
from scenara.platform.models import (
    ApiEnvelope,
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
    IamSummary,
    LoginRequest,
    Membership,
    Organization,
    PrincipalContext,
    ProductEntitlement,
    Project,
    Role,
    ServiceAccount,
    UpdateProductEntitlementRequest,
    UserAccount,
)
from scenara.platform.control_plane import SessionResponse

EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_access_router(
    runtime: Runtime,
    principal_context: PrincipalDependency,
    envelope: EnvelopeFactory,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/platform/iam/summary", tags=["IAM"])
    async def iam_summary(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[IamSummary]:
        return envelope(request, await runtime.access.summary(context))

    @router.post("/api/v1/auth/login", tags=["IAM"])
    async def login(
        body: LoginRequest, request: Request
    ) -> ApiEnvelope[SessionResponse]:
        context = await runtime.access.authenticate_user(
            body.username,
            body.password,
            runtime.settings.default_tenant_id,
            runtime.settings.default_project_id,
        )
        if context is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid username or password",
            )
        return envelope(
            request,
            await runtime.control_plane.create_authenticated_session(
                context, ttl_seconds=body.ttl_seconds
            ),
        )

    @router.post("/api/v1/platform/organizations", status_code=201, tags=["IAM"])
    async def create_organization(
        body: CreateOrganizationRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Organization]:
        return envelope(
            request, await runtime.access.create_organization(context, body)
        )

    @router.get("/api/v1/platform/organizations", tags=["IAM"])
    async def list_organizations(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[Organization]]:
        return envelope(request, await runtime.access.list_organizations(context))

    @router.post("/api/v1/platform/projects", status_code=201, tags=["IAM"])
    async def create_project(
        body: CreateProjectRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Project]:
        return envelope(request, await runtime.access.create_project(context, body))

    @router.get("/api/v1/platform/projects", tags=["IAM"])
    async def list_projects(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[Project]]:
        return envelope(request, await runtime.access.list_projects(context))

    @router.post("/api/v1/platform/users", status_code=201, tags=["IAM"])
    async def create_user(
        body: CreateUserRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[UserAccount]:
        return envelope(request, await runtime.access.create_user(context, body))

    @router.get("/api/v1/platform/users", tags=["IAM"])
    async def list_users(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[UserAccount]]:
        return envelope(request, await runtime.access.list_users(context))

    @router.post("/api/v1/platform/users/{user_id}/disable", tags=["IAM"])
    async def disable_user(
        user_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[UserAccount]:
        return envelope(
            request, await runtime.access.set_user_disabled(context, user_id, True)
        )

    @router.post("/api/v1/platform/users/{user_id}/restore", tags=["IAM"])
    async def restore_user(
        user_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[UserAccount]:
        return envelope(
            request, await runtime.access.set_user_disabled(context, user_id, False)
        )

    @router.post("/api/v1/platform/roles", status_code=201, tags=["IAM"])
    async def create_role(
        body: CreateRoleRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Role]:
        return envelope(request, await runtime.access.create_role(context, body))

    @router.get("/api/v1/platform/roles", tags=["IAM"])
    async def list_roles(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[Role]]:
        return envelope(request, await runtime.access.list_roles(context))

    @router.post("/api/v1/platform/memberships", status_code=201, tags=["IAM"])
    async def create_membership(
        body: CreateMembershipRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Membership]:
        return envelope(request, await runtime.access.create_membership(context, body))

    @router.get("/api/v1/platform/memberships", tags=["IAM"])
    async def list_memberships(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[Membership]]:
        return envelope(request, await runtime.access.list_memberships(context))

    @router.post("/api/v1/platform/service-accounts", status_code=201, tags=["IAM"])
    async def create_service_account(
        body: CreateServiceAccountRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ServiceAccount]:
        return envelope(
            request, await runtime.access.create_service_account(context, body)
        )

    @router.get("/api/v1/platform/service-accounts", tags=["IAM"])
    async def list_service_accounts(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[ServiceAccount]]:
        return envelope(request, await runtime.access.list_service_accounts(context))

    @router.post(
        "/api/v1/platform/service-accounts/{service_account_id}/disable", tags=["IAM"]
    )
    async def disable_service_account(
        service_account_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ServiceAccount]:
        return envelope(
            request,
            await runtime.access.set_service_account_disabled(
                context, service_account_id, True
            ),
        )

    @router.post(
        "/api/v1/platform/service-accounts/{service_account_id}/restore", tags=["IAM"]
    )
    async def restore_service_account(
        service_account_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ServiceAccount]:
        return envelope(
            request,
            await runtime.access.set_service_account_disabled(
                context, service_account_id, False
            ),
        )

    @router.post(
        "/api/v1/platform/service-accounts/{service_account_id}/api-keys",
        status_code=201,
        tags=["IAM"],
    )
    async def create_api_key(
        service_account_id: str,
        body: CreateApiKeyRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[CreateApiKeyResponse]:
        return envelope(
            request,
            await runtime.access.create_api_key(context, service_account_id, body),
        )

    @router.get("/api/v1/platform/api-keys", tags=["IAM"])
    async def list_api_keys(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[ApiKeyRecord]]:
        return envelope(request, await runtime.access.list_api_keys(context))

    @router.post("/api/v1/platform/api-keys/{key_id}/revoke", tags=["IAM"])
    async def revoke_api_key(
        key_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ApiKeyRecord]:
        return envelope(request, await runtime.access.revoke_api_key(context, key_id))

    @router.post("/api/v1/platform/product-entitlements", status_code=201, tags=["IAM"])
    async def create_product_entitlement(
        body: CreateProductEntitlementRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ProductEntitlement]:
        return envelope(
            request,
            await runtime.access.create_product_entitlement(context, body),
        )

    @router.get("/api/v1/platform/product-entitlements", tags=["IAM"])
    async def list_product_entitlements(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[ProductEntitlement]]:
        return envelope(
            request, await runtime.access.list_product_entitlements(context)
        )

    @router.put("/api/v1/platform/product-entitlements/{product_id}", tags=["IAM"])
    async def update_product_entitlement(
        product_id: str,
        body: UpdateProductEntitlementRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ProductEntitlement]:
        return envelope(
            request,
            await runtime.access.update_product_entitlement(context, product_id, body),
        )

    return router


__all__ = ["build_access_router"]
