from __future__ import annotations

from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken

from scenara.platform.objects import ObjectStore


class SecretNotFound(RuntimeError):
    pass


class SecretStore(Protocol):
    async def put(self, secret_ref: str, value: str) -> None: ...

    async def get(self, secret_ref: str) -> str: ...

    async def delete(self, secret_ref: str) -> bool: ...


class MemorySecretStore:
    """Process-local secret store for tests and development only."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    async def put(self, secret_ref: str, value: str) -> None:
        EncryptedObjectSecretStore._object_key(secret_ref)
        if not value:
            raise ValueError("secret value is empty")
        self._values[secret_ref] = value

    async def get(self, secret_ref: str) -> str:
        try:
            return self._values[secret_ref]
        except KeyError as exc:
            raise SecretNotFound(secret_ref) from exc

    async def delete(self, secret_ref: str) -> bool:
        return self._values.pop(secret_ref, None) is not None


class EncryptedObjectSecretStore:
    def __init__(self, objects: ObjectStore, key: str) -> None:
        if not key:
            raise ValueError("secret encryption key is required")
        try:
            self._cipher = Fernet(key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise ValueError("secret encryption key must be a URL-safe Fernet key") from exc
        self._objects = objects

    @staticmethod
    def _object_key(secret_ref: str) -> str:
        prefix = "secret://"
        if not secret_ref.startswith(prefix):
            raise ValueError("invalid secret reference")
        path = secret_ref[len(prefix) :]
        if not path or ".." in path or any(not part for part in path.split("/")):
            raise ValueError("invalid secret reference")
        return f"system/secrets/{path}.enc"

    async def put(self, secret_ref: str, value: str) -> None:
        if not value:
            raise ValueError("secret value is empty")
        encrypted = self._cipher.encrypt(value.encode("utf-8"))
        await self._objects.put(
            self._object_key(secret_ref),
            encrypted,
            "application/octet-stream",
            overwrite=True,
            retention_category="secret",
        )

    async def get(self, secret_ref: str) -> str:
        try:
            encrypted = await self._objects.get(self._object_key(secret_ref))
        except FileNotFoundError as exc:
            raise SecretNotFound(secret_ref) from exc
        try:
            return self._cipher.decrypt(encrypted).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise SecretNotFound("secret could not be decrypted") from exc

    async def delete(self, secret_ref: str) -> bool:
        return await self._objects.delete(self._object_key(secret_ref))


__all__ = ["EncryptedObjectSecretStore", "MemorySecretStore", "SecretNotFound", "SecretStore"]
