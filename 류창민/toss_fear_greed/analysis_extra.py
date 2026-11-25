"""보완 분석 (발표 4-4장). 입력: index_out/daily_stock.csv, ohlcv.json, krx_index.json, krx_investor.json, krx_short.json, sectors.json
C2 지수 구간·국면별 이후 성과 / C3 심리·글 수 → 다음 날 거래량·변동폭·공매도 / C4 의견 갈림 → 거래량
C6 탐욕·공포 비율 충격의 0~10일 반응 경로 / B4 잔차 심리(주가로 설명되는 부분을 뺀 심리) / C5 다음 날 수급·거래량·변동폭 예측 비교
회귀는 모두 종목·날짜 고정효과, 종목·날짜 이중 군집 표준오차. 출력: extra_results.json
사용: uv run --python 3.10 --with pandas --with statsmodels --with scikit-learn python analysis_extra.py"""
import json, os
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
import statsmodels.api as sm

D = os.path.dirname(os.path.abspath(__file__)); os.chdir(D)
KOSDAQ = {"086520","196170","000250","028300","058470","005290","036930","403870","032820","277810","108490","222800"}
ohl = json.load(open("ohlcv.json")); kidx = json.load(open("krx_index.json")); inv = json.load(open("krx_investor.json")); sht = json.load(open("krx_short.json"))
s = pd.read_csv("index_out/daily_stock.csv", dtype={"code": str})
px = lambda c, d, k: (ohl.get(c, {}).get(d) or [None] * 5)[k]
for i, k in enumerate(["open", "high", "low", "close", "vol"]): s[k] = [px(c, d, i) for c, d in zip(s.code, s.date)]
s = s[s.close.notna() & (s.open > 0)].sort_values(["code", "date"]).reset_index(drop=True)
s["mk"] = np.where(s.code.isin(KOSDAQ), "KOSDAQ", "KOSPI")
s["m_close"] = [(kidx[m].get(t) or [None] * 5)[3] for m, t in zip(s.mk, s.date)]
g = s.groupby("code")
s["ret"] = (s.close / g.close.shift(1) - 1) * 100
s["mret"] = (s.m_close / g.m_close.shift(1) - 1) * 100
s["exret"] = s.ret - s.mret
s["range"] = (s.high - s.low) / s.open * 100                                     # 일중 변동폭
s["vr"] = s.vol / g.vol.transform(lambda v: v.shift(1).rolling(20, min_periods=10).mean())   # 거래량 ÷ 직전 20일 평균
s["tv"] = s.close * s.vol
for w, k in [("priv", "개인"), ("inst", "기관합계"), ("frgn", "외국인합계")]:
    s[w] = [(inv.get(c, {}).get(d) or {}).get(k) for c, d in zip(s.code, s.date)]; s[w] = s[w] / s.tv * 100
s["short"] = pd.to_numeric(pd.Series([(sht.get(c, {}).get(d) or {}).get("비중") for c, d in zip(s.code, s.date)], index=s.index), errors="coerce")   # 공매도 비중(%), 2025-03-31 재개 이후
s["greed_sh"] = s.n_greed / s.n_posts.where(s.n_posts > 0); s["fear_sh"] = s.n_fear / s.n_posts.where(s.n_posts > 0)
s["disagree"] = 1 - s.concentration                                            # 의견 갈림 = 탐욕·공포 엔트로피
s["lint"] = np.log(s.interest.where(s.interest > 0))                           # 관심도(글 수 ÷ 20일 평균)의 로그
s["absret"] = s.ret.abs()
g = s.groupby("code")
for c in ["vr", "range", "priv", "short", "exret"]: s[c + "_n1"] = g[c].shift(-1)
for h in (1, 5, 20): s[f"fwd{h}"] = sum(g.exret.shift(-k) for k in range(1, h + 1))   # 이후 h일 누적 초과수익률(%p)
s = s.replace([np.inf, -np.inf], np.nan)                                     # 0으로 나눈 값 제거
z = lambda v: (v - v.mean()) / v.std()
s["Sz"] = z(s.S)
R = {}

def fe(formula, data):
    """종목·날짜 고정효과: 변수마다 종목 평균과 날짜 평균을 번갈아 빼는 방식(더미 회귀와 같은 계수), 종목·날짜 이중 군집 표준오차."""
    y, xs = formula.split("~"); cols = [y.strip()] + [c.strip() for c in xs.split("+")]
    d0 = data.dropna(subset=cols)[cols + ["code", "date"]].copy()
    for c in cols: d0[c] = d0[c].astype(float)
    for _ in range(30):
        prev = d0[cols].copy()
        d0[cols] = d0[cols] - d0.groupby("code")[cols].transform("mean")
        d0[cols] = d0[cols] - d0.groupby("date")[cols].transform("mean")
        if (d0[cols] - prev).abs().max().max() < 1e-9: break
    gg = np.column_stack([d0.code.astype("category").cat.codes, d0.date.astype("category").cat.codes])
    return smf.ols(f"{cols[0]} ~ {' + '.join(cols[1:])} - 1", data=d0).fit(cov_type="cluster", cov_kwds={"groups": gg})
def keep(m, names): return {k: {"b": float(m.params[k]), "t": float(m.tvalues[k]), "p": float(m.pvalues[k])} for k in names} | {"n": int(m.nobs)}

# ---------- B4 잔차 심리: 그날·전날 수익률과 시장 수익률로 설명되는 부분을 뺀 심리 ----------
s["ret_1"] = g.ret.shift(1)
base = s.dropna(subset=["S", "ret", "mret", "ret_1"])
m = smf.ols("S ~ ret + mret + ret_1 + C(code)", data=base).fit()
s.loc[base.index, "S_res"] = m.resid; s["Sres_z"] = z(s.S_res)
R["b4_fit"] = {"r2": float(m.rsquared), "b_ret": float(m.params["ret"]), "n": int(m.nobs)}
x = s.dropna(subset=["S_res", "ret"])
R["b4_cases"] = {"up_but_fear": float(((x.ret > 1) & (x.S_res < x.S_res.quantile(.2))).mean()),
                 "down_but_greed": float(((x.ret < -1) & (x.S_res > x.S_res.quantile(.8))).mean())}
for y in ["fwd1", "fwd5", "priv_n1", "vr_n1"]:
    R[f"b4_{y}"] = keep(fe(f"{y} ~ Sres_z + ret + vr", s), ["Sres_z"])

# ---------- C2 지수 구간·국면별 이후 성과 ----------
s["bucket"] = pd.cut(s.direction, [-0.1, 20, 40, 60, 80, 100.1], labels=["0~20 극단적 공포", "20~40 공포", "40~60 중립", "60~80 탐욕", "80~100 극단적 탐욕"])
t = s.dropna(subset=["bucket", "fwd20"]).groupby("bucket", observed=True).agg(
    n=("fwd1", "size"), fwd1=("fwd1", "mean"), fwd5=("fwd5", "mean"), fwd20=("fwd20", "mean"),
    up5=("fwd5", lambda v: (v > 0).mean()), range1=("range_n1", "mean"), priv1=("priv_n1", "mean")).reset_index()
R["c2_bucket"] = [{k: (str(v) if k == "bucket" else float(v)) for k, v in r.items()} for r in t.to_dict("records")]
t = s.dropna(subset=["regime", "fwd20"]).groupby("regime").agg(n=("fwd1", "size"), fwd1=("fwd1", "mean"), fwd5=("fwd5", "mean"), fwd20=("fwd20", "mean"), priv1=("priv_n1", "mean")).reset_index()
R["c2_regime"] = t.to_dict("records")
s["xfear"] = (s.direction <= 20).astype(float); s["xgreed"] = (s.direction >= 80).astype(float)
for h in (1, 5, 20):   # 극단 구간 vs 나머지 (같은 날 다른 종목과 비교: 날짜 고정효과)
    R[f"c2_reg_fwd{h}"] = keep(fe(f"fwd{h} ~ xfear + xgreed", s.dropna(subset=["direction"])), ["xfear", "xgreed"])

# ---------- C3 심리·글 수 → 다음 날 거래량·변동폭·공매도 ----------
for y, ctrl in [("vr_n1", "vr"), ("range_n1", "range"), ("short_n1", "short")]:
    data = (s if y != "short_n1" else s[s.date >= "2025-03-31"]).dropna(subset=[y, ctrl, "Sz", "lint", "absret"])
    R[f"c3_{y}"] = keep(fe(f"{y} ~ Sz + lint + absret + {ctrl}", data), ["Sz", "lint"])

# ---------- C4 의견 갈림 → 거래량 ----------
s["dis_z"] = z(s.disagree)
R["c4_same"] = keep(fe("vr ~ dis_z + lint + absret", s), ["dis_z", "lint"])
R["c4_next"] = keep(fe("vr_n1 ~ dis_z + lint + absret + vr", s), ["dis_z", "lint"])
R["c4_quint"] = s.dropna(subset=["disagree", "vr"]).groupby(pd.qcut(s.disagree, 5, labels=False, duplicates="drop")).vr.mean().round(3).tolist()

# ---------- C6 탐욕·공포 비율 충격의 0~10일 반응 경로 (local projection) ----------
s["gz"] = z(s.greed_sh); s["fz"] = z(s.fear_sh)
path = []
for h in range(0, 11):
    s["cum_h"] = s.exret if h == 0 else sum(g.exret.shift(-k) for k in range(1, h + 1))
    s["priv_h"] = g.priv.shift(-h)
    a = keep(fe("cum_h ~ gz + fz + ret_1", s), ["gz", "fz"]); b = keep(fe("priv_h ~ gz + fz + ret_1", s), ["gz", "fz"])
    path.append({"h": h, "ret_g": a["gz"]["b"], "ret_g_t": a["gz"]["t"], "ret_f": a["fz"]["b"], "ret_f_t": a["fz"]["t"],
                 "priv_g": b["gz"]["b"], "priv_g_t": b["gz"]["t"], "priv_f": b["fz"]["b"], "priv_f_t": b["fz"]["t"]})
R["c6_path"] = path

# ---------- C5 다음 날 개인 순매수·거래량·변동폭 예측: 시장 자료만 vs + 커뮤니티 ----------
from sklearn.linear_model import RidgeCV
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
MKT = ["ret", "mret", "ret_1", "absret", "vr", "range", "priv", "inst", "frgn"]
COM = MKT + ["S", "kw", "lint", "disagree", "pre_S", "greed_sh", "fear_sh", "S_res"]
s["lnp"] = np.log1p(s.n_posts); COM.append("lnp")
months = sorted(s.date.str[:7].unique()); test_months = [m_ for m_ in months if "2025-07" <= m_ <= "2026-10"]
out = {}
for y in ["priv_n1", "vr_n1", "range_n1"]:
    dd = s.dropna(subset=COM + [y]).copy(); dd["ym"] = dd.date.str[:7]
    preds = {k: [] for k in ["mkt_ridge", "com_ridge", "mkt_gbm", "com_gbm"]}; truth = []; dates = []
    for m_ in test_months:
        tr, te = dd[dd.ym < m_], dd[dd.ym == m_]
        if te.empty: continue
        for name, cols in (("mkt", MKT), ("com", COM)):
            r = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 12))).fit(tr[cols], tr[y]); preds[f"{name}_ridge"] += list(r.predict(te[cols]))
            gb = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=31, random_state=0).fit(tr[cols], tr[y]); preds[f"{name}_gbm"] += list(gb.predict(te[cols]))
        truth += list(te[y]); dates += list(te.date)
    truth = np.array(truth); res = {}
    base_mse = np.mean((truth - truth.mean()) ** 2)
    for k, p in preds.items(): res[k] = {"r2": float(1 - np.mean((truth - np.array(p)) ** 2) / base_mse), "mae": float(np.mean(np.abs(truth - np.array(p))))}
    for mdl in ("ridge", "gbm"):   # Diebold–Mariano: 날짜별 평균 제곱오차 차이(시장만 − 커뮤니티 추가)의 평균, HAC 표준오차
        e = pd.DataFrame({"date": dates, "d": (truth - np.array(preds[f"mkt_{mdl}"])) ** 2 - (truth - np.array(preds[f"com_{mdl}"])) ** 2}).groupby("date").d.mean()
        o = sm.OLS(e.values, np.ones(len(e))).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
        res[f"dm_{mdl}"] = {"mean_gain": float(o.params[0]), "t": float(o.tvalues[0]), "days": int(len(e))}
    res["n_test"] = int(len(truth)); out[y] = res
R["c5"] = out; R["c5_test"] = [test_months[0], test_months[-1]]

R["short_coverage"] = {"days": int(s[s.date >= "2025-03-31"].short.notna().sum()), "zero_share": float((s[s.date >= "2025-03-31"].short == 0).mean())}
json.dump(R, open("extra_results.json", "w"), ensure_ascii=False, indent=1, default=float)
pr = lambda k: print(k, json.dumps(R[k], ensure_ascii=False, default=float)[:600])
for k in ["b4_fit", "b4_cases", "b4_fwd1", "b4_fwd5", "b4_priv_n1", "b4_vr_n1", "c2_bucket", "c2_regime", "c2_reg_fwd1", "c2_reg_fwd5", "c2_reg_fwd20",
          "c3_vr_n1", "c3_range_n1", "c3_short_n1", "c4_same", "c4_next", "c4_quint", "c5", "short_coverage"]: pr(k)
for r in path: print(r["h"], round(r["ret_g"], 3), round(r["ret_g_t"], 1), round(r["ret_f"], 3), round(r["ret_f_t"], 1), "| priv", round(r["priv_g"], 2), round(r["priv_g_t"], 1), round(r["priv_f"], 2), round(r["priv_f_t"], 1))
