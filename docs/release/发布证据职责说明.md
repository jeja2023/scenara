# 发布证据职责说明

Scenara 当前为个人开发项目。因此，证据契约仅通过报告的执行目标环境与可复现输出来记录执行校验的人员。不强制要求指定审批人、审批时间戳、法务审批人或受控审批记录编号。

| 证据类型 | 项目执行校验 | 所需客观覆盖范围 |
|---|---|---|
| `integration_services` | 运行集成测试套件 | PostgreSQL/pgvector、Redis、MinIO，无跳过测试，无重复逻辑结果，Redis 队列重建验证 |
| `security_assessment` | 运行安全测试套件 | SSRF、恶意媒体输入、权限授权、凭据脱敏、审计关闭式防篡改、生物特征删除 |
| `model_rights` | 记录模型清单与权利状态 | 每个模型均具备版本、制品 SHA-256、许可证标识符、源 URI 及权利合规标志 |
| `software_license` | 计算哈希、识别并自检仓库 `LICENSE` | 确切的 `LICENSE` SHA-256、SPDX 标识符与条款完整性自检范围；无外部法务审批声明 |
| `portrait_evaluation` | 运行固定人像评估 | 版本化合规数据集、固定阈值、容差范围内的两次运行 |
| `ocr_evaluation` | 运行固定 OCR 评估 | 版本化合规数据集、固定阈值、容差范围内的两次运行 |
| `behavior_evaluation` | 运行固定行为分析评估 | 版本化合规视频数据集、行为 F1、时间 IoU、容差范围内的两次运行 |
| `fashion_evaluation` | 运行固定服饰分析评估 | 版本化合规数据集、分类 F1、检测 mAP、容差范围内的两次运行 |
| `gpu_capacity` | 在目标 GPU 上运行容量实测负载 | 持续负载、突发流量、显存压力、背压机制、故障恢复、延迟与吞吐量指标 |
| `offline_install` | 在隔离空白主机上执行离线安装 | 校验和、健康检查探针、控制台、示例客户端、核心解析链路 |
| `backup_restore` | 运行备份与灾难恢复演练 | RPO/RTO 指标以及全部必需业务实体的恢复验证 |

每种证据类型在 `docs/release/evidence/manifest.json` 中恰好出现一次。当尚未执行检查时使用 `pending` 状态。`passed` 条目必须包含其报告路径、报告 SHA-256、执行时间、目标环境、发布身份以及类型特定的元数据。在任何必需证据处于 pending 状态时，发布门禁严格保持关闭（fail-closed）。
