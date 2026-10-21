import numpy as np
import pandas as pd
from analysis.temporal import forecast


def test_forecasts_do_not_use_future_targets():
    rng = np.random.default_rng(17)
    g = pd.DataFrame({"trading_date": pd.date_range("2026-01-01", periods=55).astype(str),
                      "ret": rng.normal(size=55), "market_return": rng.normal(size=55),
                      "log_post_count": rng.normal(size=55), "sentiment_index": rng.normal(size=55)})
    original = forecast(g)
    assert (original.train_target_max <= original.date).all()
    # 첫 예측 시점 이후 수익률을 바꿔도 해당 예측값은 같아야 한다.
    changed = g.copy()
    changed.loc[41:, "ret"] += 100
    rerun = forecast(changed)
    np.testing.assert_allclose(original.iloc[0][["controls", "with_sentiment"]].astype(float),
                               rerun.iloc[0][["controls", "with_sentiment"]].astype(float))
