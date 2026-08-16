# Scenara Data 切流操作说明

本文是 `scenara` 作为共享控制面切换到独立 `scenara-data` 服务的操作说明。Data 的数据库、迁移、备份、恢复和领域表只在 `scenara-data` 仓库实施；Core 不连接或写入 Data 数据库。

## Core 配置

开发与迁移验证可使用本地兼容适配器：

```dotenv
SCENARA_DATA_PLATFORM_MODE=local
```

正式切流必须使用远程 Data 服务：

```dotenv
SCENARA_DATA_PLATFORM_MODE=http
SCENARA_DATA_PLATFORM_URL=https://scenara-data.internal
SCENARA_DATA_PLATFORM_SERVICE_TOKEN=<Core 签发的服务间凭据>
SCENARA_DATA_PLATFORM_TIMEOUT_SECONDS=10
SCENARA_DATA_PLATFORM_MAX_RETRIES=2
```

生产配置会拒绝 `local` 模式、空服务地址和空服务间凭据。Core 会向 Data 转发租户、项目、主体、权限范围、产品授权、请求 ID、`traceparent` 和稳定的幂等键。公共路径保持不变：

```text
/api/v1/datasets
/api/v1/datasets/{dataset_id}
/api/v1/datasets/{dataset_id}/versions
/api/v1/dataset-versions/{version_id}/transition
/api/v1/data/annotation-*
```

兼容期内，Core 把公开 API 的 Version 状态 `validated`/`retired` 映射为 Data 内部状态 `ready`/`archived`，并在响应时映射回公开状态；新状态不泄漏到已发布的 Core SDK。

## 迁移流程

1. 在维护窗口前导出迁移包：

   ```powershell
   python scripts/export_data_migration.py --tenant-id <tenant> --project-id <project> --output <新目录>
   ```

2. 将完整目录交给 Data 导入器。导入器必须先验证 `checksums.txt` 和 `migration-manifest.json`，再保留 Dataset、Dataset Version 和 Annotation 的既有 ID。
3. 对已发布 Dataset Version 重新计算 Manifest 摘要；缺少有效对象引用或摘要的版本不得自动发布。
4. 在 Data 独立数据库完成导入后，用相同租户/项目执行影子读，比对 Dataset、Version、Annotation 的数量、ID、状态和摘要。
5. 启用 `http` 模式，在一个发布周期内观察请求 ID/追踪链路、错误率和 HardSampleManifest 幂等接收结果。
6. 仅在明确的回滚窗口内恢复 `local` 模式；窗口结束后 Core 旧数据表只能只读，并在 Data 侧归档迁移报告、备份和恢复演练记录后退役。

## Hard Sample 与模型输入

Core 仍审核反馈并生成不可变 `HardSampleManifest`。当 `http` 模式启用时，已创建清单会立即提交到 Data 的 `/internal/v1/hard-sample-manifests`。Data 负责幂等接收、Sample/Annotation 创建、Dataset Builder 和 `DatasetVersionReference` 向 Model 的发布；Core 不处理这些数据集事实。

## 发布门禁

切流前必须通过：公共 API/SDK 兼容、租户与项目隔离、已发布版本摘要、Data 到 Model 的 `DatasetVersionReference`、HardSampleManifest 幂等、请求链路查询、迁移数量/摘要报告、Data 备份恢复和回滚演练。不得长期双写或让 Core/Model 连接 Data 数据库。
