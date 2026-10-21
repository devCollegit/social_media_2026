from collector.parser import COLUMNS
from collector.store import CollectorState, FailureLog, PostStore


def row(pid, created, like=0, parent="", reply=0):
    return {"stock_id": "005930", "post_id": str(pid), "parent_id": parent, "text": f"글 {pid}",
            "created_at": created, "collected_at": "2026-10-19T21:00:00+09:00", "source": "tossinvest",
            "badge": "", "like_count": like, "reply_count": reply, "is_holder": 1}


def test_upsert_dedups_and_updates(tmp_path):
    store = PostStore(tmp_path)
    a = row(1, "2026-10-16T10:00:00.000000+09:00", like=1)
    b = row(2, "2026-10-16T11:00:00.000000+09:00")
    assert store.upsert("005930", [a, b]) == (2, 0)
    a2 = dict(a, like_count=9)
    assert store.upsert("005930", [a2, a2]) == (0, 1)
    df = store.load("005930")
    assert list(df.columns) == COLUMNS
    assert len(df) == 2
    assert df.loc[df.post_id == "1", "like_count"].item() == "9"
    assert df.stock_id.tolist() == ["005930", "005930"]  # 앞자리 0 유지


def test_reply_counts(tmp_path):
    store = PostStore(tmp_path)
    store.upsert("005930", [row(1, "2026-10-16T10:00:00.000000+09:00", reply=3)])
    # 부모에 표시된 3건만으로 댓글 수집 완료로 판단하면 안 된다.
    assert store.reply_counts("005930") == {"1": 0}
    store.upsert("005930", [row(2, "2026-10-16T10:01:00.000000+09:00", parent="1")])
    assert store.reply_counts("005930")["1"] == 1
    assert store.load("005930").loc[lambda df: df.post_id == "1", "reply_count"].item() == "3"
    assert store.reply_counts("000660") == {}


def test_state_roundtrip_keeps_max(tmp_path):
    s = CollectorState(tmp_path)
    s.update("005930", 10, "2026-10-16T10:00:00.000000+09:00")
    s.update("005930", 5, "2026-10-15T10:00:00.000000+09:00")
    s.save()
    s2 = CollectorState(tmp_path)
    assert s2.get("005930")["max_post_id"] == 10
    assert s2.get("005930")["max_created_at"].startswith("2026-10-16")


def test_failure_log(tmp_path):
    f = FailureLog(tmp_path)
    f.add("005930", "list", 1004, "타임아웃")
    f.add("005930", "list", None, "403")
    lines = (tmp_path / "failures.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "time,stock_id,stage,cursor,error" and len(lines) == 3
