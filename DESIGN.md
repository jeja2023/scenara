# Design

## Source of truth

- Status: Active
- Last refreshed: 2026-07-30
- Primary product surfaces: Scenara Console 的 12 个工作区、图片/视频/实时流解析工作台、全局导航、连接设置和管理对话框。
- Evidence reviewed: `README.md`、`docs/brand/BRAND.md`、`docs/strategy/MEDIA_PARSE_PRODUCT_STANDARD.md`、`frontend/console/src/App.vue`、`frontend/console/src/router.ts`、`frontend/console/src/styles.css`、`frontend/console/src/labels.ts`、全部 `frontend/console/src/views/*.vue`、Vitest 与 Playwright 验收用例。

## Brand

- Personality: 专业、克制、可靠，面向需要高频操作与审计追踪的企业用户。
- Trust signals: 明确的状态、版本、租户和项目上下文；不可逆操作有清楚命名；成熟度和门禁不夸大。
- Brand mark: 使用蓝紫青双曲面带与中心四向星组成的 Scenara 景枢标准标志；完整品牌口号为“连接视觉 · 理解世界”。
- Avoid: 营销化大标题、装饰性卡片堆叠、含糊状态、未经说明的中英文混排，以及把规划能力展示成已发布能力。

## Product goals

- Goals: 让中文企业用户不依赖英文知识即可完成日常操作；统一展示产品矩阵、视觉解析、模型治理、IAM、运维与企业治理能力；让图片、视频文件和实时流从输入、参数配置、任务观察到结果复核形成同一套完整工作流。
- Non-goals: 不翻译品牌名、协议名、算法名、标准单位和必须原样输入的技术标识；不把浏览器无法原生播放的 RTSP 流伪装为可预览内容；不把有限采样任务表述为永久在线的流处理器。
- Success signals: 12 个工作区的通用界面文案全部为中文；三类媒体均可在解析工作台完成任务；枚举和后端英文说明不直接暴露；桌面与移动端无溢出或交互回归；任务状态、采样时间点、媒体元数据和失败原因可追溯。

## Personas and jobs

- Primary personas: 平台管理员、算法与集成工程师、运维人员、审核与合规人员。
- User jobs: 上传和探测媒体、登记流源、选择解析领域与采样策略、启动/取消运行、按时间点检查结果、管理媒体和运行、配置流水线与模型、管理访问凭据和产品授权、审核反馈、检查运行状态与合规证据。
- Key contexts of use: 企业内网、私有化部署、桌面高频操作和移动端临时查看。

## Information architecture

- Primary navigation: 工作台、领域、配置、治理四组导航。
- Core routes/screens: 总览、媒体、运行、结果、人像解析、OCR 文档、流水线、模型、反馈与发布、接入、运维、企业。人像解析与 OCR 文档共享图片/视频/实时流输入模式和运行观察模式。
- Content hierarchy: 页面标题和操作优先，其次是状态与汇总，再展示原始技术标识和诊断信息。

## Design principles

- 中文优先: 所有操作、字段、状态、空状态、错误、帮助文本和后端描述使用自然中文。
- 技术标识克制保留: Scenara、AI、API、OCR、HTTP(S)、JSON、SHA-256、PostgreSQL、Redis、S3、MiB、KB 等专有名称可保留；`Scope` 显示为“权限范围”，`Key` 显示为“密钥”，`ID` 显示为“标识”。
- 展示值与契约值分离: API 枚举和资源标识保持原值，必须经 `labels.ts` 转换为中文后展示；确需排障时才把原值作为次要等宽文本呈现。
- Tradeoffs: 完整中文可读性优先于逐字对应；技术准确性优先于强行翻译公认专名。

## Visual language

- Color: 界面延用石墨、青绿、珊瑚、绿色和琥珀色语义色；蓝紫青渐变仅用于标准品牌标志，不扩散为单色界面主题。
- Typography: 延用系统中文字体栈；正文紧凑，面板标题不使用大号展示字体，字距为 0。
- Spacing/layout rhythm: 延用 8-16px 紧凑操作节奏和现有网格。
- Shape/radius/elevation: 延用 3-6px 圆角；阴影仅用于模态框和必要浮层。
- Motion: 仅保留导航与状态反馈所需的短过渡。
- Imagery/iconography: 导航、移动品牌区和浏览器图标统一使用新版几何标志；按钮优先使用现有 Lucide 图标并提供中文提示。

## Components

- Existing components to reuse: 页面标题、统计块、面板、数据表、标签、分段控制、表单、模态框、空状态和提示条。
- New/changed components: 扩充 `labels.ts` 为统一界面翻译层；解析工作台增加媒体模式分段控件、视频播放器、流源摘要、采样参数、运行进度和按媒体单元浏览的结果区；媒体页增加技术元数据、预览和删除操作；不新增独立设计系统。
- Variants and states: 所有状态标签必须覆盖正常、警告、失败、停用、规划和未知兜底。
- Token/component ownership: 全局视觉 token 归 `styles.css`；跨页面术语和枚举归 `labels.ts`；业务专属文案留在对应视图。

## Accessibility

- Target standard: WCAG 2.1 AA 的键盘、焦点、对比度和语义基线。
- Keyboard/focus behavior: 模态框打开后聚焦首个输入；图标按钮保留中文 `title` 或 `aria-label`；标签页保留正确角色和选中状态。
- Contrast/readability: 状态不能只依赖颜色；中文状态文字始终可见。
- Screen-reader semantics: 导航、标签页、按钮、对话框和表单标签使用原生语义或对应 ARIA。
- Reduced motion and sensory considerations: 不以动画传达唯一信息，保持过渡短暂。

## Responsive behavior

- Supported breakpoints/devices: 桌面 Chromium 与 Pixel 7 尺寸移动视口；最低宽度 320px。
- Layout adaptations: 900px 以下使用抽屉导航，统计与双栏逐级收为单栏；宽表格在自身容器滚动。
- Touch/hover differences: 移动端不依赖悬停；图标按钮保持稳定触控尺寸和中文可访问名称。

## Interaction states

- Loading: 使用“加载中”或禁用当前操作，不显示英文状态码。
- Empty: 明确说明当前没有哪类数据，并给出下一步操作时机。
- Error: API 错误统一由 `api.ts` 输出中文；未知错误不得直接展示后端英文消息。
- Success: 一次性密钥、复制、保存和任务创建结果使用明确中文确认；长任务显示运行状态和进度，完成后自动加载结果。
- Disabled: 按钮禁用时保留可理解的中文上下文或提示。
- Offline/slow network: 全局连接状态使用“检查中 / 已连接 / 未连接”；视频与流任务不依赖单次长 HTTP 请求，页面恢复后可从运行记录继续查看。

## Content voice

- Tone: 简洁、直接、客观，不使用营销口号和无意义解释。
- Terminology: “接口”“标识”“权限范围”“API 密钥”“事件回调”“服务等级协议”“流水线”“运行”“产品授权”为统一用语。
- Microcopy rules: 句子使用中文标点；按钮使用动词；表头使用名词；未知值使用“未知状态 / 未命名能力”等中文兜底；不直接显示英文枚举、英文后端说明或英文异常消息。

## Implementation constraints

- Framework/styling system: Vue 3、TypeScript、现有 CSS 和 Lucide 图标。
- Design-token constraints: 复用 `styles.css` 现有变量和组件类，不引入新的 UI 框架。
- Performance constraints: 标签映射为本地常量与纯函数；媒体对象 URL 必须释放；运行轮询仅在非终态时进行并在组件卸载后停止；大文件不在控制台生成 Base64 副本。
- Compatibility constraints: 已有 API 请求与响应字段、资源标识、协议值保持兼容；新增字段必须有默认值；视频和流运行继续复用 Media/Run/Pipeline/Result 契约。
- Test/screenshot expectations: Vitest 静态扫描阻止通用英文回归；Playwright 覆盖 12 个路由、桌面和移动视口、三类媒体模式、运行状态、结果浏览、标签页及一次性凭据流程。

## Open questions

- [ ] 后续若增加英文服务端动态内容，接口所有者需决定由服务端提供中文字段，或在 Console 的标签层登记稳定映射。
- [ ] 浏览器端实时流预览需在 HLS/WebRTC 网关成为正式平台组件后启用；当前 RTSP/RTMP 只在服务端解析。
