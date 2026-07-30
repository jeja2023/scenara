from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from scenara.platform.models import PrincipalContext


class PolicyDenied(RuntimeError):
    pass


class PolicyUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    reason: str
    entitlements: frozenset[str] = frozenset()
    limits: dict[str, int] | None = None


class PolicyProvider(Protocol):
    provider_id: str

    async def authorize(
        self,
        context: PrincipalContext,
        action: str,
        resource: str,
        attributes: dict[str, Any] | None = None,
    ) -> PolicyDecision: ...

    async def consume(
        self,
        context: PrincipalContext,
        metric: str,
        amount: int,
        attributes: dict[str, Any] | None = None,
    ) -> None: ...


class DevelopmentPolicyProvider:
    provider_id = "development-open"

    async def authorize(
        self,
        context: PrincipalContext,
        action: str,
        resource: str,
        attributes: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        del context, action, resource, attributes
        return PolicyDecision(allowed=True, reason="development policy")

    async def consume(
        self,
        context: PrincipalContext,
        metric: str,
        amount: int,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        del context, metric, amount, attributes


class DenyUnavailablePolicyProvider:
    provider_id = "unavailable"

    async def authorize(
        self,
        context: PrincipalContext,
        action: str,
        resource: str,
        attributes: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        del context, action, resource, attributes
        raise PolicyUnavailable("enterprise policy provider is required but unavailable")

    async def consume(
        self,
        context: PrincipalContext,
        metric: str,
        amount: int,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        del context, metric, amount, attributes
        raise PolicyUnavailable("enterprise policy provider is required but unavailable")


async def require_allowed(
    provider: PolicyProvider,
    context: PrincipalContext,
    action: str,
    resource: str,
    attributes: dict[str, Any] | None = None,
) -> PolicyDecision:
    decision = await provider.authorize(context, action, resource, attributes)
    if not decision.allowed:
        raise PolicyDenied(decision.reason)
    return decision


__all__ = [
    "DenyUnavailablePolicyProvider",
    "DevelopmentPolicyProvider",
    "PolicyDecision",
    "PolicyDenied",
    "PolicyProvider",
    "PolicyUnavailable",
    "require_allowed",
]
