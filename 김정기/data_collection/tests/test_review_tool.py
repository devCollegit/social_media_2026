import csv
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from review_tool.server import Conflict, ReviewStore, VISIBLE, make_server


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "input.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=[*VISIBLE, "ai_label"])
        writer.writeheader()
        for i in range(2):
            writer.writerow({"stock_id": "003670", "post_id": str(i + 1), "parent_id": "",
                             "text_norm": "<script>합성 표본</script>", "parent_text": "",
                             "context_status": "top_level", "ai_label": "부정"})
    return path


@pytest.fixture
def store(source, tmp_path):
    instance = ReviewStore(source, tmp_path / "output")
    yield instance
    instance.close()


def record(index=0, revision=0, **changes):
    return {"index": index, "revision": revision, "label": "긍정", "uncertain": False,
            "note": "합성 검수", "reviewer": "테스트 검수자", **changes}


def test_resume_preserves_source_and_hides_ai(store, source):
    original = source.read_bytes()
    assert "ai_label" not in store.snapshot()["rows"][0]
    store.save(record())
    store.close()
    reopened = ReviewStore(source, store.output)
    try:
        assert reopened.snapshot()["records"]["0"]["label"] == "긍정"
        assert source.read_bytes() == original
    finally:
        reopened.close()


def test_export_requires_all_resolved_and_has_no_text(store):
    with pytest.raises(ValueError, match="모든 항목"):
        store.export(0)
    store.save(record())
    store.save(record(1, 1, uncertain=True))
    with pytest.raises(ValueError, match="모든 항목"):
        store.export(2)
    store.save(record(1, 2, label="중립"))
    exported = store.export(3)
    assert exported["csv"].splitlines() == ["stock_id,post_id,label", "003670,1,긍정", "003670,2,중립"]
    assert store.export(3)["filename"] != exported["filename"]


def test_stale_revision_and_invalid_input_cannot_overwrite(store):
    store.save(record())
    with pytest.raises(Conflict):
        store.save(record(label="부정"))
    with pytest.raises(ValueError):
        store.save(record(revision=1, label="오류"))
    assert store.snapshot()["records"]["0"]["label"] == "긍정"


def test_failed_write_keeps_prior_progress(store, monkeypatch):
    store.save(record())
    before = store.path.read_bytes()
    def fail(*args):
        raise OSError("합성 디스크 실패")
    monkeypatch.setattr("review_tool.server.os.replace", fail)
    with pytest.raises(OSError):
        store.save(record(revision=1, label="부정"))
    assert store.path.read_bytes() == before
    assert store.snapshot()["revision"] == 1


def test_changed_input_and_double_process_are_rejected(store, source):
    with pytest.raises(ValueError, match="이미 실행"):
        ReviewStore(source, store.output)
    store.save(record())
    store.close()
    source.write_text(source.read_text() + "\n")
    with pytest.raises(ValueError, match="입력 파일이 변경"):
        ReviewStore(source, store.output)


def test_http_requires_token_and_same_origin(store):
    server = make_server(store, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(url + "/api/state") as response:
            data = json.load(response)
        for headers in [{}, {"X-Review-Token": data["token"], "Origin": "https://example.invalid"}]:
            req = Request(url + "/api/save", data=json.dumps(record()).encode(), headers=headers)
            with pytest.raises(HTTPError) as error:
                urlopen(req)
            assert error.value.code == 403
        with urlopen(Request(url + "/api/save", data=json.dumps(record()).encode(),
                             headers={"X-Review-Token": data["token"], "Origin": url})) as response:
            assert json.load(response)["revision"] == 1
        with pytest.raises(HTTPError) as error:
            urlopen(url + "/.env")
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
