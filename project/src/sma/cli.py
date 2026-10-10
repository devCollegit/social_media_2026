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

from .agents import BookAgent, ContestAgent, ResearchAgent
from .agents.base import AgentContext
from .collectors import default_collectors
from .config import DEFAULT_DB_PATH, DEFAULT_OUTPUT_DIR, DEFAULT_PLAN_PATH, ResearchPlan
from .controllers import CollectionController
from .storage import DocumentStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sma", description="소셜미디어 분석 에이전트")
    parser.add_argument("--plan", default=str(DEFAULT_PLAN_PATH), help="연구 계획 JSON 경로")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite 경로")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR), help="산출물 디렉터리")
    parser.add_argument("--source", action="append", dest="sources", help="사용할 수집기 (반복 지정)")
    parser.add_argument("--quiet", action="store_true", help="로그 숨김")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="수집기 가용 상태와 적재 현황 확인")
    sub.add_parser("collect", help="수집만 실행")
    sub.add_parser("research", help="개인과제 에이전트 실행 (수집+분석+리포트)")
    sub.add_parser("analyze", help="기존 데이터로 분석/리포트만 재생성")

    contest = sub.add_parser("contest", help="공모전 제출물 생성")
    contest.add_argument("--name", default="데이터 분석 공모전")
    contest.add_argument("--deadline", help="YYYY-MM-DD")

    book = sub.add_parser("book", help="책 집필 구조 생성")
    book.add_argument("--title", default="섞이지 않는 도시")
    book.add_argument("--months", type=int, default=6)

    all_cmd = sub.add_parser("all", help="과제 → 공모전 → 책까지 전체 실행")
    all_cmd.add_argument("--contest-name", default="데이터 분석 공모전")
    all_cmd.add_argument("--deadline")
    all_cmd.add_argument("--title", default="섞이지 않는 도시")

    sub.add_parser("reset", help="수집 DB 비우기")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda _msg: None) if args.quiet else print

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
        ContestAgent(contest_name=args.contest_name, deadline=args.deadline).run(ctx)
        BookAgent(title=args.title).run(ctx)
        log(f"\n모든 산출물이 {ctx.output_dir} 에 생성되었습니다.")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
