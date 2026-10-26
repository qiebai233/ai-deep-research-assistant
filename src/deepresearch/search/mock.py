"""Deterministic synthetic search results for the offline demo and tests."""

from __future__ import annotations

import hashlib
import re
from typing import List, Optional, Sequence

from ..models import SearchHit

__all__ = ["MockSearch"]

#: Fixed domain pool required by the providers contract (CONTRACTS.md §5.4).
DOMAIN_POOL: Sequence[str] = (
    "arxiv.org",
    "nature.com",
    "en.wikipedia.org",
    "techcrunch.com",
    "www.gov.cn",
    "zhuanlan.zhihu.com",
)

_PUBLISHED = (
    "2024-08-27",
    "2024-09-18",
    "2024-11-05",
    "2024-12-03",
    "2025-01-12",
    "2025-02-20",
)
_ASPECTS_ZH = ("研究综述", "关键数据", "案例分析", "行业观察", "官方通报", "深度解读")
_ASPECTS_EN = (
    "research review",
    "key data",
    "case study",
    "industry watch",
    "official notice",
    "deep dive",
)
_PERCENTS = (18.4, 26.7, 12.5, 35.2, 42.9, 8.6)
_SAMPLES = (48, 126, 215, 360, 480, 92)
_ASCII_SLUG_RE = re.compile(r"[^a-z0-9]+")


class MockSearch:
    """Deterministic in-memory search backend.

    The same ``query`` always produces the same 5–6 hits (up to ``max_results``),
    using the fixed domain pool above.  This keeps the offline demo and the test
    suite stable while still exercising deduplication, fetching and citations.
    """

    name = "mock"

    def __init__(self, settings: object = None) -> None:
        self.settings = settings

    def search(
        self,
        query: str,
        *,
        max_results: int = 6,
        recency_days: Optional[int] = None,
    ) -> List[SearchHit]:
        """Return deterministic synthetic hits for ``query``."""
        query_text = " ".join(str(query or "").split()).strip()
        if not query_text:
            return []
        limit = max(1, min(int(max_results or 6), 6))
        seed = _seed(query_text)
        language = str(getattr(self.settings, "language", "zh") or "zh").lower()
        aspects = _ASPECTS_EN if language.startswith("en") else _ASPECTS_ZH
        hits: List[SearchHit] = []
        for index in range(limit):
            domain = DOMAIN_POOL[(seed + index) % len(DOMAIN_POOL)]
            digest = hashlib.sha1(f"{query_text}|{index}".encode("utf-8")).hexdigest()
            aspect = aspects[(seed + index) % len(aspects)]
            percent = _PERCENTS[(seed + index) % len(_PERCENTS)]
            sample = _SAMPLES[(seed + index) % len(_SAMPLES)]
            published = _PUBLISHED[(seed + index) % len(_PUBLISHED)]
            if language.startswith("en"):
                title = f"{query_text}: {aspect} ({index + 1})"
                snippet = (
                    f"Synthetic source {index + 1} about {query_text}. "
                    f"Sample size {sample}, year-over-year change {percent}%, "
                    f"published {published} on {domain}."
                )
            else:
                title = f"{query_text}：{aspect}（{index + 1}）"
                snippet = (
                    f"围绕「{query_text}」合成的第 {index + 1} 份资料："
                    f"样本量 {sample}，同比变化 {percent}%，"
                    f"发布于 {published}，来源 {domain}。"
                )
            hits.append(
                SearchHit(
                    url=_fake_url(domain, digest, query_text),
                    title=title,
                    snippet=snippet,
                    score=round(max(0.1, 0.95 - index * 0.07), 2),
                    provider="mock",
                    published=published,
                )
            )
        return hits

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "MockSearch()"


def _seed(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def _slug(text: str, limit: int = 40) -> str:
    ascii_part = _ASCII_SLUG_RE.sub("-", text.lower()).strip("-")[:limit]
    return ascii_part or hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _fake_url(domain: str, digest: str, query_text: str) -> str:
    """Build a plausible, deterministic URL for each domain in the pool."""
    slug = _slug(query_text)
    if domain == "arxiv.org":
        return (
            f"https://arxiv.org/abs/24{int(digest[:2], 16) % 12 + 1:02d}.{int(digest[2:6], 16):04d}"
        )
    if domain == "nature.com":
        return f"https://nature.com/articles/s41586-024-{digest[:6]}"
    if domain == "en.wikipedia.org":
        return f"https://en.wikipedia.org/wiki/{slug.replace('-', '_')}"
    if domain == "techcrunch.com":
        return f"https://techcrunch.com/2025/01/12/{slug}"
    if domain == "www.gov.cn":
        return f"https://www.gov.cn/zhengce/{digest[:10]}.htm"
    return f"https://zhuanlan.zhihu.com/p/{int(digest[:6], 16)}"
