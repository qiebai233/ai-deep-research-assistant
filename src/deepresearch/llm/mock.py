"""Deterministic offline language model used by the demo, tests and CI.

The mock understands the prompt contract (see ``CONTRACTS.md`` §7): the user
message starts with ``TASK: <name>`` (``plan``, ``findings``, ``outline``,
``section`` or ``meta``) followed by ``KEY: value`` blocks.  It parses the real
question, sub-question ids (``Q1``...), source ids (``S1``...) and the section
heading out of the prompt and answers with the exact JSON schema expected by the
agent layer, so an offline run produces a complete, citation-valid report.

Every answer is a pure function of the prompt text — no randomness, no mutable
state — which makes the offline output stable enough to assert in tests.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .base import LLMResponse, Message

__all__ = ["MockLLM"]

# --------------------------------------------------------------------------- #
# Prompt parsing (the contract is documented in CONTRACTS.md §7)
# --------------------------------------------------------------------------- #
_TASK_RE = re.compile(r"(?im)^[ \t]*TASK:[ \t]*([a-z][a-z_]*)[ \t]*$")
_SUB_QUESTION_RE = re.compile(
    r"(?im)^[ \t]*SUB_QUESTION:[ \t]*(Q\d+)[ \t]*[—–\-:：]?[ \t]*(.*?)[ \t]*$"
)
_SUB_QUESTION_LINE_RE = re.compile(r"(?im)^[ \t]*(Q\d+)[ \t]*\|[ \t]*(.+?)[ \t]*$")
_SOURCE_RE = re.compile(r"(?m)^[ \t]*\[(S\d+)\][ \t]*(.*?)[ \t]*$")
_QID_RE = re.compile(r"\bQ(\d+)\b")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_FIELD_TEMPLATE = r"(?im)^[ \t]*{name}:[ \t]*(.+?)[ \t]*$"

# --------------------------------------------------------------------------- #
# Deterministic content pools
# --------------------------------------------------------------------------- #
_ASPECTS: Tuple[Tuple[str, str, str, str, str, str], ...] = (
    (
        "{q}的核心背景、定义与当前现状是什么？",
        "What are the background, definitions and current status of {q}?",
        "背景 定义 现状 综述",
        "发展历程 关键节点 数据",
        "background definition status review",
        "history milestones data",
    ),
    (
        "{q}在 2025 年的最新进展与关键数据有哪些？",
        "What are the latest 2025 developments and key figures for {q}?",
        "最新进展 关键数据 2025",
        "规模 增速 权威 统计",
        "latest developments key data 2025",
        "market size growth official statistics",
    ),
    (
        "{q}涉及的主要技术路线、参与方与竞争格局如何？",
        "Which technology routes, players and competitive dynamics shape {q}?",
        "技术路线 参与方 竞争格局",
        "头部企业 市场份额 对比",
        "technology routes key players competition",
        "leading companies market share comparison",
    ),
    (
        "{q}存在哪些风险、争议与落地瓶颈？",
        "What risks, controversies and adoption bottlenecks affect {q}?",
        "风险 争议 落地 瓶颈",
        "成本 合规 失败案例",
        "risks controversies adoption bottlenecks",
        "cost compliance failure cases",
    ),
    (
        "{q}未来 2–3 年的趋势与可执行建议是什么？",
        "What trends and actionable recommendations apply to {q} over the next 2-3 years?",
        "趋势 展望 预测 建议",
        "路线图 投资 机会",
        "trends outlook forecast recommendations",
        "roadmap investment opportunities",
    ),
    (
        "{q}有哪些可验证的关键案例与实证数据？",
        "Which verifiable case studies and empirical data exist for {q}?",
        "案例 实证 数据 复盘",
        "试点 项目 效果评估",
        "case studies empirical data review",
        "pilot projects impact evaluation",
    ),
    (
        "与 {q} 相关的政策法规、标准与伦理问题有哪些？",
        "Which policies, standards and ethical issues relate to {q}?",
        "政策 法规 标准 伦理",
        "监管 合规 行业规范",
        "policy regulation standards ethics",
        "supervision compliance industry norms",
    ),
)

_ASPECT_NAMES_ZH = (
    "背景与现状",
    "最新进展与关键数据",
    "技术路线与竞争格局",
    "风险与瓶颈",
    "趋势与建议",
    "案例与实证",
    "政策与伦理",
)
_ASPECT_NAMES_EN = (
    "background and status",
    "latest developments and key data",
    "technology routes and competition",
    "risks and bottlenecks",
    "outlook and recommendations",
    "case studies and evidence",
    "policy and ethics",
)

_RATIONALE_ZH = (
    "拆解问题的背景维度，形成可交叉验证的背景信息。",
    "聚焦最新数据与统计口径，确保结论有数字支撑。",
    "识别主要技术路线与参与者，判断竞争格局。",
    "找出风险、争议与瓶颈，避免结论过度乐观。",
    "形成面向未来的趋势判断与可执行建议。",
    "寻找可复盘的案例与实证数据，补强证据链。",
    "梳理政策法规与伦理边界，保证结论合规。",
)
_RATIONALE_EN = (
    "Break down the background so later claims can be cross-checked.",
    "Focus on recent figures and definitions so conclusions carry numbers.",
    "Map the main technical routes and players to frame the competitive landscape.",
    "Surface risks, controversies and bottlenecks to avoid overly optimistic claims.",
    "Turn the evidence into an outlook and actionable recommendations.",
    "Find verifiable case studies that strengthen the evidence chain.",
    "Cover policy, standards and ethical boundaries for compliant conclusions.",
)

_SECTION_HEADINGS: Tuple[Tuple[str, str], ...] = (
    ("研究背景与问题界定", "Background and Problem Framing"),
    ("最新进展与关键数据", "Latest Developments and Key Data"),
    ("技术路线与主要参与方", "Technology Routes and Key Players"),
    ("风险、争议与瓶颈", "Risks, Controversies and Bottlenecks"),
    ("趋势展望与行动建议", "Outlook and Recommendations"),
    ("关键案例与实证", "Case Studies and Evidence"),
    ("政策法规与伦理", "Policy, Regulation and Ethics"),
)

_PERCENTS = (
    18.4,
    26.7,
    12.5,
    35.2,
    42.9,
    8.6,
    51.6,
    63.8,
    21.8,
    29.3,
    47.1,
    33.6,
    57.4,
    15.9,
)
_AMOUNTS = (
    "2,480",
    "5,120",
    "8,750",
    "12,360",
    "3,640",
    "19,800",
    "6,275",
    "24,500",
    "1,930",
    "31,700",
)
_YEARS = ("2023", "2024", "2025")
_SAMPLES = (48, 126, 215, 360, 480, 92, 174)


# --------------------------------------------------------------------------- #
# Public client
# --------------------------------------------------------------------------- #
class MockLLM:
    """A deterministic, network-free :class:`~deepresearch.llm.base.LLMClient`."""

    name = "mock"
    model = "mock-researcher"

    def __init__(self, latency_s: float = 0.0) -> None:
        self.latency_s = max(0.0, float(latency_s))

    def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Return the deterministic answer for the task encoded in ``messages``."""
        prompt = _prompt_text(messages)
        started = time.perf_counter()
        if self.latency_s:
            time.sleep(self.latency_s)
        task = _task(prompt)
        if task == "plan":
            payload: Any = _build_plan(prompt)
        elif task == "findings":
            payload = _build_findings(prompt)
        elif task == "outline":
            payload = _build_outline(prompt)
        elif task == "section":
            payload = _build_section(prompt)
        elif task == "meta":
            payload = _build_meta(prompt)
        else:
            payload = _fallback_text(prompt)
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        elapsed = time.perf_counter() - started
        return LLMResponse(
            text=text,
            model=self.model,
            prompt_tokens=max(1, len(prompt) // 4),
            completion_tokens=max(1, len(text) // 4),
            latency_s=round(elapsed, 4),
            finish_reason="stop",
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"MockLLM(latency_s={self.latency_s!r})"


# --------------------------------------------------------------------------- #
# Task builders
# --------------------------------------------------------------------------- #
def _build_plan(prompt: str) -> Dict[str, Any]:
    language = _language(prompt)
    question = _question(prompt)
    q_short = _short(question or _fallback_question(language), 60)
    _seed(prompt)
    limit = _int_field(prompt, "MAX_SUB_QUESTIONS", 5)
    count = max(1, min(limit, len(_ASPECTS)))
    queries_per_question = max(2, min(_int_field(prompt, "QUERIES_PER_QUESTION", 3), 4))
    sub_questions: List[Dict[str, Any]] = []
    for index in range(count):
        zh_question, en_question, zh_q1, zh_q2, en_q1, en_q2 = _ASPECTS[index]
        template = zh_question if language == "zh" else en_question
        text = template.format(q=q_short)
        base = question or q_short
        if language == "zh":
            rationale = _RATIONALE_ZH[index]
            candidates = [
                f"{base} {zh_q1}",
                f"{base} {zh_q2}",
                f"{q_short} 2025 数据 报告",
                f"{q_short} 深度 分析 综述",
            ]
        else:
            rationale = _RATIONALE_EN[index]
            candidates = [
                f"{base} {en_q1}",
                f"{base} {en_q2}",
                f"{q_short} 2025 data report",
                f"{q_short} in-depth analysis review",
            ]
        queries = _dedupe(candidates)[:queries_per_question]
        sub_questions.append(
            {
                "question": text,
                "rationale": rationale,
                "queries": queries,
                "priority": index + 1,
            }
        )
    if language == "zh":
        strategy = (
            "优先检索学术与官方来源，再用行业媒体交叉验证；"
            "重点关注 2024–2025 年的一手数据与统计口径。"
        )
    else:
        strategy = (
            "Start with academic and official sources, then cross-check with industry "
            "media, focusing on 2024-2025 primary data and definitions."
        )
    return {"search_strategy": strategy, "sub_questions": sub_questions}


def _build_findings(prompt: str) -> Dict[str, Any]:
    language = _language(prompt)
    question = _question(prompt)
    sources = _sources(prompt)
    sub_questions = _subquestions(prompt)
    if not sub_questions:
        fallback_question = question or _fallback_question(language)
        sub_questions = [("Q1", fallback_question)]
    if not sources:
        sources = [("S1", question or _fallback_source_title(language), "")]
    seed = _seed(prompt)
    findings: List[Dict[str, Any]] = []
    for index, (qid, qtext) in enumerate(sub_questions):
        subject = _short(_strip_punctuation(qtext or question or _fallback_question(language)), 60)
        finding_count = 2 if len(sources) >= 2 and index % 2 == 0 else 1
        for offset in range(finding_count):
            sid, title, _url = sources[(index + offset) % len(sources)]
            pct = _pick(_PERCENTS, seed, index * 5 + offset)
            pct2 = _pick(_PERCENTS, seed, index * 7 + offset + 3)
            amount = _pick(_AMOUNTS, seed, index * 3 + offset)
            year = _pick(_YEARS, seed, index + offset)
            sample = _pick(_SAMPLES, seed, index * 2 + offset)
            source_ids = [sid]
            if offset == 1 and len(sources) > 1:
                extra = sources[(index + offset + 1) % len(sources)][0]
                if extra not in source_ids:
                    source_ids.append(extra)
            if language == "en":
                if offset == 0:
                    claim = (
                        f"On {subject}, {title} reports that the relevant metric reached "
                        f"about {amount} million USD in {year}, up {pct}% year over year, "
                        "suggesting the field is still evolving quickly."
                    )
                else:
                    claim = (
                        f"Cross-source evidence suggests that progress on {subject} "
                        f"accelerated by roughly {pct2} percentage points in {year}, "
                        f"covering {sample} sampled cases with visible regional gaps."
                    )
                evidence = (
                    f"Source [{sid}] ({title}) states that {sample} objects were sampled "
                    f"between {year} and 2025, with a core growth rate of {pct}%."
                )
                caveats = (
                    "Only one public source was available; add cross-validation."
                    if len(sources) == 1
                    else "Figures come from public summaries; verify the original definitions."
                )
            else:
                if offset == 0:
                    claim = (
                        f"关于「{subject}」，{title} 指出 {year} 年相关指标约为 {amount} 亿元，"
                        f"同比增长 {pct}%，表明该方向仍处于快速演进阶段。"
                    )
                else:
                    claim = (
                        f"交叉证据表明，{subject}在 {year} 年的推进速度约提升 {pct2} 个百分点，"
                        f"覆盖样本 {sample} 个，区域与行业间差异明显。"
                    )
                evidence = (
                    f"来源 [{sid}]《{title}》的正文摘要提到：样本覆盖 {sample} 个对象，"
                    f"统计区间为 {year}–2025 年，核心指标增速为 {pct}%。"
                )
                caveats = (
                    "仅依赖单一公开来源，建议补充交叉验证。"
                    if len(sources) == 1
                    else "数据来自公开摘要，建议核对原始报告口径。"
                )
            confidence = round(
                0.62 + ((seed + index * 11 + offset * 7) % 27) / 100.0,
                2,
            )
            findings.append(
                {
                    "sub_question_id": qid,
                    "claim": claim,
                    "evidence": evidence,
                    "source_ids": source_ids,
                    "confidence": confidence,
                    "caveats": caveats,
                }
            )
    gap_qid, gap_text = sub_questions[-1]
    gap_subject = _short(
        _strip_punctuation(gap_text or question or _fallback_question(language)), 60
    )
    if language == "en":
        description = (
            f"Primary 2025 statistics about {gap_subject} are missing; current evidence "
            "relies on secondary coverage."
        )
        queries = [
            f"{question or gap_subject} 2025 official statistics",
            f"{question or gap_subject} primary data report",
        ]
    else:
        description = f"关于「{gap_subject}」缺少 2025 年的一手官方统计，现有证据以二手报道为主。"
        queries = [
            f"{question or gap_subject} 2025 官方 统计",
            f"{question or gap_subject} 一手 数据 报告",
        ]
    return {
        "findings": findings,
        "gaps": [
            {
                "sub_question_id": gap_qid,
                "description": description,
                "queries": queries,
            }
        ],
    }


def _build_outline(prompt: str) -> Dict[str, Any]:
    language = _language(prompt)
    question = _question(prompt)
    q_short = _short(question or _fallback_question(language), 60)
    sources = _sources(prompt)
    source_ids = [sid for sid, _title, _url in sources]
    sub_questions = _subquestions(prompt)
    by_id = {qid: text for qid, text in sub_questions}
    qids = _sort_qids(_qids(prompt))
    if not qids:
        qids = [qid for qid, _text in sub_questions]
    candidates = len(qids) if qids else min(5, len(_SECTION_HEADINGS))
    max_sections = _int_field(prompt, "MAX_SECTIONS", 0)
    if max_sections > 0:
        candidates = min(candidates, max_sections)
    section_count = max(1, candidates)
    seed = _seed(prompt)
    sections: List[Dict[str, Any]] = []
    for index in range(section_count):
        heading_zh, heading_en = _SECTION_HEADINGS[index % len(_SECTION_HEADINGS)]
        heading = heading_zh if language == "zh" else heading_en
        qid = qids[index] if index < len(qids) else ""
        subject = _strip_punctuation(by_id.get(qid, "") or question or _fallback_question(language))
        section_source_ids: List[str] = []
        if source_ids:
            picks = [
                source_ids[(2 * index) % len(source_ids)],
                source_ids[(2 * index + 1) % len(source_ids)],
            ]
            section_source_ids = _dedupe(picks)
        if language == "zh":
            cite = "".join(f"[{sid}]" for sid in section_source_ids) or "[S1]"
            brief = f"结合 {cite} 等来源，梳理「{_short(subject, 40)}」的证据与关键数据。"
        else:
            cite = "".join(f"[{sid}]" for sid in section_source_ids) or "[S1]"
            brief = (
                f"Use {cite} and related sources to review the evidence and key "
                f"figures on {_short(subject, 40)}."
            )
        sections.append(
            {
                "heading": heading,
                "brief": brief,
                "sub_question_ids": [qid] if qid else [],
                "source_ids": section_source_ids,
            }
        )
    n_sources = len(source_ids)
    if language == "zh":
        title = f"{q_short}：带引用的深度调研报告"
        source_phrase = f"{n_sources} 个来源" if n_sources else "公开资料"
        summary = (
            f"本报告基于 {source_phrase}、{len(sections)} 个章节，围绕「{q_short}」"
            "从背景、最新数据、参与方、风险与趋势等维度展开，并给出可执行建议。"
        )
    else:
        title = f"Deep Research Report: {q_short}"
        source_phrase = f"{n_sources} sources" if n_sources else "public sources"
        summary = (
            f"This report draws on {source_phrase} across {len(sections)} sections to examine "
            f"{q_short} from the angles of background, recent data, key players, risks and "
            "outlook, and closes with actionable recommendations."
        )
    year = _pick(_YEARS, seed, 0)
    pct = _pick(_PERCENTS, seed, 1)
    pct2 = _pick(_PERCENTS, seed, 2)
    if language == "zh":
        takeaways = [
            f"关键指标在 {year} 年同比增长约 {pct}%，整体仍处于扩张区间。",
            f"技术路线分化明显，约 {pct2}% 的样本选择主流方案，其余押注替代路线。",
            "未来 2–3 年需重点跟踪政策口径与一手数据，避免单一来源偏差。",
        ]
    else:
        takeaways = [
            f"The key metric grew about {pct}% year over year in {year}, so the field is "
            "still expanding.",
            f"Technology routes diverge: about {pct2}% of samples favour the mainstream "
            "approach while others bet on alternatives.",
            "Track policy definitions and primary data over the next 2-3 years to avoid "
            "single-source bias.",
        ]
    return {
        "title": title,
        "summary": summary,
        "key_takeaways": takeaways,
        "sections": sections,
    }


def _build_section(prompt: str) -> Dict[str, Any]:
    language = _language(prompt)
    question = _question(prompt)
    heading = _field(prompt, "SECTION") or ("核心分析" if language == "zh" else "Core analysis")
    brief = _field(prompt, "BRIEF")
    sources = _sources(prompt)
    ids = [sid for sid, _title, _url in sources] or ["S1"]
    seed = _seed(prompt)
    first = ids[0]
    second = ids[1] if len(ids) > 1 else first
    third = ids[2] if len(ids) > 2 else first
    pct = _pick(_PERCENTS, seed, 0)
    pct2 = _pick(_PERCENTS, seed, 4)
    pct3 = _pick(_PERCENTS, seed, 7)
    amount = _pick(_AMOUNTS, seed, 1)
    year = _pick(_YEARS, seed, 2)
    subject = _short(_strip_punctuation(question or _fallback_question(language)), 50)
    if language == "zh":
        opening = (
            f"围绕「{heading}」，本报告综合了 {len(ids)} 个来源的公开信息。"
            f"核心判断是：{subject}的推进由政策、技术与需求三条主线共同驱动 [{first}]。"
            f"{year} 年相关指标达到 {amount} 亿元量级，同比增长约 {pct}% [{second}]。"
        )
        if brief and brief != "-":
            opening = f"本节聚焦：{_short(brief, 60)}\n\n" + opening
        bullets = (
            f"- 需求侧：约 {pct2}% 的受访者计划在未来 12 个月内增加投入 [{third}]。\n"
            f"- 供给侧：前五名厂商合计份额约 {pct3}%，集中度持续提升 [{first}]。\n"
            f"- 风险侧：数据口径不统一与落地成本偏高是主要制约 [{second}]。"
        )
        closing = (
            f"上述结论分别得到 [{first}] 与 [{second}] 的支持，但部分数字来自公开摘要，"
            f"统计区间与样本定义可能存在差异，引用时应保留原始口径。不同来源对同一指标的"
            f"统计范围也不完全一致，正文只采用可交叉验证的区间。后续章节将继续用一手数据"
            f"校准结论，并与其它维度交叉验证 [{third}]。"
        )
        body = "\n\n".join([opening, bullets, closing])
    else:
        opening = (
            f"This section examines {heading}. Drawing on {len(ids)} sources, the central "
            f"finding is that {subject} is driven by policy, technology and demand [{first}]. "
            f"In {year} the relevant indicator reached roughly {amount} million USD, up about "
            f"{pct}% year over year [{second}]."
        )
        if brief and brief != "-":
            opening = f"Focus: {_short(brief, 60)}\n\n" + opening
        bullets = (
            f"- Demand: about {pct2}% of respondents plan to increase investment within "
            f"12 months [{third}].\n"
            f"- Supply: the top five players now hold roughly {pct3}% of the market [{first}].\n"
            f"- Risk: inconsistent definitions and high deployment costs remain the main "
            f"constraints [{second}]."
        )
        closing = (
            f"The conclusions above are supported by [{first}] and [{second}], but some figures "
            "come from public summaries; definitions should be checked against the original "
            f"reports. Later sections will re-calibrate them with primary data [{third}]."
        )
        body = "\n\n".join([opening, bullets, closing])
    return {"heading": heading, "body_md": body}


def _build_meta(prompt: str) -> Dict[str, Any]:
    language = _language(prompt)
    question = _question(prompt)
    q_short = _short(question or _fallback_question(language), 50)
    sources = _sources(prompt)
    headings = _headings(prompt)
    seed = _seed(prompt)
    year = _pick(_YEARS, seed, 0)
    pct = _pick(_PERCENTS, seed, 1)
    pct2 = _pick(_PERCENTS, seed, 3)
    if language == "zh":
        title = f"深度研究报告：{q_short}"
        source_phrase = f"{len(sources)} 个来源" if sources else "公开资料"
        heading_hint = (
            f"章节包括：{'、'.join(headings[:3])}。" if headings else "报告从多个维度展开。"
        )
        summary = (
            f"本报告围绕「{q_short}」展开，基于 {source_phrase}梳理了背景、最新进展、"
            f"主要参与方、风险与趋势。{heading_hint}总体上，该主题仍处于快速演进阶段，"
            "结论需结合一手数据持续校准。"
        )
        takeaways = [
            f"关键指标在 {year} 年同比增长约 {pct}%，行业景气度仍在上行。",
            f"约 {pct2}% 的样本集中在主流技术路线，替代路线仍待验证。",
            "政策口径与统计定义是影响结论的主要不确定性来源。",
            "建议用一手报告对核心数字做二次核对后再引用。",
        ]
        limitations = [
            "部分来源为二手报道或摘要，关键数字建议回到原始报告核对口径。",
            "受检索时间窗口与来源覆盖限制，可能遗漏最新的一手数据。",
            "本报告由自动化流程生成，不构成投资、医疗或法律建议。",
        ]
    else:
        title = f"Deep Research Report: {q_short}"
        source_phrase = f"{len(sources)} sources" if sources else "public sources"
        heading_hint = (
            f"Sections include: {', '.join(headings[:3])}. "
            if headings
            else "The report is organised across several dimensions. "
        )
        summary = (
            f"This report examines {q_short} using {source_phrase}, covering background, "
            f"recent developments, key players, risks and outlook. {heading_hint}"
            "The topic is still evolving quickly, so conclusions should be re-calibrated "
            "against primary data."
        )
        takeaways = [
            f"The key metric grew about {pct}% year over year in {year}, indicating an "
            "upward cycle.",
            f"About {pct2}% of samples cluster around the mainstream technology route; "
            "alternatives remain unproven.",
            "Policy definitions and statistical methods are the main source of uncertainty.",
            "Cross-check headline numbers against primary reports before citing them.",
        ]
        limitations = [
            "Some sources are secondary reports or summaries; verify key figures against "
            "the original publications.",
            "The retrieval window and source coverage are limited, so newer primary data "
            "may be missing.",
            "This report is generated automatically and is not investment, medical or "
            "legal advice.",
        ]
    return {
        "title": title,
        "summary": summary,
        "key_takeaways": takeaways,
        "limitations": limitations,
    }


def _fallback_text(prompt: str) -> str:
    language = _language(prompt)
    if language == "en":
        return (
            "This is the offline MockLLM. It only produces structured output for prompts "
            "that start with 'TASK: plan|findings|outline|section|meta'. No recognised task "
            "marker was found in this prompt, so no JSON was generated."
        )
    return (
        "这是离线 MockLLM。它只对以 `TASK: plan|findings|outline|section|meta` 开头的"
        "结构化请求返回 JSON；当前提示词中没有可识别的任务标记，因此未生成结构化内容。"
    )


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def _prompt_text(messages: Sequence[Message]) -> str:
    user_parts = [
        str(getattr(message, "content", "") or "")
        for message in messages
        if str(getattr(message, "role", "")) == "user"
    ]
    text = "\n\n".join(part for part in user_parts if part)
    if not text:
        text = "\n\n".join(str(getattr(m, "content", "") or "") for m in messages)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _task(prompt: str) -> str:
    match = _TASK_RE.search(prompt)
    return match.group(1).lower() if match else ""


def _field(prompt: str, name: str) -> str:
    match = re.search(_FIELD_TEMPLATE.format(name=re.escape(name)), prompt)
    return match.group(1).strip() if match else ""


def _int_field(prompt: str, name: str, default: int) -> int:
    raw = _field(prompt, name)
    try:
        return max(1, int(raw)) if raw else default
    except ValueError:
        return default


def _question(prompt: str) -> str:
    return _short(_field(prompt, "QUESTION").replace("\n", " ").strip(), 200)


def _language(prompt: str) -> str:
    declared = _field(prompt, "LANGUAGE").strip().lower()
    if declared.startswith("en"):
        return "en"
    if declared.startswith("zh"):
        return "zh"
    return "en" if not _CJK_RE.search(prompt) else "zh"


def _sources(prompt: str) -> List[Tuple[str, str, str]]:
    """Parse ``[S1] title | url`` lines, tolerating missing titles/URLs."""
    sources: List[Tuple[str, str, str]] = []
    seen: set[str] = set()
    for match in _SOURCE_RE.finditer(prompt):
        sid = match.group(1).upper()
        if sid in seen:
            continue
        seen.add(sid)
        rest = match.group(2).strip()
        title, url = rest, ""
        if "|" in rest:
            head, _, tail = rest.partition("|")
            title, url = head.strip(), tail.strip()
        elif re.search(r"https?://\S+$", rest):
            match_url = re.search(r"(.*?)\s+[-–—]\s+(https?://\S+)$", rest)
            if match_url:
                title, url = match_url.group(1).strip(), match_url.group(2).strip()
        title = title.strip(" -–—|") or sid
        sources.append((sid, _short(title, 120), url))
    return sources


def _subquestions(prompt: str) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    seen: set[str] = set()
    for match in _SUB_QUESTION_RE.finditer(prompt):
        qid = match.group(1).upper()
        if qid in seen:
            continue
        seen.add(qid)
        found.append((qid, _short(match.group(2).strip(), 200)))
    block = re.search(
        r"(?im)^[ \t]*SUB_QUESTIONS:[ \t]*\n((?:[ \t]*Q\d+[ \t]*\|.*(?:\n|$))+)",
        prompt,
    )
    if block:
        for line in block.group(1).splitlines():
            match = _SUB_QUESTION_LINE_RE.match(line)
            if match is None:
                continue
            qid = match.group(1).upper()
            if qid in seen:
                continue
            seen.add(qid)
            found.append((qid, _short(match.group(2).strip(), 200)))
    return found


def _qids(prompt: str) -> List[str]:
    found: List[str] = []
    for match in _QID_RE.finditer(prompt):
        qid = f"Q{int(match.group(1))}"
        if qid not in found:
            found.append(qid)
    return found


def _sort_qids(qids: Sequence[str]) -> List[str]:
    return sorted(dict.fromkeys(qids), key=lambda qid: int(qid[1:]))


def _headings(prompt: str) -> List[str]:
    headings: List[str] = []
    block = re.search(
        r"(?im)^[ \t]*SECTIONS:[ \t]*\n"
        r"((?:(?:[ \t]*\d+\.[ \t]+|[ \t]*[-*][ \t]+).*(?:\n|$))+)",
        prompt,
    )
    if block:
        for line in block.group(1).splitlines():
            heading = re.sub(r"^[ \t]*(?:\d+\.|[-*])[ \t]+", "", line).strip()
            if heading and not heading.startswith("("):
                headings.append(heading)
    patterns = (
        r"(?im)^[ \t]*SECTION:[ \t]*(.+?)[ \t]*$",
        r"(?m)^[ \t]*#{2,3}[ \t]+(.+?)[ \t]*$",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, prompt):
            heading = match.group(1).strip()
            if heading:
                headings.append(heading)
    return _dedupe(headings)[:10]


def _dedupe(values: Sequence[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _seed(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def _pick(pool: Sequence[Any], seed: int, offset: int) -> Any:
    return pool[(seed + offset) % len(pool)]


def _short(text: str, limit: int = 60) -> str:
    collapsed = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _strip_punctuation(text: str) -> str:
    return re.sub(r"[\s？?。.!！:：;；]+$", "", str(text or "").strip())


def _fallback_question(language: str) -> str:
    return "该研究问题" if language == "zh" else "the research topic"


def _fallback_source_title(language: str) -> str:
    return "公开资料" if language == "zh" else "public source"
