from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, Request
from scenara.bootstrap import Runtime
from scenara.platform.control_plane import (
    AcknowledgeEdgeDeploymentRequest,
    AcknowledgeEdgeSyncRequest,
    CreateEdgeDeploymentRequest,
    EdgeDeployment,
    EdgeDevice,
    EdgeHeartbeatRequest,
    EdgeSyncItem,
    RegisterEdgeDeviceRequest,
)
from scenara.platform.models import ApiEnvelope, PrincipalContext


EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_edge_router(
    runtime: Runtime,
    principal_context: PrincipalDependency,
    envelope: EnvelopeFactory,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/edge/devices", status_code=201, tags=["Edge"])
    async def register_edge_device(
        body: RegisterEdgeDeviceRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[EdgeDevice]:
        return envelope(
            request, await runtime.control_plane.register_device(context, body)
        )

    @router.get("/api/v1/edge/devices", tags=["Edge"])
    async def list_edge_devices(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[EdgeDevice]]:
        return envelope(request, await runtime.control_plane.list_devices(context))

    @router.post("/api/v1/edge/deployments", status_code=202, tags=["Edge"])
    async def create_edge_deployment(
        body: CreateEdgeDeploymentRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[EdgeDeployment]:
        return envelope(request, await runtime.control_plane.deploy_edge(context, body))

    @router.get("/api/v1/edge/deployments", tags=["Edge"])
    async def list_edge_deployments(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[EdgeDeployment]]:
        return envelope(
            request, await runtime.control_plane.list_edge_deployments(context)
        )

    @router.post("/api/v1/edge/deployments/{deployment_id}/acknowledge", tags=["Edge"])
    async def acknowledge_edge_deployment(
        deployment_id: str,
        body: AcknowledgeEdgeDeploymentRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[EdgeDeployment]:
        return envelope(
            request,
            await runtime.control_plane.acknowledge_edge_deployment(
                context, deployment_id, body
            ),
        )

    @router.post(
        "/api/v1/edge/devices/{device_id}/sync", status_code=202, tags=["Edge"]
    )
    async def enqueue_edge_sync(
        device_id: str,
        object_ref: str,
        sha256: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[EdgeSyncItem]:
        return envelope(
            request,
            await runtime.control_plane.edge_sync(
                context, device_id, object_ref, sha256
            ),
        )

    @router.post("/api/v1/edge/devices/{device_id}/heartbeat", tags=["Edge"])
    async def edge_device_heartbeat(
        device_id: str,
        body: EdgeHeartbeatRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[EdgeDevice]:
        return envelope(
            request,
            await runtime.control_plane.edge_heartbeat(context, device_id, body),
        )

    @router.post("/api/v1/edge/sync/{item_id}/acknowledge", tags=["Edge"])
    async def acknowledge_edge_sync(
        item_id: str,
        body: AcknowledgeEdgeSyncRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[EdgeSyncItem]:
        return envelope(
            request,
            await runtime.control_plane.acknowledge_edge_sync(context, item_id, body),
        )

    return router


__all__ = ["build_edge_router"]
