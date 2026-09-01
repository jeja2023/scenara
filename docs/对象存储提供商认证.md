# 经过认证的 S3 对象存储提供商

Scenara 依赖于标准 S3 契约，而非特定的存储产品。PostgreSQL 是业务记录和对象引用的权威数据源。经过认证的 S3 提供商负责存储原始媒体、预览图、运行产物以及不可变的结构化解析结果。

## 提供商状态

| 提供商 | 状态 | 预期部署场景 |
|---|---|---|
| MinIO | 经认证基线（Certified baseline） | 单节点私有化与离线部署 |
| Amazon S3 | 候选支持（Candidate） | AWS 托管生产环境 |
| 阿里云 OSS (S3 API) | 候选支持（Candidate） | 中国大陆云托管生产环境 |
| Ceph RGW | 候选支持（Candidate） | 既有私有云存储平台 |

“候选支持”意味着适配器可针对该提供商进行配置，并不代表当前发布版本已具备其资格凭据。提供商只有在针对真实服务通过 `tests/object_store_contract.py` 目标版本测试并将生成的报告附加到发布证据后，才会成为“经认证”。

该契约涵盖不可变幂等上传与并发冲突拒绝、带校验和保护的分片上传、完整及基于文件的下载验证、元数据、存在性检查、删除、重连恢复、预签名 PUT/GET 以及带标签的生命周期规则。

使用特定提供商的环境变量运行 S3 资质测试：

```powershell
$env:SCENARA_RUN_INTEGRATION = "1"
$env:SCENARA_INTEGRATION_S3_ENDPOINT = "https://objects.example.com"
$env:SCENARA_INTEGRATION_S3_ACCESS_KEY = "..."
$env:SCENARA_INTEGRATION_S3_SECRET_KEY = "..."
python -m pytest -q tests/integration/test_services.py -k "s3_provider or presigned_media"
```

请使用隔离的测试存储桶。测试套件会创建唯一键并将其删除，而生命周期测试会更新存储桶的生命周期配置。

## 完整性与不可变性

默认情况下，所有已发布的写入操作均为不可变的。`If-None-Match: *` 可防止不同有效负载替换现有键；使用相同的键和 SHA-256 重试是幂等的。分片上传完成也使用相同的条件。唯一可变的对象类别是加密的内部机密存储，它采用了显式的原子覆盖路径。

每次写入都会将 SHA-256 作为 S3 元数据存储，并在受支持时发送原生 S3 校验和。媒体执行、结果加载、产物读取和 Redis 队列恢复会将对象字节或元数据与 PostgreSQL 引用进行对比。

## 凭据、TLS 与加密

MinIO 和离线安装继续支持静态凭据。将 access key、secret key 和 session token 留空可使用 AWS/默认凭据提供者链（包括实例角色和工作负载身份）。STS 会话凭据可以通过 `SCENARA_S3_SESSION_TOKEN` 提供。

TLS 验证默认启用。`SCENARA_S3_CA_BUNDLE` 可配置私有 CA 信任路径。`SCENARA_S3_SERVER_SIDE_ENCRYPTION` 支持 `AES256` 和 `aws:kms`；后者可以使用 `SCENARA_S3_KMS_KEY_ID`。

`SCENARA_S3_ADDRESSING_STYLE` 接受 `auto`、`path` 或 `virtual`。MinIO 通常使用 `path`；OSS 通常需要 `virtual`。

## 生命周期归属

PostgreSQL 数据保留记录和 Scenara 调度器保持权威性。当 `SCENARA_S3_LIFECYCLE_ENABLED=true` 时，提供商会在应用保留截止日期后一天为原始媒体、预览和结构化结果安装基于标签的规则。该宽限期允许调度器先标记数据库记录。未完成的直传文件将在一天后过期。

仅对具有调用 `PutBucketLifecycleConfiguration` 权限的身份启用生命周期管理。否则，请在 Scenara 外部配置等效规则并将该设置保持为 false。

## 客户端直传

设置 `SCENARA_S3_PRESIGNED_URLS_ENABLED=true` 以暴露受控的直传工作流：

1. `POST /api/v1/media/uploads/presign` 将 PUT URL 绑定到租户、项目、文件名、内容类型、精确字节长度、SHA-256 和过期时间。
2. 客户端使用返回的全部请求头将字节直接上传到存储提供商。
3. `POST /api/v1/media/uploads/complete` 在创建资产并删除待处理对象之前，验证 HMAC 令牌、大小和摘要。
4. `GET /api/v1/media/assets/{asset_id}/download-url` 仅在授权和完整性验证后返回短期的 GET URL。

在容器部署中，将 `SCENARA_S3_PUBLIC_ENDPOINT_URL` 设置为外部客户端可访问的端点。内部端点仍可用于 API 和 worker 流量。Python SDK `upload_asset_direct` 和 TypeScript SDK `uploadAssetDirect` 实现了此工作流。
