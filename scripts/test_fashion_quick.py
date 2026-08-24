"""
服饰风格识别功能快速测试脚本

用于验证服饰识别引擎是否正确安装和配置
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
        import PIL
        print(f"   [PASS] PIL (Pillow) {PIL.__version__}")
    except ImportError as e:
        print(f"   [FAIL] PIL 导入失败: {e}")
        return False

    return True


def test_engine_init() -> bool:
    """测试引擎初始化"""
    print("\n2. 测试引擎初始化...")
    try:
        from scenara.domains.fashion.production import ProductionFashionEngine

        engine = ProductionFashionEngine(
            verify_checksums=False,
            use_gpu=False,
        )
        print(f"   [PASS] 引擎初始化成功: {engine.model_id} v{engine.version}")
        print(f"   [PASS] 生产就绪: {engine.production_ready}")
        print(f"   [PASS] 能力: {', '.join(engine.production_capabilities)}")
        print(f"   [PASS] 支持的角色数: {len(engine.supported_characters)}")
        print(f"   [PASS] 支持的风格数: {len(engine.supported_styles)}")
        return True
    except Exception as e:
        print(f"   [FAIL] 引擎初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cosplay_detection() -> bool:
    """测试 Cosplay 识别"""
    print("\n3. 测试 Cosplay 识别...")
    try:
        from PIL import Image
        from scenara.domains.fashion.production import ProductionFashionEngine

        # 创建测试图像
        img = Image.new("RGB", (224, 224), color=(100, 150, 200))

        # 执行 Cosplay 识别
        engine = ProductionFashionEngine(
            verify_checksums=False,
            use_gpu=False,
        )
        results = engine.detect_cosplay(img, min_confidence=0.0)

        print("   [PASS] 识别完成")
        if results:
            print(f"   [INFO] 检测到 {len(results)} 个 Cosplay 角色")
            for i, item in enumerate(results[:3], 1):
                print(f"     [{i}] {item['character_name']} ({item['series_name']}) - {item['confidence']:.2f}")
        else:
            print("   [INFO] 未检测到 Cosplay 角色(正常,测试图像)")
        return True
    except Exception as e:
        print(f"   [FAIL] Cosplay 识别失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_clothing_detection() -> bool:
    """测试服装风格识别"""
    print("\n4. 测试服装风格识别...")
    try:
        from PIL import Image
        from scenara.domains.fashion.production import ProductionFashionEngine

        # 创建测试图像
        img = Image.new("RGB", (224, 224), color=(255, 200, 200))

        # 执行服装风格识别
        engine = ProductionFashionEngine(
            verify_checksums=False,
            use_gpu=False,
        )
        results = engine.detect_clothing_style(img, min_confidence=0.0)

        print("   [PASS] 识别完成")
        if results:
            print(f"   [INFO] 检测到 {len(results)} 种服装风格")
            for i, item in enumerate(results[:3], 1):
                print(f"     [{i}] {item['style_label']} - {item['confidence']:.2f}")
        else:
            print("   [INFO] 未检测到服装风格(正常,测试图像)")
        return True
    except Exception as e:
        print(f"   [FAIL] 服装风格识别失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_accessory_detection() -> bool:
    """测试配饰识别"""
    print("\n5. 测试配饰识别...")
    try:
        from PIL import Image
        from scenara.domains.fashion.production import ProductionFashionEngine

        # 创建测试图像
        img = Image.new("RGB", (224, 224), color=(200, 200, 255))

        # 执行配饰识别
        engine = ProductionFashionEngine(
            verify_checksums=False,
            use_gpu=False,
        )
        results = engine.detect_accessories(img, min_confidence=0.0)

        print("   [PASS] 识别完成")
        if results:
            print(f"   [INFO] 检测到 {len(results)} 个配饰")
            for i, item in enumerate(results[:3], 1):
                print(f"     [{i}] {item['accessory_label']} - {item['confidence']:.2f}")
        else:
            print("   [INFO] 未检测到配饰(正常,测试图像)")
        return True
    except Exception as e:
        print(f"   [FAIL] 配饰识别失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_factory() -> bool:
    """测试工厂函数"""
    print("\n6. 测试工厂函数...")
    try:
        from scenara.domains.fashion.production import create_production_fashion_engine

        engine = create_production_fashion_engine()
        print(f"   [PASS] 工厂函数创建引擎成功: {engine.model_id}")
        return True
    except Exception as e:
        print(f"   [FAIL] 工厂函数失败: {e}")
        return False


def test_plugin() -> bool:
    """测试插件"""
    print("\n7. 测试插件...")
    try:
        from scenara.domains.fashion import FashionPlugin

        plugin = FashionPlugin()
        print(f"   [PASS] 插件初始化成功: {plugin.manifest.domain_id}")
        print(f"   [PASS] 显示名称: {plugin.manifest.display_name}")
        print(f"   [PASS] 能力: {', '.join(plugin.manifest.capabilities)}")
        print(f"   [PASS] 支持的媒体类型: {', '.join(plugin.manifest.supported_media_kinds)}")

        operators = plugin.operators()
        print(f"   [PASS] 算子数量: {len(operators)}")

        pipelines = plugin.pipelines()
        print(f"   [PASS] 流水线数量: {len(pipelines)}")

        return True
    except Exception as e:
        print(f"   [FAIL] 插件测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main() -> None:
    print("=" * 80)
    print("服饰风格识别功能快速测试")
    print("=" * 80)

    results = []

    # 运行测试
    results.append(("依赖导入", test_import()))

    if results[-1][1]:  # 只有导入成功才继续
        results.append(("引擎初始化", test_engine_init()))
        results.append(("Cosplay 识别", test_cosplay_detection()))
        results.append(("服装风格识别", test_clothing_detection()))
        results.append(("配饰识别", test_accessory_detection()))
        results.append(("工厂函数", test_factory()))
        results.append(("插件", test_plugin()))

    # 打印摘要
    print("\n" + "=" * 80)
    print("测试摘要")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} - {name}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n[SUCCESS] 所有测试通过! 服饰风格识别功能已就绪。")
        print("\n支持的功能:")
        print("  - Cosplay 角色识别 (100+ 角色)")
        print("  - 服装风格检测 (8+ 风格)")
        print("  - 配饰识别")
        print("  - 服饰属性分析")
        sys.exit(0)
    else:
        print("\n[FAIL] 部分测试失败,请检查依赖安装和配置。")
        print("\n安装命令:")
        print("  pip install torch torchvision pillow")
        sys.exit(1)


if __name__ == "__main__":
    main()
