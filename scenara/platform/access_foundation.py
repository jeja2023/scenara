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
                current_scope=["organization records", "project records", "tenant/project scoped storage keys"],
                not_in_scope_yet=["project suspension", "project deletion workflow"],
                next_gate="Add project lifecycle controls after tenant provisioning rules settle.",
            ),
            AccessCapabilityItem(
                capability_id="api_authentication",
                name="API authentication",
                status=AccessCapabilityStatus.AVAILABLE,
                summary="Production accepts a root bearer token and revocable scoped service-account API keys.",
                current_scope=["single configured bearer token", "service account API keys", "scoped API keys"],
                not_in_scope_yet=["OAuth applications", "external identity federation"],
                next_gate="Add SSO and OAuth only after service-account and API-key administration settle.",
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
                not_in_scope_yet=["plan assignment", "seat allocation", "self-service billing"],
                next_gate="Require every future product module to register its resource-to-product policy mapping.",
            ),
            AccessCapabilityItem(
                capability_id="audit_trail",
                name="Audit trail",
                status=AccessCapabilityStatus.AVAILABLE,
                summary="Platform services emit audit events for sensitive workflows.",
                current_scope=["service-level audit events", "enterprise evidence workflows", "IAM audit events"],
                not_in_scope_yet=["central audit search", "retention policy UI", "export approvals"],
                next_gate="Expose tenant-scoped audit search and export controls in Console.",
            ),
            AccessCapabilityItem(
                capability_id="role_management",
                name="Role management",
                status=AccessCapabilityStatus.AVAILABLE,
                summary="Shared users, roles and project memberships are persisted for all Scenara products.",
                current_scope=["users", "projects", "roles", "memberships"],
                not_in_scope_yet=["visual permission editor", "hierarchical groups"],
                next_gate="Resolve role bindings during interactive user authentication.",
            ),
            AccessCapabilityItem(
                capability_id="sso",
                name="Single sign-on",
                status=AccessCapabilityStatus.PLANNED,
                summary="Future enterprise identity federation for operators and service users.",
                not_in_scope_yet=["OIDC", "SAML", "SCIM", "session management"],
                next_gate="Add role management and service account foundations before SSO.",
            ),
        ],
    )


__all__ = ["build_access_foundation"]
