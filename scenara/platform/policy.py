from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from scenara.platform.models import PrincipalContext

RESOURCE_PRODUCTS = {
    "audit_event": "console",
    "dataset": "data",
    "dataset_version": "data",
    "enterprise_compliance": "console",
    "enterprise_incident": "console",
    "enterprise_sla": "console",
    "enterprise_support": "console",
    "feedback": "data",
    "hard-sample-manifest": "data",
    "iam": "console",
    "media_asset": "parse",
    "media_source": "parse",
    "model_package": "model",
    "model-deployment-event": "model",
    "model-release": "model",
    "operations": "console",
    "pipeline": "parse",
    "portrait_camera": "parse",
    "portrait_feature": "parse",
    "portrait_identity": "parse",
    "portrait_trajectory": "parse",
    "search_index": "parse",
    "saved_search": "search",
    "run": "parse",
    "webhook_delivery": "api",
    "webhook_subscription": "api",
}


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


class LocalPolicyProvider:
    """Self-hosted policy provider. Scope and product checks happen before this provider."""

    provider_id = "local-scoped"

    async def authorize(
        self,
        context: PrincipalContext,
        action: str,
        resource: str,
        attributes: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        del context, action, resource, attributes
        return PolicyDecision(allowed=True, reason="local self-hosted policy")

    async def consume(
        self,
        context: PrincipalContext,
        metric: str,
        amount: int,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        if amount < 0:
            raise ValueError("usage amount must be non-negative")
        del context, metric, attributes


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
    required = {
        "*",
        f"{resource}:*",
        f"{resource}:{action}",
    }
    if not (required & context.scopes):
        raise PolicyDenied(f"scope denied: {resource}:{action}")
    product_id = RESOURCE_PRODUCTS.get(resource)
    if product_id is not None and "*" not in context.product_ids and product_id not in context.product_ids:
        raise PolicyDenied(f"product denied: {product_id}")
    decision = await provider.authorize(context, action, resource, attributes)
    if not decision.allowed:
        raise PolicyDenied(decision.reason)
    return decision


__all__ = [
    "RESOURCE_PRODUCTS",
    "DenyUnavailablePolicyProvider",
    "DevelopmentPolicyProvider",
    "LocalPolicyProvider",
    "PolicyDecision",
    "PolicyDenied",
    "PolicyProvider",
    "PolicyUnavailable",
    "require_allowed",
]
