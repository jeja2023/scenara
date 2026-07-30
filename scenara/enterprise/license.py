from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, field_validator

from scenara.platform.models import PrincipalContext
from scenara.platform.policy import PolicyDecision, PolicyDenied


class EnterpriseLicenseError(RuntimeError):
    pass


class LicenseClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    license_id: str = Field(min_length=1, max_length=128)
    customer: str = Field(min_length=1, max_length=256)
    sla_targets: dict[str, float] = Field(default_factory=dict)
    tenant_ids: tuple[str, ...] = Field(min_length=1)
    entitlements: frozenset[str] = Field(min_length=1)
    limits: dict[str, int] = Field(default_factory=dict)
    support_tier: str = Field(default="standard", min_length=1, max_length=64)
    issued_at: int
    not_before: int
    expires_at: int

    @field_validator("limits")
    @classmethod
    def validate_limits(cls, value: dict[str, int]) -> dict[str, int]:
        if any(limit < 0 for limit in value.values()):
            raise ValueError("license limits must be non-negative")
        return value

    def validate_time(self, now: int | None = None) -> None:
        current = int(time.time()) if now is None else now
        if self.issued_at > self.not_before or self.not_before >= self.expires_at:
            raise EnterpriseLicenseError("enterprise license time bounds are invalid")
        if current < self.not_before:
            raise EnterpriseLicenseError("enterprise license is not active yet")
        if current >= self.expires_at:
            raise EnterpriseLicenseError("enterprise license has expired")


class SignedLicense(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: LicenseClaims
    signature: str = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class VerifiedLicense:
    claims: LicenseClaims
    document_sha256: str


def canonical_claims(claims: LicenseClaims) -> bytes:
    payload = claims.model_dump(mode="json")
    payload["entitlements"] = sorted(claims.entitlements)
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def verify_license(
    document: bytes,
    public_key_pem: bytes,
    *,
    now: int | None = None,
) -> VerifiedLicense:
    try:
        signed = SignedLicense.model_validate_json(document)
        signature = base64.b64decode(signed.signature, validate=True)
        key = serialization.load_pem_public_key(public_key_pem)
    except Exception as exc:
        raise EnterpriseLicenseError("enterprise license document is invalid") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise EnterpriseLicenseError("enterprise license key must be Ed25519")
    try:
        key.verify(signature, canonical_claims(signed.claims))
    except InvalidSignature as exc:
        raise EnterpriseLicenseError("enterprise license signature is invalid") from exc
    signed.claims.validate_time(now)
    return VerifiedLicense(
        claims=signed.claims,
        document_sha256=hashlib.sha256(document).hexdigest(),
    )


def load_verified_license(
    license_path: Path,
    public_key_path: Path,
) -> VerifiedLicense:
    if not license_path.is_file() or not public_key_path.is_file():
        raise EnterpriseLicenseError("enterprise license or public key file is missing")
    return verify_license(license_path.read_bytes(), public_key_path.read_bytes())


class UsageStore(Protocol):
    async def consume_usage(
        self,
        tenant_id: str,
        metric: str,
        amount: int,
        limit: int | None,
    ) -> int: ...

    async def usage(self, tenant_id: str) -> dict[str, int]: ...


class EnterprisePolicyProvider:
    def __init__(self, license: VerifiedLicense, usage_store: UsageStore) -> None:
        self.license = license
        self.usage_store = usage_store
        self.provider_id = f"enterprise-license:{license.claims.license_id}"

    def claims(self, context: PrincipalContext) -> LicenseClaims:
        claims = self.license.claims
        claims.validate_time()
        if context.tenant_id not in claims.tenant_ids:
            raise PolicyDenied("tenant is not covered by the enterprise license")
        return claims

    async def authorize(
        self,
        context: PrincipalContext,
        action: str,
        resource: str,
        attributes: dict[str, object] | None = None,
    ) -> PolicyDecision:
        del attributes
        claims = self.claims(context)
        required = {
            "*",
            resource,
            f"{resource}:*",
            f"{resource}:{action}",
        }
        matched = required & claims.entitlements
        if not matched:
            return PolicyDecision(
                allowed=False,
                reason=f"enterprise entitlement denied: {resource}:{action}",
                entitlements=claims.entitlements,
                limits=claims.limits,
            )
        return PolicyDecision(
            allowed=True,
            reason="enterprise entitlement granted",
            entitlements=claims.entitlements,
            limits=claims.limits,
        )

    async def consume(
        self,
        context: PrincipalContext,
        metric: str,
        amount: int,
        attributes: dict[str, object] | None = None,
    ) -> None:
        del attributes
        if amount < 0:
            raise ValueError("usage amount must be non-negative")
        claims = self.claims(context)
        limit = claims.limits.get(metric)
        await self.usage_store.consume_usage(context.tenant_id, metric, amount, limit)


__all__ = [
    "EnterpriseLicenseError",
    "EnterprisePolicyProvider",
    "LicenseClaims",
    "SignedLicense",
    "UsageStore",
    "VerifiedLicense",
    "canonical_claims",
    "load_verified_license",
    "verify_license",
]
