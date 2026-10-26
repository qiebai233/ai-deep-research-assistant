"""Writer: outline -> per-section prose -> report metadata.

The writer is deliberately defensive: every LLM call may return ``None`` (budget
exhausted / invalid JSON / provider error) and the stage still produces a
deterministic, citation-clean section from the findings gathered so far.  All
``[S#]`` markers are validated against the sources that actually exist, and
``ReportSection.source_ids`` records the ids in the order they appear in the
body.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from ..models import (
    Finding,
    OutlineItem,
    Report,
    ReportSection,
    ResearchState,
    Source,
    UsageStats,
)
from . import prompts
from .caller import LlmCaller

__all__ = ["Writer"]

_CITE_RE = re.compile(r"\[(S\d+)\]")
_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*|\s*```$")


def _language(value: str) -> str:
    return "en" if str(value or "zh").lower().startswith("en") else "zh"


def _as_text(value: Any, limit: int = 400) -> str:
    return " ".join(str(value or "").split())[:limit]


def _as_str_list(value: Any, *, limit: int = 240) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    result: List[str] = []
    for item in value:
        text = _as_text(item, limit)
        if text and text not in result:
            result.append(text)
    return result


def _citation_ids(body: str) -> List[str]:
    """Unique citation ids in order of first appearance."""
    ids: List[str] = []
    for source_id in _CITE_RE.findall(body or ""):
        if source_id not in ids:
            ids.append(source_id)
    return ids


def _sanitize_citations(body: str, valid_ids: Sequence[str]) -> str:
    """Drop citations to non-existent sources and collapse duplicate markers."""
    valid = set(valid_ids)

    def _replace(match: re.Match[str]) -> str:
        return match.group(0) if match.group(1) in valid else ""

    text = _CITE_RE.sub(_replace, body or "")
    # ``[S1][S1]`` -> ``[S1]`` and stray double spaces left behind.
    text = re.sub(r"(\[S\d+\])(?:\s*\1)+", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def _clean_body(body: str, heading: str) -> str:
    """Strip fences and a duplicated leading heading from model output."""
    text = _FENCE_RE.sub("", (body or "").strip()).strip()
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and _MD_HEADING_RE.match(lines[0]):
        title = _as_text(lines[0].lstrip("# "), 160).casefold()
        if not heading or title == _as_text(heading, 160).casefold():
            lines = lines[1:]
    return "\n".join(lines).strip()


def _first_sentence(text: str, limit: int = 220) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return ""
    match = re.search(r"[^。！？.!?]{8,}[。！？.!?]", cleaned)
    return (match.group(0) if match else cleaned)[:limit]


def _short_heading(question: str, limit: int = 42) -> str:
    text = " ".join(str(question or "").split()).rstrip("？?。.!！:：")
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text or "本章"


class Writer:
    """Turns a :class:`ResearchState` into ``ReportSection`` objects and a report."""

    def __init__(
        self,
        llm: Any,
        settings: Any,
        *,
        caller: Optional[LlmCaller] = None,
        language: Optional[str] = None,
    ) -> None:
        self.llm = llm
        self.settings = settings
        self.language = _language(language or settings.language)
        self.caller = caller if caller is not None else LlmCaller(llm, settings)
        self.profile = settings.profile()
        self._outline_meta: Dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # Outline
    # ------------------------------------------------------------------ #
    def build_outline(self, state: ResearchState) -> List[OutlineItem]:
        """Return the report outline, falling back to one section per sub-question."""
        max_sections = max(
            1, min(int(self.profile.max_sub_questions), max(1, len(state.plan.sub_questions)))
        )
        messages = prompts.outline_messages(
            state.plan.question,
            state.ok_sources()[: int(self.profile.max_sources)],
            state.findings[: int(self.profile.max_findings)],
            language=self.language,
            max_sections=max_sections,
            sub_questions=state.plan.sub_questions,
        )
        data = self.caller.complete_json(messages, label="outline")
        payload = data if isinstance(data, dict) else {}
        items = self._parse_outline_items(state, payload, max_sections)
        if not items:
            items = self._heuristic_outline(state, max_sections)
        title = _as_text(payload.get("title"), 140) or state.plan.question
        summary = _as_text(payload.get("summary"), 1200) or self._heuristic_summary(state)
        takeaways = _as_str_list(payload.get("key_takeaways"))[:6] or self._heuristic_takeaways(
            state
        )
        self._outline_meta = {"title": title, "summary": summary, "key_takeaways": takeaways}
        return items

    def _parse_outline_items(
        self, state: ResearchState, payload: Dict[str, Any], max_sections: int
    ) -> List[OutlineItem]:
        raw = payload.get("sections")
        if not isinstance(raw, (list, tuple)):
            return []
        valid_sq = {sub_question.id for sub_question in state.plan.sub_questions}
        valid_source_ids = {source.id for source in state.ok_sources()}
        items: List[OutlineItem] = []
        seen: set[str] = set()
        for entry in raw:
            if len(items) >= max_sections:
                break
            if not isinstance(entry, dict):
                continue
            heading = _as_text(entry.get("heading"), 160)
            if not heading or heading.casefold() in seen:
                continue
            seen.add(heading.casefold())
            items.append(
                OutlineItem(
                    heading=heading,
                    brief=_as_text(entry.get("brief"), 400),
                    sub_question_ids=[
                        sid
                        for sid in _as_str_list(entry.get("sub_question_ids"), limit=20)
                        if sid in valid_sq
                    ],
                    source_ids=[
                        sid
                        for sid in _as_str_list(entry.get("source_ids"), limit=20)
                        if sid in valid_source_ids
                    ],
                )
            )
        return items

    def _heuristic_outline(self, state: ResearchState, max_sections: int) -> List[OutlineItem]:
        ordered = sorted(
            enumerate(state.plan.sub_questions), key=lambda item: (item[1].priority, item[0])
        )
        items: List[OutlineItem] = []
        for _, sub_question in ordered[:max_sections]:
            source_ids: List[str] = []
            for finding in state.finding_for(sub_question.id):
                for source_id in finding.source_ids:
                    if source_id not in source_ids:
                        source_ids.append(source_id)
            items.append(
                OutlineItem(
                    heading=_short_heading(sub_question.question),
                    brief=sub_question.rationale
                    or self._msg(
                        f"回答子问题 {sub_question.id}",
                        f"Answer sub-question {sub_question.id}",
                    ),
                    sub_question_ids=[sub_question.id],
                    source_ids=source_ids[:4],
                )
            )
        return items

    # ------------------------------------------------------------------ #
    # Sections
    # ------------------------------------------------------------------ #
    def write_section(
        self,
        state: ResearchState,
        item: OutlineItem,
        *,
        index: int = 0,
        outline: Optional[Sequence[OutlineItem]] = None,
    ) -> ReportSection:
        """Write one report section with validated ``[S#]`` citations."""
        sources = self._section_sources(state, item)
        findings = self._section_findings(state, item, sources)
        messages = prompts.section_messages(
            state.plan.question,
            item.heading,
            item.brief,
            sources,
            findings,
            outline if outline is not None else state.outline,
            language=self.language,
            target_words=int(self.profile.section_words),
            max_sources=8,
        )
        data = self.caller.complete_json(messages, label=f"section:{index + 1}")
        payload = data if isinstance(data, dict) else {}
        heading = _as_text(payload.get("heading"), 160) or item.heading
        body = _clean_body(str(payload.get("body_md") or payload.get("body") or ""), heading)
        valid_ids = [source.id for source in state.ok_sources()]
        if not body:
            body = self._heuristic_body(state, item, sources, findings)
        body = _sanitize_citations(body, valid_ids)
        citations = _citation_ids(body)
        if not citations and sources:
            marker = "".join(f"[{source.id}]" for source in sources[:3])
            body = f"{body}\n\n{self._msg('参考：', 'Sources: ')}{marker}".strip()
            citations = _citation_ids(body)
        return ReportSection(
            heading=heading or item.heading,
            level=2,
            body=body,
            source_ids=citations,
        )

    def _section_sources(self, state: ResearchState, item: OutlineItem) -> List[Source]:
        by_id = {source.id: source for source in state.ok_sources()}
        chosen: List[Source] = []
        for source_id in item.source_ids:
            source = by_id.get(source_id)
            if source is not None and source not in chosen:
                chosen.append(source)
        if not chosen:
            wanted = set(item.sub_question_ids)
            for finding in state.findings:
                if wanted and finding.sub_question_id not in wanted:
                    continue
                for source_id in finding.source_ids:
                    source = by_id.get(source_id)
                    if source is not None and source not in chosen:
                        chosen.append(source)
        if not chosen:
            chosen = state.ok_sources()[:5]
        return chosen[:8]

    def _section_findings(
        self, state: ResearchState, item: OutlineItem, sources: Sequence[Source]
    ) -> List[Finding]:
        wanted = set(item.sub_question_ids)
        source_ids = {source.id for source in sources}
        selected: List[Finding] = []
        for finding in state.findings:
            has_sub_question = not wanted or finding.sub_question_id in wanted
            shares_source = bool(set(finding.source_ids) & source_ids)
            if has_sub_question or shares_source:
                selected.append(finding)
        if not selected:
            selected = list(state.findings)
        return selected[:8]

    def _heuristic_body(
        self,
        state: ResearchState,
        item: OutlineItem,
        sources: Sequence[Source],
        findings: Sequence[Finding],
    ) -> str:
        del state, item  # kept for a uniform signature
        if findings:
            paragraphs: List[str] = []
            for finding in list(findings)[:4]:
                claim = finding.claim.strip()
                if claim and claim[-1] not in "。！？.!?":
                    claim += "。"
                paragraph = f"{claim}{finding.citation_marker()}".strip()
                if finding.evidence:
                    paragraph = f"{paragraph} {finding.evidence}".strip()
                paragraphs.append(paragraph)
            return "\n\n".join(paragraphs)
        if sources:
            paragraphs = []
            for source in list(sources)[:3]:
                snippet = _first_sentence(source.excerpt(240)) or source.title or source.url
                paragraphs.append(
                    self._msg(
                        f"《{source.title or source.domain}》指出：{snippet} [{source.id}]",
                        f"{source.title or source.domain} reports: {snippet} [{source.id}]",
                    )
                )
            return "\n\n".join(paragraphs)
        return self._msg(
            "本节暂无可用外部证据。", "No external evidence was gathered for this section."
        )

    # ------------------------------------------------------------------ #
    # Metadata & report
    # ------------------------------------------------------------------ #
    def build_meta(self, state: ResearchState, sections: Sequence[ReportSection]) -> Dict[str, Any]:
        """Build title/summary/takeaways/limitations with outline-based fallbacks."""
        messages = prompts.meta_messages(
            state.plan.question,
            state.ok_sources()[: int(self.profile.max_sources)],
            sections,
            language=self.language,
            outline=state.outline,
            findings=state.findings[: int(self.profile.max_findings)],
        )
        data = self.caller.complete_json(messages, label="meta")
        payload = data if isinstance(data, dict) else {}
        outline = self._outline_meta
        return {
            "title": _as_text(payload.get("title"), 140)
            or _as_text(outline.get("title"), 140)
            or state.plan.question,
            "summary": _as_text(payload.get("summary"), 1200)
            or _as_text(outline.get("summary"), 1200)
            or self._heuristic_summary(state),
            "key_takeaways": _as_str_list(payload.get("key_takeaways"))[:6]
            or list(outline.get("key_takeaways") or [])[:6]
            or self._heuristic_takeaways(state),
            "limitations": _as_str_list(payload.get("limitations"))[:8]
            or [
                self._msg(
                    "本报告由 AI 自动生成，关键数据请以原始来源为准。",
                    "This report was generated by AI; verify key facts against the "
                    "original sources.",
                )
            ],
        }

    def assemble(
        self,
        state: ResearchState,
        sections: Sequence[ReportSection],
        meta: Dict[str, Any],
        *,
        usage: UsageStats,
        limitations: Optional[Sequence[str]] = None,
    ) -> Report:
        """Assemble the final :class:`Report` (``references``/``markdown`` set later)."""
        return Report(
            question=state.plan.question,
            title=_as_text(meta.get("title"), 140) or state.plan.question,
            language=self.language,
            summary=_as_text(meta.get("summary"), 1200),
            key_takeaways=_as_str_list(meta.get("key_takeaways"))[:6],
            sections=list(sections),
            references=[],
            limitations=_as_str_list(
                limitations if limitations is not None else meta.get("limitations")
            ),
            usage=usage,
        )

    # ------------------------------------------------------------------ #
    def _heuristic_summary(self, state: ResearchState) -> str:
        claims = [finding.claim for finding in state.findings[:3] if finding.claim]
        if claims:
            return "；".join(claims) + "。"
        return self._msg(
            f"本报告围绕「{state.plan.question}」梳理公开资料，给出结构化要点。",
            f"This report structures the available evidence around “{state.plan.question}”.",
        )

    def _heuristic_takeaways(self, state: ResearchState) -> List[str]:
        claims = [finding.claim for finding in state.findings[:5] if finding.claim]
        if claims:
            return claims
        return [
            self._msg(
                "问题已被拆解为多个子问题并完成资料检索。",
                "The question was decomposed into sub-questions and researched.",
            ),
            self._msg(
                "当前可用证据有限，结论需结合原始来源核实。",
                "Available evidence is limited; verify conclusions against primary sources.",
            ),
        ]

    def _msg(self, zh: str, en: str) -> str:
        return zh if self.language == "zh" else en
