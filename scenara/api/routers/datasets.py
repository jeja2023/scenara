from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from scenara.bootstrap import Runtime
from scenara.platform.models import (
    ApiEnvelope,
    CreateDatasetRequest,
    CreateDatasetVersionRequest,
    DatasetPage,
    DatasetRecord,
    DatasetVersion,
    DatasetVersionPage,
    PrincipalContext,
    TransitionDatasetVersionRequest,
    UpdateDatasetRequest,
)

EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_datasets_router(
    runtime: Runtime,
    principal_context: PrincipalDependency,
    envelope: EnvelopeFactory,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/datasets", status_code=201, tags=["Data"])
    async def create_dataset(
        body: CreateDatasetRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[DatasetRecord]:
        result = await runtime.data.create_dataset(context, body)
        return envelope(request, result)

    @router.get("/api/v1/datasets", tags=["Data"])
    async def list_datasets(
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[DatasetPage]:
        result = await runtime.data.list_datasets(context, offset=offset, limit=limit)
        return envelope(request, result)

    @router.get("/api/v1/datasets/{dataset_id}", tags=["Data"])
    async def get_dataset(
        dataset_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[DatasetRecord]:
        result = await runtime.data.get_dataset(context, dataset_id)
        return envelope(request, result)

    @router.patch("/api/v1/datasets/{dataset_id}", tags=["Data"])
    async def update_dataset(
        dataset_id: str,
        body: UpdateDatasetRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[DatasetRecord]:
        result = await runtime.data.update_dataset(context, dataset_id, body)
        return envelope(request, result)

    @router.post(
        "/api/v1/datasets/{dataset_id}/versions", status_code=201, tags=["Data"]
    )
    async def create_dataset_version(
        dataset_id: str,
        body: CreateDatasetVersionRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[DatasetVersion]:
        result = await runtime.data.create_dataset_version(context, dataset_id, body)
        return envelope(request, result)

    @router.get("/api/v1/datasets/{dataset_id}/versions", tags=["Data"])
    async def list_dataset_versions(
        dataset_id: str,
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[DatasetVersionPage]:
        result = await runtime.data.list_dataset_versions(
            context, dataset_id, offset=offset, limit=limit
        )
        return envelope(request, result)

    @router.post("/api/v1/dataset-versions/{version_id}/transition", tags=["Data"])
    async def transition_dataset_version(
        version_id: str,
        body: TransitionDatasetVersionRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[DatasetVersion]:
        result = await runtime.data.transition_dataset_version(
            context, version_id, body
        )
        return envelope(request, result)

    return router


__all__ = ["build_datasets_router"]
