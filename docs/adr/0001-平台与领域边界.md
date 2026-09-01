# ADR 0001：平台与领域边界

- 状态：已接受 (accepted)
- 日期：2026-07-29

## 背景

Scenara 必须支持独立演进的视觉领域（Domain），而无需使平台内核感知 Portrait 或 OCR 的具体语义。它还必须基于相同契约支持 API、批处理 worker、流式 worker 和调度器进程。

## 决策

代码仓库划分为四个依赖层次与方向：

1. `scenara.platform` 定义媒体、运行任务（Run）、流水线（Pipeline）、解析结果（Result）、模型（Model）、特征（Feature）、数据保留（Retention）、审计（Audit）、策略（Policy）和 worker 契约。它绝不导入具体领域或基础设施实现。
2. `scenara.domains` 实现上述契约。领域在构建时安装，并仅通过 `DomainPluginRegistry` 对外可见。不支持运行时代码动态上传。
3. `scenara.infrastructure` 实现 PostgreSQL、Redis 以及经认证的兼容 S3 提供商的平台端口。它不定义领域行为，亦不将平台契约硬绑定至 MinIO、Amazon S3、OSS 或 Ceph RGW。
4. `scenara.enterprise` 实现可选的企业策略提供者。平台代码调用策略提供者契约，不直接导入企业实现。

PostgreSQL 是权威数据源。Redis 仅保存投递、租约和临时事件状态。兼容 S3 的对象存储保存媒体文件和不可变的结果产物，而 PostgreSQL 保存其元数据引用与校验和。

## 影响

- 架构导入规则测试作为发布门禁。
- 领域特定的可辨识结果 schema 保留在平台契约中，以便客户端能够安全解码已登记的公共领域。执行内核完全通过注册表进行分发。
- 新增领域需要提供插件实现、类型化结果契约、固定评估集和控制台路由；不需要在平台执行内核中添加条件分支。
