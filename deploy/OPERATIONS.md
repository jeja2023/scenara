# Scenara 1.0 运维基线

本文档定义单节点、多 GPU 私有化部署的升级、回滚、探针、指标和告警最低要求。它不能替代目标环境的可复现演练报告。

## 数据库升级

`deploy/scripts/migrate.sh` 按文件名顺序扫描 `migrations/*.sql`，并以 `scenara_schema_migrations` 为权威记录，只执行尚未应用的迁移。已经发布的迁移文件不可修改；每次 schema 变化必须新增连续编号文件，例如 `0002_add_delivery_index.sql`。迁移文件必须在自身的 `BEGIN`/`COMMIT` 事务中写入同名版本记录；脚本会在执行后验证该记录，避免结构变更与版本登记分离。

迁移必须满足：

- 使用 `BEGIN`/`COMMIT` 保证单文件原子性；
- 对大表操作先在生产规模副本验证锁等待和磁盘增长；
- 新代码先兼容旧 schema，再迁移，最后在后续版本移除旧字段；
- CI 必须验证空库安装和上一支持版本升级两条路径。

## 依赖与镜像复现

- `requirements/production.in` 是生产依赖输入，`requirements/production.lock` 是生产镜像和离线包唯一允许使用的解析结果；安装和下载必须启用 `--require-hashes`。
- 修改生产依赖后必须用固定的 uv 版本为 Python 3.12、x86_64 manylinux 目标重新生成锁文件；CI 会再次生成并拒绝任何漂移。
- PostgreSQL/pgvector、Redis 和 MinIO 镜像在 Compose 中使用 manifest digest。联网发布构建还必须记录 Node、CUDA 基础镜像的实际 digest，并以最终应用镜像 digest 进入发布身份。
- 离线包摘要、应用镜像 digest、OpenAPI 摘要、模型集合摘要和源提交共同构成发布身份；任一值变化都必须重新执行并记录九类发布证据。
- 生产配置先运行 `python scripts/validate_production_config.py --env-file /secure/scenara.env`；环境文件保持 `0600`，凭据不跨 PostgreSQL、Redis、MinIO 根账号、应用 S3、Data 双向信任与 API Bootstrap 边界复用。
- API 默认仅绑定回环地址，由受管 TLS 反向代理提供证书续期、请求体上限、连接/速率限制和访问日志。`SCENARA_ALLOWED_HOSTS` 与 `SCENARA_FORWARDED_ALLOW_IPS` 必须精确到实际域名和代理地址，禁止 `*`。

## 升级与恢复式回滚

1. 记录当前 commit、镜像 digest、Compose 文件 SHA-256 和数据库迁移版本。
2. 使用 `deploy/scripts/backup.sh` 生成并验证 PostgreSQL 与 MinIO 备份。
3. 停止 batch worker、stream worker 和 scheduler，等待正在执行的 Run 到达可恢复状态。
4. 加载已校验的新镜像和模型包，先运行 `docker compose run --rm preflight` 和 `docker compose run --rm migrate`，再执行 `docker compose up -d --no-build --wait`。
5. 检查 `/livez`、`/readyz`、`/console/`、示例客户端和核心 Parse 链路。
6. 若升级失败，停止全部服务，使用 `deploy/scripts/restore.sh BACKUP --confirm` 恢复数据库和对象，再加载上一镜像及模型包。

Scenara 1.0 不提供破坏性 down migration。发生不兼容 schema 变更时，唯一受支持的回滚方式是恢复升级前备份。升级演练必须记录实际 RPO、RTO 和抽样一致性。

## 探针与指标

- `/livez` 只证明 API 进程可响应。
- `/readyz` 检查 PostgreSQL/内存状态存储、S3/本地对象存储和 Redis/内联队列；任一失败返回 503。
- `/metrics` 输出 Prometheus 文本并沿用 API 认证策略，生产抓取任务必须携带 Bearer Token。
- `/healthz` 为兼容性存活探针；新部署应使用 `/livez` 和 `/readyz`。

最低告警集合：API readiness 连续失败、HTTP 5xx 比例、p95/p99 延迟、Redis pending/lease 恢复、Webhook 死信、对象删除失败、审计写入失败、GPU 显存压力、worker 重启和备份校验失败。阈值必须来自目标 GPU 容量报告，不能使用开发机数据。

## Run 长时间 queued 排查

`/readyz` 能证明 API、Redis 和对象存储可连接，但不代表 Redis stream 已经有 worker 消费者。Run 长时间停留在 `queued` 时，先确认对应队列 lane 的 worker：图片、视频和文档使用 `batch`，实时流使用 `stream`。

- Docker Compose：执行 `docker compose ps api batch-worker stream-worker`，再查看 `docker compose logs --tail=100 batch-worker`；生产环境必须同时运行 `batch-worker` 和 `stream-worker`。
- 本地启动：使用 `python start.py` 重新启动；当 `.env` 配置 `SCENARA_QUEUE_BACKEND=redis` 时，启动器会自动拉起两个 worker，旧版启动进程不会热加载此行为。
- Redis 侧：检查 `scenara:runs:batch` / `scenara:runs:stream` 的 consumer group、pending 数和 lag。只有 API 在写 stream、没有消费者时，Run 会持续显示 `queued`，图片解码器本身尚未开始执行。
- worker 启动后若仍不前进，检查模型加载日志、CUDA/CPU provider、PostgreSQL/S3 连接和 `QUEUE_UNAVAILABLE` / `PIPELINE_ERROR`；首次加载模型可能需要数秒到数十秒，但不应无限停留在 `queued`。

## Redis Run queue recovery

PostgreSQL is the source of truth for Run state and the certified S3 provider retains uploaded media. If Redis Run streams are lost, stop both workers and run the following command before restarting them:

    python scripts/rebuild_redis_queue.py --env-file deploy/.env.production

The command requires PostgreSQL, S3/MinIO, and Redis backends. It enumerates every non-terminal Run, verifies each retained media object, and atomically repopulates the empty batch and stream queues. It refuses to run when either Redis Run stream already contains messages, or when a Run record or required media object is missing. The JSON output records the number of recoverable, verified, and enqueued Runs for release evidence.

## 已知限制


- 支持 Ubuntu 24.04 x86_64、Docker Compose 和一张或多张可被 `nvidia-smi` 测量的 NVIDIA GPU；生产 Compose 默认将所有可见 GPU 提供给 GPU Worker，显存容量记录在资格报告中，但不设固定 GPU 数量或显存门槛。
- 不提供多节点高可用、跨地域容灾、在线 schema 降级或自动模型训练。
- 发布仓库当前仍缺目标 GPU、模型权利、固定评估集和隔离离线安装等严格门禁要求的客观证据；缺失时不得声明 1.0 Released。
