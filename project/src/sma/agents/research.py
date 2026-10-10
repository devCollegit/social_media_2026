"""개인과제 수행 에이전트.

조현호 아이디어 "국내 거주 외국인과 내국인의 생활권 및 교류 공간 분석" 을
계획 점검 → 수집 → 분석 → 리포트 → 다음 액션 제안 순서로 자동 수행한다.
"""

from __future__ import annotations

from ..analysis.compare import compare_segments, exchange_candidates
from ..collectors import default_collectors
from ..controllers import CollectionController
from .base import Agent, AgentContext, Step, StepResult

ANALYSIS_FILE = "analysis.json"
REPORT_FILE = "report/과제_리포트.md"


def _table(rows: list[list[str]], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


class ResearchAgent(Agent):
    name = "research_agent"
    description = "개인과제(사회 집단 비교 분석)를 끝까지 수행하는 에이전트"
    continue_on_error = False

    def __init__(self, sources: list[str] | None = None, skip_collect: bool = False) -> None:
        self.sources = sources
        self.skip_collect = skip_collect

    def steps(self) -> list[Step]:
        return [
            Step("plan_check", "연구 질문과 수집 계획 점검", self._plan_check),
            Step("collect", "소셜 데이터 수집 (컨트롤러 위임)", self._collect),
            Step("analyze", "집단 비교 분석 수행", self._analyze),
            Step("report", "마크다운 리포트 생성", self._report),
            Step("next_actions", "후속 과제 제안", self._next_actions),
        ]

    # --- steps --------------------------------------------------------
    def _plan_check(self, ctx: AgentContext) -> StepResult:
        plan = ctx.plan
        issues = []
        if len(plan.segments) < 2:
            issues.append("비교 집단이 2개 미만입니다.")
        for segment in plan.segments:
            if not segment.queries:
                issues.append(f"'{segment.name}' 집단에 검색어가 없습니다.")
            if not segment.sources:
                issues.append(f"'{segment.name}' 집단에 수집 소스가 없습니다.")
        if issues:
            return StepResult("plan_check", False, "; ".join(issues))

        path = ctx.write_json(
            "plan_snapshot.json",
            {
                "topic": plan.topic,
                "question": plan.question,
                "regions": plan.regions,
                "segments": [
                    {"name": s.name, "label": s.label, "queries": s.queries, "sources": s.sources}
                    for s in plan.segments
                ],
                "tasks": len(plan.tasks(self.sources)),
            },
        )
        return StepResult(
            "plan_check",
            True,
            f"집단 {len(plan.segments)}개 / 작업 {len(plan.tasks(self.sources))}건 확인",
            [str(path)],
        )

    def _collect(self, ctx: AgentContext) -> StepResult:
        if self.skip_collect:
            return StepResult(
                "collect", True, f"수집 생략 (기존 {ctx.store.count()}건 사용)"
            )
        controller = CollectionController(
            ctx.store, default_collectors(), logger=lambda m: ctx.logger("    " + m)
        )
        report = controller.run(ctx.plan, self.sources)
        ctx.data["collection_report"] = report
        path = ctx.write_json("collection_report.json", report.to_dict())
        if ctx.store.count() == 0:
            return StepResult(
                "collect",
                False,
                "수집 결과가 0건입니다. 샘플 데이터나 API 키를 확인하세요.",
                [str(path)],
            )
        return StepResult(
            "collect",
            True,
            f"신규 {report.stored}건 저장 / 중복 {report.duplicated}건 / 누적 {ctx.store.count()}건",
            [str(path)],
        )

    def _analyze(self, ctx: AgentContext) -> StepResult:
        names = ctx.plan.segment_names()
        a, b = names[0], names[1]
        labels = {n: ctx.plan.label_of(n) for n in names}
        analysis = compare_segments(list(ctx.store.documents()), a, b, labels)
        analysis["topic"] = ctx.plan.topic
        analysis["question"] = ctx.plan.question
        analysis["exchange_candidates"] = exchange_candidates(analysis)
        ctx.data["analysis"] = analysis
        path = ctx.write_json(ANALYSIS_FILE, analysis)
        overlap = analysis["overlap"]["place_jaccard"]
        return StepResult(
            "analyze",
            True,
            f"장소 겹침(자카드) {overlap} / 교류 후보 {len(analysis['exchange_candidates'])}곳",
            [str(path)],
        )

    def _report(self, ctx: AgentContext) -> StepResult:
        analysis = ctx.data.get("analysis") or ctx.read_json(ANALYSIS_FILE)
        md = render_report(analysis)
        path = ctx.write(REPORT_FILE, md)
        return StepResult("report", True, f"리포트 {len(md)}자 생성", [str(path)])

    def _next_actions(self, ctx: AgentContext) -> StepResult:
        analysis = ctx.data.get("analysis") or ctx.read_json(ANALYSIS_FILE)
        overlap = analysis["overlap"]["place_jaccard"]
        actions = [
            "수집 기간을 분기 단위로 나눠 시계열 변화(교류 공간 증가/감소)를 확인한다.",
            "감성 사전을 KNU 감성사전 또는 KoBERT 기반 모델로 교체해 베이스라인과 비교한다.",
            "공공데이터(행정안전부 등록외국인 통계)와 결합해 생활권 지도를 작성한다.",
        ]
        if overlap < 0.2:
            actions.insert(0, "두 집단의 장소 겹침이 매우 낮다 → '분리된 생활권' 가설을 주요 논지로 삼는다.")
        else:
            actions.insert(0, "겹치는 장소가 상당하다 → 공유 장소의 공통 속성(가격대·메뉴·언어 지원)을 심층 분석한다.")
        path = ctx.write(
            "next_actions.md",
            "# 다음 액션\n\n" + "\n".join(f"{i}. {a}" for i, a in enumerate(actions, 1)) + "\n",
        )
        return StepResult("next_actions", True, f"{len(actions)}개 제안", [str(path)])


def render_report(analysis: dict) -> str:
    segments = analysis["segments"]
    names = list(segments)
    a, b = names[0], names[1]
    la, lb = segments[a]["label"], segments[b]["label"]
    overlap = analysis["overlap"]

    out: list[str] = []
    out.append(f"# {analysis.get('topic', '소셜미디어 분석 리포트')}\n")
    out.append(f"> 연구 질문: {analysis.get('question', '')}\n")

    out.append("## 1. 수집 개요\n")
    out.append(
        _table(
            [
                [
                    segments[n]["label"],
                    segments[n]["documents"],
                    ", ".join(f"{k}({v})" for k, v in segments[n]["sources"].items()) or "-",
                    segments[n]["mean_rating"] if segments[n]["mean_rating"] is not None else "-",
                ]
                for n in names
            ],
            ["집단", "문서 수", "소스", "평균 평점"],
        )
    )

    out.append("\n## 2. 집단별 주요 키워드\n")
    for n in names:
        terms = ", ".join(f"{t['term']}({t['count']})" for t in segments[n]["top_terms"][:12])
        out.append(f"- **{segments[n]['label']}**: {terms or '데이터 부족'}")

    out.append("\n## 3. 변별 키워드 (로그 오즈비 z-score)\n")
    terms_a = analysis["distinctive_terms"][a]
    terms_b = analysis["distinctive_terms"][b]
    rows = [
        [_format_term(terms_a, i), _format_term(terms_b, i)]
        for i in range(max(len(terms_a), len(terms_b), 1))
    ][:10]
    out.append(_table(rows, [f"{la} 특징어", f"{lb} 특징어"]))

    out.append("\n## 4. 감성 분포\n")
    out.append(
        _table(
            [
                [
                    segments[n]["label"],
                    segments[n]["sentiment"]["count"],
                    segments[n]["sentiment"]["mean_score"],
                    segments[n]["sentiment"].get("distribution", {}).get("positive", 0),
                    segments[n]["sentiment"].get("distribution", {}).get("neutral", 0),
                    segments[n]["sentiment"].get("distribution", {}).get("negative", 0),
                ]
                for n in names
            ],
            ["집단", "문서", "평균 점수", "긍정", "중립", "부정"],
        )
    )

    out.append("\n## 5. 생활권 겹침\n")
    out.append(f"- 장소 자카드 유사도: **{overlap['place_jaccard']}**")
    out.append(f"- 지역 자카드 유사도: **{overlap['region_jaccard']}**")
    out.append(f"- 공유 지역: {', '.join(overlap['shared_regions']) or '없음'}")
    out.append(f"- {la} 전용 장소 {len(overlap['only_a_places'])}곳 / {lb} 전용 장소 {len(overlap['only_b_places'])}곳")

    out.append("\n## 6. 교류 공간 후보\n")
    candidates = analysis.get("exchange_candidates", [])
    if candidates:
        out.append(
            _table([[i, c["place"], c["mentions"]] for i, c in enumerate(candidates, 1)],
                   ["순위", "장소", "언급 수"])
        )
    else:
        out.append("두 집단이 함께 언급한 장소가 아직 없습니다. 수집 범위를 넓혀 주세요.")

    out.append("\n## 7. 해석 메모\n")
    out.append(
        f"- {la}과 {lb}의 장소 겹침이 {overlap['place_jaccard']} 수준으로, "
        f"{'생활권이 상당히 분리되어 있다' if overlap['place_jaccard'] < 0.2 else '일정 부분 생활권을 공유한다'}고 볼 수 있다."
    )
    out.append("- 변별 키워드는 두 집단이 같은 공간에서도 서로 다른 가치를 소비하고 있음을 시사한다.")
    out.append("- 공유 장소 목록은 교류 프로그램을 시범 운영할 1순위 후보지로 활용할 수 있다.\n")
    return "\n".join(out)


def _format_term(items: list, index: int) -> str:
    if index >= len(items):
        return "-"
    item = items[index]
    return f"{item['term']} ({item['z']})"
