#!/usr/bin/env python3
"""Heuristic content audit for Chinese research reports.

The checks are deliberately conservative. They point reviewers to paragraphs
that deserve attention; they do not decide whether a scientific or commercial
claim is true.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LIST_RE = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
SENTENCE_RE = re.compile(r"(?<=[。！？!?；;])\s*")
CITATION_RE = re.compile(
    r"(?:\[(?:\^\d+|[A-Za-z]+-?\d+|"
    r"\d+(?:\s*[-–—]\s*\d+)?(?:\s*[,，]\s*\d+(?:\s*[-–—]\s*\d+)?)*)\]|"
    r"\[[^\]]*https?://[^\]]+\]|"
    r"https?://\S+|(?:来源|资料来源|出处)\s*[:：])",
    re.IGNORECASE,
)
NUMERIC_CITATION_RE = re.compile(
    r"\[(?P<body>\^?\d+(?:\s*[-–—]\s*\d+)?(?:\s*[,，]\s*\d+(?:\s*[-–—]\s*\d+)?)*)\]"
)
NUMBERED_REFERENCE_ENTRY_RE = re.compile(
    r"^\s*(?:[-+*]\s+)?(?:\[(?:\^)?(?P<number>\d+)\]|"
    r"(?P<bare_number>\d+)[.)])(?:\s*[:：]|\s+)"
)
FINDING_REFERENCE_RE = re.compile(r"\b(?:F|J|R|U)-\d+\b", re.IGNORECASE)
SUMMARY_LEAD_LABEL_RE = re.compile(
    r"^\s*(?:\*\*)?[\u4e00-\u9fff]{2,8}[。.:：](?:\*\*)?\s*"
)
SUMMARY_SENTENCE_LABEL_RE = re.compile(
    r"(?:^|[。！？!?；;])\s*(?:\*\*)?[\u4e00-\u9fff]{2,8}[：:]\s*"
)
INTERNAL_CLASSIFICATION_HEADING_RE = re.compile(r"^[DFJRU]-\d+\b", re.IGNORECASE)
INTERNAL_CLASSIFICATION_LEAD_RE = re.compile(
    r"^\s*(?:\*\*)?[DFJRU]-\d+\s*[：:]", re.IGNORECASE
)
INTERNAL_CLASSIFICATION_ANY_RE = re.compile(
    r"(?<![A-Za-z0-9_-])[DFJRU]-\d{1,3}\b", re.IGNORECASE
)
INTERNAL_SOURCE_CITATION_RE = re.compile(
    r"(?:\[\s*S(?:[-‐‑–—]|\s)?\d{1,3}\s*\]|"
    r"(?<![A-Za-z0-9_-])S(?:[-‐‑–—]|\s)?\d{1,3}\b)",
    re.IGNORECASE,
)
QUESTION_STYLE_HEADING_RE = re.compile(
    r"(?:[？?]$|(?:什么|哪些|为什么|怎么办|还有啥)$|"
    r"(?:^|.*)(?:如何|怎么)(?:推进|选择|选|判断|实施|处理|安排|验证|评估)$|"
    r"(?:到底|要不要|靠不靠谱))"
)
COLLOQUIAL_PURPOSE_RE = re.compile(
    r"(?:这份|本)?报告(?:要)?帮助.{0,12}(?:判断|弄清|看清)|"
    r"(?:帮助|供)(?:项目)?(?:团队|项目组|评审组|读者).{0,12}(?:判断|弄清|看清|了解)"
)
VAGUE_PENDING_DISCLOSURE_RE = re.compile(
    r"尚未(?:公布|公开|披露|提供|给出|说明)"
)
COLLOQUIAL_SOURCE_GAP_RE = re.compile(
    r"(?:公告|文件|通知|资料|材料|说明|页面).{0,12}没有(?:公布|公开|披露|提供|给出|说明)"
)
DEFENSIVE_LIMITATION_RE = re.compile(
    r"尚(?:不能|无法|难以)(?:说明|判断|确认|评估|下结论)"
)
DOUBLE_NEGATION_RE = re.compile(
    r"(?:不是没有|并非没有|并非不存在|并不是不|不是不|不能不|不会不|未必不|无不|没有不|不无)"
)
WEAK_QUALIFIER_RE = re.compile(
    r"(?:在一定程度上|一定程度上|某种程度上|某种意义上|从某种意义上(?:看|说)?|相对而言|不排除)"
)
FORMAL_UNFINISHED_HEADING_RE = re.compile(
    r"(?:证据(?:范围|边界|缺口|限制)|资料(?:缺口|缺失)|"
    r"待(?:核实|确认|补充|补证)|引用(?:信息)?待补|"
    r"未(?:完成|闭合)|后续(?:取证|调研)|研究(?:缺口|限制))"
)
FORMAL_UNFINISHED_STATUS_RE = re.compile(
    r"(?:有待(?:补充|核实|确认)|待(?:核实|确认|补充|补证|完善|补)|"
    r"仍待(?:补证|补充)|引用(?:信息)?待补|"
    r"(?:证据|资料|材料|信息|来源)(?:不足|缺口|限制|未闭合|不完整)|"
    r"(?:尚|仍)未(?:完成|闭合|核验|确认|覆盖)|"
    r"暂不(?:判断|评估|下结论)|"
    r"(?:现有|上述|原稿)?(?:资料|材料|证据).{0,18}"
    r"(?:不能|无法|不足以|不支持|难以).{0,18}"
    r"(?:说明|判断|确认|评估|估算|证明)|"
    r"(?:还|仍).{0,8}(?:需要|缺少).{0,24}(?:资料|证据|来源|数据))"
)
DOCUMENT_ROLES = {"formal", "internal-ledger"}
ACTIONABLE_HEADING_RE = re.compile(
    r"(?:建议|行动(?:安排|方案)?|下一步|下一阶段|推进(?:安排|计划)?|"
    r"实施(?:计划|安排)?|验证安排|后续安排|工作安排|路线图)"
)
ACTION_DIRECTIVE_RE = re.compile(
    r"(?:建议|应当|应该|应优先|应在|应先|不宜|不应|必须|"
    r"下一步(?:应|需|要|先)?|下一阶段(?:应|需|要|先)?|"
    r"优先(?:开展|推进|建设|验证|完成)|暂不(?:开展|推进|冻结|确定)?|建议先)|"
    r"(?:^|[，。；：\s])宜(?=[，。；：\s])|"
    r"(?:以|按).{0,24}进入后续(?:验证|工作)|"
    r"(?:待|在).{0,40}(?:后|以后).{0,12}(?:再|再行)?(?:冻结|评估|确定|推进|实施|验证)|"
    r"(?:后续|项目组|项目团队|本项目|该项目|该方案).{0,12}(?:需|应|要|须).{0,12}"
    r"(?:推进|开展|建设|冻结|验证|评估|确定|补齐)"
)
SUMMARY_META_LEAD_RE = re.compile(
    r"^\s*(?:本报告|本文|本次(?:研究|重构)|原稿(?:所列|中的)|现有资料|据此|因此|基于(?:现有|上述)|就目前)"
)
SUMMARY_NEGATION_RE = re.compile(
    r"(?:也|亦)?没有|尚未|仍未|"
    r"未(?:见|能|予|获|经|完成|公开|公布|披露|说明|提供|给出|形成|验证|确认|核验|覆盖|达到|进入|建立|支持)|"
    r"不能|无法|不足以|不具备|缺少|缺乏|只能"
)

DEFINITION_PATTERNS = (
    "是指",
    "指的是",
    "定义为",
    "通常指",
    "本文所称",
    "本报告所称",
    "又称",
    "即指",
    "英文全称",
)
DEFINITION_SENTENCE_RE = re.compile(
    r"^(?:本文|本报告)?(?:所称)?[\u4e00-\u9fffA-Za-z0-9（）()·-]{2,24}"
    r"(?:是指|指的是|定义为|通常指|又称|即指|"
    r"是(?:一种|一类|一套|一个|由|通过|设备|系统|方式|技术|服务|网络|过程|状态))"
)
FACT_PATTERNS = (
    "发布",
    "公布",
    "公开",
    "显示",
    "列明",
    "提出",
    "记录",
    "统计",
    "测得",
    "报告称",
    "官网",
    "文件规定",
    "截至",
    "根据",
)
JUDGMENT_PATTERNS = (
    "表明",
    "说明",
    "意味着",
    "据此",
    "由此",
    "可以判断",
    "可判断",
    "综合来看",
    "综合判断",
    "可见",
    "反映出",
    "预计",
    "推测",
)
UNKNOWN_PATTERNS = (
    "尚无",
    "未见",
    "无法确认",
    "待核实",
    "待确认",
    "证据不足",
    "未公开",
    "未知",
    "待补充",
)
GENERIC_HEADINGS = {
    "核心洞察",
    "关键洞察",
    "深度解析",
    "战略启示",
    "关键抓手",
    "核心判断",
    "发展赋能",
    "趋势展望",
    "总结与展望",
}
JARGON_PATTERNS = (
    "赋能",
    "抓手",
    "能力闭环",
    "端到端闭环",
    "生态位",
    "战略纵深",
    "深度解析",
    "核心洞察",
    "价值重构",
    "全链路",
    "蓬勃发展",
)
TRANSITION_PATTERNS = (
    "从市场来看",
    "从技术来看",
    "不只是",
    "更是",
    "综上所述",
    "总体而言",
)


@dataclass(frozen=True)
class Paragraph:
    line: int
    section: str
    text: str


def _clean_heading(value: str) -> str:
    return re.sub(r"[*_`]+", "", value).strip()


def _flush_paragraph(
    output: list[Paragraph], buffer: list[str], line: int, section: str
) -> None:
    if not buffer:
        return
    text = " ".join(part.strip() for part in buffer if part.strip()).strip()
    if text:
        output.append(Paragraph(line=line, section=section, text=text))
    buffer.clear()


def parse_markdown(text: str) -> tuple[list[Paragraph], list[tuple[int, str]]]:
    paragraphs: list[Paragraph] = []
    headings: list[tuple[int, str]] = []
    buffer: list[str] = []
    buffer_line = 1
    current_section = "文档开头"
    in_code = False

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            _flush_paragraph(paragraphs, buffer, buffer_line, current_section)
            in_code = not in_code
            continue
        if in_code:
            continue

        heading_match = HEADING_RE.match(stripped)
        if heading_match:
            _flush_paragraph(paragraphs, buffer, buffer_line, current_section)
            current_section = _clean_heading(heading_match.group(2))
            headings.append((line_number, current_section))
            continue

        if not stripped:
            _flush_paragraph(paragraphs, buffer, buffer_line, current_section)
            continue

        if stripped.startswith("|") or stripped.startswith("![]("):
            _flush_paragraph(paragraphs, buffer, buffer_line, current_section)
            continue

        # Preserve one source entry per line so numbered citations can be
        # matched against the correct reference entry.
        if _is_reference_section(current_section):
            _flush_paragraph(paragraphs, buffer, buffer_line, current_section)
            paragraphs.append(
                Paragraph(line=line_number, section=current_section, text=stripped)
            )
            continue

        if LIST_RE.match(stripped):
            _flush_paragraph(paragraphs, buffer, buffer_line, current_section)
            item = LIST_RE.sub("", stripped, count=1).strip()
            if item:
                paragraphs.append(
                    Paragraph(line=line_number, section=current_section, text=item)
                )
            continue

        if not buffer:
            buffer_line = line_number
        buffer.append(stripped)

    _flush_paragraph(paragraphs, buffer, buffer_line, current_section)
    return paragraphs, headings


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_RE.split(text) if part.strip()]


def classify_sentence(sentence: str) -> set[str]:
    categories: set[str] = set()
    if any(marker in sentence for marker in DEFINITION_PATTERNS) or DEFINITION_SENTENCE_RE.search(
        sentence
    ):
        categories.add("definition")
    has_citation = bool(CITATION_RE.search(sentence))
    has_dated_or_quantified_value = bool(
        re.search(r"(?:19|20)\d{2}年", sentence)
        or re.search(
            r"\d+(?:\.\d+)?\s*(?:%|亿元|万元|万户|户|家|台|套|GHz|MHz|Gbit/s|Mbit/s|kg|W)\b",
            sentence,
            re.IGNORECASE,
        )
    )
    fact_markers = {marker for marker in FACT_PATTERNS if marker in sentence}
    if "发布" in fact_markers and "发布后" in sentence:
        fact_markers.remove("发布")
    if has_citation or has_dated_or_quantified_value or fact_markers:
        categories.add("fact")
    if any(marker in sentence for marker in JUDGMENT_PATTERNS):
        categories.add("judgment")
    if ACTION_DIRECTIVE_RE.search(sentence):
        categories.add("action")
    if any(marker in sentence for marker in UNKNOWN_PATTERNS):
        categories.add("unknown")
    return categories


def _finding(
    code: str,
    severity: str,
    message: str,
    *,
    line: int | None = None,
    section: str | None = None,
    excerpt: str | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "code": code,
        "severity": severity,
        "message": message,
    }
    if line is not None:
        item["line"] = line
    if section:
        item["section"] = section
    if excerpt:
        item["excerpt"] = excerpt[:240]
    return item


def _is_summary(section: str) -> bool:
    normalized = re.sub(r"\s+", "", section)
    return normalized in {"摘要", "执行摘要", "报告摘要", "内容摘要"}


def _is_reference_section(section: str) -> bool:
    normalized = re.sub(r"\s+", "", section)
    return any(
        normalized.startswith(prefix)
        for prefix in ("参考资料", "参考文献", "来源", "资料来源", "注释")
    )


def _normalize_sentence(sentence: str) -> str:
    sentence = CITATION_RE.sub("", sentence)
    sentence = re.sub(r"[*_`\s，。！？!?；;：:]", "", sentence)
    return sentence


def _expand_numeric_citation_body(body: str) -> set[int]:
    normalized = re.sub(r"\s+", "", body)
    if normalized.startswith("^"):
        return {int(normalized[1:])}

    identifiers: set[int] = set()
    for item in re.split(r"[,，]", normalized):
        match = re.fullmatch(r"(\d+)(?:[-–—](\d+))?", item)
        if not match:
            continue
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if end < start or end - start > 100:
            continue
        identifiers.update(range(start, end + 1))
    return identifiers


def audit_text(
    text: str, source: str = "<memory>", document_role: str = "formal"
) -> dict[str, object]:
    if document_role not in DOCUMENT_ROLES:
        choices = ", ".join(sorted(DOCUMENT_ROLES))
        raise ValueError(f"unsupported document role {document_role!r}; use {choices}")

    formal = document_role == "formal"
    paragraphs, headings = parse_markdown(text)
    findings: list[dict[str, object]] = []
    summary_labelled_paragraphs: list[Paragraph] = []
    summary_meta_lead_paragraphs: list[Paragraph] = []
    summary_sentence_labelled_paragraphs: list[Paragraph] = []
    summary_negation_chain_paragraphs: list[Paragraph] = []

    for line, heading in headings:
        if formal and heading in GENERIC_HEADINGS:
            findings.append(
                _finding(
                    "GENERIC_HEADING",
                    "warning",
                    "标题没有直接说明本节讨论的对象或发现。",
                    line=line,
                    section=heading,
                    excerpt=heading,
                )
            )
        if formal and INTERNAL_CLASSIFICATION_HEADING_RE.match(heading):
            findings.append(
                _finding(
                    "INTERNAL_CLASSIFICATION_LABEL",
                    "warning",
                    "正式标题暴露了工作副本的 D/F/J/R/U 分类编号，应改成说明实际内容的标题。",
                    line=line,
                    section=heading,
                    excerpt=heading,
                )
            )
        if formal and ACTIONABLE_HEADING_RE.search(heading):
            findings.append(
                _finding(
                    "ACTION_DIRECTIVE_HEADING",
                    "warning",
                    "正式标题包含建议、行动或推进安排；应删除行动安排，改为对象明确的事实或结论标题。",
                    line=line,
                    section=heading,
                    excerpt=heading,
                )
            )
        if formal and QUESTION_STYLE_HEADING_RE.search(heading):
            findings.append(
                _finding(
                    "QUESTION_STYLE_HEADING",
                    "warning",
                    "正式标题直接使用了口语化读者问题；应改成对象明确的名词短语或结论句。",
                    line=line,
                    section=heading,
                    excerpt=heading,
                )
            )
        if formal and FORMAL_UNFINISHED_HEADING_RE.search(heading):
            findings.append(
                _finding(
                    "FORMAL_UNFINISHED_STATUS",
                    "warning",
                    "正式标题呈现了未完成调研或取证状态；应移入内部调研台账，完成后再写入正式报告。",
                    line=line,
                    section=heading,
                    excerpt=heading,
                )
            )

    summary_sentences: list[tuple[Paragraph, str, set[str]]] = []
    sentence_locations: dict[str, list[tuple[int, str, str]]] = defaultdict(list)

    for paragraph in paragraphs:
        sentences = split_sentences(paragraph.text)
        sentence_categories = [classify_sentence(sentence) for sentence in sentences]
        paragraph_categories = set().union(*sentence_categories) if sentences else set()

        if _is_summary(paragraph.section):
            summary_sentences.extend(
                (paragraph, sentence, categories)
                for sentence, categories in zip(sentences, sentence_categories)
            )
            if SUMMARY_LEAD_LABEL_RE.match(paragraph.text):
                summary_labelled_paragraphs.append(paragraph)
            if SUMMARY_META_LEAD_RE.match(paragraph.text):
                summary_meta_lead_paragraphs.append(paragraph)
            if len(SUMMARY_SENTENCE_LABEL_RE.findall(paragraph.text)) >= 2:
                summary_sentence_labelled_paragraphs.append(paragraph)
            negation_counts = [
                len(SUMMARY_NEGATION_RE.findall(sentence)) for sentence in sentences
            ]
            has_dense_sentence = any(count >= 3 for count in negation_counts)
            has_dense_pair = any(
                left > 0 and right > 0 and left + right >= 3
                for left, right in zip(negation_counts, negation_counts[1:])
            )
            if has_dense_sentence or has_dense_pair:
                summary_negation_chain_paragraphs.append(paragraph)

        if formal and INTERNAL_CLASSIFICATION_LEAD_RE.match(paragraph.text):
            findings.append(
                _finding(
                    "INTERNAL_CLASSIFICATION_LABEL",
                    "warning",
                    "正式段落暴露了工作副本的 D/F/J/R/U 分类编号，应删除标签并改写为自然句子。",
                    line=paragraph.line,
                    section=paragraph.section,
                    excerpt=paragraph.text,
                )
            )
        internal_body_labels = INTERNAL_CLASSIFICATION_ANY_RE.findall(paragraph.text)
        if formal and internal_body_labels and not INTERNAL_CLASSIFICATION_LEAD_RE.match(
            paragraph.text
        ):
            findings.append(
                _finding(
                    "INTERNAL_CLASSIFICATION_BODY",
                    "warning",
                    f"正文中残留工作分类编号（{', '.join(sorted(set(internal_body_labels), key=str.upper))}），应改为自然标题、章节引用或来源标识。",
                    line=paragraph.line,
                    section=paragraph.section,
                    excerpt=paragraph.text,
                )
            )

        internal_source_markers = INTERNAL_SOURCE_CITATION_RE.findall(paragraph.text)
        if formal and internal_source_markers:
            findings.append(
                _finding(
                    "INTERNAL_SOURCE_CITATION",
                    "warning",
                    "正式稿使用了 S 类内部来源编号；应核对真实来源，并转换为有完整条目支撑的脚注、尾注或参考文献编号。",
                    line=paragraph.line,
                    section=paragraph.section,
                    excerpt=paragraph.text,
                )
            )

        if formal and COLLOQUIAL_PURPOSE_RE.search(paragraph.text):
            findings.append(
                _finding(
                    "COLLOQUIAL_PURPOSE_STATEMENT",
                    "warning",
                    "目的陈述使用了“帮助或供某人判断”式口语元话语；应直接写评估对象、判定条件或决策事项。",
                    line=paragraph.line,
                    section=paragraph.section,
                    excerpt=paragraph.text,
                )
            )

        if (
            formal
            and DOUBLE_NEGATION_RE.search(paragraph.text)
            and not _is_reference_section(paragraph.section)
        ):
            findings.append(
                _finding(
                    "DOUBLE_NEGATION",
                    "warning",
                    "正式稿出现连续否定，容易增加理解负担；应改为直接肯定或直接否定的表述。",
                    line=paragraph.line,
                    section=paragraph.section,
                    excerpt=paragraph.text,
                )
            )

        if (
            formal
            and WEAK_QUALIFIER_RE.search(paragraph.text)
            and not _is_reference_section(paragraph.section)
        ):
            findings.append(
                _finding(
                    "WEAK_QUALIFIER",
                    "warning",
                    "正式稿使用了缺少证据作用的弱化限定语；应删除，或改写为可核验的条件、区间、样本或来源。",
                    line=paragraph.line,
                    section=paragraph.section,
                    excerpt=paragraph.text,
                )
            )

        if (
            formal
            and
            ACTION_DIRECTIVE_RE.search(paragraph.text)
            and not _is_reference_section(paragraph.section)
        ):
            findings.append(
                _finding(
                    "ACTION_DIRECTIVE",
                    "warning",
                    "正式稿保留了建议、应当、不宜或下一步等行动性表达；应删除行动安排，不用“证据条件”改写后保留。",
                    line=paragraph.line,
                    section=paragraph.section,
                    excerpt=paragraph.text,
                )
            )

        if (
            formal
            and
            DEFENSIVE_LIMITATION_RE.search(paragraph.text)
            and not _is_reference_section(paragraph.section)
        ):
            findings.append(
                _finding(
                    "DEFENSIVE_LIMITATION",
                    "warning",
                    "“尚不能说明”类表述像自我免责；应移入内部调研台账，完成取证后再形成正式结论。",
                    line=paragraph.line,
                    section=paragraph.section,
                    excerpt=paragraph.text,
                )
            )

        vague_pending_disclosure = (
            VAGUE_PENDING_DISCLOSURE_RE.search(paragraph.text)
            or COLLOQUIAL_SOURCE_GAP_RE.search(paragraph.text)
        )
        if (
            formal
            and vague_pending_disclosure
            and not _is_reference_section(paragraph.section)
        ):
            findings.append(
                _finding(
                    "VAGUE_PENDING_DISCLOSURE",
                    "warning",
                    "“尚未公布/公开/披露”与“资料没有给出”把未完成取证带入正式稿，也容易形成悬空判断；应移入内部调研台账。",
                    line=paragraph.line,
                    section=paragraph.section,
                    excerpt=paragraph.text,
                )
            )

        if (
            formal
            and FORMAL_UNFINISHED_STATUS_RE.search(paragraph.text)
        ):
            findings.append(
                _finding(
                    "FORMAL_UNFINISHED_STATUS",
                    "warning",
                    "正式报告呈现了未完成调研、来源补全或取证状态；应移入内部调研台账，完成后再写入正式报告。不要将其改写成资料范围、证据条件或免责声明。",
                    line=paragraph.line,
                    section=paragraph.section,
                    excerpt=paragraph.text,
                )
            )

        if _is_summary(paragraph.section):
            mixed = "definition" in paragraph_categories and bool(
                paragraph_categories & {"fact", "judgment", "action"}
            )
        else:
            mixed = (
                "definition" in paragraph_categories
                and bool(
                    paragraph_categories & {"fact", "judgment", "action"}
                )
            ) or (
                "action" in paragraph_categories
                and bool(paragraph_categories & {"fact", "judgment"})
            ) or (
                "fact" in paragraph_categories and "judgment" in paragraph_categories
            )
        if formal and mixed and not _is_reference_section(paragraph.section):
            findings.append(
                _finding(
                    "MIXED_STATEMENT_TYPES",
                    "warning",
                    "同一段落可能混合了定义、事实、综合判断或行动性表达，应人工拆分。",
                    line=paragraph.line,
                    section=paragraph.section,
                    excerpt=paragraph.text,
                )
            )

        fact_sentences = [
            sentence
            for sentence, categories in zip(sentences, sentence_categories)
            if "fact" in categories and "definition" not in categories
        ]
        has_evidence_reference = bool(
            CITATION_RE.search(paragraph.text)
            or FINDING_REFERENCE_RE.search(paragraph.text)
            or (
                not formal
                and INTERNAL_SOURCE_CITATION_RE.search(paragraph.text)
            )
        )
        if (
            fact_sentences
            and not has_evidence_reference
            and not _is_reference_section(paragraph.section)
        ):
            findings.append(
                _finding(
                    "UNCITED_FACTUAL_PARAGRAPH",
                    "warning",
                    "段落含日期、数字或来源性陈述，但未检测到就近来源标识。",
                    line=paragraph.line,
                    section=paragraph.section,
                    excerpt=paragraph.text,
                )
            )

        jargon = sorted({term for term in JARGON_PATTERNS if term in paragraph.text})
        if jargon:
            findings.append(
                _finding(
                    "CONSULTING_JARGON",
                    "info",
                    f"发现可能空泛的报告用语：{', '.join(jargon)}。",
                    line=paragraph.line,
                    section=paragraph.section,
                    excerpt=paragraph.text,
                )
            )

        for sentence in sentences:
            normalized = _normalize_sentence(sentence)
            if len(normalized) >= 15:
                sentence_locations[normalized].append(
                    (paragraph.line, paragraph.section, sentence)
                )

    if formal:
        reference_numbers: set[int] = set()
        for paragraph in paragraphs:
            if not _is_reference_section(paragraph.section):
                continue
            match = NUMBERED_REFERENCE_ENTRY_RE.match(paragraph.text)
            if match:
                number = match.group("number") or match.group("bare_number")
                reference_numbers.add(int(number))

        unresolved_citations: set[tuple[int, int]] = set()
        for paragraph in paragraphs:
            if _is_reference_section(paragraph.section):
                continue
            for match in NUMERIC_CITATION_RE.finditer(paragraph.text):
                for number in _expand_numeric_citation_body(match.group("body")):
                    key = (paragraph.line, number)
                    if number in reference_numbers or key in unresolved_citations:
                        continue
                    unresolved_citations.add(key)
                    findings.append(
                        _finding(
                            "UNRESOLVED_NUMERIC_CITATION",
                            "warning",
                            f"文内引用 [{number}] 没有对应的真实参考资料条目。",
                            line=paragraph.line,
                            section=paragraph.section,
                            excerpt=paragraph.text,
                        )
                    )

    if summary_sentences:
        definition_count = sum(
            1 for _, _, categories in summary_sentences if "definition" in categories
        )
        density = definition_count / len(summary_sentences)
        if definition_count >= 2 and density >= 0.35:
            paragraph = summary_sentences[0][0]
            findings.append(
                _finding(
                    "SUMMARY_DEFINITION_DENSITY",
                    "warning",
                    f"摘要中 {definition_count}/{len(summary_sentences)} 个句子带定义特征，术语解释可能挤占主要发现。",
                    line=paragraph.line,
                    section=paragraph.section,
                    excerpt=paragraph.text,
                )
            )

    if len(summary_labelled_paragraphs) >= 2:
        first = summary_labelled_paragraphs[0]
        findings.append(
            _finding(
                "SUMMARY_LABEL_CHAIN",
                "warning",
                "摘要连续使用短标签领起段落，容易把内容检查清单写成机械的字段表。",
                line=first.line,
                section=first.section,
                excerpt=first.text,
            )
        )

    if summary_sentence_labelled_paragraphs:
        first = summary_sentence_labelled_paragraphs[0]
        findings.append(
            _finding(
                "SUMMARY_SENTENCE_LABEL_CHAIN",
                "warning",
                "摘要同一段内连续用短标签领起句子，可能是在逐句复述内容清单。",
                line=first.line,
                section=first.section,
                excerpt=first.text,
            )
        )

    if summary_negation_chain_paragraphs:
        first = summary_negation_chain_paragraphs[0]
        findings.append(
            _finding(
                "SUMMARY_NEGATION_CHAIN",
                "warning",
                "摘要连续堆叠否定或限制谓词，容易变成低信息量的缺项清单；应先写可确认事实，再集中收束关键限制。",
                line=first.line,
                section=first.section,
                excerpt=first.text,
            )
        )

    summary_paragraphs = [p for p in paragraphs if _is_summary(p.section)]
    summary_paragraph_count = len(summary_paragraphs)
    if (
        summary_paragraph_count >= 3
        and len(summary_meta_lead_paragraphs) >= 3
        and len(summary_meta_lead_paragraphs) / summary_paragraph_count >= 0.75
    ):
        first = summary_meta_lead_paragraphs[0]
        findings.append(
            _finding(
                "SUMMARY_FORMULAIC_LEADS",
                "warning",
                f"摘要 {summary_paragraph_count} 个段落中有 {len(summary_meta_lead_paragraphs)} 个以报告元话语开头，可能是在逐项复述内容清单；应合并为自然的判断链。",
                line=first.line,
                section=first.section,
                excerpt=first.text,
            )
        )

    for locations in sentence_locations.values():
        if len(locations) < 2:
            continue
        first_line, first_section, first_sentence = locations[0]
        other_lines = ", ".join(str(line) for line, _, _ in locations[1:4])
        findings.append(
            _finding(
                "DUPLICATE_SENTENCE",
                "info",
                f"同一句或近乎相同的句子重复出现，其他位置：{other_lines}。",
                line=first_line,
                section=first_section,
                excerpt=first_sentence,
            )
        )

    visible_text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    visible_text = re.sub(r"^#{1,6}\s+.*$", "", visible_text, flags=re.MULTILINE)
    bold_chunks = re.findall(r"\*\*(.+?)\*\*", visible_text, flags=re.DOTALL)
    plain_length = len(re.sub(r"\s+", "", re.sub(r"[*_`]", "", visible_text)))
    bold_length = sum(len(re.sub(r"\s+", "", chunk)) for chunk in bold_chunks)
    bold_ratio = bold_length / plain_length if plain_length else 0.0
    if plain_length >= 200 and bold_ratio >= 0.35:
        findings.append(
            _finding(
                "EXCESSIVE_BOLD",
                "info",
                f"正文加粗字符约占 {bold_ratio:.0%}，可能削弱层次。",
            )
        )

    for phrase in TRANSITION_PATTERNS:
        count = text.count(phrase)
        if count >= 3:
            findings.append(
                _finding(
                    "REPETITIVE_TRANSITION",
                    "info",
                    f"连接表达“{phrase}”出现 {count} 次，建议检查是否为模板化重复。",
                )
            )

    severity_counts = Counter(str(item["severity"]) for item in findings)
    code_counts = Counter(str(item["code"]) for item in findings)
    return {
        "schema_version": 2,
        "source": source,
        "document_role": document_role,
        "disclaimer": "启发式结果仅用于定位候选问题，必须结合原文人工判断。",
        "summary": {
            "paragraphs_checked": len(paragraphs),
            "headings_checked": len(headings),
            "findings": len(findings),
            "severity_counts": dict(sorted(severity_counts.items())),
            "code_counts": dict(sorted(code_counts.items())),
            "bold_ratio": round(bold_ratio, 4),
        },
        "findings": findings,
    }


def format_text_report(result: dict[str, object]) -> str:
    summary = result["summary"]
    assert isinstance(summary, dict)
    lines = [
        f"Source: {result['source']}",
        f"Role: {result.get('document_role', 'formal')}",
        str(result["disclaimer"]),
        (
            "Checked: "
            f"{summary['paragraphs_checked']} paragraphs, "
            f"{summary['headings_checked']} headings; "
            f"{summary['findings']} findings."
        ),
    ]
    findings = result["findings"]
    assert isinstance(findings, list)
    for index, item in enumerate(findings, start=1):
        assert isinstance(item, dict)
        location_parts = []
        if "line" in item:
            location_parts.append(f"line {item['line']}")
        if "section" in item:
            location_parts.append(str(item["section"]))
        location = f" ({', '.join(location_parts)})" if location_parts else ""
        lines.append(
            f"{index}. [{str(item['severity']).upper()}] {item['code']}{location}: "
            f"{item['message']}"
        )
        if item.get("excerpt"):
            lines.append(f"   {item['excerpt']}")
    return "\n".join(lines)


def _should_fail(result: dict[str, object], threshold: str) -> bool:
    if threshold == "none":
        return False
    findings = result["findings"]
    assert isinstance(findings, list)
    if threshold == "error":
        return any(item.get("severity") == "error" for item in findings)
    return any(item.get("severity") in {"warning", "error"} for item in findings)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Heuristically audit a Markdown or plain-text research report."
    )
    parser.add_argument("report", type=Path, help="UTF-8 Markdown or text file")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--mode",
        choices=tuple(sorted(DOCUMENT_ROLES)),
        default="formal",
        help="formal audits reader-facing reports; internal-ledger permits work status and internal keys",
    )
    parser.add_argument(
        "--fail-on",
        choices=("none", "warning", "error"),
        default="none",
        help="set a non-zero exit code at or above this severity",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        text = args.report.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"audit_report: cannot read {args.report}: {exc}", file=sys.stderr)
        return 2

    result = audit_text(
        text, source=str(args.report.resolve()), document_role=args.mode
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(result))
    return 1 if _should_fail(result, args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
