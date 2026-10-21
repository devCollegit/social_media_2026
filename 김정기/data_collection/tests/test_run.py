import sys
import types
from pathlib import Path

import pandas as pd
from copy import deepcopy

from collector.fetchers import FixtureFetcher
from collector.http import RequestController
from collector.run import RunOptions, collect_stock
from collector.store import CollectorState, FailureLog, PostStore

FIX = Path(__file__).parent / "fixtures" / "toss"
NOW = "2026-10-19T21:00:00+09:00"
PIPELINE = Path(__file__).resolve().parents[3] / "조현호" / "toss_sentiment"


def env(tmp_path):
    ctl = RequestController(min_interval=1.0, sleep=lambda s: None)
    return dict(fetcher=FixtureFetcher(FIX), ctl=ctl, store=PostStore(tmp_path / "posts"),
                state=CollectorState(tmp_path / "state"), failures=FailureLog(tmp_path / "logs"))


def run(e, **opts):
    return collect_stock("005930", e["fetcher"], e["ctl"], e["store"], e["state"], e["failures"], NOW,
                         RunOptions(**opts))


def test_full_collect_posts_and_replies(tmp_path):
    e = env(tmp_path)
    st = run(e)
    assert st.pages == 2 and st.stop_reason == "end" and not st.errors
    df = e["store"].load("005930")
    assert sorted(df.post_id) == ["1001", "1004", "1005", "1006", "2001", "2002"]
    assert df.loc[df.post_id == "1004", "like_count"].item() == "2"  # 두 번째 페이지의 최신 값
    replies = df[df.parent_id != ""]
    assert set(replies.post_id) == {"2001", "2002"} and set(replies.parent_id) == {"1006"}
    assert st.skipped == 2  # 삭제 1, 빈 본문 1


def test_incremental_run_stops_at_cutoff_and_skips_known_replies(tmp_path):
    e = env(tmp_path)
    run(e)
    e["fetcher"].calls.clear()
    st = run(e, lookback_hours=1)
    # 마지막 글(15:45) - 1시간 = 14:45 이전 글(1004, 14:10)에서 멈추므로 1페이지만 본다
    assert st.pages == 1 and st.stop_reason.startswith("cutoff")
    assert e["fetcher"].calls == ["005930/list_start"]  # 댓글 수 변화 없음 → 댓글 재요청 없음
    assert st.added == 0 and len(e["store"].load("005930")) == 6


def test_missing_page_logged_as_failure(tmp_path):
    e = env(tmp_path)
    st = collect_stock("000660", e["fetcher"], e["ctl"], e["store"], e["state"], e["failures"], NOW, RunOptions())
    assert st.stop_reason == "error" and st.errors
    assert (tmp_path / "logs" / "failures.csv").exists()


def test_page_limit_does_not_advance_checkpoint(tmp_path):
    e = env(tmp_path)
    st = run(e, max_pages=1, include_replies=False)
    assert st.stop_reason == "max_pages=1"
    assert not e["state"].get("005930")
    assert not e["store"].load("005930").empty


def test_cyclic_list_cursor_reports_error(tmp_path):
    e = env(tmp_path)
    page = e["fetcher"].list_page("005930", None)
    keys = iter([1, 2, 1])
    def repeated(*args):
        result = deepcopy(page)
        result.update(key=next(keys), hasNext=True)
        return result
    e["fetcher"].list_page = repeated
    st = run(e, include_replies=False)
    assert st.stop_reason == "cursor-stuck" and st.errors
    assert st.pages == 3
    assert not e["state"].get("005930")


def test_partial_reply_failure_retried_next_run(tmp_path):
    e = env(tmp_path)
    original = e["fetcher"].reply_page
    from collector.http import PermanentError
    def broken(*args):
        raise PermanentError("합성 댓글 오류")
    e["fetcher"].reply_page = broken
    assert run(e).errors
    assert not e["state"].get("005930")
    e["fetcher"].reply_page = original
    result = run(e)
    assert not result.errors and result.reply_requests > 0


def test_interruption_preserves_finished_pages_without_advancing_state(tmp_path):
    import pytest
    e = env(tmp_path)
    original = e["fetcher"].list_page
    def interrupted(code, cursor):
        if cursor is not None:
            raise KeyboardInterrupt
        return original(code, cursor)
    e["fetcher"].list_page = interrupted
    with pytest.raises(KeyboardInterrupt):
        run(e, include_replies=False)
    assert len(e["store"].load("005930")) > 0
    assert not e["state"].get("005930")


def test_output_passes_pipeline_collect_normalize(tmp_path):
    """조현호 파이프라인 s01_collect 의 manual_csv 읽기·정규화를 그대로 통과하는지 확인 (코드는 읽기만 한다)."""
    e = env(tmp_path)
    run(e)
    sys.path.insert(0, str(PIPELINE))
    try:
        from pipeline.stages import s01_collect
    finally:
        sys.path.remove(str(PIPELINE))

    notes = []
    ctx = types.SimpleNamespace(
        config=types.SimpleNamespace(get=lambda k, d=None: {"project.timezone": "Asia/Seoul",
                                                            "collect.source": "manual_csv"}.get(k, d)),
        note=notes.append,
    )
    raw = pd.read_csv(e["store"].path("005930"), dtype={"stock_id": str})  # _manual_csv 와 같은 읽기
    out = s01_collect._normalize(ctx, raw)
    assert len(out) == 6 and not notes  # 작성 시각 해석 실패 없음
    assert out["created_at"].dt.tz is None  # KST 로 변환 후 tz 제거됨
    assert out["parent_id"].isna().sum() == 4  # 게시글 4, 댓글 2
    assert str(out.loc[out.post_id == 1005, "created_at"].item()) == "2026-10-16 15:29:59"
    for col in ("badge", "like_count", "reply_count", "is_holder"):
        assert col in out.columns  # 추가 컬럼은 뒤에 보존된다
