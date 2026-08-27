from __future__ import annotations

import asyncio
import html
import inspect
import time
from typing import Any, Literal, Protocol, cast

from scenara.domains.ocr.compliance import OcrComplianceChecker, OcrComplianceHit
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
from scenara.platform.artifacts import store_object_crop, store_unit_frame
from scenara.platform.media import parse_roi
from scenara.platform.pipeline import (
    DomainUnavailable,
    ExecutionContext,
    OperatorDefinition,
)


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
        x1 = max(5.0, min(50.0, width * 0.1))
        y1 = max(5.0, min(50.0, height * 0.1))
        x2 = max(x1 + 10.0, width - x1)
        y2 = max(y1 + 10.0, min(y1 + 50.0, height - y1))
        return [
            {
                "text": "Scenara 景枢 OCR 演示文本（本地未安装 paddleocr，处于开发回退模式）",
                "score": 0.98,
                "polygon": [
                    [x1, y1],
                    [x2, y1],
                    [x2, y2],
                    [x1, y2],
                ],
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
    production_capabilities = frozenset(
        [
            "text_detection",
            "text_recognition",
            "multi_language",
        ]
    )

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
                str(region.get("block_type"))
                if str(region.get("block_type")) in OCR_BLOCK_TYPES
                else "text"
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
                (index, region)
                for index, region in enumerate(normalized_regions)
                if _contains(region, normalized)
            ]
            if candidates:
                index, region = min(
                    candidates,
                    key=lambda pair: (
                        (_bounds(pair[1])[2] - _bounds(pair[1])[0])
                        * (_bounds(pair[1])[3] - _bounds(pair[1])[1])
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


_parse_roi = parse_roi


def _generate_html_layout(
    width: int,
    height: int,
    objects_or_blocks: list[Any],
    hits: list[Any] | None = None,
) -> str:
    """生成 1:1 自适应百分比绝对定位的 HTML 仿真排版页面，支持违规高亮与悬停提示"""
    if width <= 0 or height <= 0 or not objects_or_blocks:
        return ""

    hit_map: dict[str, list[Any]] = {}
    if hits:
        for h in hits:
            bid = getattr(h, "block_id", None)
            if bid:
                hit_map.setdefault(bid, []).append(h)

    block_elements: list[str] = []
    for item in objects_or_blocks:
        text = ""
        bid = ""
        btype = "text"
        bx, by, bw, bh = 0.0, 0.0, 0.0, 0.0

        if isinstance(item, VisionObject):
            bid = item.object_id
            btype = item.object_type or "text"
            text = str(item.attributes.get("text", "") or "")
            if item.bbox is not None:
                bx, by, bw, bh = (
                    item.bbox.x,
                    item.bbox.y,
                    item.bbox.width,
                    item.bbox.height,
                )
        elif isinstance(item, OcrTextBlock):
            bid = item.block_id
            btype = item.block_type or "text"
            text = item.text or ""
            if item.polygon:
                xs = [p.x for p in item.polygon]
                ys = [p.y for p in item.polygon]
                bx, by, bw, bh = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        elif isinstance(item, dict):
            bid = str(item.get("block_id", ""))
            btype = str(item.get("block_type", "text"))
            text = str(item.get("text", "") or "")
            b = _bounds(item)
            if b[0] != float("inf"):
                bx, by, bw, bh = b[0], b[1], b[2] - b[0], b[3] - b[1]

        if not text.strip() or bw <= 0 or bh <= 0:
            continue

        left_pct = round((bx / width) * 100, 3)
        top_pct = round((by / height) * 100, 3)
        width_pct = round((bw / width) * 100, 3)
        height_pct = round((bh / height) * 100, 3)

        font_size_px = max(11, min(48, int(bh * 0.72)))
        font_weight = "bold" if btype == "title" else "normal"
        line_height = max(1.1, round(bh / max(1, font_size_px), 2))

        display_text = html.escape(text)
        block_hits = hit_map.get(bid, [])
        if block_hits:
            for h in block_hits:
                h_word = html.escape(getattr(h, "word", ""))
                h_sev = getattr(h, "severity", "suspect")
                h_cat = html.escape(getattr(h, "rule_category", ""))
                h_ref = html.escape(getattr(h, "legal_reference", ""))
                h_sug = html.escape(getattr(h, "suggestion", ""))
                mark_tag = (
                    f'<mark class="ocr-compliance-mark ocr-compliance-{h_sev}" '
                    f'title="{h_cat}: {h_ref} &#10;建议: {h_sug}">{h_word}</mark>'
                )
                display_text = display_text.replace(h_word, mark_tag)

        elem = (
            f'<div class="ocr-visual-block ocr-type-{btype}" '
            f'data-block-id="{bid}" '
            f'style="position: absolute; left: {left_pct}%; top: {top_pct}%; '
            f"width: {width_pct}%; height: {height_pct}%; "
            f"display: flex; align-items: center; justify-content: flex-start; "
            f"font-size: clamp(10px, {font_size_px}px, 52px); font-weight: {font_weight}; "
            f'line-height: {line_height}; overflow: hidden; word-break: break-word;">'
            f'<span class="ocr-block-inner">{display_text}</span>'
            f"</div>"
        )
        block_elements.append(elem)

    content_html = "\n    ".join(block_elements)
    styles = (
        "<style>\n"
        ".ocr-visual-container { position: relative; width: 100%; aspect-ratio: "
        f"{width} / {height}; "
        "background-color: #ffffff; color: #1e293b; box-shadow: 0 4px 20px rgba(0,0,0,0.06); "
        "border-radius: 6px; overflow: hidden; user-select: text; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }\n"
        ".ocr-visual-block { box-sizing: border-box; transition: background 0.15s ease; }\n"
        ".ocr-visual-block:hover { background-color: rgba(59, 130, 246, 0.08); outline: 1px dashed rgba(59, 130, 246, 0.4); }\n"
        ".ocr-type-title { color: #0f172a; }\n"
        ".ocr-compliance-mark { border-radius: 2px; padding: 0 2px; cursor: help; }\n"
        ".ocr-compliance-mark.ocr-compliance-block { background-color: rgba(239, 68, 68, 0.25); color: #dc2626; border-bottom: 2px wavy #dc2626; font-weight: bold; }\n"
        ".ocr-compliance-mark.ocr-compliance-suspect { background-color: rgba(245, 158, 11, 0.25); color: #d97706; border-bottom: 2px wavy #d97706; }\n"
        "</style>"
    )
    return (
        f"{styles}\n"
        f'<div class="ocr-visual-container" data-width="{width}" data-height="{height}">\n'
        f"    {content_html}\n"
        f"</div>"
    )


def _predict_blocks(
    engine: OcrEngine,
    image: Any,
    *,
    min_score: float,
    language_hint: str | None,
) -> list[dict[str, Any]]:
    """Call both the 1.0 bare-image adapter and the extended OCR adapter safely."""
    parameters = inspect.signature(engine.predict).parameters.values()
    accepts_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters
    )
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
        raw_roi = parameters.get("roi")
        enable_compliance = bool(parameters.get("enable_compliance", True))
        custom_sensitive_words = parameters.get("custom_sensitive_words")
        compliance_whitelist = parameters.get("compliance_whitelist")
        custom_sensitive_severity = str(
            parameters.get("custom_sensitive_severity", "block")
        )
        deduplicate_slides = bool(parameters.get("deduplicate_slides", True))
        layout_reconstruction = bool(parameters.get("layout_reconstruction", True))

        # 检查生产就绪状态
        production_ready = bool(getattr(engine, "production_ready", False))
        layout_predictor = getattr(engine, "predict_layout", None)
        layout_capabilities = frozenset(getattr(engine, "production_capabilities", ()))
        layout_ready = (
            callable(layout_predictor) and "layout_analysis" in layout_capabilities
        )

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
        slides_catalog: list[dict[str, Any]] = []
        prev_unit_pts_ms: int | None = None
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
                dominant_language = max(
                    detected_languages,
                    key=lambda language: detected_languages[language],
                )

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
            elif (
                deduplicate_text
                and any(u.page_number for u in units)
                and len(units) > 1
                and tracked_texts
            ):
                formatted_lines = []
                for track in tracked_texts:
                    txt = track["text"].strip()
                    if not txt:
                        continue
                    if track["first_page"] != track["last_page"]:
                        formatted_lines.append(
                            f"[第 {track['first_page']}-{track['last_page']} 页] {txt}"
                        )
                    elif track["first_page"] is not None:
                        formatted_lines.append(f"[第 {track['first_page']} 页] {txt}")
                    else:
                        formatted_lines.append(txt)
                aggregate_text = "\n".join(formatted_lines)
            else:
                aggregate_text = "\n".join(block.text for block in blocks if block.text)

            # 文本合规性审核
            compliance_report_dict: dict[str, Any] | None = None
            hits_list: list[OcrComplianceHit] = []
            if enable_compliance and aggregate_text.strip():
                checker = OcrComplianceChecker()
                rep = checker.inspect(
                    aggregate_text,
                    blocks=blocks,
                    custom_words=custom_sensitive_words,
                    whitelist=compliance_whitelist,
                    custom_severity=custom_sensitive_severity,
                )
                compliance_report_dict = rep.model_dump()
                hits_list = rep.hits
                # 同步为各 Slide 也计算合规报告
                for s in slides_catalog:
                    s_rep = checker.inspect(
                        s.get("text", ""),
                        custom_words=custom_sensitive_words,
                        whitelist=compliance_whitelist,
                        custom_severity=custom_sensitive_severity,
                    )
                    s["compliance"] = s_rep.model_dump()

            # HTML 仿真排版生成
            html_layout_str: str | None = None
            if layout_reconstruction and units:
                first_u = units[0]
                html_layout_str = _generate_html_layout(
                    first_u.width,
                    first_u.height,
                    first_u.objects,
                    hits=hits_list,
                )

            return ResultEnvelope(
                run_id=context.run_id,
                domain="ocr",
                pipeline=PipelineRef(
                    pipeline_id=context.pipeline_id, version=context.pipeline_version
                ),
                asset_id=context.asset_id,
                source_id=context.source_id,
                units=list(units),
                domain_payload=OcrDomainPayload(
                    text=aggregate_text,
                    blocks=list(blocks),
                    language=dominant_language,
                    compliance_report=compliance_report_dict,
                    slides=list(slides_catalog),
                    html_layout=html_layout_str,
                ),
                models=models,
                media_metadata=decoded.metadata.model_copy(
                    update={"sampled_units": processed_units}
                ),
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
                    # ROI 区域检测与局部裁剪
                    crop_box = _parse_roi(raw_roi, unit.width, unit.height)
                    if crop_box is not None:
                        cx1, cy1, cx2, cy2 = crop_box
                        pred_image = unit.image.crop((cx1, cy1, cx2, cy2))
                    else:
                        cx1, cy1 = 0, 0
                        pred_image = unit.image

                    # 动静态画面检测：若画面无显著动态变化，直接复用上一帧识别结果，极速跳过深度推理
                    is_static_frame = False
                    curr_thumb = None
                    if motion_filter_enabled and is_time_series:
                        curr_thumb = _get_gray_thumb(pred_image)
                        if prev_thumb is not None and cached_raw_blocks:
                            diff = (
                                float(np.mean(np.abs(curr_thumb - prev_thumb))) / 255.0
                            )
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
                            pred_image,
                            min_score=min_score,
                            language_hint=language_hint,
                        )

                        # 执行版面分析(如果需要且支持)
                        regions = []
                        if layout_required and callable(layout_predictor):
                            predicted = await asyncio.to_thread(
                                layout_predictor, pred_image
                            )
                            if not isinstance(predicted, list):
                                raise TypeError("OCR layout engine must return a list")
                            regions = [
                                item for item in predicted if isinstance(item, dict)
                            ]

                        # 若进行了 ROI 局部裁剪，将 polygon 坐标无损逆映射回原图全画幅坐标系
                        if crop_box is not None and (cx1 > 0 or cy1 > 0):
                            offset_blocks = []
                            for b in raw_blocks:
                                poly = b.get("polygon")
                                if isinstance(poly, (list, tuple)):
                                    offset_blocks.append(
                                        {
                                            **b,
                                            "polygon": [
                                                [float(p[0]) + cx1, float(p[1]) + cy1]
                                                for p in poly
                                                if len(p) >= 2
                                            ],
                                        }
                                    )
                                else:
                                    offset_blocks.append(b)
                            raw_blocks = offset_blocks

                            offset_regions = []
                            for r in regions:
                                poly = r.get("polygon")
                                if isinstance(poly, (list, tuple)):
                                    offset_regions.append(
                                        {
                                            **r,
                                            "polygon": [
                                                [float(p[0]) + cx1, float(p[1]) + cy1]
                                                for p in poly
                                                if len(p) >= 2
                                            ],
                                        }
                                    )
                                else:
                                    offset_regions.append(r)
                            regions = offset_regions

                        cached_raw_blocks = raw_blocks
                        cached_regions = regions
                        if (
                            motion_filter_enabled
                            and is_time_series
                            and curr_thumb is not None
                        ):
                            prev_thumb = curr_thumb

                    # 合并版面信息
                    ordered_blocks = _merge_layout(raw_blocks, regions)
                    if crop_box is not None:
                        cx1, cy1, cx2, cy2 = crop_box
                        filtered_blocks = []
                        for b in ordered_blocks:
                            b_left, b_top, b_right, b_bottom = _bounds(b)
                            if b_left != float("inf"):
                                bcx = (b_left + b_right) / 2.0
                                bcy = (b_top + b_bottom) / 2.0
                                if not (cx1 <= bcx <= cx2 and cy1 <= bcy <= cy2):
                                    continue
                            filtered_blocks.append(b)
                        ordered_blocks = filtered_blocks

                    unit_objects: list[VisionObject] = []

                    # 构建结果块
                    for block_index, item in enumerate(ordered_blocks):
                        points = [
                            Point(x=point[0], y=point[1])
                            for point in _polygon(item.get("polygon"))
                        ]
                        block_type = str(item.get("block_type", "text"))
                        if block_type not in OCR_BLOCK_TYPES:
                            block_type = "text"

                        text = str(item.get("text", ""))
                        score = item.get("score")

                        # 统计语言
                        lang = item.get("language")
                        if lang:
                            detected_languages[lang] = detected_languages.get(
                                lang, 0
                            ) + len(text)

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
                                Literal["text", "title", "paragraph", "image", "table"],
                                block_type,
                            ),
                            reading_order=reading_order,
                        )

                        # 添加页码信息(通过扩展字段)
                        if unit.page_number is not None:
                            ocr_block.__dict__["page_number"] = unit.page_number

                        # 添加表格结构信息(如果有)
                        if block_type == "table" and "table_structure" in item:
                            ocr_block.__dict__["table_structure"] = item[
                                "table_structure"
                            ]

                        blocks.append(ocr_block)

                        # 时序文本去重匹配
                        if deduplicate_text and text.strip():
                            matched_track = None
                            for track in reversed(tracked_texts):
                                if track["text"] == text:
                                    if (
                                        track["last_pts_ms"] is not None
                                        and unit.pts_ms is not None
                                        and unit.pts_ms - track["last_pts_ms"] <= 4000
                                    ) or (
                                        track["last_page"] is not None
                                        and unit.page_number is not None
                                        and unit.page_number == track["last_page"] + 1
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
                        crop_artifact_id = await store_object_crop(
                            getattr(context, "artifacts", None),
                            unit.image,
                            bbox=bbox,
                            polygon=points,
                        )
                        vision_obj = VisionObject(
                            object_id=block_id,
                            object_type=block_type,
                            score=score,
                            bbox=bbox,
                            polygon=points,
                            attributes={"text": text, "reading_order": reading_order},
                            crop_artifact_id=crop_artifact_id,
                        )
                        unit_objects.append(vision_obj)
                        reading_order += 1

                    frame_artifact_id = (
                        await store_unit_frame(
                            getattr(context, "artifacts", None), unit.image
                        )
                        if unit_objects
                        or decoded.kind not in {MediaKind.VIDEO, MediaKind.STREAM}
                        else None
                    )
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
                            frame_artifact_id=frame_artifact_id,
                        )
                    )

                    # 轮播海报聚类与生命周期追踪
                    unit_text = "\n".join(
                        str(o.attributes.get("text", "")).strip()
                        for o in unit_objects
                        if o.attributes.get("text")
                    )
                    if deduplicate_slides and unit_text.strip():
                        matched_slide = None
                        for s in reversed(slides_catalog):
                            if s["text"].strip() == unit_text.strip():
                                matched_slide = s
                                break
                        if matched_slide is not None:
                            matched_slide["last_pts_ms"] = unit.pts_ms
                            matched_slide["last_page"] = unit.page_number
                            matched_slide["display_count"] += 1
                            if (
                                prev_unit_pts_ms is not None
                                and unit.pts_ms is not None
                                and unit.pts_ms > prev_unit_pts_ms
                            ):
                                delta_s = (unit.pts_ms - prev_unit_pts_ms) / 1000.0
                                matched_slide["duration_seconds"] = round(
                                    matched_slide["duration_seconds"] + delta_s, 2
                                )
                        else:
                            slide_html = (
                                _generate_html_layout(
                                    unit.width, unit.height, unit_objects
                                )
                                if layout_reconstruction
                                else ""
                            )
                            slides_catalog.append(
                                {
                                    "slide_id": f"slide_{len(slides_catalog) + 1}",
                                    "first_pts_ms": unit.pts_ms,
                                    "last_pts_ms": unit.pts_ms,
                                    "first_page": unit.page_number,
                                    "last_page": unit.page_number,
                                    "display_count": 1,
                                    "duration_seconds": 0.0,
                                    "text": unit_text,
                                    "frame_artifact_id": frame_artifact_id,
                                    "html_layout": slide_html,
                                    "object_count": len(unit_objects),
                                }
                            )
                    prev_unit_pts_ms = unit.pts_ms
                processed_units += len(chunk)
                progress = (
                    None
                    if expected_units is None
                    else 0.03
                    + 0.94 * min(1.0, processed_units / max(1, expected_units))
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
