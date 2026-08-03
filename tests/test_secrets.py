from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from scenara.infrastructure.object_store import LocalObjectStore
from scenara.platform.secrets import EncryptedObjectSecretStore, SecretNotFound


@pytest.mark.asyncio
async def test_encrypted_secret_survives_store_reconstruction(tmp_path) -> None:
    key = Fernet.generate_key().decode("ascii")
    secret_ref = "secret://media-sources/source-1"
    source_url = "rtsp://camera.example.test/live?token=sensitive"

    first = EncryptedObjectSecretStore(LocalObjectStore(tmp_path), key)
    await first.put(secret_ref, source_url)
    stored = (tmp_path / "system" / "secrets" / "media-sources" / "source-1.enc").read_bytes()
    assert source_url.encode("utf-8") not in stored

    reconstructed = EncryptedObjectSecretStore(LocalObjectStore(tmp_path), key)
    assert await reconstructed.get(secret_ref) == source_url
    assert await reconstructed.delete(secret_ref) is True
    with pytest.raises(SecretNotFound):
        await reconstructed.get(secret_ref)
