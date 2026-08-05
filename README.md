# Scenara 景枢

Scenara 是面向企业私有化部署的视觉 AI 中枢平台。平台以版本化数据资产、Run、Pipeline 和 Result 契约接收图片、视频、PDF 与实时流，并通过可安装的 Domain 提供强类型视觉能力。

当前产品阶段：`0.3.0-dev.12`（Python 包版本为 `0.3.0.dev12`）

- 正式领域：Portrait（迁移中）
- 验证领域：OCR / Document
- 正式部署基线：Ubuntu x86_64、Docker Compose、NVIDIA GPU、PostgreSQL/pgvector、Redis、S3/MinIO
- 开发模式：本地对象存储、进程内状态与显式标记的开发适配器

> Scenara 尚未发布 1.0。缺少合法模型制品、固定评估集、目标 GPU 容量报告或恢复证据时，不得宣称对应能力可用于正式生产。

## 产品矩阵与访问底座

Scenara 作为平台母品牌，统一规划 Parse、Model、Data、Edge、Flow、Search、Agent、Console、API、SDK 与 Index。当前并非 11 套独立系统：Console、API 和 SDK 是共享入口，Index 是共享底座，产品模块继续复用同一平台内核、IAM、授权、审计和部署栈。

当前版本已提供产品目录、仓库拓扑、正式跨仓库契约、Organization、Project、User、Role、Membership、Service Account、API Key 与 Product Entitlement，并支持平台根令牌、按项目绑定的服务账号 API Key 以及用户名密码登录。完整成熟度、依赖顺序与非目标见 [产品矩阵](docs/strategy/PRODUCT_MATRIX.md)，当前仓库与独立 Model/Data 仓库的分工见 [仓库拓扑](docs/strategy/REPOSITORY_TOPOLOGY.md)，四条可发布契约见 [契约包](contracts/repository/README.md)，认证和授权边界见 [访问底座](docs/strategy/ACCESS_FOUNDATION.md)，人像 AI 长期演进方向见 [人像智能基础平台战略](docs/strategy/PORTRAIT_INTELLIGENCE_STRATEGY.md)，升级影响见 [0.3.0-dev.12 开发版发布说明](docs/release/0.3.0-dev.12.md)。

解析控制台采用“解析 -> 领域”的工作区结构，人像和 OCR 文档分别进入独立领域页面；图片、视频、文档和视频流是页面内部的数据类型标签，例如 `parse/portrait/image` 与 `parse/ocr/document` 仍可作为深链路访问。每个领域工作区内完成上传、参数配置、运行进度、当前结果查看与历史恢复；“数据资产”和“运行”页面分别承担文件/视频流来源管理与运行生命周期管理，新增的“解析结果”页面负责跨领域、跨任务浏览和筛选结果。领域菜单由后端 `DomainManifest` 驱动，新领域接入时不需要重新拆分前端解析流程。

## 架构

```mermaid
flowchart LR
    C["Client / Console"] --> A["Scenara API"]
    A --> M["Data Assets"]
    A --> R["Run Service"]
    M --> R
    R --> P["Pipeline Engine"]
    P --> O["Typed Operators"]
    O --> D1["Portrait Domain"]
    O --> D2["OCR Domain"]
    O --> MR["Model Runtime"]
    D1 --> F["Feature Store"]
    D1 --> RI["Result Index"]
    D2 --> RI
    RI --> RS["Result Store"]
```

依赖规则：`platform` 不导入具体 Domain；Domain 只实现平台契约；`infrastructure` 只实现平台端口；可选 Enterprise Module 通过 Policy Hook 接入。

## 本地启动

```powershell
python -m pip install -r requirements/dev.txt
Copy-Item .env.example .env
python scripts/prepare_runtime_state.py
python -m uvicorn scenara.server:app --host 127.0.0.1 --port 8000 --env-file .env
```

本地运行时的持久化状态和 rollout 审计默认写入 `runtime-state/`，可保留的日志文件放在
`runtime-state/logs/`；生产部署继续将应用日志输出到 stdout，由容器运行时统一采集。

`.env.example` 已按运行模式、认证、资源限制、模型与加密、网络安全、数据保留、运行产物和生产后端分组提供中文说明。本地首次登录需同时设置 `SCENARA_BOOTSTRAP_ADMIN_USERNAME` 与 `SCENARA_BOOTSTRAP_ADMIN_PASSWORD`，密码长度不得少于 12 个字符；真实 `.env` 已被 Git 忽略，不得提交密码、根令牌或加密密钥。

前端构建完成后，服务会在 `http://127.0.0.1:8000/console/` 提供同版本中文控制台；根路径会自动跳转到该地址。

存活探针：`GET /livez`；依赖就绪探针：`GET /readyz`；兼容探针：`GET /healthz`。经接口认证的 Prometheus 指标位于 `GET /metrics`。新公共契约统一位于 `/api/v1`，旧 Portrait Hub `/v1` 契约不属于 Scenara。

生产镜像和离线轮子只使用带 SHA-256 的 `requirements/production.lock`。修改 `requirements.txt` 或 `requirements/prod-optional.txt` 后，运行 `uv pip compile requirements/production.in --python-version 3.12 --python-platform x86_64-manylinux_2_28 --generate-hashes --no-emit-index-url --output-file requirements/production.lock` 并提交锁文件。

## 仓库边界

本仓库是 Scenara 平台集成仓库，不单独改名为 Scenara Parse。Scenara Parse、Console、API、SDK 及共享平台底座在此统一演进；已有模型训练仓库独立承担 Scenara Model 的训练生产，未来 Scenara Data 在数据集治理门禁成熟后独立建仓。模型准入、发布、部署、回滚以及业务反馈与难例导出仍由本仓库治理，跨仓库禁止共享数据库和源码导入。

模型闭环从 `POST /api/v1/model-packages/admissions` 接收带不可变 SHA-256 引用的正式清单，经证据验证进入发布状态机。激活或回滚按租户、项目和能力切换唯一运行时绑定；每个 Run 在开始时冻结该绑定并写入结果来源。部署状态变化同时持久化为 `ModelDeploymentEvent`，并通过 `model.deployment.changed` Webhook 投递回训练仓库。契约目录由 `GET /api/v1/platform/contracts` 暴露。

`app/` 是从 Portrait Hub 筛选导入的迁移适配层，只能被 `scenara.domains.portrait` 使用。新平台能力必须进入 `scenara/`，不得继续向 `app/portrait_*` 增加通用平台职责。

来源与筛选规则见 [PROVENANCE.md](PROVENANCE.md)，品牌规范见 [docs/brand/BRAND.md](docs/brand/BRAND.md)，模型资产政策见 [MODEL_ASSETS.md](MODEL_ASSETS.md)，升级、回滚、探针和告警见 [deploy/OPERATIONS.md](deploy/OPERATIONS.md)，版本变更见 [更新日志.md](更新日志.md)。

## 授权

源码公开不代表开源授权。除第三方组件另有声明外，本仓库使用 [Scenara Proprietary Source License](LICENSE)。
Current release baseline: `0.3.0-dev.12` (`0.3.0.dev12` for Python packages).
