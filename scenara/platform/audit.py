from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from scenara.platform.models import PrincipalContext


class AuditUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    tenant_id: str
    project_id: str
    principal_id: str
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    request_id: str | None
    evidence: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class AuditEventView(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    event_id: str
    tenant_id: str
    project_id: str
    principal_id: str
    action: str
    resource_type: str
    resource_id: str | None = None
    outcome: str
    request_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: float


class AuditEventPage(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    items: list[AuditEventView]
    offset: int
    limit: int
    total: int


def audit_event_view(event: AuditEvent) -> AuditEventView:
    return AuditEventView(
        event_id=event.event_id,
        tenant_id=event.tenant_id,
        project_id=event.project_id,
        principal_id=event.principal_id,
        action=event.action,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        outcome=event.outcome,
        request_id=event.request_id,
        evidence=event.evidence,
        created_at=event.created_at,
    )


class AuditSink(Protocol):
    async def append_audit(self, event: AuditEvent) -> None: ...


class AuditLogger:
    def __init__(self, sink: AuditSink, *, fail_closed: bool = True) -> None:
        self._sink = sink
        self._fail_closed = fail_closed

    async def record(
        self,
        context: PrincipalContext,
        *,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        outcome: str = "success",
        request_id: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=f"aud_{uuid4().hex}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            principal_id=context.principal_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            request_id=request_id,
            evidence=evidence or {},
        )
        try:
            await self._sink.append_audit(event)
        except Exception as exc:
            if self._fail_closed:
                raise AuditUnavailable("audit event could not be persisted") from exc
        return event


__all__ = [
    "AuditEvent",
    "AuditEventPage",
    "AuditEventView",
    "AuditLogger",
    "AuditSink",
    "AuditUnavailable",
    "audit_event_view",
]
