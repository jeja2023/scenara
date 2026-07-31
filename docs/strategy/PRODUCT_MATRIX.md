# Scenara 产品矩阵

适用版本：`0.3.0-dev.2`。本文是产品边界和演进顺序的权威说明，不是所有产品均已发布的销售清单。

Scenara 是平台母品牌。长期产品矩阵采用三层边界：产品模块、共享入口和底层 AI 数据底座。`Console`、`API`、`SDK` 不作为重复建设的业务产品，而作为所有产品模块共享的控制面和开发者入口。

## 目录边界

| 层级 | 名称 | 当前定位 | 状态 |
| --- | --- | --- | --- |
| 产品模块 | Scenara Parse | 视觉解析平台，承载媒体、运行、流水线和结构化视觉结果 | 可用，仍受 1.0 生产证据门禁约束 |
| 产品模块 | Scenara Model | 模型包准入、发布、回滚、部署事件和证据追踪 | 种子能力，不包含训练作业 |
| 产品模块 | Scenara Data | 媒体、特征、反馈和 Hard Sample Manifest 数据闭环 | 种子能力，还不是完整 Data Hub |
| 产品模块 | Scenara Edge | 边缘推理、设备、离线同步和远程下发 | 门禁中 |
| 产品模块 | Scenara Flow | 运行编排、人工审核和流程自动化 | 规划中 |
| 产品模块 | Scenara Search | 跨媒体、跨文档和跨索引检索 | 规划中 |
| 产品模块 | Scenara Agent | 可审计的智能动作编排 | 门禁中 |
| 共享控制面 | Scenara Console | 平台管理中心和所有产品模块的统一界面 | 可用 |
| 开发者平台 | Scenara API | 版本化开放能力契约 | 可用 |
| 开发者平台 | Scenara SDK | Python 与 TypeScript 集成入口 | 可用 |
| 底层底座 | Scenara Index | 特征、向量和未来通用索引资源 | 种子能力 |

## 升级原则

- 先完成 Scenara 1.0 的合法模型、固定评估集、目标 GPU、离线安装、备份恢复和签署证据。
- 在拆分产品前，先建设共享 IAM、组织、项目、角色、服务账号、API Key、权限范围、授权、配额、审计和产品目录。
- `Model` 近期只做模型治理和训练平台契约，不把训练作业、实验跟踪、标注系统直接并入当前仓库。
- `Data` 先把反馈、难例和数据授权闭环做实，再升级为完整 Data Hub。
- `Index` 先成为稳定底座，再支撑 `Search`；`Flow` 和 `Search` 稳定后再启动 `Agent`。
- `Edge` 等 1.0 服务端部署和证据闭环稳定后再启动，避免同时复制 UI、权限、部署和运维工作。

## 仓库契约

产品矩阵通过 `GET /api/v1/platform/products` 暴露。该接口返回产品名称、层级、成熟度、当前范围、尚未纳入范围、Console 路由、API 路径、依赖关系和下一道门禁。

仓库拓扑通过 `GET /api/v1/platform/repositories` 暴露。当前 `scenara` 是平台集成仓库，已有模型训练仓库映射为 `scenara-model` 专业仓库，`scenara-data` 处于规划拆分状态。拓扑契约同时公开职责、排除职责、跨仓库清单/API/事件和禁止共享数据库、禁止跨仓库源码导入等强制规则。四条正式跨仓库契约由 `GET /api/v1/platform/contracts` 和 `contracts/repository/v1.0.0/` 发布，并由 Schema 摘要、有效示例和向后兼容门禁保护。

这份目录是战略边界，不代表所有条目已经可生产使用。`available` 表示仓库已有可使用能力；`seed` 表示已有基础闭环但尚未独立产品化；`planned` 表示规划中；`gated` 表示必须等待前置证据或前置产品稳定。

访问控制底座通过 `GET /api/v1/platform/access-foundation` 暴露；IAM 库存通过 `GET /api/v1/platform/iam/summary` 暴露。组织、项目、用户、角色、项目成员、服务账号、API Key 和项目产品授权均已成为一等资源，并由内存或 PostgreSQL 后端持久化。Console、Python SDK、TypeScript SDK 与 OpenAPI 共享同一组 `/api/v1/platform/*` 契约。

当前身份底座支持平台根令牌和按项目绑定的服务账号 API Key。API Key 只在签发时返回一次，服务端仅保存 SHA-256 摘要；子 Key 的 scope 和产品范围不得超过服务账号，撤销、过期、账号停用和租户/项目不匹配都会拒绝认证。项目产品授权可暂停和恢复，媒体、运行、流水线、模型、反馈、Webhooks、企业工作区与 IAM 资源均在共享策略边界执行产品检查。交互式用户登录、OIDC/SAML/SCIM、角色绑定登录时解析和计费套餐仍属于后续门禁，不应由现有 IAM 资源状态推断为已经完成。

详细仓库职责见 [`REPOSITORY_TOPOLOGY.md`](./REPOSITORY_TOPOLOGY.md)，认证与安全边界见 [`ACCESS_FOUNDATION.md`](./ACCESS_FOUNDATION.md)。

Parse、Model、Data 三个模块在人像方向的长期演进目标、六大能力模块与三项核心资产见 [`PORTRAIT_INTELLIGENCE_STRATEGY.md`](./PORTRAIT_INTELLIGENCE_STRATEGY.md)，其成熟度与能力就绪度通过 `GET /api/v1/platform/portrait-intelligence` 暴露。该契约是产品矩阵在人像领域的纵向深化，不新增产品条目。
