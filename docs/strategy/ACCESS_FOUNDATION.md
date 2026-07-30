# Scenara 访问底座

适用版本：`0.3.0-dev.0`（Python 包为 `0.3.0.dev0`）。

Scenara 的访问底座是产品矩阵共享的控制面能力。它不属于某一个视觉产品，所有 Scenara 产品复用同一套租户、项目、主体、权限范围、服务凭据和产品授权资源。

## 已落地资源

| 资源 | 作用域 | API |
| --- | --- | --- |
| Organization | 租户 | `GET/POST /api/v1/platform/organizations` |
| Project | 租户 | `GET/POST /api/v1/platform/projects` |
| User | 租户 | `GET/POST /api/v1/platform/users` |
| Role | 租户 | `GET/POST /api/v1/platform/roles` |
| Membership | 项目 | `GET/POST /api/v1/platform/memberships` |
| Service Account | 项目 | `GET/POST /api/v1/platform/service-accounts` |
| API Key | 项目 | `GET /api/v1/platform/api-keys`、`POST .../service-accounts/{id}/api-keys`、`POST .../api-keys/{id}/revoke` |
| Product Entitlement | 项目 | `GET/POST /api/v1/platform/product-entitlements`、`PUT /api/v1/platform/product-entitlements/{product_id}` |

`GET /api/v1/platform/iam/summary` 返回当前租户和项目可见的 IAM 库存。`GET /api/v1/platform/access-foundation` 返回认证模式、当前身份来源、策略提供者和各访问能力的成熟度。

## 认证与授权

生产认证开启后支持两类 Bearer 凭据：

- 平台根令牌来自 `SCENARA_API_TOKEN`，用于首次引导和平台级管理。租户与项目由经过校验的请求头选择。
- 服务账号 API Key 绑定唯一租户、项目和服务账号。租户、项目、主体 ID、scope 与产品范围都从凭据派生，调用方不能通过请求头覆盖。

服务 scope 使用 `resource:action` 形式。`iam:read` 允许读取 IAM；`iam:*` 允许管理 IAM；`*` 代表全局管理。现有服务仍调用共享策略提供者，API Key scope 是策略提供者之前的附加收窄层，不会扩大企业许可证或策略提供者授予的权限。

服务账号签发子 Key 时，子 Key 的 scope 和产品范围必须被账号配置覆盖；`*` 和 `resource:*` 按通配语义向下授权。密钥只在创建响应中返回一次，存储层仅持久化 SHA-256 摘要和非敏感前缀。被撤销、已过期、所属账号停用或上下文不匹配的 Key 不能认证；每次成功使用会更新 `last_used_at`。

服务凭据的有效产品集合是“服务账号产品 ∩ API Key 产品 ∩ 当前项目启用的 Product Entitlement”。共享策略把媒体、运行、流水线和人像映射到 `parse`，反馈与难例映射到 `data`，模型包与模型发布映射到 `model`，IAM 与企业资源映射到 `console`，Webhook 资源映射到 `api`。暂停项目授权会立即让现有服务凭据失去对应产品访问；恢复后无需重新签发 Key。

## 存储与审计

开发配置使用进程内仓库，PostgreSQL 配置通过 `0002_access_foundation.sql` 创建 `scenara_organizations`、`scenara_projects`、`scenara_users`、`scenara_roles`、`scenara_memberships`、`scenara_service_accounts`、`scenara_api_keys` 和 `scenara_product_entitlements`。所有 IAM 写操作写入平台审计日志。

Console 的“接入”工作区提供资源库存、组织项目、用户角色、项目成员、服务账号、API Key、产品授权、事件回调和浏览器连接管理。Python 与 TypeScript SDK 提供对应的强类型高层方法。

## 后续门禁

以下能力没有由当前底座虚构为已完成：

- 交互式用户会话及 OIDC、SAML、SCIM 身份联邦；
- 登录时解析 Membership 和 Role，并生成用户的有效 scope；
- 新产品模块资源映射的自动注册与契约门禁；
- 配额、套餐、席位、账单和自助购买；
- 用户、项目和服务账号的停用、删除、恢复及审批工作流；
- 集中审计搜索、导出审批和保留策略控制。

这些门禁应在共享底座上继续演进，不能在各产品模块中各自复制身份或授权系统。
