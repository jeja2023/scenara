from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, Request
from scenara.bootstrap import Runtime
from scenara.platform.control_plane import (
    AgentAction,
    AgentEvaluation,
    AgentMemoryEntry,
    AgentTool,
    AgentTrace,
    ApproveAgentActionRequest,
    CreateAgentEvaluationRequest,
    CreateAgentTraceRequest,
    ProposeAgentActionRequest,
    PutAgentMemoryRequest,
    RegisterAgentToolRequest,
)
from scenara.platform.models import ApiEnvelope, PrincipalContext


EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_agents_router(
    runtime: Runtime,
    principal_context: PrincipalDependency,
    envelope: EnvelopeFactory,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/agents/tools", status_code=201, tags=["Agent"])
    async def register_agent_tool(
        body: RegisterAgentToolRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentTool]:
        return envelope(
            request, await runtime.control_plane.register_tool(context, body)
        )

    @router.get("/api/v1/agents/tools", tags=["Agent"])
    async def list_agent_tools(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[AgentTool]]:
        return envelope(request, await runtime.control_plane.list_tools(context))

    @router.post("/api/v1/agents/actions", status_code=202, tags=["Agent"])
    async def propose_agent_action(
        body: ProposeAgentActionRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentAction]:
        return envelope(
            request, await runtime.control_plane.propose_action(context, body)
        )

    @router.post("/api/v1/agents/actions/{action_id}/decide", tags=["Agent"])
    async def decide_agent_action(
        action_id: str,
        body: ApproveAgentActionRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentAction]:
        return envelope(
            request, await runtime.control_plane.decide_action(context, action_id, body)
        )

    @router.post("/api/v1/agents/actions/{action_id}/execute", tags=["Agent"])
    async def execute_agent_action(
        action_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentAction]:
        return envelope(
            request, await runtime.control_plane.execute_action(context, action_id)
        )

    @router.post("/api/v1/agents/traces", status_code=201, tags=["Agent"])
    async def record_agent_trace(
        body: CreateAgentTraceRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentTrace]:
        return envelope(
            request, await runtime.control_plane.record_agent_trace(context, body)
        )

    @router.get("/api/v1/agents/traces", tags=["Agent"])
    async def list_agent_traces(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[AgentTrace]]:
        return envelope(request, await runtime.control_plane.list_agent_traces(context))

    @router.post("/api/v1/agents/evaluations", status_code=201, tags=["Agent"])
    async def record_agent_evaluation(
        body: CreateAgentEvaluationRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentEvaluation]:
        return envelope(
            request, await runtime.control_plane.record_agent_evaluation(context, body)
        )

    @router.get("/api/v1/agents/evaluations", tags=["Agent"])
    async def list_agent_evaluations(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[AgentEvaluation]]:
        return envelope(
            request, await runtime.control_plane.list_agent_evaluations(context)
        )

    @router.put("/api/v1/agents/memory", tags=["Agent"])
    async def put_agent_memory(
        body: PutAgentMemoryRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentMemoryEntry]:
        return envelope(
            request, await runtime.control_plane.put_agent_memory(context, body)
        )

    @router.get("/api/v1/agents/memory", tags=["Agent"])
    async def get_agent_memory(
        namespace: str,
        key: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AgentMemoryEntry | None]:
        return envelope(
            request,
            await runtime.control_plane.get_agent_memory(context, namespace, key),
        )

    return router


__all__ = ["build_agents_router"]
