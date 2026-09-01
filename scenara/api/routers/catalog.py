from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from scenara.bootstrap import Runtime
from scenara.domains.portrait.capabilities import portrait_capability_snapshot
from scenara.platform.access_foundation import build_access_foundation
from scenara.platform.models import (
    AccessFoundationStatus,
    ApiEnvelope,
    PortraitIntelligenceStatus,
    PrincipalContext,
    ProductCatalogItem,
    RepositoryTopology,
)
from scenara.platform.policy import require_allowed
from scenara.platform.portrait_intelligence import build_portrait_intelligence
from scenara.platform.product_catalog import build_product_catalog
from scenara.platform.repository_contracts import (
    CONTRACT_ROOT,
    RepositoryContractCatalog,
    load_repository_contract_catalog,
)
from scenara.platform.repository_topology import build_repository_topology

EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_catalog_router(
    runtime: Runtime,
    principal_context: PrincipalDependency,
    envelope: EnvelopeFactory,
) -> APIRouter:
    """Build read-only model, domain, and platform-discovery endpoints.

    Keeping this product-catalog surface outside the application factory makes
    its public contract independently testable while retaining the existing
    URLs and authentication dependency.
    """

    router = APIRouter()

    @router.get("/api/v1/models", tags=["Models"])
    async def list_models(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[dict[str, object]]]:
        await require_allowed(runtime.policy, context, "list", "model_package")
        packages = await runtime.state.list_model_packages()
        rows = [package.model_dump(mode="json") for package in packages]
        return envelope(request, rows)

    @router.get("/api/v1/domains", tags=["Domains"])
    async def list_domains(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[dict[str, object]]]:
        del context
        rows = [
            {
                "domain_id": manifest.domain_id,
                "display_name": manifest.display_name,
                "schema_version": manifest.schema_version,
                "console_route": manifest.console_route,
                "capabilities": list(manifest.capabilities),
                "description": manifest.description,
                "supported_media_kinds": list(manifest.supported_media_kinds),
                "default_pipeline_id": manifest.default_pipeline_id
                or runtime.plugins.default_pipeline_id(manifest.domain_id),
                "navigation_order": manifest.navigation_order,
            }
            for manifest in runtime.plugins.manifests()
        ]
        return envelope(request, rows)

    @router.get("/api/v1/platform/products", tags=["Platform"])
    async def list_platform_products(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[ProductCatalogItem]]:
        del context
        manifests = runtime.plugins.manifests()
        installed_domains = [manifest.domain_id for manifest in manifests]
        domain_scopes = {
            manifest.domain_id: manifest.product_scope for manifest in manifests
        }
        return envelope(
            request,
            build_product_catalog(installed_domains, domain_scopes=domain_scopes),
        )

    @router.get("/api/v1/platform/repositories", tags=["Platform"])
    async def platform_repository_topology(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[RepositoryTopology]:
        del context
        return envelope(request, build_repository_topology())

    @router.get("/api/v1/platform/contracts", tags=["Platform"])
    async def platform_repository_contracts(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[RepositoryContractCatalog]:
        del context
        return envelope(request, load_repository_contract_catalog())

    @router.get("/api/v1/platform/contracts/{contract_id}/schema", tags=["Platform"])
    async def platform_repository_contract_schema(
        contract_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> FileResponse:
        del context
        catalog = load_repository_contract_catalog()
        artifact = next(
            (item for item in catalog.contracts if item.contract_id == contract_id),
            None,
        )
        if artifact is None:
            raise HTTPException(status_code=404, detail="repository contract not found")
        schema_path = CONTRACT_ROOT / Path(artifact.schema_path).name
        return FileResponse(
            schema_path,
            media_type="application/schema+json",
            filename=schema_path.name,
            headers={"ETag": f'"sha256:{artifact.schema_sha256}"'},
        )

    @router.get("/api/v1/platform/access-foundation", tags=["Platform"])
    async def platform_access_foundation(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[AccessFoundationStatus]:
        return envelope(
            request,
            build_access_foundation(
                runtime.settings, context, policy_provider=runtime.policy.provider_id
            ),
        )

    @router.get("/api/v1/platform/portrait-intelligence", tags=["Platform"])
    async def platform_portrait_intelligence(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[PortraitIntelligenceStatus]:
        """Return the Portrait Intelligence Foundation Platform contract.

        The response reports strategic modules, core assets, and capability
        readiness derived from the installed configuration. It describes
        current readiness rather than deployed model quality.
        """
        del context
        installed_domains = [
            manifest.domain_id for manifest in runtime.plugins.manifests()
        ]
        snapshot: dict[str, Any] = {}
        if "portrait" in installed_domains:
            with suppress(Exception):
                snapshot = portrait_capability_snapshot()
        return envelope(
            request,
            build_portrait_intelligence(snapshot, installed_domains=installed_domains),
        )

    return router


__all__ = ["build_catalog_router"]
