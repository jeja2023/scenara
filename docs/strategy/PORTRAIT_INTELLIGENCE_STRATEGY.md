# Scenara 人像智能基础平台长期战略

适用版本：`0.3.0-dev.26`。本文是景枢人像 AI 方向的长期技术战略，定义平台演进目标、六大核心模块、三项核心资产以及各阶段的门禁与现状差距。本文是战略意图文件，不是已发布能力清单。能力成熟度以 `model-capabilities.yml` 和 [实现矩阵](../release/IMPLEMENTATION_MATRIX.md) 为准。

---

## 战略定位

景枢的长期定位不是“人脸识别平台”，而是：

> **Portrait Intelligence Foundation Platform（人像智能基础平台）**
> ——为企业私有化场景持续积累可演进的人像 AI 基础设施，而不只是交付若干识别模型。

这一定位的根本区别在于：识别模型是边界固定的点状能力，基础平台是随数据、标注和反馈持续成长的资产体系。前者交付一次即停止增值，后者每一轮业务运行都在扩大自身资产。

当前平台骨架（`scenara` 集成仓库）已提供正确的分层基础：媒体/运行/流水线契约、模型准入状态机、特征存储抽象、反馈与难例导出、跨仓库契约体系。长期战略在此基础上纵向深化。

---

## 六大核心模块

### 模块总览

| 模块 | 推荐开源方案 | 战略价值 | 当前状态 |
| --- | --- | --- | --- |
| 数据治理 | FiftyOne · LakeFS · DVC | 建立高质量、可追溯的数据资产 | 🟡 Core 已具备远程接入、迁移和契约；Data 原生治理工具未建设 |
| 标注平台 | CVAT · Label Studio | 支持图像、视频、多模态标注闭环 | 🟡 Core 已具备远程接入与任务契约；工具集成未建设 |
| 模型训练 | OpenMMLab · PyTorch Lightning | 统一训练框架，覆盖检测/识别/姿态等任务 | 🟡 平台侧契约就绪，训练侧在 `scenara-model` 独立仓库 |
| 人像算法 | InsightFace · SCRFD · RTMPose · FastReID | 构建完整人像 AI 能力矩阵 | 🟡 7 项中 2 项就绪，4 项 fallback，1 项 placeholder |
| 向量检索 | Milvus · Qdrant | 支撑海量人像检索、聚类和跨摄像头关联 | 🟡 pgvector/Qdrant 适配器已实现；Milvus 未建；真实 Qdrant 资格待验收 |
| MLOps | MLflow · Triton · Kubernetes | 实现模型生命周期管理与持续迭代 | 🟡 MLflow/Triton HTTP 边界和自动回滚已实现；真实集群与 K8s 资格待验收 |

---

### 1. 数据治理

**目标**：建立高质量、版本化、血缘完整的人像训练与评估数据资产。

**工具选型**：

- FiftyOne — 数据集可视化、质量检测与难例发现
- LakeFS — 数据集版本控制（Git 语义，支持不可变快照）
- DVC — 训练数据与模型制品的版本绑定

**关键能力**：

- 数据集版本不可变，每次训练绑定到唯一 `DatasetVersionReference`（含 SHA-256）
- 质量标签体系：分辨率、遮挡、角度、光照、姿态置信度
- 标注血缘：从原始媒体 → 标注 → 训练集 → 模型制品全链路可追溯
- Embedding 版本管理：特征空间升级时保留历史向量的迁移路径

**平台侧已有**：`HardSampleManifest` 和 `DatasetVersionReference` 契约（[contracts/repository/v1.0.0/](../../contracts/repository/v1.0.0/)）；Core 的远程 Data 客户端、带校验和的迁移导出和切流门禁（见 [Data 切流操作说明](./DATA_PLATFORM_CUTOVER.md)）。

**建设门禁**：独立 `scenara-data` 服务必须在自己的持久化边界中完成导入、备份恢复、数据质量和授权职责；正式切流前通过仓库拓扑和 Data 切流文档定义的兼容、幂等、影子读和回滚门禁。

---

### 2. 标注平台

**目标**：支持图像、视频、实时流截帧的人工标注与质量复核，实现难例闭环。

**工具选型**：

- CVAT — 面向检测/关键点/ReID 的专业图像/视频标注
- Label Studio — 多模态标注与人工审核流程

**关键能力**：

- 检测框、人体关键点、属性标签的标注工作流
- 与平台反馈系统（`POST /api/v1/feedback`）的双向同步
- 难例导出：平台审批 → `HardSampleManifest` → 标注入队 → 复核 → 版本化数据集
- 标注质量门禁：标注一致性分数、复核比例门禁

**平台侧已有**：反馈采集、难例导出契约、`scenara-data` 消费方接口定义。标注工具集成属于 `scenara-data` 仓库职责。

---

### 3. 模型训练

**目标**：在 `scenara-model` 专业仓库中建立统一的训练框架，覆盖人像全任务，产出不可变制品后经平台准入进入生产。

**工具选型**：

- OpenMMLab（MMDetection · MMPose · MMTracking）— 检测、姿态、追踪任务
- PyTorch Lightning — 统一训练循环、混合精度、实验可重现性
- MLflow — 实验跟踪、指标对比、模型版本记录

**关键能力**：

- 单一训练骨干覆盖检测/识别/属性/姿态/ReID 多任务（初期可多模型并行，中期向共享骨干演进）
- 训练配置与数据集版本绑定（`DatasetVersionReference` SHA-256）
- 模型卡自动生成：任务、指标、训练集版本、评估证据、硬件环境
- 不可变制品生成：ONNX 导出 + SHA-256 + 模型卡，通过 `ModelPackageManifest` 提交平台准入

**平台侧已有**：模型准入 API（`POST /api/v1/model-packages/admissions`）、发布状态机（`candidate → validated → approved → active → retired`）、`ModelDeploymentEvent` Webhook（[仓库拓扑](./REPOSITORY_TOPOLOGY.md)）。

**责任边界**：训练作业、实验跟踪、训练算力调度在 `scenara-model`；平台侧只做准入验证、发布治理和运行时激活/回滚。跨仓库只通过版本化契约通信，禁止共享数据库。

---

### 4. 人像算法

**目标**：将 `model-capabilities.yml` 中全部 7 项能力从 fallback/placeholder 升级为 ready，构建完整人像 AI 能力矩阵。

**当前能力矩阵**：

| 能力 | 当前状态 | 当前模型 | 目标模型 | 目标 Embedding 维度 |
| --- | --- | --- | --- | --- |
| `person_detection` | ✅ ready | YOLOv8n ONNX | 同（可升至 SCRFD-Person） | — |
| `body_embedding` (ReID) | ✅ ready | OSNet IBN 512-dim | FastReID / MGN | 512 |
| `face_detection` | ⚠️ fallback | Haar cascade | SCRFD 10GF ONNX | — |
| `face_embedding` | ⚠️ fallback | 图像指纹 64-dim | ArcFace R100 / InsightFace ONNX | 512 |
| `pose` | ❌ placeholder | 几何占位符 | RTMPose-m ONNX | — |
| `gait` | ⚠️ fallback | 轨迹指纹 64-dim | OpenGait / Gait3D ONNX | 256 |
| `appearance` | ⚠️ fallback | 颜色直方图 64-dim | 人体属性解析 ONNX | 256 |

**优先级**：face_detection + face_embedding 是 1.0 的最低门槛（SCRFD + ArcFace ONNX 制品）；pose 和 gait 是 1.1 目标；appearance 与多模态融合检索绑定。

**制品要求**：所有生产模型必须以 SHA-256 不可变引用提交 `ModelPackageManifest`，通过平台准入状态机后方可激活。开发 fallback 制品不得出现在任何面向外部的能力声明中。

---

### 5. 向量检索

**目标**：支撑海量人像库的高速 ANN 检索、跨摄像头关联和实时聚类。

**工具选型**：

- pgvector — 千万级以下规模的默认后端，随 PostgreSQL 一体部署
- Qdrant — 中大规模场景的候选后端，`scenara/infrastructure/qdrant_features.py` 已实现 `FeatureStore` HTTP 适配器
- Milvus — 超大规模或多模态混合检索场景

**平台侧已有**：

- `FeatureStore` Protocol（[scenara/platform/features.py](../../scenara/platform/features.py)）：定义完整接口（`create_space / add / search / delete_subject / delete_expired`），支持 cosine / L2 / inner_product
- 内存实现（开发模式）和 pgvector 实现（生产模式）
- `FeatureSpace` 多维度空间：按 `domain` / `modality` / `model_id` / `model_version` 隔离，支持特征空间升级而不污染历史数据

**演进路径**：

1. 当前：pgvector 覆盖 1.0 单节点场景；Qdrant provider 已可通过配置切换
2. 中期：完成 Qdrant 真实服务兼容性、容量、备份恢复和租户隔离验收
3. 长期：按规模选型，`FeatureStore` 抽象层保证上层代码零修改切换后端

**聚类与关联能力**：跨摄像头 Re-ID 长期轨迹与时间线关联已在 Portrait Intelligence Engine 层实现（`scenara/domains/portrait/trajectory.py`），不在 `FeatureStore` 层实现；无监督全库聚类与身份图谱仍在规划中。

---

### 6. MLOps

**目标**：实现模型从实验 → 训练 → 准入 → 部署 → 监控 → 反馈的完整生命周期管理，并支持持续迭代。

**工具选型**：

- MLflow — 训练实验跟踪、指标对比、模型版本记录（`scenara-model` 侧）
- Triton Inference Server — 高吞吐、低延迟的生产推理服务，支持 ONNX / TensorRT 动态批处理
- Kubernetes — 推理服务的水平自动扩缩（HPA）、多 GPU 调度和滚动发布

**平台侧已有**：

- 模型发布状态机（`candidate → validated → approved → active → retired`）
- `ModelDeploymentEvent` 审计与 Webhook 投递
- 按租户/项目的模型激活/回滚与 Run 绑定冻结
- 生产配置失败关闭门禁（`scenara/settings.py`）

**缺失项**：

- Triton 推理服务集成边界（当前默认仍为 ONNXRuntime 直接推理；真实服务资格待验收）
- K8s 目标集群兼容性、HPA 压测和滚动发布证据（清单与 HPA 已提供）
- 实时推理延迟/吞吐监控与告警的目标集群接入
- 目标集群告警编排与模型性能退化证据

**建设顺序**：1.0 以 ONNXRuntime 单节点为基线；1.1 接入 Triton 提升并发；2.0 建设 K8s 水平扩缩。Kubernetes 和多节点 HA 不属于 1.0 正式支持范围。

---

## 三项核心资产

以上六个模块最终沉淀为三项不可替代的平台资产：

### Portrait Data Lake（人像数据湖）

统一管理所有原始媒体、标注结果、Embedding、质量标签和版本血缘。

**核心特征**：

- 数据版本不可变，每个版本有唯一标识和 SHA-256
- 训练数据与模型制品双向绑定，缺任何一方都无法通过准入
- 质量门禁：分辨率、标注一致性、数据分布自动检验
- 难例闭环：平台运行结果 → 反馈 → 审批 → 标注 → 数据湖 → 训练

**当前状态**：Core 已完成 `HardSampleManifest` 远程交接、`DatasetVersionReference` 查询入口和可校验迁移包；数据湖本体、版本管理工具链、质量标签体系仍由独立 Data 服务建设并在切流验收后承担。

---

### Portrait Foundation Model（人像基础模型）

持续训练覆盖检测、人脸识别、属性、姿态、ReID、步态等多任务的大模型，而不是维护多个割裂的小模型。

**演进路径**：

- **阶段一（当前 → 1.0）**：独立小模型，各任务分别就绪（SCRFD、ArcFace、RTMPose、OSNet、OpenGait）
- **阶段二（1.x）**：共享骨干网络（如 ViT-B 或 ResNet50），多任务 head 共享低层特征，减少重复推理开销
- **阶段三（2.x+）**：统一多任务基础模型，支持持续增量训练，新数据接入后无需全量重训

**当前状态**：约 0%。多任务统一骨干在架构设计阶段。当前 7 项能力中 2 项就绪，5 项为 fallback/placeholder。

---

### Portrait Intelligence Engine（人像智能引擎）

将检索、聚类、知识图谱、事件分析和持续学习融合，形成可持续演进的平台能力。

**核心组件**：

- **跨摄像头 Re-ID 引擎**（已实现）：基于 body_embedding + face_embedding 的多模态融合检索，face 证据优先于 body；叠加摄像头拓扑最短转移时间与同帧互斥约束
- **长期轨迹与时间线**（已实现）：以真实媒体时间轴（`recording_started_at` + `pts_ms`）落片段，输出按时间排序的跨机位出现序列与转移间隔
- **人工闭环**（已实现）：确认 / 否决 / 命名 / 合并 / 拆分 / 连带生物特征删除，全部进审计
- **人像聚类服务**（规划）：无监督全库聚类 + 人工确认，形成身份图谱节点
- **事件分析**（规划）：行为序列识别、跨场景出现分析
- **持续学习**（规划）：难例自动触发重训，模型性能退化自动检测与版本回滚

**当前状态**：约 35%。向量检索（pgvector）提供基础检索能力；跨摄像头 Re-ID 长期轨迹、多模态融合、时空约束与人工闭环已落地；全库聚类、知识图谱、行为事件分析、持续学习未建设。

---

## 现状差距评估

本节记录截至 `0.3.0-dev.6` 的实际差距，随版本迭代更新。

```text
数据治理       ░░░░░░░░░░  ~5%   契约 Schema 已有，工具链空白
标注平台       ░░░░░░░░░░  ~3%   难例导出已有，标注工具未集成
模型训练       ████░░░░░░  ~40%  平台侧契约就绪；训练侧状态在 scenara-model
人像算法       ██░░░░░░░░  ~25%  2/7 能力 ready；5 项 fallback/placeholder
向量检索       ████░░░░░░  ~45%  pgvector/Qdrant 适配器可用；真实集群资格未解
MLOps         ███░░░░░░░  ~30%  Triton/MLflow HTTP 边界和自动回滚已实现；集群资格未解

Data Lake      ░░░░░░░░░░  ~3%
Foundation Model ░░░░░░░  ~0%
Intelligence Engine █░░░  ~10%
```

**综合评估**：平台底座（IAM、媒体契约、模型准入状态机、特征存储抽象）已基本到位，这是正确的建设顺序。当前最紧迫的缺口是**人像算法模型制品**——在 SCRFD + ArcFace ONNX 就绪之前，平台无法对外宣称具备完整人像识别能力。数据治理和 Foundation Model 是 1.0 之后的建设目标，按 [产品矩阵](./PRODUCT_MATRIX.md) 的升级原则推进。

---

## 分阶段建设路径

### 阶段 0 → 1.0：人像算法制品就绪（最高优先级）

**目标**：`model-capabilities.yml` 中所有 `fallback` 和 `placeholder` 能力替换为正式 ONNX 制品，通过平台准入。

| 任务 | 制品 | 状态目标 |
| --- | --- | --- |
| 人脸检测 | SCRFD-10GF ONNX + 模型卡 + SHA-256 | fallback → ready |
| 人脸识别 | ArcFace R100 / InsightFace ONNX | fallback → ready |
| 姿态估计 | RTMPose-m ONNX (coco17 keypoints) | placeholder → ready |
| 步态识别 | OpenGait / Gait3D ONNX | fallback → ready |
| 外观属性 | 人体属性解析 ONNX | fallback → ready |

**平台侧配合**：无需修改准入流程；`scenara-model` 仓库按 `ModelPackageManifest` 规范提交制品，平台走现有状态机。

---

### 阶段 1.0 → 1.1：MLOps 与向量检索强化

**目标**：生产推理服务能力提升，并在新平台架构中实现 Qdrant 后端。

- Qdrant `FeatureStore` 适配器已落地；在真实 Qdrant 集群完成兼容性、容量、备份恢复和租户隔离验收
- Triton Inference Server HTTP 适配器已实现；真实部署后替换 ONNXRuntime 直推路径
- MLflow REST 记录器已实现，`ModelPackageManifest` 可绑定实验 Run
- 多模态融合检索：face + body embedding 联合评分

---

### 阶段 1.1 → 2.0：数据治理与标注平台

**触发条件**：独立 `scenara-data` 服务完成迁移导入、影子读、备份恢复、Hard Sample 幂等接收和回滚演练（见 [Data 切流操作说明](./DATA_PLATFORM_CUTOVER.md)）。

- 部署并验收 `scenara-data` 独立服务，接入 FiftyOne 数据集可视化
- LakeFS 数据集版本管理，与 `DatasetVersionReference` 契约对接
- CVAT / Label Studio 标注工作流，与平台反馈导出闭环
- DVC 训练数据与模型制品双向版本绑定

---

### 阶段 2.0+：Portrait Foundation Model 与 Intelligence Engine

**触发条件**：数据治理成熟、多任务制品稳定、持续训练体系建立。

- 共享骨干多任务模型训练，统一 face / body / pose / attribute 低层特征
- 无监督全库人像聚类服务（跨摄像头 Re-ID 长期轨迹已在 1.0 落地）
- 人像知识图谱（身份节点、时空关联、行为事件）
- 持续学习：难例驱动的增量训练与模型版本自动管理
- K8s 水平扩缩与多 GPU 调度（2.0 正式支持范围）

---

## 不做的事

以下内容明确不属于本战略路线，防止范围蔓延：

- 通用目标检测（非人像场景）
- 消费级 SaaS 或公共云 API
- 超出私有化部署边界的数据出境
- 跨仓库共享数据库或源码导入
- 把规划阶段能力在发布说明或 Console 中展示为已发布

---

## 与现有架构文件的关系

| 文件 | 与本文的关系 |
| --- | --- |
| [产品矩阵](./PRODUCT_MATRIX.md) | 产品模块状态与升级原则，本文的 AI 战略是其中 Model / Data / Parse 模块的深化 |
| [仓库拓扑](./REPOSITORY_TOPOLOGY.md) | 三仓库分工与跨仓库契约，本文遵从其边界约束 |
| [访问底座](./ACCESS_FOUNDATION.md) | IAM 与认证体系，本文所有产品模块共享 |
| [实现矩阵](../release/IMPLEMENTATION_MATRIX.md) | 能力成熟度实时状态，优先级高于本文的定性描述 |

本文描述“景枢应当成为什么”；上述文件描述“当前已经是什么”。两者不矛盾，但以上述文件为准时以它们为准。

---

## 可执行契约

本文的六大模块、三项资产与七项能力就绪度已成为版本化平台契约，不再只是文档描述。

`GET /api/v1/platform/portrait-intelligence` 返回 `PortraitIntelligenceStatus`，当前结构版本为 `1.0`。响应包含三部分：

- `modules` — 六个战略模块，每项声明 `maturity`、`owner_repository_id`、`current_scope`、`not_in_scope_yet` 与 `next_gate`。`owner_repository_id` 与[仓库拓扑](./REPOSITORY_TOPOLOGY.md)一致：数据治理与标注平台归 `scenara-data`，模型训练与人像算法制品归 `scenara-model`，向量检索与模型运维归 `scenara`。
- `assets` — 三项战略资产，`depends_on_modules` 声明其依赖的模块，由契约校验器保证引用完整。
- `capabilities` — 七项人像能力的就绪度，从平台安装的 `model-capabilities.yml` 实时派生，不在契约层硬编码。

成熟度使用五值枚举：`available`、`partial`、`seed`、`planned`、`external`。`external` 表示职责在其他仓库，平台如实记录差距而不隐藏模块。能力就绪度使用 `ready`、`fallback`、`placeholder`、`not_configured`，与 `model-capabilities.yml` 的 `status` 字段一一对应。

Python SDK 使用 `get_portrait_intelligence()`，TypeScript SDK 使用 `getPortraitIntelligence()`。Console 总览从该接口读取并在“人像智能基础平台”面板展示，所有面向用户的模块名、资产名、能力名、成熟度与门禁说明均通过 `labels.ts` 转为中文，服务端契约保持英文字段。

契约构建器 `scenara/platform/portrait_intelligence.py` 是纯函数，能力快照由调用方注入，因此 `scenara/platform` 不导入 `app.*`，符合 `tests/test_architecture.py` 的架构边界约束。修改模块归属或能力清单时，必须同时更新构建器、OpenAPI、两个 SDK、Console 标签层与契约测试。

该接口是本文的机器可读事实来源；本文件解释其战略意图。接口反映当前成熟度与差距，不代表已部署的模型质量——推理时的权威能力状态始终以 `model-capabilities.yml` 为准。
## 0.3.0-dev.10 已落地的索引、比对与治理闭环

本版本完成了人像比对从“调用方提交向量”到“图片输入、模型编码、特征空间校验、身份/图片搜索、审计和删除”的完整闭环。`PortraitImageEncoder` 是领域适配边界，生产模式没有人脸时会拒绝请求，开发模式的图像指纹 fallback 会在响应和审计证据中明确标记。

平台新增 `IndexStore` 契约：`IndexDefinition` 固化域、记录类型、向量维度、模型版本、距离度量和阈值；`IndexRecord` 通过 `IndexSourceRef` 绑定租户、项目、资产、运行、单元、对象、页码和时间戳。身份注册写入 `portrait.identity.<feature_space>`，解析结果写入 `result.<domain>`，旧向量接口继续兼容但不再是唯一入口。

公开索引记录只返回脱敏投影，原始向量不会进入 API、Console 或 SDK 返回值。重跑、身份删除、资产删除和过期清理都使用软删除语义，结果索引失败会将结果摘要标记为 `partial`。

The non-model platform work is now represented by first-class annotation-provider, index-backend, and reranker adapter registries with auditable health probes. These registries define the integration boundary for CVAT/Label Studio, ANN stores, and semantic reranking without claiming that a licensed model or external service is installed.
