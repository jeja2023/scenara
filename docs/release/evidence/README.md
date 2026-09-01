# Scenara 发布证据管理规范

`manifest.json` 始终对应当前开发发布；上一发布的证据清单按版本归档，例如 `manifest.0.3.0-dev.25.json`。证据不得跨版本自动继承，新版本必须重新记录 source commit、镜像、OpenAPI、模型集合和目标环境身份。

本目录记录 Scenara 个人项目的客观发布证据。不需要指定审批人、审批时间戳、法务审批人或受控审批记录编号。

实现发布门禁：

    python scripts/release_gate.py --implementation-only

严格发布门禁：

    python scripts/release_gate.py

在真实资格认证运行后记录已完成的报告：

    python scripts/record_release_evidence.py /secure/result.json

直接从原始资质认证结果生成候选报告（该命令仅对客观事实进行标准化，除非通过完全相同的 `validate_entry` 契约，否则拒绝写入输出）：

    python scripts/prepare_release_evidence.py gpu_capacity /secure/gpu-result.json \
      --target 'Ubuntu 24.04 qualification host with measured NVIDIA device' \
      --output /secure/gpu-capacity-report.json

关于算法评估、GPU 算力容量、模型权利和离线安装的确切输入契约与端到端命令，详见 [QUALIFICATION_INPUTS.md](QUALIFICATION_INPUTS.md)。

每个顶级资格输入均使用 schema version 1.0，且证据类型与执行命令相匹配。相对路径根据该输入文件进行解析。生成器自行读取引用的文件并计算其 SHA-256 值；不接受调用方提供的摘要作为替代品。报告绝不从缺失或预估的数值合成，且绝不覆盖已存在的输出。

记录器仅接受 `schema_version: "1.0"`、`status: "passed"` 且发布身份与清单匹配的报告。它会验证客观元数据，原子地写入标准报告，计算其 SHA-256，并替换对应的 pending 条目。它不会凭空创建证据或将不完整的结果转为通过。

严格门禁要求清单满足 `schema_version: "1.2"`，且 `manifest.example.json` 中列出的每种证据类型恰好有一个条目。在项目开发期间，条目可以为 `pending`。处于 pending 状态的条目仅包含 `evidence_type` 和 `status`；不得声明报告路径、摘要、执行时间或元数据。在每个条目均变为 `passed` 之前，严格门禁保持关闭状态（fail-closed）。

每个 passed 报告必须是 `docs/release/evidence/reports/` 下的 UTF-8 JSON 文件，使用报告 `schema_version: "1.0"`，并完整对应清单条目的证据类型、状态、执行时间、目标环境、发布身份与元数据。清单保存报告经验证的 SHA-256。报告必须使用真实执行目标和精确、可复现的元数据；占位符与跳过的检查均不构成有效证据。

发布身份将已完成的证据绑定到一个完整 Git commit、应用镜像摘要、离线包 SHA-256、OpenAPI SHA-256 和模型集合 SHA-256。在个人项目开发期间，若有任何证据仍处于 pending 状态，这些值可为 `null`。已完成的正式发布必须填充每个身份字段，并与迁出的 Git commit 及仓库 OpenAPI 摘要严格匹配。

算法评估报告必须指明固定的、版本化的、权利合规的数据集、执行前固定的阈值，以及容差范围内的两次独立运行。容量证据必须来自受支持的目标硬件，并包含延迟分位数、吞吐量、错误率、峰值显存、持续负载、突发、压力、背压和恢复指标。模型权利证据必须记录每个生产模型的 ID、版本、制品 SHA-256、许可证标识符、源 URI 和权利合规标志。集成、安全、模型权利、软件许可证、离线安装和备份报告必须包含示例清单中展示的必需客观元数据。

软件许可证证据绑定确切的 MIT `LICENSE` SHA-256 与 SPDX 标识符，并记录个人项目许可证自检所覆盖的章节。这是一项条款完整性检查，而非外部法律建议；它不声明公司法务审批或受控审批记录。

## 模型发布资格认证对象

受控的模型生命周期使用已配置对象存储中的证据对象。每个引用必须使用以下确切形式：

    tenants/<tenant>/projects/<project>/model-evidence/<name>.json#sha256=<64位小写十六进制字符>

引用的 UTF-8 JSON 对象使用 `schema_version: "1.0"`、`status: "passed"`，并记录 `model_id`、`model_version`、`package_sha256`、带时区的 `executed_at` 以及类型特定的 `details`。指定审批人字段不属于个人项目发布证据契约的一部分。模型 ID、版本、包摘要、对象摘要、租户和项目必须与发布请求严格匹配。

超越 `candidate` 阶段的每一次状态流转都需要唯一的 `model_rights`、领域评估（`portrait_evaluation` 或 `ocr_evaluation`）和 `regression` 对象。权利证据必须设置 `rights_cleared: true`；评估证据必须记录至少两次独立运行、执行前固定的阈值以及容差范围内的结果；回归证据必须设置 `regressions_passed: true`。缺失、不可读、重复、被篡改、不匹配或占位符证据均会导致门禁关闭失败（fail closed）。
