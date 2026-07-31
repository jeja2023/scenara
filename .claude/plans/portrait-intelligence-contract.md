# 人像智能基础平台契约层实现方案

## 目标

把 `docs/strategy/PORTRAIT_INTELLIGENCE_STRATEGY.md` 的六大模块与三项资产，从散文文档变成**机器可读、可门禁、Console 可见**的平台契约。与 `product_catalog.py` / `access_foundation.py` / `repository_topology.py` 完全同构。

不做的事（本轮明确排除）：
- 不虚构模型能力（SCRFD/ArcFace ONNX 制品必须由 `scenara-model` 提供）
- 不在本仓库建训练、标注、数据湖（违反仓库拓扑边界）
- 不把 `planned` 能力标为 `available`

## 为什么这么做

战略文档现在只有人能读。把它变成契约后：
1. 能力成熟度成为**唯一事实来源**，Console/SDK/OpenAPI 共享
2. 六模块进度可被 CI 门禁校验，防止文档与代码漂移
3. 后续每次能力升级（fallback → ready）只改一处

## 改动清单

### 1. 平台模型（`scenara/platform/models.py`）

追加至 `AccessFoundationStatus` 之后，复用现有 `StrictModel` 与 pattern 约束风格：

```python
type PortraitModuleId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")]

class PortraitModuleMaturity(StrEnum):      # 与 ProductMaturity 同语义，独立枚举避免耦合
    AVAILABLE = "available"
    PARTIAL = "partial"
    SEED = "seed"
    PLANNED = "planned"
    EXTERNAL = "external"                    # 职责在其他仓库

class PortraitCapabilityReadiness(StrEnum):  # 映射 model-capabilities.yml 的 status
    READY = "ready"
    FALLBACK = "fallback"
    PLACEHOLDER = "placeholder"
    NOT_CONFIGURED = "not_configured"

class PortraitCapabilityItem(StrictModel):
    capability_id: str                       # face_detection / body_embedding ...
    readiness: PortraitCapabilityReadiness
    production_ready: bool                   # 复用 production_model_ready() 语义
    target_model: str | None                 # SCRFD 10GF ONNX
    embedding_dimension: int | None
    target_embedding_dimension: int | None

class PortraitModuleItem(StrictModel):
    module_id: PortraitModuleId              # data_governance / annotation / training / algorithms / vector_retrieval / mlops
    name: str
    maturity: PortraitModuleMaturity
    summary: str
    owner_repository_id: RepositoryId        # 复用已有 RepositoryId，显式声明职责归属
    current_scope: list[str]
    not_in_scope_yet: list[str]
    next_gate: str

class PortraitAssetItem(StrictModel):
    asset_id: PortraitModuleId               # data_lake / foundation_model / intelligence_engine
    name: str
    maturity: PortraitModuleMaturity
    summary: str
    depends_on_modules: list[PortraitModuleId]
    next_gate: str

class PortraitIntelligenceStatus(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    positioning: Literal["portrait_intelligence_foundation_platform"]
    modules: list[PortraitModuleItem]
    assets: list[PortraitAssetItem]
    capabilities: list[PortraitCapabilityItem]

    @model_validator(mode="after")           # 与 RepositoryTopology 同样的引用完整性校验
    def validate_references(self) -> PortraitIntelligenceStatus: ...
```

校验器保证：module_id/asset_id 唯一、`depends_on_modules` 必须指向已声明模块。

### 2. 契约构建器（新建 `scenara/platform/portrait_intelligence.py`）

仿 `access_foundation.py` 的纯函数风格：

```python
def build_portrait_intelligence(
    capability_snapshot: Mapping[str, CapabilitySnapshot],   # 由调用方注入，避免 platform 导入 app/
    *, installed_domains: Iterable[str],
) -> PortraitIntelligenceStatus
```

**关键约束**：`tests/test_architecture.py` 禁止 `scenara/platform/*` 导入 `app.*`。因此能力快照通过**参数注入**，由 `scenara/domains/portrait/plugin.py` 或 server 层从 `app.portrait_model_capabilities` 读取后传入。这保持了现有架构边界不被破坏。

六模块的 `owner_repository_id` 如实标注：
- `data_governance` / `annotation` → `scenara-data`（maturity: `planned`）
- `training` → `scenara-model`（maturity: `external`）
- `algorithms` → `scenara-model` 产制品 + `scenara` 运行（`partial`）
- `vector_retrieval` / `mlops` → `scenara`（`partial` / `seed`）

### 3. API 端点（`scenara/server.py`）

在 `platform_access_foundation` 之后追加，复用 `_envelope` 与 `principal_context`：

```python
@app.get("/api/v1/platform/portrait-intelligence", tags=["Platform"])
async def platform_portrait_intelligence(...) -> ApiEnvelope[PortraitIntelligenceStatus]
```

能力快照读取放在 server 层（server 已允许导入 domains）。

### 4. SDK

- `sdk/python/scenara_sdk/models.py`：追加 TypedDict（与现有 `RepositoryTopology` 同风格）
- `sdk/python/scenara_sdk/client.py`：`get_portrait_intelligence()`
- `sdk/typescript/src/client.ts`：`getPortraitIntelligence()`
- `sdk/typescript/src/types.ts` + `generated.ts`：由 `scripts/generate_typescript_sdk.py` 重新生成

### 5. Console

- `types.ts`：追加对应 interface
- `labels.ts`：追加 `portraitModuleLabels` / `portraitAssetLabels` / `portraitCapabilityLabels` / `portraitMaturityLabels` 四组中文映射（服务端英文 → 界面中文，遵循现有约定）
- `OverviewView.vue`：在产品矩阵面板后增加"人像智能基础平台"面板，展示六模块成熟度 + 七能力就绪度 + 三资产。复用现有 `.panel` / `.product-grid` / `.badge` 类，不新增设计系统

### 6. 契约文档同步

- `docs/openapi.json`：`python scripts/export_openapi.py`
- `docs/strategy/PORTRAIT_INTELLIGENCE_STRATEGY.md`：新增"可执行契约"章节，说明 API 路径与 SDK 方法（对齐 REPOSITORY_TOPOLOGY.md 的写法）
- `docs/strategy/PRODUCT_MATRIX.md`：在文末交叉引用
- `更新日志.md`：记录本次契约新增

### 7. 测试

- `tests/test_platform_kernel.py`：构建器单测（模块唯一性、依赖引用完整性、能力快照映射、maturity 不虚高）
- `tests/test_api.py`：端点契约测试（200、schema、envelope）
- `tests/test_python_sdk.py`：SDK 方法测试
- `frontend/console/tests/api.test.ts`：新标签的中文覆盖断言（防英文泄漏回归）
- `frontend/console/e2e/workspaces.spec.ts`：总览路由 mock 追加新端点

## 验证

```
python -m pytest -q
python scripts/export_openapi.py --check
python -m ruff check . && python -m mypy scenara sdk/python
npm run check
```

## 风险与边界

| 风险 | 处理 |
|---|---|
| `platform` 导入 `app` 破坏架构测试 | 能力快照参数注入，构建器保持纯函数 |
| 把规划能力宣传为已发布 | maturity 枚举含 `external`/`planned`；`next_gate` 强制填写；测试断言 `data_governance` 不得为 `available` |
| OpenAPI/SDK 漂移 | 走现有 `--check` 门禁 |
| Console 英文泄漏 | labels.ts 全映射 + e2e 白名单扫描 |
