"""
服饰风格识别评估框架

用于评估服饰识别引擎在不同场景下的准确率和性能
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class FashionEvaluationSample:
    """服饰识别评估样本"""

    sample_id: str
    image_path: Path
    ground_truth: dict[str, Any]  # {"cosplay": [...], "clothing": [...], "accessories": [...]}
    category: str = "general"  # general, cosplay, clothing, mixed
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FashionEvaluationResult:
    """单个样本的评估结果"""

    sample_id: str
    predicted: dict[str, Any]
    ground_truth: dict[str, Any]

    # Cosplay 指标
    cosplay_accuracy: float
    cosplay_precision: float
    cosplay_recall: float

    # 服装风格指标
    clothing_accuracy: float
    clothing_precision: float
    clothing_recall: float

    # 配饰指标
    accessory_accuracy: float

    # 综合指标
    overall_f1: float
    inference_time_ms: float
    avg_confidence: float


@dataclass
class FashionEvaluationReport:
    """服饰识别评估报告"""

    engine_id: str
    engine_version: str
    timestamp: float
    total_samples: int

    # 平均指标
    cosplay_accuracy_avg: float
    cosplay_precision_avg: float
    cosplay_recall_avg: float
    clothing_accuracy_avg: float
    clothing_precision_avg: float
    clothing_recall_avg: float
    accessory_accuracy_avg: float
    overall_f1_avg: float
    inference_time_avg_ms: float

    # 按类别统计
    results_by_category: dict[str, dict[str, float]]

    # 详细结果
    individual_results: list[FashionEvaluationResult]


class FashionEvaluator:
    """服饰风格识别引擎评估器"""

    def __init__(self, engine: Any) -> None:
        """
        初始化评估器

        Args:
            engine: 实现了 detect_cosplay/detect_clothing_style/detect_accessories 方法的引擎
        """
        self.engine = engine

    def evaluate_sample(self, sample: FashionEvaluationSample) -> FashionEvaluationResult:
        """
        评估单个样本

        Args:
            sample: 评估样本

        Returns:
            评估结果
        """
        # 加载图像
        image = self._load_image(sample.image_path)

        if image is None:
            raise ValueError(f"Failed to load image: {sample.image_path}")

        # 执行识别
        start_time = time.perf_counter()

        cosplay_pred = self.engine.detect_cosplay(image, min_confidence=0.3)
        clothing_pred = self.engine.detect_clothing_style(image, min_confidence=0.3)
        accessory_pred = self.engine.detect_accessories(image, min_confidence=0.3)

        inference_time_ms = (time.perf_counter() - start_time) * 1000

        predicted = {
            "cosplay": cosplay_pred,
            "clothing": clothing_pred,
            "accessories": accessory_pred,
        }

        # 计算 Cosplay 指标
        cosplay_acc, cosplay_prec, cosplay_rec = self._compute_cosplay_metrics(
            cosplay_pred, sample.ground_truth.get("cosplay", [])
        )

        # 计算服装风格指标
        clothing_acc, clothing_prec, clothing_rec = self._compute_clothing_metrics(
            clothing_pred, sample.ground_truth.get("clothing", [])
        )

        # 计算配饰指标
        accessory_acc = self._compute_accessory_accuracy(
            accessory_pred, sample.ground_truth.get("accessories", [])
        )

        # 计算综合 F1
        overall_prec = (cosplay_prec + clothing_prec) / 2
        overall_rec = (cosplay_rec + clothing_rec) / 2
        overall_f1 = 2 * overall_prec * overall_rec / (overall_prec + overall_rec) if (overall_prec + overall_rec) > 0 else 0

        # 平均置信度
        all_confidences = []
        all_confidences.extend([p.get("confidence", 0) for p in cosplay_pred])
        all_confidences.extend([p.get("confidence", 0) for p in clothing_pred])
        all_confidences.extend([p.get("confidence", 0) for p in accessory_pred])
        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0

        return FashionEvaluationResult(
            sample_id=sample.sample_id,
            predicted=predicted,
            ground_truth=sample.ground_truth,
            cosplay_accuracy=cosplay_acc,
            cosplay_precision=cosplay_prec,
            cosplay_recall=cosplay_rec,
            clothing_accuracy=clothing_acc,
            clothing_precision=clothing_prec,
            clothing_recall=clothing_rec,
            accessory_accuracy=accessory_acc,
            overall_f1=overall_f1,
            inference_time_ms=inference_time_ms,
            avg_confidence=avg_confidence,
        )

    def evaluate_dataset(
        self,
        samples: list[FashionEvaluationSample],
    ) -> FashionEvaluationReport:
        """
        评估整个数据集

        Args:
            samples: 评估样本列表

        Returns:
            评估报告
        """
        logger.info(f"Starting fashion recognition evaluation with {len(samples)} samples")

        results: list[FashionEvaluationResult] = []
        for idx, sample in enumerate(samples, 1):
            try:
                result = self.evaluate_sample(sample)
                results.append(result)
                logger.info(
                    f"[{idx}/{len(samples)}] {sample.sample_id}: "
                    f"cosplay_acc={result.cosplay_accuracy:.2%}, "
                    f"clothing_acc={result.clothing_accuracy:.2%}, "
                    f"f1={result.overall_f1:.2f}"
                )
            except Exception as exc:
                logger.error(f"Failed to evaluate {sample.sample_id}: {exc}")
                continue

        if not results:
            raise ValueError("No samples were successfully evaluated")

        # 计算整体指标
        cosplay_acc_avg = sum(r.cosplay_accuracy for r in results) / len(results)
        cosplay_prec_avg = sum(r.cosplay_precision for r in results) / len(results)
        cosplay_rec_avg = sum(r.cosplay_recall for r in results) / len(results)
        clothing_acc_avg = sum(r.clothing_accuracy for r in results) / len(results)
        clothing_prec_avg = sum(r.clothing_precision for r in results) / len(results)
        clothing_rec_avg = sum(r.clothing_recall for r in results) / len(results)
        accessory_acc_avg = sum(r.accessory_accuracy for r in results) / len(results)
        f1_avg = sum(r.overall_f1 for r in results) / len(results)
        time_avg = sum(r.inference_time_ms for r in results) / len(results)

        # 按类别统计
        category_results: dict[str, list[FashionEvaluationResult]] = {}
        for sample, result in zip(samples, results):
            cat = sample.category
            if cat not in category_results:
                category_results[cat] = []
            category_results[cat].append(result)

        results_by_category: dict[str, dict[str, float]] = {}
        for cat, cat_results in category_results.items():
            results_by_category[cat] = {
                "cosplay_accuracy": sum(r.cosplay_accuracy for r in cat_results) / len(cat_results),
                "clothing_accuracy": sum(r.clothing_accuracy for r in cat_results) / len(cat_results),
                "overall_f1": sum(r.overall_f1 for r in cat_results) / len(cat_results),
                "inference_time_ms": sum(r.inference_time_ms for r in cat_results) / len(cat_results),
                "samples": len(cat_results),
            }

        report = FashionEvaluationReport(
            engine_id=getattr(self.engine, "model_id", "unknown"),
            engine_version=getattr(self.engine, "version", "unknown"),
            timestamp=time.time(),
            total_samples=len(results),
            cosplay_accuracy_avg=cosplay_acc_avg,
            cosplay_precision_avg=cosplay_prec_avg,
            cosplay_recall_avg=cosplay_rec_avg,
            clothing_accuracy_avg=clothing_acc_avg,
            clothing_precision_avg=clothing_prec_avg,
            clothing_recall_avg=clothing_rec_avg,
            accessory_accuracy_avg=accessory_acc_avg,
            overall_f1_avg=f1_avg,
            inference_time_avg_ms=time_avg,
            results_by_category=results_by_category,
            individual_results=results,
        )

        logger.info(
            f"Evaluation complete: {len(results)}/{len(samples)} samples, "
            f"avg_f1={f1_avg:.2%}"
        )

        return report

    def _load_image(self, image_path: Path) -> Any | None:
        """加载图像"""
        try:
            from PIL import Image
            return Image.open(image_path).convert("RGB")
        except Exception as exc:
            logger.error(f"Failed to load image {image_path}: {exc}")
            return None

    def _compute_cosplay_metrics(
        self,
        predictions: list[dict[str, Any]],
        ground_truth: list[dict[str, Any]],
    ) -> tuple[float, float, float]:
        """计算 Cosplay 识别指标"""
        if not ground_truth:
            return (1.0, 1.0, 1.0) if not predictions else (0.0, 0.0, 0.0)

        if not predictions:
            return (0.0, 0.0, 0.0)

        # 提取角色名称
        gt_characters = {gt["character_name"] for gt in ground_truth}
        pred_characters = {pred["character_name"] for pred in predictions}

        # 计算指标
        true_positives = len(gt_characters & pred_characters)
        false_positives = len(pred_characters - gt_characters)
        false_negatives = len(gt_characters - pred_characters)

        accuracy = true_positives / len(gt_characters) if gt_characters else 0
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0

        return (accuracy, precision, recall)

    def _compute_clothing_metrics(
        self,
        predictions: list[dict[str, Any]],
        ground_truth: list[dict[str, Any]],
    ) -> tuple[float, float, float]:
        """计算服装风格识别指标"""
        if not ground_truth:
            return (1.0, 1.0, 1.0) if not predictions else (0.0, 0.0, 0.0)

        if not predictions:
            return (0.0, 0.0, 0.0)

        # 提取风格类型
        gt_styles = {gt["style_type"] for gt in ground_truth}
        pred_styles = {pred["style_type"] for pred in predictions}

        # 计算指标
        true_positives = len(gt_styles & pred_styles)
        false_positives = len(pred_styles - gt_styles)
        false_negatives = len(gt_styles - pred_styles)

        accuracy = true_positives / len(gt_styles) if gt_styles else 0
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0

        return (accuracy, precision, recall)

    def _compute_accessory_accuracy(
        self,
        predictions: list[dict[str, Any]],
        ground_truth: list[dict[str, Any]],
    ) -> float:
        """计算配饰识别准确率"""
        if not ground_truth:
            return 1.0 if not predictions else 0.0

        if not predictions:
            return 0.0

        gt_types = {gt["accessory_type"] for gt in ground_truth}
        pred_types = {pred["accessory_type"] for pred in predictions}

        intersection = len(gt_types & pred_types)
        union = len(gt_types | pred_types)

        return intersection / union if union > 0 else 0.0

    def save_report(self, report: FashionEvaluationReport, output_path: Path) -> None:
        """
        保存评估报告为 JSON

        Args:
            report: 评估报告
            output_path: 输出文件路径
        """
        output_data = {
            "engine_id": report.engine_id,
            "engine_version": report.engine_version,
            "timestamp": report.timestamp,
            "total_samples": report.total_samples,
            "metrics": {
                "cosplay_accuracy_avg": report.cosplay_accuracy_avg,
                "cosplay_precision_avg": report.cosplay_precision_avg,
                "cosplay_recall_avg": report.cosplay_recall_avg,
                "clothing_accuracy_avg": report.clothing_accuracy_avg,
                "clothing_precision_avg": report.clothing_precision_avg,
                "clothing_recall_avg": report.clothing_recall_avg,
                "accessory_accuracy_avg": report.accessory_accuracy_avg,
                "overall_f1_avg": report.overall_f1_avg,
                "inference_time_avg_ms": report.inference_time_avg_ms,
            },
            "results_by_category": report.results_by_category,
            "individual_results": [
                {
                    "sample_id": r.sample_id,
                    "cosplay_accuracy": r.cosplay_accuracy,
                    "clothing_accuracy": r.clothing_accuracy,
                    "overall_f1": r.overall_f1,
                    "inference_time_ms": r.inference_time_ms,
                }
                for r in report.individual_results
            ],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Evaluation report saved to {output_path}")


def load_evaluation_dataset(dataset_path: Path) -> list[FashionEvaluationSample]:
    """
    从 JSON 文件加载评估数据集

    数据集格式:
    {
        "samples": [
            {
                "sample_id": "sample_001",
                "image_path": "images/sample_001.jpg",
                "ground_truth": {
                    "cosplay": [{"character_name": "初音未来", "series_name": "VOCALOID"}],
                    "clothing": [{"style_type": "jk_uniform", "style_label": "JK制服"}],
                    "accessories": [{"accessory_type": "wig", "accessory_label": "假发"}]
                },
                "category": "cosplay"
            },
            ...
        ]
    }

    Args:
        dataset_path: 数据集 JSON 文件路径

    Returns:
        评估样本列表
    """
    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)

    samples: list[FashionEvaluationSample] = []
    base_dir = dataset_path.parent

    for item in data.get("samples", []):
        image_path = base_dir / item["image_path"]
        if not image_path.exists():
            logger.warning(f"Image not found: {image_path}")
            continue

        samples.append(
            FashionEvaluationSample(
                sample_id=item["sample_id"],
                image_path=image_path,
                ground_truth=item["ground_truth"],
                category=item.get("category", "general"),
                metadata=item.get("metadata", {}),
            )
        )

    logger.info(f"Loaded {len(samples)} evaluation samples from {dataset_path}")
    return samples


__all__ = [
    "FashionEvaluator",
    "FashionEvaluationSample",
    "FashionEvaluationResult",
    "FashionEvaluationReport",
    "load_evaluation_dataset",
]
