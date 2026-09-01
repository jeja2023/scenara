# 源码出处与溯源说明

Scenara 基于 `https://github.com/jeja2023/portrait-hub` 的精选快照构建，未复制其既有 Git 历史。

初始 Scenara 根提交创建时，确切的源码锚点已记录在 `source-manifest.json` 中。启动期间观察到的候选提交为 `ae9798f3119099a5b3aec554a830e25d97293e66`；一切以清单为准。

导入的模块类别：

- 媒体解码与输入校验；
- 推理运行时与任务调度；
- 迁移 Domain 所需的人像算法与存储适配器；
- 作为 UI 迁移基础的 Console 前端源码；
- 模型卡、标签文件及依赖锁（不包含模型权重文件）。

排除的模块类别：

- Portrait Hub 历史 Git 提交记录与历史发布说明；
- 旧版 OpenAPI 基线与生成的旧版客户端；
- 运行时状态、`.env`、凭证密钥、客户数据与模型权重；
- 实验性 Go、Java 和 Node SDK；
- 已废弃的早期规划与兼容性承诺。

在 Portrait Hub 归档前，任何向 Scenara 移植的阻断性修复必须在 Scenara 提交说明或变更记录中明确引用源提交哈希。
