"""예측 모델 비교 (보완안 C5)와 개인 수급 예상 범위 (결론 확장의 '개인 수급 예보').

질문: 시장 자료만 쓴 모델에 커뮤니티 변수를 더하면 다음 날 예측이 나아지는가?
- 대상: 다음 날 개인 순매수 비율(priv_n1), 다음 날 거래량 비율(lvr_n1), 다음 날 일중 변동폭(range_n1), 다음 날 시가가 오를지(gap_up_n1)
- 방법: 날짜 순 확장 창. 처음 --min-train 거래일로 학습하고 --refit 거래일마다 다시 학습하며 다음 구간을 예측한다 (미래 자료를 쓰지 않음)
- 모델: 릿지(기준선 선형), LightGBM(주 모델). 방향은 로지스틱 회귀, LightGBM 분류기
- 평가: 표본 밖 R², 평균절대오차, Diebold–Mariano 검정(일별 손실 차이의 평균, Newey-West 표준오차), 방향은 Brier 점수·AUC
- 예상 범위: LightGBM 분위 회귀(10%·50%·90%)로 다음 날 개인 순매수의 범위와 실제 적중률

입력: analysis_v2.py와 같음 (--base, --out/index_v2)
출력: reports/predict_report.{json,md}, predictions/latest_priv_interval.csv (가장 최근 날짜의 종목별 예상 범위)
사용: python predict_v2.py --base <toss_fear_greed 폴더> --out v2_out [--min-train 120 --refit 20]
"""
import argparse
import json
import os
import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import LogisticRegression, RidgeCV
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import write_json

warnings.filterwarnings("ignore")
P = argparse.ArgumentParser()
P.add_argument("--base", required=True)
P.add_argument("--out", default="v2_out")
P.add_argument("--min-train", type=int, default=120)
P.add_argument("--refit", type=int, default=20)
A = P.parse_args()
KOSDAQ = {"086520", "196170", "000250", "028300", "058470", "005290", "036930", "403870", "032820", "277810", "108490", "222800"}

# ---------------- 패널 (analysis_v2.py와 같은 변수) ----------------
s = pd.read_csv(os.path.join(A.out, "index_v2", "daily_stock.csv"), dtype={"code": str})
ohl = json.load(open(os.path.join(A.base, "ohlcv.json")))
kidx = json.load(open(os.path.join(A.base, "krx_index.json")))
inv = json.load(open(os.path.join(A.base, "krx_investor.json")))
usf = os.path.join(A.base, "us_overnight.csv")
us = pd.read_csv(usf, dtype={"date": str}).set_index("date").us_ret.to_dict() if os.path.exists(usf) else None
ahf = os.path.join(A.base, "nxt_after.json")
ah = json.load(open(ahf)) if os.path.exists(ahf) else None
px = lambda c, t, k: (ohl.get(c, {}).get(t) or [np.nan] * 5)[k]
for k, n in enumerate(["open", "high", "low", "close", "vol"]):
    s[n] = [px(c, t, k) for c, t in zip(s.code, s.date)]
s = s[s.close.notna() & (s.open > 0)].sort_values(["code", "date"]).reset_index(drop=True)
mk = np.where(s.code.isin(KOSDAQ), "KOSDAQ", "KOSPI")
s["m_close"] = [(kidx[m].get(t) or [np.nan] * 5)[3] for m, t in zip(mk, s.date)]
g = s.groupby("code")
s["ret"] = (s.close / g.close.shift(1) - 1) * 100
s["gap"] = (s.open / g.close.shift(1) - 1) * 100
s["mret"] = (s.m_close / g.m_close.shift(1) - 1) * 100
s["absret"] = s.ret.abs()
s["range"] = (s.high - s.low) / s.open * 100
s["lvr"] = np.log(s.vol / g.vol.transform(lambda v: v.shift(1).rolling(20, min_periods=5).mean()))
s["tv"] = s.close * s.vol
for w, k in [("priv", "개인"), ("inst", "기관합계"), ("frgn", "외국인합계")]:
    s[w] = [(inv.get(c, {}).get(t) or {}).get(k) for c, t in zip(s.code, s.date)]
    s[w] = s[w].astype(float) / s.tv * 100
s["pro"] = s.inst + s.frgn
s["lattn"] = np.log(s.attn_ratio.clip(lower=0.05))
z = lambda v: (v - v.mean()) / v.std()
for a, b in [("S_z", "S_shr"), ("day_z", "S_day_shr"), ("night_z", "S_night_shr"), ("conc_z", "concentration"), ("resid_z", "resid")]:
    s[a] = z(s[b])
s["buy_z"] = z(s.buy_ratio).fillna(0)
s["buy_na"] = s.buy_ratio.isna().astype(float)
s["us_ret"] = s.date.map(us) if us else 0.0
s["ah"] = [((ah.get(c) or {}).get(t, 0.0)) for c, t in zip(s.code, s.date)] if ah else 0.0
g = s.groupby("code")
for c in ["ret", "priv", "lattn", "S_z"]:
    s[c + "_1"] = g[c].shift(1)
for c in ["priv", "lvr", "range", "gap", "night_z", "us_ret"]:
    s[c + "_n1"] = g[c].shift(-1)
s["gap_up_n1"] = (s.gap_n1 > 0).astype(float).where(s.gap_n1.notna())

MARKET = ["ret", "ret_1", "absret", "lvr", "range", "mret", "priv", "priv_1", "pro"]
COMM = ["S_z", "S_z_1", "day_z", "night_z", "lattn", "lattn_1", "conc_z", "resid_z", "buy_z", "buy_na"]
# 다음 날 시가는 그날 밤 글(다음 거래일의 야간 심리)과 밤사이 미국 증시, 그날 저녁 시간외까지 알고 예측한다
GAP_MARKET = MARKET + (["us_ret_n1"] if us else []) + (["ah"] if ah else [])
TASKS = {"priv_n1": ("reg", MARKET, COMM), "lvr_n1": ("reg", MARKET, COMM), "range_n1": ("reg", MARKET, COMM),
         "gap_up_n1": ("clf", GAP_MARKET, COMM + ["night_z_n1"])}
dates = sorted(s.date.unique())


def lgb_reg(**kw):
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=50, subsample=0.8,
                             subsample_freq=1, colsample_bytree=0.8, verbose=-1, **kw)


def lgb_clf():
    return lgb.LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=50, subsample=0.8,
                              subsample_freq=1, colsample_bytree=0.8, verbose=-1)


def walk(y, xs, kind, model):
    d = s[["date", "code", y] + xs].replace([np.inf, -np.inf], np.nan).dropna()
    preds = []
    for i in range(A.min_train, len(dates), A.refit):
        tr = d[d.date < dates[i]]
        end = dates[i + A.refit] if i + A.refit < len(dates) else None
        te = d[(d.date >= dates[i]) & ((d.date < end) if end else True)]
        if te.empty or len(tr) < 200:
            continue
        if kind == "reg":
            m = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 12))) if model == "ridge" else lgb_reg()
            m.fit(tr[xs], tr[y])
            p = m.predict(te[xs])
        else:
            m = make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=2000)) if model == "ridge" else lgb_clf()
            m.fit(tr[xs], tr[y].astype(int))
            p = m.predict_proba(te[xs])[:, 1]
        preds.append(te[["date", "code", y]].assign(pred=p, hist_mean=tr[y].mean()))
    return pd.concat(preds) if preds else pd.DataFrame()


def dm_test(la, lb):
    """일별 평균 손실 차이(b − a)의 평균이 0인지. 음수면 b가 더 좋음."""
    dd = (lb - la).groupby(level=0).mean()
    r = sm.OLS(dd.values, np.ones(len(dd))).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    return float(r.params[0]), float(r.tvalues[0]), float(r.pvalues[0])


R = {"min_train_days": A.min_train, "refit_days": A.refit, "n_dates": len(dates), "tasks": {}}
for y, (kind, mx, cx) in TASKS.items():
    R["tasks"][y] = {}
    for model in ("ridge", "lgbm"):
        a = walk(y, mx, kind, model)
        b = walk(y, mx + cx, kind, model)
        key = ["date", "code"]
        mm = a.merge(b[key + ["pred"]], on=key, suffixes=("_mkt", "_all")).set_index("date")
        yt = mm[y]
        if kind == "reg":
            sse = lambda p: ((yt - p) ** 2)
            r2 = lambda p: 1 - sse(p).sum() / ((yt - mm.hist_mean) ** 2).sum()
            diff, t, p = dm_test(sse(mm.pred_mkt), sse(mm.pred_all))
            R["tasks"][y][model] = {"n": int(len(mm)), "r2_oos_market": float(r2(mm.pred_mkt)), "r2_oos_all": float(r2(mm.pred_all)),
                                    "mae_market": float((yt - mm.pred_mkt).abs().mean()), "mae_all": float((yt - mm.pred_all).abs().mean()),
                                    "dm_loss_diff": diff, "dm_t": t, "dm_p": p}
        else:
            br = lambda p: (yt - p) ** 2
            diff, t, p = dm_test(br(mm.pred_mkt), br(mm.pred_all))
            R["tasks"][y][model] = {"n": int(len(mm)), "base_rate": float(yt.mean()),
                                    "brier_hist": float(brier_score_loss(yt, mm.hist_mean.clip(0.01, 0.99))),
                                    "brier_market": float(brier_score_loss(yt, mm.pred_mkt)), "brier_all": float(brier_score_loss(yt, mm.pred_all)),
                                    "auc_market": float(roc_auc_score(yt, mm.pred_mkt)), "auc_all": float(roc_auc_score(yt, mm.pred_all)),
                                    "dm_loss_diff": diff, "dm_t": t, "dm_p": p}
        print(y, model, {k: round(v, 4) if isinstance(v, float) else v for k, v in R["tasks"][y][model].items()}, flush=True)

# ---------------- 변수 중요도 (전체 기간 LightGBM, 이득 기준) ----------------
d = s[["priv_n1"] + MARKET + COMM].replace([np.inf, -np.inf], np.nan).dropna()
m = lgb_reg().fit(d[MARKET + COMM], d.priv_n1)
imp = pd.Series(m.booster_.feature_importance("gain"), index=MARKET + COMM)
R["importance_priv_n1"] = (imp / imp.sum()).sort_values(ascending=False).round(4).to_dict()

# ---------------- 개인 수급 예상 범위 (분위 회귀) ----------------
X = MARKET + COMM
d = s[["date", "code", "priv_n1"] + X].replace([np.inf, -np.inf], np.nan).dropna(subset=X)
hist = d.dropna(subset=["priv_n1"])
cut = dates[int(len(dates) * 0.75)]
tr, te = hist[hist.date < cut], hist[hist.date >= cut]
qs = {q: lgb_reg(objective="quantile", alpha=q).fit(tr[X], tr.priv_n1) for q in (0.1, 0.5, 0.9)}
lo, mid, hi = (qs[q].predict(te[X]) for q in (0.1, 0.5, 0.9))
R["priv_interval_test"] = {"split_date": cut, "n": int(len(te)), "coverage_10_90": float(((te.priv_n1 >= lo) & (te.priv_n1 <= hi)).mean()),
                           "mean_width": float(np.mean(hi - lo)), "mae_median": float(np.mean(np.abs(te.priv_n1 - mid)))}
qs = {q: lgb_reg(objective="quantile", alpha=q).fit(hist[X], hist.priv_n1) for q in (0.1, 0.5, 0.9)}
last = d[d.date == d.date.max()].copy()
for q in (0.1, 0.5, 0.9):
    last[f"q{int(q * 100)}"] = qs[q].predict(last[X])
os.makedirs(os.path.join(A.out, "predictions"), exist_ok=True)
last[["date", "code", "q10", "q50", "q90"]].to_csv(os.path.join(A.out, "predictions", "latest_priv_interval.csv"), index=False, float_format="%.3f")
write_json(os.path.join(A.out, "reports", "predict_report.json"), R)

# ---------------- 보고서 ----------------
NM = {"priv_n1": "다음 날 개인 순매수 비율", "lvr_n1": "다음 날 거래량 비율(log)", "range_n1": "다음 날 일중 변동폭", "gap_up_n1": "다음 날 시가 상승 여부"}
L = ["# 예측 모델 비교: 시장 자료만 vs + 커뮤니티 변수", "",
     f"날짜 순 확장 창, 처음 {A.min_train}거래일 학습 후 {A.refit}거래일마다 재학습. DM = 커뮤니티 변수를 더한 모델의 일별 손실 − 시장 자료만 모델 (음수면 개선).", "",
     "| 대상 | 모델 | 표본 | 시장 자료만 | + 커뮤니티 | DM t (p) |", "|---|---|---|---|---|---|"]
for y, mm in R["tasks"].items():
    for model, r in mm.items():
        if "r2_oos_all" in r:
            L.append(f"| {NM[y]} | {model} | {r['n']:,} | R² {r['r2_oos_market']:.3f} | R² {r['r2_oos_all']:.3f} | {r['dm_t']:.2f} ({r['dm_p']:.3f}) |")
        else:
            L.append(f"| {NM[y]} | {model} | {r['n']:,} | Brier {r['brier_market']:.4f}, AUC {r['auc_market']:.3f} | Brier {r['brier_all']:.4f}, AUC {r['auc_all']:.3f} | {r['dm_t']:.2f} ({r['dm_p']:.3f}) |")
pi = R["priv_interval_test"]
L += ["", "## 다음 날 개인 순매수 예상 범위 (LightGBM 분위 회귀)", "",
      f"{pi['split_date']} 이후 {pi['n']:,}건 시험: 10~90% 범위 적중률 {pi['coverage_10_90']:.1%} (목표 80%), 평균 폭 {pi['mean_width']:.2f}%p, 중앙값 절대오차 {pi['mae_median']:.2f}%p", "",
      "## 다음 날 개인 순매수 예측의 변수 중요도 (상위 8)", ""]
L += [f"- {k}: {v:.1%}" for k, v in list(R["importance_priv_n1"].items())[:8]]
open(os.path.join(A.out, "reports", "predict_report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L))
