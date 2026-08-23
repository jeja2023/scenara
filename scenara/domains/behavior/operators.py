"""
行为识别算子和引擎协议

提供视频/流场景下的人体动作识别、活动检测和异常行为分析能力。
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any, Protocol

from scenara.platform.media_batch import DecodedMedia
from scenara.platform.models import (
    BehaviorAction,
    BehaviorDomainPayload,
    MediaKind,
    MediaUnitResult,
    ModelProvenance,
    PipelineRef,
    ProvenanceEvidence,
    ResultEnvelope,
    TemporalSegment,
)
from scenara.platform.pipeline import DomainUnavailable, ExecutionContext, OperatorDefinition


class BehaviorEngine(Protocol):
    """行为识别引擎协议"""

    model_id: str
    production_ready: bool
    version: str
    action_classes: list[str]  # 支持的行为类别列表

    def predict(
        self,
        frames: list[Any],  # 时序帧序列
        *,
        temporal_window_ms: int = 1000,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]: ...

    def predict_anomaly(
        self,
        frames: list[Any],
    ) -> list[dict[str, Any]]: ...


class DevelopmentBehaviorEngine:
    """开发环境行为识别适配器,返回模拟结果"""

    model_id = "behavior-dev"
    production_ready = False
    version = "0.1.0"
    action_classes = ["walking", "standing", "sitting", "running", "falling"]

    def predict(
        self,
        frames: list[Any],
        *,
        temporal_window_ms: int = 1000,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]:
        """返回模拟的行为识别结果"""
        if not frames:
            return []

        # 模拟:每个时间窗口返回一个行为
        import random

        results = []
        for i in range(0, len(frames), max(1, len(frames) // 3)):
            action_type = random.choice(self.action_classes)
            confidence = random.uniform(min_confidence, 1.0)

            if confidence >= min_confidence:
                results.append({
                    "action_type": action_type,
                    "action_label": action_type.capitalize(),
                    "confidence": confidence,
                    "start_frame": i,
                    "end_frame": min(i + len(frames) // 3, len(frames) - 1),
                })

        return results

    def predict_anomaly(
        self,
        frames: list[Any],
    ) -> list[dict[str, Any]]:
        """返回模拟的异常检测结果"""
        # 模拟:随机检测一些异常片段
        import random

        if random.random() < 0.3:  # 30% 概率检测到异常
            return [{
                "segment_type": "anomaly",
                "confidence": random.uniform(0.6, 0.95),
                "start_frame": random.randint(0, len(frames) // 2),
                "end_frame": random.randint(len(frames) // 2, len(frames) - 1),
                "description": "检测到异常行为",
            }]
        return []


class BehaviorRecognitionOperator:
    """行为识别算子"""

    definition = OperatorDefinition(
        operator_id="behavior.action-recognition",
        version="1.0.0",
        domain="behavior",
        input_types={"batch": "media/batch"},
        resource_budget={"vram_mb": 6144, "cpu_cores": 4},  # 行为识别需要更多资源
        max_batch_size=64,
        output_types={"result": "result/behavior"},
        timeout_seconds=3600,  # 1小时,视频可能很长
        resource_class="gpu",
        batchable=True,
    )

    def __init__(self, engine: BehaviorEngine | None = None) -> None:
        self._engine = engine

    async def execute(
        self,
        context: ExecutionContext,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        decoded = inputs["batch"]
        if not isinstance(decoded, DecodedMedia):
            raise TypeError("Behavior recognition requires a decoded media batch")

        # 只支持视频和流
        if decoded.kind not in {MediaKind.VIDEO, MediaKind.STREAM}:
            raise DomainUnavailable("Behavior recognition only supports video and stream media")

        # 初始化引擎
        if self._engine is None:
            loaded_engine = await asyncio.to_thread(lambda: DevelopmentBehaviorEngine())
            self._engine = loaded_engine

        engine = self._engine
        assert engine is not None

        # 提取参数
        temporal_window_ms = int(parameters.get("temporal_window_ms", 1000))
        min_confidence = float(parameters.get("min_confidence", 0.5))
        enable_anomaly_detection = bool(parameters.get("enable_anomaly_detection", False))

        # 检查生产就绪状态
        production_ready = bool(getattr(engine, "production_ready", False))
        if context.production and not production_ready:
            raise DomainUnavailable("Behavior engine is not approved for production")

        substitutes: list[str] = []
        if not production_ready:
            substitutes.append("behavior_engine")

        models = [
            ModelProvenance(
                capability="action_recognition",
                model_id=engine.model_id,
                version=engine.version,
                production_ready=production_ready,
            )
        ]

        # 收集结果
        actions: list[BehaviorAction] = []
        segments: list[TemporalSegment] = []
        units: list[MediaUnitResult] = []
        processed_units = 0

        # 时序窗口缓冲
        temporal_buffer: list[tuple[Any, int, int]] = []  # (image, pts_ms, index)
        action_counter = 0
        segment_counter = 0

        def build_result(*, final: bool = False) -> ResultEnvelope:
            warnings = [f"development_substitute:{item}" for item in substitutes]
            if final and decoded.termination_reason:
                warnings.append(f"media_termination:{decoded.termination_reason}")

            # 生成摘要
            action_counts = defaultdict(int)
            for action in actions:
                action_counts[action.action_type] += 1

            summary_parts = []
            for action_type, count in sorted(action_counts.items(), key=lambda x: -x[1]):
                summary_parts.append(f"{action_type}({count})")
            summary = "识别到的行为: " + ", ".join(summary_parts) if summary_parts else "未识别到明显行为"

            return ResultEnvelope(
                run_id=context.run_id,
                domain="behavior",
                pipeline=PipelineRef(pipeline_id=context.pipeline_id, version=context.pipeline_version),
                asset_id=context.asset_id,
                source_id=context.source_id,
                units=list(units),
                domain_payload=BehaviorDomainPayload(
                    actions=list(actions),
                    segments=list(segments),
                    summary=summary,
                ),
                models=models,
                media_metadata=decoded.metadata.model_copy(update={"sampled_units": processed_units}),
                warnings=warnings,
                provenance=ProvenanceEvidence(development_substitutes=substitutes),
                created_at=time.time(),
            )

        try:
            async for chunk, expected_units in decoded.iter_batches(4):
                for unit in chunk:
                    # 添加到时序缓冲
                    temporal_buffer.append((unit.image, unit.pts_ms or 0, unit.index))

                    # 当缓冲区达到窗口大小时,进行推理
                    if len(temporal_buffer) >= 8:  # 至少 8 帧作为一个窗口
                        frames = [item[0] for item in temporal_buffer]
                        start_pts = temporal_buffer[0][1]
                        end_pts = temporal_buffer[-1][1]

                        # 执行行为识别
                        predictions = await asyncio.to_thread(
                            engine.predict,
                            frames,
                            temporal_window_ms=temporal_window_ms,
                            min_confidence=min_confidence,
                        )

                        for pred in predictions:
                            action_counter += 1
                            # 计算实际时间
                            start_frame = pred.get("start_frame", 0)
                            end_frame = pred.get("end_frame", len(temporal_buffer) - 1)

                            actual_start_ms = temporal_buffer[start_frame][1]
                            actual_end_ms = temporal_buffer[min(end_frame, len(temporal_buffer) - 1)][1]

                            actions.append(
                                BehaviorAction(
                                    action_id=f"action_{action_counter}",
                                    action_type=pred["action_type"],
                                    action_label=pred.get("action_label", pred["action_type"]),
                                    confidence=pred["confidence"],
                                    start_ms=actual_start_ms,
                                    end_ms=actual_end_ms,
                                )
                            )

                        # 异常检测
                        if enable_anomaly_detection:
                            anomalies = await asyncio.to_thread(engine.predict_anomaly, frames)
                            for anomaly in anomalies:
                                segment_counter += 1
                                start_frame = anomaly.get("start_frame", 0)
                                end_frame = anomaly.get("end_frame", len(temporal_buffer) - 1)

                                actual_start_ms = temporal_buffer[start_frame][1]
                                actual_end_ms = temporal_buffer[min(end_frame, len(temporal_buffer) - 1)][1]

                                segments.append(
                                    TemporalSegment(
                                        segment_id=f"segment_{segment_counter}",
                                        start_ms=actual_start_ms,
                                        end_ms=actual_end_ms,
                                        segment_type=anomaly["segment_type"],
                                        confidence=anomaly.get("confidence"),
                                        description=anomaly.get("description", ""),
                                    )
                                )

                        # 滑动窗口:保留后半部分
                        temporal_buffer = temporal_buffer[len(temporal_buffer) // 2:]

                    # 记录处理单元
                    units.append(
                        MediaUnitResult(
                            unit_id=unit.unit_id,
                            unit_type=unit.unit_type,
                            index=unit.index,
                            pts_ms=unit.pts_ms,
                            page_number=unit.page_number,
                            width=unit.width,
                            height=unit.height,
                        )
                    )

                processed_units += len(chunk)
                progress = (
                    None
                    if expected_units is None
                    else 0.03 + 0.94 * min(1.0, processed_units / max(1, expected_units))
                )

                # 流式发布部分结果
                if decoded.kind == MediaKind.STREAM:
                    await context.publish_partial_result(build_result())

                await context.report_progress(
                    progress,
                    stage="behavior",
                    processed_units=processed_units,
                    expected_units=expected_units,
                    latest_pts_ms=chunk[-1].pts_ms if chunk else None,
                )

            # 处理剩余的缓冲区
            if temporal_buffer:
                frames = [item[0] for item in temporal_buffer]
                predictions = await asyncio.to_thread(
                    engine.predict,
                    frames,
                    temporal_window_ms=temporal_window_ms,
                    min_confidence=min_confidence,
                )

                for pred in predictions:
                    action_counter += 1
                    start_frame = pred.get("start_frame", 0)
                    end_frame = pred.get("end_frame", len(temporal_buffer) - 1)

                    actual_start_ms = temporal_buffer[start_frame][1]
                    actual_end_ms = temporal_buffer[min(end_frame, len(temporal_buffer) - 1)][1]

                    actions.append(
                        BehaviorAction(
                            action_id=f"action_{action_counter}",
                            action_type=pred["action_type"],
                            action_label=pred.get("action_label", pred["action_type"]),
                            confidence=pred["confidence"],
                            start_ms=actual_start_ms,
                            end_ms=actual_end_ms,
                        )
                    )

        except BaseException:
            await decoded.close()
            raise

        return {"result": build_result(final=True)}


__all__ = [
    "BehaviorEngine",
    "DevelopmentBehaviorEngine",
    "BehaviorRecognitionOperator",
]
