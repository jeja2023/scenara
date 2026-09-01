"""Bounded, streaming helpers for multipart media uploads."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path
import tempfile

from fastapi import UploadFile


UPLOAD_CHUNK_BYTES = 1024 * 1024


def upload_limit(maximum: int, direct_maximum: int) -> int:
    """Return the effective limit for a direct multipart upload."""
    return min(maximum, direct_maximum)


async def spool_upload(file: UploadFile, max_bytes: int) -> Path:
    """Write an upload to a private temporary file without buffering it in memory.

    The caller owns and must remove the returned path.  The byte counter is
    deliberately independent of ``Content-Length`` because clients can omit
    or lie about that header.
    """
    suffix = Path(file.filename or "").suffix[:32]
    handle = tempfile.NamedTemporaryFile(
        prefix="scenara-upload-", suffix=suffix, delete=False
    )
    path = Path(handle.name)
    size = 0
    failed = False
    try:
        while chunk := await file.read(UPLOAD_CHUNK_BYTES):
            size += len(chunk)
            if size > max_bytes:
                raise ValueError(f"multipart upload exceeds {max_bytes} bytes; use a presigned upload")
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


def remove_spooled_upload(path: Path) -> None:
    """Best-effort cleanup for a temporary multipart upload."""
    with suppress(FileNotFoundError, PermissionError):
        path.unlink()


__all__ = ["UPLOAD_CHUNK_BYTES", "remove_spooled_upload", "spool_upload", "upload_limit"]
