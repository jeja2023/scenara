from __future__ import annotations

import time
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from scenara.enterprise.license import EnterprisePolicyProvider
from scenara.platform.audit import AuditLogger
from scenara.platform.models import PrincipalContext
from scenara.platform.policy import PolicyDenied, require_allowed


class EnterpriseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


class EnterpriseStatus(EnterpriseModel):
    provider_id: str
    license_id: str
    customer: str
    tenant_ids: tuple[str, ...]
    entitlements: frozenset[str]
    limits: dict[str, int]
    usage: dict[str, int]
    support_tier: str
    sla_targets: dict[str, float]
    expires_at: int
    document_sha256: str


class Incident(EnterpriseModel):
    incident_id: str
    tenant_id: str
    project_id: str
    title: str = Field(min_length=1, max_length=300)
    severity: Literal["sev1", "sev2", "sev3", "sev4"]
    status: Literal["open", "mitigated", "resolved"] = "open"
    summary: str = Field(default="", max_length=10_000)
    started_at: float
    resolved_at: float | None = None
    created_at: float
    updated_at: float


class CreateIncidentRequest(EnterpriseModel):
    title: str = Field(min_length=1, max_length=300)
    severity: Literal["sev1", "sev2", "sev3", "sev4"]
    summary: str = Field(default="", max_length=10_000)
    started_at: float | None = None


class ResolveIncidentRequest(EnterpriseModel):
    summary: str = Field(default="", max_length=10_000)


class SupportCase(EnterpriseModel):
    case_id: str
    tenant_id: str
    project_id: str
    subject: str = Field(min_length=1, max_length=300)
    priority: Literal["low", "normal", "high", "urgent"]
    status: Literal["open", "waiting", "closed"] = "open"
    description: str = Field(min_length=1, max_length=20_000)
    created_by: str
    created_at: float
    updated_at: float


class CreateSupportCaseRequest(EnterpriseModel):
    subject: str = Field(min_length=1, max_length=300)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    description: str = Field(min_length=1, max_length=20_000)


class ComplianceEvidence(EnterpriseModel):
    evidence_id: str
    tenant_id: str
    project_id: str
    evidence_type: str = Field(min_length=1, max_length=128)
    object_ref: str = Field(min_length=1, max_length=2048)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signed_by: str = Field(min_length=1, max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float


class CreateComplianceEvidenceRequest(EnterpriseModel):
    evidence_type: str = Field(min_length=1, max_length=128)
    object_ref: str = Field(min_length=1, max_length=2048)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signed_by: str = Field(min_length=1, max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SlaSnapshot(EnterpriseModel):
    targets: dict[str, float]
    measurements: dict[str, float]
    breaches: list[str]
    measured_at: float


class EnterpriseRepository(Protocol):
    async def consume_usage(
        self,
        tenant_id: str,
        metric: str,
        amount: int,
        limit: int | None,
    ) -> int: ...

    async def usage(self, tenant_id: str) -> dict[str, int]: ...

    async def create_incident(self, incident: Incident) -> Incident: ...

    async def get_incident(
        self,
        tenant_id: str,
        project_id: str,
        incident_id: str,
    ) -> Incident | None: ...

    async def save_incident(self, incident: Incident) -> Incident: ...

    async def list_incidents(self, tenant_id: str, project_id: str) -> list[Incident]: ...

    async def create_support_case(self, case: SupportCase) -> SupportCase: ...

    async def list_support_cases(self, tenant_id: str, project_id: str) -> list[SupportCase]: ...

    async def create_evidence(self, evidence: ComplianceEvidence) -> ComplianceEvidence: ...

    async def list_evidence(self, tenant_id: str, project_id: str) -> list[ComplianceEvidence]: ...


class MemoryEnterpriseRepository:
    def __init__(self) -> None:
        self._usage: dict[tuple[str, str], int] = {}
        self._incidents: dict[tuple[str, str, str], Incident] = {}
        self._cases: dict[tuple[str, str, str], SupportCase] = {}
        self._evidence: dict[tuple[str, str, str], ComplianceEvidence] = {}

    async def consume_usage(
        self,
        tenant_id: str,
        metric: str,
        amount: int,
        limit: int | None,
    ) -> int:
        key = (tenant_id, metric)
        next_value = self._usage.get(key, 0) + amount
        if limit is not None and next_value > limit:
            raise PolicyDenied(f"enterprise quota exceeded: {metric}")
        self._usage[key] = next_value
        return next_value

    async def usage(self, tenant_id: str) -> dict[str, int]:
        return {metric: value for (row_tenant, metric), value in self._usage.items() if row_tenant == tenant_id}

    async def create_incident(self, incident: Incident) -> Incident:
        key = (incident.tenant_id, incident.project_id, incident.incident_id)
        if key in self._incidents:
            raise ValueError("incident already exists")
        self._incidents[key] = incident.model_copy(deep=True)
        return incident.model_copy(deep=True)

    async def get_incident(
        self,
        tenant_id: str,
        project_id: str,
        incident_id: str,
    ) -> Incident | None:
        value = self._incidents.get((tenant_id, project_id, incident_id))
        return value.model_copy(deep=True) if value else None

    async def save_incident(self, incident: Incident) -> Incident:
        key = (incident.tenant_id, incident.project_id, incident.incident_id)
        if key not in self._incidents:
            raise ValueError("incident does not exist")
        self._incidents[key] = incident.model_copy(deep=True)
        return incident.model_copy(deep=True)

    async def list_incidents(self, tenant_id: str, project_id: str) -> list[Incident]:
        return sorted(
            [
                value.model_copy(deep=True)
                for (row_tenant, row_project, _), value in self._incidents.items()
                if (row_tenant, row_project) == (tenant_id, project_id)
            ],
            key=lambda value: (value.created_at, value.incident_id),
            reverse=True,
        )

    async def create_support_case(self, case: SupportCase) -> SupportCase:
        key = (case.tenant_id, case.project_id, case.case_id)
        if key in self._cases:
            raise ValueError("support case already exists")
        self._cases[key] = case.model_copy(deep=True)
        return case.model_copy(deep=True)

    async def list_support_cases(self, tenant_id: str, project_id: str) -> list[SupportCase]:
        return sorted(
            [
                value.model_copy(deep=True)
                for (row_tenant, row_project, _), value in self._cases.items()
                if (row_tenant, row_project) == (tenant_id, project_id)
            ],
            key=lambda value: (value.created_at, value.case_id),
            reverse=True,
        )

    async def create_evidence(self, evidence: ComplianceEvidence) -> ComplianceEvidence:
        key = (evidence.tenant_id, evidence.project_id, evidence.evidence_id)
        if key in self._evidence:
            raise ValueError("compliance evidence already exists")
        self._evidence[key] = evidence.model_copy(deep=True)
        return evidence.model_copy(deep=True)

    async def list_evidence(self, tenant_id: str, project_id: str) -> list[ComplianceEvidence]:
        return sorted(
            [
                value.model_copy(deep=True)
                for (row_tenant, row_project, _), value in self._evidence.items()
                if (row_tenant, row_project) == (tenant_id, project_id)
            ],
            key=lambda value: (value.created_at, value.evidence_id),
            reverse=True,
        )


class EnterpriseService:
    def __init__(
        self,
        provider: EnterprisePolicyProvider,
        repository: EnterpriseRepository,
        audit: AuditLogger,
    ) -> None:
        self.provider = provider
        self.repository = repository
        self.audit = audit

    async def status(self, context: PrincipalContext) -> EnterpriseStatus:
        claims = self.provider.claims(context)
        return EnterpriseStatus(
            provider_id=self.provider.provider_id,
            license_id=claims.license_id,
            customer=claims.customer,
            tenant_ids=claims.tenant_ids,
            entitlements=claims.entitlements,
            limits=claims.limits,
            usage=await self.repository.usage(context.tenant_id),
            support_tier=claims.support_tier,
            sla_targets=claims.sla_targets,
            expires_at=claims.expires_at,
            document_sha256=self.provider.license.document_sha256,
        )

    async def sla(
        self,
        context: PrincipalContext,
        measurements: dict[str, float],
    ) -> SlaSnapshot:
        await require_allowed(self.provider, context, "read", "enterprise_sla")
        targets = self.provider.license.claims.sla_targets
        breaches = [
            metric for metric, target in targets.items() if metric in measurements and measurements[metric] < target
        ]
        return SlaSnapshot(
            targets=targets,
            measurements=measurements,
            breaches=sorted(breaches),
            measured_at=time.time(),
        )

    async def list_incidents(self, context: PrincipalContext) -> list[Incident]:
        await require_allowed(self.provider, context, "read", "enterprise_incident")
        return await self.repository.list_incidents(context.tenant_id, context.project_id)

    async def list_support_cases(self, context: PrincipalContext) -> list[SupportCase]:
        await require_allowed(self.provider, context, "read", "enterprise_support")
        return await self.repository.list_support_cases(context.tenant_id, context.project_id)

    async def list_evidence(self, context: PrincipalContext) -> list[ComplianceEvidence]:
        await require_allowed(self.provider, context, "read", "enterprise_compliance")
        return await self.repository.list_evidence(context.tenant_id, context.project_id)

    async def create_incident(
        self,
        context: PrincipalContext,
        request: CreateIncidentRequest,
    ) -> Incident:
        await require_allowed(self.provider, context, "create", "enterprise_incident")
        now = time.time()
        incident = Incident(
            incident_id=f"inc_{uuid4().hex}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            title=request.title,
            severity=request.severity,
            summary=request.summary,
            started_at=request.started_at or now,
            created_at=now,
            updated_at=now,
        )
        stored = await self.repository.create_incident(incident)
        await self.audit.record(
            context,
            action="enterprise.incident.create",
            resource_type="enterprise_incident",
            resource_id=incident.incident_id,
            evidence={"severity": incident.severity},
        )
        return stored

    async def resolve_incident(
        self,
        context: PrincipalContext,
        incident_id: str,
        request: ResolveIncidentRequest,
    ) -> Incident:
        await require_allowed(self.provider, context, "resolve", "enterprise_incident")
        incident = await self.repository.get_incident(
            context.tenant_id,
            context.project_id,
            incident_id,
        )
        if incident is None:
            raise ValueError("incident not found")
        now = time.time()
        updated = incident.model_copy(
            update={
                "status": "resolved",
                "summary": request.summary or incident.summary,
                "resolved_at": now,
                "updated_at": now,
            },
            deep=True,
        )
        stored = await self.repository.save_incident(updated)
        await self.audit.record(
            context,
            action="enterprise.incident.resolve",
            resource_type="enterprise_incident",
            resource_id=incident_id,
        )
        return stored

    async def create_support_case(
        self,
        context: PrincipalContext,
        request: CreateSupportCaseRequest,
    ) -> SupportCase:
        await require_allowed(self.provider, context, "create", "enterprise_support")
        now = time.time()
        case = SupportCase(
            case_id=f"case_{uuid4().hex}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            subject=request.subject,
            priority=request.priority,
            description=request.description,
            created_by=context.principal_id,
            created_at=now,
            updated_at=now,
        )
        stored = await self.repository.create_support_case(case)
        await self.audit.record(
            context,
            action="enterprise.support.create",
            resource_type="enterprise_support_case",
            resource_id=case.case_id,
            evidence={"priority": case.priority},
        )
        return stored

    async def create_evidence(
        self,
        context: PrincipalContext,
        request: CreateComplianceEvidenceRequest,
    ) -> ComplianceEvidence:
        await require_allowed(self.provider, context, "create", "enterprise_compliance")
        evidence = ComplianceEvidence(
            evidence_id=f"evd_{uuid4().hex}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            **request.model_dump(),
            created_at=time.time(),
        )
        stored = await self.repository.create_evidence(evidence)
        await self.audit.record(
            context,
            action="enterprise.compliance_evidence.create",
            resource_type="enterprise_compliance_evidence",
            resource_id=evidence.evidence_id,
            evidence={"sha256": evidence.sha256, "evidence_type": evidence.evidence_type},
        )
        return stored


__all__ = [
    "ComplianceEvidence",
    "CreateComplianceEvidenceRequest",
    "CreateIncidentRequest",
    "CreateSupportCaseRequest",
    "EnterpriseRepository",
    "EnterpriseService",
    "EnterpriseStatus",
    "Incident",
    "MemoryEnterpriseRepository",
    "ResolveIncidentRequest",
    "SlaSnapshot",
    "SupportCase",
]
