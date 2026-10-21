"""저장된 패널의 정밀도·댓글·최소 글 수 민감도 점검. 네트워크 사용 없음."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests


def adjust(table, column="p"):
    table = table.copy()
    valid = table[column].notna()
    table["q_bh"] = np.nan
    if valid.any():
        table.loc[valid, "q_bh"] = multipletests(table.loc[valid, column], method="fdr_bh")[1]
    return table


def lag_pair(frame, minimum, lag):
    # 결측 제거 전에 거래일 행에서 shift해야 실제 시차가 유지된다.
    g = frame.sort_values("trading_date")
    sentiment = ((g.positive_count - g.negative_count) / g.post_count.replace(0, np.nan))
    return pd.DataFrame({"s": sentiment.where(g.post_count >= minimum),
                         "r": g.ret.shift(-lag)}).dropna()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", type=Path, required=True)
    parser.add_argument("--posts-only", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root / "state"):
        raise ValueError("결과는 Git 제외 state 아래에 저장하세요.")
    correlations, regressions, descriptive, inputs = [], [], [], []
    for variant, path in [("with_comments", args.full), ("posts_only", args.posts_only)]:
        inputs.append({"variant": variant, "path": str(path.resolve()),
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        frame = pd.read_csv(path, dtype={"stock_id": str})
        if frame.duplicated(["stock_id", "trading_date"]).any():
            raise ValueError("중복 거래일")
        for code, g in frame.groupby("stock_id"):
            g = g.sort_values("trading_date").copy()
            descriptive.append({"variant": variant, "stock_id": code,
                                "days": len(g), "messages": int(g.post_count.sum()),
                                "neutral_fraction": g.neutral_count.sum() / g.post_count.sum(),
                                "cumulative_simple_return": np.expm1(g.ret.sum())})
            for minimum in [1, 5, 10]:
                for lag in range(-5, 6):
                    pair = lag_pair(g, minimum, lag)
                    r, p = pearsonr(pair.s, pair.r) if len(pair) >= 10 and pair.s.nunique() > 1 and pair.r.nunique() > 1 else (np.nan, np.nan)
                    correlations.append({"variant": variant, "stock_id": code,
                                         "minimum": minimum, "lag": lag, "n": len(pair), "r": r, "p": p})
                g["s"] = ((g.positive_count - g.negative_count) / g.post_count.replace(0, np.nan)).where(g.post_count >= minimum)
                g["target"] = g.ret.shift(-1)
                columns = ["s", "ret", "market_return", "log_post_count"]
                data = g[["target"] + columns].dropna()
                row = {"variant": variant, "stock_id": code, "minimum": minimum, "n": len(data)}
                if len(data) >= 20:
                    fit = sm.OLS(data.target, sm.add_constant(data[columns])).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
                    ci = fit.conf_int().loc["s"]
                    row.update(coefficient=fit.params["s"], p=fit.pvalues["s"], ci_low=ci.iloc[0], ci_high=ci.iloc[1])
                else:
                    row.update(p=np.nan)
                regressions.append(row)
    lag = pd.DataFrame(correlations)
    # 기존 22검정 비교와 전체 132검정 탐색을 각각 명시한다.
    baseline = adjust(lag[(lag.variant == "with_comments") & (lag.minimum == 5)])
    lag, regression = adjust(lag), adjust(pd.DataFrame(regressions))
    args.output.mkdir(parents=True, exist_ok=False)
    for name, table in [("baseline_exact", baseline), ("lag_sensitivity", lag),
                        ("h2_sensitivity", regression), ("descriptive", pd.DataFrame(descriptive))]:
        table.to_csv(args.output / f"{name}.csv", index=False)
    summary = {"inputs": inputs, "baseline_tests": len(baseline),
               "baseline_significant": baseline[baseline.q_bh < .05].to_dict("records"),
               "all_lag_tests": len(lag), "all_lag_significant": int((lag.q_bh < .05).sum()),
               "h2_tests": len(regression), "h2_significant": int((regression.q_bh < .05).sum()),
               "limitations": ["사전 기반 분류, 사람 정답 없음", "2종목 74거래일의 탐색 분석", "Pearson p값은 시간 의존성을 보정하지 않음", "시차 상관·H2는 각각 별도 BH 검정군", "원래 BH와 달리 반올림 전 p값 사용"]}
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
