import pandas as pd
import pytest

from analysis.human_review import evaluate
from analysis.sentiment_candidate import classify
from integration.prepare_followup_review import select_followup


def test_human_evaluation_requires_complete_unique_stock_specific_join():
    gold = pd.DataFrame({"stock_id": ["001", "002"], "post_id": ["1", "1"],
                         "label": ["부정", "중립"]})
    scored = gold.drop(columns="label").assign(sentiment=["중립", "중립"], text_norm=["a", "b"])
    _, metrics = evaluate(gold, scored)
    assert metrics["accuracy"] == .5
    assert metrics["always_neutral_accuracy"] == .5
    with pytest.raises(ValueError, match="연결되지"):
        evaluate(gold, scored.iloc[:1])
    with pytest.raises(ValueError, match="중복"):
        evaluate(pd.concat([gold, gold]), scored)


def test_followup_excludes_previous_ids_text_and_context_and_hides_predictions():
    clean = pd.DataFrame({
        "stock_id": ["001"] * 8, "post_id": list("12345678"),
        "parent_id": ["", "", "", "", "1", "", "", ""],
        "text_norm": ["seen", "parent seen", " seen  ", "new", "new reply",
                      "other", "other", "last"], "sentiment": ["부정"] * 8})
    previous = clean.iloc[:1].assign(parent_text="parent seen")
    result, _ = select_followup(clean, previous, size=3, seed=1)
    assert set(result.post_id) == {"4", "6", "8"}
    assert not {"sentiment", "baseline_sentiment"}.intersection(result.columns)
    assert (result.label == "").all()
    assert result.text_norm.nunique() == 3
    with pytest.raises(ValueError):
        select_followup(clean, previous, size=10)


def test_candidate_preserves_directional_baseline_and_avoids_ambiguous_context():
    assert classify("마이너스 오십", "긍정") == ("긍정", "baseline_directional")
    assert classify("지금 양전했지만 마이너스야", "중립") == ("중립", "mixed_phrases")
    assert classify("🙏 힘내요", "중립")[0] == "중립"
    assert classify("이거 왜이래요?", "중립")[0] == "중립"
    assert classify("괜히 샀네", "중립")[0] == "부정"
    assert classify("양전이네", "중립")[0] == "긍정"
