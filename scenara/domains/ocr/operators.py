from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Literal, Protocol, cast

from scenara.platform.media_batch import DecodedMedia
from scenara.platform.models import (
    BoundingBox,
    MediaKind,
    MediaUnitResult,
    ModelProvenance,
    OcrDomainPayload,
    OcrTextBlock,
    PipelineRef,
    Point,
    ProvenanceEvidence,
    ResultEnvelope,
    VisionObject,
)
from scenara.platform.pipeline import DomainUnavailable, ExecutionContext, OperatorDefinition


class OcrEngine(Protocol):
    model_id: str
    production_ready: bool
    version: str

    def predict(
        self,
        image: Any,
        *,
        min_score: float = 0.0,
        language_hint: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def predict_layout(self, image: Any) -> list[dict[str, Any]]: ...


class DevelopmentOcrEngine:
    """开发环境 OCR 模拟引擎，当未安装 paddleocr 时提供开发回退"""

    model_id = "ocr-dev"
    production_ready = False
    version = "0.1.0"

    def predict(
        self,
        image: Any,
        *,
        min_score: float = 0.0,
        language_hint: str | None = None,
    ) -> list[dict[str, Any]]:
        width, height = 800, 600
        if hasattr(image, "size"):
            width, height = image.size
        elif hasattr(image, "shape"):
            height, width = image.shape[:2]
        return [
            {
                "text": "Scenara 景枢 OCR 演示文本（本地未安装 paddleocr，处于开发回退模式）",
                "score": 0.98,
                "polygon": [[50.0, 50.0], [float(width - 50), 50.0], [float(width - 50), 100.0], [50.0, 100.0]],
                "language": language_hint or "zh",
                "block_type": "text",
            }
        ]

    def predict_layout(self, image: Any) -> list[dict[str, Any]]:
        return []


class PaddleOcrEngine:
    """生产级 PaddleOCR 适配器，加载正式 PP-OCRv4 文本识别模型"""

    model_id = "paddleocr-production"
    production_ready = True
    production_capabilities = frozenset([
        "text_detection",
        "text_recognition",
        "multi_language",
    ])

    def __init__(self) -> None:
        try:
            import paddleocr
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise DomainUnavailable("PaddleOCR is not installed") from exc
        self.version = str(getattr(paddleocr, "__version__", "unknown"))

        from pathlib import Path
        ocr_dir = Path("models/ocr")
        det_dir = ocr_dir / "ch_PP-OCRv4_det_infer"
        rec_dir = ocr_dir / "ch_PP-OCRv4_rec_infer"
        cls_dir = ocr_dir / "ch_ppocr_mobile_v2.0_cls_infer"

        kwargs: dict[str, Any] = {
            "use_angle_cls": True,
            "lang": "ch",
            "show_log": False,
        }
        if det_dir.exists() and rec_dir.exists():
            kwargs["det_model_dir"] = str(det_dir.resolve())
            kwargs["rec_model_dir"] = str(rec_dir.resolve())
            if cls_dir.exists():
                kwargs["cls_model_dir"] = str(cls_dir.resolve())

        self._engine = PaddleOCR(**kwargs)

    def predict(
        self,
        image: Any,
        *,
        min_score: float = 0.0,
        language_hint: str | None = None,
    ) -> list[dict[str, Any]]:
        import numpy as np

        img_array = np.asarray(image)
        result = self._engine.ocr(img_array, cls=True)

        blocks: list[dict[str, Any]] = []
        if not result or not result[0]:
            return blocks

        for line in result[0]:
            if not line or len(line) < 2:
                continue
            box, (text, score) = line[0], line[1]

            # 应用置信度过滤
            if score < min_score:
                continue

            polygon = [[float(p[0]), float(p[1])] for p in box]
            blocks.append(
                {
                    "text": text,
                    "score": float(score),
                    "polygon": polygon,
                    "language": language_hint or "zh",
                }
            )
        return blocks

    def predict_layout(self, image: Any) -> list[dict[str, Any]]:
        """开发版不支持版面分析"""
        return []


OCR_BLOCK_TYPES = {"text", "title", "paragraph", "image", "table"}


def _format_pts(pts_ms: int | None) -> str:
    if pts_ms is None:
        return "00:00.0"
    total_seconds = max(0, pts_ms) / 1000.0
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:04.1f}"


def _get_gray_thumb(image: Any, size: tuple[int, int] = (160, 90)) -> Any:
    import numpy as np

    if hasattr(image, "convert") and hasattr(image, "resize"):
        try:
            small = image.convert("L").resize(size)
            return np.asarray(small, dtype=np.float32)
        except Exception:
            pass
    arr = np.asarray(image)
    if arr.ndim == 3:
        gray = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    else:
        gray = arr
    h, w = gray.shape[:2]
    step_y = max(1, h // size[1])
    step_x = max(1, w // size[0])
    return gray[::step_y, ::step_x][: size[1], : size[0]].astype(np.float32)


def _polygon(value: object) -> list[list[float]]:
    if not isinstance(value, (list, tuple)):
        return []
    points: list[list[float]] = []
    for point in value:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            points.append([float(point[0]), float(point[1])])
    return points


def _bounds(item: dict[str, Any]) -> tuple[float, float, float, float]:
    points = _polygon(item.get("polygon"))
    if not points:
        return (float("inf"), float("inf"), float("inf"), float("inf"))
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _contains(region: dict[str, Any], block: dict[str, Any]) -> bool:
    left, top, right, bottom = _bounds(region)
    block_left, block_top, block_right, block_bottom = _bounds(block)
    if block_left == float("inf"):
        return False
    center_x = (block_left + block_right) / 2
    center_y = (block_top + block_bottom) / 2
    return left <= center_x <= right and top <= center_y <= bottom


def _merge_layout(
    raw_blocks: list[dict[str, Any]],
    regions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_regions = [
        {
            **region,
            "polygon": _polygon(region.get("polygon")),
            "block_type": (
                str(region.get("block_type")) if str(region.get("block_type")) in OCR_BLOCK_TYPES else "text"
            ),
        }
        for region in regions
    ]
    merged: list[dict[str, Any]] = []
    used_regions: set[int] = set()
    for block in raw_blocks:
        normalized = {**block, "polygon": _polygon(block.get("polygon"))}
        explicit_type = str(normalized.get("block_type", ""))
        if explicit_type not in OCR_BLOCK_TYPES:
            candidates = [
                (index, region) for index, region in enumerate(normalized_regions) if _contains(region, normalized)
            ]
            if candidates:
                index, region = min(
                    candidates,
                    key=lambda pair: (
                        (_bounds(pair[1])[2] - _bounds(pair[1])[0]) * (_bounds(pair[1])[3] - _bounds(pair[1])[1])
                    ),
                )
                normalized["block_type"] = region["block_type"]
                used_regions.add(index)
            else:
                normalized["block_type"] = "text"
        merged.append(normalized)
    for index, region in enumerate(normalized_regions):
        if index not in used_regions and region["block_type"] in {"image", "table"}:
            merged.append({**region, "text": "", "score": region.get("score")})
    return sorted(merged, key=lambda item: (_bounds(item)[1], _bounds(item)[0]))


def _predict_blocks(
    engine: OcrEngine,
    image: Any,
    *,
    min_score: float,
    language_hint: str | None,
) -> list[dict[str, Any]]:
    """Call both the 1.0 bare-image adapter and the extended OCR adapter safely."""
    parameters = inspect.signature(engine.predict).parameters.values()
    accepts_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters)
    names = {parameter.name for parameter in parameters}
    options: dict[str, Any] = {}
    if accepts_kwargs or "min_score" in names:
        options["min_score"] = min_score
    if accepts_kwargs or "language_hint" in names:
        options["language_hint"] = language_hint
    return engine.predict(image, **options)


class OcrDocumentOperator:
    definition = OperatorDefinition(
        operator_id="ocr.document-recognition",
        version="1.0.0",
        domain="ocr",
        input_types={"batch": "media/batch"},
        resource_budget={"vram_mb": 4096, "cpu_cores": 2},
        max_batch_size=256,
        output_types={"result": "result/ocr"},
        timeout_seconds=3600,
        resource_class="gpu",
        batchable=True,
    )

    def __init__(self, engine: OcrEngine | None = None) -> None:
        self._engine = engine

    async def execute(
        self,
        context: ExecutionContext,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        decoded = inputs["batch"]
        if not isinstance(decoded, DecodedMedia):
            raise TypeError("OCR requires a decoded media batch")
        if self._engine is None:
            try:
                loaded_engine = await asyncio.to_thread(lambda: PaddleOcrEngine())
            except Exception:
                loaded_engine = DevelopmentOcrEngine()
            self._engine = loaded_engine
        engine = self._engine
        assert engine is not None

        # 提取参数
        min_score = float(parameters.get("min_score", 0.0))
        language_hint = parameters.get("language_hint") or None
        if language_hint:
            language_hint = str(language_hint).strip() or None
        layout_required = bool(parameters.get("layout_required", False))
        motion_filter_enabled = bool(parameters.get("motion_filter_enabled", True))
        motion_threshold = float(parameters.get("motion_threshold", 0.025))
        deduplicate_text = bool(parameters.get("deduplicate_text", True))

        # 检查生产就绪状态
        production_ready = bool(getattr(engine, "production_ready", False))
        layout_predictor = getattr(engine, "predict_layout", None)
        layout_capabilities = frozenset(getattr(engine, "production_capabilities", ()))
        layout_ready = callable(layout_predictor) and "layout_analysis" in layout_capabilities

        if context.production and not production_ready:
            raise DomainUnavailable("OCR engine is not approved for production")
        if context.production and layout_required and not layout_ready:
            raise DomainUnavailable("OCR layout engine is not approved for production")

        substitutes: list[str] = []
        if not production_ready:
            substitutes.append("ocr_engine")
        if layout_required and not layout_ready:
            substitutes.append("ocr_layout")

        models = [
            ModelProvenance(
                capability="ocr_recognition",
                model_id=engine.model_id,
                version=engine.version,
                production_ready=production_ready,
            )
        ]
        if callable(layout_predictor):
            models.append(
                ModelProvenance(
                    capability="ocr_layout",
                    model_id=str(getattr(engine, "layout_model_id", engine.model_id)),
                    version=str(getattr(engine, "layout_version", engine.version)),
                    production_ready=layout_ready,
                )
            )

        blocks: list[OcrTextBlock] = []
        units: list[MediaUnitResult] = []
        tracked_texts: list[dict[str, Any]] = []
        reading_order = 0
        processed_units = 0
        detected_languages: dict[str, int] = {}

        def build_result(*, final: bool = False) -> ResultEnvelope:
            warnings = [f"development_substitute:{item}" for item in substitutes]
            if final and decoded.termination_reason:
                warnings.append(f"media_termination:{decoded.termination_reason}")

            # 确定主要语言
            dominant_language = None
            if detected_languages:
                dominant_language = max(detected_languages, key=lambda language: detected_languages[language])

            # 构建聚合文本展示（针对视频/时序流或多页文档进行去重与时间戳标记）
            is_time_series = decoded.kind in {MediaKind.VIDEO, MediaKind.STREAM}
            if deduplicate_text and is_time_series and tracked_texts:
                formatted_lines: list[str] = []
                for track in tracked_texts:
                    txt = track["text"].strip()
                    if not txt:
                        continue
                    start_t = _format_pts(track["first_pts_ms"])
                    end_t = _format_pts(track["last_pts_ms"])
                    if track["first_pts_ms"] != track["last_pts_ms"]:
                        formatted_lines.append(f"[{start_t} - {end_t}] {txt}")
                    else:
                        formatted_lines.append(f"[{start_t}] {txt}")
                aggregate_text = "\n".join(formatted_lines)
            elif deduplicate_text and any(u.page_number for u in units) and len(units) > 1 and tracked_texts:
                formatted_lines = []
                for track in tracked_texts:
                    txt = track["text"].strip()
                    if not txt:
                        continue
                    if track["first_page"] != track["last_page"]:
                        formatted_lines.append(f"[第 {track['first_page']}-{track['last_page']} 页] {txt}")
                    elif track["first_page"] is not None:
                        formatted_lines.append(f"[第 {track['first_page']} 页] {txt}")
                    else:
                        formatted_lines.append(txt)
                aggregate_text = "\n".join(formatted_lines)
            else:
                aggregate_text = "\n".join(block.text for block in blocks if block.text)

            return ResultEnvelope(
                run_id=context.run_id,
                domain="ocr",
                pipeline=PipelineRef(pipeline_id=context.pipeline_id, version=context.pipeline_version),
                asset_id=context.asset_id,
                source_id=context.source_id,
                units=list(units),
                domain_payload=OcrDomainPayload(
                    text=aggregate_text,
                    blocks=list(blocks),
                    language=dominant_language,
                ),
                models=models,
                media_metadata=decoded.metadata.model_copy(update={"sampled_units": processed_units}),
                warnings=warnings,
                provenance=ProvenanceEvidence(development_substitutes=substitutes),
                created_at=time.time(),
            )

        batch_size = 1 if decoded.kind == MediaKind.STREAM else 4
        prev_thumb: Any = None
        cached_raw_blocks: list[dict[str, Any]] = []
        cached_regions: list[dict[str, Any]] = []
        is_time_series = decoded.kind in {MediaKind.VIDEO, MediaKind.STREAM}

        try:
            import numpy as np

            async for chunk, expected_units in decoded.iter_batches(batch_size):
                for unit in chunk:
                    # 动静态画面检测：若画面无显著动态变化，直接复用上一帧识别结果，极速跳过深度推理
                    is_static_frame = False
                    curr_thumb = None
                    if motion_filter_enabled and is_time_series:
                        curr_thumb = _get_gray_thumb(unit.image)
                        if prev_thumb is not None and cached_raw_blocks:
                            diff = float(np.mean(np.abs(curr_thumb - prev_thumb))) / 255.0
                            if diff < motion_threshold:
                                is_static_frame = True

                    if is_static_frame and cached_raw_blocks:
                        raw_blocks = cached_raw_blocks
                        regions = cached_regions
                    else:
                        # 执行真实 OCR 识别
                        raw_blocks = await asyncio.to_thread(
                            _predict_blocks,
                            engine,
                            unit.image,
                            min_score=min_score,
                            language_hint=language_hint,
                        )

                        # 执行版面分析(如果需要且支持)
                        regions = []
                        if layout_required and callable(layout_predictor):
                            predicted = await asyncio.to_thread(layout_predictor, unit.image)
                            if not isinstance(predicted, list):
                                raise TypeError("OCR layout engine must return a list")
                            regions = [item for item in predicted if isinstance(item, dict)]

                        cached_raw_blocks = raw_blocks
                        cached_regions = regions
                        if motion_filter_enabled and is_time_series and curr_thumb is not None:
                            prev_thumb = curr_thumb

                    # 合并版面信息
                    ordered_blocks = _merge_layout(raw_blocks, regions)
                    unit_objects: list[VisionObject] = []

                    # 构建结果块
                    for block_index, item in enumerate(ordered_blocks):
                        points = [Point(x=point[0], y=point[1]) for point in _polygon(item.get("polygon"))]
                        block_type = str(item.get("block_type", "text"))
                        if block_type not in OCR_BLOCK_TYPES:
                            block_type = "text"

                        text = str(item.get("text", ""))
                        score = item.get("score")

                        # 统计语言
                        lang = item.get("language")
                        if lang:
                            detected_languages[lang] = detected_languages.get(lang, 0) + len(text)

                        # 计算包围盒
                        left, top, right, bottom = _bounds(item)
                        bbox = (
                            BoundingBox(
                                x=left,
                                y=top,
                                width=max(0.0, right - left),
                                height=max(0.0, bottom - top),
                            )
                            if left != float("inf")
                            else None
                        )

                        # 构建 block
                        block_id = f"{unit.unit_id}_block_{block_index}"
                        ocr_block = OcrTextBlock(
                            block_id=block_id,
                            text=text,
                            score=score,
                            polygon=points,
                            block_type=cast(
                                Literal["text", "title", "paragraph", "image", "table"], block_type
                            ),
                            reading_order=reading_order,
                        )

                        # 添加页码信息(通过扩展字段)
                        if unit.page_number is not None:
                            ocr_block.__dict__["page_number"] = unit.page_number

                        # 添加表格结构信息(如果有)
                        if block_type == "table" and "table_structure" in item:
                            ocr_block.__dict__["table_structure"] = item["table_structure"]

                        blocks.append(ocr_block)

                        # 时序文本去重匹配
                        if deduplicate_text and text.strip():
                            matched_track = None
                            for track in reversed(tracked_texts):
                                if track["text"] == text:
                                    if (
                                        (track["last_pts_ms"] is not None and unit.pts_ms is not None and unit.pts_ms - track["last_pts_ms"] <= 4000)
                                        or (track["last_page"] is not None and unit.page_number is not None and unit.page_number == track["last_page"] + 1)
                                    ):
                                        matched_track = track
                                        break
                            if matched_track is not None:
                                matched_track["last_pts_ms"] = unit.pts_ms
                                matched_track["last_page"] = unit.page_number
                                matched_track["occurrences"] += 1
                                if score and score > matched_track["score"]:
                                    matched_track["score"] = score
                            else:
                                tracked_texts.append(
                                    {
                                        "text": text,
                                        "first_pts_ms": unit.pts_ms,
                                        "last_pts_ms": unit.pts_ms,
                                        "first_page": unit.page_number,
                                        "last_page": unit.page_number,
                                        "score": score or 0.0,
                                        "occurrences": 1,
                                    }
                                )

                        # 构建单元内的 VisionObject，供时间轴与对象明细展示
                        vision_obj = VisionObject(
                            object_id=block_id,
                            object_type=block_type,
                            score=score,
                            bbox=bbox,
                            polygon=points,
                            attributes={"text": text, "reading_order": reading_order},
                        )
                        unit_objects.append(vision_obj)
                        reading_order += 1

                    units.append(
                        MediaUnitResult(
                            unit_id=unit.unit_id,
                            unit_type=unit.unit_type,
                            index=unit.index,
                            pts_ms=unit.pts_ms,
                            page_number=unit.page_number,
                            width=unit.width,
                            height=unit.height,
                            objects=unit_objects,
                        )
                    )
                processed_units += len(chunk)
                progress = (
                    None
                    if expected_units is None
                    else 0.03 + 0.94 * min(1.0, processed_units / max(1, expected_units))
                )
                if decoded.kind in {MediaKind.VIDEO, MediaKind.STREAM}:
                    await context.publish_partial_result(build_result())
                await context.report_progress(
                    progress,
                    stage="ocr",
                    processed_units=processed_units,
                    expected_units=expected_units,
                    latest_pts_ms=chunk[-1].pts_ms if chunk else None,
                )
        except BaseException:
            await decoded.close()
            raise
        return {"result": build_result(final=True)}
