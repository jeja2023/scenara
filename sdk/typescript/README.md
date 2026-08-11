# Scenara 景枢 TypeScript SDK

Scenara 景枢 v1 API 的官方 TypeScript 客户端，支持图片、PDF、视频文件、实时视频流解析，媒体源注册与探测，运行生命周期、结果读取，数据集版本治理、审计查询导出和保存检索，以及产品目录、仓库拓扑、跨仓库契约与统一访问底座查询能力。仓库拓扑使用 `ScenaraClient.getRepositoryTopology()` 读取，正式契约目录使用 `getRepositoryContracts()` 读取，模型包通过 `admitModelPackage()` 准入。

```typescript
await client.parseImage({
  file: image,
  filename: "frame.jpg",
  pipelineId: "portrait.person-detection",
  idempotencyKey: "camera-42-frame-1001",
});
await client.parseVideo({
  file,
  filename: "clip.mp4",
  sampleStrategy: "scene_change",
  sampleStartMs: 5_000,
  sampleEndMs: 30_000,
  sceneChangeThreshold: 0.25,
  frameMaxEdge: 1_280,
});
await client.parseDocument({ file: pdf, filename: "report.pdf", pageScale: 2 });
await client.parseStream({
  sourceId: "source-id",
  streamSegmentDurationMs: 300_000,
  maxReconnectAttempts: 5,
  connectTimeoutMs: 3_000,
  readTimeoutMs: 2_000,
});
```

视频和文档省略 `maxUnits` 时处理至 EOF；实时流省略该参数时按时间窗口持续分段。`maxUnits` 仅用于兼容旧集成或调用方显式设置保护上限。省略 `pipelineVersion` 时由服务端选择唯一的 active 版本；需要固定复现某次运行时应显式传入版本。
