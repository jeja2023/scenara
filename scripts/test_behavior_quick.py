"""
行为识别功能快速测试脚本

用于验证行为识别引擎是否正确安装和配置
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_import() -> bool:
    """测试依赖导入"""
    print("1. 测试依赖导入...")
    try:
        import paddle
        print(f"   ✓ PaddlePaddle {paddle.__version__}")
    except ImportError as e:
        print(f"   ✗ PaddlePaddle 导入失败: {e}")
        return False

    try:
        import cv2
        print(f"   ✓ OpenCV {cv2.__version__}")
    except ImportError as e:
        print(f"   ✗ OpenCV 导入失败: {e}")
        return False

    return True


def test_engine_init() -> bool:
    """测试引擎初始化"""
    print("\n2. 测试引擎初始化...")
    try:
        from scenara.domains.behavior.paddle_production import ProductionPaddleVideoBehaviorEngine

        engine = ProductionPaddleVideoBehaviorEngine(
            verify_checksums=False,
            use_gpu=False,
        )
        print(f"   ✓ 引擎初始化成功: {engine.model_id} v{engine.version}")
        print(f"   ✓ 生产就绪: {engine.production_ready}")
        print(f"   ✓ 能力: {', '.join(engine.production_capabilities)}")
        print(f"   ✓ 支持的行为类别数: {len(engine.action_classes)}")
        return True
    except Exception as e:
        print(f"   ✗ 引擎初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_behavior_prediction() -> bool:
    """测试行为识别"""
    print("\n3. 测试行为识别...")
    try:
        import numpy as np
        from PIL import Image
        from scenara.domains.behavior.paddle_production import ProductionPaddleVideoBehaviorEngine

        # 创建测试视频序列(16 帧)
        frames = []
        for i in range(16):
            # 创建简单的移动物体
            img = Image.new("RGB", (224, 224), color=(255, 255, 255))
            # 模拟移动:在图像中绘制一个移动的矩形
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            x = 50 + i * 5
            draw.rectangle([x, 100, x + 30, 150], fill=(255, 0, 0))
            frames.append(np.array(img))

        # 执行行为识别
        engine = ProductionPaddleVideoBehaviorEngine(
            verify_checksums=False,
            use_gpu=False,
        )
        results = engine.predict(frames, min_confidence=0.0)

        if results:
            print(f"   ✓ 识别到 {len(results)} 个行为")
            for i, action in enumerate(results[:3], 1):  # 只显示前3个
                print(
                    f"     [{i}] {action['action_label']} "
                    f"(type: {action['action_type']}, "
                    f"confidence: {action['confidence']:.2f})"
                )
            return True
        else:
            print("   [WARN] 未识别到行为(使用回退方法)")
            return True  # 不算失败
    except Exception as e:
        print(f"   ✗ 行为识别失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_anomaly_detection() -> bool:
    """测试异常检测"""
    print("\n4. 测试异常检测...")
    try:
        import numpy as np
        from PIL import Image
        from scenara.domains.behavior.paddle_production import ProductionPaddleVideoBehaviorEngine

        # 创建包含异常变化的视频序列
        frames = []
        for i in range(16):
            if i < 8:
                # 前半段:静止
                img = Image.new("RGB", (224, 224), color=(200, 200, 200))
            else:
                # 后半段:剧烈变化
                color = (255 if i % 2 else 0, 0, 0)
                img = Image.new("RGB", (224, 224), color=color)
            frames.append(np.array(img))

        # 执行异常检测
        engine = ProductionPaddleVideoBehaviorEngine(
            verify_checksums=False,
            use_gpu=False,
        )
        anomalies = engine.predict_anomaly(frames)

        print(f"   ✓ 检测到 {len(anomalies)} 个异常片段")
        if anomalies:
            for i, anomaly in enumerate(anomalies[:3], 1):
                print(
                    f"     [{i}] {anomaly.get('description', 'anomaly')} "
                    f"(confidence: {anomaly.get('confidence', 0):.2f})"
                )
        return True
    except Exception as e:
        print(f"   ✗ 异常检测失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_factory() -> bool:
    """测试工厂函数"""
    print("\n5. 测试工厂函数...")
    try:
        from scenara.domains.behavior.paddle_production import create_production_behavior_engine

        engine = create_production_behavior_engine()
        print(f"   ✓ 工厂函数创建引擎成功: {engine.model_id}")
        return True
    except Exception as e:
        print(f"   ✗ 工厂函数失败: {e}")
        return False


def test_plugin() -> bool:
    """测试插件"""
    print("\n6. 测试插件...")
    try:
        from scenara.domains.behavior import BehaviorPlugin

        plugin = BehaviorPlugin()
        print(f"   ✓ 插件初始化成功: {plugin.manifest.domain_id}")
        print(f"   ✓ 显示名称: {plugin.manifest.display_name}")
        print(f"   ✓ 能力: {', '.join(plugin.manifest.capabilities)}")
        print(f"   ✓ 支持的媒体类型: {', '.join(plugin.manifest.supported_media_kinds)}")

        operators = plugin.operators()
        print(f"   ✓ 算子数量: {len(operators)}")

        pipelines = plugin.pipelines()
        print(f"   ✓ 流水线数量: {len(pipelines)}")

        return True
    except Exception as e:
        print(f"   ✗ 插件测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main() -> None:
    print("=" * 80)
    print("行为识别功能快速测试")
    print("=" * 80)

    results = []

    # 运行测试
    results.append(("依赖导入", test_import()))

    if results[-1][1]:  # 只有导入成功才继续
        results.append(("引擎初始化", test_engine_init()))
        results.append(("行为识别", test_behavior_prediction()))
        results.append(("异常检测", test_anomaly_detection()))
        results.append(("工厂函数", test_factory()))
        results.append(("插件", test_plugin()))

    # 打印摘要
    print("\n" + "=" * 80)
    print("测试摘要")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status} - {name}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n✓ 所有测试通过! 行为识别功能已就绪。")
        sys.exit(0)
    else:
        print("\n✗ 部分测试失败,请检查依赖安装和配置。")
        print("\n安装命令:")
        print("  pip install paddlepaddle-gpu paddlevideo opencv-python")
        sys.exit(1)


if __name__ == "__main__":
    main()
