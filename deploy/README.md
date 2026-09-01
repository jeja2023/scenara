# Scenara 景枢私有化部署

升级、恢复式回滚、运行探针、指标和告警基线见 [运维基线.md](运维基线.md)；上线逐项验收见 [上线逐项验收清单.md](上线逐项验收清单.md)。

支持的 1.0 目标系统为 Ubuntu x86_64，配备 Docker Engine、Docker Compose v2 和一个或多个可测量的 NVIDIA GPU。PostgreSQL/pgvector、Redis 和 MinIO 属于生产 Compose 拓扑的一部分。数据服务镜像通过清单摘要固定。Python 生产依赖项仅从 `requirements/production.lock` 安装，并经过 SHA-256 校验。

## 配置

在代码仓库外生成部署候选环境文件，然后填写外部端点、镜像摘要、允许的主机名和经过批准的模型工厂：

    python scripts/generate_production_env.py --output /secure/scenara.env
    python scripts/validate_production_config.py --env-file /secure/scenara.env

校验器不会打印机密值。在 Linux 上，它会拒绝具有组/全局可读权限的环境文件、跨信任边界复用的机密、过短的凭证、无效的 Fernet 密钥、通配符 Host/代理信任、未经认证的内置适配器、可变的镜像引用以及非 TLS 的 Data URL（除非显式允许隔离的内部 HTTP）。

默认的 `deploy/compose.yml` 为个人部署配置文件。它使用本地策略提供者，不需要、不读取也不挂载企业许可证。签名企业策略实现作为可选扩展提供。要启用它，请将 `SCENARA_ENTERPRISE_LICENSE_FILE` 和 `SCENARA_ENTERPRISE_PUBLIC_KEY_FILE` 设置为可读文件，并在每个 Compose 命令中添加 `-f deploy/compose.enterprise.yml`。

每个 GPU worker 只请求一张 GPU，避免批处理和实时任务默认同时占用所有显卡。Compose 运行时负责容器级 GPU 隔离；仅在完成容量验证后，才通过 `SCENARA_BATCH_GPU_DEVICE_IDS` 与 `SCENARA_STREAM_GPU_DEVICE_IDS` 固定应用内模型缓存的设备选择。传统推理适配器从容器可见的 CUDA 设备节点或 `nvidia-smi` 发现设备。

HTTP multipart 直传默认限制为 512 MiB，并在 API 读取请求体前按 `Content-Length` 拒绝超限请求；流式落盘仍会对实际字节数复核。更大的媒体必须使用 S3 预签名上传和完成确认接口。`SCENARA_MAX_MEDIA_BYTES` 是资产总上限，不是 API 直传额度。生产容器应同时为临时目录预留至少一个直传上限的空间。

PostgreSQL 连接池默认每进程 `1..4` 条连接。调整 API/worker 副本前，先计算“全部副本 × `SCENARA_POSTGRES_POOL_MAX_SIZE`”，再为迁移、监控和数据库保留连接预留容量；达到数据库连接上限前应部署 PgBouncer。

经过认证的模型包目录必须包含由 `SCENARA_OCR_ENGINE_FACTORY`、`SCENARA_BEHAVIOR_ENGINE_FACTORY` 和 `SCENARA_FASHION_ENGINE_FACTORY` 指定的私有 OCR、Behavior 和 Fashion 适配器模块。每个工厂必须返回一个具有不可变模型标识、`production_ready=true`、所需推理方法和声明能力的合格引擎。Compose 将此目录只读挂载在 `/opt/scenara/models`。内置的参考适配器在生产校验中会被显式拒绝。

在不启动服务的情况下进行验证。Compose `preflight` 一次性服务在 API 启动前重复运行时验证：

    docker compose --env-file /secure/scenara.env -f deploy/compose.yml config --quiet

在 CI 中构建并推送发布镜像，将其摘要记录在 `SCENARA_IMAGE_REFERENCE` 中，然后在 TLS 反向代理后启动。请勿对固定摘要的生产引用使用 `--build`。默认的主机绑定为 `127.0.0.1:8000`；直接非回环 HTTP 访问需要显式的不安全覆盖配置：

    docker compose --env-file /secure/scenara.env -f deploy/compose.yml pull
    docker compose --env-file /secure/scenara.env -f deploy/compose.yml run --rm preflight
    docker compose --env-file /secure/scenara.env -f deploy/compose.yml run --rm migrate
    docker compose --env-file /secure/scenara.env -f deploy/compose.yml up -d --no-build --wait

对于可选的企业配置文件，使用这两个文件进行验证和启动：

    docker compose --env-file /secure/scenara.env \
      -f deploy/compose.yml -f deploy/compose.enterprise.yml config --quiet

    docker compose --env-file /secure/scenara.env \
      -f deploy/compose.yml -f deploy/compose.enterprise.yml run --rm preflight

    docker compose --env-file /secure/scenara.env \
      -f deploy/compose.yml -f deploy/compose.enterprise.yml up -d --no-build --wait

API 健康检查通过后，通过配置的 TLS 域名打开内置的中文控制台，例如 `https://scenara.example.com/console/`。8000 端口仍仅限回环访问。相同的版本化镜像同时提供 API 和控制台服务，因此离线部署不会意外混合不同的契约版本。

私有 RTSP/RTMP/HTTP 源地址默认被拒绝。仅当部署网络将 worker 与管理和元数据端点隔离时，才设置 `SCENARA_ALLOW_PRIVATE_MEDIA_SOURCES=true`；URL 凭证在配置的机密存储中保持加密。

API、批处理 worker、流式 worker 和调度器共享同一个版本化镜像。批处理和实时运行使用独立的 Redis 流消费者组。

## 离线安装包

在联网的 Ubuntu 构建主机上：

    SCENARA_COMPOSE_ENV_FILE=deploy/.env.production \
      SCENARA_MODEL_BUNDLE_DIR=/secure/qualified-model-packages \
      deploy/scripts/build-offline-bundle.sh /srv/scenara-release

通过项目的受控渠道传输生成的 tar 压缩包，解压后在目标机器上安装：

    deploy/scripts/install-offline.sh \
      /srv/scenara-offline-0.3.0-dev.42 \
      /secure/scenara.env \
      /secure/offline-installer-result.json

经过认证的模型包目录是必需的，并被复制到带校验和的离线包中；仓库从不提供或替换模型权重。在加载镜像之前，安装程序会验证 Ubuntu 24.04 x86_64、Docker Engine 27+、Docker Compose 2.29+、CUDA 12.8 驱动兼容性以及至少一个可测量的 NVIDIA GPU。每个 GPU worker 默认只请求一张 GPU；安装程序记录 GPU 数量和总显存，但不施加固定的 GPU 数量或显存限制。它使用 `--no-build --wait` 启动 Compose，验证依赖就绪端点和中文控制台，并拒绝任何未运行的必需服务。可选的第三个参数以 schema-version 1.0 JSON 结果原子写入，且不允许覆盖现有文件。

构建器还会在压缩包旁写入 `scenara-offline-<tag>.release-identity.json`。它记录了严格发布清单所需的源提交、应用镜像摘要、压缩包 SHA-256、OpenAPI SHA-256 以及聚合的合格模型集 SHA-256。请将此伴随文件与发布产物一起保存。

本仓库不捆绑模型权重。仅安装符合 [模型资产政策.md](../模型资产政策.md) 并通过严格发布证据门禁的模型包。

## 备份与恢复

创建并验证 PostgreSQL 与 MinIO 备份：

    SCENARA_COMPOSE_ENV_FILE=/secure/scenara.env \
      deploy/scripts/backup.sh /srv/backups/scenara-2026-07-29

恢复操作具有破坏性，需要显式确认：

    SCENARA_COMPOSE_ENV_FILE=/secure/scenara.env \
      deploy/scripts/restore.sh /srv/backups/scenara-2026-07-29 --confirm

Redis 被显式排除在备份之外，因为它是投递、租约和短期事件服务，而非记录系统。PostgreSQL 和 MinIO 在 worker 重启前恢复。

CI 可以设置 `SCENARA_RESTORE_DATA_ONLY=true` 来演练 PostgreSQL 和 MinIO 的恢复，而不启动 GPU worker。此模式不能作为有效的 1.0 发布证据；目标主机演练必须使用默认的完整重启路径。

备份记录容器镜像名称、Compose 版本、部署文件的 SHA-256 和源码提交溯源。解析后的 Compose 配置被显式排除，因为它包含部署机密。

脚本运行成功本身不能作为发布证据。请在严格证据清单中记录目标、执行时间戳、校验和、恢复目标以及观察到的数据丢失窗口。
