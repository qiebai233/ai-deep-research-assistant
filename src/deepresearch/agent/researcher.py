"""Researcher: search, dedupe, concurrently fetch, extract findings and gaps.

One *round* of research performs, for every target sub-question:

1. run its queries through the search provider (single failures only warn);
2. deduplicate result URLs and interleave candidates across sub-questions;
3. fetch pages concurrently with :class:`~concurrent.futures.ThreadPoolExecutor`
   (the main thread is the only one mutating state);
4. assign ``S1..Sn`` ids, capped by ``profile.max_sources``;
5. ask the model once for ``TASK: findings`` JSON per sub-question, then
   validate/dedupe claims, drop citations to non-existent sources, clamp
   confidence and record evidence gaps.

The model is never trusted blindly: everything it returns is normalised here.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from ..events import EventType
from ..models import Document, Finding, Gap, ResearchState, SearchHit, Source, SubQuestion
from . import prompts
from .caller import LlmCaller
from .planner import fallback_queries

__all__ = ["Researcher", "RoundResult", "domain_of", "normalize_url"]

_MAX_CANDIDATE_SPARE = 4
_MAX_GAP_TARGETS = 4
_CITE_ID_RE = re.compile(r"^S\d+$")


def _language(value: str) -> str:
    return "en" if str(value or "zh").lower().startswith("en") else "zh"


def normalize_url(url: Any) -> str:
    """Normalise a search-result URL: strip fragments/dashes and reject junk."""
    text = str(url or "").strip()
    if not text:
        return ""
    if text.startswith("//"):
        text = "https:" + text
    if not text.startswith(("http://", "https://")):
        return ""
    text = text.split("#", 1)[0].rstrip("/")
    return text


def domain_of(url: str) -> str:
    """Hostname of ``url`` without a leading ``www.``."""
    host = (urlparse(url).netloc or "").lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def _word_count(text: str) -> int:
    """Count Latin words plus CJK characters (works for zh and en content)."""
    latin = len(re.findall(r"[A-Za-z0-9_]+", text or ""))
    cjk = len(re.findall(r"[\u3400-\u9fff]", text or ""))
    return latin + cjk


def _as_text(value: Any, limit: int = 400) -> str:
    return " ".join(str(value or "").split())[:limit]


def _as_str_list(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    result: List[str] = []
    for item in value:
        text = _as_text(item, 240)
        if text and text not in result:
            result.append(text)
    return result


def _confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.6
    return max(0.0, min(1.0, number))


def _claim_key(claim: str) -> str:
    """Normalised claim text used for deduplication."""
    return re.sub(r"[\s\W_]+", "", str(claim or "").casefold())[:200]


def _first_sentence(text: str, limit: int = 220) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return ""
    match = re.search(r"[^。！？.!?]{8,}[。！？.!?]", cleaned)
    return (match.group(0) if match else cleaned)[:limit]


@dataclass
class RoundResult:
    """Outcome of one research round (used by the orchestrator for progress)."""

    round_index: int
    queries_run: int = 0
    hits_found: int = 0
    new_source_ids: List[str] = field(default_factory=list)
    new_findings: int = 0
    new_gaps: List[Gap] = field(default_factory=list)
    gaps: List[Gap] = field(default_factory=list)
    stop_reason: Optional[str] = None


@dataclass
class _Target:
    sub_question_id: str
    question: str
    queries: List[str]
    gap_id: Optional[str] = None


class Researcher:
    """Runs search -> fetch -> findings -> gaps for one round at a time."""

    def __init__(
        self,
        llm: Any,
        search: Any,
        fetcher: Any,
        settings: Any,
        events: Any = None,
        *,
        caller: Optional[LlmCaller] = None,
        warn: Optional[Callable[..., None]] = None,
        language: Optional[str] = None,
    ) -> None:
        self.llm = llm
        self.search = search
        self.fetcher = fetcher
        self.settings = settings
        self.events = events
        self.caller = caller if caller is not None else LlmCaller(llm, settings)
        self.usage = self.caller.usage
        self.warn = warn or (lambda message, data=None: None)
        self.language = _language(language or settings.language)
        self.profile = settings.profile()
        self._sq_sources: Dict[str, List[str]] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def run_round(
        self,
        state: ResearchState,
        *,
        round_index: int = 1,
        total_rounds: int = 1,
        progress: Optional[Callable[..., None]] = None,
        percent_base: float = 0.0,
        percent_span: float = 100.0,
    ) -> RoundResult:
        """Execute one full research round and mutate ``state`` in place."""
        emit = progress or (lambda *args, **kwargs: None)
        span = max(1.0, float(percent_span))
        base = float(percent_base)

        def pct(fraction: float) -> float:
            return base + max(0.0, min(1.0, fraction)) * span

        result = RoundResult(round_index=round_index)
        targets = self._targets(state, round_index)
        if not targets:
            return result

        query_count = sum(len(target.queries) for target in targets)
        search_message = self._msg(
            f"第 {round_index}/{total_rounds} 轮检索："
            f"{len(targets)} 个子问题，{query_count} 条查询",
            f"Round {round_index}/{total_rounds} search: {len(targets)} sub-questions, "
            f"{query_count} queries",
        )
        emit(
            EventType.SEARCH_START,
            search_message,
            data={"round": round_index, "sub_questions": len(targets), "queries": query_count},
            percent=pct(0.0),
        )
        url_map, hits_total = self._search(state, targets, result)
        result.hits_found = hits_total
        emit(
            EventType.SEARCH_DONE,
            self._msg(
                f"检索完成：{hits_total} 条新候选结果",
                f"Search done: {hits_total} new candidate results",
            ),
            data={"round": round_index, "queries_run": result.queries_run, "hits": hits_total},
            percent=pct(0.18),
        )

        self._fetch_and_register(state, url_map, result, emit, pct)

        before_findings = len(state.findings)
        for target in targets:
            if self.caller.exhausted():
                result.stop_reason = self.caller.stop_reason
                break
            sources = self._sources_for_sq(
                state, target.sub_question_id, include_global=round_index <= 1
            )
            self._collect_findings(state, target, sources, round_index, result)
        result.new_findings = len(state.findings) - before_findings

        emit(
            EventType.FINDINGS_READY,
            self._msg(
                f"证据提炼完成：新增 {result.new_findings} 条发现（累计 {len(state.findings)} 条）",
                f"Findings ready: +{result.new_findings} (total {len(state.findings)})",
            ),
            data={
                "round": round_index,
                "new_findings": result.new_findings,
                "total_findings": len(state.findings),
            },
            percent=pct(0.8),
        )

        for index, gap in enumerate(result.new_gaps):
            emit(
                EventType.GAP_FOUND,
                self._msg(f"发现证据缺口：{gap.description}", f"Evidence gap: {gap.description}"),
                data={
                    "gap_id": gap.id,
                    "sub_question_id": gap.sub_question_id,
                    "queries": gap.queries,
                },
                percent=pct(0.85 + 0.1 * (index + 1) / max(1, len(result.new_gaps))),
            )
        result.gaps = [gap for gap in state.gaps if gap.status == "open"]
        state.notes.append(
            f"round {round_index}: +{len(result.new_source_ids)} sources, "
            f"+{result.new_findings} findings, {len(result.gaps)} open gaps"
        )
        return result

    # ------------------------------------------------------------------ #
    # Targets
    # ------------------------------------------------------------------ #
    def _targets(self, state: ResearchState, round_index: int) -> List[_Target]:
        sub_questions = list(state.plan.sub_questions)
        if round_index <= 1:
            ordered = sorted(enumerate(sub_questions), key=lambda item: (item[1].priority, item[0]))
            targets = [
                _Target(
                    sub_question_id=sq.id,
                    question=sq.question,
                    queries=list(sq.queries) or fallback_queries(sq.question, self.language),
                )
                for _, sq in ordered
            ]
            return targets
        targets: List[_Target] = []
        by_id = {sq.id: sq for sq in sub_questions}
        limit = max(1, min(_MAX_GAP_TARGETS, len(sub_questions) or _MAX_GAP_TARGETS))
        for gap in state.gaps:
            if gap.status != "open":
                continue
            sq = by_id.get(gap.sub_question_id)
            if sq is None:
                gap.status = "dropped"
                continue
            queries = list(gap.queries) or fallback_queries(sq.question, self.language)
            targets.append(_Target(sq.id, sq.question, queries[:4], gap.id))
            if len(targets) >= limit:
                break
        return targets

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #
    def _search(
        self, state: ResearchState, targets: Sequence[_Target], result: RoundResult
    ) -> Tuple[Dict[str, Dict[str, Any]], int]:
        known_urls = {source.url for source in state.sources.values()}
        url_map: Dict[str, Dict[str, Any]] = {}
        hits_total = 0
        recency = int(getattr(self.settings, "search_recency_days", 0) or 0) or None
        for target in targets:
            for query in target.queries:
                if self.caller.exhausted():
                    result.stop_reason = self.caller.stop_reason
                    return url_map, hits_total
                try:
                    hits = self.search.search(
                        query,
                        max_results=int(getattr(self.settings, "search_max_results", 6)),
                        recency_days=recency,
                    )
                    self.usage.search_calls += 1
                    result.queries_run += 1
                except Exception as exc:  # noqa: BLE001 - one bad query must not kill a run
                    self.warn(
                        self._msg(
                            f"搜索失败（{query}）：{exc}",
                            f"Search failed ({query}): {exc}",
                        ),
                        data={"query": query, "error": str(exc)[:200]},
                    )
                    continue
                for hit in list(hits or []):
                    url = normalize_url(getattr(hit, "url", ""))
                    if not url or url in known_urls:
                        continue
                    entry = url_map.get(url)
                    if entry is None:
                        url_map[url] = {"hit": hit, "sq_ids": [target.sub_question_id]}
                        hits_total += 1
                    elif target.sub_question_id not in entry["sq_ids"]:
                        entry["sq_ids"].append(target.sub_question_id)
        return url_map, hits_total

    # ------------------------------------------------------------------ #
    # Fetch
    # ------------------------------------------------------------------ #
    def _fetch_and_register(
        self,
        state: ResearchState,
        url_map: Dict[str, Dict[str, Any]],
        result: RoundResult,
        emit: Callable[..., None],
        pct: Callable[[float], float],
    ) -> List[str]:
        cap = int(self.profile.max_sources) - len(state.sources)
        if cap <= 0 or not url_map:
            return []
        urls = list(url_map.keys())
        fetch_urls = urls[: min(len(urls), cap + _MAX_CANDIDATE_SPARE)]
        emit(
            EventType.FETCH_START,
            self._msg(
                f"并发抓取 {len(fetch_urls)} 篇网页正文",
                f"Fetching {len(fetch_urls)} pages concurrently",
            ),
            data={"round": result.round_index, "count": len(fetch_urls)},
            percent=pct(0.2),
        )
        documents = self._fetch_many(fetch_urls)
        planned = max(1, min(cap, len(fetch_urls)))
        new_ids: List[str] = []
        for url in fetch_urls:
            if len(state.sources) >= int(self.profile.max_sources):
                break
            entry = url_map[url]
            document = documents.get(url)
            self.usage.fetches += 1
            text_ok = bool((document.text or "").strip()) if document is not None else False
            ok = document is not None and document.status == "ok" and text_ok
            if not ok:
                self.usage.fetch_failures += 1
                reason = (document.error if document is not None else None) or "empty document"
                self.warn(
                    self._msg(
                        f"抓取失败：{url}（{reason}）",
                        f"Fetch failed: {url} ({reason})",
                    ),
                    data={"url": url, "error": str(reason)[:200]},
                )
                continue
            source = self._make_source(state, url, entry["hit"], document)
            state.sources[source.id] = source
            for sub_question_id in entry["sq_ids"]:
                bucket = self._sq_sources.setdefault(sub_question_id, [])
                if source.id not in bucket:
                    bucket.append(source.id)
            result.new_source_ids.append(source.id)
            new_ids.append(source.id)
            emit(
                EventType.SOURCE_READY,
                self._msg(
                    f"来源就绪：[{source.id}] {source.title or source.domain}",
                    f"Source ready: [{source.id}] {source.title or source.domain}",
                ),
                data={
                    "source_id": source.id,
                    "url": source.url,
                    "domain": source.domain,
                    "word_count": source.word_count,
                },
                percent=pct(0.22 + 0.33 * (len(new_ids) / planned)),
            )
        return new_ids

    def _fetch_many(self, urls: Sequence[str]) -> Dict[str, Document]:
        workers = max(1, int(getattr(self.settings, "fetch_concurrency", 4) or 1))
        documents: Dict[str, Document] = {}
        with ThreadPoolExecutor(max_workers=min(workers, max(1, len(urls)))) as pool:
            futures = {pool.submit(self.fetcher.fetch, url): url for url in urls}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    document = future.result()
                except Exception as exc:  # noqa: BLE001 - fetchers should not raise, but be safe
                    document = Document(url=url, status="failed", error=str(exc))
                documents[url] = document
        return documents

    def _make_source(
        self, state: ResearchState, url: str, hit: SearchHit, document: Document
    ) -> Source:
        content = str(document.text or "")[: int(getattr(self.settings, "fetch_max_chars", 12000))]
        title = _as_text(document.title, 300) or _as_text(getattr(hit, "title", ""), 300) or url
        return Source(
            id=f"S{len(state.sources) + 1}",
            url=url,
            title=title,
            domain=domain_of(url),
            snippet=_as_text(getattr(hit, "snippet", ""), 600),
            content=content,
            word_count=_word_count(content),
            provider=_as_text(getattr(hit, "provider", ""), 40)
            or _as_text(getattr(self.fetcher, "name", ""), 40),
            published=getattr(hit, "published", None),
            fetched_at=getattr(document, "fetched_at", None),
            status="ok",
        )

    # ------------------------------------------------------------------ #
    # Findings / gaps
    # ------------------------------------------------------------------ #
    def _sources_for_sq(
        self, state: ResearchState, sub_question_id: str, *, include_global: bool = False
    ) -> List[Source]:
        ids = list(dict.fromkeys(self._sq_sources.get(sub_question_id, [])))
        sources = [
            state.sources[sid]
            for sid in ids
            if sid in state.sources and state.sources[sid].status == "ok"
        ]
        if not sources:
            for finding in state.finding_for(sub_question_id):
                for sid in finding.source_ids:
                    source = state.sources.get(sid)
                    if source is not None and source.status == "ok" and source not in sources:
                        sources.append(source)
        if not sources and include_global:
            sources = state.ok_sources()[:3]
        return sources

    def _collect_findings(
        self,
        state: ResearchState,
        target: _Target,
        sources: Sequence[Source],
        round_index: int,
        result: RoundResult,
    ) -> None:
        sub_question = next(
            (sq for sq in state.plan.sub_questions if sq.id == target.sub_question_id), None
        )
        if sub_question is None:
            return
        remaining = int(self.profile.max_findings) - len(state.findings)
        if remaining <= 0:
            return
        messages = prompts.findings_messages(
            state.plan.question,
            sub_question,
            sources,
            language=self.language,
            round_index=round_index,
            max_sources=6,
        )
        data = self.caller.complete_json(messages, label=f"findings:{sub_question.id}")
        valid_ids = {sid for sid, src in state.sources.items() if src.status == "ok"}
        seen_claims = {_claim_key(finding.claim) for finding in state.findings}
        new_findings: List[Finding] = []
        if isinstance(data, dict) and isinstance(data.get("findings"), (list, tuple)):
            for item in data["findings"]:
                if len(new_findings) >= remaining:
                    break
                if not isinstance(item, dict):
                    continue
                claim = _as_text(item.get("claim"), 400)
                if not claim or _claim_key(claim) in seen_claims:
                    continue
                source_ids = [
                    sid
                    for sid in _as_str_list(item.get("source_ids"))
                    if sid in valid_ids and _CITE_ID_RE.match(sid)
                ]
                new_findings.append(
                    Finding(
                        id=f"F{len(state.findings) + len(new_findings) + 1}",
                        sub_question_id=sub_question.id,
                        claim=claim,
                        evidence=_as_text(item.get("evidence"), 800),
                        source_ids=source_ids,
                        confidence=_confidence(item.get("confidence")),
                        caveats=_as_text(item.get("caveats"), 300),
                    )
                )
                seen_claims.add(_claim_key(claim))
        if not new_findings and sources:
            new_findings = self._heuristic_findings(state, sub_question, sources, remaining)
        state.findings.extend(new_findings)
        has_citations = any(finding.source_ids for finding in state.finding_for(sub_question.id))
        if self._has_findings_for(state, sub_question.id):
            sub_question.status = "covered" if has_citations else "gap"
        else:
            sub_question.status = "gap"

        new_gaps = self._parse_gaps(state, sub_question, data)
        result.new_gaps.extend(new_gaps)
        if not self._has_findings_for(state, sub_question.id) and not new_gaps:
            gap = self._auto_gap(state, sub_question)
            if gap is not None:
                result.new_gaps.append(gap)
        if target.gap_id:
            self._resolve_gap(state, target.gap_id, sub_question.id, new_findings)

    def _heuristic_findings(
        self,
        state: ResearchState,
        sub_question: SubQuestion,
        sources: Sequence[Source],
        remaining: int,
    ) -> List[Finding]:
        findings: List[Finding] = []
        for source in list(sources)[: min(2, remaining)]:
            claim = _first_sentence(source.excerpt(240)) or _as_text(source.title, 300)
            if not claim:
                continue
            findings.append(
                Finding(
                    id=f"F{len(state.findings) + len(findings) + 1}",
                    sub_question_id=sub_question.id,
                    claim=claim,
                    evidence=self._msg(
                        f"原文摘录，来自《{source.title or source.domain}》",
                        f"Excerpt from {source.title or source.domain}",
                    ),
                    source_ids=[source.id],
                    confidence=0.4,
                )
            )
        return findings

    def _parse_gaps(self, state: ResearchState, sub_question: SubQuestion, data: Any) -> List[Gap]:
        if not isinstance(data, dict) or not isinstance(data.get("gaps"), (list, tuple)):
            return []
        max_gaps = max(2, int(self.profile.max_sub_questions))
        base = len(state.gaps)
        if base >= max_gaps:
            return []
        valid_sq_ids = {sq.id for sq in state.plan.sub_questions}
        existing = {(gap.sub_question_id, _claim_key(gap.description)) for gap in state.gaps}
        new_gaps: List[Gap] = []
        for item in data["gaps"]:
            if base + len(new_gaps) >= max_gaps:
                break
            if not isinstance(item, dict):
                continue
            description = _as_text(item.get("description"), 300)
            if not description:
                continue
            sq_id = _as_text(item.get("sub_question_id"), 20) or sub_question.id
            if sq_id not in valid_sq_ids:
                sq_id = sub_question.id
            key = (sq_id, _claim_key(description))
            if key in existing:
                continue
            queries = (
                _as_str_list(item.get("queries"))[:3]
                or fallback_queries(sub_question.question, self.language)[1:3]
            )
            new_gaps.append(
                Gap(
                    id=f"G{base + len(new_gaps) + 1}",
                    sub_question_id=sq_id,
                    description=description,
                    queries=queries,
                )
            )
            existing.add(key)
        state.gaps.extend(new_gaps)
        return new_gaps

    def _auto_gap(self, state: ResearchState, sub_question: SubQuestion) -> Optional[Gap]:
        for gap in state.gaps:
            if gap.sub_question_id == sub_question.id and gap.status == "open":
                return None
        gap = Gap(
            id=f"G{len(state.gaps) + 1}",
            sub_question_id=sub_question.id,
            description=self._msg(
                f"缺少关于「{sub_question.question}」的可引用证据",
                f"Not enough citable evidence for “{sub_question.question}”",
            ),
            queries=fallback_queries(sub_question.question, self.language)[1:3],
        )
        state.gaps.append(gap)
        return gap

    def _resolve_gap(
        self,
        state: ResearchState,
        gap_id: str,
        sub_question_id: str,
        new_findings: Sequence[Finding],
    ) -> None:
        gap = next((item for item in state.gaps if item.id == gap_id), None)
        if gap is None or gap.status != "open":
            return
        resolved = any(
            finding.sub_question_id == sub_question_id and finding.source_ids
            for finding in new_findings
        )
        gap.status = "resolved" if resolved else "dropped"

    # ------------------------------------------------------------------ #
    def _has_findings_for(self, state: ResearchState, sub_question_id: str) -> bool:
        return any(finding.sub_question_id == sub_question_id for finding in state.findings)

    def _msg(self, zh: str, en: str) -> str:
        return zh if self.language == "zh" else en
