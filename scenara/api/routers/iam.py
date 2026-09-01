from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from scenara.bootstrap import Runtime
from scenara.platform.control_plane import (
    AssignSeatRequest,
    AuditRetentionPolicy,
    BillingAccount,
    BillingUsage,
    CreateBillingAccountRequest,
    CreateIdentityProviderRequest,
    CreateProjectLifecycleRequest,
    CreateQuotaPlanRequest,
    CreateSessionRequest,
    DecideProjectLifecycleRequest,
    IdentityProvider,
    MeterEvent,
    ProjectLifecycleRequest,
    PurgeAuditRequest,
    PurgeAuditResponse,
    QuotaCheckRequest,
    QuotaCheckResponse,
    QuotaPlan,
    RecordMeterEventRequest,
    ResourceLifecycleRecord,
    SeatAssignment,
    SessionResponse,
    SetAuditRetentionPolicyRequest,
)
from scenara.platform.models import ApiEnvelope, PrincipalContext


EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_iam_router(
    runtime: Runtime,
    principal_context: PrincipalDependency,
    envelope: EnvelopeFactory,
) -> APIRouter:
    router = APIRouter()

    # 以下产品模块共享同一控制面，通过明确的权限作用域进行保护；
    # 所有变更都会像现有 Parse/Model/Data 资源一样写入审计记录。
    @router.post("/api/v1/platform/identity-providers", status_code=201, tags=["IAM"])
    async def create_identity_provider(
        body: CreateIdentityProviderRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[IdentityProvider]:
        return envelope(
            request, await runtime.control_plane.create_identity_provider(context, body)
        )

    @router.get("/api/v1/platform/identity-providers", tags=["IAM"])
    async def list_identity_providers(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[IdentityProvider]]:
        return envelope(
            request, await runtime.control_plane.list_identity_providers(context)
        )

    @router.post(
        "/api/v1/platform/identity-providers/{provider_id}/probe", tags=["IAM"]
    )
    async def probe_identity_provider(
        provider_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[IdentityProvider]:
        return envelope(
            request,
            await runtime.control_plane.probe_identity_provider(context, provider_id),
        )

    @router.post("/api/v1/platform/sessions", status_code=201, tags=["IAM"])
    async def create_interactive_session(
        body: CreateSessionRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SessionResponse]:
        if await runtime.access.is_user_disabled(context.tenant_id, body.user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="user is disabled"
            )
        return envelope(
            request, await runtime.control_plane.create_session(context, body)
        )

    @router.post(
        "/api/v1/platform/projects/lifecycle-requests", status_code=202, tags=["IAM"]
    )
    async def request_project_lifecycle(
        body: CreateProjectLifecycleRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ProjectLifecycleRequest]:
        return envelope(
            request,
            await runtime.control_plane.request_project_lifecycle(context, body),
        )

    @router.get("/api/v1/platform/projects/lifecycle-requests", tags=["IAM"])
    async def list_project_lifecycle_requests(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[ProjectLifecycleRequest]]:
        return envelope(
            request,
            await runtime.control_plane.list_project_lifecycle_requests(context),
        )

    @router.post(
        "/api/v1/platform/projects/lifecycle-requests/{request_id}/decide", tags=["IAM"]
    )
    async def decide_project_lifecycle(
        request_id: str,
        body: DecideProjectLifecycleRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ProjectLifecycleRequest]:
        return envelope(
            request,
            await runtime.control_plane.decide_project_lifecycle(
                context, request_id, body
            ),
        )

    @router.put("/api/v1/platform/audit/retention", tags=["Operations"])
    async def set_audit_retention_policy(
        body: SetAuditRetentionPolicyRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AuditRetentionPolicy]:
        return envelope(
            request,
            await runtime.control_plane.set_audit_retention_policy(context, body),
        )

    @router.get("/api/v1/platform/audit/retention", tags=["Operations"])
    async def get_audit_retention_policy(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[AuditRetentionPolicy]:
        return envelope(
            request, await runtime.control_plane.get_audit_retention_policy(context)
        )

    @router.post("/api/v1/platform/audit/purge", tags=["Operations"])
    async def purge_audit_events(
        body: PurgeAuditRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PurgeAuditResponse]:
        return envelope(
            request, await runtime.control_plane.purge_audit_events(context, body)
        )

    @router.post(
        "/api/v1/platform/lifecycle/{resource_type}/{resource_id}/{action}",
        tags=["IAM"],
    )
    async def transition_resource_lifecycle(
        resource_type: str,
        resource_id: str,
        action: str,
        request: Request,
        reason: str = Query(default="", max_length=2_000),
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ResourceLifecycleRecord]:
        return envelope(
            request,
            await runtime.control_plane.lifecycle(
                context, resource_type, resource_id, action, reason
            ),
        )

    @router.post("/api/v1/platform/quotas/plans", status_code=201, tags=["Operations"])
    async def create_quota_plan(
        body: CreateQuotaPlanRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[QuotaPlan]:
        return envelope(
            request, await runtime.control_plane.create_quota_plan(context, body)
        )

    @router.get("/api/v1/platform/quotas/plans", tags=["Operations"])
    async def list_quota_plans(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[QuotaPlan]]:
        return envelope(request, await runtime.control_plane.list_quota_plans(context))

    @router.post("/api/v1/platform/quotas/check", tags=["Operations"])
    async def check_quota(
        body: QuotaCheckRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[QuotaCheckResponse]:
        return envelope(request, await runtime.control_plane.check_quota(context, body))

    @router.post(
        "/api/v1/platform/billing/accounts",
        status_code=201,
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def create_billing_account(
        body: CreateBillingAccountRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[BillingAccount]:
        return envelope(
            request, await runtime.control_plane.create_billing_account(context, body)
        )

    @router.get(
        "/api/v1/platform/billing/accounts",
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def list_billing_accounts(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[BillingAccount]]:
        return envelope(
            request, await runtime.control_plane.list_billing_accounts(context)
        )

    @router.post(
        "/api/v1/platform/billing/meter-events",
        status_code=201,
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def record_meter_event(
        body: RecordMeterEventRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MeterEvent]:
        return envelope(
            request, await runtime.control_plane.record_meter_event(context, body)
        )

    @router.get(
        "/api/v1/platform/billing/usage",
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def list_billing_usage(
        request: Request,
        account_id: str | None = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[BillingUsage]]:
        return envelope(
            request, await runtime.control_plane.list_billing_usage(context, account_id)
        )

    @router.post(
        "/api/v1/platform/billing/seats",
        status_code=201,
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def assign_billing_seat(
        body: AssignSeatRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SeatAssignment]:
        return envelope(
            request, await runtime.control_plane.assign_billing_seat(context, body)
        )

    @router.get(
        "/api/v1/platform/billing/seats",
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def list_billing_seats(
        request: Request,
        account_id: str | None = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[SeatAssignment]]:
        return envelope(
            request, await runtime.control_plane.list_billing_seats(context, account_id)
        )

    return router


__all__ = ["build_iam_router"]
