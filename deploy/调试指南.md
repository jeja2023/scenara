# Scenara 本地 Docker 调试

本配置用于本机功能调试，不代表 Scenara 1.0 生产验收环境。它使用 PostgreSQL 状态、内联队列和本地对象存储，并通过 Docker GPU 容器加载仓库中的模型制品。PostgreSQL 由调试 Compose 管理并自动执行仓库迁移，数据保存在 `debug-postgres` 卷中。

调试拓扑使用仅限本机的默认 Fernet 密钥，把视频流地址和 Webhook 密钥加密写入 `debug-state` 对象卷，因此重建 API 容器后已登记视频流仍可使用。需要与其他本地环境共享调试数据时，在首次启动前设置稳定的 `SCENARA_DEBUG_SECRET_ENCRYPTION_KEY`；修改已有环境的密钥会让此前密文按失败关闭规则不可解密。生产环境不得使用该调试默认值，生产 Compose 继续强制显式提供 `SCENARA_SECRET_ENCRYPTION_KEY`。

## 启动

在仓库根目录执行：

```powershell
docker compose -f deploy/compose.debug.yml up -d --build
docker compose -f deploy/compose.debug.yml ps
```

控制台地址：`http://127.0.0.1:8011/console/`

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8011/healthz
Invoke-RestMethod http://127.0.0.1:8011/readyz
```

## 停止

```powershell
docker compose -f deploy/compose.debug.yml down
```

默认 `debug-postgres` volume 会保留 Run、事件和元数据，`debug-state` volume 会保留本地对象文件。API 容器重启时，浏览器中正在进行的 SSE 连接会短暂断开；前端轮询会从 PostgreSQL 恢复状态，内联队列会重新提交非终态 Run，并沿用原 `run_id` 继续执行。只有明确需要清理调试数据时才执行：

```powershell
docker compose -f deploy/compose.debug.yml down -v
```

视频解析会根据预计采样数量自动压缩有效帧边长，使解码后 RGB 帧保持在 512 MiB 总预算上限内；人体检测按最多 16 帧执行一个推理批次。文件视频通过有界队列每 8 个单元发布一次部分结果，实时流逐单元发布；控制台在 Run 完成前即可看到实时百分比、已处理/预计单元数、时间轴和特征图片。结果中的 `media_metadata.frame_max_edge` 是实际采用的边长，可用于容量记录。调试时可使用以下命令同时观察容器内存和异常退出：

```powershell
docker stats scenara-debug-api-1 --no-stream
docker events --since 10m --filter container=scenara-debug-api-1 --filter event=oom
```

本机需要 Docker Desktop GPU 支持；没有可用 GPU 时，Compose 会在容器创建阶段失败。生产部署仍必须使用 [compose.yml](compose.yml) 和经过批准的模型、密钥、PostgreSQL、Redis、MinIO 及发布证据。
