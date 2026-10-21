import numpy as np
import pandas as pd

from analysis.robustness import adjust, lag_pair


def test_bh_preserves_precision_missing_and_order():
    result = adjust(pd.DataFrame({"p": [.04, .001001, np.nan, .03]}))
    np.testing.assert_allclose(result.q_bh, [.04, .003003, np.nan, .04])


def test_sparse_day_does_not_compress_lag():
    frame = pd.DataFrame({"trading_date": ["2026-07-01", "2026-07-02", "2026-07-03"],
                          "positive_count": [5, 0, 5], "negative_count": [0, 0, 0],
                          "post_count": [5, 0, 5], "ret": [.1, .2, .3]})
    pair = lag_pair(frame, 5, 1)
    assert len(pair) == 1
    assert pair.iloc[0].r == .2
