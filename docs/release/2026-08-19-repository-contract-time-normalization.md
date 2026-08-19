# 跨仓库契约时间字段修订说明

**日期**：2026-08-19  
**适用范围**：`scenara` 集成仓库、`scenara-data`、`scenara-model` 消费方及 `@scenara/repository-contracts` `1.0.0` 目录  
**版本策略**：兼容性修订，不改变应用版本号

## 背景

跨仓库契约此前使用 Unix 浮点秒表示 `created_at`。这种表示在 JSON、日志、数据库适配器和不同语言客户端之间缺少明确的时区语义，也容易在跨服务转发时发生重复转换或精度损失。本次修订将契约边界的时间表示收敛为明确的 UTC RFC3339 字符串。

## 变更内容

### 契约层

以下三个跨仓库契约的 `created_at` 均改为字符串：

| 契约 | 生产方 | 消费方 | 影响字段 |
| --- | --- | --- | --- |
| `hard-sample-handoff` | `scenara` | `scenara-data` | `HardSampleManifest.created_at` |
| `dataset-version-input` | `scenara-data` | `scenara-model` | `DatasetVersionReference.created_at` |
| `deployment-feedback` | `scenara` | `scenara-model` | `ModelDeploymentEvent.created_at` |

合法格式为：

```text
YYYY-MM-DDTHH:mm:ssZ
YYYY-MM-DDTHH:mm:ss.ssssssZ
```

小数秒可省略，最多保留 6 位；时区必须使用 `Z`，不接受带偏移量的 `+08:00` 等写法。示例：

```json
{
  "created_at": "2026-08-18T00:00:00Z"
}
```

### Core 实现层

- `scenara/platform/feedback.py` 提供 UTC RFC3339 生成、校验和到 Unix epoch 的存储转换函数。
- `HardSampleManifest` 和 `ModelDeploymentEvent` 在模型边界拒绝非 UTC RFC3339 字符串。
- PostgreSQL 反馈适配器在写入清单和部署事件时将合法 UTC 字符串转换为数据库使用的 epoch 时间。
- HTTP Data 客户端透传清单中的 UTC 字符串，不再先转换为 epoch 再重新格式化。

### 发布资料层

- 三个 JSON Schema 和对应有效示例已同步更新。
- `contracts/repository/v1.0.0/manifest.json` 与 `release-index.json` 的 SHA-256 摘要已同步刷新。
- 发布证据 manifest 及已登记报告的 OpenAPI 发行摘要已同步到当前记录。
- 《景枢平台总体开发规范》已登记 `1.3.0` 版本，明确独立前端部署边界和共享主题约束；本次时间字段修订遵循同一契约优先原则。

## 兼容与迁移说明

这是跨仓库 JSON 载荷表示方式的契约修订。生产方应从本修订起发送 UTC RFC3339 字符串，消费方应在契约入口执行格式校验。数据库、内部队列或历史内部接口可以继续使用 epoch 或数据库原生时间类型，但这些类型不得直接暴露为跨仓库契约字段。

历史载荷如需重放，应在发送前将 Unix 时间转换为 UTC RFC3339 字符串，并保持事件或清单中的原始时刻不变。不得通过读取机器本地时区重新解释历史数字时间。

## 当前发布边界

本说明只记录已经落在当前工作区中的实现、契约和文档修订。GPU 容量、模型权利、离线安装和领域评估等仍处于各自证据状态，未因本次修订而改变。本文不新增测试执行记录，也不将待完成证据标记为已完成。
