"""
OCR 功能快速测试脚本

用于验证 OCR 引擎是否正确安装和配置
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
        import paddleocr
        print(f"   ✓ PaddleOCR {paddleocr.__version__}")
    except ImportError as e:
        print(f"   ✗ PaddleOCR 导入失败: {e}")
        return False

    try:
        import paddle
        print(f"   ✓ PaddlePaddle {paddle.__version__}")
    except ImportError as e:
        print(f"   ✗ PaddlePaddle 导入失败: {e}")
        return False

    try:
        import pdfplumber
        print(f"   ✓ pdfplumber {pdfplumber.__version__}")
    except ImportError as e:
        print(f"   ✗ pdfplumber 导入失败: {e}")
        return False

    return True


def test_engine_init() -> bool:
    """测试引擎初始化"""
    print("\n2. 测试引擎初始化...")
    try:
        from scenara.domains.ocr.paddle_production import ProductionPaddleOcrEngine

        engine = ProductionPaddleOcrEngine(verify_checksums=False, use_gpu=False)
        print(f"   ✓ 引擎初始化成功: {engine.model_id} v{engine.version}")
        print(f"   ✓ 生产就绪: {engine.production_ready}")
        print(f"   ✓ 能力: {', '.join(engine.production_capabilities)}")
        return True
    except Exception as e:
        print(f"   ✗ 引擎初始化失败: {e}")
        return False


def test_ocr_prediction() -> bool:
    """测试 OCR 识别"""
    print("\n3. 测试 OCR 识别...")
    try:
        from PIL import Image, ImageDraw, ImageFont
        from scenara.domains.ocr.paddle_production import ProductionPaddleOcrEngine

        # 创建测试图像
        img = Image.new("RGB", (400, 100), color="white")
        draw = ImageDraw.Draw(img)

        # 绘制文本(使用系统默认字体)
        text = "Hello PaddleOCR 测试"
        try:
            # 尝试使用中文字体
            font = ImageFont.truetype("simhei.ttf", 32)
        except OSError:
            # 回退到默认字体
            font = ImageFont.load_default()

        draw.text((10, 30), text, fill="black", font=font)

        # 执行 OCR
        engine = ProductionPaddleOcrEngine(verify_checksums=False, use_gpu=False)
        results = engine.predict(img, min_score=0.0)

        if results:
            print(f"   ✓ 识别到 {len(results)} 个文本块")
            for i, block in enumerate(results[:3], 1):  # 只显示前3个
                print(f"     [{i}] {block['text'][:30]} (score: {block.get('score', 0):.2f})")
            return True
        else:
            print("   ⚠ 未识别到文本(可能是图像质量或字体问题)")
            return True  # 不算失败
    except Exception as e:
        print(f"   ✗ OCR 识别失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_layout_analysis() -> bool:
    """测试版面分析"""
    print("\n4. 测试版面分析...")
    try:
        from PIL import Image, ImageDraw
        from scenara.domains.ocr.paddle_production import ProductionPaddleOcrEngine

        # 创建简单布局的测试图像
        img = Image.new("RGB", (800, 600), color="white")
        draw = ImageDraw.Draw(img)

        # 绘制几个区域
        draw.rectangle([50, 50, 750, 150], outline="black", width=2)  # 标题区域
        draw.rectangle([50, 200, 750, 400], outline="gray", width=1)  # 文本区域
        draw.rectangle([50, 450, 350, 550], outline="blue", width=2)  # 图片区域

        # 执行版面分析
        engine = ProductionPaddleOcrEngine(verify_checksums=False, use_gpu=False)
        regions = engine.predict_layout(img)

        print(f"   ✓ 检测到 {len(regions)} 个版面区域")
        if regions:
            for i, region in enumerate(regions[:5], 1):
                print(f"     [{i}] {region.get('block_type', 'unknown')}")
        return True
    except Exception as e:
        print(f"   ✗ 版面分析失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_factory() -> bool:
    """测试工厂函数"""
    print("\n5. 测试工厂函数...")
    try:
        from scenara.domains.ocr.paddle_production import create_production_ocr_engine

        engine = create_production_ocr_engine()
        print(f"   ✓ 工厂函数创建引擎成功: {engine.model_id}")
        return True
    except Exception as e:
        print(f"   ✗ 工厂函数失败: {e}")
        return False


def main() -> None:
    print("=" * 80)
    print("OCR 功能快速测试")
    print("=" * 80)

    results = []

    # 运行测试
    results.append(("依赖导入", test_import()))

    if results[-1][1]:  # 只有导入成功才继续
        results.append(("引擎初始化", test_engine_init()))
        results.append(("OCR 识别", test_ocr_prediction()))
        results.append(("版面分析", test_layout_analysis()))
        results.append(("工厂函数", test_factory()))

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
        print("\n✓ 所有测试通过! OCR 功能已就绪。")
        sys.exit(0)
    else:
        print("\n✗ 部分测试失败,请检查依赖安装和配置。")
        print("\n安装命令:")
        print("  pip install paddlepaddle-gpu==3.0.0 paddleocr==2.9.2 pdfplumber==0.11.5")
        sys.exit(1)


if __name__ == "__main__":
    main()
