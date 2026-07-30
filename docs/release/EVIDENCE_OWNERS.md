# 发布证据责任矩阵

仓库中的模板和自动化不能替代真实执行与签署。每份报告必须记录目标、执行时间、批准时间、签署人和 SHA-256。

| 证据类型 | 执行负责人 | 批准角色 | 必要场景 |
|---|---|---|---|
| `integration_services` | 平台工程 | 架构负责人 | PostgreSQL/pgvector、Redis、MinIO、幂等、恢复、删除 |
| `security_assessment` | 安全工程 | 安全负责人 | SSRF、恶意媒体、越权、凭证、审计失败关闭、生物信息删除 |
| `model_rights` | 模型治理 | 法务/合规负责人 | 全部生产模型来源、许可证、再分发与使用权 |
| `software_license_approval` | 法务/合规 | 法务负责人 | 软件许可证正文、商业分发权、LICENSE SHA-256 与受控批准记录 |
| `portrait_evaluation` | 人像算法 | 产品与算法负责人 | 固定、合法、脱敏、版本化评估集与预声明阈值 |
| `ocr_evaluation` | 文档算法 | 产品与算法负责人 | 中文、旋转、多页 PDF、阅读顺序与版面 |
| `gpu_capacity` | 性能工程 | 交付负责人 | 持续负载、突发、显存压力、背压、故障恢复 |
| `offline_install` | 交付工程 | 交付负责人 | 隔离网络空白目标机安装与校验 |
| `backup_restore` | 运维工程 | 运维负责人 | PostgreSQL + MinIO 恢复、RPO/RTO 与数据抽样一致性 |

严格门禁在缺少任何类型时失败关闭。不得将模板、跳过的测试或开发机结果签署为生产证据。
