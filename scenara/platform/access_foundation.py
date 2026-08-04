from __future__ import annotations

from typing import Literal

from scenara.platform.models import (
    AccessCapabilityItem,
    AccessCapabilityStatus,
    AccessFoundationStatus,
    PrincipalContext,
)
from scenara.settings import Settings

type AuthMode = Literal["development_open", "single_bearer_token"]
type PrincipalSource = Literal["anonymous", "api_token", "service_account_api_key", "header"]


def build_access_foundation(
    settings: Settings,
    context: PrincipalContext,
    *,
    policy_provider: str,
) -> AccessFoundationStatus:
    auth_mode: AuthMode = "single_bearer_token" if settings.auth_required else "development_open"
    if settings.auth_required:
        principal_source: PrincipalSource = "service_account_api_key" if context.scopes else "api_token"
    elif context.principal_id == "anonymous":
        principal_source = "anonymous"
    else:
        principal_source = "header"

    return AccessFoundationStatus(
        auth_mode=auth_mode,
        principal_source=principal_source,
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        principal_id=context.principal_id,
        policy_provider=policy_provider,
        capabilities=[
            AccessCapabilityItem(
                capability_id="tenant_project_context",
                name="Tenant and project context",
                status=AccessCapabilityStatus.AVAILABLE,
                summary="Every request and IAM resource is scoped by tenant and project identifiers.",
                current_scope=[
                    "organization records",
                    "project records",
                    "tenant/project scoped storage keys",
                    "project lifecycle approval requests",
                ],
                not_in_scope_yet=["cross-tenant project moves", "irreversible storage erasure evidence"],
                next_gate="Bind lifecycle approvals to the deployment evidence and retention owner.",
            ),
            AccessCapabilityItem(
                capability_id="api_authentication",
                name="API authentication",
                status=AccessCapabilityStatus.AVAILABLE,
                summary="Production accepts a root bearer token and revocable scoped service-account API keys.",
                current_scope=["single configured bearer token", "service account API keys", "scoped API keys"],
                not_in_scope_yet=["OAuth applications", "signed external identity assertion exchange"],
                next_gate="Connect a deployment-owned OIDC/SAML/SCIM adapter with verified assertions.",
            ),
            AccessCapabilityItem(
                capability_id="policy_provider",
                name="Policy provider",
                status=AccessCapabilityStatus.AVAILABLE,
                summary="Runtime services call a shared policy provider for authorization and quota decisions.",
                current_scope=[policy_provider, "API key scope enforcement"],
                not_in_scope_yet=["fine-grained policy editor", "ABAC UI"],
                next_gate="Persist role and product entitlement assignments outside the enterprise license document.",
            ),
            AccessCapabilityItem(
                capability_id="product_entitlements",
                name="Product entitlements",
                status=AccessCapabilityStatus.AVAILABLE,
                summary=(
                    "Project product assignments and service credential product limits are enforced "
                    "at the shared policy boundary."
                ),
                current_scope=[
                    "enterprise entitlements",
                    "project product activation and suspension",
                    "service account and API key product limits",
                    "runtime resource-to-product enforcement",
                ],
                not_in_scope_yet=["plan-to-entitlement automation", "self-service billing settlement"],
                next_gate="Require every future product module to register its resource-to-product policy mapping.",
            ),
            AccessCapabilityItem(
                capability_id="audit_trail",
                name="Audit trail",
                status=AccessCapabilityStatus.AVAILABLE,
                summary="Platform services emit audit events for sensitive workflows.",
                current_scope=[
                    "service-level audit events",
                    "enterprise evidence workflows",
                    "IAM audit events",
                    "tenant-scoped audit search",
                    "JSON and CSV audit export",
                    "retention policy and purge controls",
                ],
                not_in_scope_yet=["export approval workflow", "long-term archival backend"],
                next_gate=(
                    "Add retention policy administration and immutable archival after operational ownership "
                    "is assigned."
                ),
            ),
            AccessCapabilityItem(
                capability_id="role_management",
                name="Role management",
                status=AccessCapabilityStatus.AVAILABLE,
                summary="Shared users, roles and project memberships are persisted for all Scenara products.",
                current_scope=["users", "projects", "roles", "memberships"],
                not_in_scope_yet=["visual permission editor", "hierarchical groups"],
                next_gate="Add group and external-claim mapping without bypassing project memberships.",
            ),
            AccessCapabilityItem(
                capability_id="sso",
                name="Single sign-on",
                status=AccessCapabilityStatus.PLANNED,
                summary=(
                    "Identity-provider registration and configuration probes are available "
                    "for enterprise adapters."
                ),
                current_scope=["OIDC/SAML/SCIM provider records", "configuration health probes"],
                not_in_scope_yet=["signed OIDC/SAML assertion exchange", "SCIM user push/pull"],
                next_gate="Bind a verified deployment adapter and map external claims to project memberships.",
            ),
        ],
    )


__all__ = ["build_access_foundation"]
