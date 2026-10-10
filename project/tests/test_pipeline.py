"""핵심 파이프라인 회귀 테스트.

실행: python3 -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sma.agents import BookAgent, ContestAgent, ResearchAgent  # noqa: E402
from sma.agents.base import AgentContext  # noqa: E402
from sma.analysis.compare import compare_segments, region_key  # noqa: E402
from sma.analysis.sentiment import score_text  # noqa: E402
from sma.analysis.text import tokenize  # noqa: E402
from sma.collectors import SampleCollector  # noqa: E402
from sma.collectors.base import CollectorUnavailable  # noqa: E402
from sma.config import ResearchPlan  # noqa: E402
from sma.controllers import CollectionController  # noqa: E402
from sma.models import Document, QueryTask  # noqa: E402
from sma.storage import DocumentStore  # noqa: E402

PLAN_PATH = ROOT / "config" / "research_plan.json"
SAMPLE_DIR = ROOT / "data" / "samples"


class TextTests(unittest.TestCase):
    def test_tokenize_filters_stopwords_and_short_tokens(self):
        tokens = tokenize("정말 맛있는 성수동 카페 the best a")
        self.assertIn("성수동", tokens)
        self.assertIn("카페", tokens)
        self.assertNotIn("정말", tokens)
        self.assertNotIn("the", tokens)

    def test_sentiment_direction(self):
        self.assertEqual(score_text("정말 친절하고 맛있어요").label, "positive")
        self.assertEqual(score_text("불친절하고 최악이었다").label, "negative")


class ModelTests(unittest.TestCase):
    def test_html_is_stripped_and_id_is_stable(self):
        a = Document(source="s", query="q", segment="korean", title="<b>맛집</b>", url="http://x/1")
        b = Document(source="s", query="other", segment="korean", title="맛집", url="http://x/1")
        self.assertEqual(a.title, "맛집")
        self.assertEqual(a.doc_id, b.doc_id)

    def test_region_key_uses_two_levels(self):
        self.assertEqual(region_key("서울 성동구 성수동"), "서울 성동구")


class StorageTests(unittest.TestCase):
    def test_duplicates_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DocumentStore(Path(tmp) / "t.sqlite3")
            doc = Document(source="s", query="q", segment="korean", url="http://x/1", text="hi")
            stored, duplicated = store.add_many([doc, doc])
            self.assertEqual((stored, duplicated), (1, 1))
            self.assertEqual(store.count("korean"), 1)
            store.close()


class CollectorTests(unittest.TestCase):
    def test_sample_collector_respects_segment_and_limit(self):
        collector = SampleCollector(SAMPLE_DIR)
        docs = list(
            collector.collect(QueryTask(query="맛집", segment="korean", source="sample", limit=3))
        )
        self.assertEqual(len(docs), 3)
        self.assertTrue(all(d.segment == "korean" for d in docs))

    def test_missing_sample_dir_is_unavailable(self):
        collector = SampleCollector(SAMPLE_DIR / "does-not-exist")
        ok, _reason = collector.available()
        self.assertFalse(ok)
        with self.assertRaises(CollectorUnavailable):
            list(collector.collect(QueryTask(query="x", segment="korean", source="sample")))


class ControllerTests(unittest.TestCase):
    def test_run_collects_and_skips_unavailable_sources(self):
        plan = ResearchPlan.load(PLAN_PATH)
        with tempfile.TemporaryDirectory() as tmp:
            store = DocumentStore(Path(tmp) / "t.sqlite3")
            controller = CollectionController(store, [SampleCollector(SAMPLE_DIR)])
            report = controller.run(plan)
            self.assertGreater(report.stored, 0)
            self.assertEqual(report.stored, store.count())
            self.assertIn("naver_blog", report.skipped_sources)
            store.close()


class AnalysisTests(unittest.TestCase):
    def test_compare_produces_overlap_and_distinctive_terms(self):
        plan = ResearchPlan.load(PLAN_PATH)
        with tempfile.TemporaryDirectory() as tmp:
            store = DocumentStore(Path(tmp) / "t.sqlite3")
            CollectionController(store, [SampleCollector(SAMPLE_DIR)]).run(plan)
            analysis = compare_segments(list(store.documents()), "korean", "foreign")
            self.assertGreater(analysis["segments"]["korean"]["documents"], 0)
            self.assertGreater(analysis["segments"]["foreign"]["documents"], 0)
            self.assertTrue(analysis["overlap"]["shared_places"])
            self.assertTrue(analysis["distinctive_terms"]["korean"])
            self.assertTrue(analysis["distinctive_terms"]["foreign"])
            store.close()


class AgentTests(unittest.TestCase):
    def test_full_agent_chain_writes_artifacts(self):
        plan = ResearchPlan.load(PLAN_PATH)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            store = DocumentStore(tmp_path / "t.sqlite3")
            ctx = AgentContext(
                plan=plan, store=store, output_dir=tmp_path / "out", logger=lambda _m: None
            )
            self.assertTrue(ResearchAgent(sources=["sample"]).run(ctx).ok)
            self.assertTrue(ContestAgent(deadline="2026-06-30").run(ctx).ok)
            self.assertTrue(BookAgent().run(ctx).ok)

            for expected in [
                "analysis.json",
                "report/과제_리포트.md",
                "contest/제안서.md",
                "contest/일정.md",
                "book/목차.md",
                "book/chapters/03_두_개의_식탁.md",
            ]:
                self.assertTrue((ctx.output_dir / expected).exists(), expected)
            store.close()

    def test_agent_stops_on_failed_step(self):
        plan = ResearchPlan.load(PLAN_PATH)
        plan.segments = plan.segments[:1]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            store = DocumentStore(tmp_path / "t.sqlite3")
            ctx = AgentContext(
                plan=plan, store=store, output_dir=tmp_path / "out", logger=lambda _m: None
            )
            run = ResearchAgent(sources=["sample"]).run(ctx)
            self.assertFalse(run.ok)
            self.assertEqual(len(run.results), 1)
            store.close()


if __name__ == "__main__":
    unittest.main()
