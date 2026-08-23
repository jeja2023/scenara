"""
行为识别评估框架

用于评估行为识别引擎在不同场景下的准确率和性能
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BehaviorEvaluationSample:
    """行为识别评估样本"""

    sample_id: str
    video_path: Path
    ground_truth_actions: list[dict[str, Any]]  # [{"action": "walking", "start_frame": 0, "end_frame": 30}]
    fps: float = 30.0
    category: str = "general"  # general, sports, anomaly, multi_person
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BehaviorEvaluationResult:
    """单个样本的评估结果"""

    sample_id: str
    predicted_actions: list[dict[str, Any]]
    ground_truth_actions: list[dict[str, Any]]
    action_accuracy: float  # 动作类别准确率
    temporal_iou: float  # 时序 IoU
    precision: float
    recall: float
    f1_score: float
    inference_time_ms: float
    avg_confidence: float


@dataclass
class BehaviorEvaluationReport:
    """行为识别评估报告"""

    engine_id: str
    engine_version: str
    timestamp: float
    total_samples: int
    action_accuracy_avg: float
    temporal_iou_avg: float
    precision_avg: float
    recall_avg: float
    f1_score_avg: float
    inference_time_avg_ms: float
    results_by_category: dict[str, dict[str, float]]
    individual_results: list[BehaviorEvaluationResult]


class BehaviorEvaluator:
    """行为识别引擎评估器"""

    def __init__(self, engine: Any) -> None:
        """
        初始化评估器

        Args:
            engine: 实现了 predict() 方法的行为识别引擎
        """
        self.engine = engine

    def evaluate_sample(self, sample: BehaviorEvaluationSample) -> BehaviorEvaluationResult:
        """
        评估单个样本

        Args:
            sample: 评估样本

        Returns:
            评估结果
        """
        # 加载视频帧
        frames = self._load_video_frames(sample.video_path)

        if not frames:
            raise ValueError(f"Failed to load video: {sample.video_path}")

        # 执行行为识别
        start_time = time.perf_counter()
        predictions = self.engine.predict(frames)
        inference_time_ms = (time.perf_counter() - start_time) * 1000

        # 计算指标
        action_acc = self._compute_action_accuracy(predictions, sample.ground_truth_actions)
        temporal_iou = self._compute_temporal_iou(predictions, sample.ground_truth_actions)
        precision, recall, f1 = self._compute_precision_recall_f1(predictions, sample.ground_truth_actions)

        # 平均置信度
        avg_confidence = 0.0
        if predictions:
            confidences = [p.get("confidence", 0.0) for p in predictions]
            avg_confidence = sum(confidences) / len(confidences)

        return BehaviorEvaluationResult(
            sample_id=sample.sample_id,
            predicted_actions=predictions,
            ground_truth_actions=sample.ground_truth_actions,
            action_accuracy=action_acc,
            temporal_iou=temporal_iou,
            precision=precision,
            recall=recall,
            f1_score=f1,
            inference_time_ms=inference_time_ms,
            avg_confidence=avg_confidence,
        )

    def evaluate_dataset(
        self,
        samples: list[BehaviorEvaluationSample],
    ) -> BehaviorEvaluationReport:
        """
        评估整个数据集

        Args:
            samples: 评估样本列表

        Returns:
            评估报告
        """
        logger.info(f"Starting behavior recognition evaluation with {len(samples)} samples")

        results: list[BehaviorEvaluationResult] = []
        for idx, sample in enumerate(samples, 1):
            try:
                result = self.evaluate_sample(sample)
                results.append(result)
                logger.info(
                    f"[{idx}/{len(samples)}] {sample.sample_id}: "
                    f"acc={result.action_accuracy:.2%}, "
                    f"iou={result.temporal_iou:.2f}, "
                    f"f1={result.f1_score:.2f}"
                )
            except Exception as exc:
                logger.error(f"Failed to evaluate {sample.sample_id}: {exc}")
                continue

        if not results:
            raise ValueError("No samples were successfully evaluated")

        # 计算整体指标
        action_acc_avg = sum(r.action_accuracy for r in results) / len(results)
        temporal_iou_avg = sum(r.temporal_iou for r in results) / len(results)
        precision_avg = sum(r.precision for r in results) / len(results)
        recall_avg = sum(r.recall for r in results) / len(results)
        f1_avg = sum(r.f1_score for r in results) / len(results)
        time_avg = sum(r.inference_time_ms for r in results) / len(results)

        # 按类别统计
        category_results: dict[str, list[BehaviorEvaluationResult]] = {}
        for sample, result in zip(samples, results):
            cat = sample.category
            if cat not in category_results:
                category_results[cat] = []
            category_results[cat].append(result)

        results_by_category: dict[str, dict[str, float]] = {}
        for cat, cat_results in category_results.items():
            results_by_category[cat] = {
                "action_accuracy": sum(r.action_accuracy for r in cat_results) / len(cat_results),
                "temporal_iou": sum(r.temporal_iou for r in cat_results) / len(cat_results),
                "f1_score": sum(r.f1_score for r in cat_results) / len(cat_results),
                "inference_time_ms": sum(r.inference_time_ms for r in cat_results) / len(cat_results),
                "samples": len(cat_results),
            }

        report = BehaviorEvaluationReport(
            engine_id=getattr(self.engine, "model_id", "unknown"),
            engine_version=getattr(self.engine, "version", "unknown"),
            timestamp=time.time(),
            total_samples=len(results),
            action_accuracy_avg=action_acc_avg,
            temporal_iou_avg=temporal_iou_avg,
            precision_avg=precision_avg,
            recall_avg=recall_avg,
            f1_score_avg=f1_avg,
            inference_time_avg_ms=time_avg,
            results_by_category=results_by_category,
            individual_results=results,
        )

        logger.info(
            f"Evaluation complete: {len(results)}/{len(samples)} samples, "
            f"avg_acc={action_acc_avg:.2%}, avg_f1={f1_avg:.2%}"
        )

        return report

    def _load_video_frames(self, video_path: Path) -> list[np.ndarray]:
        """加载视频帧"""
        try:
            import cv2

            cap = cv2.VideoCapture(str(video_path))
            frames = []

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # 转换为 RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(frame)

            cap.release()
            return frames

        except Exception as exc:
            logger.error(f"Failed to load video {video_path}: {exc}")
            return []

    def _compute_action_accuracy(
        self,
        predictions: list[dict[str, Any]],
        ground_truth: list[dict[str, Any]],
    ) -> float:
        """计算动作类别准确率"""
        if not ground_truth:
            return 1.0 if not predictions else 0.0

        if not predictions:
            return 0.0

        # 简单匹配:如果预测的主要动作与真实标签匹配
        gt_actions = {gt["action"] for gt in ground_truth}
        pred_actions = {pred["action_type"] for pred in predictions}

        intersection = gt_actions & pred_actions
        union = gt_actions | pred_actions

        return len(intersection) / len(union) if union else 0.0

    def _compute_temporal_iou(
        self,
        predictions: list[dict[str, Any]],
        ground_truth: list[dict[str, Any]],
    ) -> float:
        """计算时序 IoU (Intersection over Union)"""
        if not ground_truth or not predictions:
            return 0.0

        total_iou = 0.0
        count = 0

        for gt in ground_truth:
            gt_start = gt.get("start_frame", 0)
            gt_end = gt.get("end_frame", 0)
            gt_action = gt.get("action")

            best_iou = 0.0
            for pred in predictions:
                if pred.get("action_type") != gt_action:
                    continue

                pred_start = pred.get("start_frame", 0)
                pred_end = pred.get("end_frame", 0)

                # 计算 IoU
                intersection = max(0, min(gt_end, pred_end) - max(gt_start, pred_start))
                union = max(gt_end, pred_end) - min(gt_start, pred_start)

                iou = intersection / union if union > 0 else 0.0
                best_iou = max(best_iou, iou)

            total_iou += best_iou
            count += 1

        return total_iou / count if count > 0 else 0.0

    def _compute_precision_recall_f1(
        self,
        predictions: list[dict[str, Any]],
        ground_truth: list[dict[str, Any]],
    ) -> tuple[float, float, float]:
        """计算精确率、召回率和 F1 分数"""
        if not ground_truth:
            return (0.0, 0.0, 0.0) if predictions else (1.0, 1.0, 1.0)

        if not predictions:
            return (0.0, 0.0, 0.0)

        gt_actions = {gt["action"] for gt in ground_truth}
        pred_actions = {pred["action_type"] for pred in predictions}

        true_positives = len(gt_actions & pred_actions)
        false_positives = len(pred_actions - gt_actions)
        false_negatives = len(gt_actions - pred_actions)

        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        return (precision, recall, f1)

    def save_report(self, report: BehaviorEvaluationReport, output_path: Path) -> None:
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
                "action_accuracy_avg": report.action_accuracy_avg,
                "temporal_iou_avg": report.temporal_iou_avg,
                "precision_avg": report.precision_avg,
                "recall_avg": report.recall_avg,
                "f1_score_avg": report.f1_score_avg,
                "inference_time_avg_ms": report.inference_time_avg_ms,
            },
            "results_by_category": report.results_by_category,
            "individual_results": [
                {
                    "sample_id": r.sample_id,
                    "action_accuracy": r.action_accuracy,
                    "temporal_iou": r.temporal_iou,
                    "precision": r.precision,
                    "recall": r.recall,
                    "f1_score": r.f1_score,
                    "inference_time_ms": r.inference_time_ms,
                    "avg_confidence": r.avg_confidence,
                }
                for r in report.individual_results
            ],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Evaluation report saved to {output_path}")


def load_evaluation_dataset(dataset_path: Path) -> list[BehaviorEvaluationSample]:
    """
    从 JSON 文件加载评估数据集

    数据集格式:
    {
        "samples": [
            {
                "sample_id": "sample_001",
                "video_path": "videos/sample_001.mp4",
                "ground_truth_actions": [
                    {"action": "walking", "start_frame": 0, "end_frame": 30},
                    {"action": "running", "start_frame": 31, "end_frame": 60}
                ],
                "fps": 30.0,
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

    samples: list[BehaviorEvaluationSample] = []
    base_dir = dataset_path.parent

    for item in data.get("samples", []):
        video_path = base_dir / item["video_path"]
        if not video_path.exists():
            logger.warning(f"Video not found: {video_path}")
            continue

        samples.append(
            BehaviorEvaluationSample(
                sample_id=item["sample_id"],
                video_path=video_path,
                ground_truth_actions=item["ground_truth_actions"],
                fps=item.get("fps", 30.0),
                category=item.get("category", "general"),
                metadata=item.get("metadata", {}),
            )
        )

    logger.info(f"Loaded {len(samples)} evaluation samples from {dataset_path}")
    return samples


__all__ = [
    "BehaviorEvaluator",
    "BehaviorEvaluationSample",
    "BehaviorEvaluationResult",
    "BehaviorEvaluationReport",
    "load_evaluation_dataset",
]
