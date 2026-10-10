"""명령행 진입점.

사용 예
    python -m sma status
    python -m sma collect --source sample
    python -m sma research
    python -m sma contest --name "2026 데이터 분석 공모전" --deadline 2026-06-30
    python -m sma book --title "섞이지 않는 도시"
    python -m sma all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .agents import BookAgent, ContestAgent, GeoAgent, ResearchAgent, TuningAgent
from .agents.base import AgentContext
from .analysis.text import load_stopwords
from .collectors import default_collectors
from .config import (
    DEFAULT_DB_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PLAN_PATH,
    DEFAULT_STOPWORDS_PATH,
    ResearchPlan,
)
from .collectors.base import CollectorError, CollectorUnavailable
from .collectors.naver import BACKENDS, DEFAULT_BACKEND, NaverBlogCollector
from .controllers import CollectionController
from .models import QueryTask
from .storage import DocumentStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sma", description="소셜미디어 분석 에이전트")
    parser.add_argument("--plan", default=str(DEFAULT_PLAN_PATH), help="연구 계획 JSON 경로")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite 경로")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR), help="산출물 디렉터리")
    parser.add_argument(
        "--stopwords", default=str(DEFAULT_STOPWORDS_PATH), help="추가 불용어 파일 경로"
    )
    parser.add_argument("--source", action="append", dest="sources", help="사용할 수집기 (반복 지정)")
    parser.add_argument("--quiet", action="store_true", help="로그 숨김")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="수집기 가용 상태와 적재 현황 확인")
    sub.add_parser("collect", help="수집만 실행")
    sub.add_parser("research", help="개인과제 에이전트 실행 (수집+분석+리포트)")
    sub.add_parser("analyze", help="기존 데이터로 분석/리포트만 재생성")

    tune = sub.add_parser("tune", help="불용어 후보 추출 및 표본 균형 진단")
    tune.add_argument("--top", type=int, default=30, help="불용어 후보 개수")
    tune.add_argument("--max-z", type=float, default=1.0, help="변별력 상한(|z|)")
    tune.add_argument("--min-count", type=int, default=5, help="최소 전체 등장 횟수")

    geo = sub.add_parser("geo", help="공공데이터 결합 및 생활권 지도 생성")
    geo.add_argument("--stats", help="등록외국인 통계 CSV 경로")
    geo.add_argument("--coords", help="지역 좌표 CSV 경로")
    geo.add_argument(
        "--min-mentions",
        type=int,
        default=4,
        help="교류 지수 순위에 포함할 최소 언급 수 (기본 4)",
    )

    contest = sub.add_parser("contest", help="공모전 제출물 생성")
    contest.add_argument("--name", default="데이터 분석 공모전")
    contest.add_argument("--deadline", help="YYYY-MM-DD")

    book = sub.add_parser("book", help="책 집필 구조 생성")
    book.add_argument("--title", default="섞이지 않는 도시")
    book.add_argument("--months", type=int, default=6)

    all_cmd = sub.add_parser("all", help="과제 → 보정 → 지도 → 공모전 → 책까지 전체 실행")
    all_cmd.add_argument("--contest-name", default="데이터 분석 공모전")
    all_cmd.add_argument("--deadline")
    all_cmd.add_argument("--title", default="섞이지 않는 도시")

    sub.add_parser("reset", help="수집 DB 비우기")

    doctor = sub.add_parser("doctor", help="네이버 API 키가 실제로 동작하는지 1회 호출로 확인")
    doctor.add_argument("--query", default="이태원 맛집", help="검증용 검색어")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda _msg: None) if args.quiet else print

    load_stopwords(args.stopwords)
    plan = ResearchPlan.load(args.plan)
    store = DocumentStore(args.db)
    ctx = AgentContext(plan=plan, store=store, output_dir=Path(args.output), logger=log)

    try:
        return _dispatch(args, ctx, store, plan, log)
    finally:
        store.close()


def _dispatch(args, ctx: AgentContext, store: DocumentStore, plan: ResearchPlan, log) -> int:
    command = args.command

    if command == "status":
        controller = CollectionController(store, default_collectors(), logger=log)
        log(f"주제: {plan.topic}")
        log(f"DB: {store.path} (총 {store.count()}건)")
        for name in plan.segment_names():
            log(f"  - {plan.label_of(name)}: {store.count(name)}건")
        log("수집기 상태:")
        for name, reason in controller.available_sources().items():
            log(f"  - {name}: {'사용 가능' if not reason else '사용 불가 — ' + reason}")
        return 0

    if command == "reset":
        store.clear()
        log("수집 DB를 비웠습니다.")
        return 0

    if command == "doctor":
        return _doctor(args.query, log)

    if command == "collect":
        controller = CollectionController(store, default_collectors(), logger=log)
        report = controller.run(plan, args.sources)
        log(f"\n수집 완료: 신규 {report.stored}건 / 중복 {report.duplicated}건 / 누적 {store.count()}건")
        for source, reason in report.skipped_sources.items():
            log(f"  건너뜀 {source}: {reason}")
        return 0

    if command in {"research", "analyze"}:
        agent = ResearchAgent(sources=args.sources, skip_collect=(command == "analyze"))
        return 0 if agent.run(ctx).ok else 1

    if command == "tune":
        agent = TuningAgent(top_n=args.top, max_abs_z=args.max_z, min_total=args.min_count)
        return 0 if agent.run(ctx).ok else 1

    if command == "geo":
        agent = GeoAgent(
            stats_path=args.stats,
            coords_path=args.coords,
            min_mentions=args.min_mentions,
        )
        return 0 if agent.run(ctx).ok else 1

    if command == "contest":
        agent = ContestAgent(contest_name=args.name, deadline=args.deadline)
        return 0 if agent.run(ctx).ok else 1

    if command == "book":
        agent = BookAgent(title=args.title, months=args.months)
        return 0 if agent.run(ctx).ok else 1

    if command == "all":
        research = ResearchAgent(sources=args.sources)
        if not research.run(ctx).ok:
            log("개인과제 에이전트가 실패해 후속 단계를 중단합니다.")
            return 1
        TuningAgent().run(ctx)
        GeoAgent().run(ctx)
        ContestAgent(contest_name=args.contest_name, deadline=args.deadline).run(ctx)
        BookAgent(title=args.title).run(ctx)
        log(f"\n모든 산출물이 {ctx.output_dir} 에 생성되었습니다.")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())


def _doctor(query: str, log) -> int:
    """네이버 검색 API 자격증명을 실제 호출 1회로 검증한다."""
    import os

    backend = (os.getenv("NAVER_API_BACKEND") or DEFAULT_BACKEND).lower()
    client_id = os.getenv("NAVER_CLIENT_ID", "")
    secret = os.getenv("NAVER_CLIENT_SECRET", "")

    log(f"백엔드: {backend}")
    if backend in BACKENDS:
        log(f"  호출 주소: {BACKENDS[backend]['base']}")
        log(f"  인증 헤더: {BACKENDS[backend]['id_header']}")
    log(f"NAVER_CLIENT_ID: {_mask(client_id)}")
    log(f"NAVER_CLIENT_SECRET: {_mask(secret)}")

    collector = NaverBlogCollector()
    ok, reason = collector.available()
    if not ok:
        log(f"\n실패: {reason}")
        return 1

    task = QueryTask(query=query, segment="doctor", source="naver_blog", limit=1)
    try:
        docs = list(collector.collect(task))
    except (CollectorError, CollectorUnavailable) as exc:
        log(f"\n실패: {exc}")
        return 1

    if not docs:
        log(f"\n호출은 됐지만 '{query}' 결과가 0건입니다. 검색어를 바꿔 다시 확인하세요.")
        return 1

    log(f"\n성공: {len(docs)}건 수신")
    log(f"  예시 제목: {docs[0].title[:60]}")
    log("\n`python -m sma collect --source naver_blog` 로 수집을 시작할 수 있습니다.")
    return 0


def _mask(value: str) -> str:
    if not value:
        return "(미설정)"
    return f"{value[:4]}…{value[-2:]} (길이 {len(value)})"
