"""연속 거래일 HAC 시차 검증 및 사후 expanding-window 예측 진단."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .robustness import adjust, lag_pair


def forecast(g, min_train=40):
    """t일 예측 시 학습 목표는 t일 종가까지 관측된 값만 사용한다."""
    g = g.sort_values("trading_date").reset_index(drop=True).copy()
    g["target"] = g.ret.shift(-1)
    g["target_date"] = g.trading_date.shift(-1)
    features = ["ret", "market_return", "log_post_count", "sentiment_index"]
    rows = []
    for i in range(len(g) - 1):
        train = g.iloc[:i].dropna(subset=features + ["target"])
        current = g.iloc[[i]]
        if len(train) < min_train or current[features + ["target"]].isna().any().any():
            continue
        row = {"date": current.trading_date.iloc[0], "target_date": current.target_date.iloc[0],
               "train_target_max": train.target_date.max(), "n_train": len(train),
               "actual": current.target.iloc[0], "historical_mean": train.target.mean()}
        for name, cols in [("controls", features[:-1]), ("with_sentiment", features)]:
            fit = sm.OLS(train.target, sm.add_constant(train[cols], has_constant="add")).fit()
            row[name] = float(fit.predict(sm.add_constant(current[cols], has_constant="add")).iloc[0])
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root / "state"):
        raise ValueError("출력은 state 아래 새 경로여야 합니다.")
    frame = pd.read_csv(args.panel, dtype={"stock_id": str})
    results, predictions, metrics = [], [], []
    for code, g in frame.groupby("stock_id"):
        g = g.sort_values("trading_date").reset_index(drop=True)
        if g.trading_date.duplicated().any():
            raise ValueError("중복 거래일")
        for lag in range(-5, 6):
            pair = lag_pair(g, 5, lag)
            # 경계 결측만 허용. 내부 결측을 압축해 HAC 시간축을 바꾸지 않는다.
            if len(pair) < 20 or not np.all(np.diff(pair.index) == 1):
                raise ValueError("HAC 입력은 최소 20개 연속 거래일이어야 합니다.")
            for bandwidth in [1, 3, 5, 10]:
                fit = sm.OLS(pair.r, sm.add_constant(pair.s)).fit(
                    cov_type="HAC", cov_kwds={"maxlags": bandwidth, "use_correction": True}, use_t=True)
                results.append({"stock_id": code, "lag": lag, "bandwidth": bandwidth,
                                "n": len(pair), "coefficient": fit.params["s"], "p": fit.pvalues["s"]})
        pred = forecast(g)
        if pred.empty:
            raise ValueError("예측 진단에 필요한 표본이 부족합니다.")
        pred.insert(0, "stock_id", code)
        predictions.append(pred)
        mse = {c: float(np.mean((pred[c] - pred.actual) ** 2))
               for c in ["historical_mean", "controls", "with_sentiment"]}
        metrics.append({"stock_id": code, "n_forecasts": len(pred), **{f"mse_{k}": v for k, v in mse.items()},
                        "relative_mse_vs_controls": mse["with_sentiment"] / mse["controls"],
                        "relative_mse_vs_mean": mse["with_sentiment"] / mse["historical_mean"]})
    table = pd.DataFrame(results)
    table["q_within_bandwidth"] = table.groupby("bandwidth")["p"].transform(
        lambda p: adjust(pd.DataFrame({"p": p})).q_bh)
    table = adjust(table)
    args.output.mkdir(parents=True, exist_ok=False)
    table.to_csv(args.output / "hac_lags.csv", index=False)
    pd.concat(predictions).to_csv(args.output / "forecasts.csv", index=False)
    pd.DataFrame(metrics).to_csv(args.output / "forecast_metrics.csv", index=False)
    summary = {"input": str(args.panel.resolve()), "sha256": hashlib.sha256(args.panel.read_bytes()).hexdigest(),
               "hac_tests": len(table), "significant_all_bandwidths": int((table.q_bh < .05).sum()),
               "bandwidth5_significant": table[(table.bandwidth == 5) & (table.q_within_bandwidth < .05)].to_dict("records"),
               "forecast_metrics": metrics,
               "limits": ["사후 설계 진단이며 독립 홀드아웃 평가가 아님", "소표본 HAC 근사 추론", "감성분류 정확도 미검증"]}
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
