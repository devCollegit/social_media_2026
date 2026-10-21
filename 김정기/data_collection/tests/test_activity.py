from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

from collector.activity import measure
from collector.parser import KST


def post(n, day=21):
    return {"commentId": n, "createdAt": f"2026-10-{day}T09:00:00+09:00",
            "message": {"message": "합성"}, "statistic": {"replyCount": 1000}}


def test_activity_counts_unique_observed_posts_not_reported_replies():
    f = SimpleNamespace(list_page=Mock(side_effect=[
        {"results": [post(1), post(2)], "hasNext": True, "key": 1},
        {"results": [post(2), post(3)], "hasNext": True, "key": 2}]))
    c = SimpleNamespace(call=lambda fn: fn())
    result = measure("005930", f, c, Mock(), datetime(2026, 10, 21, 10, tzinfo=KST), max_pages=2)
    assert result["unique_posts_lower_bound"] == 3
    assert result["status"] == "needs_more_observation"


def test_activity_threshold_and_window_boundary():
    f = SimpleNamespace(list_page=Mock(return_value={
        "results": [post(1), post(2, day=19)], "hasNext": True, "key": 1}))
    c = SimpleNamespace(call=lambda fn: fn())
    result = measure("005930", f, c, Mock(), datetime(2026, 10, 21, 10, tzinfo=KST), threshold=1)
    assert result["status"] == "preliminary_pass"
    assert result["unique_posts_lower_bound"] == 1
