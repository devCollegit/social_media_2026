"""공모전 출품 에이전트.

분석 산출물(analysis.json)을 받아 공모전 제출에 필요한 문서 세트를 만든다.
- 제안서(요약/문제정의/방법/결과/기대효과)
- 심사기준 자가점검 체크리스트
- 제출 일정(역산 스케줄)
"""

from __future__ import annotations

from datetime import date, timedelta

from .base import Agent, AgentContext, Step, StepResult

CONTEST_DIR = "contest"

# 다수 공공·데이터 분석 공모전에서 공통으로 쓰이는 평가 항목
JUDGING_CRITERIA = [
    ("문제 정의의 타당성", 20, "사회적 필요성과 데이터로 풀 수 있는 문제임을 제시했는가"),
    ("데이터 활용 적절성", 25, "수집 경로가 합법적이고 재현 가능하며 규모가 충분한가"),
    ("분석 방법의 적합성", 25, "지표 선택과 비교 설계가 연구 질문에 대응하는가"),
    ("결과 해석 및 시각화", 15, "핵심 메시지가 한눈에 전달되는가"),
    ("활용 가능성", 15, "정책·서비스로 이어질 구체적 제안이 있는가"),
]

MILESTONES = [
    (42, "주제 확정 및 역할 분담", "팀 전원"),
    (35, "수집 파이프라인 안정화 / 1차 데이터 확보", "크롤링 담당"),
    (28, "전처리·감성사전 고도화", "분석 담당"),
    (21, "핵심 분석 결과 도출 및 가설 검증", "분석 담당"),
    (14, "시각화 및 스토리라인 확정", "발표자료 담당"),
    (7, "제안서 초안 완성 및 내부 리뷰", "팀 전원"),
    (3, "발표 리허설 및 Q&A 대비", "발표 담당"),
    (0, "최종 제출", "팀장"),
]


class ContestAgent(Agent):
    name = "contest_agent"
    description = "분석 결과를 공모전 제출물로 패키징하는 에이전트"
    continue_on_error = True

    def __init__(self, contest_name: str = "데이터 분석 공모전", deadline: str | None = None) -> None:
        self.contest_name = contest_name
        self.deadline = date.fromisoformat(deadline) if deadline else date.today() + timedelta(days=42)

    def steps(self) -> list[Step]:
        return [
            Step("proposal", "제안서 초안 작성", self._proposal),
            Step("checklist", "심사기준 자가점검표 작성", self._checklist),
            Step("schedule", "제출 역산 일정 수립", self._schedule),
        ]

    def _proposal(self, ctx: AgentContext) -> StepResult:
        analysis = ctx.data.get("analysis") or ctx.read_json("analysis.json")
        geo = ctx.data.get("geo")
        if geo is None:
            try:
                geo = ctx.read_json("geo/geo_analysis.json")
            except FileNotFoundError:
                geo = None
        md = render_proposal(analysis, self.contest_name, self.deadline, geo)
        path = ctx.write(f"{CONTEST_DIR}/제안서.md", md)
        return StepResult("proposal", True, "제안서 초안 생성", [str(path)])

    def _checklist(self, ctx: AgentContext) -> StepResult:
        lines = [f"# {self.contest_name} 자가점검 체크리스트\n", "| 평가 항목 | 배점 | 확인 사항 | 상태 |", "|---|---|---|---|"]
        for name, weight, desc in JUDGING_CRITERIA:
            lines.append(f"| {name} | {weight} | {desc} | ☐ |")
        lines.append("\n## 제출물 점검\n")
        for item in [
            "제안서 PDF (분량 제한 확인)",
            "발표자료 (PPT/PDF)",
            "분석 코드 저장소 링크 및 README",
            "데이터 출처·라이선스 명시",
            "개인정보 비식별 처리 확인",
            "팀원 전원 참가 동의서",
        ]:
            lines.append(f"- [ ] {item}")
        path = ctx.write(f"{CONTEST_DIR}/체크리스트.md", "\n".join(lines) + "\n")
        return StepResult("checklist", True, f"점검 항목 {len(JUDGING_CRITERIA) + 6}개", [str(path)])

    def _schedule(self, ctx: AgentContext) -> StepResult:
        lines = [
            f"# {self.contest_name} 역산 일정\n",
            f"- 마감일: **{self.deadline.isoformat()}**\n",
            "| D- | 날짜 | 마일스톤 | 담당 |",
            "|---|---|---|---|",
        ]
        for days, title, owner in MILESTONES:
            when = self.deadline - timedelta(days=days)
            lines.append(f"| D-{days} | {when.isoformat()} | {title} | {owner} |")
        path = ctx.write(f"{CONTEST_DIR}/일정.md", "\n".join(lines) + "\n")
        return StepResult("schedule", True, f"마일스톤 {len(MILESTONES)}개", [str(path)])


def render_proposal(
    analysis: dict, contest_name: str, deadline: date, geo: dict | None = None
) -> str:
    segments = analysis["segments"]
    names = list(segments)
    a, b = names[0], names[1]
    la, lb = segments[a]["label"], segments[b]["label"]
    overlap = analysis["overlap"]
    candidates = analysis.get("exchange_candidates", [])
    total_docs = sum(segments[n]["documents"] for n in names)

    top = lambda n: ", ".join(t["term"] for t in segments[n]["top_terms"][:8]) or "-"
    distinct = lambda n: ", ".join(t["term"] for t in analysis["distinctive_terms"][n][:8]) or "-"

    return f"""# {contest_name} 제안서

**주제** {analysis.get('topic', '')}
**제출 예정일** {deadline.isoformat()}

## 1. 한 줄 요약

소셜미디어 게시물과 장소 리뷰를 수집해 {la}과 {lb}의 생활권 분리 정도를 정량화하고,
두 집단이 함께 이용하는 '교류 공간'의 조건을 도출한다.

## 2. 문제 정의

국내 체류 외국인은 꾸준히 증가하고 있으나, 내국인과 외국인이 자연스럽게 마주치는
생활 공간은 제한적이다. 기존 통계는 '어디에 사는가'는 보여주지만 '어디서 함께
시간을 보내는가'는 설명하지 못한다. 본 과제는 소셜 데이터를 통해 이 공백을 메운다.

## 3. 연구 질문

{analysis.get('question', '')}

## 4. 데이터 및 수집 방법

- 수집 대상: 소셜미디어 게시물, 장소 리뷰, 지역 검색 결과
- 수집 규모: 현재 {total_docs:,}건 (집단별 {', '.join(f"{segments[n]['label']} {segments[n]['documents']}건" for n in names)})
- 수집 구조: 다중 수집기(Collector) + 수집 컨트롤러(호출 간격 제어·재시도·중복 제거·SQLite 적재)
- 재현성: 검색어·소스 정의를 설정 파일로 분리해 동일 조건 재수집 가능

## 5. 분석 방법

1. 한국어·영어 혼합 토크나이저로 키워드 빈도 추출
2. 로그 오즈비(z-score)로 집단별 변별 키워드 도출
3. 사전 기반 감성 점수로 만족/불만 요인 비교
4. 장소·지역 집합의 자카드 유사도로 생활권 겹침 정량화

## 6. 현재까지의 결과

| 항목 | 값 |
|---|---|
| 장소 겹침(자카드) | {overlap['place_jaccard']} |
| 지역 겹침(자카드) | {overlap['region_jaccard']} |
| 공유 장소 수 | {len(overlap['shared_places'])} |
| {la} 전용 장소 | {len(overlap['only_a_places'])} |
| {lb} 전용 장소 | {len(overlap['only_b_places'])} |

- {la} 주요 키워드: {top(a)}
- {lb} 주요 키워드: {top(b)}
- {la} 변별 키워드: {distinct(a)}
- {lb} 변별 키워드: {distinct(b)}
- 교류 공간 후보 상위: {', '.join(c['place'] for c in candidates[:5]) or '추가 수집 필요'}

{_geo_section(geo, la, lb)}## 7. 기대 효과 및 활용 방안

- **지자체**: 다문화 정책 예산을 '겹침이 높은 지역'에 우선 배분하는 근거 자료
- **상권**: 외국인 유입 가능성이 높은 업종·입지 조건 제시
- **시민 사회**: 교류 프로그램 시범 운영지 선정 기준 제공

## 8. 추진 일정

`일정.md` 참조 (마감 역산 기준).

## 9. 역할 분담

| 역할 | 담당 | 산출물 |
|---|---|---|
| 데이터 수집·DB | | 수집 파이프라인, 적재 DB |
| 분석·모델링 | | 분석 노트북, 지표 정의서 |
| 시각화·발표자료 | | 대시보드, 발표 슬라이드 |
| 발표 | | 발표 스크립트, Q&A 대응 |

## 10. 윤리 및 준수 사항

- 공개된 API와 robots.txt 허용 범위 내에서만 수집
- 작성자 식별 정보는 저장하지 않으며 분석 단위는 문서 집계값
- 특정 국적·집단에 대한 가치 판단이 아닌 공간 이용 패턴 기술에 한정
"""


def _geo_section(geo: dict | None, label_a: str, label_b: str) -> str:
    """공공데이터 결합 결과가 있으면 제안서에 끼워 넣는다."""
    if not geo or not geo.get("regions"):
        return ""

    corr = geo.get("correlation_resident_vs_mention_share")
    gaps = [r for r in geo["regions"] if r.get("gap") is not None]
    over = sorted(gaps, key=lambda r: -r["gap"])[:3]
    under = sorted(gaps, key=lambda r: r["gap"])[:3]
    top_mix = geo.get("top_mix_regions", [])[:5]

    lines = [
        "## 6-1. 공공데이터 결합 결과\n",
        "등록외국인 통계와 결합해 '사는 곳'과 '활동하는 곳'의 차이를 확인했다.\n",
        f"- 분석 지역 {len(geo['regions'])}곳 (공공통계 매칭 {geo.get('matched_regions', 0)}곳)",
    ]
    if corr is not None:
        lines.append(f"- 거주 분포와 {label_b} 언급 분포의 상관계수: **{corr}**")
    if over:
        lines.append(
            "- 거주 대비 활동이 많은 지역: "
            + ", ".join(f"{r['region']}({r['gap']:+})" for r in over)
        )
    if under:
        lines.append(
            "- 거주 대비 활동이 적은 지역: "
            + ", ".join(f"{r['region']}({r['gap']:+})" for r in under)
        )
    if top_mix:
        lines.append(
            f"- {label_a}·{label_b} 언급이 가장 고른 지역: "
            + ", ".join(f"{r['region']}({r['mix_index']})" for r in top_mix)
        )
    lines.append("\n제출 시 `outputs/geo/생활권지도.html` 을 인터랙티브 지도로 함께 첨부한다.\n")
    return "\n".join(lines) + "\n"
