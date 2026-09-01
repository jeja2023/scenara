# Portrait Hub 能力处置与迁移矩阵

源码锚点记录于 `source-manifest.json`。旧版 API 路径兼容性不作为验收标准。每个已迁移的能力必须能够通过 Scenara 领域插件及公共 Media/Run/Result 契约访问。

| 算法能力 | 处置方式 | Scenara 证据与实现 |
|---|---|---|
| 图片校验与解码 | 重新实现 (reimplemented) | `scenara.platform.media` |
| 人体检测 | 迁移导入 (migrated) | Portrait 插件算子与契约测试 |
| 人体 ReID | 重新实现 (reimplemented) | portrait.analysis 后端契约；生产环境拒绝缺失授权的 OSNet 模型包 |
| 人脸检测/对齐/特征向量提取 | 重新实现 (reimplemented) | 类型化人脸对象、关联关系、递归特征脱敏与生产模型门禁 |
| 人体姿态估计 | 重新实现 (reimplemented) | portrait.analysis 姿态属性；经批准的 RTMPose 模型包与固定评估仍作为发布门禁 |
| 人体解析与服饰属性 | 重新实现 (reimplemented) | 类型化能力与显式开发替代品出处溯源 |
| 剪影分割 (Silhouette) | 重新实现 (reimplemented) | 类型化剪影对象与关联关系；生产环境拒绝边界框替代实现 |
| 步态识别 | 重新实现 (reimplemented) | 纯序列契约，强制要求至少 8 帧并记录模型溯源 |
| 底库身份注册与人像检索 | 重新实现 (reimplemented) | 租户身份/注册/检索 API、特征空间隔离与生物特征删除测试 |
| 长视频目标跟踪 | 重新实现 (reimplemented) | 批处理媒体单元、Track 轨迹契约、结果分片与专用 worker 队列通道 |
| 视频内行人轨迹片段 (Tracklets) | 重新实现 (reimplemented) | 两阶段关联、全局指派、带时间兼容性的碎片重连、轨迹质量评分以及交接至长期身份注册 |
| 跨摄像头长期轨迹分析 | 重新实现 (reimplemented) | 人脸 + 人体多模态融合、摄像头拓扑与时空互斥约束、真实媒体时间轴、受限模板库、人工研判（确认/拒绝/重命名/合并/拆分/删除）以及跨视频身份持久化/查询闭环 |
| 摄像头登记与拓扑约束 | 重新实现 (reimplemented) | 租户作用域摄像头记录、自动源摄像头登记，以及 Re-ID 期间强制执行的最小/最大转移时间约束 |
| 实时流式视频处理 | 重新实现 (reimplemented) | 加密凭据存储、有界解码、流式队列通道与终止原因契约 |
| 旧版 `/v1` API 兼容性 | 明确停用 (explicitly retired) | 新版公共 API 统一为 `/api/v1` |
| 旧版数据库与开发数据 | 明确停用 (explicitly retired) | 干净的全新数据库迁移版本 |
| 旧版发布与生成的 SDK 产物 | 明确停用 (explicitly retired) | 源码清单排除项 |
