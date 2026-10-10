"""공공데이터 결합·지도 시각화 에이전트."""

from __future__ import annotations

from ..analysis.geo import regional_join, render_geo_report, render_map_html
from ..public_data import load_region_stats
from .base import Agent, AgentContext, Step, StepResult

GEO_DIR = "geo"


class GeoAgent(Agent):
    name = "geo_agent"
    description = "등록외국인 통계와 결합해 생활권 지도를 만드는 에이전트"
    continue_on_error = False

    def __init__(
        self,
        stats_path: str | None = None,
        coords_path: str | None = None,
        min_mentions: int = 4,
    ) -> None:
        self.stats_path = stats_path
        self.coords_path = coords_path
        self.min_mentions = min_mentions

    def steps(self) -> list[Step]:
        return [
            Step("load_public_data", "공공데이터 로드", self._load),
            Step("join", "지역별 언급 분포와 통계 결합", self._join),
            Step("map", "Leaflet 지도 생성", self._map),
            Step("report", "결합 리포트 생성", self._report),
        ]

    def _load(self, ctx: AgentContext) -> StepResult:
        stats = load_region_stats(self.stats_path, self.coords_path)
        if not stats:
            return StepResult(
                "load_public_data",
                False,
                "공공데이터를 찾지 못했습니다. data/public/foreign_residents.csv 를 확인하세요.",
            )
        ctx.data["region_stats"] = stats
        with_coords = sum(1 for s in stats.values() if s.lat is not None)
        return StepResult(
            "load_public_data", True, f"지역 {len(stats)}곳 (좌표 보유 {with_coords}곳)"
        )

    def _join(self, ctx: AgentContext) -> StepResult:
        names = ctx.plan.segment_names()
        if len(names) < 2:
            return StepResult("join", False, "비교 집단이 2개 미만입니다.")
        geo = regional_join(
            ctx.store.documents(),
            ctx.data["region_stats"],
            names[0],
            names[1],
            min_mix_mentions=self.min_mentions,
        )
        geo["region_stats"] = {k: v.to_dict() for k, v in ctx.data["region_stats"].items()}
        ctx.data["geo"] = geo
        path = ctx.write_json(f"{GEO_DIR}/geo_analysis.json", geo)
        corr = geo["correlation_resident_vs_mention_share"]
        return StepResult(
            "join",
            True,
            f"지역 {len(geo['regions'])}곳 결합 / 통계 매칭 {geo['matched_regions']}곳 / "
            f"상관계수 {corr if corr is not None else 'N/A'}",
            [str(path)],
        )

    def _map(self, ctx: AgentContext) -> StepResult:
        geo = ctx.data["geo"]
        labels = self._labels(ctx)
        html = render_map_html(geo, f"{ctx.plan.topic} — 생활권 지도", labels)
        path = ctx.write(f"{GEO_DIR}/생활권지도.html", html)
        plotted = sum(1 for r in geo["regions"] if r["lat"] is not None)
        return StepResult("map", True, f"지도 마커 {plotted}개", [str(path)])

    def _report(self, ctx: AgentContext) -> StepResult:
        geo = ctx.data["geo"]
        md = render_geo_report(geo, self._labels(ctx))
        path = ctx.write(f"{GEO_DIR}/공공데이터_결합.md", md)
        return StepResult("report", True, "결합 리포트 생성", [str(path)])

    def _labels(self, ctx: AgentContext) -> tuple[str, str]:
        names = ctx.plan.segment_names()
        return ctx.plan.label_of(names[0]), ctx.plan.label_of(names[1])
