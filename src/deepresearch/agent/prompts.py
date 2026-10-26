"""Prompt construction for every agent stage.

Cross-team contract (see ``CONTRACTS.md`` section 7) — the ``user`` message of
every prompt starts with ``TASK: <name>`` followed by ``KEY: value`` blocks.
``MockLLM`` relies on those markers to stay deterministic, and real providers
rely on the system message to enforce "JSON only" and ``[S#]`` citations.

The functions here are pure: they never touch providers and never mutate the
objects they receive.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from ..llm.base import Message
from ..models import Finding, OutlineItem, Source, SubQuestion

__all__ = [
    "findings_messages",
    "meta_messages",
    "outline_messages",
    "plan_messages",
    "section_messages",
    "system_message",
]

TASK_PLAN = "plan"
TASK_FINDINGS = "findings"
TASK_OUTLINE = "outline"
TASK_SECTION = "section"
TASK_META = "meta"

MAX_EXCERPT_CHARS = 900

_SCHEMAS = {
    TASK_PLAN: (
        '{"search_strategy": "string", "sub_questions": [{"question": "string", '
        '"rationale": "string", "queries": ["string"], "priority": 1}]}'
    ),
    TASK_FINDINGS: (
        '{"findings": [{"sub_question_id": "Q1", "claim": "string", "evidence": "string", '
        '"source_ids": ["S1"], "confidence": 0.8, "caveats": "string"}], '
        '"gaps": [{"sub_question_id": "Q1", "description": "string", "queries": ["string"]}]}'
    ),
    TASK_OUTLINE: (
        '{"title": "string", "summary": "string", "key_takeaways": ["string"], '
        '"sections": [{"heading": "string", "brief": "string", '
        '"sub_question_ids": ["Q1"], "source_ids": ["S1"]}]}'
    ),
    TASK_SECTION: '{"heading": "string", "body_md": "string"}',
    TASK_META: (
        '{"title": "string", "summary": "string", "key_takeaways": ["string"], '
        '"limitations": ["string"]}'
    ),
}

_TASK_RULES = {
    TASK_PLAN: {
        "zh": "把研究问题拆解为不超过 MAX_SUB_QUESTIONS 个子问题，"
        "每个子问题给出 2–4 条检索 query，priority 数字越小越优先。",
        "en": "Decompose the question into at most MAX_SUB_QUESTIONS sub-questions; "
        "give 2-4 search queries each; lower priority numbers come first.",
    },
    TASK_FINDINGS: {
        "zh": "提炼 1–3 条可验证、带引用的发现；source_ids 只能取自 SOURCES；"
        "证据不足时在 gaps 中给出补检建议。",
        "en": "Extract 1-3 verifiable cited findings; source_ids must come from SOURCES; "
        "report evidence gaps with follow-up queries.",
    },
    TASK_OUTLINE: {
        "zh": "规划 3–6 个逻辑递进的章节，标题具体，覆盖全部子问题；title/summary/"
        "key_takeaways 面向最终报告。",
        "en": "Design 3-6 logically ordered sections with specific headings covering every "
        "sub-question; title/summary/key_takeaways target the final report.",
    },
    TASK_SECTION: {
        "zh": "只写本节正文（Markdown，不要重复章节标题），段落之间空行，"
        "必须使用 [S#] 引用给定来源，不要编造数据。",
        "en": "Write only this section's body (Markdown, no repeated heading), separate "
        "paragraphs with blank lines, cite given sources as [S#], never invent data.",
    },
    TASK_META: {
        "zh": "生成最终报告的标题、摘要、关键要点与局限说明。",
        "en": "Produce the final report title, summary, key takeaways and limitations.",
    },
}

_SYSTEM_ZH = """你是一位资深研究员，擅长把开放问题拆解为可验证的子问题，并严格依据给定资料写作。

硬性规则：
1. 只输出一个合法 JSON 对象；不要输出解释文字，不要用 Markdown 代码块包裹。
2. 引用来源时必须使用给定的 [S#] 编号（例如 [S1]、[S3]），严禁编造未给出的来源或链接。
3. 不确定或资料不足的内容必须明确说明，绝不虚构数据、时间与引用。
4. 报告语言：简体中文。
5. JSON 结构必须严格为：{schema}
6. 本阶段要求：{rule}"""

_SYSTEM_EN = """You are a senior research analyst who decomposes open questions into \
verifiable sub-questions and writes strictly from the supplied sources.

Hard rules:
1. Output exactly one valid JSON object; no prose, no Markdown code fences.
2. Cite sources only with the given [S#] ids (e.g. [S1], [S3]); never invent sources or URLs.
3. State uncertainty explicitly; never fabricate data, dates or citations.
4. Report language: English.
5. The JSON schema must be exactly: {schema}
6. This stage: {rule}"""


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def _inline(text: object, limit: int = 400) -> str:
    """Collapse any text to a single bounded line."""
    value = " ".join(str(text or "").split())
    if len(value) > limit:
        value = value[: limit - 1].rstrip() + "…"
    return value


def _language(language: str) -> str:
    return "en" if str(language or "zh").lower().startswith("en") else "zh"


def system_message(task: str, language: str = "zh") -> Message:
    """Build the system message enforcing the research-analyst persona."""
    lang = _language(language)
    rule = _TASK_RULES.get(task, {}).get(lang, "")
    template = _SYSTEM_ZH if lang == "zh" else _SYSTEM_EN
    schema = _SCHEMAS.get(task, "{}")
    return Message(role="system", content=template.format(schema=schema, rule=rule))


def _header(task: str, language: str, question: str) -> List[str]:
    return [
        f"TASK: {task}",
        f"LANGUAGE: {_language(language)}",
        f"QUESTION: {_inline(question, 1200)}",
    ]


def _source_block(
    sources: Sequence[Source],
    *,
    max_sources: int = 6,
    excerpt_chars: int = MAX_EXCERPT_CHARS,
) -> List[str]:
    """``SOURCES:`` block; MockLLM parses the ``[S#]`` ids from these lines."""
    lines = ["SOURCES:"]
    for source in list(sources)[:max_sources]:
        title = _inline(source.title or source.url, 160)
        lines.append(f"[{source.id}] {title} | {source.url}")
        excerpt = source.excerpt(excerpt_chars)
        if excerpt:
            lines.append(excerpt)
    if len(lines) == 1:
        lines.append("(no sources available)")
    return lines


def _finding_block(findings: Sequence[Finding], *, limit: int = 12) -> List[str]:
    lines = ["FINDINGS:"]
    for finding in list(findings)[:limit]:
        markers = finding.citation_marker()
        claim = _inline(finding.claim, 300)
        lines.append(f"[{finding.id}] {finding.sub_question_id} | {claim} {markers}".rstrip())
    if len(lines) == 1:
        lines.append("(no findings yet)")
    return lines


def _outline_block(outline: Sequence[OutlineItem]) -> List[str]:
    lines = ["OUTLINE:"]
    for index, item in enumerate(outline, 1):
        lines.append(f"{index}. {_inline(item.heading, 120)}")
    if len(lines) == 1:
        lines.append("(no outline yet)")
    return lines


# --------------------------------------------------------------------------- #
# Stage prompts
# --------------------------------------------------------------------------- #
def plan_messages(
    question: str,
    *,
    language: str = "zh",
    depth: str = "standard",
    max_sub_questions: int = 5,
    queries_per_question: int = 3,
) -> List[Message]:
    """Prompt asking the planner for ``TASK: plan`` JSON."""
    lines = _header(TASK_PLAN, language, question)
    lines.extend(
        [
            f"DEPTH: {depth}",
            f"MAX_SUB_QUESTIONS: {max_sub_questions}",
            f"QUERIES_PER_QUESTION: {queries_per_question}",
            "INSTRUCTIONS: 返回 JSON，字段为 search_strategy 与 sub_questions；"
            "sub_questions 保持 1..n 顺序。",
        ]
    )
    return [system_message(TASK_PLAN, language), Message(role="user", content="\n".join(lines))]


def findings_messages(
    question: str,
    sub_question: SubQuestion,
    sources: Sequence[Source],
    *,
    language: str = "zh",
    round_index: int = 1,
    max_sources: int = 6,
) -> List[Message]:
    """Prompt asking for ``TASK: findings`` JSON for one sub-question."""
    lines = _header(TASK_FINDINGS, language, question)
    lines.extend(
        [
            f"ROUND: {round_index}",
            f"SUB_QUESTION: {sub_question.id} — {_inline(sub_question.question, 300)}",
        ]
    )
    if sub_question.rationale:
        lines.append(f"RATIONALE: {_inline(sub_question.rationale, 200)}")
    lines.extend(_source_block(sources, max_sources=max_sources))
    lines.append(
        "INSTRUCTIONS: sub_question_id 必须是 "
        f"{sub_question.id}；source_ids 只能从上面的 SOURCES 中选取；confidence 为 0–1 的小数。"
        if _language(language) == "zh"
        else f"INSTRUCTIONS: sub_question_id must be {sub_question.id}; source_ids must be "
        "chosen from SOURCES above; confidence is a float in 0-1."
    )
    return [system_message(TASK_FINDINGS, language), Message(role="user", content="\n".join(lines))]


def outline_messages(
    question: str,
    sources: Sequence[Source],
    findings: Sequence[Finding],
    *,
    language: str = "zh",
    max_sections: int = 5,
    sub_questions: Sequence[SubQuestion] = (),
) -> List[Message]:
    """Prompt asking for ``TASK: outline`` JSON."""
    lines = _header(TASK_OUTLINE, language, question)
    lines.append(f"MAX_SECTIONS: {max_sections}")
    if sub_questions:
        lines.append("SUB_QUESTIONS:")
        for sub_question in list(sub_questions)[:max_sections]:
            lines.append(f"{sub_question.id} | {_inline(sub_question.question, 200)}")
    lines.extend(_source_block(sources, max_sources=max(len(sources), 1)))
    lines.extend(_finding_block(findings))
    return [system_message(TASK_OUTLINE, language), Message(role="user", content="\n".join(lines))]


def section_messages(
    question: str,
    heading: str,
    brief: str,
    sources: Sequence[Source],
    findings: Sequence[Finding],
    outline: Sequence[OutlineItem],
    *,
    language: str = "zh",
    target_words: int = 320,
    max_sources: int = 8,
) -> List[Message]:
    """Prompt asking for ``TASK: section`` JSON (one report section)."""
    lines = _header(TASK_SECTION, language, question)
    lines.extend(
        [
            f"SECTION: {_inline(heading, 160)}",
            f"BRIEF: {_inline(brief, 320) or '-'}",
            f"TARGET_WORDS: {target_words}",
        ]
    )
    lines.extend(_outline_block(outline))
    lines.extend(_source_block(sources, max_sources=max_sources))
    lines.extend(_finding_block(findings))
    return [system_message(TASK_SECTION, language), Message(role="user", content="\n".join(lines))]


def meta_messages(
    question: str,
    sources: Sequence[Source],
    sections: Sequence[object],
    *,
    language: str = "zh",
    outline: Optional[Sequence[OutlineItem]] = None,
    findings: Sequence[Finding] = (),
) -> List[Message]:
    """Prompt asking for ``TASK: meta`` JSON (title / summary / takeaways / limits)."""
    lines = _header(TASK_META, language, question)
    lines.append("SECTIONS:")
    section_count = 0
    for index, section in enumerate(sections or (), 1):
        heading = getattr(section, "heading", section)
        lines.append(f"{index}. {_inline(heading, 140)}")
        section_count += 1
    if not section_count:
        lines.append("(no sections yet)")
    if outline:
        lines.extend(_outline_block(outline))
    lines.extend(_source_block(sources, max_sources=max(len(sources), 1)))
    if findings:
        lines.extend(_finding_block(findings))
    return [system_message(TASK_META, language), Message(role="user", content="\n".join(lines))]
