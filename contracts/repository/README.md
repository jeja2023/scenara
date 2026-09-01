# Scenara 跨仓库契约规范

当前已发布的契约包为 `@scenara/repository-contracts` 版本 `1.2.0`。它为每个跨仓库有效负载包含一个 Draft 2020-12 JSON Schema 和一个有效示例，外加一个带校验和的清单文件。

## 契约列表

| 契约名称 | 生产方 (Producer) | 消费方 (Consumer) | 传输协议 (Transport) |
|---|---|---|---|
| `model-package-admission` | `scenara-model` | `scenara` | 不可变清单 (immutable manifest) |
| `deployment-feedback` | `scenara` | `scenara-model` | 领域事件 / 签名 Webhook |
| `hard-sample-handoff` | `scenara` | `scenara-data` | 不可变清单 (immutable manifest) |
| `dataset-version-input` | `scenara-data` | `scenara-model` | 版本化 API |
| `domain-annotation-schema` | `scenara-contracts` | `scenara-data` | 不可变清单 (immutable manifest) |

`release-index.json` 通过 SHA-256 锁定每个已发布的清单。已发布的目录是不可变的；不兼容的变更需要升级 Major 主版本，向后兼容的新增特性需要升级 Minor 次版本。

## 时间字段规范

`hard-sample-handoff`、`dataset-version-input` 和 `deployment-feedback` 中的 `created_at` 字段均为 UTC RFC3339 字符串格式。必须以 `Z` 结尾；可选的小数秒可包含 1 到 6 位数字。例如：

```json
{
  "created_at": "2026-08-18T00:00:00Z"
}
```

消费方必须在契约边界验证此格式。内部数据库或队列适配器可以将其转换为原生时间戳或 Unix 时间戳进行存储，但必须保留表示的瞬时时间，且不得在跨仓库负载中暴露内部表示。

## 生产方验证

生成并验证已提交的契约包：

```bash
python scripts/repository_contracts.py --check
```

在发布前校验生产方契约文档：

```bash
python scripts/repository_contracts.py \
  --check \
  --verify-contract model-package-admission \
  --verify-document model-package.json
```

构建 CI 所需的确定性发布归档包：

```bash
python scripts/repository_contracts.py \
  --check \
  --bundle repository-contracts-1.2.0.zip
```

## 消费方兼容性

在准备后续契约版本时，针对上一个已发布目录运行候选版本：

```bash
python scripts/repository_contracts.py \
  --output-dir contracts/repository/v1.2.0 \
  --against contracts/repository/v1.1.0 \
  --check
```

兼容性门禁会解析本地 schema 引用，并自动拒绝新增必填属性、删除属性、枚举/联合类型缩窄、数据类型缩窄、新增收紧的字符串/数字/数组限制以及封闭额外属性。消费方仓库也应针对已发布的 schema 校验自身捕获的负载样本。

`--verify-document` 会同时运行 Draft 2020-12 校验与标准语义校验器。语义阶段会校验模型包与数据集引用的跨字段摘要一致性，并重新计算标准难例清单校验和。
