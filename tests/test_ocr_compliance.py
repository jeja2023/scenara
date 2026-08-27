from __future__ import annotations

import json
from pathlib import Path
from scenara.domains.ocr.compliance import (
    OcrComplianceChecker,
    parse_words_input,
)
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


def test_compliance_parse_words_input() -> None:
    raw = "内部绝密, 商业机密; 竞品A \n 竞品B | 内部绝密, ， ；"
    parsed = parse_words_input(raw)
    assert parsed == ["内部绝密", "商业机密", "竞品A", "竞品B"]

    list_input = ["词1", "词2, 词3", ["词4", "词1"]]
    assert parse_words_input(list_input) == ["词1", "词2", "词3", "词4"]


def test_compliance_whitelist_exemption() -> None:
    checker = OcrComplianceChecker()
    # "第一人民医院" 含有 "第一"，但配置了白名单后应被豁免放行
    text = "欢迎前往北京市第一人民医院门诊部就诊。"
    report = checker.inspect(text, whitelist=["第一人民医院"])
    assert report.status == "pass"
    assert report.total_hits == 0

    # 当同一个文本既有白名单机构，又有真实违规极限词时，白名单精准豁免，违规词正常捕获
    text2 = "北京市第一人民医院是一家综合医院，其心内科号称全网第一。"
    report2 = checker.inspect(text2, whitelist=["第一人民医院"])
    assert report2.status == "block"
    assert report2.total_hits >= 1
    hit_words = [h.word for h in report2.hits]
    assert any("第一" in w for w in hit_words)
    # 确保命中起始位置不是在 "第一人民医院" 内部
    for hit in report2.hits:
        assert hit.start >= text2.find("全网第一") or hit.word in {"全网第一", "第一"}


def test_compliance_dynamic_task_sensitive_words() -> None:
    checker = OcrComplianceChecker()
    text = "本次方案包含了绝密代码项目与未公开商业策略。"
    report = checker.inspect(
        text,
        custom_words="绝密代码, 未公开商业策略",
        custom_severity="block",
    )
    assert report.status == "block"
    assert report.total_hits == 2
    for hit in report.hits:
        assert hit.rule_id == "custom_task_sensitive_words"
        assert hit.rule_category == "自定义敏感词"
        assert hit.severity == "block"


def test_compliance_persistent_custom_rules_and_hot_reload(tmp_path: Path) -> None:
    dict_file = tmp_path / "custom_dict.json"
    data = {
        "whitelist": ["国家级非物质文化遗产"],
        "rules": [
            {
                "rule_id": "custom_rule_confidential",
                "rule_category": "企业机密防范",
                "severity": "block",
                "keywords": ["内部核心机密"],
                "legal_reference": "企业信息安全制度",
                "suggestion": "请立即撤回内部机密内容",
            }
        ],
    }
    dict_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    checker = OcrComplianceChecker(dict_path=dict_file)

    # 1. 验证持久化自定义规则与白名单生效
    text = "此项目为国家级非物质文化遗产保护工程，但文档标注为内部核心机密。"
    report = checker.inspect(text)
    assert report.status == "block"
    # "国家级非物质文化遗产" 被白名单豁免，不会命中 "国家级"
    words = [h.word for h in report.hits]
    assert "国家级" not in words
    assert "内部核心机密" in words
    hit = next(h for h in report.hits if h.word == "内部核心机密")
    assert hit.rule_id == "custom_rule_confidential"
    assert hit.rule_category == "企业机密防范"

    # 2. 验证热重载：更新字典文件增加规则
    data["rules"].append(
        {
            "rule_id": "custom_rule_new",
            "rule_category": "热重载测试分类",
            "severity": "suspect",
            "keywords": ["临时测试词"],
            "legal_reference": "测试依据",
            "suggestion": "测试建议",
        }
    )
    # 修改文件并更新 mtime
    dict_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    text_reload = "这是一段包含临时测试词的更新文本。"
    report_reload = checker.inspect(text_reload)
    assert report_reload.status == "suspect"
    assert any(h.word == "临时测试词" for h in report_reload.hits)
