import pandas as pd
from integration.prepare_context_review import attach_context, parent_key


def test_decimal_parent_id_preserves_precision_and_blindness():
    large = "9007199254740993"
    assert parent_key(large + ".0") == large
    sample = pd.DataFrame({"stock_id": ["003670"], "post_id": ["42"],
                           "parent_id": [large + ".0"], "text_norm": ["댓글"], "ai_label": ["긍정"]})
    clean = pd.DataFrame({"stock_id": ["450080", "003670"], "post_id": [large, large],
                          "text_norm": ["다른 종목", "부모 글"]})
    out = attach_context(sample, clean)
    assert out.parent_text.iloc[0] == "부모 글"
    assert out.context_status.iloc[0] == "parent_available"
    assert out.label.iloc[0] == ""
    assert "ai_label" not in out.columns
