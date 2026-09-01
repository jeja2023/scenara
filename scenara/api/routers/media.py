from __future__ import annotations

import asyncio
import hmac
import json
import tempfile
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)

from scenara.bootstrap import Runtime
from scenara.platform.models import (
    ApiEnvelope,
    CompleteMediaUploadRequest,
    CreateMediaSourceRequest,
    MediaAsset,
    MediaAssetPage,
    MediaKind,
    MediaSource,
    MediaSourcePage,
    MediaSourceProbe,
    MediaSourceView,
    PresignedMediaDownload,
    PresignedMediaUpload,
    PresignMediaUploadRequest,
    PrincipalContext,
)
from scenara.platform.policy import require_allowed
from scenara.platform.services import ResourceNotFound

PRESIGN_UPLOAD_EXPIRY_GRACE_SECONDS = 60
EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def _media_source_view(source: MediaSource) -> MediaSourceView:
    return MediaSourceView(
        source_id=source.source_id,
        kind=source.kind,
        name=source.name,
        masked_url=source.masked_url,
        metadata=source.metadata,
        created_at=source.created_at,
    )


def build_media_router(
    runtime: Runtime,
    principal_context: PrincipalDependency,
    envelope: EnvelopeFactory,
) -> APIRouter:
    router = APIRouter()

    async def spool_upload(file: UploadFile, max_bytes: int) -> Path:
        handle = tempfile.NamedTemporaryFile(prefix="scenara-upload-", delete=False)
        path = Path(handle.name)
        size = 0
        failed = False
        try:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError(f"media exceeds {max_bytes} bytes")
                await asyncio.to_thread(handle.write, chunk)
            await asyncio.to_thread(handle.flush)
            return path
        except Exception:
            failed = True
            raise
        finally:
            with suppress(Exception):
                handle.close()
            if failed:
                with suppress(FileNotFoundError, PermissionError):
                    path.unlink()

    def require_presigned_storage() -> None:
        if not runtime.settings.s3_presigned_urls_enabled:
            raise HTTPException(
                status_code=404, detail="presigned object URLs are not enabled"
            )
        if runtime.settings.object_backend != "s3":
            raise HTTPException(
                status_code=409, detail="presigned object URLs require an S3 provider"
            )

    def validate_direct_upload_size(body: PresignMediaUploadRequest) -> None:
        maximum = (
            runtime.settings.max_image_bytes
            if body.kind == MediaKind.IMAGE
            else runtime.settings.max_media_bytes
        )
        if body.size_bytes > maximum:
            raise ValueError(f"media exceeds {maximum} bytes")

    def upload_token(
        context: PrincipalContext,
        upload_id: str,
        body: PresignMediaUploadRequest,
        expires_at: int,
    ) -> str:
        secret = runtime.settings.api_token or runtime.settings.secret_encryption_key
        if not secret:
            raise HTTPException(
                status_code=503, detail="presigned upload signing key is not configured"
            )
        payload = json.dumps(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "upload_id": upload_id,
                "filename": body.filename,
                "content_type": body.content_type,
                "kind": body.kind.value,
                "size_bytes": body.size_bytes,
                "sha256": body.sha256,
                "expires_at": expires_at,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hmac.new(
            secret.encode("utf-8"), payload.encode("utf-8"), "sha256"
        ).hexdigest()

    @router.post("/api/v1/media/assets", status_code=201, tags=["Media"])
    async def create_media_asset(
        request: Request,
        file: Annotated[UploadFile, File()],
        kind: Annotated[MediaKind, Form()] = MediaKind.IMAGE,
        domain: Annotated[str | None, Form()] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaAsset]:
        max_read = (
            runtime.settings.max_image_bytes + 1
            if kind == MediaKind.IMAGE
            else runtime.settings.max_media_bytes + 1
        )
        if kind == MediaKind.VIDEO:
            path = await spool_upload(file, runtime.settings.max_media_bytes)
            try:
                asset = await runtime.runs.create_asset_from_path(
                    context,
                    path=str(path),
                    filename=file.filename,
                    content_type=file.content_type or "application/octet-stream",
                    kind=kind,
                    domain=domain,
                )
            finally:
                with suppress(FileNotFoundError, PermissionError):
                    path.unlink()
        else:
            data = await file.read(max_read)
            asset = await runtime.runs.create_asset(
                context,
                data=data,
                filename=file.filename,
                content_type=file.content_type or "application/octet-stream",
                kind=kind,
                domain=domain,
            )
        return envelope(request, asset)

    @router.post("/api/v1/media/uploads/presign", tags=["Media"])
    async def presign_media_upload(
        body: PresignMediaUploadRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PresignedMediaUpload]:
        require_presigned_storage()
        validate_direct_upload_size(body)
        await require_allowed(
            runtime.policy, context, "create", "media_asset", {"kind": body.kind.value}
        )
        upload_id = f"upl_{uuid4().hex}"
        object_key = (
            f"tenants/{context.tenant_id}/projects/{context.project_id}"
            f"/pending-uploads/{upload_id}/original"
        )
        expires_at = int(time.time()) + runtime.settings.s3_presign_expiry_seconds
        signed = await runtime.objects.presign_upload(
            object_key,
            content_type=body.content_type,
            sha256=body.sha256,
            size_bytes=body.size_bytes,
            expires_in=runtime.settings.s3_presign_expiry_seconds,
            retention_category="pending_upload",
        )
        response = PresignedMediaUpload(
            upload_id=upload_id,
            upload_token=upload_token(context, upload_id, body, expires_at),
            url=signed.url,
            headers=signed.headers,
            expires_at=expires_at,
        )
        return envelope(request, response)

    @router.post("/api/v1/media/uploads/complete", status_code=201, tags=["Media"])
    async def complete_media_upload(
        body: CompleteMediaUploadRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaAsset]:
        require_presigned_storage()
        validate_direct_upload_size(body)
        expected_token = upload_token(
            context, body.upload_id, body, int(body.expires_at)
        )
        if not hmac.compare_digest(expected_token, body.upload_token):
            raise HTTPException(
                status_code=403, detail="presigned upload token is invalid"
            )
        if time.time() > body.expires_at + PRESIGN_UPLOAD_EXPIRY_GRACE_SECONDS:
            raise HTTPException(status_code=410, detail="presigned upload has expired")
        object_key = (
            f"tenants/{context.tenant_id}/projects/{context.project_id}"
            f"/pending-uploads/{body.upload_id}/original"
        )
        if not await runtime.objects.exists(object_key):
            raise HTTPException(
                status_code=409, detail="presigned upload object is not available"
            )
        metadata = await runtime.objects.verify(object_key, body.sha256)
        if metadata.size_bytes != body.size_bytes:
            raise ValueError("uploaded object size does not match the request")
        suffix = Path(body.filename or "media.bin").suffix or ".bin"
        handle = tempfile.NamedTemporaryFile(
            prefix="scenara-direct-upload-", suffix=suffix, delete=False
        )
        handle.close()
        path = Path(handle.name)
        try:
            await runtime.objects.get_to_file(
                object_key, path, expected_sha256=body.sha256
            )
            asset = await runtime.runs.create_asset_from_path(
                context,
                path=str(path),
                filename=body.filename,
                content_type=body.content_type,
                kind=body.kind,
            )
        finally:
            with suppress(FileNotFoundError, PermissionError):
                path.unlink()
            with suppress(Exception):
                await runtime.objects.delete(object_key)
        return envelope(request, asset)

    @router.get("/api/v1/media/assets/{asset_id}/download-url", tags=["Media"])
    async def presign_media_download(
        asset_id: str,
        request: Request,
        expires_in: Annotated[int | None, Query(ge=60, le=86_400)] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PresignedMediaDownload]:
        require_presigned_storage()
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
            raise ResourceNotFound("media asset not found")
        await runtime.objects.verify(asset.object_key, asset.sha256)
        signed = await runtime.objects.presign_download(
            asset.object_key,
            expires_in=expires_in or runtime.settings.s3_presign_expiry_seconds,
            filename=asset.filename,
        )
        response = PresignedMediaDownload(
            url=signed.url,
            headers=signed.headers,
            expires_at=signed.expires_at,
        )
        return envelope(request, response)

    @router.get("/api/v1/media/assets", tags=["Media"])
    async def list_media_assets(
        request: Request,
        domain: Annotated[str | None, Query()] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaAssetPage]:
        await require_allowed(runtime.policy, context, "list", "media_asset")
        rows, total = await asyncio.gather(
            runtime.state.list_assets(
                context.tenant_id,
                context.project_id,
                domain=domain,
                include_deleted=False,
                offset=offset,
                limit=limit,
            ),
            runtime.state.count_assets(
                context.tenant_id,
                context.project_id,
                domain=domain,
                include_deleted=False,
            ),
        )
        return envelope(
            request,
            MediaAssetPage(items=rows, offset=offset, limit=limit, total=total),
        )

    @router.get("/api/v1/media/assets/{asset_id}", tags=["Media"])
    async def get_media_asset(
        asset_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaAsset]:
        await require_allowed(
            runtime.policy, context, "read", "media_asset", {"asset_id": asset_id}
        )
        asset = await runtime.state.get_asset(
            context.tenant_id, context.project_id, asset_id
        )
        if asset is None or asset.deleted_at is not None:
            raise ResourceNotFound("media asset not found")
        return envelope(request, asset)

    @router.get("/api/v1/media/assets/{asset_id}/preview", tags=["Media"])
    async def get_media_asset_preview(
        asset_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        data, content_type = await runtime.runs.get_asset_preview(context, asset_id)
        return Response(content=data, media_type=content_type)

    @router.delete("/api/v1/media/assets/{asset_id}", status_code=204, tags=["Media"])
    async def delete_media_asset(
        asset_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.runs.delete_asset(context, asset_id)
        return Response(status_code=204)

    @router.post("/api/v1/media/sources", status_code=201, tags=["Media"])
    async def create_media_source(
        body: CreateMediaSourceRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaSourceView]:
        source = await runtime.runs.create_source(context, body)
        return envelope(request, _media_source_view(source))

    @router.get("/api/v1/media/sources", tags=["Media"])
    async def list_media_sources(
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaSourcePage]:
        await require_allowed(runtime.policy, context, "list", "media_source")
        rows, total = await asyncio.gather(
            runtime.state.list_sources(
                context.tenant_id,
                context.project_id,
                offset=offset,
                limit=limit,
            ),
            runtime.state.count_sources(context.tenant_id, context.project_id),
        )
        return envelope(
            request,
            MediaSourcePage(
                items=[_media_source_view(item) for item in rows],
                offset=offset,
                limit=limit,
                total=total,
            ),
        )

    @router.get("/api/v1/media/sources/{source_id}", tags=["Media"])
    async def get_media_source(
        source_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaSourceView]:
        source = await runtime.runs.get_source(context, source_id)
        return envelope(request, _media_source_view(source))

    @router.post("/api/v1/media/sources/{source_id}/probe", tags=["Media"])
    async def probe_media_source(
        source_id: str,
        request: Request,
        timeout_ms: Annotated[int, Query(ge=100, le=30_000)] = 10_000,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[MediaSourceProbe]:
        return envelope(
            request,
            await runtime.runs.probe_source(context, source_id, timeout_ms=timeout_ms),
        )

    @router.get("/api/v1/media/sources/{source_id}/preview", tags=["Media"])
    async def get_media_source_preview(
        source_id: str,
        timeout_ms: Annotated[int, Query(ge=100, le=30_000)] = 10_000,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        data, content_type = await runtime.runs.get_source_preview(
            context, source_id, timeout_ms=timeout_ms
        )
        return Response(content=data, media_type=content_type)

    @router.delete("/api/v1/media/sources/{source_id}", status_code=204, tags=["Media"])
    async def delete_media_source(
        source_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.runs.delete_source(context, source_id)
        return Response(status_code=204)

    return router


__all__ = ["build_media_router"]
