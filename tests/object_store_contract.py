from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from scenara.platform.objects import ObjectAlreadyExistsError, ObjectStore


async def assert_object_store_contract(
    factory: Callable[[], ObjectStore],
    temporary_directory: Path,
) -> None:
    """Exercise the minimum contract required from every certified provider."""

    prefix = f"qualification/{uuid4().hex}"
    keys = {
        "round_trip": f"{prefix}/round-trip.bin",
        "concurrent": f"{prefix}/concurrent.bin",
        "multipart": f"{prefix}/multipart.bin",
        "recovery": f"{prefix}/recovery.bin",
    }
    store = factory()
    await store.open()
    try:
        payload = b"scenara-object-contract"
        digest = hashlib.sha256(payload).hexdigest()
        metadata = await store.put(
            keys["round_trip"],
            payload,
            "application/octet-stream",
            sha256=digest,
            retention_category="structured_result",
        )
        assert metadata.sha256 == digest
        assert metadata.size_bytes == len(payload)
        assert (await store.stat(keys["round_trip"], expected_sha256=digest)).sha256 == digest
        assert await store.get(keys["round_trip"], expected_sha256=digest) == payload

        # A delivery retry with the same bytes is idempotent.
        assert (await store.put(keys["round_trip"], payload, "application/octet-stream")).sha256 == digest

        downloaded = temporary_directory / "downloaded.bin"
        await store.get_to_file(keys["round_trip"], downloaded, expected_sha256=digest)
        assert downloaded.read_bytes() == payload

        contenders = [f"writer-{index}".encode() for index in range(6)]
        outcomes = await asyncio.gather(
            *(
                store.put(keys["concurrent"], value, "application/octet-stream")
                for value in contenders
            ),
            return_exceptions=True,
        )
        assert sum(not isinstance(outcome, BaseException) for outcome in outcomes) == 1
        assert sum(isinstance(outcome, ObjectAlreadyExistsError) for outcome in outcomes) == len(contenders) - 1
        assert await store.get(keys["concurrent"]) in contenders

        # Providers configure a low multipart threshold in this suite so this
        # exercises stream/file upload without allocating the whole file in the API.
        large_path = temporary_directory / "multipart-source.bin"
        large_path.write_bytes((b"scenara-multipart" * 400_000) + b"tail")
        large_digest = hashlib.sha256(large_path.read_bytes()).hexdigest()
        uploaded = await store.put_file(
            keys["multipart"],
            large_path,
            "application/octet-stream",
            sha256=large_digest,
            retention_category="raw_media",
        )
        assert uploaded.sha256 == large_digest
        assert (await store.verify(keys["multipart"], large_digest)).size_bytes == large_path.stat().st_size

        await store.put(
            keys["recovery"],
            b"survives-provider-restart",
            "application/octet-stream",
            retention_category="structured_result",
        )
    finally:
        await store.close()

    recovered = factory()
    await recovered.open()
    try:
        recovery_digest = hashlib.sha256(b"survives-provider-restart").hexdigest()
        assert await recovered.get(keys["recovery"], expected_sha256=recovery_digest) == b"survives-provider-restart"
        for key in keys.values():
            assert await recovered.delete(key) is True
            assert not await recovered.exists(key)
    finally:
        await recovered.close()


__all__ = ["assert_object_store_contract"]
