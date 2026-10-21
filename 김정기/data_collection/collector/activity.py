"""후보별 최근 24시간 게시글 활동량 하한을 순차 측정한다.

댓글 수를 게시글 시점에 더해 일별 실측치로 간주하지 않는다. 관찰한 고유 게시글만
세어 20건 이상이면 예비 통과이며, 미달은 탈락이 아니라 추가 관찰 대상이다.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from collector.fetchers import TossFetcher
from collector.http import RequestController
from collector.parser import KST, parse_page
from collector.store import PostStore


def summarize(output: Path, candidates: Path) -> dict:
    activity = pd.read_csv(output / "activity.csv", dtype={"stock_id": str})
    universe = pd.read_csv(candidates, dtype=str)
    selected = universe.merge(activity[activity.status == "preliminary_pass"], on="stock_id", how="inner")
    selected.to_csv(output / "selected_candidates.csv", index=False)
    summary = {"candidate_count": len(universe), "measured_count": len(activity),
               "preliminary_pass": len(selected), "needs_more_observation": int((activity.status != "preliminary_pass").sum()),
               "window_hours": 24, "threshold": 20, "max_pages_per_stock": 3,
               "method": "관찰한 고유 게시글 수 하한. 댓글 미포함. 종목별 조회 시작 직전 24시간.",
               "limitation": "하루 예비 관찰이며 장기 평균·전체 글 수가 아니다. 미통과는 탈락이 아니다."}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def measure(code, fetcher, controller, store, end, max_pages=3, threshold=20):
    start = end - timedelta(days=1)
    start_iso, end_iso = start.isoformat(timespec="microseconds"), end.isoformat(timespec="microseconds")
    cursor, seen, observed = None, set(), {}
    reason = "page_limit"
    page_count = 0
    for _ in range(max_pages):
        page = controller.call(lambda: fetcher.list_page(code, cursor))
        page_count += 1
        rows, key, has_next, skipped = parse_page(page, end_iso, code)
        store.upsert(code, rows)
        for row in rows:
            if not row["parent_id"] and start_iso <= row["created_at"] < end_iso:
                observed[row["post_id"]] = row
        if len(observed) >= threshold:
            reason = "threshold_lower_bound"
            break
        if any(row["created_at"] < start_iso for row in rows) or not has_next:
            reason = "window_end"
            break
        if key is None or repr(key) in seen:
            raise ValueError("활동량 측정 커서 반복/누락")
        seen.add(repr(key))
        cursor = key
    return {"stock_id": code, "window_start": start_iso, "window_end": end_iso,
            "unique_posts_lower_bound": len(observed), "pages": page_count,
            "status": "preliminary_pass" if len(observed) >= threshold else "needs_more_observation",
            "stop_reason": reason}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidates", type=Path, default=Path("data/raw/meta/candidates.csv"))
    ap.add_argument("--master", type=Path, default=Path("data/raw/meta/stock_master.csv"))
    ap.add_argument("--output", type=Path, default=Path("data/activity_pilot"))
    ap.add_argument("--max-requests", type=int, default=900)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    stats_path = args.output / "activity.csv"
    results = pd.read_csv(stats_path, dtype={"stock_id": str}).to_dict("records") if stats_path.exists() else []
    completed = {r["stock_id"] for r in results}
    candidates = pd.read_csv(args.candidates, dtype=str)
    f = TossFetcher(args.master, max_requests=args.max_requests)
    c = RequestController(min_interval=2.0, max_retries=0)
    store = PostStore(args.output / "posts")
    try:
        for code in candidates.stock_id:
            if code in completed:
                continue
            result = measure(code, f, c, store, datetime.now(KST))
            results.append(result)
            tmp = stats_path.with_suffix(".tmp")
            pd.DataFrame(results).to_csv(tmp, index=False)
            tmp.replace(stats_path)
            if len(results) % 10 == 0:
                print(json.dumps({"completed": len(results), "requests": f.requests,
                                  "preliminary_pass": sum(r["status"] == "preliminary_pass" for r in results)}), flush=True)
        print(json.dumps(summarize(args.output, args.candidates), ensure_ascii=False), flush=True)
    finally:
        (args.output / "last_run.json").write_text(json.dumps({"requests": f.requests, "completed": len(results)}, indent=2))


if __name__ == "__main__":
    main()
