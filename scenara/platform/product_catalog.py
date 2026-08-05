from __future__ import annotations

from collections.abc import Iterable, Mapping

from scenara.platform.models import ProductCatalogItem, ProductLayer, ProductMaturity


def build_product_catalog(
    installed_domains: Iterable[str],
    *,
    domain_scopes: Mapping[str, Iterable[str]] | None = None,
) -> list[ProductCatalogItem]:
    domains = frozenset(installed_domains)
    parse_maturity = ProductMaturity.AVAILABLE if domains else ProductMaturity.SEED
    parse_scope = ["媒体接入", "运行生命周期", "版本化流水线", "类型化视觉结果", "OCR document parsing"]
    for domain_id in sorted(domains):
        parse_scope.extend(domain_scopes.get(domain_id, ()) if domain_scopes is not None else ())

    return [
        ProductCatalogItem(
            product_id="parse",
            name="Scenara Parse",
            layer=ProductLayer.PRODUCT_MODULE,
            maturity=parse_maturity,
            summary="面向图片、文档、视频和实时流的视觉解析产品模块。",
            current_scope=parse_scope,
            not_in_scope_yet=["已签名的生产评估证据", "更多客户领域"],
            console_route="/parse",
            api_paths=[
                "/api/v1/parse/image",
                "/api/v1/parse/video",
                "/api/v1/parse/document",
                "/api/v1/parse/stream",
                "/api/v1/runs",
                "/api/v1/runs/{run_id}/result",
                "/api/v1/runs/{run_id}/artifacts/{artifact_id}",
            ],
            depends_on=["api", "console", "sdk"],
            next_gate="完成批准模型制品和目标 GPU 证据的 1.0 生产资格验证。",
        ),
        ProductCatalogItem(
            product_id="model",
            name="Scenara Model",
            layer=ProductLayer.PRODUCT_MODULE,
            maturity=ProductMaturity.SEED,
            summary="模型准入、发布治理、回滚和部署证据管理。",
            current_scope=["模型制品目录", "发布生命周期", "部署事件", "反馈溯源"],
            not_in_scope_yet=["数据集标注", "实验跟踪", "training jobs", "算力调度"],
            console_route="/models",
            api_paths=[
                "/api/v1/model-packages/admissions",
                "/api/v1/models",
                "/api/v1/model-releases",
                "/api/v1/model-deployment-events",
            ],
            depends_on=["data", "api", "console"],
            next_gate=(
                "在数据集、实验和算力归属明确产品化前，训练能力继续由外部平台承担。"
            ),
        ),
        ProductCatalogItem(
            product_id="data",
            name="Scenara Data",
            layer=ProductLayer.PRODUCT_MODULE,
            maturity=ProductMaturity.SEED,
            summary="为视觉 AI 产品提供媒体、特征、反馈和难例数据闭环。",
            current_scope=[
                "媒体资产",
                "特征存储",
                "反馈记录",
                "难例清单",
                "数据集目录与版本管理",
                "资产清单绑定",
                "质量评分与溯源摘要",
                "标注交接契约",
            ],
            not_in_scope_yet=["标注审核界面", "数据湖存储", "训练作业编排"],
            console_route="/assets",
            api_paths=[
                "/api/v1/media/assets",
                "/api/v1/datasets",
                "/api/v1/datasets/{dataset_id}/versions",
                "/api/v1/feedback",
                "/api/v1/hard-sample-manifests",
            ],
            depends_on=["api", "console"],
            next_gate=(
                "采用版本契约后，再增加标注审核和与外部 Data 仓库的交接。"
            ),
        ),
        ProductCatalogItem(
            product_id="console",
            name="Scenara Console",
            layer=ProductLayer.CONTROL_PLANE,
            maturity=ProductMaturity.AVAILABLE,
            summary="平台运维与各产品模块共用的管理界面。",
            current_scope=[
                "概览",
                "资产",
                "数据集",
                "运行",
                "结果",
                "流水线",
                "模型",
                "反馈",
                "运维",
                "审计",
            ],
            not_in_scope_yet=["单点登录", "审计保留策略管理"],
            console_route="/",
            next_gate="在拆分商业产品前，补充 IAM 与产品授权管理。",
        ),
        ProductCatalogItem(
            product_id="api",
            name="Scenara API",
            layer=ProductLayer.DEVELOPER_SURFACE,
            maturity=ProductMaturity.AVAILABLE,
            summary="面向平台集成的版本化公开契约。",
            current_scope=["OpenAPI 契约", "v1 接口", "Webhook", "系统探针"],
            not_in_scope_yet=["开发者门户", "OAuth 应用", "弃用策略"],
            api_paths=["/openapi.json", "/api/v1/platform/products", "/api/v1/webhooks/subscriptions"],
            next_gate="在将 API 作为独立平台开放前，引入应用凭据和权限作用域。",
        ),
        ProductCatalogItem(
            product_id="sdk",
            name="Scenara SDK",
            layer=ProductLayer.DEVELOPER_SURFACE,
            maturity=ProductMaturity.AVAILABLE,
            summary="面向 v1 API 的 Python 与 TypeScript 开发客户端。",
            current_scope=["Python SDK", "TypeScript SDK", "OpenAPI 生成的模式类型"],
            not_in_scope_yet=[
                "多产品命名空间",
                "公开发布自动化",
                "长期弃用测试",
            ],
            api_paths=["/api/v1/platform/products"],
            depends_on=["api"],
            next_gate=(
                "保持 SDK 方法与 OpenAPI 同步，待产品拥有独立生命周期后再拆分命名空间。"
            ),
        ),
        ProductCatalogItem(
            product_id="index",
            name="Scenara Index",
            layer=ProductLayer.FOUNDATION,
            maturity=ProductMaturity.SEED,
            summary="面向解析结果和人像检索的租户级向量、文本与多模态索引基础设施。",
            current_scope=[
                "索引定义",
                "来源引用",
                "向量与文本查询",
                "软删除与保留策略",
                "保存的检索",
                "可重建的来源引用",
            ],
            not_in_scope_yet=[
                "ANN 加速",
                "分布式索引分片",
                "学习排序重排",
            ],
            api_paths=["/api/v1/indexes", "/api/v1/search/text", "/api/v1/search/image"],
            depends_on=["data"],
            next_gate=(
                "在面向生产前完成 ANN 后端、重建流程和固定排名评估的资格验证。"
            ),
        ),
        ProductCatalogItem(
            product_id="search",
            name="Scenara Search",
            layer=ProductLayer.PRODUCT_MODULE,
            maturity=ProductMaturity.SEED,
            summary="面向视觉资产、结果索引和来源位置的统一文本与人像检索。",
            current_scope=[
                "人像结果检索",
                "文档文本检索",
                "图片与视频筛选",
                "结果中心来源链接",
                "保存的检索定义与执行",
            ],
            not_in_scope_yet=["语义重排", "学习排序", "跨租户联邦检索"],
            api_paths=[
                "/api/v1/search/text",
                "/api/v1/search/image",
                "/api/v1/search/saved",
                "/api/v1/portrait/compare/images",
            ],
            depends_on=["parse", "index", "data"],
            next_gate="补充固定检索评估、相关性反馈和生产排名治理。",
        ),
        ProductCatalogItem(
            product_id="flow",
            name="Scenara Flow",
            layer=ProductLayer.PRODUCT_MODULE,
            maturity=ProductMaturity.SEED,
            summary="面向运行、Webhook 和人工审核的未来工作流编排产品。",
            current_scope=[
                "类型化流水线引擎",
                "流水线生命周期",
                "审批节点",
                "可支持条件的执行上下文",
                "调度进程",
            ],
            not_in_scope_yet=["工作流编辑", "分布式重试", "拖放式编辑器"],
            console_route="/pipelines",
            api_paths=["/api/v1/pipelines"],
            depends_on=["parse", "api"],
            next_gate="在增加用户自定义工作流前，保持流水线契约不可变。",
        ),
        ProductCatalogItem(
            product_id="edge",
            name="Scenara Edge",
            layer=ProductLayer.PRODUCT_MODULE,
            maturity=ProductMaturity.SEED,
            summary="面向离线和近端设备部署的未来边缘推理产品。",
            current_scope=[
                "设备注册表",
                "心跳与证书指纹",
                "已签名制品部署引用",
                "离线同步确认",
            ],
            not_in_scope_yet=[
                "设备群管理",
                "遥测",
                "全设备群发布策略",
            ],
            depends_on=["parse", "model", "api"],
            next_gate="待服务端部署和发布证据稳定后再启动。",
        ),
        ProductCatalogItem(
            product_id="agent",
            name="Scenara Agent",
            layer=ProductLayer.PRODUCT_MODULE,
            maturity=ProductMaturity.GATED,
            summary="可协调解析、检索、工作流和审核操作的未来智能代理层。",
            current_scope=[
                "工具注册表",
                "最小权限声明",
                "审批门禁操作",
                "可审计操作执行",
            ],
            not_in_scope_yet=[
                "代理评估",
                "记忆策略",
                "长时代理轨迹",
            ],
            depends_on=["flow", "search", "api", "console"],
            next_gate="待 Flow 与 Search 契约稳定并具备可审计操作治理后再增加。",
        ),
    ]


__all__ = ["build_product_catalog"]
