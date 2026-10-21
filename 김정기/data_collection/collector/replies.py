"""저장된 게시글의 댓글만 순차 보충한다. 목록 페이지를 다시 요청하지 않는다."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from collector.fetchers import TossFetcher
from collector.http import RequestController
from collector.parser import now_kst
from collector.run import StockStats, _collect_replies
from collector.store import PostStore, FailureLog


def supplement(codes, fetcher, controller, store, failures, progress_path):
    completed = json.loads(progress_path.read_text()) if progress_path.exists() else {}
    report = {"completed_parents": 0, "reply_rows_observed": 0, "errors": 0}
    for code in codes:
        frame = store.load(code)
        parents = frame[frame.parent_id == ""].to_dict("records")
        for parent in parents:
            count = int(parent["reply_count"])
            key = code + ":" + parent["post_id"]
            if count <= 0 or completed.get(key) == count:
                continue
            stats = StockStats(code)
            rows = _collect_replies(code, parent["post_id"], fetcher, controller, failures,
                                    now_kst(), stats, store)
            report["reply_rows_observed"] += len(rows)
            if stats.errors:
                report["errors"] += 1
                return report
            # 끝 페이지까지 조회 완료한 부모만 기록한다. 삭제·빈 본문 댓글은 저장 수가 적을 수 있다.
            completed[key] = count
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = progress_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(completed))
            tmp.replace(progress_path)
            report["completed_parents"] += 1
            if report["completed_parents"] % 25 == 0:
                print(json.dumps(report), flush=True)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--posts", type=Path, default=Path("data/history/posts"))
    ap.add_argument("--stocks", default="267250,450080,003670")
    ap.add_argument("--max-requests", type=int, default=800)
    ap.add_argument("--progress", type=Path, default=Path("state/history_reply_progress.json"))
    args = ap.parse_args()
    fetcher = TossFetcher(Path("data/raw/meta/stock_master.csv"), max_requests=args.max_requests)
    report = supplement(args.stocks.split(","), fetcher, RequestController(min_interval=2, max_retries=0),
                        PostStore(args.posts), FailureLog(Path("logs/history")), args.progress)
    report["requests"] = fetcher.requests
    args.progress.with_suffix(".summary.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
