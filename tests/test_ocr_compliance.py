from __future__ import annotations

from scenara.domains.ocr.compliance import OcrComplianceChecker
from scenara.platform.models import OcrTextBlock, Point


def test_compliance_checker_clean_text() -> None:
    checker = OcrComplianceChecker()
    report = checker.inspect("欢迎来到景枢视觉AI中枢平台，提供多模态智能解析。")
    assert report.status == "pass"
    assert report.risk_score == 0.0
    assert report.total_hits == 0
    assert len(report.hits) == 0


def test_compliance_checker_extreme_words() -> None:
    checker = OcrComplianceChecker()
    text = "我们是行业第一的视觉产品，拥有国家级实验室和顶级算法。"
    report = checker.inspect(text)
    assert report.status == "block"
    assert report.total_hits >= 3
    words = [h.word for h in report.hits]
    assert "第一" in words or "行业第一" in words
    assert "国家级" in words
    assert "顶级" in words


def test_compliance_checker_financial_and_medical_guarantee() -> None:
    checker = OcrComplianceChecker()
    text = "投资本理财产品100%保本，零风险稳赚不赔！特供秘方，包治百病，当天见效。"
    report = checker.inspect(text)
    assert report.status == "block"
    words = [h.word for h in report.hits]
    assert "100%保本" in words
    assert "零风险" in words
    assert "稳赚不赔" in words
    assert "特供" in words
    assert "包治百病" in words


def test_compliance_checker_suspect_words_and_blocks() -> None:
    checker = OcrComplianceChecker()
    block1 = OcrTextBlock(
        block_id="b1",
        text="本技术行业遥遥领先",
        polygon=[Point(x=0, y=0), Point(x=10, y=10)],
    )
    block2 = OcrTextBlock(
        block_id="b2",
        text="支持全场景自适应",
        polygon=[Point(x=0, y=10), Point(x=10, y=20)],
    )
    text = f"{block1.text}\n{block2.text}"
    report = checker.inspect(text, blocks=[block1, block2])
    assert report.status == "suspect"
    assert report.total_hits >= 1
    assert any("领先" in h.word for h in report.hits)
    hit = next(h for h in report.hits if "领先" in h.word)
    assert hit.block_id == "b1"
    assert "《广告法》" in hit.legal_reference
