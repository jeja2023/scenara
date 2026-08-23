"""
OCR 质量评估框架

用于评估 OCR 引擎在不同场景下的准确率和性能
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class OcrEvaluationSample:
    """OCR 评估样本"""

    sample_id: str
    image_path: Path
    ground_truth: str
    language: str = "zh"
    category: str = "general"  # general, rotated, handwritten, table, multi_column
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OcrEvaluationResult:
    """单个样本的评估结果"""

    sample_id: str
    predicted_text: str
    ground_truth: str
    character_accuracy: float
    word_accuracy: float
    edit_distance: int
    inference_time_ms: float
    confidence_score: float | None = None


@dataclass
class OcrEvaluationReport:
    """OCR 评估报告"""

    engine_id: str
    engine_version: str
    timestamp: float
    total_samples: int
    character_accuracy_avg: float
    word_accuracy_avg: float
    inference_time_avg_ms: float
    results_by_category: dict[str, dict[str, float]]
    individual_results: list[OcrEvaluationResult]


class OcrEvaluator:
    """OCR 引擎评估器"""

    def __init__(self, engine: Any) -> None:
        """
        初始化评估器

        Args:
            engine: 实现了 predict() 方法的 OCR 引擎
        """
        self.engine = engine

    def evaluate_sample(self, sample: OcrEvaluationSample) -> OcrEvaluationResult:
        """
        评估单个样本

        Args:
            sample: 评估样本

        Returns:
            评估结果
        """
        # 加载图像
        image = Image.open(sample.image_path).convert("RGB")

        # 执行 OCR
        start_time = time.perf_counter()
        predictions = self.engine.predict(image, language_hint=sample.language)
        inference_time_ms = (time.perf_counter() - start_time) * 1000

        # 提取文本和置信度
        predicted_text = ""
        total_confidence = 0.0
        confidence_count = 0

        for block in predictions:
            text = block.get("text", "")
            predicted_text += text
            score = block.get("score")
            if score is not None:
                total_confidence += score
                confidence_count += 1

        avg_confidence = total_confidence / confidence_count if confidence_count > 0 else None

        # 计算准确率
        char_acc = self._character_accuracy(predicted_text, sample.ground_truth)
        word_acc = self._word_accuracy(predicted_text, sample.ground_truth)
        edit_dist = self._levenshtein_distance(predicted_text, sample.ground_truth)

        return OcrEvaluationResult(
            sample_id=sample.sample_id,
            predicted_text=predicted_text,
            ground_truth=sample.ground_truth,
            character_accuracy=char_acc,
            word_accuracy=word_acc,
            edit_distance=edit_dist,
            inference_time_ms=inference_time_ms,
            confidence_score=avg_confidence,
        )

    def evaluate_dataset(
        self,
        samples: list[OcrEvaluationSample],
    ) -> OcrEvaluationReport:
        """
        评估整个数据集

        Args:
            samples: 评估样本列表

        Returns:
            评估报告
        """
        logger.info(f"Starting OCR evaluation with {len(samples)} samples")

        results: list[OcrEvaluationResult] = []
        for idx, sample in enumerate(samples, 1):
            try:
                result = self.evaluate_sample(sample)
                results.append(result)
                logger.info(
                    f"[{idx}/{len(samples)}] {sample.sample_id}: "
                    f"char_acc={result.character_accuracy:.2%}, "
                    f"time={result.inference_time_ms:.1f}ms"
                )
            except Exception as exc:
                logger.error(f"Failed to evaluate {sample.sample_id}: {exc}")
                continue

        # 计算整体指标
        total_char_acc = sum(r.character_accuracy for r in results) / len(results) if results else 0.0
        total_word_acc = sum(r.word_accuracy for r in results) / len(results) if results else 0.0
        total_time = sum(r.inference_time_ms for r in results) / len(results) if results else 0.0

        # 按类别统计
        category_results: dict[str, list[OcrEvaluationResult]] = {}
        for sample, result in zip(samples, results):
            cat = sample.category
            if cat not in category_results:
                category_results[cat] = []
            category_results[cat].append(result)

        results_by_category: dict[str, dict[str, float]] = {}
        for cat, cat_results in category_results.items():
            results_by_category[cat] = {
                "character_accuracy": sum(r.character_accuracy for r in cat_results) / len(cat_results),
                "word_accuracy": sum(r.word_accuracy for r in cat_results) / len(cat_results),
                "inference_time_ms": sum(r.inference_time_ms for r in cat_results) / len(cat_results),
                "samples": len(cat_results),
            }

        report = OcrEvaluationReport(
            engine_id=getattr(self.engine, "model_id", "unknown"),
            engine_version=getattr(self.engine, "version", "unknown"),
            timestamp=time.time(),
            total_samples=len(results),
            character_accuracy_avg=total_char_acc,
            word_accuracy_avg=total_word_acc,
            inference_time_avg_ms=total_time,
            results_by_category=results_by_category,
            individual_results=results,
        )

        logger.info(
            f"Evaluation complete: {len(results)}/{len(samples)} samples, "
            f"avg_char_acc={total_char_acc:.2%}, avg_time={total_time:.1f}ms"
        )

        return report

    @staticmethod
    def _character_accuracy(predicted: str, ground_truth: str) -> float:
        """计算字符级准确率"""
        if not ground_truth:
            return 1.0 if not predicted else 0.0

        # 移除空白符进行比较
        pred_clean = predicted.replace(" ", "").replace("\n", "")
        gt_clean = ground_truth.replace(" ", "").replace("\n", "")

        if not gt_clean:
            return 1.0 if not pred_clean else 0.0

        # 计算编辑距离
        distance = OcrEvaluator._levenshtein_distance(pred_clean, gt_clean)
        accuracy = 1.0 - (distance / len(gt_clean))
        return max(0.0, accuracy)

    @staticmethod
    def _word_accuracy(predicted: str, ground_truth: str) -> float:
        """计算词级准确率"""
        pred_words = set(predicted.split())
        gt_words = set(ground_truth.split())

        if not gt_words:
            return 1.0 if not pred_words else 0.0

        # 计算交集
        common = pred_words & gt_words
        return len(common) / len(gt_words)

    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        """计算 Levenshtein 编辑距离"""
        if len(s1) < len(s2):
            return OcrEvaluator._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # 插入、删除、替换的代价
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def save_report(self, report: OcrEvaluationReport, output_path: Path) -> None:
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
                "character_accuracy_avg": report.character_accuracy_avg,
                "word_accuracy_avg": report.word_accuracy_avg,
                "inference_time_avg_ms": report.inference_time_avg_ms,
            },
            "results_by_category": report.results_by_category,
            "individual_results": [
                {
                    "sample_id": r.sample_id,
                    "character_accuracy": r.character_accuracy,
                    "word_accuracy": r.word_accuracy,
                    "edit_distance": r.edit_distance,
                    "inference_time_ms": r.inference_time_ms,
                    "confidence_score": r.confidence_score,
                }
                for r in report.individual_results
            ],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Evaluation report saved to {output_path}")


def load_evaluation_dataset(dataset_path: Path) -> list[OcrEvaluationSample]:
    """
    从 JSON 文件加载评估数据集

    数据集格式:
    {
        "samples": [
            {
                "sample_id": "sample_001",
                "image_path": "images/sample_001.png",
                "ground_truth": "正确的文本内容",
                "language": "zh",
                "category": "general"
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

    samples: list[OcrEvaluationSample] = []
    base_dir = dataset_path.parent

    for item in data.get("samples", []):
        image_path = base_dir / item["image_path"]
        if not image_path.exists():
            logger.warning(f"Image not found: {image_path}")
            continue

        samples.append(
            OcrEvaluationSample(
                sample_id=item["sample_id"],
                image_path=image_path,
                ground_truth=item["ground_truth"],
                language=item.get("language", "zh"),
                category=item.get("category", "general"),
                metadata=item.get("metadata", {}),
            )
        )

    logger.info(f"Loaded {len(samples)} evaluation samples from {dataset_path}")
    return samples


__all__ = [
    "OcrEvaluator",
    "OcrEvaluationSample",
    "OcrEvaluationResult",
    "OcrEvaluationReport",
    "load_evaluation_dataset",
]
