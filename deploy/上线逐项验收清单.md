# Scenara 生产部署检查清单

本清单用于把“配置可启动”与“产品可生产”分开。所有必选项完成前，不得将环境标记为生产合格。

## 发布身份

- 应用镜像使用 `repository@sha256:<digest>`，并与源码提交、OpenAPI 摘要、离线包摘要和模型集合摘要绑定。
- Contracts 固定为 `1.2.0`，Core、Data、Model 消费摘要必须一致。
- 运行 `python scripts/release_gate.py --implementation-only`；正式发布还必须运行严格门禁且无 pending 证据。

## 配置与凭据

- 使用 `scripts/generate_production_env.py` 生成独立随机凭据，环境文件权限为 `0600`。
- PostgreSQL、Redis、MinIO 根账号、应用 S3、Core→Data、Data→Core、API Bootstrap 凭据互不复用。
- Fernet 密钥在密码管理系统中备份并制定轮换/重加密方案。
- 生产主机、代理地址和 Data HTTPS 地址通过 `scripts/validate_production_config.py`。
- Bootstrap 管理员首次登录后创建实名管理员/服务账号并轮换 Bootstrap Token；禁止共享管理员账号。

## 网络与入口

- Compose API 默认只监听 `127.0.0.1`；外部流量经过 TLS 1.2/1.3 反向代理或受管负载均衡。
- 单机部署可从 `deploy/reverse-proxy/nginx.conf.example` 起步；Kubernetes 可参考 `deploy/kubernetes/ingress.example.yaml`。两者都是环境模板，域名、证书、请求体上限和代理地址必须显式替换。
- `SCENARA_ALLOWED_HOSTS` 精确列出域名，`SCENARA_FORWARDED_ALLOW_IPS` 只信任实际代理，二者禁止 `*`。
- 配置证书自动续期、HSTS、请求体上限、连接数/速率限制、SSE/WebSocket 长连接和访问日志脱敏。
- Kubernetes 使用默认拒绝 NetworkPolicy；按实际数据库、Redis、对象存储、Data、DNS、Webhook 和媒体源补充最小 egress。
- 只有完成摄像头网络与云元数据地址隔离后，才能开启私网媒体源或私网 Webhook。

## 数据与依赖

- PostgreSQL 使用专用业务用户、TLS、连接池、监控、时间点恢复和定期 VACUUM/ANALYZE。
- Redis 开启认证、AOF everysec、noeviction；确认 pending reclaim 和从 PostgreSQL/S3 重建队列流程。
- MinIO/S3 使用独立应用账号、桶级权限、版本化、生命周期、服务端加密、TLS 和异地备份。
- Scenara Data 独立部署，生产禁止使用 Core 内置 SQLite 兼容服务。
- 数据库迁移先备份、再运行迁移 Job，最后滚动发布 API；不支持破坏性 down migration。

## 模型与 GPU

- OCR、Behavior、Fashion 工厂必须来自批准的私有模型包；内置参考适配器会被生产校验拒绝。
- 每个模型包具备权属、许可证、模型卡、逐文件 SHA-256、固定评估集、两次独立评估和回归样例。
- Worker 使用显式 GPU 配额/设备隔离；并发数、批大小、显存水位和降级阈值来自目标硬件容量测试。
- GPU 驱动、CUDA、容器运行时和模型框架版本写入发布证据。

## 高可用与运维

- API 至少两个副本并配置 PDB、拓扑分散、startup/readiness/liveness 探针和滚动更新 `maxUnavailable=0`。
- Scheduler 保持单副本；切换必须依赖数据库幂等/租约，不允许两个不受控调度器同时工作。
- 为 API、Worker、PostgreSQL、Redis、对象存储配置 CPU、内存、PID、磁盘和 GPU 告警。
- 采集 5xx、p95/p99、队列 lag/pending、Webhook 死信、审计失败、对象删除失败、GPU OOM、重启和备份校验指标。
- 每个发布在隔离环境执行备份→破坏→恢复演练，并记录 RPO/RTO；定期执行离线安装和灾难恢复演练。

## 当前停止条件

代码和配置门禁已具备，但当前 dev.28 严格发布清单仍将以下项目标记为 pending：模型权属与各领域固定评估、GPU 容量、集成服务、安全评估、离线安装、备份恢复和软件许可证复核。缺少真实目标环境证据时，配置再完整也不能声明生产合格。
