"""커뮤니티 수집 CLI. cron 에 걸 수 있도록 실패 시 0이 아닌 코드로 끝난다.

    python -m collector.cli run                         # 설정의 종목, 증분 수집
    python -m collector.cli run --stocks 005930 --full  # 상태 무시, 처음부터
    python -m collector.cli run --since 2026-10-01T00:00:00+09:00

cron 예시 (매일 16:10, 장 마감 후):
    10 16 * * 1-5  cd <repo>/김정기/data_collection && .venv/bin/python -m collector.cli run >> logs/cron.log 2>&1
"""

from __future__ import annotations

import argparse
import sys

import settings as settings_mod
from collector.fetchers import FixtureFetcher, TossFetcher
from collector.http import RequestController
from collector.parser import normalize_created_at, now_kst
from collector.run import RunOptions, collect_stock
from collector.store import CollectorState, FailureLog, PostStore


def build_fetcher(source: str, cfg: settings_mod.Settings):
    if source == "fixture":
        return FixtureFetcher(cfg.path("community.fixture_dir"))
    if source == "toss":
        if not cfg.get("community.collection_approved", False):
            raise SystemExit(
                "community.collection_approved 가 false 입니다. "
                "토스증권 이용 허락 확인 전에는 네트워크 수집을 하지 않습니다 (docs/수집가능성_점검표.md)."
            )
        return TossFetcher()
    raise SystemExit(f"알 수 없는 source: {source}")


def cmd_run(args: argparse.Namespace, cfg: settings_mod.Settings) -> int:
    log = settings_mod.setup_logging(cfg, "collector")
    source = args.source or cfg.get("community.source", "fixture")
    fetcher = build_fetcher(source, cfg)
    ctl = RequestController(
        min_interval=float(cfg.get("community.min_interval_sec", 2.0)),
        max_retries=int(cfg.get("community.max_retries", 4)),
        backoff_base=float(cfg.get("community.backoff_base_sec", 2.0)),
        backoff_max=float(cfg.get("community.backoff_max_sec", 60.0)),
    )
    if source == "fixture":
        ctl.min_interval = 0.0  # 파일 읽기에는 대기가 필요 없다

    store = PostStore(cfg.path("paths.posts_dir"))
    state = CollectorState(cfg.path("paths.state_dir"))
    failures = FailureLog(cfg.path("paths.logs_dir"))
    opts = RunOptions(
        full=args.full,
        since=normalize_created_at(args.since) if args.since else None,
        lookback_hours=float(args.lookback_hours),
        include_replies=bool(cfg.get("community.include_replies", True)) and not args.no_replies,
        max_pages=args.max_pages,
    )
    codes = settings_mod.parse_stock_list(args.stocks, args.stocks_file, cfg)
    collected_at = now_kst()
    log.info("수집 시작: source=%s, %d종목, full=%s, since=%s", source, len(codes), opts.full, opts.since)

    failed = 0
    for i, code in enumerate(codes, 1):
        st = collect_stock(code, fetcher, ctl, store, state, failures, collected_at, opts)
        state.save()  # 종목마다 저장해 중간에 끊겨도 다음 실행이 이어 간다
        level = log.warning if st.errors else log.info
        level("[%d/%d] %s pages=%d rows=%d 신규=%d 갱신=%d 제외=%d 댓글요청=%d 종료=%s%s",
              i, len(codes), code, st.pages, st.rows, st.added, st.updated, st.skipped,
              st.reply_requests, st.stop_reason, f" 오류={len(st.errors)}" if st.errors else "")
        failed += bool(st.errors)

    log.info("수집 종료: 요청 %d회, 오류 종목 %d개", ctl.requests, failed)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="collector.cli", description="토스증권 커뮤니티 수집")
    parser.add_argument("-c", "--config", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="수집 실행")
    r.add_argument("--stocks")
    r.add_argument("--stocks-file")
    r.add_argument("--source", choices=["fixture", "toss"])
    r.add_argument("--full", action="store_true", help="증분 상태를 무시하고 처음부터")
    r.add_argument("--since", help="이 시각보다 오래된 글이 나오면 멈춤 (ISO, KST)")
    r.add_argument("--lookback-hours", type=float, default=48.0)
    r.add_argument("--no-replies", action="store_true")
    r.add_argument("--max-pages", type=int)
    r.set_defaults(func=cmd_run)
    args = parser.parse_args(argv)
    cfg = settings_mod.load(args.config)
    return args.func(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
