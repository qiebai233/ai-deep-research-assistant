"""Unit tests for the Markdown renderer and citation ordering."""

from __future__ import annotations

import unittest

from deepresearch.models import Report, ReportSection, Source, UsageStats
from deepresearch.report import citation_order, render_markdown
from deepresearch.report.renderer import disclaimer_for

QUESTION = "固态电池产业化进展如何？"


def make_source(source_id: str, *, title: str = "", url: str = "") -> Source:
    return Source(
        id=source_id,
        url=url or f"https://example.com/{source_id.lower()}",
        title=title if title else f"来源 {source_id}",
        domain="example.com",
        content="正文内容",
        word_count=4,
        status="ok",
    )


def make_section(heading: str, body: str = "", source_ids=None, level: int = 2) -> ReportSection:
    return ReportSection(heading=heading, level=level, body=body, source_ids=list(source_ids or []))


def make_report(**overrides) -> Report:
    defaults = dict(
        question=QUESTION,
        title="固态电池深度研究报告",
        language="zh",
        summary="这是摘要正文。",
        key_takeaways=["要点一", "要点二"],
        sections=[
            make_section("研究背景", "背景正文 [S2]。", ["S2"]),
            make_section("最新进展", "进展正文 [S1][S2]。", ["S1", "S2"]),
        ],
        references=[make_source("S1"), make_source("S2")],
        limitations=["部分来源为二手报道。"],
        usage=UsageStats(search_calls=3, fetches=2, fetch_failures=1),
        disclaimer="",
    )
    defaults.update(overrides)
    return Report(**defaults)


def references_block(markdown: str) -> str:
    _, _, tail = markdown.partition("## 参考文献")
    return tail


class RenderMarkdownTests(unittest.TestCase):
    def test_report_structure(self) -> None:
        report = make_report()
        markdown = render_markdown(report)

        self.assertTrue(markdown.startswith("# 固态电池深度研究报告"))
        self.assertIn(f"> **研究问题**：{QUESTION}", markdown)
        self.assertIn("生成时间", markdown)
        self.assertIn("模型", markdown)
        self.assertIn("深度", markdown)
        for heading in (
            "## 摘要",
            "## 关键发现",
            "## 目录",
            "## 研究方法与局限",
            "## 参考文献",
        ):
            self.assertIn(heading, markdown)
        self.assertIn("- 要点一", markdown)
        self.assertIn("这是摘要正文。", markdown)
        self.assertIn("研究背景", markdown)
        self.assertIn("---", markdown)
        self.assertIn("*由 DeepResearch v0.1.0 生成", markdown)
        self.assertTrue(markdown.endswith("\n"))
        self.assertEqual(report.markdown, "")  # renderer never mutates the report

    def test_contents_anchors(self) -> None:
        markdown = render_markdown(make_report())
        self.assertIn("1. [研究背景](#研究背景)", markdown)
        self.assertIn("2. [最新进展](#最新进展)", markdown)

    def test_duplicate_headings_get_unique_anchors(self) -> None:
        report = make_report(
            sections=[
                make_section("重复章节", "A [S1]", ["S1"]),
                make_section("重复章节", "B [S1]", ["S1"]),
            ]
        )
        markdown = render_markdown(report)
        self.assertIn("(#重复章节)", markdown)
        self.assertIn("(#重复章节-1)", markdown)

    def test_references_only_cited_and_in_citation_order(self) -> None:
        report = make_report(
            sections=[
                make_section("第三章", "先引用第三个来源 [S3]。", ["S3"]),
                make_section("第一二章", "再引用第一与第二来源 [S1][S2]。", ["S1", "S2"]),
            ],
            references=[make_source("S1"), make_source("S2"), make_source("S3")],
        )
        self.assertEqual(citation_order(report), ["S3", "S1", "S2"])
        block = references_block(render_markdown(report))
        self.assertIn("[S3]", block)
        self.assertIn("[S1]", block)
        self.assertLess(block.index("[S3]"), block.index("[S1]"))
        self.assertLess(block.index("[S1]"), block.index("[S2]"))

    def test_uncited_reference_is_dropped(self) -> None:
        report = make_report(
            sections=[make_section("正文", "只引用一个来源 [S1]。", ["S1"])],
            references=[make_source("S1"), make_source("S2", title="未被引用的来源")],
        )
        block = references_block(render_markdown(report))
        self.assertIn("[S1]", block)
        self.assertNotIn("[S2]", block)
        self.assertNotIn("未被引用的来源", block)

    def test_reference_line_uses_url_when_title_missing(self) -> None:
        empty = make_source("S1")
        empty.title = ""
        report = make_report(
            sections=[make_section("正文", "引用 [S1]。", ["S1"])],
            references=[empty],
        )
        block = references_block(render_markdown(report))
        self.assertIn("https://example.com/s1", block)

    def test_empty_sections_and_references(self) -> None:
        report = make_report(
            sections=[], references=[], key_takeaways=[], summary="", limitations=[]
        )
        markdown = render_markdown(report)
        self.assertIn("# 固态电池深度研究报告", markdown)
        self.assertIn("_（本次报告没有分节内容）_", markdown)
        self.assertIn("_（本次运行未引用外部来源）_", markdown)
        self.assertIn("## 研究方法与局限", markdown)
        self.assertIn("本报告由 AI 自动生成", markdown)  # default limitation

    def test_no_citations_but_references_present(self) -> None:
        report = make_report(
            sections=[make_section("正文", "本节没有任何引用。", [])],
            references=[make_source("S1")],
        )
        markdown = render_markdown(report)
        self.assertIn("_（本次运行未引用外部来源）_", references_block(markdown))
        self.assertIn("本节没有任何引用。", markdown)

    def test_empty_body_section_renders_placeholder(self) -> None:
        report = make_report(sections=[make_section("空章节", "", [])])
        markdown = render_markdown(report)
        self.assertIn("## 空章节", markdown)
        self.assertIn("_（本节暂无内容）_", markdown)

    def test_section_level_is_respected(self) -> None:
        report = make_report(sections=[make_section("三级章节", "正文 [S1]", ["S1"], level=3)])
        markdown = render_markdown(report)
        self.assertIn("### 三级章节", markdown)

    def test_custom_disclaimer(self) -> None:
        report = make_report(disclaimer="自定义免责声明")
        markdown = render_markdown(report)
        self.assertIn("*自定义免责声明*", markdown)

    def test_extra_metadata_line(self) -> None:
        report = make_report()
        report.model = "mock-researcher"  # type: ignore[attr-defined]
        report.depth = "quick"  # type: ignore[attr-defined]
        report.rounds = 2  # type: ignore[attr-defined]
        markdown = render_markdown(report)
        self.assertIn("模型：mock-researcher", markdown)
        self.assertIn("深度：快速", markdown)
        self.assertIn("共进行 2 轮检索与补检", markdown)

    def test_english_report(self) -> None:
        report = make_report(
            language="en",
            title="Solid-State Battery Report",
            summary="Summary in English.",
            key_takeaways=["Point one"],
            limitations=["Secondary sources only."],
        )
        markdown = render_markdown(report)
        self.assertIn("# Solid-State Battery Report", markdown)
        self.assertIn("## Summary", markdown)
        self.assertIn("## Key Findings", markdown)
        self.assertIn("## Contents", markdown)
        self.assertIn("## Methodology & Limitations", markdown)
        self.assertIn("## References", markdown)
        self.assertIn("Generated by DeepResearch v", markdown)
        self.assertNotIn("## 摘要", markdown)
        self.assertEqual(
            disclaimer_for("en"),
            "Generated by DeepResearch v0.1.0 · AI-summarised content; verify key facts",
        )


class CitationOrderTests(unittest.TestCase):
    def test_citation_order_dedupes_and_orders(self) -> None:
        report = make_report(
            sections=[
                make_section("A", "[S2] [S1] [S2]", ["S1", "S2"]),
                make_section("B", "[S3]", ["S3"]),
            ]
        )
        self.assertEqual(citation_order(report), ["S2", "S1", "S3"])

    def test_citation_order_falls_back_to_section_source_ids(self) -> None:
        report = make_report(
            sections=[
                make_section("A", "", ["S2", "S1"]),
                make_section("B", "引用 [S1]", ["S1"]),
            ]
        )
        self.assertEqual(citation_order(report), ["S1", "S2"])

    def test_citation_order_empty_report(self) -> None:
        self.assertEqual(citation_order(make_report(sections=[], references=[])), [])

    def test_disclaimer_for_zh_contains_version(self) -> None:
        self.assertIn("由 DeepResearch v0.1.0 生成", disclaimer_for("zh"))
        self.assertIn("由 DeepResearch v0.1.0 生成", disclaimer_for(""))


if __name__ == "__main__":
    unittest.main()
