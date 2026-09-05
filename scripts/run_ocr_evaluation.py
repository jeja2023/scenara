"""
OCR 评估运行脚本

使用方法:
    python scripts/run_ocr_evaluation.py --dataset tests/ocr_evaluation/dataset.json --output reports/ocr_evaluation_report.json

环境变量:
    SCENARA_OCR_MODEL_DIR: 模型目录
    SCENARA_OCR_USE_GPU: 是否使用 GPU
"""

import argparse
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scenara.domains.ocr.evaluation import OcrEvaluator, load_evaluation_dataset  # noqa: E402
from scenara.domains.ocr.paddle_reference_adapter import ReferencePaddleOcrEngine  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 OCR 质量评估")
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="评估数据集 JSON 文件路径",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/ocr_evaluation_report.json"),
        help="评估报告输出路径",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        help="OCR 模型目录(覆盖环境变量)",
    )
    parser.add_argument(
        "--no-gpu",
        action="store_true",
        help="不使用 GPU 加速",
    )
    parser.add_argument(
        "--skip-checksum",
        action="store_true",
        help="跳过模型权重校验",
    )

    args = parser.parse_args()

    # 验证数据集文件
    if not args.dataset.exists():
        logger.error(f"Dataset file not found: {args.dataset}")
        sys.exit(1)

    # 加载评估数据集
    logger.info(f"Loading evaluation dataset from {args.dataset}")
    samples = load_evaluation_dataset(args.dataset)

    if not samples:
        logger.error("No valid samples found in dataset")
        sys.exit(1)

    # 初始化 OCR 引擎
    logger.info("Initializing OCR engine...")
    try:
        engine = ReferencePaddleOcrEngine(
            model_dir=str(args.model_dir) if args.model_dir else None,
            use_gpu=not args.no_gpu,
            verify_checksums=not args.skip_checksum,
        )
        logger.info(
            f"OCR engine initialized: {engine.model_id} v{engine.version} "
            f"(GPU: {not args.no_gpu})"
        )
    except Exception as exc:
        logger.error(f"Failed to initialize OCR engine: {exc}")
        sys.exit(1)

    # 运行评估
    evaluator = OcrEvaluator(engine)
    report = evaluator.evaluate_dataset(samples)

    # 保存报告
    evaluator.save_report(report, args.output)

    # 打印摘要
    print("\n" + "=" * 80)
    print("OCR 评估报告摘要")
    print("=" * 80)
    print(f"引擎: {report.engine_id} v{report.engine_version}")
    print(f"样本总数: {report.total_samples}")
    print(f"字符准确率: {report.character_accuracy_avg:.2%}")
    print(f"词准确率: {report.word_accuracy_avg:.2%}")
    print(f"平均推理时间: {report.inference_time_avg_ms:.1f} ms")
    print("\n按类别统计:")
    for category, metrics in report.results_by_category.items():
        print(
            f"  {category}: "
            f"char_acc={metrics['character_accuracy']:.2%}, "
            f"samples={metrics['samples']}"
        )
    print("=" * 80)
    print(f"\n完整报告已保存至: {args.output}")


if __name__ == "__main__":
    main()
