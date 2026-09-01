from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, Request
from scenara.bootstrap import Runtime
from scenara.platform.control_plane import (
    CreateFlowRequest,
    DecideApprovalRequest,
    ExecuteFlowRequest,
    FlowApproval,
    FlowDefinition,
    FlowExecution,
)
from scenara.platform.models import ApiEnvelope, PrincipalContext


EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_flows_router(
    runtime: Runtime,
    principal_context: PrincipalDependency,
    envelope: EnvelopeFactory,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/flows", status_code=201, tags=["Flow"])
    async def create_flow(
        body: CreateFlowRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[FlowDefinition]:
        return envelope(request, await runtime.control_plane.create_flow(context, body))

    @router.get("/api/v1/flows", tags=["Flow"])
    async def list_flows(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[FlowDefinition]]:
        return envelope(request, await runtime.control_plane.list_flows(context))

    @router.post("/api/v1/flows/{flow_id}/execute", status_code=202, tags=["Flow"])
    async def execute_flow(
        flow_id: str,
        body: ExecuteFlowRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[FlowExecution]:
        return envelope(
            request, await runtime.control_plane.execute_flow(context, flow_id, body)
        )

    @router.get(
        "/api/v1/flows/{flow_id}/executions/{execution_id}/approvals", tags=["Flow"]
    )
    async def list_flow_approvals(
        flow_id: str,
        execution_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[FlowApproval]]:
        del flow_id
        return envelope(
            request,
            await runtime.control_plane.list_flow_approvals(context, execution_id),
        )

    @router.post("/api/v1/flows/approvals/{approval_id}/decide", tags=["Flow"])
    async def decide_flow_approval(
        approval_id: str,
        body: DecideApprovalRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[FlowApproval]:
        return envelope(
            request,
            await runtime.control_plane.decide_flow_approval(
                context, approval_id, body
            ),
        )

    return router


__all__ = ["build_flows_router"]
