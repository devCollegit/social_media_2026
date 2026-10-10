"""키워드 보정 · 공공데이터 결합 테스트.

실행: python3 -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sma.agents import GeoAgent, TuningAgent  # noqa: E402
from sma.agents.base import AgentContext  # noqa: E402
from sma.analysis import text as text_mod  # noqa: E402
from sma.analysis.geo import (  # noqa: E402
    pearson,
    regional_join,
    render_geo_report,
    render_map_html,
)
from sma.analysis.tuning import sample_balance, suggest_stopwords  # noqa: E402
from sma.collectors import SampleCollector  # noqa: E402
from sma.config import ResearchPlan  # noqa: E402
from sma.controllers import CollectionController  # noqa: E402
from sma.models import Document  # noqa: E402
from sma.public_data import RegionStat, load_region_stats  # noqa: E402
from sma.storage import DocumentStore  # noqa: E402

PLAN_PATH = ROOT / "config" / "research_plan.json"
SAMPLE_DIR = ROOT / "data" / "samples"
STOPWORDS_PATH = ROOT / "config" / "stopwords.txt"


def _doc(segment: str, text: str, region: str = "", place: str = "") -> Document:
    return Document(
        source="t",
        query="q",
        segment=segment,
        text=text,
        region=region,
        place_name=place,
        url=f"http://x/{abs(hash((segment, text, region, place)))}",
    )


class StopwordConfigTests(unittest.TestCase):
    def tearDown(self):
        text_mod.reset_stopwords()

    def test_loaded_file_extends_base_stopwords(self):
        text_mod.reset_stopwords()
        self.assertNotIn("다녀왔어요", text_mod.active_stopwords())
        text_mod.load_stopwords(STOPWORDS_PATH)
        self.assertIn("다녀왔어요", text_mod.active_stopwords())
        self.assertIn("그리고", text_mod.active_stopwords())
        self.assertNotIn("다녀왔어요", text_mod.tokenize("성수동 다녀왔어요"))

    def test_replace_mode_drops_base_stopwords(self):
        text_mod.load_stopwords(STOPWORDS_PATH, replace=True)
        self.assertNotIn("그리고", text_mod.active_stopwords())

    def test_missing_file_is_ignored(self):
        text_mod.reset_stopwords()
        before = text_mod.active_stopwords()
        text_mod.load_stopwords(ROOT / "config" / "nope.txt")
        self.assertEqual(before, text_mod.active_stopwords())


class StopwordSuggestionTests(unittest.TestCase):
    def tearDown(self):
        text_mod.reset_stopwords()

    def test_common_terms_are_suggested_and_distinctive_terms_are_not(self):
        docs = []
        for i in range(6):
            docs.append(_doc("korean", f"공통단어 공통단어 내국인전용 사례{i}"))
            docs.append(_doc("foreign", f"공통단어 공통단어 외국인전용 사례{i}"))
        candidates = suggest_stopwords(docs, "korean", "foreign", min_total=4)
        terms = {c["term"] for c in candidates}
        self.assertIn("공통단어", terms)
        self.assertNotIn("내국인전용", terms)

    def test_terms_frequent_in_both_segments_are_flagged_by_document_frequency(self):
        docs = [_doc("korean", f"상투어 고유{i}") for i in range(8)]
        docs += [_doc("foreign", f"상투어 unique{i}") for i in range(8)]
        candidates = suggest_stopwords(docs, "korean", "foreign", min_total=99)
        reasons = {c["term"]: c["reason"] for c in candidates}
        self.assertIn("상투어", reasons)
        self.assertIn("문서빈도", reasons["상투어"])

    def test_segment_exclusive_term_is_not_flagged(self):
        """한쪽에서만 고빈도인 단어는 결론일 수 있으므로 후보에서 제외한다."""
        docs = [_doc("korean", f"내국인전용 고유{i}") for i in range(8)]
        docs += [_doc("foreign", f"english unique{i}") for i in range(8)]
        candidates = suggest_stopwords(docs, "korean", "foreign", min_total=99)
        terms = {c["term"] for c in candidates}
        self.assertNotIn("내국인전용", terms)
        self.assertNotIn("english", terms)

    def test_existing_stopwords_are_never_suggested(self):
        text_mod.add_stopwords(["공통단어"])
        docs = []
        for i in range(6):
            docs.append(_doc("korean", f"공통단어 공통단어 사례{i}"))
            docs.append(_doc("foreign", f"공통단어 공통단어 case{i}"))
        candidates = suggest_stopwords(docs, "korean", "foreign", min_total=4)
        self.assertNotIn("공통단어", {c["term"] for c in candidates})


class SampleBalanceTests(unittest.TestCase):
    def test_imbalanced_sample_produces_warnings(self):
        plan = ResearchPlan.load(PLAN_PATH)
        docs = [_doc("korean", f"문서 {i}") for i in range(30)]
        docs += [_doc("foreign", "only one doc")]
        balance = sample_balance(docs, plan)
        self.assertFalse(balance["balanced"])
        self.assertTrue(any("비대칭" in w for w in balance["warnings"]))

    def test_collection_report_drives_per_query_counts(self):
        plan = ResearchPlan.load(PLAN_PATH)
        report = {
            "task_stats": [
                {"segment": s.name, "query": q, "fetched": 10}
                for s in plan.segments
                for q in s.queries
            ]
        }
        # 저장된 문서는 없지만 수집 시도 기록이 있으면 빈 검색어로 보지 않는다
        balance = sample_balance([], plan, report)
        for profile in balance["segments"].values():
            self.assertEqual(profile["empty_queries"], [])
            self.assertEqual(profile["query_counts_source"], "수집 시도 기준")


class PublicDataTests(unittest.TestCase):
    def test_bundled_stats_load_with_coordinates(self):
        stats = load_region_stats()
        self.assertIn("서울 용산구", stats)
        yongsan = stats["서울 용산구"]
        self.assertGreater(yongsan.foreign_ratio, 0)
        self.assertIsNotNone(yongsan.lat)

    def test_foreign_ratio_handles_zero_population(self):
        self.assertEqual(RegionStat(region="x", population=0, foreign_residents=10).foreign_ratio, 0.0)


class GeoAnalysisTests(unittest.TestCase):
    def test_pearson_edge_cases(self):
        self.assertIsNone(pearson([1.0, 2.0], [1.0, 2.0]))
        self.assertIsNone(pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]))
        self.assertEqual(pearson([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]), 1.0)

    def test_regional_join_computes_shares_and_mix(self):
        stats = {
            "서울 용산구": RegionStat("서울 용산구", 100, 10, 37.5, 127.0),
            "서울 강남구": RegionStat("서울 강남구", 100, 10, 37.5, 127.1),
        }
        docs = [
            _doc("korean", "a", "서울 용산구 한남동", "공유식당"),
            _doc("foreign", "b", "서울 용산구 이태원", "공유식당"),
            _doc("foreign", "c", "서울 강남구 역삼동", "강남식당"),
            _doc("korean", "d", "서울 중구 을지로", "을지로집"),
        ]
        geo = regional_join(docs, stats, "korean", "foreign")
        by_region = {r["region"]: r for r in geo["regions"]}

        yongsan = by_region["서울 용산구"]
        self.assertEqual(yongsan["mix_index"], 1.0)
        self.assertEqual(yongsan["shared_places"], ["공유식당"])
        self.assertEqual(yongsan["mention_share_b"], 50.0)
        self.assertAlmostEqual(yongsan["resident_share"], 50.0)
        self.assertAlmostEqual(yongsan["gap"], 0.0)

        self.assertEqual(by_region["서울 강남구"]["mix_index"], 0.0)
        self.assertIn("서울 중구", geo["missing_stats"])
        self.assertIsNone(by_region["서울 중구"].get("gap"))
        self.assertEqual(geo["matched_regions"], 2)

    def test_min_mix_mentions_filters_thin_regions(self):
        """언급 1건씩만 있어도 교류 지수는 1.0이 된다. 순위에서 걸러져야 한다."""
        stats = {
            "서울 용산구": RegionStat("서울 용산구", 100, 10, 37.5, 127.0),
            "서울 강남구": RegionStat("서울 강남구", 100, 10, 37.5, 127.1),
        }
        docs = [
            _doc("korean", "a", "서울 용산구"),
            _doc("foreign", "b", "서울 용산구"),
            _doc("korean", "c", "서울 강남구"),
            _doc("korean", "d", "서울 강남구"),
            _doc("foreign", "e", "서울 강남구"),
            _doc("foreign", "f", "서울 강남구"),
        ]
        geo = regional_join(docs, stats, "korean", "foreign", min_mix_mentions=4)
        self.assertEqual([r["region"] for r in geo["top_mix_regions"]], ["서울 강남구"])

        loose = regional_join(docs, stats, "korean", "foreign", min_mix_mentions=1)
        self.assertEqual(len(loose["top_mix_regions"]), 2)

    def test_geo_report_explains_empty_mix_ranking(self):
        stats = {"서울 용산구": RegionStat("서울 용산구", 100, 10, 37.5, 127.0)}
        geo = regional_join(
            [_doc("korean", "a", "서울 용산구")], stats, "korean", "foreign", min_mix_mentions=4
        )
        report = render_geo_report(geo, ("내국인", "외국인"))
        self.assertEqual(geo["top_mix_regions"], [])
        self.assertIn("--min-mentions", report)

    def test_map_html_is_self_contained(self):
        stats = {"서울 용산구": RegionStat("서울 용산구", 100, 10, 37.5, 127.0)}
        geo = regional_join([_doc("korean", "a", "서울 용산구")], stats, "korean", "foreign")
        html = render_map_html(geo, "테스트 지도", ("내국인", "외국인"))
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("서울 용산구", html)
        self.assertIn("leaflet", html.lower())


class NewAgentTests(unittest.TestCase):
    def _context(self, tmp_path: Path) -> tuple[AgentContext, DocumentStore]:
        plan = ResearchPlan.load(PLAN_PATH)
        store = DocumentStore(tmp_path / "t.sqlite3")
        CollectionController(store, [SampleCollector(SAMPLE_DIR)]).run(plan)
        ctx = AgentContext(
            plan=plan, store=store, output_dir=tmp_path / "out", logger=lambda _m: None
        )
        return ctx, store

    def test_tuning_agent_writes_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, store = self._context(Path(tmp))
            self.assertTrue(TuningAgent().run(ctx).ok)
            for name in ["tuning/키워드_보정.md", "tuning/표본균형.json", "tuning/stopwords.suggested.txt"]:
                self.assertTrue((ctx.output_dir / name).exists(), name)
            store.close()

    def test_geo_agent_writes_map_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, store = self._context(Path(tmp))
            self.assertTrue(GeoAgent().run(ctx).ok)
            for name in ["geo/geo_analysis.json", "geo/생활권지도.html", "geo/공공데이터_결합.md"]:
                self.assertTrue((ctx.output_dir / name).exists(), name)
            store.close()

    def test_geo_agent_fails_clearly_without_public_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ctx, store = self._context(tmp_path)
            run = GeoAgent(stats_path=str(tmp_path / "missing.csv")).run(ctx)
            self.assertFalse(run.ok)
            self.assertIn("공공데이터", run.results[0].summary)
            store.close()


if __name__ == "__main__":
    unittest.main()
