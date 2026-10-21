import pandas as pd
import pytest
from analysis.review_agreement import compare


def test_comparison_rejects_missing_duplicate_and_invalid_labels():
    review = pd.DataFrame({"stock_id": ["003670"], "post_id": ["1"], "ai_label": ["긍정"]})
    scored = pd.DataFrame({"stock_id": ["003670"], "post_id": ["1"], "sentiment": ["중립"]})
    assert not compare(review, scored).agreement.iloc[0]
    with pytest.raises(ValueError, match="연결되지"):
        compare(review, scored.assign(post_id="2"))
    with pytest.raises(ValueError, match="중복"):
        compare(pd.concat([review, review]), scored)
    with pytest.raises(ValueError, match="라벨"):
        compare(review.assign(ai_label="미정"), scored)


def test_difference_categories_preserve_stock_specific_ids():
    review = pd.DataFrame({"stock_id": ["003670", "450080", "003670", "450080"],
                           "post_id": ["1", "1", "2", "2"],
                           "ai_label": ["긍정", "중립", "부정", "긍정"]})
    scored = review.drop(columns="ai_label").assign(sentiment=["중립", "긍정", "긍정", "긍정"])
    assert compare(review, scored).difference_type.tolist() == [
        "lexicon_neutral_ai_directional", "lexicon_directional_ai_neutral", "opposite_direction", "agreement"]
