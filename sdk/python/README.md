# Scenara 景枢 Python SDK

Scenara 景枢 v1 API 的官方同步 Python 客户端，提供图片、PDF、视频文件、实时视频流解析，媒体源注册与探测，运行生命周期、结果读取，数据集版本治理、审计查询导出和保存检索，以及产品目录、仓库拓扑、跨仓库契约与统一访问底座查询能力。仓库拓扑使用 `ScenaraClient.get_repository_topology()` 读取，正式契约目录使用 `get_repository_contracts()` 读取，模型包通过 `admit_model_package()` 准入。

```python
with ScenaraClient("https://scenara.example", token="...") as client:
    image = client.parse_image(
        "frame.jpg",
        pipeline_id="portrait.person-detection",
        idempotency_key="camera-42-frame-1001",
    )
    video = client.parse_video(
        "clip.mp4",
        sample_strategy="scene_change",
        sample_start_ms=5_000,
        sample_end_ms=30_000,
        scene_change_threshold=0.25,
        frame_max_edge=1_280,
    )
    document = client.parse_document("report.pdf", page_scale=2.0)
    stream = client.parse_stream(
        "source-id",
        stream_segment_duration_ms=300_000,
        max_reconnect_attempts=5,
        connect_timeout_ms=3_000,
        read_timeout_ms=2_000,
    )
```

视频处理到 EOF 或显式 `sample_end_ms`，实时流按 `stream_segment_duration_ms` 时间窗口持续分段；这两类快捷接口不提供 `max_units`，旧版通用 Run 请求中的同名字段会被服务端忽略。PDF 文档仍可通过 `max_units` 设置页数上限。省略 `pipeline_version` 时由服务端选择唯一的 active 版本；需要固定复现某次运行时应显式传入版本。
