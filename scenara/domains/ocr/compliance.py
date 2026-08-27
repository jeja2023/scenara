import json
import logging
import os
from pathlib import Path
import re
from typing import Any
from pydantic import BaseModel, Field

logger = logging.getLogger("scenara.compliance")


class OcrComplianceHit(BaseModel):
    """单个合规违规/存疑命中项"""

    rule_id: str = Field(description="规则标识")
    rule_category: str = Field(
        description="规则分类,如: 广告法极限词、虚假承诺、公共安全、违规引流"
    )
    severity: str = Field(
        description="严重等级: block(违规禁止)、suspect(疑似存疑)、info(提示关注)"
    )
    word: str = Field(description="命中的关键词或短语")
    start: int = Field(description="在整段文本中的起始字符位置")
    end: int = Field(description="在整段文本中的结束字符位置")
    block_id: str | None = Field(default=None, description="关联的 OCR 文本块标识")
    legal_reference: str = Field(description="相关法律法规条文或监管规范")
    suggestion: str = Field(description="整改与替换建议")


class OcrComplianceReport(BaseModel):
    """OCR 文本合规性审核评估报告"""

    status: str = Field(
        default="pass",
        description="综合合规判定: pass(合规通过)、suspect(疑似存疑)、block(严重违规)",
    )
    risk_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="综合风险评分(0.0合规 ~ 1.0高危)"
    )
    total_hits: int = Field(default=0, ge=0, description="触发规则命中总数")
    hits: list[OcrComplianceHit] = Field(
        default_factory=list, description="详细命中列表"
    )
    summary: str = Field(
        default="未检测到违规或存疑内容", description="文字审核结论摘要"
    )


class ComplianceRule:
    def __init__(
        self,
        rule_id: str,
        rule_category: str,
        severity: str,
        keywords: list[str],
        legal_reference: str,
        suggestion: str,
        regex_patterns: list[str] | None = None,
    ) -> None:
        self.rule_id = rule_id
        self.rule_category = rule_category
        self.severity = severity
        self.keywords = keywords
        self.legal_reference = legal_reference
        self.suggestion = suggestion
        self.compiled_regex = [
            re.compile(p, re.IGNORECASE) for p in (regex_patterns or [])
        ]


# 内置合规规则库（依据《中华人民共和国广告法》、《中华人民共和国反不正当竞争法》及公共内容安全要求制定）
COMPLIANCE_RULES: list[ComplianceRule] = [
    ComplianceRule(
        rule_id="ad_law_absolute_extreme",
        rule_category="广告法极限词",
        severity="block",
        keywords=[
            "国家级",
            "最高级",
            "最佳",
            "第一",
            "第一品牌",
            "行业第一",
            "全网第一",
            "中国第一",
            "唯一",
            "全国首家",
            "首选",
            "顶级",
            "顶尖",
            "极品",
            "终极",
            "极致",
            "全网首发",
            "独家尊享",
            "万能",
            "史上最好",
            "世界领先",
            "国际一流",
            "无敌",
            "绝无仅有",
        ],
        legal_reference="《中华人民共和国广告法》第九条第（三）项：不得使用“国家级”、“最高级”、“最佳”等用语。",
        suggestion="建议删除或替换为客观、中性陈述（例如替换为“高品质”、“热销”、“广受欢迎”等）。",
    ),
    ComplianceRule(
        rule_id="ad_law_authoritative_claims",
        rule_category="假借权威宣称",
        severity="block",
        keywords=[
            "国家机关指定",
            "特供",
            "专供",
            "国宴",
            "钓鱼台",
            "人民大会堂专供",
            "军工品质",
            "特许专营",
            "免检",
            "中国驰名商标",  # 广告法第14条禁止将驰名商标字样用于广告
        ],
        legal_reference="《广告法》第九条第（二）项及第十四条：严禁使用国家机关名义或“驰名商标”字样进行商业宣传。",
        suggestion="严禁在商业广告或大屏宣传中使用国家机关名义或禁止性专供/免检字样，请立即移除。",
    ),
    ComplianceRule(
        rule_id="ad_law_false_guarantee",
        rule_category="绝对化收益与效果承诺",
        severity="block",
        keywords=[
            "100%保本",
            "零风险",
            "稳赚不赔",
            "无风险高收益",
            "彻底根除",
            "包治百病",
            "永不复发",
            "当天见效",
            "无效退款保证",
            "100%治愈",
        ],
        legal_reference="《广告法》第二十五条、第十六条：金融投资类广告不得含有对未来收益作保证性承诺；医疗/药品广告不得含有表示功效的保证。",
        suggestion="必须清晰标明投资风险提示（如“投资有风险，选择需谨慎”）或药品注意事项，不得做出绝对化承诺。",
    ),
    ComplianceRule(
        rule_id="ad_law_ambiguous_leading",
        rule_category="存疑夸大宣传",
        severity="suspect",
        keywords=[
            "领先",
            "遥遥领先",
            "独创",
            "首创",
            "独家",
            "名牌",
            "驰名",
            "极受欢迎",
            "霸榜",
            "前沿",
        ],
        legal_reference="《广告法》第十一条：广告使用数据、统计资料、调查结果等引证内容的，应当真实、准确，并表明出处。",
        suggestion="使用“领先”、“首创”等词汇需在显著位置标注权威调查出处或专利认证编号，否则涉嫌虚假宣传。",
    ),
    ComplianceRule(
        rule_id="public_safety_illegal",
        rule_category="公共安全与违法违禁",
        severity="block",
        keywords=[
            "赌博",
            "百家乐",
            "代开增值税发票",
            "套现",
            "办假证",
            "私人侦探",
            "定位窃听",
            "枪支弹药",
            "迷魂药",
            "高利贷",
            "裸贷",
        ],
        legal_reference="《中华人民共和国网络安全法》第十二条：任何个人和组织不得利用网络传播违法犯罪有害信息。",
        suggestion="检测到严重违法违禁信息，严禁在户外大屏或公共介质发布，需立即阻断并上报安全合规部门。",
    ),
    ComplianceRule(
        rule_id="unregulated_contact_solicitation",
        rule_category="违规引流与联系方式",
        severity="suspect",
        keywords=[],
        regex_patterns=[
            r"(?:加v|加微信|wx|微信号|vx)\s*[:：]?\s*[a-zA-Z0-9_-]{5,20}",
            r"扫码(?:\s*立即)?\s*领红包",
            r"兼职刷单",
            r"日赚\s*[0-9]{3,5}\s*元",
        ],
        legal_reference="公共户外媒体管理规范：严禁发布未经备案的隐蔽社交软件个人号引流、诱导刷单等涉诈风险信息。",
        suggestion="公共大屏广告应使用官方认证的客服电话或统一品牌公众号，不得直接放置个人微信号引流。",
    ),
]


def parse_words_input(val: Any) -> list[str]:
    """将字符串(支持逗号、分号、换行、竖线分隔)或集合解析为去重且去除首尾空白的词汇列表"""
    if not val:
        return []
    if isinstance(val, (list, tuple, set)):
        res: list[str] = []
        for item in val:
            res.extend(parse_words_input(item))
        # 保持顺序去重
        seen: set[str] = set()
        deduped: list[str] = []
        for w in res:
            if w not in seen:
                seen.add(w)
                deduped.append(w)
        return deduped
    if isinstance(val, str):
        tokens = re.split(r"[,;\n\|，；\r]+", val)
        seen_str: set[str] = set()
        deduped_str: list[str] = []
        for t in tokens:
            stripped = t.strip()
            if stripped and stripped not in seen_str:
                seen_str.add(stripped)
                deduped_str.append(stripped)
        return deduped_str
    return []


_CACHE_DICT_PATH: str | None = None
_CACHE_MTIME: float = -1.0
_CACHE_SIZE: int = -1
_CACHED_RULES: list[ComplianceRule] = []
_CACHED_WHITELIST: list[str] = []


def resolve_compliance_dict_path() -> Path:
    """获取企业自定义合规词库配置文件路径"""
    env_path = os.getenv("SCENARA_OCR_COMPLIANCE_DICT_PATH", "").strip()
    if env_path:
        return Path(env_path).resolve()
    return Path("data/compliance/custom_sensitive_words.json").resolve()


def load_persistent_compliance_data(
    dict_path: Path | None = None,
) -> tuple[list[ComplianceRule], list[str]]:
    """从磁盘加载持久化企业自定义合规词库与白名单，基于 mtime 自动热重载"""
    global _CACHE_DICT_PATH, _CACHE_MTIME, _CACHE_SIZE, _CACHED_RULES, _CACHED_WHITELIST
    path = dict_path or resolve_compliance_dict_path()
    path_str = str(path)

    if not path.is_file():
        return ([], [])

    try:
        st = path.stat()
        mtime = st.st_mtime
        size = st.st_size
    except OSError:
        return ([], [])

    if path_str == _CACHE_DICT_PATH and mtime == _CACHE_MTIME and size == _CACHE_SIZE:
        return (_CACHED_RULES, _CACHED_WHITELIST)

    rules: list[ComplianceRule] = []
    whitelist: list[str] = []

    try:
        content = path.read_text(encoding="utf-8").strip()
        if content:
            if content.startswith("{"):
                data = json.loads(content)
                raw_whitelist = data.get("whitelist", [])
                whitelist = parse_words_input(raw_whitelist)
                raw_rules = data.get("rules", [])
                for r in raw_rules:
                    r_id = str(r.get("rule_id") or f"custom_rule_{len(rules) + 1}")
                    r_cat = str(r.get("rule_category") or "企业自定义敏感词")
                    r_sev = str(r.get("severity") or "block").lower()
                    if r_sev not in {"block", "suspect", "info"}:
                        r_sev = "block"
                    r_kws = parse_words_input(r.get("keywords", []))
                    r_ref = str(r.get("legal_reference") or "企业内部合规质检标准")
                    r_sug = str(
                        r.get("suggestion")
                        or "检测到企业自定义敏感词，请根据业务规范核实整改。"
                    )
                    r_regex = [
                        str(p) for p in r.get("regex_patterns", []) if str(p).strip()
                    ]
                    if r_kws or r_regex:
                        rules.append(
                            ComplianceRule(
                                rule_id=r_id,
                                rule_category=r_cat,
                                severity=r_sev,
                                keywords=r_kws,
                                legal_reference=r_ref,
                                suggestion=r_sug,
                                regex_patterns=r_regex,
                            )
                        )
            else:
                words = parse_words_input(content)
                if words:
                    rules.append(
                        ComplianceRule(
                            rule_id="custom_persistent_words",
                            rule_category="企业自定义敏感词",
                            severity="block",
                            keywords=words,
                            legal_reference="企业自定义敏感词库标准",
                            suggestion="检测到企业自定义敏感词，请根据业务规范核实整改。",
                        )
                    )
    except Exception as e:
        logger.warning("加载企业自定义合规词库失败 (%s): %s", path, e)

    _CACHE_DICT_PATH = path_str
    _CACHE_MTIME = mtime
    _CACHE_SIZE = size
    _CACHED_RULES = rules
    _CACHED_WHITELIST = whitelist
    return (rules, whitelist)


class OcrComplianceChecker:
    """全介质 OCR 文本合规性审核检测器（三层分级合规质检体系：法规基线 + 持久化企业词库 + 任务级动态词库 + 白名单豁免）"""

    def __init__(
        self,
        base_rules: list[ComplianceRule] | None = None,
        dict_path: Path | None = None,
    ) -> None:
        self.base_rules = base_rules if base_rules is not None else COMPLIANCE_RULES
        self.dict_path = dict_path

    def inspect(
        self,
        full_text: str,
        blocks: list[Any] | None = None,
        custom_words: list[str] | str | None = None,
        whitelist: list[str] | str | None = None,
        custom_severity: str = "block",
    ) -> OcrComplianceReport:
        """对 OCR 聚合文本及各文本块进行分层合规性检测与白名单豁免过滤"""
        if not full_text or not full_text.strip():
            return OcrComplianceReport(
                status="pass", risk_score=0.0, total_hits=0, hits=[]
            )

        # 1. 汇总持久化白名单与任务级白名单
        persistent_rules, persistent_whitelist = load_persistent_compliance_data(
            self.dict_path
        )
        task_whitelist = parse_words_input(whitelist)
        all_whitelist = parse_words_input(persistent_whitelist + task_whitelist)

        # 2. 汇总规则集：法规基线 + 持久化词库 + 任务级自定义词
        all_rules = list(self.base_rules) + list(persistent_rules)
        task_words = parse_words_input(custom_words)
        if task_words:
            all_rules.append(
                ComplianceRule(
                    rule_id="custom_task_sensitive_words",
                    rule_category="自定义敏感词",
                    severity=custom_severity
                    if custom_severity in {"block", "suspect", "info"}
                    else "block",
                    keywords=task_words,
                    legal_reference="单次任务自定义敏感词风控规范",
                    suggestion="命中用户自定义敏感词，请根据业务风控要求核实并处置。",
                )
            )

        hits: list[OcrComplianceHit] = []
        lower_text = full_text.lower()

        # 3. 计算白名单在文本中的所有字符有效区间，命中白名单区间的违规词将被豁免放行
        whitelist_spans: list[tuple[int, int]] = []
        if all_whitelist:
            for w in all_whitelist:
                w_lower = w.lower().strip()
                if not w_lower:
                    continue
                pos = 0
                while True:
                    idx = lower_text.find(w_lower, pos)
                    if idx == -1:
                        break
                    whitelist_spans.append((idx, idx + len(w_lower)))
                    pos = idx + 1

        def is_whitelisted(s: int, e: int) -> bool:
            for ws, we in whitelist_spans:
                if ws <= s and e <= we:
                    return True
            return False

        # 辅助函数: 找出某个字符偏移落在哪个 block 上
        def find_block_id(start_pos: int, word_len: int) -> str | None:
            if not blocks:
                return None
            accumulated = 0
            for b in blocks:
                b_text = getattr(b, "text", "") or ""
                b_len = len(b_text)
                if accumulated <= start_pos < accumulated + b_len:
                    return getattr(b, "block_id", None)
                accumulated += b_len + 1
            return None

        # 4. 关键词规则匹配
        for rule in all_rules:
            for kw in rule.keywords:
                start = 0
                kw_lower = kw.lower()
                while True:
                    idx = lower_text.find(kw_lower, start)
                    if idx == -1:
                        break
                    end = idx + len(kw)
                    # 白名单检查：如果在白名单涵盖区间内，予以放行豁免
                    if not is_whitelisted(idx, end):
                        block_id = find_block_id(idx, len(kw))
                        hits.append(
                            OcrComplianceHit(
                                rule_id=rule.rule_id,
                                rule_category=rule.rule_category,
                                severity=rule.severity,
                                word=full_text[idx:end],
                                start=idx,
                                end=end,
                                block_id=block_id,
                                legal_reference=rule.legal_reference,
                                suggestion=rule.suggestion,
                            )
                        )
                    start = end

            # 5. 正则规则匹配
            for pattern in rule.compiled_regex:
                for match in pattern.finditer(full_text):
                    s, e = match.span()
                    if not is_whitelisted(s, e):
                        block_id = find_block_id(s, e - s)
                        hits.append(
                            OcrComplianceHit(
                                rule_id=rule.rule_id,
                                rule_category=rule.rule_category,
                                severity=rule.severity,
                                word=match.group(0),
                                start=s,
                                end=e,
                                block_id=block_id,
                                legal_reference=rule.legal_reference,
                                suggestion=rule.suggestion,
                            )
                        )

        # 6. 去除重叠命中（相同起止区间优先保留较长词）
        unique_hits: list[OcrComplianceHit] = []
        seen_spans: set[tuple[int, int]] = set()
        for hit in sorted(hits, key=lambda h: (h.start, -len(h.word))):
            span = (hit.start, hit.end)
            if span not in seen_spans:
                seen_spans.add(span)
                unique_hits.append(hit)

        if not unique_hits:
            summary = "合规通过：未发现违规极限用语或安全风险内容"
            if all_whitelist and whitelist_spans:
                summary += f"（已应用 {len(all_whitelist)} 项业务白名单豁免保护）"
            return OcrComplianceReport(
                status="pass",
                risk_score=0.0,
                total_hits=0,
                hits=[],
                summary=summary,
            )

        has_block = any(h.severity == "block" for h in unique_hits)
        has_suspect = any(h.severity == "suspect" for h in unique_hits)

        if has_block:
            status = "block"
            risk_score = min(1.0, 0.7 + 0.05 * len(unique_hits))
            summary = f"严重违规：发现 {sum(1 for h in unique_hits if h.severity == 'block')} 处违规内容，严禁直接对外发布"
        elif has_suspect:
            status = "suspect"
            risk_score = min(0.69, 0.3 + 0.05 * len(unique_hits))
            summary = f"疑似存疑：发现 {len(unique_hits)} 处存疑内容，建议补充佐证或整改后发布"
        else:
            status = "pass"
            risk_score = 0.1
            summary = "提示关注：存在少量需留意的表述"

        return OcrComplianceReport(
            status=status,
            risk_score=round(risk_score, 2),
            total_hits=len(unique_hits),
            hits=unique_hits,
            summary=summary,
        )
