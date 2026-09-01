from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from scenara.bootstrap import Runtime
from scenara.enterprise.service import (
    ComplianceEvidence,
    CreateComplianceEvidenceRequest,
    CreateIncidentRequest,
    CreateSupportCaseRequest,
    EnterpriseService,
    EnterpriseStatus,
    Incident,
    ResolveIncidentRequest,
    SlaSnapshot,
    SupportCase,
)
from scenara.platform.models import ApiEnvelope, PrincipalContext


EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_enterprise_router(
    runtime: Runtime,
    principal_context: PrincipalDependency,
    envelope: EnvelopeFactory,
) -> APIRouter:
    router = APIRouter()

    def enterprise_service() -> EnterpriseService:
        service = runtime.enterprise
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="enterprise service is disabled",
            )
        return service

    @router.get(
        "/api/v1/enterprise/status",
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def enterprise_status(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[EnterpriseStatus]:
        result = await enterprise_service().status(context)
        return envelope(request, result)

    @router.post(
        "/api/v1/enterprise/sla/evaluate",
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def enterprise_sla(
        body: dict[str, float],
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SlaSnapshot]:
        result = await enterprise_service().sla(context, body)
        return envelope(request, result)

    @router.get(
        "/api/v1/enterprise/incidents",
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def list_enterprise_incidents(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[Incident]]:
        rows = await enterprise_service().list_incidents(context)
        return envelope(request, rows)

    @router.post(
        "/api/v1/enterprise/incidents",
        status_code=201,
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def create_enterprise_incident(
        body: CreateIncidentRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Incident]:
        result = await enterprise_service().create_incident(context, body)
        return envelope(request, result)

    @router.post(
        "/api/v1/enterprise/incidents/{incident_id}/resolve",
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def resolve_enterprise_incident(
        incident_id: str,
        body: ResolveIncidentRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Incident]:
        result = await enterprise_service().resolve_incident(context, incident_id, body)
        return envelope(request, result)

    @router.get(
        "/api/v1/enterprise/support/cases",
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def list_enterprise_support_cases(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[SupportCase]]:
        rows = await enterprise_service().list_support_cases(context)
        return envelope(request, rows)

    @router.post(
        "/api/v1/enterprise/support/cases",
        status_code=201,
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def create_enterprise_support_case(
        body: CreateSupportCaseRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SupportCase]:
        result = await enterprise_service().create_support_case(context, body)
        return envelope(request, result)

    @router.get(
        "/api/v1/enterprise/compliance/evidence",
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def list_enterprise_evidence(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[ComplianceEvidence]]:
        rows = await enterprise_service().list_evidence(context)
        return envelope(request, rows)

    @router.post(
        "/api/v1/enterprise/compliance/evidence",
        status_code=201,
        tags=["Legacy"],
        deprecated=True,
        include_in_schema=False,
    )
    async def create_enterprise_evidence(
        body: CreateComplianceEvidenceRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ComplianceEvidence]:
        result = await enterprise_service().create_evidence(context, body)
        return envelope(request, result)

    return router


__all__ = ["build_enterprise_router"]
