#!/usr/bin/env python3
"""토스증권 커뮤니티 감성 분석 파이프라인 컨트롤러.

사용 예
  python run_pipeline.py run                      전체 단계 실행
  python run_pipeline.py run --from analyze       analyze 이후만 실행
  python run_pipeline.py run --only sentiment     특정 단계만 실행
  python run_pipeline.py run --force              캐시를 무시하고 재실행
  python run_pipeline.py plan                     실행 계획만 확인
  python run_pipeline.py status                   단계별 산출물 상태 확인
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from pipeline.config import ConfigError, load_config  # noqa: E402
from pipeline.context import RunContext, StageError, setup_logging  # noqa: E402
from pipeline.registry import build_stages, execute, select_stages  # noqa: E402

DEFAULT_CONFIG = BASE_DIR / "config" / "pipeline.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_pipeline.py",
        description="토스증권 커뮤니티 감성 분석 파이프라인 컨트롤러",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-c", "--config", type=Path, default=DEFAULT_CONFIG, help="설정 파일 경로"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="상세 로그 출력")

    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="단계를 실행한다")
    run_cmd.add_argument("--only", help="쉼표로 구분한 단계 목록만 실행")
    run_cmd.add_argument("--from", dest="start", help="이 단계부터 실행")
    run_cmd.add_argument("--until", help="이 단계까지 실행")
    run_cmd.add_argument("--force", action="store_true", help="산출물이 최신이어도 재실행")

    plan_cmd = sub.add_parser("plan", help="실행 계획만 출력한다")
    plan_cmd.add_argument("--only", help="쉼표로 구분한 단계 목록")
    plan_cmd.add_argument("--from", dest="start", help="이 단계부터")
    plan_cmd.add_argument("--until", help="이 단계까지")

    sub.add_parser("status", help="단계별 산출물 상태를 출력한다")
    sub.add_parser("stages", help="단계 목록을 출력한다")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"설정 오류: {exc}", file=sys.stderr)
        return 2

    stages = build_stages()

    if args.command == "stages":
        for stage in stages:
            print(f"  {stage.name:<10} {stage.title}")
        return 0

    if args.command == "status":
        return _status(config, stages)

    only = [s.strip() for s in args.only.split(",")] if getattr(args, "only", None) else None
    try:
        selected = select_stages(stages, only=only, start=args.start, until=args.until)
    except StageError as exc:
        print(f"단계 선택 오류: {exc}", file=sys.stderr)
        return 2

    dry_run = args.command == "plan"
    ctx = RunContext.create(
        config,
        force=getattr(args, "force", False),
        dry_run=dry_run,
        verbose=args.verbose,
    )
    ctx.logger.info("설정: %s (지문 %s)", ctx.rel(config.path), config.fingerprint)
    ctx.logger.info(
        "대상: %s / %s ~ %s",
        ", ".join(config.stock_names.values()),
        config.get("scope.start_date"),
        config.get("scope.end_date"),
    )

    try:
        results = execute(ctx, selected)
    except (StageError, ConfigError) as exc:
        ctx.logger.error("중단: %s", exc)
        return 1
    except FileNotFoundError as exc:
        ctx.logger.error("파일을 찾을 수 없습니다: %s", exc)
        return 1

    manifest = ctx.write_manifest(results)
    if dry_run:
        return 0

    ok = sum(1 for r in results if r["status"] == "ok")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    ctx.logger.info("─" * 60)
    ctx.logger.info("완료: 실행 %d단계, 건너뜀 %d단계", ok, skipped)
    if ctx.notes:
        ctx.logger.info("확인이 필요한 기록 %d건은 결과 요약 6절에 정리했다.", len(ctx.notes))
    if manifest:
        ctx.logger.info("실행 기록: %s", ctx.rel(manifest))
    return 0


def _status(config, stages) -> int:
    logger = setup_logging(None)
    logger.info("설정: %s (지문 %s)", config.path, config.fingerprint)
    for stage in stages:
        outs = stage.outputs(config)
        existing = [p for p in outs if p.exists()]
        if not existing:
            state = "미실행"
        elif len(existing) < len(outs):
            state = f"부분 산출 ({len(existing)}/{len(outs)})"
        elif stage.is_fresh(config):
            state = "최신"
        else:
            state = "재실행 필요"
        logger.info("  %-10s %-14s %s", stage.name, state, stage.title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
