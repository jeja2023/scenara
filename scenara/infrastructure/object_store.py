from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import shutil
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

from scenara.platform.objects import (
    ObjectAlreadyExistsError,
    ObjectIntegrityError,
    ObjectMetadata,
    ObjectStoreCapabilityError,
    PresignedObjectRequest,
    RetentionCategory,
    validate_object_key,
    validate_sha256,
)

try:
    from botocore.exceptions import ClientError
except ImportError:  # pragma: no cover
    class ClientError(Exception):  # type: ignore[no-redef]
        response: dict[str, Any]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _checksum_header(sha256: str) -> str:
    return base64.b64encode(bytes.fromhex(sha256)).decode("ascii")


def _write_fd(fd: int, data: bytes) -> None:
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()


def _copy_to_fd(fd: int, source: Path) -> None:
    with source.open("rb") as source_handle, os.fdopen(fd, "wb") as target_handle:
        shutil.copyfileobj(source_handle, target_handle, length=1024 * 1024)
        target_handle.flush()


class LocalObjectStore:
    """Filesystem provider with immutable-by-default, atomic object publication."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def health_check(self) -> None:
        if not self.root.is_dir():
            raise RuntimeError("local object store is unavailable")

    def _path(self, object_key: str) -> Path:
        target = (self.root / validate_object_key(object_key)).resolve()
        if self.root not in target.parents:
            raise ValueError("object key escapes storage root")
        return target

    def _metadata_path(self, object_key: str) -> Path:
        return self._path(object_key + ".metadata.json")

    def _read_metadata(self, object_key: str, path: Path) -> ObjectMetadata:
        metadata_path = self._metadata_path(object_key)
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            return ObjectMetadata(
                object_key=object_key,
                size_bytes=int(payload["size_bytes"]),
                sha256=validate_sha256(str(payload["sha256"])),
                content_type=str(payload.get("content_type") or "application/octet-stream"),
                version_id=None,
                retention_category=payload.get("retention_category"),
            )
        except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            sha256, size = _sha256_file(path)
            return ObjectMetadata(object_key, size, sha256, "application/octet-stream")

    async def _existing_or_raise(self, object_key: str, path: Path, sha256: str) -> ObjectMetadata:
        existing = await asyncio.to_thread(self._read_metadata, object_key, path)
        if existing.sha256 == sha256:
            return existing
        raise ObjectAlreadyExistsError(f"immutable object already exists: {object_key}")

    async def _write_metadata(self, metadata: ObjectMetadata, *, overwrite: bool) -> None:
        metadata_path = self._metadata_path(metadata.object_key)
        payload = json.dumps(
            {
                "size_bytes": metadata.size_bytes,
                "sha256": metadata.sha256,
                "content_type": metadata.content_type,
                "retention_category": metadata.retention_category,
            },
            sort_keys=True,
        ).encode("utf-8")
        if overwrite:
            await asyncio.to_thread(metadata_path.write_bytes, payload)
            return
        try:
            fd = await asyncio.to_thread(os.open, metadata_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            return
        await asyncio.to_thread(_write_fd, fd, payload)

    async def put(
        self,
        object_key: str,
        data: bytes,
        content_type: str,
        *,
        sha256: str | None = None,
        overwrite: bool = False,
        retention_category: RetentionCategory | None = None,
    ) -> ObjectMetadata:
        path = self._path(object_key)
        digest = validate_sha256(sha256) if sha256 else _sha256_bytes(data)
        if digest != _sha256_bytes(data):
            raise ObjectIntegrityError(f"bytes do not match sha256 for {object_key}")
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            return await self._existing_or_raise(object_key, path, digest)
        if overwrite:
            temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            await asyncio.to_thread(temporary.write_bytes, data)
            await asyncio.to_thread(os.replace, temporary, path)
        else:
            try:
                fd = await asyncio.to_thread(os.open, path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            except FileExistsError:
                return await self._existing_or_raise(object_key, path, digest)
            await asyncio.to_thread(_write_fd, fd, data)
        metadata = ObjectMetadata(object_key, len(data), digest, content_type, None, retention_category)
        await self._write_metadata(metadata, overwrite=overwrite)
        return metadata

    async def put_file(
        self,
        object_key: str,
        source: Path,
        content_type: str,
        *,
        sha256: str | None = None,
        overwrite: bool = False,
        retention_category: RetentionCategory | None = None,
    ) -> ObjectMetadata:
        path = self._path(object_key)
        digest, size = await asyncio.to_thread(_sha256_file, source)
        if sha256 and validate_sha256(sha256) != digest:
            raise ObjectIntegrityError(f"file does not match sha256 for {object_key}")
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            return await self._existing_or_raise(object_key, path, digest)
        if overwrite:
            temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            await asyncio.to_thread(shutil.copyfile, source, temporary)
            await asyncio.to_thread(os.replace, temporary, path)
        else:
            try:
                fd = await asyncio.to_thread(os.open, path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            except FileExistsError:
                return await self._existing_or_raise(object_key, path, digest)
            await asyncio.to_thread(_copy_to_fd, fd, source)
        metadata = ObjectMetadata(object_key, size, digest, content_type, None, retention_category)
        await self._write_metadata(metadata, overwrite=overwrite)
        return metadata

    async def stat(self, object_key: str, *, expected_sha256: str | None = None) -> ObjectMetadata:
        path = self._path(object_key)
        metadata = await asyncio.to_thread(self._read_metadata, object_key, path)
        if expected_sha256 and metadata.sha256 != validate_sha256(expected_sha256):
            raise ObjectIntegrityError(f"object checksum does not match: {object_key}")
        return metadata

    async def verify(self, object_key: str, expected_sha256: str) -> ObjectMetadata:
        return await self.stat(object_key, expected_sha256=expected_sha256)

    async def get(self, object_key: str, *, expected_sha256: str | None = None) -> bytes:
        data = await asyncio.to_thread(self._path(object_key).read_bytes)
        digest = _sha256_bytes(data)
        if expected_sha256 and digest != validate_sha256(expected_sha256):
            raise ObjectIntegrityError(f"object checksum does not match: {object_key}")
        return data

    async def get_to_file(
        self, object_key: str, path: Path, *, expected_sha256: str | None = None
    ) -> ObjectMetadata:
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, self._path(object_key), path)
        metadata = await asyncio.to_thread(_sha256_file, path)
        result = ObjectMetadata(object_key, metadata[1], metadata[0], "application/octet-stream")
        if expected_sha256 and result.sha256 != validate_sha256(expected_sha256):
            with suppress(FileNotFoundError):
                await asyncio.to_thread(path.unlink)
            raise ObjectIntegrityError(f"object checksum does not match: {object_key}")
        return result

    async def exists(self, object_key: str) -> bool:
        return await asyncio.to_thread(self._path(object_key).is_file)

    async def delete(self, object_key: str) -> bool:
        path = self._path(object_key)
        if not path.exists():
            return False
        await asyncio.to_thread(path.unlink)
        with suppress(FileNotFoundError):
            await asyncio.to_thread(self._metadata_path(object_key).unlink)
        return True

    async def set_retention_category(self, object_key: str, category: RetentionCategory) -> None:
        metadata = await self.stat(object_key)
        await self._write_metadata(
            ObjectMetadata(
                metadata.object_key,
                metadata.size_bytes,
                metadata.sha256,
                metadata.content_type,
                metadata.version_id,
                category,
            ),
            overwrite=True,
        )

    async def presign_upload(
        self,
        object_key: str,
        *,
        content_type: str,
        sha256: str,
        size_bytes: int,
        expires_in: int,
        retention_category: RetentionCategory,
    ) -> PresignedObjectRequest:
        del object_key, content_type, sha256, size_bytes, expires_in, retention_category
        raise ObjectStoreCapabilityError("local object storage does not support presigned requests")

    async def presign_download(
        self,
        object_key: str,
        *,
        expires_in: int,
        filename: str | None = None,
    ) -> PresignedObjectRequest:
        del object_key, expires_in, filename
        raise ObjectStoreCapabilityError("local object storage does not support presigned requests")


class S3ObjectStore:
    """S3 provider shared by MinIO, AWS S3, OSS and other certified backends."""

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        public_endpoint_url: str = "",
        region: str,
        access_key: str = "",
        secret_key: str = "",
        session_token: str = "",
        verify_tls: bool = True,
        ca_bundle: str = "",
        server_side_encryption: str = "",
        kms_key_id: str = "",
        multipart_threshold_bytes: int = 64 * 1024 * 1024,
        multipart_chunk_bytes: int = 16 * 1024 * 1024,
        lifecycle_enabled: bool = False,
        raw_media_retention_days: int = 7,
        preview_retention_days: int = 30,
        structured_result_retention_days: int = 180,
        addressing_style: str = "auto",
    ) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("boto3 is required for the S3 object backend") from exc
        if multipart_chunk_bytes < 5 * 1024 * 1024:
            raise ValueError("S3 multipart chunk size must be at least 5 MiB")
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.region = region
        self.server_side_encryption = server_side_encryption.strip()
        self.kms_key_id = kms_key_id.strip()
        self.multipart_threshold_bytes = multipart_threshold_bytes
        self.multipart_chunk_bytes = multipart_chunk_bytes
        self.lifecycle_enabled = lifecycle_enabled
        self.retention_days = {
            "raw_media": raw_media_retention_days,
            "preview": preview_retention_days,
            "structured_result": structured_result_retention_days,
            "pending_upload": 1,
        }
        credentials: dict[str, str] = {}
        if access_key or secret_key:
            credentials.update(aws_access_key_id=access_key, aws_secret_access_key=secret_key)
        if session_token:
            credentials["aws_session_token"] = session_token
        client_options: dict[str, Any] = {
            "region_name": region,
            "verify": ca_bundle or verify_tls,
            "config": Config(
                signature_version="s3v4",
                retries={"mode": "standard", "max_attempts": 5},
                s3=cast(Any, {"addressing_style": addressing_style}),
            ),
            **credentials,
        }
        self.client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            **client_options,
        )
        self.presign_client: Any = (
            boto3.client("s3", endpoint_url=public_endpoint_url, **client_options)
            if public_endpoint_url and public_endpoint_url != endpoint_url
            else self.client
        )

    async def open(self) -> None:
        await asyncio.to_thread(self.client.head_bucket, Bucket=self.bucket)
        if self.lifecycle_enabled:
            await self.configure_lifecycle()

    async def close(self) -> None:
        if self.presign_client is not self.client:
            self.presign_client.close()
        self.client.close()

    async def health_check(self) -> None:
        await asyncio.to_thread(self.client.head_bucket, Bucket=self.bucket)

    def _encryption_args(self) -> dict[str, str]:
        if not self.server_side_encryption:
            return {}
        args = {"ServerSideEncryption": self.server_side_encryption}
        if self.kms_key_id:
            args["SSEKMSKeyId"] = self.kms_key_id
        return args

    def _put_args(self, *, content_type: str, sha256: str, overwrite: bool) -> dict[str, Any]:
        args: dict[str, Any] = {
            "ContentType": content_type,
            "Metadata": {"sha256": sha256},
            "ChecksumSHA256": _checksum_header(sha256),
            **self._encryption_args(),
        }
        if not overwrite:
            args["IfNoneMatch"] = "*"
        return args

    async def _existing_or_raise(self, object_key: str, sha256: str) -> ObjectMetadata:
        existing = await self.stat(object_key)
        if existing.sha256 == sha256:
            return existing
        raise ObjectAlreadyExistsError(f"immutable object already exists: {object_key}")

    async def put(
        self,
        object_key: str,
        data: bytes,
        content_type: str,
        *,
        sha256: str | None = None,
        overwrite: bool = False,
        retention_category: RetentionCategory | None = None,
    ) -> ObjectMetadata:
        validate_object_key(object_key)
        digest = validate_sha256(sha256) if sha256 else _sha256_bytes(data)
        if digest != _sha256_bytes(data):
            raise ObjectIntegrityError(f"bytes do not match sha256 for {object_key}")
        args = self._put_args(content_type=content_type, sha256=digest, overwrite=overwrite)
        if retention_category:
            args["Tagging"] = f"retention-category={retention_category}"
        try:
            response = await asyncio.to_thread(
                self.client.put_object, Bucket=self.bucket, Key=object_key, Body=data, **args
            )
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if not overwrite and code in {"412", "PreconditionFailed", "ConditionalRequestConflict"}:
                return await self._existing_or_raise(object_key, digest)
            raise
        return ObjectMetadata(
            object_key,
            len(data),
            digest,
            content_type,
            response.get("VersionId"),
            retention_category,
        )

    async def put_file(
        self,
        object_key: str,
        path: Path,
        content_type: str,
        *,
        sha256: str | None = None,
        overwrite: bool = False,
        retention_category: RetentionCategory | None = None,
    ) -> ObjectMetadata:
        validate_object_key(object_key)
        digest, size = await asyncio.to_thread(_sha256_file, path)
        if sha256 and validate_sha256(sha256) != digest:
            raise ObjectIntegrityError(f"file does not match sha256 for {object_key}")
        if size < self.multipart_threshold_bytes:
            return await self.put(
                object_key,
                await asyncio.to_thread(path.read_bytes),
                content_type,
                sha256=digest,
                overwrite=overwrite,
                retention_category=retention_category,
            )
        args = {
            "Bucket": self.bucket,
            "Key": object_key,
            "ContentType": content_type,
            "Metadata": {"sha256": digest},
            "ChecksumAlgorithm": "SHA256",
            **self._encryption_args(),
        }
        if retention_category:
            args["Tagging"] = f"retention-category={retention_category}"
        upload = await asyncio.to_thread(self.client.create_multipart_upload, **args)
        upload_id = upload["UploadId"]
        parts: list[dict[str, Any]] = []
        try:
            with path.open("rb") as handle:
                part_number = 1
                while chunk := await asyncio.to_thread(handle.read, self.multipart_chunk_bytes):
                    part_digest = _sha256_bytes(chunk)
                    response = await asyncio.to_thread(
                        self.client.upload_part,
                        Bucket=self.bucket,
                        Key=object_key,
                        UploadId=upload_id,
                        PartNumber=part_number,
                        Body=chunk,
                        ChecksumSHA256=_checksum_header(part_digest),
                    )
                    parts.append(
                        {
                            "PartNumber": part_number,
                            "ETag": response["ETag"],
                            "ChecksumSHA256": response.get("ChecksumSHA256", _checksum_header(part_digest)),
                        }
                    )
                    part_number += 1
            complete_args: dict[str, Any] = {
                "Bucket": self.bucket,
                "Key": object_key,
                "UploadId": upload_id,
                "MultipartUpload": {"Parts": parts},
            }
            if not overwrite:
                complete_args["IfNoneMatch"] = "*"
            try:
                response = await asyncio.to_thread(self.client.complete_multipart_upload, **complete_args)
            except ClientError as exc:
                code = str(exc.response.get("Error", {}).get("Code", ""))
                if not overwrite and code in {"412", "PreconditionFailed", "ConditionalRequestConflict"}:
                    return await self._existing_or_raise(object_key, digest)
                raise
            return ObjectMetadata(
                object_key,
                size,
                digest,
                content_type,
                response.get("VersionId"),
                retention_category,
            )
        except Exception:
            with suppress(Exception):
                await asyncio.to_thread(
                    self.client.abort_multipart_upload,
                    Bucket=self.bucket,
                    Key=object_key,
                    UploadId=upload_id,
                )
            raise

    async def stat(self, object_key: str, *, expected_sha256: str | None = None) -> ObjectMetadata:
        validate_object_key(object_key)
        response = await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=object_key)
        metadata = response.get("Metadata", {})
        digest = metadata.get("sha256")
        if not digest and response.get("ChecksumSHA256"):
            digest = base64.b64decode(response["ChecksumSHA256"]).hex()
        if not digest:
            if expected_sha256:
                await self.get(object_key, expected_sha256=expected_sha256)
                return ObjectMetadata(
                    object_key,
                    int(response.get("ContentLength", 0)),
                    validate_sha256(expected_sha256),
                    response.get("ContentType") or "application/octet-stream",
                    response.get("VersionId"),
                )
            raise ObjectIntegrityError(f"object has no SHA-256 metadata: {object_key}")
        digest = validate_sha256(digest)
        if expected_sha256 and digest != validate_sha256(expected_sha256):
            raise ObjectIntegrityError(f"object checksum does not match: {object_key}")
        return ObjectMetadata(object_key, int(response.get("ContentLength", 0)), digest, response.get("ContentType") or "application/octet-stream", response.get("VersionId"))

    async def verify(self, object_key: str, expected_sha256: str) -> ObjectMetadata:
        return await self.stat(object_key, expected_sha256=expected_sha256)

    async def get(self, object_key: str, *, expected_sha256: str | None = None) -> bytes:
        validate_object_key(object_key)
        response = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=object_key)
        data = bytes(await asyncio.to_thread(response["Body"].read))
        digest = _sha256_bytes(data)
        declared = expected_sha256 or response.get("Metadata", {}).get("sha256")
        if declared and digest != validate_sha256(declared):
            raise ObjectIntegrityError(f"object checksum does not match: {object_key}")
        return data

    async def get_to_file(
        self, object_key: str, path: Path, *, expected_sha256: str | None = None
    ) -> ObjectMetadata:
        validate_object_key(object_key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix="scenara-download-", suffix=".tmp", dir=path.parent
        )
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            await asyncio.to_thread(self.client.download_file, self.bucket, object_key, str(temporary))
            digest, size = await asyncio.to_thread(_sha256_file, temporary)
            declared = expected_sha256 or (await self.stat(object_key)).sha256
            if digest != validate_sha256(declared):
                raise ObjectIntegrityError(f"object checksum does not match: {object_key}")
            await asyncio.to_thread(os.replace, temporary, path)
            return ObjectMetadata(object_key, size, digest, "application/octet-stream")
        finally:
            with suppress(FileNotFoundError):
                await asyncio.to_thread(temporary.unlink)

    async def exists(self, object_key: str) -> bool:
        validate_object_key(object_key)
        try:
            await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=object_key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    async def delete(self, object_key: str) -> bool:
        validate_object_key(object_key)
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=object_key)
        return True

    async def set_retention_category(self, object_key: str, category: RetentionCategory) -> None:
        validate_object_key(object_key)
        await asyncio.to_thread(
            self.client.put_object_tagging,
            Bucket=self.bucket,
            Key=object_key,
            Tagging={"TagSet": [{"Key": "retention-category", "Value": category}]},
        )

    async def configure_lifecycle(self) -> None:
        rules = []
        for category, days in self.retention_days.items():
            # PostgreSQL retention records remain authoritative. Provider-side
            # expiry is a one-day-late safety net, except for unregistered uploads.
            expiration_days = days if category == "pending_upload" else days + 1
            rules.append(
                {
                    "ID": f"scenara-{category}",
                    "Status": "Enabled",
                    "Filter": {"Tag": {"Key": "retention-category", "Value": category}},
                    "Expiration": {"Days": expiration_days},
                    "NoncurrentVersionExpiration": {"NoncurrentDays": expiration_days},
                }
            )
        await asyncio.to_thread(
            self.client.put_bucket_lifecycle_configuration,
            Bucket=self.bucket,
            LifecycleConfiguration={"Rules": rules},
        )

    async def presign_upload(
        self,
        object_key: str,
        *,
        content_type: str,
        sha256: str,
        size_bytes: int,
        expires_in: int,
        retention_category: RetentionCategory,
    ) -> PresignedObjectRequest:
        validate_object_key(object_key)
        digest = validate_sha256(sha256)
        if size_bytes < 1 or expires_in < 1 or expires_in > 86_400:
            raise ValueError("invalid presigned upload limits")
        params: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": object_key,
            "ContentType": content_type,
            "ChecksumSHA256": _checksum_header(digest),
            "Metadata": {"sha256": digest},
            "Tagging": f"retention-category={retention_category}",
            "IfNoneMatch": "*",
            **self._encryption_args(),
        }
        url = await asyncio.to_thread(
            self.presign_client.generate_presigned_url,
            "put_object",
            Params=params,
            ExpiresIn=expires_in,
        )
        return PresignedObjectRequest(
            url=url,
            method="PUT",
            headers={
                "Content-Type": content_type,
                "Content-Length": str(size_bytes),
                "x-amz-checksum-sha256": _checksum_header(digest),
                "x-amz-meta-sha256": digest,
                "x-amz-tagging": f"retention-category={retention_category}",
                "If-None-Match": "*",
                **(
                    {"x-amz-server-side-encryption": self.server_side_encryption}
                    if self.server_side_encryption
                    else {}
                ),
                **(
                    {"x-amz-server-side-encryption-aws-kms-key-id": self.kms_key_id}
                    if self.kms_key_id
                    else {}
                ),
            },
            expires_at=time.time() + expires_in,
        )

    async def presign_download(
        self,
        object_key: str,
        *,
        expires_in: int,
        filename: str | None = None,
    ) -> PresignedObjectRequest:
        validate_object_key(object_key)
        if expires_in < 1 or expires_in > 86_400:
            raise ValueError("invalid presigned download expiry")
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": object_key}
        if filename:
            safe_filename = Path(filename).name.replace('"', "").replace("\r", "").replace("\n", "")
            params["ResponseContentDisposition"] = f'attachment; filename="{safe_filename}"'
        url = await asyncio.to_thread(
            self.presign_client.generate_presigned_url,
            "get_object",
            Params=params,
            ExpiresIn=expires_in,
        )
        return PresignedObjectRequest(url=url, method="GET", headers={}, expires_at=time.time() + expires_in)


__all__ = ["LocalObjectStore", "S3ObjectStore"]
