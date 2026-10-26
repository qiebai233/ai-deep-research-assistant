"""Deterministic offline fetcher used by the mock pipeline.

Every URL produces the same 500–900 character Chinese "article": the title is
derived from the URL, the paragraphs contain numbers derived from a hash of the
URL, so findings can cite concrete figures while the whole run stays offline and
reproducible.  URLs containing ``badlink`` simulate an unreachable page.
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse

from ..models import Document

__all__ = ["MockFetcher"]

_CHARS_PER_DOC_MIN = 500
_MAX_CHARS = 900
_EXTENSION_RE = re.compile(r"\.(?:html?|php|aspx?|md|txt)$", re.IGNORECASE)
_NON_WORD_RE = re.compile(r"[-_]+")


class MockFetcher:
    """A deterministic :class:`~deepresearch.fetch.base.Fetcher` for offline runs."""

    name = "mock"

    def __init__(self, settings: object = None) -> None:
        self.settings = settings

    def fetch(self, url: str) -> Document:
        """Return a fixed synthetic document for ``url`` (``badlink`` fails)."""
        target = str(url or "").strip()
        if not target:
            return Document(url="", status="failed", error="empty URL")
        if "badlink" in target.lower():
            return Document(
                url=target,
                status="failed",
                error="simulated unreachable link (badlink)",
            )
        title = _title_from_url(target)
        text = _article_for(target)
        return Document(
            url=target,
            title=title,
            text=text,
            status="ok",
            http_status=200,
            content_type="text/html; charset=utf-8",
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "MockFetcher()"


def _seed(url: str) -> bytes:
    return hashlib.sha256(url.encode("utf-8")).digest()


def _number(seed: bytes, offset: int, low: int, high: int) -> int:
    start = offset % (len(seed) - 1)
    chunk = seed[start : start + 2].ljust(2, b"\0")
    return low + int.from_bytes(chunk, "big") % (high - low + 1)


def _article_for(url: str) -> str:
    seed = _seed(url)
    year = 2023 + _number(seed, 0, 0, 2)
    previous = year - 1
    sample = _number(seed, 2, 48, 480)
    reports = _number(seed, 4, 12, 60)
    analyses = _number(seed, 6, 8, 40)
    amount = _number(seed, 8, 240, 28_000)
    percent = _number(seed, 10, 6, 46)
    share = _number(seed, 12, 18, 72)
    optimistic = _number(seed, 14, 42, 78)
    sceptical = max(5, 100 - optimistic - _number(seed, 16, 2, 20))
    deviation = _number(seed, 18, 3, 19)
    error = _number(seed, 20, 1, 8)
    paragraphs = [
        (
            f"本文围绕该主题整理了公开资料，检索时间为 {year} 年，样本覆盖 {sample} 个案例，"
            f"数据来自 {reports} 份公开报告与 {analyses} 份行业分析，力求还原可核查的事实脉络。"
        ),
        (
            f"统计显示，相关指标在 {year} 年达到约 {amount:,} 亿元，同比增长 {percent}%，"
            f"其中头部项目的贡献度约为 {share}%；与 {previous} 年相比，"
            "增量主要集中在应用落地与供应链环节。"
        ),
        (
            f"调研样本中，{optimistic}% 的受访者认为该方向进展快于预期，"
            f"另有 {sceptical}% 认为仍存在明显的落地瓶颈；两类观点的差异主要集中在成本、"
            f"标准与数据口径三个维度，与历史均值偏差约 {deviation} 个百分点。"
        ),
        (
            f"方法上，本文交叉比对了 {analyses} 份行业报告与 {reports} 个公开案例，"
            f"对关键数字做了区间校验，误差范围约为 ±{error}%；凡口径不一致的数据，"
            "均以官方统计和原始报告为准，并在正文中标注来源编号。"
        ),
        (
            "从证据强度看，宏观数据的一致性较高，细分环节的样本量仍显不足；"
            "建议在引用具体份额、增速时保留原始定义，并在交叉验证后再写入结论。"
        ),
        (
            f"综合来看，该主题在 {year}–2026 年仍将保持较快演进，但需持续关注数据口径、"
            "成本结构与监管变化带来的不确定性，避免用单一来源的结论替代整体判断。"
        ),
    ]
    text = "\n\n".join(paragraphs)
    # Keep the contract of 500-900 characters even if template text drifts.
    while len(text) < _CHARS_PER_DOC_MIN:
        text += "\n\n补充说明：以上数字均来自公开摘要的区间估计，引用时请核对原始口径与统计年份。"
    if len(text) > _MAX_CHARS:
        text = text[: _MAX_CHARS - 1].rstrip() + "…"
    return text


def _title_from_url(url: str) -> str:
    """Build a readable title from the URL host and last path segment."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:  # pragma: no cover - malformed URL
        return url
    host = parts.netloc.rsplit("@", 1)[-1].split(":", 1)[0]
    host = host[4:] if host.startswith("www.") else host
    segments = [urllib.parse.unquote(segment) for segment in parts.path.split("/") if segment]
    slug = _EXTENSION_RE.sub("", segments[-1]) if segments else ""
    slug = _NON_WORD_RE.sub(" ", slug).strip()
    slug = " ".join(slug.split())[:60]
    if not slug:
        return f"{host} · 资料页"
    return f"{host} · {slug}"
