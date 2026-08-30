# Scenara 比对预警与布控功能研发计划

**文档版本**：v2.0（方案修订版）  
**当前代码基线**：`0.3.0-dev.35` / Python `0.3.0.dev35`  
**目标开发版本**：`0.3.0-dev.36`  
**模块归属**：`scenara.domains.portrait`、共享平台契约、`frontend/console`  
**文档定位**：本文定义目标比对、名单布控、实时预警和轨迹联动的产品边界、技术契约、研发阶段和验收门禁。本文是研发计划，不代表这些能力已经发布或具备生产资格。

---

## 一、现有基线与建设边界

### 1. 当前已经存在的基础能力

以下能力可以作为本功能的复用基础，但不能直接等同于“实时布控预警已实现”：

| 能力 | 当前实现 | 可复用方式 | 当前限制 |
| --- | --- | --- | --- |
| 人像身份与底库特征 | `PortraitIdentity`、`PortraitEnrollment`、`FeatureStore` | 名单成员引用已有身份和特征空间 | 不新增第二套人像身份主数据 |
| 向量检索 | `MemoryFeatureStore`、`PostgresFeatureStore`、Qdrant HTTP 适配器 | 按租户、项目、特征空间检索候选 | Qdrant 真实集群容量和隔离资格仍需单独验收 |
| 视频流运行 | `MediaSource`、Stream Session、分片 Run | 布控任务负责创建或管理指定 Source 的 Run | 当前默认按 5 分钟形成一个分片 Run |
| 中间结果 | `result.delta`、Run SSE | 告警评估使用中间观察批次，不等待整个流结束 | 当前事件是按 Run 查询，不是全局告警事件流 |
| 轨迹 | `TrajectoryService`、`TrajectoryRegistrar` | Alert 记录保存轨迹身份和片段引用 | 当前轨迹登记在结果处理阶段执行，失败不阻断 Run |
| 对象与抓拍 | `RunArtifactSink`、`ResultArtifact` | 优先引用已有 `unit_frame` / `object_crop` Artifact | Artifact 默认属于 Run Result，告警需要独立保留语义 |
| Webhook | `WebhookService`、Webhook Delivery Outbox | 复用签名、租户隔离、重试和死信机制 | 需要新增告警事件 Schema 和原子 Outbox 写入 |
| 反馈与难例 | `POST /api/v1/feedback`、`HardSampleManifest` | 研判完成后提交误报/低质量反馈 | 反馈必须经过授权、去标识化和审核后才能进入 Manifest |

### 2. 明确不在本计划内的内容

- 不复制 `PortraitIdentity`、`PortraitEnrollment` 或 FeatureStore，禁止建立独立的“布控身份库”。
- 不在 Core 内建设视频接入网关、摄像头厂商协议适配器或完整 GIS 平台；本计划只消费已注册的 `MediaSource` 和 `CameraRecord`。
- 不把 ArcFace、FastReID、Qdrant、Triton 或 GPU 的“已安装”写成生产资格；资格仍以模型准入、固定评估和目标硬件报告为准。
- 不把“黑名单/白名单”直接解释为告警行为。名单类别是业务标签，告警行为必须由任务的 `match_policy` 明确配置。
- 不把原始照片、身份证号、embedding 或带长期权限的公开 URL 放入告警 API、SSE 或 Webhook。

### 3. 建设目标

最终数据流应为：

```text
已注册 MediaSource + CameraRecord
        |
        v
SurveillanceTask / Binding / Schedule Supervisor
        |
        v
Stream Run -> Portrait observation batch -> Matcher -> Quality/Threshold gate
        |                                      |
        |                                      v
        |                               Debounce / Idempotency
        |                                      |
        v                                      v
Run Artifact snapshot ----------------> Alert transaction
                                             |
                         +-------------------+-------------------+
                         v                                       v
                  AlertRecord + AlertEvent                Webhook Outbox
                         |
                         v
                  Console SSE / History / Triage
                         |
                         v
             Trajectory reference / Feedback / Hard Sample
```

`triggered_at` 表示观察发生时间，`created_at` 表示告警记录持久化时间。两者必须分开，不能用处理时间冒充摄像头观察时间。

---

## 二、核心契约（先于业务开发冻结）

### 1. 身份、名单和成员关系

布控目标不是新的人像身份，而是名单与已有 `PortraitIdentity` 的关系。

#### `Watchlist`

- `tenant_id`, `project_id`, `watchlist_id`
- `name`, `category`: `blacklist` / `whitelist` / `custom`
- `description`, `status`: `active` / `paused` / `archived`
- `created_by`, `created_at`, `updated_at`, `revision`

#### `WatchlistMember`

- `tenant_id`, `project_id`, `watchlist_id`, `member_id`
- `portrait_identity_id`: 关联已有 `PortraitIdentity`
- `status`: `active` / `paused` / `removed`
- `display_label`: 可选的名单内展示名，不覆盖身份主档案
- `valid_from`, `valid_until`
- `created_by`, `created_at`, `updated_at`, `revision`

成员录入流程应优先采用两个已有动作：

1. 创建或查询 `PortraitIdentity`；
2. 通过 `/api/v1/portrait/identities/{identity_id}/enrollments/image` 完成人像图片提取和特征注册；
3. 将该身份加入 `WatchlistMember`。

可以在后续阶段提供批量便利接口，但便利接口必须编排上述同一套身份和特征服务，不能绕过模型版本、质量、租户隔离和审计。

身份证号不是 MVP 必填字段。若业务法规确实要求保存，应采用独立加密字段或外部引用，仅限授权主体读取；名单列表、告警、SSE、Webhook、审计证据均只返回脱敏值或不可逆引用。

### 2. 布控任务与摄像头绑定

#### `SurveillanceTask`

- `tenant_id`, `project_id`, `task_id`, `name`
- `status`: `draft` / `active` / `paused` / `expired` / `failed`
- `watchlist_ids`: 任务关联的名单库
- `bindings`: 每项包含 `source_id`、`camera_id`，禁止只保存无法启动 Run 的 `camera_id`
- `schedule`: 见下方时间契约
- `match_policy`: `alert_on_match` / `suppress_on_match` / `observe_only`
- `threshold_policy`: 按特征空间和模型版本声明的阈值策略
- `cooldown_seconds`: `1..86_400`，默认值需由容量和误报评估确定，开发默认可为 30 秒
- `alert_level`: `critical` / `warning` / `info`
- `created_by`, `created_at`, `updated_at`, `revision`

任务不能通过直接修改数据库生效。`active` 状态必须经过服务层校验：名单、成员、Source、Camera、模型/特征空间和权限均可用；启动、暂停、恢复必须是幂等操作。

#### Schedule 时间契约

```json
{
  "timezone": "Asia/Shanghai",
  "weekly": [
    {"weekday": 1, "start": "08:00", "end": "18:00"}
  ],
  "exceptions": [
    {"date": "2026-10-01", "enabled": false}
  ]
}
```

- `weekday` 使用 ISO 8601 的 `1..7`；时间段采用半开区间 `[start, end)`。
- `start == end` 不代表全天，全天必须显式写成 `00:00` 到 `24:00`。
- 服务端使用 IANA 时区计算本地时间，再转换为 UTC；夏令时产生的缺失或重复时间必须有固定处理规则并有测试。
- 任务未处于生效时间时不创建新 Run，也不产生告警；已经运行的流在策略变更后的边界行为必须记录在任务事件中。

### 3. 观察批次、Matcher 和分数语义

新增内部契约 `ObservationBatch`，不直接复用公开 `ResultEnvelope` 中的脱敏字段承载私有向量。至少包含：

- `run_id`, `source_id`, `camera_id`, `unit_id`, `track_id`
- `first_seen_at`, `last_seen_at`, `pts_ms`；无权威时间时标记 `timestamp_source`
- `feature_refs`: 各模态的内部 Feature 或临时向量引用
- `snapshot_artifact_id`: 已生成的 Run Artifact 引用，可为空
- `quality`: 检测、轨迹、脸部质量和遮挡等质量信息
- `model_bindings`: 每个模态的 `model_id`、`model_version`、`feature_space_id`

Matcher 的约束：

- 每次检索必须指定 `tenant_id`、`project_id`、`feature_space_id` 和 `limit`；不得依赖集合名作为安全边界。
- face、body 的相似度必须先按各自特征空间校准，再进行融合；不能默认把未经校准的两个 cosine 分数直接加权。
- 默认只输出候选，不直接生成告警。候选需同时通过成员状态、任务时间、质量门槛、模型版本和 `match_policy`。
- `threshold_face`、`threshold_body` 不再作为脱离模型版本的全局常数。任务保存的是阈值策略版本和可选覆盖值，默认值来自经固定评估验证的特征空间契约。
- 只有同时存在有效 face 和 body 证据时才执行融合；单模态结果必须记录 `modality` 和缺失原因。

### 4. Debounce、幂等和并发

频控状态必须跨进程、跨实例、可重启恢复。首选 Redis 原子脚本；没有 Redis 时使用 PostgreSQL 行级锁或原子 UPSERT，不能使用 Worker 本地字典作为生产实现。

逻辑键至少为：

```text
(tenant_id, project_id, task_id, binding_id, watchlist_id, portrait_identity_id)
```

同一目标在不同任务中默认独立频控；需要跨任务合并时必须显式配置去重组。频控状态至少保存：

- `first_seen_at`, `last_seen_at`, `last_alert_id`
- `occurrence_count`, `max_score`, `modality`
- `cooldown_until`, `revision`

同一冷却窗口内只更新出现次数、最后出现时间和最高分，不重复产生 `alert.triggered`。告警写入必须支持 `idempotency_key`，建议由 `task/binding/target/window-start` 规范化生成；重复请求必须返回原告警，而不是创建第二条记录。

### 5. AlertRecord 状态机

#### `AlertRecord`

- `tenant_id`, `project_id`, `alert_id`
- `task_id`, `binding_id`, `watchlist_id`, `member_id`, `portrait_identity_id`
- `source_id`, `camera_id`, `run_id`, `unit_id`, `track_id`
- `trajectory_identity_id`, `trajectory_segment_id`，可为空
- `match_score`, `modality`, `threshold_policy_version`, `model_bindings`
- `snapshot_artifact_id`、`snapshot_retention_expires_at`
- `status`: `pending` / `confirmed` / `false_positive` / `ignored`
- `first_seen_at`, `last_seen_at`, `triggered_at`, `created_at`, `updated_at`
- `occurrence_count`, `max_score`, `revision`
- `triaged_by`, `triaged_at`, `triage_reason`, `triage_notes`

状态只允许：

```text
pending -> confirmed
pending -> false_positive
pending -> ignored
```

处置接口必须携带 `expected_revision`，并在并发修改时返回 `409`。每次状态转换写审计；`alert.triaged` 只在事务成功后生成。是否允许重新打开应作为单独的受控动作，不得通过任意 PATCH 绕过状态机。

### 6. 告警持久化与 Outbox 原子性

接受一次告警时按以下顺序执行：

1. 验证 ObservationBatch 和 Artifact 的完整性，使用 SHA-256 校验对象。
2. 在数据库事务中写入或更新 AlertRecord、AlertEvent、Debounce 状态。
3. 在同一事务中写入 Webhook Outbox 记录或调用等价的事务内出队接口。
4. 事务提交后再向内存中的 SSE 订阅者广播；订阅者断开不影响持久化。

对象上传和数据库事务无法做到单一物理事务，因此对象必须使用不可变键。数据库失败时删除未被引用的对象；删除失败进入 orphan sweep。告警对象一旦被告警记录引用，应按照 `alert_snapshot` 保留策略治理，不得跟随普通 Run Result 静默删除。

### 7. 事件契约

告警事件统一使用以下信封，事件正文不得包含原始 embedding、身份证号、原始图片字节或永久下载凭证：

```json
{
  "event_id": "alevt_xxx",
  "event_type": "alert.triggered",
  "event_version": "1.0",
  "occurred_at": "2026-08-30T10:00:00.000000Z",
  "producer": "scenara",
  "tenant_id": "tenant-a",
  "project_id": "project-a",
  "trace_id": "...",
  "alert_id": "alt_xxx",
  "task_id": "st_xxx",
  "camera_id": "camera-a",
  "portrait_identity_id": "pi_xxx",
  "match_score": 0.91,
  "modality": "fused",
  "snapshot_artifact_id": "art_frame_xxx",
  "deduplication_key": "..."
}
```

- 支持事件：`alert.triggered`、`alert.triaged`。
- `event_id` 全局唯一且不可变；同一告警重试保持同一事件 ID。
- Webhook 使用当前 `Scenara-Signature` 签名和 Delivery Outbox，支持重试、死信、查询和人工重放。
- `SUPPORTED_WEBHOOK_EVENTS`、事件 Schema、OpenAPI、Python SDK、TypeScript SDK 和契约测试必须同步更新。

### 8. 实时 SSE 契约

第一版只实现 SSE，复用现有 `/api/v1/runs/{run_id}/events` 的心跳、`Last-Event-ID` 和断开检测模式；只有确实需要双向控制时才评估 WebSocket。

端点：`GET /api/v1/surveillance/alerts/live-stream`

- 租户和项目只从认证上下文取得，不接受查询参数覆盖。
- 支持 `Last-Event-ID` 断点续传；服务端先从持久化 `AlertEvent` 回放，再订阅新事件。
- 回放游标过期时返回明确错误和新的起始游标，不能静默丢事件。
- 每 15 秒发送心跳；客户端断开后释放订阅资源。
- SSE 延迟指标从 AlertRecord 事务提交到客户端发送分别统计，不能把 HTTP 请求耗时当告警延迟。

---

## 三、三阶段研发路线

### 阶段零：契约和资格前置门禁

**目标**：在写业务代码前冻结跨模块契约，避免生成第二套身份、事件和存储语义。

- [ ] 评审并冻结 Watchlist/Member、Task/Binding、ObservationBatch、AlertRecord、AlertEvent Schema。
- [ ] 在共享 IAM 和产品目录中注册 `surveillance_watchlist`、`surveillance_task`、`surveillance_alert` 资源；初期复用 `parse` 产品授权，不建设独立认证体系。
- [ ] 冻结阈值策略、模型绑定、分数校准、时间戳来源和 `match_policy` 语义。
- [ ] 冻结 `alert_snapshot` 保留天数、敏感字段访问规则、删除级联和备份恢复要求。
- [ ] 冻结负载模型：视频分辨率、采样间隔、每路流 FPS、名单规模、并发流数、GPU/CPU、Qdrant 或 pgvector 后端。
- [ ] 在 contracts、OpenAPI 和 SDK 中建立版本化 API/事件契约；契约不通过不得进入阶段一。

### 阶段一：核心闭环与可测试实时评估

**目标**：先完成“观察批次 -> 比对 -> 频控 -> 告警事务 -> Outbox”的后端闭环，再接入实际 Stream Run。

#### 1.1 数据和仓储

- [ ] 实现 Watchlist、WatchlistMember、SurveillanceTask、TaskBinding、AlertRecord、AlertEvent、DebounceState 模型。
- [ ] 新增 `SurveillanceRepository` 和 `AlertEventRepository` 协议，方法必须带租户、项目和分页参数。
- [ ] 实现内存仓储，仅用于单测和开发模式；明确不支持生产级频控。
- [ ] 实现 PostgreSQL 仓储，使用复合主键/唯一键、外键、版本字段和事务方法。
- [ ] 新增 `0014_surveillance_alerts.sql`，遵循现有 SQL 迁移机制；每个迁移文件使用 `BEGIN`/`COMMIT` 并登记同名版本。
- [ ] 为告警列表建立按租户/项目、状态、时间、摄像头、任务和身份的组合索引；为 AlertEvent 建立可回放的有序游标索引。

#### 1.2 Matcher 和 Debounce

- [ ] 实现 `PortraitSurveillanceMatcher`，通过现有 `FeatureStore.search` 执行按特征空间的 Top-K 检索。
- [ ] 实现模态质量门禁和分数校准接口；没有校准证据时禁止宣称融合准确率。
- [ ] 实现 `AlertDebounceManager` 的 Redis 原子实现和 PostgreSQL 兼容实现。
- [ ] 覆盖同一目标、不同任务、不同摄像头、冷却边界、Worker 重启、重复消息和并发竞争。

#### 1.3 接入 Stream Run

- [ ] 在 Run/Portrait 边界增加平台无关的 `ObservationBatch` 观察器接口。
- [ ] Portrait 分析在每个可发布的中间批次生成观察批次，保留私有 embedding 只在进程内传递；公开 Result 继续脱敏。
- [ ] Alert Evaluator 在 `result.delta` 产生前后采用固定顺序调用，告警失败可重试但不能破坏 Result 主流程；失败必须有可观测错误和补偿任务。
- [ ] `camera_id`、`source_id`、`recording_started_at` 和 `timestamp_source` 全程传递；缺少权威时间时禁止跨 Run 形成时空结论。
- [ ] 任务 Supervisor 以幂等方式启动/暂停/恢复绑定的 Stream Run，处理 Source 不可用、断流、重连、任务过期和重复启动。

#### 1.4 告警对象、事务和 Webhook

- [ ] 优先使用现有 `RunArtifactSink` 生成帧/目标抓拍；AlertRecord 只保存 Artifact 引用。
- [ ] 扩展对象保留模型，增加 `alert_snapshot` 类别和 `surveillance_alert` owner；告警快照默认保留策略由配置提供。
- [ ] 实现 AlertRecord + AlertEvent + Debounce + Webhook Outbox 的事务写入。
- [ ] 在 `SUPPORTED_WEBHOOK_EVENTS` 注册 `alert.triggered`、`alert.triaged`，补充事件版本、签名、重放和死信测试。

#### 1.5 阶段一 API

```text
POST   /api/v1/surveillance/watchlists
GET    /api/v1/surveillance/watchlists
GET    /api/v1/surveillance/watchlists/{watchlist_id}
PATCH  /api/v1/surveillance/watchlists/{watchlist_id}
DELETE /api/v1/surveillance/watchlists/{watchlist_id}

POST   /api/v1/surveillance/watchlists/{watchlist_id}/members
GET    /api/v1/surveillance/watchlists/{watchlist_id}/members
PATCH  /api/v1/surveillance/watchlists/{watchlist_id}/members/{member_id}
DELETE /api/v1/surveillance/watchlists/{watchlist_id}/members/{member_id}

POST   /api/v1/surveillance/tasks
GET    /api/v1/surveillance/tasks
GET    /api/v1/surveillance/tasks/{task_id}
PATCH  /api/v1/surveillance/tasks/{task_id}
POST   /api/v1/surveillance/tasks/{task_id}/start
POST   /api/v1/surveillance/tasks/{task_id}/pause
POST   /api/v1/surveillance/tasks/{task_id}/resume

GET    /api/v1/surveillance/alerts
GET    /api/v1/surveillance/alerts/{alert_id}
PATCH  /api/v1/surveillance/alerts/{alert_id}/status
```

列表接口必须支持 `offset`、`limit` 和稳定排序；告警查询支持时间范围、任务、摄像头、名单、身份、分数、模态和处置状态。所有写接口使用共享认证、scope、product entitlement、审计和标准错误码。

#### 1.6 阶段一验收

- [ ] 领域模型和仓储单测覆盖率达到 90%，并包含租户/项目越权测试。
- [ ] 固定 embedding fixture 能复现候选、阈值、单模态/融合和误报拒绝结果。
- [ ] 100 个并发重复请求最多生成一条相同幂等告警。
- [ ] 多 Worker 和 Redis/数据库重启后，冷却状态不丢失且不产生告警风暴。
- [ ] AlertRecord、AlertEvent 和 Webhook Delivery 可从同一次事务中恢复，失败时可重试且不重复投递。
- [ ] 告警抓拍可通过授权 Artifact 接口读取，过期后返回明确的不可用状态；原始 embedding 和身份证号不会出现在响应或日志。
- [ ] 至少完成一条真实 Stream Source 的 `result.delta -> alert.triggered` 集成测试；测试必须记录采样间隔、流分片时长和模型状态。

### 阶段二：控制台实时预警与人工处置

**目标**：在阶段一契约稳定后提供完整的管理和研判体验。

#### 2.1 SSE 与告警中心

- [ ] 实现 `GET /api/v1/surveillance/alerts/live-stream`，支持回放、心跳、断线续传和权限过滤。
- [ ] 仅展示已提交的告警事件；内存广播丢失不能影响历史查询和断点回放。
- [ ] 处理浏览器自动播放限制：声音默认静音，用户主动开启后才播放声光提示；暂停推流只影响当前客户端。
- [ ] 增加前端连接中、断线重连、游标过期、权限过期、空状态和告警风暴降级状态。

#### 2.2 管理页面

- [ ] `/console/surveillance/watchlists`：名单、成员、身份引用、有效期、状态和脱敏信息管理。
- [ ] `/console/surveillance/tasks`：选择名单、Source/Camera 绑定、Schedule、阈值策略、匹配策略和任务状态。
- [ ] `/console/surveillance/live`：实时告警时间线、抓拍与底库图对比、摄像头、时间、模态、分数和任务信息。
- [ ] `/console/surveillance/alerts`：历史筛选、分页、详情、处置和审计记录。
- [ ] 告警详情以 Artifact 权限接口读取抓拍，不拼接对象存储内部 URL，不在浏览器缓存长期凭证。

#### 2.3 人工研判

- [ ] 处置动作只使用后端状态机接受的 `confirmed`、`false_positive`、`ignored`。
- [ ] 提交 `expected_revision`、原因和备注，展示冲突后刷新结果。
- [ ] 处置人、处置时间、备注和原始告警摘要进入审计；禁止修改原始匹配证据。
- [ ] `false_positive` 或 `low_quality` 只能创建待审核 Feedback，不得自动进入训练集。

#### 2.4 阶段二验收

- [ ] Playwright 验证“身份/照片注册 -> 加入名单 -> 创建任务 -> 启动流 -> 告警出现 -> 处置”的完整流程。
- [ ] 以固定浏览器、网络和流负载测量从 AlertRecord 提交到页面展示的 P50/P95/P99；`<500ms` 只能作为在明确负载下的目标，不能作为脱离环境的承诺。
- [ ] 验证断线续传不会重复展示或丢失已持久化告警。
- [ ] 验证不同租户、项目和权限主体不能读取名单成员、抓拍、告警和 SSE 事件。

### 阶段三：轨迹联动、时空约束与反馈闭环

**目标**：在告警记录已具备稳定 `run_id/track_id/camera_id` 引用后，接入现有长期轨迹能力。

#### 3.1 轨迹联动

- [ ] AlertRecord 保存 `trajectory_identity_id` 和 `trajectory_segment_id`，为空时显示“暂无轨迹关联”，不能猜测身份。
- [ ] 详情页调用现有 `/api/v1/portrait/trajectories/identities/{identity_id}/timeline` 和片段接口。
- [ ] 没有 `recording_started_at` 时只展示单 Run 相对时间，不生成跨摄像头权威路线。
- [ ] 轨迹登记失败不丢失告警；后续补偿任务可以按 `run_id/track_id` 重试并幂等回填引用。

#### 3.2 时空可达性

- [ ] 复用 `CameraRecord` 和 `CameraTransition` 的 `min_seconds/max_seconds` 契约。
- [ ] 若使用物理距离，必须为 Camera 增加受控的坐标/拓扑字段和坐标精度、来源、更新时间；文本 `location` 不能直接用于距离计算。
- [ ] “500 米/1 秒”只能作为测试案例，不得写成默认业务规则；真实阈值由摄像头拓扑和目标环境容量报告提供。
- [ ] 时空过滤应作为候选合并的证据或降权规则，不能把单次时空异常直接当作确认身份。

#### 3.3 反馈和难例

- [ ] `false_positive` 映射到 `FeedbackKind.WRONG_IDENTITY` 或经评审确定的类型；低质量需在 `correction` 中使用结构化原因。
- [ ] 调用 `POST /api/v1/feedback` 时提供真实 `run_id`、模型 ID/版本、结果来源和纠正信息；不能伪造最小字段绕过验证。
- [ ] 反馈必须满足 `authorized_for_training`、`deidentified` 和人工审核条件，才允许创建 `HardSampleManifest`。
- [ ] 误报对象引用使用受控 `media_ref/result_ref`；不得把原始抓拍字节或 embedding 写入 correction。

#### 3.4 特征和模型升级

- [ ] 以 `feature_space_id + model_id + model_version + dimension + distance_metric` 作为特征版本边界。
- [ ] 新模型通过现有 Model Package Admission、Qualification Evidence 和 Release 状态机后，才允许建立新的特征空间。
- [ ] 重提取采用后台作业、批次进度、失败重试和双索引切换；切换前保留旧空间，切换后验证数量、维度、摘要和抽样结果。
- [ ] 不因模型切换直接覆盖旧 embedding；生物特征删除必须同时清理所有版本空间。

#### 3.5 阶段三验收

- [ ] 告警详情在有权威录制时间和轨迹数据时能查询对应跨摄像头时间线；无数据时明确返回空原因。
- [ ] 时空不可达案例、可达案例、时间重叠案例和无拓扑案例均有自动化测试。
- [ ] 反馈经过审核后可生成合法 Hard Sample Manifest，并完成 Core -> Data 的契约测试。
- [ ] 完成模型版本升级、回滚、生物特征删除和告警引用保留的恢复演练。

---

## 四、性能、可观测性和运维门禁

### 1. 性能指标定义

所有性能数字必须绑定以下测试条件：模型制品摘要、特征空间维度、名单规模、每路流采样间隔、输入分辨率、并发流数、GPU/CPU、FeatureStore 后端和网络拓扑。

- `matcher_duration_seconds`：只计算向量召回、候选过滤和阈值决策；在 10 万人库上的 `50ms` 只能作为经过目标环境验证后的 P95 目标，不能代表端到端告警延迟。
- `alert_persist_latency_seconds`：从观察批次进入评估到 AlertRecord 事务提交。
- `alert_delivery_latency_seconds`：从事务提交到 SSE 客户端发送或 Webhook 交付。
- 端到端目标应分别报告 P50/P95/P99、吞吐、队列积压、丢弃/降级数和错误率。
- “50+ 路并发视频流”必须给出每路视频参数和 GPU 利用率；不允许只用开发机或单个短视频得出结论。

### 2. Prometheus 指标

在现有 `/metrics` 基础上增加低基数标签，禁止使用 `tenant_id`、`project_id`、`target_id`、`camera_id` 作为指标标签：

```text
scenara_surveillance_alerts_total{level,status,modality}
scenara_surveillance_match_duration_seconds{modality,backend}
scenara_surveillance_alert_persist_duration_seconds
scenara_surveillance_alert_delivery_duration_seconds{channel,status}
scenara_surveillance_debounce_suppressed_total{reason}
scenara_surveillance_active_tasks_count
scenara_surveillance_observation_backlog
scenara_surveillance_webhook_dead_letter_total
```

同时补充结构化日志字段：`request_id`、`trace_id`、`alert_id`、`task_id`、`run_id`、`event_id`。日志中不得出现原始 embedding、身份证号、访问密钥或图片字节。

### 3. 最低运维告警

- Alert Event 回放失败或游标积压；
- Debounce Redis/PostgreSQL 不可用；
- Stream Run 长时间 queued/running；
- 告警 Outbox pending/dead-letter；
- Artifact 上传、校验或删除失败；
- 审计写入失败；
- matcher P95/P99 超过目标；
- observation backlog 持续增长；
- 模型特征空间不存在、维度冲突或模型版本漂移。

生产部署仍遵循现有备份、迁移、恢复和“不提供破坏性 down migration”的运维基线。新增告警表、事件表、Debounce 状态和对象保留记录必须纳入备份恢复抽样核验。

---

## 五、文件与代码变动规划

```text
scenara/
├── platform/
│   ├── models.py                       # MODIFY: 共享请求/响应、保留记录和事件引用模型
│   ├── policy.py                       # MODIFY: surveillance 资源与产品授权映射
│   ├── webhook_service.py              # MODIFY: 注册 alert.triggered/alert.triaged
│   ├── observability.py                # MODIFY: 告警指标
│   └── surveillance.py                 # NEW: 通用端口、事件/仓储/评估协议
├── domains/portrait/
│   ├── surveillance.py                 # NEW: 名单成员编排、Portrait Matcher、观察批次评估
│   ├── trajectory.py                    # MODIFY: 告警轨迹引用和补偿登记接口
│   └── service.py                       # MODIFY: 复用身份和 Enrollment，不复制底库
├── infrastructure/
│   ├── postgres_surveillance.py         # NEW: PostgreSQL 仓储和事务实现
│   ├── memory_surveillance.py           # NEW: 开发/测试仓储
│   ├── redis_surveillance.py            # NEW: 多 Worker Debounce 原子实现
│   └── postgres_state.py                # MODIFY: 迁移、告警事件回放和 Outbox 接入
├── platform/services.py                 # MODIFY: ObservationBatch/AlertEvaluator Hook
├── server.py                            # MODIFY: REST、SSE、错误码和依赖装配
frontend/console/src/
├── api/surveillance.ts                  # NEW: API 类型和请求封装
├── views/surveillance/
│   ├── WatchlistManagement.vue          # NEW
│   ├── TaskManagement.vue               # NEW
│   ├── LiveAlertCenter.vue              # NEW
│   └── AlertHistory.vue                 # NEW
├── router.ts                            # MODIFY: 注册控制台路由
└── types.ts                             # MODIFY: 生成/共享类型同步
migrations/
└── 0014_surveillance_alerts.sql        # NEW: 事务迁移，不修改历史迁移
tests/
├── test_surveillance.py                 # NEW: 模型、匹配、阈值、频控和权限
├── test_surveillance_events.py           # NEW: SSE、Webhook、Outbox、回放和幂等
├── test_surveillance_integration.py      # NEW: Stream Run -> AlertRecord
└── test_surveillance_security.py         # NEW: PII、embedding、对象和租户隔离
```

说明：当前仓库的测试目录是扁平结构，计划中的测试文件应放在现有 `tests/` 下；除非项目后续统一迁移测试布局，否则不创建与当前约定不一致的 `tests/unit` 或 `tests/e2e` 目录。

---

## 六、里程碑和发布门禁

### 当前实施状态（开发工作区）

截至本次开发，M1/M2/M3 的代码级交付已经落地：Watchlist 与既有人像身份关联、任务与 Source/Camera 绑定、PostgreSQL/内存仓储、跨实例可恢复的 PostgreSQL 频控、Run 观察批次、告警/事件/Outbox、SSE 回放、Webhook、Console 页面、轨迹引用、误报反馈入口、SDK 与 OpenAPI 均已实现并纳入自动化回归。

本地开发基础设施已具备并完成验证：`start.py` 会在 `.env` 配置本地地址且端口未监听时自动启动 Redis Streams、MinIO 和 Qdrant；Qdrant 1.18.2 的 FeatureStore CRUD/租户过滤在真实 HTTP 服务上通过；PostgreSQL 18 的原生 `pg_dump`/`pg_restore` 与 MinIO 对象恢复可使用 `python scripts/local_native_backup_restore_drill.py` 在临时 schema 上演练，不要求创建数据库权限。

本地开发环境还完成了以下**模拟资格验证**，所有报告写入被忽略的 `runtime-state/qualification/`，均不写入发布证据清单，也不构成生产资格：

- `python scripts/run_surveillance_local_simulation.py`：50 个逻辑 Source/Camera 绑定的并发观察、冷却去重；本地临时 TLS Webhook 的 HMAC 校验；真实本机 HTTP SSE 的游标回放。
- `python scripts/run_local_stream_protocol_simulation.py`：本机 MediaMTX 与 FFmpeg 合成画面构成的 RTSP、RTMP 回环，Scenara 解码器各完成一个两秒分片采样。OpenCV 无帧时使用现有 PyAV 依赖回退，避免 Windows 精简 FFmpeg 的协议握手成功但无法解码问题。
- `python scripts/run_local_data_cutover_simulation.py`：Core 本地 Adapter 与真实本机 Data HTTP 边界的影子记录对比、幂等重放、读取、更新和归档清理。Core 的 200 条分页契约已桥接为 Data 的最多 100 条分页请求。
- `python scripts/run_local_evidence_pipeline_simulation.py`：自编写的合成向量和合成模型文件验证“固定阈值早于两次独立运行”、摘要绑定和模型权利候选报告的失败关闭流程；绝不代表真实模型或真实评估集的权利状态。

仍保持未完成状态的项目是目标环境资格，而不是代码待办：物理摄像头与外部网络的 RTSP/RTMP 实测、目标生产规模 Qdrant、目标 GPU 上 50+ **实际视频解码**压力、真实固定评估集和模型权利批准、外部网络 Webhook/SSE、整库备份恢复和 Data 服务正式切流，必须在实际部署环境取得可复现证据后才可关闭。

| 里程碑 | 核心交付 | 退出条件 |
| --- | --- | --- |
| M0 | 契约、权限、隐私、负载和迁移设计冻结 | Schema、OpenAPI、事件、SDK 和安全评审通过 |
| M1 | 后端告警闭环 | 固定观察批次和真实 Stream 集成通过；幂等、频控、事务、Outbox 和租户隔离有证据 |
| M2 | Console 告警中心 | SSE 回放/重连、名单任务管理、抓拍核验、人工处置和 Playwright 流程通过 |
| M3 | 轨迹和反馈闭环 | 轨迹引用、时空约束、反馈审核、Hard Sample 和模型升级恢复演练通过 |

以下任一项未通过，不得对外声明“实时布控生产可用”：

- 没有固定模型版本、阈值策略和评估集；
- 没有真实目标环境的 GPU/CPU、FeatureStore、流并发和延迟报告；
- 没有告警对象保留、删除、备份恢复和审计证据；
- 没有跨租户、PII、embedding、对象 URL、Webhook 签名和重放安全测试；
- 没有 Stream Run 到 AlertRecord 的真实链路测试；
- 没有 Webhook Outbox 死信和 SSE 断点回放测试；
- 没有合法反馈授权、去标识化和 Hard Sample 契约证据。

当前文档对应的是 `0.3.0-dev.36` 目标方案。实现过程中如 API、事件或模型契约发生变化，必须同步更新 OpenAPI、两个 SDK、Console 类型、迁移、契约测试和发布说明；不能只修改本文档。
