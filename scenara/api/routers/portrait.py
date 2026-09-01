from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from scenara.bootstrap import Runtime
from scenara.domains.portrait.service import (
    CreateIdentityRequest,
    EnrollIdentityRequest,
    PortraitAssetCompareRequest,
    PortraitCompareRequest,
    PortraitCompareResponse,
    PortraitEnrollment,
    PortraitIdentity,
    PortraitIdentityPage,
    PortraitNotFound,
    PortraitSearchRequest,
    PortraitSearchResponse,
)
from scenara.domains.portrait.trajectory import (
    CameraRecord,
    CameraTransition,
    IdentityPage,
    LongTermIdentity,
    MergeIdentitiesRequest,
    RegisterCameraRequest,
    SegmentPage,
    SetCameraTransitionsRequest,
    SplitIdentityRequest,
    TimelineEntry,
    TrajectoryStatus,
    UpdateCameraRequest,
    UpdateIdentityRequest,
)
from scenara.platform.models import ApiEnvelope, MediaKind, PrincipalContext
from scenara.platform.policy import require_allowed
from typing import Annotated


EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_portrait_router(
    runtime: Runtime, principal_context: PrincipalDependency, envelope: EnvelopeFactory
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/portrait/identities", status_code=201, tags=["Portrait"])
    async def create_portrait_identity(
        body: CreateIdentityRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitIdentity]:
        identity = await runtime.portrait.create_identity(context, body)
        return envelope(request, identity)

    @router.get("/api/v1/portrait/identities", tags=["Portrait"])
    async def list_portrait_identities(
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitIdentityPage]:
        page = await runtime.portrait.list_identities(
            context, offset=offset, limit=limit
        )
        return envelope(request, page)

    @router.get("/api/v1/portrait/identities/{identity_id}", tags=["Portrait"])
    async def get_portrait_identity(
        identity_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitIdentity]:
        identity = await runtime.portrait.get_identity(context, identity_id)
        return envelope(request, identity)

    @router.delete(
        "/api/v1/portrait/identities/{identity_id}", status_code=204, tags=["Portrait"]
    )
    async def delete_portrait_identity(
        identity_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.portrait.delete_identity(context, identity_id)
        return Response(status_code=204)

    @router.get(
        "/api/v1/portrait/trajectories/identities", tags=["Portrait Intelligence"]
    )
    async def list_long_term_portrait_identities(
        request: Request,
        status: Annotated[TrajectoryStatus | None, Query()] = None,
        camera_id: Annotated[str | None, Query(max_length=128)] = None,
        since: Annotated[float | None, Query(ge=0)] = None,
        until: Annotated[float | None, Query(ge=0)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[IdentityPage]:
        page = await runtime.trajectory.list_identities(
            context,
            status=status,
            camera_id=camera_id,
            since=since,
            until=until,
            offset=offset,
            limit=limit,
        )
        return envelope(request, page)

    @router.get(
        "/api/v1/portrait/trajectories/identities/{identity_id}",
        tags=["Portrait Intelligence"],
    )
    async def get_long_term_portrait_identity(
        identity_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[LongTermIdentity]:
        return envelope(
            request, await runtime.trajectory.get_identity(context, identity_id)
        )

    @router.patch(
        "/api/v1/portrait/trajectories/identities/{identity_id}",
        tags=["Portrait Intelligence"],
    )
    async def update_long_term_portrait_identity(
        identity_id: str,
        body: UpdateIdentityRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[LongTermIdentity]:
        identity = await runtime.trajectory.update_identity(context, identity_id, body)
        return envelope(request, identity)

    @router.delete(
        "/api/v1/portrait/trajectories/identities/{identity_id}",
        status_code=204,
        tags=["Portrait Intelligence"],
    )
    async def delete_long_term_portrait_identity(
        identity_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.trajectory.delete_identity(context, identity_id)
        return Response(status_code=204)

    @router.get(
        "/api/v1/portrait/trajectories/identities/{identity_id}/segments",
        tags=["Portrait Intelligence"],
    )
    async def list_long_term_portrait_segments(
        identity_id: str,
        request: Request,
        camera_id: Annotated[str | None, Query(max_length=128)] = None,
        since: Annotated[float | None, Query(ge=0)] = None,
        until: Annotated[float | None, Query(ge=0)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SegmentPage]:
        page = await runtime.trajectory.list_segments(
            context,
            identity_id,
            camera_id=camera_id,
            since=since,
            until=until,
            offset=offset,
            limit=limit,
        )
        return envelope(request, page)

    @router.get(
        "/api/v1/portrait/trajectories/identities/{identity_id}/timeline",
        tags=["Portrait Intelligence"],
    )
    async def get_long_term_portrait_timeline(
        identity_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[TimelineEntry]]:
        return envelope(
            request, await runtime.trajectory.timeline(context, identity_id)
        )

    @router.post(
        "/api/v1/portrait/trajectories/identities/merge", tags=["Portrait Intelligence"]
    )
    async def merge_long_term_portrait_identities(
        body: MergeIdentitiesRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[LongTermIdentity]:
        return envelope(
            request, await runtime.trajectory.merge_identities(context, body)
        )

    @router.post(
        "/api/v1/portrait/trajectories/identities/{identity_id}/split",
        status_code=201,
        tags=["Portrait Intelligence"],
    )
    async def split_long_term_portrait_identity(
        identity_id: str,
        body: SplitIdentityRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[LongTermIdentity]:
        identity = await runtime.trajectory.split_identity(context, identity_id, body)
        return envelope(request, identity)

    @router.post(
        "/api/v1/portrait/cameras", status_code=201, tags=["Portrait Intelligence"]
    )
    async def register_portrait_camera(
        body: RegisterCameraRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[CameraRecord]:
        return envelope(
            request, await runtime.trajectory.register_camera(context, body)
        )

    @router.get("/api/v1/portrait/cameras", tags=["Portrait Intelligence"])
    async def list_portrait_cameras(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[CameraRecord]]:
        return envelope(request, await runtime.trajectory.list_cameras(context))

    @router.patch(
        "/api/v1/portrait/cameras/{camera_id}", tags=["Portrait Intelligence"]
    )
    async def update_portrait_camera(
        camera_id: str,
        body: UpdateCameraRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[CameraRecord]:
        return envelope(
            request, await runtime.trajectory.update_camera(context, camera_id, body)
        )

    @router.delete(
        "/api/v1/portrait/cameras/{camera_id}",
        status_code=204,
        tags=["Portrait Intelligence"],
    )
    async def delete_portrait_camera(
        camera_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.trajectory.delete_camera(context, camera_id)
        return Response(status_code=204)

    @router.get(
        "/api/v1/portrait/cameras/{camera_id}/transitions",
        tags=["Portrait Intelligence"],
    )
    async def list_portrait_camera_transitions(
        camera_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[CameraTransition]]:
        transitions = await runtime.trajectory.list_camera_transitions(
            context, camera_id
        )
        return envelope(request, transitions)

    @router.put(
        "/api/v1/portrait/cameras/{camera_id}/transitions",
        tags=["Portrait Intelligence"],
    )
    async def set_portrait_camera_transitions(
        camera_id: str,
        body: SetCameraTransitionsRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[CameraTransition]]:
        transitions = await runtime.trajectory.set_camera_transitions(
            context, camera_id, body
        )
        return envelope(request, transitions)

    @router.post(
        "/api/v1/portrait/identities/{identity_id}/enrollments",
        status_code=201,
        tags=["Portrait"],
    )
    async def enroll_portrait_identity(
        identity_id: str,
        body: EnrollIdentityRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitEnrollment]:
        enrollment = await runtime.portrait.enroll(context, identity_id, body)
        return envelope(request, enrollment)

    @router.post(
        "/api/v1/portrait/identities/{identity_id}/enrollments/image",
        status_code=201,
        tags=["Portrait"],
    )
    async def enroll_portrait_identity_image(
        identity_id: str,
        file: Annotated[UploadFile, File()],
        request: Request,
        feature_space_id: Annotated[str | None, Form()] = None,
        quality: Annotated[float | None, Form(ge=0, le=1)] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitEnrollment]:
        data = await file.read(runtime.settings.max_image_bytes + 1)
        if len(data) > runtime.settings.max_image_bytes:
            raise ValueError(f"image exceeds {runtime.settings.max_image_bytes} bytes")
        enrollment = await runtime.portrait.enroll_image(
            context,
            identity_id,
            data,
            feature_space_id=feature_space_id,
            quality_override=quality,
        )
        return envelope(request, enrollment)

    @router.post("/api/v1/portrait/search", tags=["Portrait"])
    async def search_portrait_identities(
        body: PortraitSearchRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitSearchResponse]:
        result = await runtime.portrait.search(context, body)
        return envelope(request, result)

    @router.post("/api/v1/portrait/search/image", tags=["Portrait"])
    async def search_portrait_identities_image(
        file: Annotated[UploadFile, File()],
        request: Request,
        feature_space_id: Annotated[str | None, Form()] = None,
        limit: Annotated[int, Form(ge=1, le=200)] = 20,
        threshold: Annotated[float | None, Form(ge=-1, le=1)] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitSearchResponse]:
        data = await file.read(runtime.settings.max_image_bytes + 1)
        if len(data) > runtime.settings.max_image_bytes:
            raise ValueError(f"image exceeds {runtime.settings.max_image_bytes} bytes")
        result = await runtime.portrait.search_image(
            context,
            data,
            feature_space_id=feature_space_id,
            limit=limit,
            threshold=threshold,
        )
        return envelope(request, result)

    @router.post("/api/v1/portrait/compare", tags=["Portrait"])
    async def compare_portrait_features(
        body: PortraitCompareRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitCompareResponse]:
        result = await runtime.portrait.compare(context, body)
        return envelope(request, result)

    @router.post("/api/v1/portrait/compare/images", tags=["Portrait"])
    async def compare_portrait_images(
        left: Annotated[UploadFile, File()],
        right: Annotated[UploadFile, File()],
        request: Request,
        feature_space_id: Annotated[str | None, Form()] = None,
        threshold: Annotated[float | None, Form(ge=-1, le=1)] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitCompareResponse]:
        left_data = await left.read(runtime.settings.max_image_bytes + 1)
        right_data = await right.read(runtime.settings.max_image_bytes + 1)
        if (
            len(left_data) > runtime.settings.max_image_bytes
            or len(right_data) > runtime.settings.max_image_bytes
        ):
            raise ValueError(f"image exceeds {runtime.settings.max_image_bytes} bytes")
        result = await runtime.portrait.compare_images(
            context,
            left_data,
            right_data,
            feature_space_id=feature_space_id,
            threshold=threshold,
        )
        return envelope(request, result)

    @router.post("/api/v1/portrait/compare/assets", tags=["Portrait"])
    async def compare_portrait_assets(
        body: PortraitAssetCompareRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitCompareResponse]:
        await require_allowed(
            runtime.policy,
            context,
            "read",
            "media_asset",
            {"asset_id": body.left_asset_id},
        )
        await require_allowed(
            runtime.policy,
            context,
            "read",
            "media_asset",
            {"asset_id": body.right_asset_id},
        )
        left_asset = await runtime.state.get_asset(
            context.tenant_id, context.project_id, body.left_asset_id
        )
        right_asset = await runtime.state.get_asset(
            context.tenant_id, context.project_id, body.right_asset_id
        )
        if (
            left_asset is None
            or right_asset is None
            or left_asset.deleted_at is not None
            or right_asset.deleted_at is not None
            or left_asset.original_deleted_at is not None
            or right_asset.original_deleted_at is not None
        ):
            raise PortraitNotFound("portrait comparison asset not found")
        if left_asset.kind.value != "image" or right_asset.kind.value != "image":
            raise ValueError("portrait comparison assets must be images")
        result = await runtime.portrait.compare_images(
            context,
            await runtime.objects.get(left_asset.object_key),
            await runtime.objects.get(right_asset.object_key),
            feature_space_id=body.feature_space_id,
            threshold=body.threshold,
            mode="asset",
        )
        return envelope(request, result)

    @router.post("/api/v1/portrait/compare/asset-image", tags=["Portrait"])
    async def compare_portrait_asset_image(
        asset_id: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
        request: Request,
        feature_space_id: Annotated[str | None, Form()] = None,
        threshold: Annotated[float | None, Form(ge=-1, le=1)] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitCompareResponse]:
        await require_allowed(
            runtime.policy, context, "read", "media_asset", {"asset_id": asset_id}
        )
        asset = await runtime.state.get_asset(
            context.tenant_id, context.project_id, asset_id
        )
        if (
            asset is None
            or asset.deleted_at is not None
            or asset.original_deleted_at is not None
        ):
            raise PortraitNotFound("portrait comparison asset not found")
        if asset.kind != MediaKind.IMAGE:
            raise ValueError("portrait comparison assets must be images")
        right_data = await file.read(runtime.settings.max_image_bytes + 1)
        if len(right_data) > runtime.settings.max_image_bytes:
            raise ValueError(f"image exceeds {runtime.settings.max_image_bytes} bytes")
        result = await runtime.portrait.compare_images(
            context,
            await runtime.objects.get(asset.object_key),
            right_data,
            feature_space_id=feature_space_id,
            threshold=threshold,
            mode="mixed",
        )
        return envelope(request, result)

    @router.post("/api/v1/portrait/compare/image-asset", tags=["Portrait"])
    async def compare_portrait_image_asset(
        file: Annotated[UploadFile, File()],
        asset_id: Annotated[str, Form()],
        request: Request,
        feature_space_id: Annotated[str | None, Form()] = None,
        threshold: Annotated[float | None, Form(ge=-1, le=1)] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitCompareResponse]:
        await require_allowed(
            runtime.policy, context, "read", "media_asset", {"asset_id": asset_id}
        )
        asset = await runtime.state.get_asset(
            context.tenant_id, context.project_id, asset_id
        )
        if (
            asset is None
            or asset.deleted_at is not None
            or asset.original_deleted_at is not None
        ):
            raise PortraitNotFound("portrait comparison asset not found")
        if asset.kind != MediaKind.IMAGE:
            raise ValueError("portrait comparison assets must be images")
        left_data = await file.read(runtime.settings.max_image_bytes + 1)
        if len(left_data) > runtime.settings.max_image_bytes:
            raise ValueError(f"image exceeds {runtime.settings.max_image_bytes} bytes")
        result = await runtime.portrait.compare_images(
            context,
            left_data,
            await runtime.objects.get(asset.object_key),
            feature_space_id=feature_space_id,
            threshold=threshold,
            mode="mixed",
        )
        return envelope(request, result)

    return router


__all__ = ["build_portrait_router"]
