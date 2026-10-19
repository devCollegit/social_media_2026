"""종목 1개 수집 절차.

1. 최신순 목록을 첫 페이지부터 넘긴다.
2. 증분 모드에서는 '마지막으로 본 가장 최근 글 시각 - lookback' 보다 오래된 글이 나오면 멈춘다.
   lookback 구간의 글은 다시 보면서 공감 수·댓글 수를 갱신한다.
3. 댓글 수가 저장값보다 늘어난 글만 댓글을 다시 받는다.
4. 종목 CSV 에 post_id 기준 upsert 하고 상태를 저장한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from collector.fetchers import Fetcher
from collector.http import PermanentError, RequestController, TransientError
from collector.parser import parse_page, unwrap
from collector.store import CollectorState, FailureLog, PostStore

log = logging.getLogger("collector")


@dataclass
class RunOptions:
    full: bool = False                 # True 면 상태를 무시하고 끝까지(또는 since 까지) 넘긴다
    since: str | None = None           # 이 시각(KST ISO)보다 오래된 글이 나오면 멈춤
    lookback_hours: float = 48.0
    include_replies: bool = True
    max_pages: int | None = None       # 안전장치. None 이면 제한 없음


@dataclass
class StockStats:
    stock_id: str
    pages: int = 0
    rows: int = 0
    added: int = 0
    updated: int = 0
    skipped: int = 0
    reply_requests: int = 0
    stop_reason: str = ""
    errors: list[str] = field(default_factory=list)


def _cutoff(state: dict[str, Any], opts: RunOptions) -> str | None:
    if opts.since:
        return opts.since
    if opts.full or not state.get("max_created_at"):
        return None
    last = datetime.fromisoformat(state["max_created_at"])
    return (last - timedelta(hours=opts.lookback_hours)).isoformat(timespec="microseconds")


def collect_stock(
    stock_id: str,
    fetcher: Fetcher,
    ctl: RequestController,
    store: PostStore,
    state: CollectorState,
    failures: FailureLog,
    collected_at: str,
    opts: RunOptions,
) -> StockStats:
    st = StockStats(stock_id)
    cutoff = _cutoff(state.get(stock_id), opts)
    known_replies = store.reply_counts(stock_id)
    rows: list[dict[str, Any]] = []
    cursor: Any = None

    while True:
        if opts.max_pages is not None and st.pages >= opts.max_pages:
            st.stop_reason = f"max_pages={opts.max_pages}"
            break
        try:
            page = unwrap(ctl.call(lambda: fetcher.list_page(stock_id, cursor), f"{stock_id} list {cursor}"))
        except (TransientError, PermanentError) as exc:
            failures.add(stock_id, "list", cursor, exc)
            st.errors.append(f"list@{cursor}: {exc}")
            st.stop_reason = "error"
            break
        st.pages += 1
        page_rows, next_key, has_next, skipped = parse_page(page, collected_at, stock_id)
        st.skipped += skipped

        reached_cutoff = False
        for row in page_rows:
            if cutoff and row["created_at"] < cutoff:
                reached_cutoff = True
                continue
            rows.append(row)
        if reached_cutoff:
            st.stop_reason = f"cutoff {cutoff}"
            break
        if not has_next or next_key is None:
            st.stop_reason = "end"
            break
        if next_key == cursor:
            st.stop_reason = "cursor-stuck"
            failures.add(stock_id, "list", cursor, "다음 커서가 이전과 같음")
            break
        cursor = next_key

    if opts.include_replies:
        for parent in [r for r in rows if not r["parent_id"]]:
            if int(parent["reply_count"]) <= known_replies.get(parent["post_id"], 0):
                continue
            rows.extend(_collect_replies(stock_id, parent["post_id"], fetcher, ctl, failures, collected_at, st))

    st.rows = len(rows)
    st.added, st.updated = store.upsert(stock_id, rows)
    if rows:
        top_level = [r["created_at"] for r in rows if not r["parent_id"]]
        state.update(stock_id, max(int(r["post_id"]) for r in rows), max(top_level) if top_level else None)
    return st


def _collect_replies(stock_id, post_id, fetcher, ctl, failures, collected_at, st) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor: Any = None
    while True:
        try:
            page = unwrap(ctl.call(lambda: fetcher.reply_page(stock_id, post_id, cursor),
                                   f"{stock_id} replies {post_id} {cursor}"))
        except (TransientError, PermanentError) as exc:
            failures.add(stock_id, f"replies:{post_id}", cursor, exc)
            st.errors.append(f"replies {post_id}@{cursor}: {exc}")
            return out
        st.reply_requests += 1
        page_rows, next_key, has_next, skipped = parse_page(page, collected_at, stock_id)
        st.skipped += skipped
        for row in page_rows:
            if not row["parent_id"]:  # 응답에 parentId 가 빠져 있으면 요청한 글로 채운다
                row["parent_id"] = post_id
            out.append(row)
        if not has_next or next_key is None or next_key == cursor:
            return out
        cursor = next_key
