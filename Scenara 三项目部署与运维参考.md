
# Scenara 三项目部署与运维参考

本文档总结本次实际部署中验证过的流程，供以后全新部署、版本更新、故障排查和密钥轮换使用。

适用仓库：

- scenara：Core/API、Scheduler、Batch Worker、Stream Worker
- scenara-data：Data API、Outbox Worker、数据库迁移
- scenara-model：Model API、数据库迁移

当前方案是“正式生产配置下的测试环境”：

- PostgreSQL、Redis、MinIO 由一个共享基础设施项目统一管理。
- Core 使用 Docker Compose。
- Data 和 Model 使用 Docker Swarm Stack，因为它们使用 Docker secrets。
- 没有公网 IP 或公网域名时，使用 Docker 内部 DNS、内部 CA 和 HTTPS。
- 当前没有训练产生的正式模型时，只能完成基础设施和服务部署验收，不能宣称完成最终模型生产验收。

> 安全要求：本文档不包含任何真实密码、Token、S3 Secret、Fernet key 或 CA 私钥。真实密钥只保存在服务器的环境文件、Docker secrets 和证书目录中，不能提交到 GitHub、聊天记录、截图或日志。

## 1. 架构和固定地址

共享 Docker 网络名称：

    scenara-platform

Docker 内部服务地址：

| 服务 | 地址 |
|---|---|
| PostgreSQL | postgres.scenara.internal:5432 |
| Redis TLS | redis.scenara.internal:6379 |
| MinIO S3 | https://minio.scenara.internal:9000 |
| Core | https://core.scenara.internal:8000 |
| Data | https://data.scenara.internal:8081 |
| Model | https://model.scenara.internal:8080 |

数据库：

| 项目 | 数据库 |
|---|---|
| Core | scenara |
| Data | scenara_data |
| Model | scenara_model |

MinIO 应使用独立用户和最小权限策略：

- scenara-core
- scenara-data
- scenara-model

不要让 Core、Data、Model 各自创建 PostgreSQL、Redis 或 MinIO 容器。

## 2. Ubuntu 服务器目录

以下命令均在 Ubuntu 服务器执行。

    mkdir -p ~/project ~/scenara-env
    cd ~/project

首次克隆：

    git clone https://github.com/jeja2023/scenara.git
    git clone https://github.com/jeja2023/scenara-data.git
    git clone https://github.com/jeja2023/scenara-model.git

检查仓库：

    git -C ~/project/scenara status
    git -C ~/project/scenara-data status
    git -C ~/project/scenara-model status

以后更新：

    git -C ~/project/scenara pull --ff-only origin main
    git -C ~/project/scenara-data pull --ff-only origin main
    git -C ~/project/scenara-model pull --ff-only origin main

偶发 gnutls_handshake failed 通常是 GitHub 网络连接瞬断，重试即可，不要因此执行 git reset --hard 或删除工作区。

检查部署文件：

    test -f ~/project/scenara/deploy/shared-infra/compose.yml
    test -f ~/project/scenara/deploy/shared-infra/compose.tls.yml
    test -f ~/project/scenara/deploy/compose.yml
    test -f ~/project/scenara-data/deploy/compose.production.yml
    test -f ~/project/scenara-model/deploy/compose.production.yml

环境文件：

    /home/<user>/scenara-env/scenara-infra.env
    /home/<user>/scenara-env/scenara-core.env
    /home/<user>/scenara-env/scenara-data.env
    /home/<user>/scenara-env/scenara-model.env

保护目录和文件：

    chmod 700 /home/<user>/scenara-env
    chmod 600 /home/<user>/scenara-env/*.env

## 3. 内部 CA 和服务证书

没有公网域名时，使用内部 CA 给 postgres、redis、minio、core、data、model 签发证书。

首次生成：

    sudo mkdir -p /secure/scenara-certs

    sudo ~/project/scenara/deploy/shared-infra/scripts/generate-internal-ca.sh \
      /secure/scenara-certs

检查文件：

    sudo find /secure/scenara-certs -maxdepth 2 -type f | sort

检查证书链：

    for service in postgres redis minio core data model; do
      sudo openssl verify \
        -CAfile /secure/scenara-certs/ca/ca.crt \
        /secure/scenara-certs/$service/server.crt
    done

每个服务都应显示 OK。

私钥权限：

    sudo chmod 600 /secure/scenara-certs/postgres/server.key
    sudo chmod 600 /secure/scenara-certs/redis/server.key
    sudo chmod 600 /secure/scenara-certs/core/server.key
    sudo chmod 600 /secure/scenara-certs/data/server.key
    sudo chmod 600 /secure/scenara-certs/model/server.key
    sudo chmod 600 /secure/scenara-certs/minio/server.key

PostgreSQL 对私钥权限最严格，出现 private key file has group or world access 时，优先检查 postgres/server.key 是否为 0600。

环境文件中的证书配置：

    SCENARA_PLATFORM_CERTS_DIR=/secure/scenara-certs
    SCENARA_PLATFORM_CA_FILE=/run/tls/ca.crt

## 4. 关键环境变量

### 4.1 Core

    SCENARA_POSTGRES_DSN=postgresql://scenara:<core-db-password>@postgres.scenara.internal:5432/scenara?sslmode=verify-full&sslrootcert=/run/tls/ca.crt
    SCENARA_REDIS_URL=rediss://:<redis-password>@redis.scenara.internal:6379/0?ssl_cert_reqs=required&ssl_ca_certs=/run/tls/ca.crt
    SCENARA_S3_ENDPOINT_URL=https://minio.scenara.internal:9000
    SCENARA_DATA_PLATFORM_URL=https://data.scenara.internal:8081
    SCENARA_S3_VERIFY_TLS=true

### 4.2 Data

    SCENARA_DATA_CORE_EVENT_ENDPOINT=https://core.scenara.internal:8000/internal/v1/data/events
    SCENARA_DATA_CORS_ALLOW_ORIGINS=https://core.scenara.internal:8000
    SCENARA_DATA_S3_ENDPOINT_URL=https://minio.scenara.internal:9000
    SCENARA_DATA_S3_REGION=us-east-1

### 4.3 Model

    SCENARA_MODEL_DATA_PLATFORM_URL=https://data.scenara.internal:8081
    SCENARA_MODEL_S3_ENDPOINT_URL=https://minio.scenara.internal:9000
    SCENARA_MODEL_S3_REGION=us-east-1

us-east-1 是 S3 API 的逻辑区域标识，不代表服务器时区，不会影响东八区时间。

Data 和 Model 的生产文件必须使用：

    SCENARA_DATA_DATABASE_URL_FILE=/run/secrets/data_database_url
    SCENARA_MODEL_DATABASE_URL_FILE=/run/secrets/model_database_url

不要同时提供同一个 secret 的内联值和 FILE 配置，避免应用报 value and file both configured。

## 5. 密码、Token、S3 Secret 和 Fernet key

### 5.1 通用随机值

    openssl rand -hex 32

该命令生成 64 个十六进制字符，等价于 32 字节随机数。可用于密码、Token、S3 Secret 和上下文签名密钥。

需要至少 24 个字符的密码也使用同样命令。

S3 Access Key 可以使用稳定的用户标识：

    scenara-core
    scenara-data
    scenara-model

S3 Secret Key 必须为每个用户单独生成，不能三个项目复用同一个值。

### 5.2 Fernet key

SCENARA_SECRET_ENCRYPTION_KEY 不是普通 hex 字符串，必须使用 Fernet 格式：

    sudo docker run --rm \
      scenara-api:<core-image-tag> \
      python3 -c \
      "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

检查长度而不显示值：

    sudo awk -F= \
      '$1=="SCENARA_SECRET_ENCRYPTION_KEY" { print "Fernet key length:", length($2) }' \
      /home/<user>/scenara-env/scenara-core.env

结果应为 43。

### 5.3 上下文签名密钥关系

这组密钥不能混用：

| Secret | 要求 |
|---|---|
| model_context_signing_key | 必须与 model_service_token 不同 |
| model_service_token | Model 服务身份 Token，单独生成 |
| data_context_signing_key | 必须与 model_data_context_signing_key 相同 |
| model_data_context_signing_key | 必须等于 data_context_signing_key |
| data_service_token | Data 服务身份 Token，单独生成 |
| model_data_service_token | Model 访问 Data 的 Token，单独生成 |

生成示意：

    data_context_key="$(openssl rand -hex 32)"
    model_context_key="$(openssl rand -hex 32)"
    model_service_token="$(openssl rand -hex 32)"
    data_service_token="$(openssl rand -hex 32)"
    model_data_service_token="$(openssl rand -hex 32)"

    test "$model_context_key" != "$model_service_token"

data_context_key 的值同时用于 data_context_signing_key 和 model_data_context_signing_key；model_context_key 不能复用它。

### 5.4 生成 Core 密钥文件

使用 umask 077，避免生成文件被其他用户读取：

    umask 077
    touch /home/<user>/scenara-env/core-generated-secrets.env
    chmod 600 /home/<user>/scenara-env/core-generated-secrets.env

文件每行必须是 KEY=VALUE，不能把说明文字或带行号文本写进去。格式检查：

    sudo awk '
    /^[[:space:]]*$/ { next }
    /^[A-Z][A-Z0-9_]*=/ { next }
    { print "invalid line:", NR }
    ' /home/<user>/scenara-env/core-generated-secrets.env

无输出才表示格式正确。

建议的 Core 密钥名：

    SCENARA_POSTGRES_PASSWORD
    SCENARA_REDIS_PASSWORD
    SCENARA_BOOTSTRAP_ADMIN_PASSWORD
    SCENARA_API_TOKEN
    SCENARA_S3_SECRET_KEY
    SCENARA_DATA_PLATFORM_SERVICE_TOKEN
    SCENARA_DATA_EVENT_SERVICE_TOKEN
    SCENARA_DATA_CONTEXT_SIGNING_KEY
    SCENARA_SECRET_ENCRYPTION_KEY

不能把同一个值复制到多个信任边界。尤其 API token、Data service token、S3 secret、Fernet key 必须分别生成。

## 6. 启动共享基础设施

### 6.1 配置检查

    cd ~/project/scenara

    sudo docker compose \
      --env-file /home/<user>/scenara-env/scenara-infra.env \
      -f deploy/shared-infra/compose.yml \
      -f deploy/shared-infra/compose.tls.yml \
      config --quiet

没有输出表示配置解析通过。

### 6.2 启动 PostgreSQL、Redis、MinIO

    sudo docker compose -p scenara-infra \
      --env-file /home/<user>/scenara-env/scenara-infra.env \
      -f deploy/shared-infra/compose.yml \
      -f deploy/shared-infra/compose.tls.yml \
      up -d --wait postgres redis minio

检查：

    sudo docker compose -p scenara-infra \
      --env-file /home/<user>/scenara-env/scenara-infra.env \
      -f deploy/shared-infra/compose.yml \
      -f deploy/shared-infra/compose.tls.yml \
      ps

三个容器都应为 healthy。

### 6.3 初始化 PostgreSQL

    sudo docker compose -p scenara-infra \
      --env-file /home/<user>/scenara-env/scenara-infra.env \
      -f deploy/shared-infra/compose.yml \
      -f deploy/shared-infra/compose.tls.yml \
      run --rm postgres-init

正常结果：

    shared PostgreSQL databases are ready: scenara, scenara_data, scenara_model

重复执行时 extension already exists, skipping 属于正常幂等输出。

### 6.4 初始化 MinIO

    sudo docker compose -p scenara-infra \
      --env-file /home/<user>/scenara-env/scenara-infra.env \
      -f deploy/shared-infra/compose.yml \
      -f deploy/shared-infra/compose.tls.yml \
      run --rm minio-init

正常结果：

    shared MinIO buckets and least-privilege users are ready

如果出现 x509: certificate signed by unknown authority，先确认脚本、compose.tls.yml 和 CA 挂载来自最新 scenara 仓库，不要把关闭 TLS 验证作为长期修复。

## 7. Docker Swarm 和共享网络

检查 Swarm：

    sudo docker info --format '{{.Swarm.LocalNodeState}}'

如果 inactive，使用当前服务器局域网 IP：

    hostname -I
    sudo docker swarm init --advertise-addr <服务器局域网IP>

例如：

    sudo docker swarm init --advertise-addr 192.168.1.100

以后换到另一个局域网时，advertise IP 可能需要重新配置。不要把旧 IP 当成永久值。

创建共享 overlay 网络：

    sudo docker network inspect scenara-platform >/dev/null 2>&1 || \
    sudo docker network create \
      --driver overlay \
      --attachable \
      scenara-platform

如果出现 network is declared as external, but it is not in the right scope: local instead of swarm，说明同名网络是 bridge 网络，不是 overlay 网络。

## 8. 创建 Docker secrets

Data 和 Model 的生产 Compose 文件依赖 Docker secrets。必须先创建 secrets，再部署 Stack；普通 docker compose run 不能代替 Swarm secrets。

检查已有 secrets：

    sudo docker secret ls --format '{{.Name}}' | sort

需要的名称：

    data_context_signing_key
    data_core_event_token
    data_database_url
    data_s3_access_key_id
    data_s3_secret_access_key
    data_service_token
    data_service_tokens
    model_context_signing_key
    model_database_url
    model_data_context_signing_key
    model_data_service_token
    model_deployment_feedback_secret
    model_s3_access_key
    model_s3_secret
    model_service_token

创建模板：

    printf '%s' "$(openssl rand -hex 32)" | sudo docker secret create data_context_signing_key -
    printf '%s' "$(openssl rand -hex 32)" | sudo docker secret create data_core_event_token -
    printf '%s' '<data-database-url>' | sudo docker secret create data_database_url -
    printf '%s' 'scenara-data' | sudo docker secret create data_s3_access_key_id -
    printf '%s' "$(openssl rand -hex 32)" | sudo docker secret create data_s3_secret_access_key -
    printf '%s' "$(openssl rand -hex 32)" | sudo docker secret create data_service_token -
    printf '%s' '<trusted-token-list>' | sudo docker secret create data_service_tokens -

    printf '%s' "$(openssl rand -hex 32)" | sudo docker secret create model_context_signing_key -
    printf '%s' '<model-database-url>' | sudo docker secret create model_database_url -
    printf '%s' '<same-value-as-data_context_signing_key>' | sudo docker secret create model_data_context_signing_key -
    printf '%s' "$(openssl rand -hex 32)" | sudo docker secret create model_data_service_token -
    printf '%s' "$(openssl rand -hex 32)" | sudo docker secret create model_deployment_feedback_secret -
    printf '%s' 'scenara-model' | sudo docker secret create model_s3_access_key -
    printf '%s' "$(openssl rand -hex 32)" | sudo docker secret create model_s3_secret -
    printf '%s' "$(openssl rand -hex 32)" | sudo docker secret create model_service_token -

data_database_url 示例：

    postgresql://scenara_data:<password>@postgres.scenara.internal:5432/scenara_data?sslmode=verify-full&sslrootcert=/run/tls/ca.crt

model_database_url 示例：

    postgresql://scenara_model:<password>@postgres.scenara.internal:5432/scenara_model?sslmode=verify-full&sslrootcert=/run/tls/ca.crt

检查 secret 是否齐全而不读取内容：

    missing=''
    for name in \
      data_context_signing_key data_core_event_token data_database_url \
      data_s3_access_key_id data_s3_secret_access_key data_service_token \
      data_service_tokens model_context_signing_key model_database_url \
      model_data_context_signing_key model_data_service_token \
      model_deployment_feedback_secret model_s3_access_key model_s3_secret \
      model_service_token; do
      sudo docker secret inspect "$name" >/dev/null 2>&1 || missing="$missing $name"
    done
    test -z "$missing" && echo 'all required secrets exist' || echo "missing:$missing"

## 9. Core 配置检查和部署

### 9.1 Compose 配置和 Preflight

    cd ~/project/scenara

    sudo docker compose \
      --env-file /home/<user>/scenara-env/scenara-core.env \
      -f deploy/compose.yml \
      config --quiet

    sudo docker compose \
      --env-file /home/<user>/scenara-env/scenara-core.env \
      -f deploy/compose.yml \
      run --rm preflight

尚未有训练产生的正式模型时，测试阶段可使用：

    SCENARA_MODEL_VALIDATION_MODE=reference
    SCENARA_PRODUCTION_MODELS_REQUIRED=false

但不能把 engine factory 简单置空。若 preflight 报：

    SCENARA_OCR_ENGINE_FACTORY is required
    SCENARA_BEHAVIOR_ENGINE_FACTORY is required
    SCENARA_FASHION_ENGINE_FACTORY is required

说明当前版本仍要求合格的、带模块或包路径的 factory 引用。应填写项目支持的限定引用，而不是空值或 unqualified built-in reference adapter。

正式模型验收时改为：

    SCENARA_PRODUCTION_MODELS_REQUIRED=true

### 9.2 Core 启动

    sudo docker compose \
      --env-file /home/<user>/scenara-env/scenara-core.env \
      -f deploy/compose.yml \
      up -d --no-build --wait \
      api batch-worker stream-worker scheduler

检查：

    sudo docker compose \
      --env-file /home/<user>/scenara-env/scenara-core.env \
      -f deploy/compose.yml \
      ps

期望：

- api 为 healthy
- batch-worker、stream-worker、scheduler 为 Up
- migrate 和 preflight 为一次性任务，完成后 Exited

GPU 检查：

    sudo nvidia-smi -L
    sudo docker exec scenara-batch-worker-1 nvidia-smi -L
    sudo docker exec scenara-stream-worker-1 nvidia-smi -L

两张卡分别分配给两个 Worker 时，容器内各自只能看到一张卡是正常的。应通过 GPU UUID 检查是否为不同显卡。

## 10. Data 部署

### 10.1 配置检查

    cd ~/project/scenara-data

    sudo docker compose \
      --env-file /home/<user>/scenara-env/scenara-data.env \
      -f deploy/compose.production.yml \
      config --quiet

检查必需变量：

    grep -nE '^SCENARA_DATA_(S3_REGION|S3_ENDPOINT_URL|CORE_EVENT_ENDPOINT|CORS_ALLOW_ORIGINS)=' \
      /home/<user>/scenara-env/scenara-data.env

### 10.2 Stack 转换和部署

Docker Compose 和 Docker Stack 不完全兼容，需要删除 depends_on 和顶层 name，并把 CPU 数值转换为字符串：

    sudo docker compose \
      --env-file /home/<user>/scenara-env/scenara-data.env \
      -f deploy/compose.production.yml \
      config \
    | awk '
    /^    depends_on:$/ {skip=1; next}
    skip && /^    [^ ]/ {skip=0}
    !skip {print}
    ' \
    | sed -E '/^name:/d; s/^([[:space:]]+cpus: )([0-9]+(\.[0-9]+)?)$/\1"\2"/' \
    | sudo docker stack deploy \
      --resolve-image never \
      -c - scenara-data

检查：

    sudo docker stack services scenara-data
    sudo docker stack ps scenara-data --no-trunc

期望：

- scenara-data_data-api 为 1/1
- scenara-data_data-outbox 为 1/1
- scenara-data_data-migrate 为 0/1，历史任务为 Complete

Data HTTPS 检查：

    data_container="$(sudo docker ps -q \
      --filter label=com.docker.swarm.service.name=scenara-data_data-api \
      | head -n 1)"

    sudo docker exec "$data_container" python3 -c \
    "import ssl, urllib.request; c=ssl.create_default_context(cafile='/run/tls/ca.crt'); print(urllib.request.urlopen('https://data.scenara.internal:8081/readyz', context=c, timeout=5).read().decode())"

若 readyz 返回 object_storage false，检查 MinIO 用户策略、bucket 权限和 CA 验证，然后重新执行 minio-init。

## 11. Model 部署

### 11.1 配置检查

    cd ~/project/scenara-model

    sudo docker compose \
      --env-file /home/<user>/scenara-env/scenara-model.env \
      -f deploy/compose.production.yml \
      config --quiet

生产部署使用 model_database_url secret 时，删除旧的内联配置：

    sudo sed -i '/^SCENARA_MODEL_CONTEXT_SIGNING_KEY=/d' \
      /home/<user>/scenara-env/scenara-model.env

    sudo sed -i '/^SCENARA_MODEL_METADATA_DB=/d' \
      /home/<user>/scenara-env/scenara-model.env

### 11.2 Stack 部署

    sudo docker compose \
      --env-file /home/<user>/scenara-env/scenara-model.env \
      -f deploy/compose.production.yml \
      config \
    | awk '
    /^    depends_on:$/ {skip=1; next}
    skip && /^    [^ ]/ {skip=0}
    !skip {print}
    ' \
    | sed -E '/^name:/d; s/^([[:space:]]+cpus: )([0-9]+(\.[0-9]+)?)$/\1"\2"/' \
    | sudo docker stack deploy \
      --resolve-image never \
      -c - scenara-model

检查：

    sudo docker stack services scenara-model
    sudo docker stack ps scenara-model --no-trunc

期望：

- scenara-model_model-api 为 1/1
- scenara-model_model-migrate 为 0/1
- migration 历史任务为 Complete

Model HTTPS 检查：

    model_container="$(sudo docker ps -q \
      --filter label=com.docker.swarm.service.name=scenara-model_model-api \
      | head -n 1)"

    sudo docker exec "$model_container" python3 -c \
    "import ssl, urllib.request; c=ssl.create_default_context(cafile='/run/tls/ca.crt'); print(urllib.request.urlopen('https://model.scenara.internal:8080/health', context=c, timeout=5).read().decode())"

成功应返回 status ok，并显示 metadata_persistent true、storage_backend minio、auth_required true。

## 12. 镜像构建和版本更新

在测试生产服务器上可直接构建本地镜像，用 Git commit 作为不可变标签。

### 12.1 Data

    cd ~/project/scenara-data
    git pull --ff-only origin main
    commit="$(git rev-parse HEAD)"
    sudo docker build -t "scenara-data:$commit" .

    sudo sed -i '/^SCENARA_DATA_IMAGE=/d' \
      /home/<user>/scenara-env/scenara-data.env
    echo "SCENARA_DATA_IMAGE=scenara-data:$commit" | \
      sudo tee -a /home/<user>/scenara-env/scenara-data.env >/dev/null

### 12.2 Model

    cd ~/project/scenara-model
    git pull --ff-only origin main
    commit="$(git rev-parse HEAD)"
    sudo docker build -t "scenara-model:$commit" .

    sudo sed -i '/^SCENARA_MODEL_IMAGE=/d' \
      /home/<user>/scenara-env/scenara-model.env
    echo "SCENARA_MODEL_IMAGE=scenara-model:$commit" | \
      sudo tee -a /home/<user>/scenara-env/scenara-model.env >/dev/null

### 12.3 Core

    cd ~/project/scenara
    git pull --ff-only origin main
    commit="$(git rev-parse HEAD)"
    sudo docker build -t "scenara-api:$commit" .

    sudo sed -i '/^SCENARA_IMAGE_REFERENCE=/d' \
      /home/<user>/scenara-env/scenara-core.env
    echo "SCENARA_IMAGE_REFERENCE=scenara-api:$commit" | \
      sudo tee -a /home/<user>/scenara-env/scenara-core.env >/dev/null

检查镜像引用：

    grep -nE '^SCENARA_(IMAGE_REFERENCE|DATA_IMAGE|MODEL_IMAGE)=' \
      /home/<user>/scenara-env/*.env

不要保留空行：

    SCENARA_IMAGE_REFERENCE=

更新部署前先执行对应项目的 config --quiet。不要为了更新镜像删除 PostgreSQL、Redis、MinIO volume。

如果 Model 镜像报 alembic executable file not found，说明镜像没有包含迁移依赖，需要拉取包含 migration dependencies 的提交后重新构建，不要继续使用旧镜像。

## 13. 密钥泄露和轮换

### 13.1 通用原则

如果密码、Token、数据库 URL、S3 Secret、Fernet key 或 CA 私钥出现在日志、聊天、截图或终端录屏中，应按已泄露处理。

通用顺序：

1. 停止使用旧密钥的应用服务。
2. 在后端系统中修改真实凭据。
3. 删除旧 Docker secret，用相同名称创建新 secret。
4. 更新环境文件或数据库 URL secret。
5. 重新部署。
6. 验证健康检查、业务访问和日志。
7. 确认旧密钥不再被任何服务使用。

不要删除数据库、Redis、MinIO 数据 volume 来解决密钥问题。

### 13.2 Model 上下文密钥轮换

错误：

    SCENARA_MODEL_CONTEXT_SIGNING_KEY must differ from SCENARA_MODEL_SERVICE_TOKEN

只轮换 model_context_signing_key，不要轮换 model_data_context_signing_key，因为后者必须继续和 Data 的 data_context_signing_key 相同。

    cd ~/project/scenara-model
    sudo docker stack rm scenara-model
    sleep 10

    new_model_context_key="$(openssl rand -hex 32)"
    sudo docker secret rm model_context_signing_key 2>/dev/null || true
    printf '%s' "$new_model_context_key" | \
      sudo docker secret create model_context_signing_key -
    unset new_model_context_key

    sudo sed -i '/^SCENARA_MODEL_CONTEXT_SIGNING_KEY=/d' \
      /home/<user>/scenara-env/scenara-model.env

然后按 Model 部署章节重新部署。不需要重建镜像，不会删除 Model 数据。

### 13.3 数据库 URL 或数据库密码泄露

如果 API health 返回值或错误日志包含完整 DSN，数据库密码已经泄露。只修改环境文件是不够的，数据库服务端必须同时修改角色密码。

示例：

    new_model_db_password="$(openssl rand -hex 32)"

使用仍然有效的 PostgreSQL 管理账号执行：

    sudo docker exec -it scenara-infra-postgres-1 psql \
      -U <postgres-admin-user> \
      -d postgres \
      -c "ALTER ROLE scenara_model WITH PASSWORD '$new_model_db_password';"

停止 Model stack 并替换 URL secret：

    sudo docker stack rm scenara-model
    sleep 10

    sudo docker secret rm model_database_url
    printf '%s' \
      "postgresql://scenara_model:$new_model_db_password@postgres.scenara.internal:5432/scenara_model?sslmode=verify-full&sslrootcert=/run/tls/ca.crt" \
    | sudo docker secret create model_database_url -

    unset new_model_db_password

然后重新部署 Model，并验证迁移和 HTTPS health。

Data 的 data_database_url 和 Core 的 SCENARA_POSTGRES_DSN 按同样原则处理，但要修改各自的数据库角色，不能复用密码。

如果管理员密码本身泄露，先使用仍有效的管理凭据修改管理员角色，再修改应用角色。

### 13.4 Redis 密码轮换

Redis 密码需要同时更新：

- Redis 容器启动配置
- Core 的 SCENARA_REDIS_URL
- Data 的 SCENARA_DATA_REDIS_URL
- 所有使用 Redis 的 Worker

只改应用 URL 而不改 Redis 容器会导致认证失败。

### 13.5 MinIO S3 Secret 轮换

每个项目使用自己的 MinIO 用户。轮换步骤：

1. 用 openssl rand -hex 32 生成新 Secret。
2. 在 MinIO 更新对应用户密码，或禁用旧用户后创建新用户。
3. 更新项目配置或 Docker secret。
4. 重新运行 minio-init。
5. 检查 bucket、策略和应用 readiness。
6. 重启对应应用。

### 13.6 CA 私钥泄露

如果 ca.key 或任何服务私钥泄露：

1. 重新生成整套 CA 和服务证书。
2. 更新所有服务的证书挂载。
3. 重启 PostgreSQL、Redis、MinIO、Core、Data、Model。
4. 在应用容器内验证 /run/tls/ca.crt。

重新生成 CA 会使旧证书失效，应安排维护窗口。

## 14. 常见错误速查

### required variable is missing

原因是 Compose 插值变量不存在或为空。补齐变量后重新运行 config --quiet。不要使用 KEY= 伪装成已配置。

### SCENARA_DATA_CORS_ALLOW_ORIGINS 缺失

没有公网域名时也必须填写内部来源：

    SCENARA_DATA_CORS_ALLOW_ORIGINS=https://core.scenara.internal:8000

### S3_REGION 缺失

    SCENARA_DATA_S3_REGION=us-east-1
    SCENARA_MODEL_S3_REGION=us-east-1

### Redis Permission denied 配置 TLS

检查：

- compose.tls.yml 是否加载
- CA 和私钥是否正确挂载
- 目录是否可执行、证书是否可读
- 私钥是否被不相关用户写入

### PostgreSQL 私钥权限错误

    sudo chmod 600 /secure/scenara-certs/postgres/server.key

然后重启 PostgreSQL。不要删除 PostgreSQL volume。

### unsupported external secret 或 secret not found

Data/Model 生产文件必须使用 Docker Swarm secrets。先 docker secret create，再 docker stack deploy。不要使用普通 docker compose run 替代。

### depends_on must be a list、cpus must be a string、top-level name

这是 Compose 和 Stack 规范差异。使用本文 Data/Model 部署章节的 awk 和 sed 转换管道。

### network scope local instead of swarm

外部网络必须是 attachable overlay。检查：

    sudo docker network inspect scenara-platform

### Data migration 找不到 SCENARA_DATA_DATABASE_URL

检查容器中是否提供：

    SCENARA_DATA_DATABASE_URL_FILE=/run/secrets/data_database_url

确认使用了包含最新迁移脚本的 Data 镜像，并重新构建部署。

### Data outbox 一直 0/1

Outbox 是长期运行的 worker，不应使用 API HTTP healthcheck。日志有 Outbox 工作进程已启动但服务不稳定时，拉取包含禁用 outbox healthcheck 修复的 Data 提交，重新构建并部署。最终应为 1/1。

### Model context signing key 与 service token 相同

只轮换 model_context_signing_key，不能修改 Data 共享的 model_data_context_signing_key。

### Core preflight 报密码太短、Fernet 无效、secret 被复用

- 密码和 Token 使用独立的 openssl rand -hex 32
- Fernet 使用 Fernet.generate_key()
- 不同信任边界不能复用 Token
- 正式模型完成后设置 SCENARA_PRODUCTION_MODELS_REQUIRED=true
- 测试阶段才可使用 reference 模式

### NVIDIA Driver was not detected

如果是在没有 GPU runtime 的临时 preflight 容器中出现，先看作提示。最终检查必须在真正的 worker 容器内执行：

    sudo docker exec scenara-batch-worker-1 nvidia-smi
    sudo docker exec scenara-stream-worker-1 nvidia-smi

### 健康检查返回完整数据库 URL

视为数据库密码泄露，立即执行数据库角色密码和对应 Docker secret 的轮换。

## 15. 全新部署顺序

按以下顺序执行：

1. 安装 Docker、Compose plugin、NVIDIA Container Toolkit。
2. 克隆三个仓库并确认 main 分支。
3. 生成内部 CA 和服务证书。
4. 准备四个权限为 600 的环境文件。
5. 生成密码、Token、S3 Secret 和 Fernet key。
6. 启动 shared infra。
7. 初始化 PostgreSQL。
8. 初始化 MinIO。
9. 初始化 Swarm。
10. 创建 scenara-platform overlay 网络。
11. 创建 Data 和 Model Docker secrets。
12. Core config、preflight、迁移和启动。
13. Data config、迁移和 Stack 部署。
14. Model config、迁移和 Stack 部署。
15. 执行 Core、Data、Model HTTPS 和 GPU 验证。
16. 进行 Core → Data → Model 端到端业务联调。

## 16. 更新部署顺序

单个项目更新：

1. git pull --ff-only origin main。
2. 检查仓库最新提交和 Dockerfile。
3. 使用 commit tag 构建本地镜像。
4. 只更新对应项目环境文件的镜像标签。
5. 执行 config --quiet。
6. 重新部署对应 Compose 或 Stack。
7. 检查 migration、replicas、health 和日志。
8. 确认通过后再更新下一个项目。

更新共享基础设施或 CA 时，先备份并安排维护窗口。不要在普通版本更新中执行 down --volumes。

## 17. 最终验收清单

    sudo docker compose -p scenara-infra \
      --env-file /home/<user>/scenara-env/scenara-infra.env \
      -f ~/project/scenara/deploy/shared-infra/compose.yml \
      -f ~/project/scenara/deploy/shared-infra/compose.tls.yml ps

    sudo docker compose \
      --env-file /home/<user>/scenara-env/scenara-core.env \
      -f ~/project/scenara/deploy/compose.yml ps

    sudo docker stack services scenara-data
    sudo docker stack services scenara-model
    sudo nvidia-smi -L

应满足：

- PostgreSQL、Redis、MinIO healthy
- Core API healthy
- Core 的 Scheduler、Batch Worker、Stream Worker 为 Up
- Data API 为 1/1
- Data Outbox 为 1/1
- Model API 为 1/1
- Data 和 Model migration 最近任务为 Complete
- 内部 HTTPS 健康检查返回 200
- PostgreSQL 三个数据库独立
- MinIO 用户和 bucket 使用最小权限
- 真实密钥未提交到 Git、日志、聊天或截图
- GPU UUID 分配符合预期

## 18. 真正生产模型上线前

当前仓库没有实际训练产生的生产模型文件时，仍需完成：

1. 训练并导出正式模型。
2. 上传模型资产到正确 MinIO bucket。
3. 校验模型文件哈希、版本和元数据。
4. 配置正式、限定的 engine factory 引用。
5. 设置 SCENARA_PRODUCTION_MODELS_REQUIRED=true。
6. 重新执行 Core preflight。
7. 完成 Core → Data → Model 端到端测试。
8. 完成数据库、MinIO、Docker secrets 和 CA 的备份恢复演练。

当前部署可以判定为基础设施和服务编排完成，但正式模型验收需要另行完成。

