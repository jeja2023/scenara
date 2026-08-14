from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scenara.infrastructure.object_store import LocalObjectStore
from scenara.platform.objects import ObjectIntegrityError, ObjectStoreCapabilityError
from tests.object_store_contract import assert_object_store_contract


@pytest.mark.asyncio
async def test_local_provider_satisfies_object_store_contract(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    await assert_object_store_contract(lambda: LocalObjectStore(root), tmp_path)


@pytest.mark.asyncio
async def test_local_provider_detects_corruption(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")
    digest = hashlib.sha256(b"original").hexdigest()
    await store.put("integrity/original.bin", b"original", "application/octet-stream", sha256=digest)
    store._path("integrity/original.bin").write_bytes(b"corrupt")

    with pytest.raises(ObjectIntegrityError):
        await store.get("integrity/original.bin", expected_sha256=digest)


@pytest.mark.asyncio
async def test_local_provider_explicitly_rejects_presigned_urls(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")
    with pytest.raises(ObjectStoreCapabilityError):
        await store.presign_download("objects/example.bin", expires_in=60)
