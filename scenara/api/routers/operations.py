from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, Request
from scenara.bootstrap import Runtime
from scenara import __version__
from scenara.platform.control_plane import (
    DeploymentTopology,
    RegisterWorkerRequest,
    WorkerHeartbeatRequest,
    WorkerLease,
)
from scenara.platform.models import ApiEnvelope, PrincipalContext, SystemStatus
from scenara.platform.policy import require_allowed


EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_operations_router(
    runtime: Runtime,
    principal_context: PrincipalDependency,
    envelope: EnvelopeFactory,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/platform/workers", status_code=201, tags=["Operations"])
    async def register_worker(
        body: RegisterWorkerRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[WorkerLease]:
        return envelope(
            request, await runtime.control_plane.register_worker(context, body)
        )

    @router.post("/api/v1/platform/workers/{worker_id}/heartbeat", tags=["Operations"])
    async def heartbeat_worker(
        worker_id: str,
        body: WorkerHeartbeatRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[WorkerLease]:
        return envelope(
            request,
            await runtime.control_plane.heartbeat_worker(context, worker_id, body),
        )

    @router.get("/api/v1/platform/workers", tags=["Operations"])
    async def list_workers(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[WorkerLease]]:
        return envelope(request, await runtime.control_plane.list_workers(context))

    @router.get("/api/v1/platform/deployment/topology", tags=["Operations"])
    async def deployment_topology(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[DeploymentTopology]:
        return envelope(request, await runtime.control_plane.topology(context))

    @router.get("/api/v1/system/status", tags=["Operations"])
    async def system_status(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SystemStatus]:
        await require_allowed(runtime.policy, context, "read", "operations")
        settings = runtime.settings
        return envelope(
            request,
            SystemStatus(
                version=__version__,
                profile=settings.profile,
                state_backend=settings.state_backend,
                object_backend=settings.object_backend,
                queue_backend=settings.queue_backend,
                production_models_required=settings.production_models_required,
                auth_required=settings.auth_required,
                policy_provider=runtime.policy.provider_id,
            ),
        )

    return router


__all__ = ["build_operations_router"]
