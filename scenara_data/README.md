# Scenara Data 独立数据服务

`scenara_data` 是面向数据集（Dataset）、数据集版本（Dataset Version）、样本（Sample）、标注（Annotation）、质量评估（Quality）、血缘追踪（Lineage）与难例（Hard Sample）准入边界的独立 Data 侧服务进程。它独立管理租户与项目作用域状态，仅暴露 Core 网关 `HttpDataPlatformClient` 所使用的内部版本化 HTTP 接口。

该包不导入 Core 状态存储，亦不共享 Core 数据库。本地单元测试可使用内存型 `DataStore`；配置 `SCENARA_DATA_STATE_PATH` 时，独立进程会使用持久化的 SQLite 状态日志。PostgreSQL schema 基线位于 `migrations/data/0001_data_domain.sql`，由独立服务全权拥有。生产环境对象存储绑定、影子读比对、备份恢复与最终切流证据均属于显式发布门禁。

本地运行方式：

```text
SCENARA_DATA_PLATFORM_SERVICE_TOKEN=dev-secret \
SCENARA_DATA_STATE_PATH=runtime-state/scenara-data.db \
python -m scenara_data
```

迁移导入工具在保留源 ID 之前会严格校验 `checksums.txt`：

```text
python scripts/import_data_migration.py ./scenara-data-migration-<timestamp>
```

`/readyz` 负责检查已配置的状态后端。`GET /internal/v1/events/outbox` 暴露用于投递 worker 的待处理版本化事件；它并不替代 Core 的统一审计查询。
