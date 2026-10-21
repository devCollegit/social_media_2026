import json
from pathlib import Path

import pandas as pd
import pytest

from collector.parser import COLUMNS, normalize_created_at, parse_page, redact_mentions, text_from

FIX = Path(__file__).parent / "fixtures" / "toss" / "005930"
NOW = "2026-10-19T21:00:00+09:00"


def load(name):
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("raw, expected", [
    ("2026-10-19T20:29:42.326512699+09:00", "2026-10-19T20:29:42.326512+09:00"),
    ("2026-10-19T20:28:25+09:00", "2026-10-19T20:28:25.000000+09:00"),
    ("2026-10-16T14:10:00.5+09:00", "2026-10-16T14:10:00.500000+09:00"),
    ("2026-10-19T11:28:25Z", "2026-10-19T20:28:25.000000+09:00"),
    ("2026-10-19T20:28:25", "2026-10-19T20:28:25.000000+09:00"),
])
def test_normalize_created_at_fixed_format(raw, expected):
    assert normalize_created_at(raw) == expected


def test_mixed_precision_parses_without_nat():
    # 형식이 섞인 원본을 그대로 두면 pandas 가 일부를 NaT 로 만들 수 있다. 정규화 후에는 없어야 한다.
    raw = ["2026-10-19T20:29:42.326512699+09:00", "2026-10-19T20:28:25+09:00"]
    s = pd.to_datetime(pd.Series([normalize_created_at(x) for x in raw]), errors="coerce")
    assert s.notna().all()


def test_parse_page_fields_and_badges():
    rows, key, has_next, skipped = parse_page(load("list_start"), NOW)
    assert key == 1004 and has_next is True and skipped == 0
    by_id = {r["post_id"]: r for r in rows}
    assert by_id["1005"]["badge"] == "BUY"
    assert by_id["1004"]["badge"] == "SELL"
    assert by_id["1006"]["badge"] == ""
    assert by_id["1005"]["like_count"] == 7
    assert by_id["1004"]["is_holder"] == 0 and by_id["1005"]["is_holder"] == 1
    assert by_id["1005"]["text"] == "막판 매수\n종가 직전에 추가 매수했습니다"
    assert by_id["1006"]["text"] == "장 끝나고 보니 그래도 반등 성공"
    assert all(r["stock_id"] == "005930" and r["parent_id"] == "" for r in rows)


def test_parse_page_skips_deleted_and_empty():
    rows, key, has_next, skipped = parse_page(load("list_1004"), NOW)
    assert [r["post_id"] for r in rows] == ["1004", "1001"]
    assert skipped == 2 and has_next is False


def test_no_personal_fields_leak():
    rows, *_ = parse_page(load("list_start"), NOW)
    for r in rows:
        assert list(r.keys()) == COLUMNS
        blob = json.dumps(r, ensure_ascii=False)
        for leaked in ("합성닉네임", "userProfileId", "example.invalid", "자기소개", "1억대", "2604000"):
            assert leaked not in blob


def test_body_and_title_mentions_are_removed():
    assert text_from({"message": {"title": "#[합성별명](12345) 상승",
                                  "message": "#[다른별명](67890)좋아요"}}) == "상승\n 좋아요"
    assert redact_mentions("가격 (12345), [뉴스](https://example.invalid)") == "가격 (12345), [뉴스](https://example.invalid)"
    assert redact_mentions("#[합성별명](12345)") == ""
