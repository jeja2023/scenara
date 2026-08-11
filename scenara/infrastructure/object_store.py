from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from scenara.platform.objects import validate_object_key


class LocalObjectStore:
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

    async def put(self, object_key: str, data: bytes, content_type: str) -> None:
        del content_type
        path = self._path(object_key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def put_file(self, object_key: str, source: Path, content_type: str) -> None:
        del content_type
        path = self._path(object_key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source, path)

    async def get(self, object_key: str) -> bytes:
        return await asyncio.to_thread(self._path(object_key).read_bytes)

    async def get_to_file(self, object_key: str, path: Path) -> None:
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, self._path(object_key), path)

    async def delete(self, object_key: str) -> bool:
        path = self._path(object_key)
        if not path.exists():
            return False
        await asyncio.to_thread(path.unlink)
        return True


class S3ObjectStore:
    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        region: str,
        access_key: str,
        secret_key: str,
    ) -> None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - optional production dependency
            raise RuntimeError("boto3 is required for the S3 object backend") from exc
        self.bucket = bucket
        self.client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
        )

    async def open(self) -> None:
        await asyncio.to_thread(self.client.head_bucket, Bucket=self.bucket)

    async def close(self) -> None:
        self.client.close()

    async def health_check(self) -> None:
        await asyncio.to_thread(self.client.head_bucket, Bucket=self.bucket)

    async def put(self, object_key: str, data: bytes, content_type: str) -> None:
        validate_object_key(object_key)
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
        )

    async def put_file(self, object_key: str, path: Path, content_type: str) -> None:
        validate_object_key(object_key)
        await asyncio.to_thread(
            self.client.upload_file,
            str(path),
            self.bucket,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )

    async def get(self, object_key: str) -> bytes:
        validate_object_key(object_key)
        response = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=object_key)
        return await asyncio.to_thread(response["Body"].read)

    async def get_to_file(self, object_key: str, path: Path) -> None:
        validate_object_key(object_key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self.client.download_file, self.bucket, object_key, str(path))

    async def delete(self, object_key: str) -> bool:
        validate_object_key(object_key)
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=object_key)
        return True


__all__ = ["LocalObjectStore", "S3ObjectStore"]
