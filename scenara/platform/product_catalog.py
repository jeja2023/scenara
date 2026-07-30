from __future__ import annotations

from collections.abc import Iterable

from scenara.platform.models import ProductCatalogItem, ProductLayer, ProductMaturity


def build_product_catalog(installed_domains: Iterable[str]) -> list[ProductCatalogItem]:
    domains = frozenset(installed_domains)
    parse_maturity = ProductMaturity.AVAILABLE if {"portrait", "ocr"} & domains else ProductMaturity.SEED
    parse_scope = ["media ingestion", "run lifecycle", "versioned pipelines", "typed visual results"]
    if "portrait" in domains:
        parse_scope.append("portrait analysis")
    if "ocr" in domains:
        parse_scope.append("OCR document parsing")

    return [
        ProductCatalogItem(
            product_id="parse",
            name="Scenara Parse",
            layer=ProductLayer.PRODUCT_MODULE,
            maturity=parse_maturity,
            summary="Visual parsing product module for images, documents, video, and streams.",
            current_scope=parse_scope,
            not_in_scope_yet=["signed production evaluation evidence", "additional customer domains"],
            console_route="/parse",
            api_paths=["/api/v1/parse/image", "/api/v1/runs", "/api/v1/runs/{run_id}/result"],
            depends_on=["api", "console", "sdk"],
            next_gate="Complete 1.0 production qualification with approved model artifacts and target-GPU evidence.",
        ),
        ProductCatalogItem(
            product_id="model",
            name="Scenara Model",
            layer=ProductLayer.PRODUCT_MODULE,
            maturity=ProductMaturity.SEED,
            summary="Model admission, release governance, rollback, and deployment evidence.",
            current_scope=["model package catalog", "release lifecycle", "deployment events", "feedback provenance"],
            not_in_scope_yet=["dataset labeling", "experiment tracking", "training jobs", "compute scheduling"],
            console_route="/models",
            api_paths=["/api/v1/models", "/api/v1/model-releases", "/api/v1/model-deployment-events"],
            depends_on=["data", "api", "console"],
            next_gate="Keep training external until dataset, experiment, and compute ownership are explicitly productized.",
        ),
        ProductCatalogItem(
            product_id="data",
            name="Scenara Data",
            layer=ProductLayer.PRODUCT_MODULE,
            maturity=ProductMaturity.SEED,
            summary="Media, feature, feedback, and hard-sample data loop for visual AI products.",
            current_scope=["media assets", "feature store", "feedback records", "hard-sample manifests"],
            not_in_scope_yet=["dataset catalog", "labeling workflow", "data quality scoring", "lineage explorer"],
            console_route="/media",
            api_paths=["/api/v1/media/assets", "/api/v1/feedback", "/api/v1/hard-sample-manifests"],
            depends_on=["api", "console"],
            next_gate="Define first-class dataset resources before presenting Data as an independent hub.",
        ),
        ProductCatalogItem(
            product_id="console",
            name="Scenara Console",
            layer=ProductLayer.CONTROL_PLANE,
            maturity=ProductMaturity.AVAILABLE,
            summary="Shared management surface for platform operations and product modules.",
            current_scope=["overview", "media", "runs", "results", "pipelines", "models", "feedback", "operations"],
            not_in_scope_yet=["organization administration", "role management", "product entitlements", "SSO"],
            console_route="/",
            next_gate="Add IAM and product entitlement administration before separating commercial products.",
        ),
        ProductCatalogItem(
            product_id="api",
            name="Scenara API",
            layer=ProductLayer.DEVELOPER_SURFACE,
            maturity=ProductMaturity.AVAILABLE,
            summary="Versioned public contract for platform integration.",
            current_scope=["OpenAPI contract", "v1 endpoints", "webhooks", "system probes"],
            not_in_scope_yet=["developer portal", "scoped API keys", "OAuth applications", "deprecation policy"],
            api_paths=["/openapi.json", "/api/v1/platform/products", "/api/v1/webhooks/subscriptions"],
            next_gate="Introduce application credentials and scopes before opening API as a standalone platform.",
        ),
        ProductCatalogItem(
            product_id="sdk",
            name="Scenara SDK",
            layer=ProductLayer.DEVELOPER_SURFACE,
            maturity=ProductMaturity.AVAILABLE,
            summary="Python and TypeScript developer clients for the v1 API.",
            current_scope=["Python SDK", "TypeScript SDK", "OpenAPI-derived schema types"],
            not_in_scope_yet=["multi-product namespaces", "published release automation", "long-term deprecation testing"],
            api_paths=["/api/v1/platform/products"],
            depends_on=["api"],
            next_gate="Keep SDK methods aligned with OpenAPI and split namespaces only when products gain independent lifecycles.",
        ),
        ProductCatalogItem(
            product_id="index",
            name="Scenara Index",
            layer=ProductLayer.FOUNDATION,
            maturity=ProductMaturity.SEED,
            summary="Vector and feature substrate that can later become managed index infrastructure.",
            current_scope=["feature spaces", "vector search primitives", "portrait feature lookup"],
            not_in_scope_yet=["generic index resources", "index build lifecycle", "rebuild jobs", "ranking profiles"],
            api_paths=["/api/v1/portrait/search"],
            depends_on=["data"],
            next_gate="Create tenant-scoped index resources before positioning Index as a product.",
        ),
        ProductCatalogItem(
            product_id="search",
            name="Scenara Search",
            layer=ProductLayer.PRODUCT_MODULE,
            maturity=ProductMaturity.PLANNED,
            summary="Future multimodal search experience over parsed visual assets and indexes.",
            current_scope=["portrait identity search seed"],
            not_in_scope_yet=["generic visual search", "document search", "hybrid ranking", "saved queries"],
            api_paths=["/api/v1/portrait/search"],
            depends_on=["parse", "index", "data"],
            next_gate="Build generic Index resources first; keep portrait search as a domain feature meanwhile.",
        ),
        ProductCatalogItem(
            product_id="flow",
            name="Scenara Flow",
            layer=ProductLayer.PRODUCT_MODULE,
            maturity=ProductMaturity.PLANNED,
            summary="Future workflow authoring and orchestration over runs, webhooks, and human review.",
            current_scope=["typed pipeline engine", "pipeline lifecycle", "scheduler process"],
            not_in_scope_yet=["workflow authoring", "branching conditions", "approval steps", "drag-and-drop editor"],
            console_route="/pipelines",
            api_paths=["/api/v1/pipelines"],
            depends_on=["parse", "api"],
            next_gate="Keep pipeline contracts immutable before adding user-authored workflows.",
        ),
        ProductCatalogItem(
            product_id="edge",
            name="Scenara Edge",
            layer=ProductLayer.PRODUCT_MODULE,
            maturity=ProductMaturity.GATED,
            summary="Future edge inference product for offline and near-device deployments.",
            current_scope=[],
            not_in_scope_yet=["device registry", "fleet management", "signed model delivery", "offline sync", "telemetry"],
            depends_on=["parse", "model", "api"],
            next_gate="Do not start until the supported server deployment and release evidence are stable.",
        ),
        ProductCatalogItem(
            product_id="agent",
            name="Scenara Agent",
            layer=ProductLayer.PRODUCT_MODULE,
            maturity=ProductMaturity.GATED,
            summary="Future agentic layer that can coordinate parsing, search, workflow, and review actions.",
            current_scope=[],
            not_in_scope_yet=["tool permission model", "human approval loop", "agent traces", "agent evaluation", "memory policy"],
            depends_on=["flow", "search", "api", "console"],
            next_gate="Add after Flow and Search have stable contracts plus auditable action governance.",
        ),
    ]


__all__ = ["build_product_catalog"]
