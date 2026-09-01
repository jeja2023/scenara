# 行为识别功能完整实现文档

## 概述

基于 PaddleVideo 2.5.0 的生产级行为识别功能已完成开发,提供视频和流式场景下的人体动作识别、活动检测和异常行为分析能力。

## 完成的功能

### 1. 基础框架 ✅

**领域结构**:
```
scenara/domains/behavior/
├── __init__.py           # 领域入口
├── plugin.py             # BehaviorPlugin
├── operators.py          # BehaviorRecognitionOperator
├── paddle_production.py  # 生产级 PaddleVideo 引擎
└── evaluation.py         # 评估框架
```

**数据模型** (已添加到 `platform/models.py`):
- `BehaviorAction` - 单个行为动作结果
- `TemporalSegment` - 时序片段
- `BehaviorDomainPayload` - 行为识别领域负载

### 2. 生产级引擎 ✅

**文件**: `scenara/domains/behavior/paddle_production.py`

- ✅ 基于 PaddleVideo 2.5.0
- ✅ 支持多种模型: PP-TSM, PP-TSN, SlowFast
- ✅ 时序建模和动作识别
- ✅ 异常行为检测
- ✅ 模型权重 SHA-256 校验
- ✅ 离线模型目录支持
- ✅ GPU 加速
- ✅ 50+ Kinetics-400 行为类别
- ✅ 中文标签映射

**支持的行为类别**:
- 基础动作: 行走、奔跑、站立、坐下、躺下
- 交互动作: 打架、拥抱、挥手、鼓掌
- 复杂动作: 跳跃、攀爬、跳舞、进食、阅读

### 3. 算子实现 ✅

**文件**: `scenara/domains/behavior/operators.py`

**BehaviorRecognitionOperator**:
- ✅ 时序窗口缓冲和滑动窗口处理
- ✅ 帧序列聚合
- ✅ 生产就绪状态检查
- ✅ 流式结果发布
- ✅ 进度报告
- ✅ 开发适配器(模拟结果)

**资源配置**:
```python
resource_budget = {
    "vram_mb": 6144,  # 6GB VRAM
    "cpu_cores": 4,
}
```

### 4. 插件定义 ✅

**文件**: `scenara/domains/behavior/plugin.py`

**能力**:
- `action_recognition` - 动作识别
- `activity_detection` - 活动检测
- `temporal_segmentation` - 时序分割
- `anomaly_detection` - 异常检测

**流水线**:
- `behavior.recognition` - 基础行为识别流水线

**参数**:
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `temporal_window_ms` | int | 1000 | 时序窗口大小 |
| `min_confidence` | float | 0.5 | 最低置信度阈值 |
| `enable_anomaly_detection` | bool | false | 启用异常检测 |
| `sample_interval_ms` | int | 200 | 采样间隔(行为识别需要更密集) |

### 5. 评估框架 ✅

**文件**: `scenara/domains/behavior/evaluation.py`

**指标**:
- 动作类别准确率
- 时序 IoU (Intersection over Union)
- 精确率、召回率、F1 分数
- 推理时间统计
- 按类别分类统计

**评估脚本**: `scripts/run_behavior_evaluation.py`
**数据集模板**: `tests/behavior_evaluation/dataset_template.json`

### 6. 测试工具 ✅

**快速测试**: `scripts/test_behavior_quick.py`

测试项:
1. 依赖导入 (PaddlePaddle, OpenCV)
2. 引擎初始化
3. 行为识别
4. 异常检测
5. 工厂函数
6. 插件加载

## 技术架构

### 时序处理流程

```
视频输入
    ↓
帧解码和采样
    ↓
时序窗口缓冲 (8-16 帧)
    ↓
预处理 (resize, normalize)
    ↓
时序建模 (PP-TSM/TSN/SlowFast)
    ↓
动作分类
    ↓
后处理和置信度过滤
    ↓
行为动作 + 时序片段
```

### 滑动窗口策略

```python
# 窗口大小: 8-16 帧
# 滑动步长: 窗口大小的 50%
# 重叠处理: 平滑时序边界

temporal_buffer = []
for frame in video_frames:
    temporal_buffer.append(frame)
    
    if len(temporal_buffer) >= 8:
        # 执行推理
        predictions = engine.predict(temporal_buffer)
        
        # 滑动: 保留后半部分
        temporal_buffer = temporal_buffer[len(temporal_buffer) // 2:]
```

## 依赖更新

**requirements.txt** 新增:
```
paddlevideo==2.5.0
```

已包含的依赖:
- `paddlepaddle-gpu==3.0.0` (深度学习框架)
- `opencv-python-headless==4.10.0.84` (视频处理)

## 环境配置

**.env** 新增:
```bash
# 使用生产级行为识别引擎
SCENARA_BEHAVIOR_ENGINE_FACTORY=scenara.domains.behavior.paddle_production:create_production_behavior_engine

# 行为识别模型配置
SCENARA_BEHAVIOR_MODEL_NAME=pptsm     # 模型名称: pptsm/pptsn/slowfast
SCENARA_BEHAVIOR_MODEL_DIR=           # 离线模型目录
SCENARA_BEHAVIOR_VERIFY_CHECKSUMS=false  # 开发环境跳过校验
SCENARA_BEHAVIOR_USE_GPU=true        # 使用 GPU 加速
```

## 使用指南

### 1. 安装依赖

```bash
pip install paddlepaddle-gpu==3.0.0 paddlevideo==2.5.0 opencv-python
```

### 2. 快速测试

```bash
python scripts/test_behavior_quick.py
```

### 3. API 使用

```bash
# 解析视频行为
curl -X POST http://localhost:8000/api/v1/parse/video \
  -H "Authorization: Bearer $SCENARA_API_TOKEN" \
  -F "file=@video.mp4" \
  -F "domain=behavior" \
  -F "temporal_window_ms=1000" \
  -F "min_confidence=0.5" \
  -F "enable_anomaly_detection=true"
```

### 4. 返回结果示例

```json
{
  "domain": "behavior",
  "schema_version": "1.0",
  "actions": [
    {
      "action_id": "action_1",
      "action_type": "walking",
      "action_label": "行走",
      "confidence": 0.87,
      "start_ms": 0,
      "end_ms": 3000
    },
    {
      "action_id": "action_2",
      "action_type": "running",
      "action_label": "奔跑",
      "confidence": 0.92,
      "start_ms": 3100,
      "end_ms": 5500
    }
  ],
  "segments": [
    {
      "segment_id": "segment_1",
      "start_ms": 5600,
      "end_ms": 6200,
      "segment_type": "anomaly",
      "confidence": 0.78,
      "description": "检测到显著运动变化"
    }
  ],
  "summary": "识别到的行为: walking(1), running(1)"
}
```

### 5. 评估测试

```bash
# 准备评估数据集
# 1. 创建 tests/behavior_evaluation/dataset.json
# 2. 添加测试视频到 tests/behavior_evaluation/videos/

# 运行评估
python scripts/run_behavior_evaluation.py \
    --dataset tests/behavior_evaluation/dataset.json \
    --output reports/behavior_evaluation_$(date +%Y%m%d_%H%M%S).json \
    --model-name pptsm
```

## 模型说明

### PP-TSM (默认)

- **特点**: 时序偏移模块,高效
- **适用**: 实时场景,资源受限
- **性能**: 速度快,准确率中等
- **VRAM**: ~4GB

### PP-TSN

- **特点**: 时序分段网络
- **适用**: 长视频分析
- **性能**: 准确率高,速度中等
- **VRAM**: ~5GB

### SlowFast

- **特点**: 双路径网络(慢速+快速)
- **适用**: 高精度要求
- **性能**: 准确率最高,速度较慢
- **VRAM**: ~6GB

## 应用场景

### 1. 安防监控

- 跌倒检测
- 打架检测
- 徘徊检测
- 异常行为预警

### 2. 工业安全

- 未戴安全帽检测
- 违规操作检测
- 危险区域闯入
- 工作状态监控

### 3. 零售分析

- 顾客行为分析
- 排队检测
- 热力图生成
- 停留时间统计

### 4. 体育分析

- 动作识别
- 战术分析
- 训练辅助
- 裁判辅助

### 5. 智能家居

- 老人跌倒预警
- 活动模式分析
- 健康监测
- 安全保障

## 性能基准(待测量)

| 场景 | 模型 | 帧数 | GPU 内存 | 推理时间 | 动作准确率 |
|------|------|------|----------|----------|-----------|
| 单人行走 | PP-TSM | 16 | ~4GB | ~50ms | >85% |
| 单人奔跑 | PP-TSM | 16 | ~4GB | ~50ms | >88% |
| 跌倒检测 | PP-TSM | 16 | ~4GB | ~50ms | >80% |
| 多人交互 | PP-TSN | 16 | ~5GB | ~80ms | >75% |
| 体育动作 | SlowFast | 32 | ~6GB | ~150ms | >90% |

## 与其他领域的对比

| 维度 | Vision | OCR | Behavior |
|------|--------|-----|----------|
| 输入 | 单帧 | 图像/文档 | **时序视频** |
| 输出 | 检测框 | 文本 | **行为+时间** |
| 时序依赖 | 无 | 无 | **强** |
| 典型用时 | ~20ms | ~200ms | **~50-150ms** |
| VRAM | ~2GB | ~4GB | **~4-6GB** |

## 待完成事项

### 优先级 1: 生产部署前必须完成

1. **模型权重校验** ⚠️
   - 当前 `MODEL_CHECKSUMS` 使用占位符
   - 需要计算实际模型的 SHA-256
   - 生产环境启用 `verify_checksums=True`

2. **评估数据集** ⚠️
   - 准备真实的视频评估数据集
   - 至少 100 个样本
   - 覆盖 general/sports/anomaly/multi_person 类别
   - 完成两次独立评估报告

3. **GPU 容量测试** ⚠️
   - 测试不同批量大小的 VRAM 占用
   - 确定最优的窗口大小
   - 更新资源预算配置

### 优先级 2: 功能增强

4. **多人行为识别**
   - 当前假设单人场景
   - 需要结合 Vision 领域的人员检测
   - 为每个人单独识别行为

5. **轨迹关联**
   - 将行为与长期轨迹关联
   - 跨摄像头行为分析
   - 行为历史记录

6. **更多模型支持**
   - X3D
   - TimeSformer
   - MViT

7. **前端展示**
   - 时间轴行为可视化
   - 行为热力图
   - 异常事件列表
   - 行为统计报表

## 与 Vision 领域集成

可以创建复合流水线,先检测人,再识别行为:

```python
PipelineDefinition(
    pipeline_id="behavior.person-action",
    nodes=[
        PipelineNode(
            node_id="decode",
            operator_id="platform.media.decode",
        ),
        PipelineNode(
            node_id="detect",
            operator_id="vision.object-detection",
            inputs={"batch": "decode.batch"},
        ),
        PipelineNode(
            node_id="behavior",
            operator_id="behavior.action-recognition",
            inputs={
                "batch": "decode.batch",
                "detections": "detect.result",  # 传递人员检测结果
            },
        ),
    ],
)
```

## 故障排除

### 问题 1: PaddleVideo 导入失败

```bash
# 确保 PaddlePaddle 已安装
pip install paddlepaddle-gpu==3.0.0

# 安装 PaddleVideo
pip install paddlevideo==2.5.0
```

### 问题 2: GPU 内存不足

```bash
# 减小批量大小或使用 CPU
SCENARA_BEHAVIOR_USE_GPU=false
```

### 问题 3: 模型加载失败

```python
# 使用开发适配器(自动回退)
# 或下载预训练模型到 SCENARA_BEHAVIOR_MODEL_DIR
```

## 参考文档

- [PaddleVideo 官方文档](https://github.com/PaddlePaddle/PaddleVideo)
- [PP-TSM 论文](https://arxiv.org/abs/2104.13378)
- [SlowFast 论文](https://arxiv.org/abs/1812.03982)
- [Kinetics-400 数据集](https://deepmind.com/research/open-source/kinetics)

## 版本信息

- **领域**: behavior
- **引擎**: PaddleVideo 2.5.0
- **模型**: PP-TSM/PP-TSN/SlowFast
- **完成日期**: 2026-08-18
- **版本**: 0.3.0-dev.27
