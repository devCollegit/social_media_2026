import json

import pandas as pd
import pytest

from analysis.llm_results import _read_predictions, analyze


def source_frame():
    return pd.DataFrame({
        "stock_id": ["001", "001", "002"],
        "post_id": ["p1", "p2", "p3"],
        "text_norm": ["오늘 상승", "그냥 보유", "부모 인용"],
        "parent_text": ["", "", "부모 반응"],
        "context_status": ["none", "none", "available"],
    })


def prediction(stock, post, relevance, sentiment, evidence="", context=False):
    return {"stock_id": stock, "post_id": post, "relevance": relevance,
            "sentiment": sentiment, "reason": "근거에 따른 분류", "evidence": evidence,
            "context_used": context}


def prediction_frame():
    return pd.DataFrame([
        prediction("001", "p1", "related", "긍정", "상승"),
        prediction("001", "p2", "related", "판단유보"),
        prediction("002", "p3", "related", "부정", "부모 반응", True),
    ])


def test_schema_rejects_nonrelated_directional_label_and_bad_evidence(tmp_path):
    path = tmp_path / "predictions.jsonl"
    row = prediction("001", "p1", "unrelated", "긍정", "상승")
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unrelated/unclear"):
        _read_predictions(path)

    rows = prediction_frame().to_dict("records")
    rows[0]["evidence"] = "없는 근거"
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                    encoding="utf-8")
    with pytest.raises(ValueError, match="evidence"):
        analyze(source_frame(), _read_predictions(path))


def test_analyze_coverage_counts_and_parent_evidence_rule():
    source, predictions = source_frame(), prediction_frame()
    summary, comparison = analyze(source, predictions)
    assert summary["eligible_count"] == 2
    assert summary["coverage"] == pytest.approx(2 / 3)
    assert summary["abstain_count"] == 1
    assert len(comparison) == 2

    predictions.loc[2, "context_used"] = False
    with pytest.raises(ValueError, match="context_used"):
        analyze(source, predictions)


def test_empty_eligible_is_safe_and_rejects_wrong_ids():
    source = source_frame()
    predictions = pd.DataFrame([
        prediction("001", "p1", "unclear", "판단유보"),
        prediction("001", "p2", "unrelated", "판단유보"),
        prediction("002", "p3", "unclear", "판단유보"),
    ])
    summary, comparison = analyze(source, predictions)
    assert summary["coverage"] == 0
    assert summary["eligible_count"] == 0
    assert summary["gold"] is None
    assert comparison.empty
    predictions.loc[0, "post_id"] = "missing"
    with pytest.raises(ValueError, match="ID 집합 불일치"):
        analyze(source, predictions)


def test_baseline_compares_same_eligible_and_full_gold_sets():
    source, predictions = source_frame(), prediction_frame()
    gold = pd.DataFrame({"stock_id": ["001", "001", "002"], "post_id": ["p1", "p2", "p3"],
                         "label": ["긍정", "중립", "부정"]})
    baseline = pd.DataFrame({"stock_id": ["001", "001", "002"], "post_id": ["p1", "p2", "p3"],
                             "sentiment": ["중립", "중립", "긍정"]})
    summary, compared = analyze(source, predictions, gold, baseline)
    assert summary["gold"]["n"] == 2
    assert summary["gold"]["overall"]["rows"] == 3
    assert summary["baseline"]["same_eligible_subset"]["n"] == 2
    assert summary["baseline"]["overall_gold"]["rows"] == 3
    assert "baseline_sentiment" in compared
