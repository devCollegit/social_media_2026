from pathlib import Path

from collector.fetchers import FixtureFetcher
from collector.http import RequestController
from collector.parser import parse_page
from collector.replies import supplement
from collector.store import PostStore, FailureLog


def test_cached_reply_collection_resumes_without_listing_requests(tmp_path):
    f = FixtureFetcher(Path(__file__).parent / "fixtures/toss")
    rows, *_ = parse_page(f.list_page("005930", None), "2026-10-21T00:00:00+09:00", "005930")
    store = PostStore(tmp_path / "posts")
    store.upsert("005930", rows)
    ctl = RequestController(sleep=lambda _: None)
    failures = FailureLog(tmp_path / "logs")
    progress = tmp_path / "progress.json"
    f.calls.clear()
    report = supplement(["005930"], f, ctl, store, failures, progress)
    assert report["errors"] == 0 and report["completed_parents"] > 0
    assert all("replies_" in call for call in f.calls)
    f.calls.clear()
    report = supplement(["005930"], f, ctl, store, failures, progress)
    assert report["completed_parents"] == 0 and not f.calls
