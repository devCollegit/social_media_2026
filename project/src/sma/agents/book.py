"""집필 에이전트.

분석 결과를 장기 산출물(책 원고)로 확장한다.
- 기획안(독자·포지셔닝·분량)
- 목차
- 장별 초고 스켈레톤(근거 데이터가 자동으로 주입된 상태)
- 집필 일정
"""

from __future__ import annotations

from datetime import date, timedelta

from .base import Agent, AgentContext, Step, StepResult

BOOK_DIR = "book"

CHAPTERS = [
    (
        "1장. 보이지 않는 경계선",
        "같은 도시에 살지만 서로 다른 지도를 쓰는 사람들",
        ["문제 제기", "왜 통계로는 보이지 않는가", "이 책이 다루는 범위"],
    ),
    (
        "2장. 데이터로 도시를 읽는 법",
        "소셜 데이터가 생활권을 드러내는 원리",
        ["소셜 데이터의 성격과 한계", "수집 파이프라인 설계", "윤리와 합법성의 선"],
    ),
    (
        "3장. 두 개의 식탁",
        "집단별 장소 선택과 키워드 차이",
        ["집단별 상위 키워드", "변별 키워드가 말해 주는 것", "가격·메뉴·언어의 장벽"],
    ),
    (
        "4장. 만족과 불만의 지형",
        "감성 분석으로 본 경험의 차이",
        ["감성 분포 비교", "불만의 언어", "환대의 언어"],
    ),
    (
        "5장. 겹치는 자리",
        "교류가 실제로 일어나는 공간의 조건",
        ["겹침 지표 읽기", "공유 장소의 공통 속성", "실패한 접점"],
    ),
    (
        "6장. 섞이는 도시를 설계하기",
        "정책·상권·커뮤니티를 위한 제안",
        ["지자체를 위한 제안", "자영업자를 위한 제안", "시민 사회를 위한 제안"],
    ),
    (
        "7장. 직접 해보기",
        "독자가 자신의 도시에서 재현하는 방법",
        ["환경 준비", "수집 설정 바꾸기", "결과 해석 가이드"],
    ),
]


class BookAgent(Agent):
    name = "book_agent"
    description = "분석 결과를 단행본 원고 구조로 확장하는 에이전트"
    continue_on_error = True

    def __init__(self, title: str = "섞이지 않는 도시", months: int = 6) -> None:
        self.title = title
        self.months = months

    def steps(self) -> list[Step]:
        return [
            Step("concept", "기획안 작성", self._concept),
            Step("outline", "목차 구성", self._outline),
            Step("drafts", "장별 초고 스켈레톤 생성", self._drafts),
            Step("schedule", "집필 일정 수립", self._schedule),
        ]

    def _concept(self, ctx: AgentContext) -> StepResult:
        analysis = ctx.data.get("analysis") or ctx.read_json("analysis.json")
        segments = analysis["segments"]
        names = list(segments)
        total = sum(segments[n]["documents"] for n in names)
        md = f"""# 『{self.title}』 기획안

## 콘셉트

{analysis.get('topic', '')}를 소재로, 데이터 분석 과정을 서사로 풀어내는 논픽션.
독자는 결과만이 아니라 '어떻게 알아냈는가'를 따라오며 스스로 재현할 수 있다.

## 핵심 메시지

같은 도시에 살아도 사람들은 서로 다른 지도를 쓴다. 그 지도가 겹치는 지점이
어디인지 알면, 섞이는 도시를 설계할 수 있다.

## 예상 독자

- 도시·이주·다문화 정책에 관심 있는 일반 독자
- 데이터 분석을 실제 사회 문제에 적용해 보고 싶은 입문자
- 지역 상권·커뮤니티 기획자

## 근거 데이터

- 분석 문서 {total:,}건
- 장소 겹침 지표 {analysis['overlap']['place_jaccard']}, 지역 겹침 지표 {analysis['overlap']['region_jaccard']}
- 교류 공간 후보 {len(analysis.get('exchange_candidates', []))}곳

## 분량 및 형식

- 7장 구성, 장당 원고지 120~150매 (총 약 900매)
- 각 장 말미에 '데이터 노트' 박스: 사용한 지표와 코드 위치 안내
- 부록: 수집 설정 파일 예시, 재현 절차

## 차별점

- 결과 소개형 교양서가 아니라, 공개 코드와 함께 재현 가능한 분석서
- 집단 간 우열이 아닌 '공간 이용 패턴' 기술에 집중해 윤리적 안전성 확보
"""
        path = ctx.write(f"{BOOK_DIR}/기획안.md", md)
        return StepResult("concept", True, "기획안 생성", [str(path)])

    def _outline(self, ctx: AgentContext) -> StepResult:
        lines = [f"# 『{self.title}』 목차\n"]
        for title, subtitle, sections in CHAPTERS:
            lines.append(f"## {title} — {subtitle}")
            for i, section in enumerate(sections, 1):
                lines.append(f"{i}. {section}")
            lines.append("")
        path = ctx.write(f"{BOOK_DIR}/목차.md", "\n".join(lines))
        return StepResult("outline", True, f"{len(CHAPTERS)}개 장 구성", [str(path)])

    def _drafts(self, ctx: AgentContext) -> StepResult:
        analysis = ctx.data.get("analysis") or ctx.read_json("analysis.json")
        artifacts = []
        for index, (title, subtitle, sections) in enumerate(CHAPTERS, 1):
            body = [f"# {title}\n", f"> {subtitle}\n"]
            for section in sections:
                body.append(f"## {section}\n")
                body.append("<!-- 본문 작성 영역 -->\n")
            body.append("## 데이터 노트\n")
            body.append(_data_note(index, analysis))
            path = ctx.write(f"{BOOK_DIR}/chapters/{index:02d}_{_slug(title)}.md", "\n".join(body))
            artifacts.append(str(path))
        return StepResult("drafts", True, f"{len(artifacts)}개 장 스켈레톤", artifacts)

    def _schedule(self, ctx: AgentContext) -> StepResult:
        start = date.today()
        weeks_per_chapter = max(1, (self.months * 4) // (len(CHAPTERS) + 2))
        lines = [
            f"# 『{self.title}』 집필 일정\n",
            f"- 시작: {start.isoformat()} / 목표 기간: {self.months}개월\n",
            "| 단계 | 기간 | 산출물 |",
            "|---|---|---|",
        ]
        cursor = start
        plan = [("자료 보강 수집", 2)] + [(t, weeks_per_chapter) for t, _, _ in CHAPTERS] + [("전체 교정·퇴고", 4)]
        for title, weeks in plan:
            end = cursor + timedelta(weeks=weeks)
            lines.append(f"| {title} | {cursor.isoformat()} ~ {end.isoformat()} | 초고 |")
            cursor = end
        lines.append(f"\n- 예상 탈고일: **{cursor.isoformat()}**\n")
        path = ctx.write(f"{BOOK_DIR}/집필일정.md", "\n".join(lines))
        return StepResult("schedule", True, f"탈고 예정 {cursor.isoformat()}", [str(path)])


def _data_note(chapter: int, analysis: dict) -> str:
    segments = analysis["segments"]
    names = list(segments)
    a, b = names[0], names[1]
    overlap = analysis["overlap"]
    if chapter == 3:
        return (
            f"- {segments[a]['label']} 변별 키워드: "
            + ", ".join(t["term"] for t in analysis["distinctive_terms"][a][:8])
            + f"\n- {segments[b]['label']} 변별 키워드: "
            + ", ".join(t["term"] for t in analysis["distinctive_terms"][b][:8])
            + "\n- 산출 방법: 로그 오즈비(z-score), `sma.analysis.compare`\n"
        )
    if chapter == 4:
        return "\n".join(
            f"- {segments[n]['label']} 평균 감성 {segments[n]['sentiment']['mean_score']} "
            f"(긍정 {segments[n]['sentiment']['distribution'].get('positive', 0)} / "
            f"부정 {segments[n]['sentiment']['distribution'].get('negative', 0)})"
            for n in names
        ) + "\n- 산출 방법: 사전 기반 감성 점수, `sma.analysis.sentiment`\n"
    if chapter == 5:
        candidates = analysis.get("exchange_candidates", [])
        return (
            f"- 장소 자카드 {overlap['place_jaccard']} / 지역 자카드 {overlap['region_jaccard']}\n"
            f"- 공유 장소 상위: {', '.join(c['place'] for c in candidates[:5]) or '추가 수집 필요'}\n"
        )
    if chapter == 2:
        return "- 수집 구조: `sma.controllers.CollectionController` + 다중 Collector\n- 적재: SQLite `documents` 테이블\n"
    total = sum(segments[n]["documents"] for n in names)
    return f"- 전체 분석 문서 {total:,}건\n"


def _slug(title: str) -> str:
    return title.split(".", 1)[-1].strip().replace(" ", "_")
