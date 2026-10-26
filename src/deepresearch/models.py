"""Dataclasses shared by every layer of DeepResearch.

The pipeline is built as a chain of small, replaceable stages:

    question -> plan -> search -> fetch -> findings -> (gap loop) -> outline
             -> sections -> report

Every value that crosses a stage boundary is defined here.  Keeping the model
layer dependency-free (stdlib only) makes it trivial to serialise a complete
run to JSON for replay, debugging or evaluation.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def utcnow() -> str:
    """Current UTC time as an ISO-8601 string (seconds precision)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Depth(str, Enum):
    """Research budget preset."""

    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"

    @classmethod
    def parse(cls, value: Any) -> "Depth":
        if isinstance(value, Depth):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            allowed = ", ".join(d.value for d in cls)
            raise ValueError(f"unknown depth {value!r} (choose one of: {allowed})") from None


@dataclass(frozen=True)
class DepthProfile:
    """Concrete limits derived from a :class:`Depth`."""

    label: str
    max_sub_questions: int
    queries_per_question: int
    max_sources: int
    max_rounds: int
    max_findings: int
    section_words: int


DEPTH_PROFILES: Dict[Depth, DepthProfile] = {
    Depth.QUICK: DepthProfile("Quick", 3, 2, 8, 1, 6, 180),
    Depth.STANDARD: DepthProfile("Standard", 5, 3, 14, 2, 14, 320),
    Depth.DEEP: DepthProfile("Deep", 7, 4, 24, 3, 24, 550),
}


def profile_for(depth: Any) -> DepthProfile:
    """Return the :class:`DepthProfile` for a depth name or enum member."""
    return DEPTH_PROFILES[Depth.parse(depth)]


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #
@dataclass
class SearchHit:
    """One raw search-engine result."""

    url: str
    title: str
    snippet: str = ""
    score: float = 0.0
    provider: str = ""
    published: Optional[str] = None


@dataclass
class Source:
    """A retrieved document, cleaned and ready to be cited.

    ``id`` is assigned by the orchestrator (``S1``, ``S2``, ...) and is what the
    LLM must use for inline citations, e.g. ``... as reported in [S3]``.
    """

    id: str
    url: str
    title: str
    domain: str = ""
    snippet: str = ""
    content: str = ""
    word_count: int = 0
    provider: str = ""
    published: Optional[str] = None
    fetched_at: Optional[str] = None
    status: str = "pending"  # pending | ok | failed | skipped
    error: Optional[str] = None

    def excerpt(self, max_chars: int = 1500) -> str:
        """Return a whitespace-normalised excerpt capped at ``max_chars``."""
        text = re.sub(r"\s+", " ", self.content or self.snippet or "").strip()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "…"


@dataclass
class Document:
    """Result of fetching a single URL."""

    url: str
    title: str = ""
    text: str = ""
    status: str = "ok"  # ok | failed | skipped
    error: Optional[str] = None
    fetched_at: str = field(default_factory=utcnow)
    http_status: Optional[int] = None
    content_type: Optional[str] = None


# --------------------------------------------------------------------------- #
# Planning / reasoning
# --------------------------------------------------------------------------- #
@dataclass
class SubQuestion:
    """One decomposed research question, with the queries used to cover it."""

    id: str
    question: str
    rationale: str = ""
    queries: List[str] = field(default_factory=list)
    priority: int = 1
    status: str = "pending"  # pending | researching | covered | gap


@dataclass
class ResearchPlan:
    question: str
    language: str = "zh"
    depth: Depth = Depth.STANDARD
    sub_questions: List[SubQuestion] = field(default_factory=list)
    search_strategy: str = ""
    created_at: str = field(default_factory=utcnow)


@dataclass
class Finding:
    """A verified statement extracted from one or more sources."""

    id: str
    sub_question_id: str
    claim: str
    evidence: str = ""
    source_ids: List[str] = field(default_factory=list)
    confidence: float = 0.6
    caveats: str = ""

    def citation_marker(self) -> str:
        if not self.source_ids:
            return ""
        return "".join(f"[{sid}]" for sid in self.source_ids)


@dataclass
class Gap:
    """A hole detected during reflection, plus the queries that might fill it."""

    id: str
    sub_question_id: str
    description: str
    queries: List[str] = field(default_factory=list)
    status: str = "open"  # open | resolved | dropped


@dataclass
class OutlineItem:
    heading: str
    brief: str = ""
    sub_question_ids: List[str] = field(default_factory=list)
    source_ids: List[str] = field(default_factory=list)


@dataclass
class ResearchState:
    """Everything the agent knows at a given moment (the working memory)."""

    plan: ResearchPlan
    sources: Dict[str, Source] = field(default_factory=dict)
    findings: List[Finding] = field(default_factory=list)
    gaps: List[Gap] = field(default_factory=list)
    outline: List[OutlineItem] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    iteration: int = 0
    started_at: str = field(default_factory=utcnow)

    # -- read helpers ------------------------------------------------------- #
    def ok_sources(self) -> List[Source]:
        return [s for s in self.sources.values() if s.status == "ok" and s.content]

    def finding_for(self, sub_question_id: str) -> List[Finding]:
        return [f for f in self.findings if f.sub_question_id == sub_question_id]

    def covered_sub_questions(self) -> List[str]:
        covered = {f.sub_question_id for f in self.findings if f.source_ids and f.sub_question_id}
        return sorted(covered)

    def source_corpus(self, max_chars_per_source: int = 1800) -> str:
        """Compact, citable context block handed to the writing prompts."""
        lines: List[str] = []
        for src in self.ok_sources():
            lines.append(
                f"[{src.id}] {src.title}\nURL: {src.url}\n{src.excerpt(max_chars_per_source)}\n"
            )
        return "\n".join(lines).strip()


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
@dataclass
class ReportSection:
    heading: str
    level: int = 2
    body: str = ""  # markdown, may contain [S1] / [S1][S3] citations
    source_ids: List[str] = field(default_factory=list)


@dataclass
class UsageStats:
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    search_calls: int = 0
    fetches: int = 0
    fetch_failures: int = 0
    elapsed_seconds: float = 0.0
    est_cost_usd: float = 0.0

    def merge(self, other: "UsageStats") -> None:
        for f in self.__dataclass_fields__:
            setattr(self, f, getattr(self, f) + getattr(other, f))


@dataclass
class Report:
    question: str
    title: str
    language: str = "zh"
    summary: str = ""
    key_takeaways: List[str] = field(default_factory=list)
    sections: List[ReportSection] = field(default_factory=list)
    references: List[Source] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    markdown: str = ""
    usage: UsageStats = field(default_factory=UsageStats)
    generated_at: str = field(default_factory=utcnow)
    disclaimer: str = ""

    def cited_source_ids(self) -> List[str]:
        ids: List[str] = []
        for section in self.sections:
            for sid in section.source_ids:
                if sid not in ids:
                    ids.append(sid)
        return ids


@dataclass
class RunResult:
    """The full outcome of one research run, as returned by the public API."""

    report: Report
    state: ResearchState
    usage: UsageStats = field(default_factory=UsageStats)
    out_dir: Optional[str] = None
    markdown_path: Optional[str] = None
    json_path: Optional[str] = None
    trace_path: Optional[str] = None


# --------------------------------------------------------------------------- #
# JSON helpers
# --------------------------------------------------------------------------- #
def to_jsonable(value: Any) -> Any:
    """Recursively convert dataclasses / enums / nested containers to primitives."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {k: to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    return value
