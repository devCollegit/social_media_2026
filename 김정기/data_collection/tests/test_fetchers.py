"""네트워크 대신 opener 합성 응답을 주입하는 공개 API 계약 테스트."""
import io
import json
import urllib.error
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock

import pytest

from collector.fetchers import TossFetcher, _NoRedirect
from collector.http import PermanentError, TransientError
from collector.parser import parse_page


def item(id=100):
    return {"commentId": id, "message": {"message": "합성 본문"},
            "createdAt": "2026-10-21T10:00:00+09:00", "statistic": {"likeCount": 3},
            "author": {"nickname": "저장 금지", "userProfileId": "secret"}}


def response(rows=None, next=False, key=None):
    stream = io.BytesIO(json.dumps({"result": {"results": [item()] if rows is None else rows,
                                             "hasNext": next, "key": key}}).encode())
    stream.status = 200
    return stream


@pytest.fixture
def make(tmp_path):
    master = tmp_path / "master.csv"
    master.write_text("stock_id,isin\n005930,KR7005930003\n", encoding="utf-8")
    def factory(*responses, **kwargs):
        opener = Mock()
        opener.open.side_effect = responses
        return TossFetcher(master, opener=opener, **kwargs), opener
    return factory


def test_list_cursor_and_no_credentials(make):
    f, o = make(response(next=True, key=99), response())
    f.list_page("005930", None)
    page = f.list_page("005930", 99)
    req = o.open.call_args.args[0]
    q = parse_qs(urlsplit(req.full_url).query)
    assert q == {"subjectType": ["STOCK"], "subjectId": ["KR7005930003"],
                 "commentSortType": ["RECENT"], "lastCommentId": ["99"]}
    assert not {"authorization", "cookie"} & {k.lower() for k in req.headers}
    rows, *_ = parse_page(page, "2026-10-21T10:00:00+09:00", "005930")
    assert "author" not in rows[0] and "secret" not in str(rows)


def test_reply_paired_cursor(make):
    f, o = make(response(next=True, key=90), response())
    first = f.reply_page("005930", "100", None)
    assert first["key"] == ("90", "3")
    f.reply_page("005930", "100", first["key"])
    req = o.open.call_args.args[0]
    assert urlsplit(req.full_url).path == "/api/v2/comments/100/replies"
    assert parse_qs(urlsplit(req.full_url).query) == {
        "replySortType": ["NEWEST"], "lastCommentId": ["90"], "lastLikeCount": ["3"]}


@pytest.mark.parametrize("status,kind", [(429, TransientError), (503, TransientError),
                                         (401, PermanentError), (403, PermanentError),
                                         (404, PermanentError), (302, PermanentError)])
def test_http_errors_do_not_expose_response(make, status, kind):
    exc = urllib.error.HTTPError("https://example.invalid", status, "secret", {"Retry-After": "120"},
                                 io.BytesIO(b"private response"))
    f, _ = make(exc)
    with pytest.raises(kind) as caught:
        f.list_page("005930", None)
    assert str(caught.value) == f"HTTP {status}"
    if kind is TransientError:
        assert caught.value.retry_after == 120


def test_budget_includes_failed_requests(make):
    f, o = make(TimeoutError(), max_requests=1)
    with pytest.raises(TransientError):
        f.list_page("005930", None)
    with pytest.raises(PermanentError, match="예산"):
        f.list_page("005930", None)
    assert o.open.call_count == 1


@pytest.mark.parametrize("payload", [b"not json", b"[]", b'{"results":[],"hasNext":true,"key":1}',
                                     b'{"results":[{}],"hasNext":false}'])
def test_invalid_payload_stops_without_raw_details(make, payload):
    r = io.BytesIO(payload)
    r.status = 200
    f, _ = make(r)
    with pytest.raises(PermanentError, match="응답 형식 오류"):
        f.list_page("005930", None)


def test_invalid_identifiers_never_request(make):
    f, o = make()
    with pytest.raises(PermanentError):
        f.list_page("000660", None)
    with pytest.raises(PermanentError):
        f.reply_page("005930", "../secret", None)
    with pytest.raises(PermanentError):
        f.reply_page("005930", "100", "90")
    o.open.assert_not_called()


def test_redirect_handler_never_follows():
    assert _NoRedirect().redirect_request(None, None, 302, None, {}, "https://example.invalid") is None


def test_toss_fetcher_to_csv_end_to_end(make, tmp_path):
    from collector.http import RequestController
    from collector.run import collect_stock, RunOptions
    from collector.store import PostStore, CollectorState, FailureLog
    parent = item(100)
    parent["statistic"]["replyCount"] = 2
    f, o = make(response([parent]), response([item(90)], next=True, key=90), response([item(80)]))
    store = PostStore(tmp_path / "posts")
    state = CollectorState(tmp_path / "state")
    result = collect_stock("005930", f, RequestController(sleep=lambda _: None), store, state,
                           FailureLog(tmp_path / "logs"), "2026-10-21T10:00:00+09:00", RunOptions())
    assert not result.errors and result.reply_requests == 2
    df = store.load("005930")
    assert set(df.post_id) == {"100", "90", "80"}
    assert set(df.loc[df.post_id != "100", "parent_id"]) == {"100"}
    assert "secret" not in store.path("005930").read_text()


def test_cli_toss_build_is_offline_and_no_approval_gate(tmp_path):
    from collector.cli import build_fetcher
    from settings import Settings
    (tmp_path / "stock_master.csv").write_text("stock_id,isin\n005930,KR7005930003\n")
    f = build_fetcher("toss", Settings({"paths": {"meta_dir": "."},
                                      "community": {"max_requests": 3}}, tmp_path))
    assert f.requests == 0 and f.max_requests == 3


def test_alphanumeric_stock_code_from_master(tmp_path):
    master = tmp_path / "master.csv"
    master.write_text("stock_id,isin\n0126Z0,KR70126Z0002\n")
    opener = Mock()
    opener.open.return_value = response()
    f = TossFetcher(master, opener=opener)
    f.list_page("0126Z0", None)
    assert parse_qs(urlsplit(opener.open.call_args.args[0].full_url).query)["subjectId"] == ["KR70126Z0002"]


def test_alphanumeric_stock_code_parser_and_file(tmp_path):
    from collector.parser import stock_id_from
    from settings import parse_stock_list, Settings
    assert stock_id_from({"board": {"stockCode": "A0126Z0"}}) == "0126Z0"
    codes = tmp_path / "stocks.txt"
    codes.write_text("0126Z0\n005930\n../../escape\n")
    assert parse_stock_list(None, str(codes), Settings({}, tmp_path)) == ["0126Z0", "005930"]


def test_cli_network_error_stops_before_next_stock(tmp_path, monkeypatch):
    import argparse
    from collector import cli
    from collector.run import StockStats
    from settings import Settings
    calls = []
    def fail(code, *args):
        calls.append(code)
        return StockStats(code, errors=["HTTP 403"], stop_reason="error")
    monkeypatch.setattr(cli, "build_fetcher", lambda *args: None)
    monkeypatch.setattr(cli, "collect_stock", fail)
    monkeypatch.setattr(cli.settings_mod, "setup_logging", lambda *args: Mock())
    cfg = Settings({"paths": {"posts_dir": "posts", "state_dir": "state", "logs_dir": "logs"}}, tmp_path)
    args = argparse.Namespace(source="toss", full=False, since=None, lookback_hours=48,
                              no_replies=True, max_pages=1, stocks="005930,000660", stocks_file=None)
    assert cli.cmd_run(args, cfg) == 1
    assert calls == ["005930"]
