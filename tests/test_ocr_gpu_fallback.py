from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import numpy as np
from PIL import Image


def _fake_ocr_module(
    monkeypatch: Any,
    factory: Any,
) -> None:
    module = ModuleType("paddleocr")
    module.__version__ = "test"
    module.PaddleOCR = factory
    monkeypatch.setitem(sys.modules, "paddleocr", module)


def _model_dirs(tmp_path: Any) -> Any:
    root = tmp_path / "ocr"
    (root / "ch_PP-OCRv4_det_infer").mkdir(parents=True)
    (root / "ch_PP-OCRv4_rec_infer").mkdir()
    return root


def test_paddle_ocr_falls_back_when_gpu_initialization_fails(
    monkeypatch: Any, tmp_path: Any
) -> None:
    from scenara.domains.ocr.operators import PaddleOcrEngine

    created: list[bool] = []

    class FakePaddleOCR:
        def __init__(self, *, use_gpu: bool, **kwargs: Any) -> None:
            del kwargs
            created.append(use_gpu)
            if use_gpu:
                raise RuntimeError("GPU is unavailable")

        def ocr(self, image: Any, *, cls: bool) -> list[Any]:
            del image, cls
            return [[([[0, 0], [1, 0], [1, 1], [0, 1]], ("cpu", 0.9))]]

    _fake_ocr_module(monkeypatch, FakePaddleOCR)
    monkeypatch.setenv("SCENARA_OCR_MODEL_DIR", str(_model_dirs(tmp_path)))
    monkeypatch.setenv("SCENARA_OCR_USE_GPU", "true")
    monkeypatch.setenv("SCENARA_OCR_GPU_FALLBACK", "true")

    engine = PaddleOcrEngine()
    blocks = engine.predict(Image.new("RGB", (2, 2)))

    assert created == [True, False]
    assert blocks[0]["text"] == "cpu"


def test_paddle_ocr_falls_back_when_gpu_inference_fails(
    monkeypatch: Any, tmp_path: Any
) -> None:
    from scenara.domains.ocr.operators import PaddleOcrEngine

    created: list[bool] = []

    class FakePaddleOCR:
        def __init__(self, *, use_gpu: bool, **kwargs: Any) -> None:
            del kwargs
            created.append(use_gpu)
            self.use_gpu = use_gpu

        def ocr(self, image: Any, *, cls: bool) -> list[Any]:
            del image, cls
            if self.use_gpu:
                raise RuntimeError("Cannot load cudnn shared library")
            return [[([[0, 0], [1, 0], [1, 1], [0, 1]], ("cpu", 0.9))]]

    _fake_ocr_module(monkeypatch, FakePaddleOCR)
    monkeypatch.setenv("SCENARA_OCR_MODEL_DIR", str(_model_dirs(tmp_path)))
    monkeypatch.setenv("SCENARA_OCR_USE_GPU", "true")
    monkeypatch.setenv("SCENARA_OCR_GPU_FALLBACK", "true")

    engine = PaddleOcrEngine()
    blocks = engine.predict(np.zeros((2, 2, 3), dtype=np.uint8))

    assert created == [True, False]
    assert blocks[0]["text"] == "cpu"
