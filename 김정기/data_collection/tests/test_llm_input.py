import json

import pandas as pd
import pytest

from integration import prepare_llm_input as llm_input


def clean_frame():
    return pd.DataFrame({
        "stock_id": ["003670", "003670", "450080", "999999"],
        "post_id": ["9007199254740993", "101", "9007199254740993", "200"],
        "parent_id": ["", "9007199254740993.0", "", ""],
        "text_norm": ["부모 문장", "댓글 문장", "같은 ID 다른 종목", "기타 종목"],
        "sentiment": ["가려야 함"] * 4,
        "author": ["가려야 함"] * 4,
    })


def test_prepare_rows_scopes_parent_keys_and_whitelists_payload():
    rows = llm_input.prepare_rows(clean_frame())
    assert list(rows.columns) == llm_input.FIELDS
    assert rows["post_id"].tolist() == ["9007199254740993", "101", "9007199254740993", "200"]
    assert rows.loc[1, "parent_text"] == "부모 문장"
    assert rows.loc[1, "context_status"] == "parent_available"
    assert rows.loc[0, "context_status"] == "top_level"
    assert rows.loc[0, "target_name"] == "포스코퓨처엠"
    assert rows.loc[2, "target_name"] == "에코프로머티"
    assert rows.loc[3, "target_name"] == "999999"
    assert "가려야 함" not in rows.to_json(force_ascii=False)


@pytest.mark.parametrize("bad_frame", [
    pd.DataFrame({"stock_id": [""], "post_id": ["1"], "parent_id": [""], "text_norm": ["x"]}),
    pd.DataFrame({"stock_id": ["1"], "post_id": [""], "parent_id": [""], "text_norm": ["x"]}),
    pd.DataFrame({"stock_id": ["1", "1"], "post_id": ["2", "2"],
                  "parent_id": ["", ""], "text_norm": ["x", "y"]}),
])
def test_prepare_rows_rejects_empty_or_duplicate_keys(bad_frame):
    with pytest.raises(ValueError):
        llm_input.prepare_rows(bad_frame)


def test_write_batches_preserves_exact_stock_scoped_id_set_and_bounds(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_input, "ROOT", tmp_path)
    clean_path = tmp_path / "clean.csv"
    clean_frame().to_csv(clean_path, index=False)
    output = tmp_path / "data" / "llm_input"

    manifest = llm_input.write_batches(clean_path, output, batch_size=3)

    assert manifest["rows"] == 4
    assert manifest["batch_count"] == 2
    assert [b["rows"] for b in manifest["batches"]] == [3, 1]
    records = [json.loads(line) for path in sorted(output.glob("batch-*.jsonl"))
               for line in path.read_text(encoding="utf-8").splitlines()]
    assert [(r["stock_id"], r["post_id"]) for r in records] == list(
        zip(clean_frame().stock_id, clean_frame().post_id))
    assert all(set(row) == set(llm_input.FIELDS) for row in records)
    assert (output / "PROMPT_TEMPLATE.txt").exists()
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8"))["rows"] == 4


@pytest.mark.parametrize("size", [0, 101])
def test_write_batches_rejects_out_of_range_batch_size(size, tmp_path):
    with pytest.raises(ValueError, match="batch-size"):
        llm_input.write_batches("unused.csv", tmp_path / "state" / "out", batch_size=size)
