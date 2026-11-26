"""가설 검정(수정): 밤사이(전 거래일 20:00 ~ 당일 09:00 전) 감성이 당일 주가 방향을 설명하는가 + 감성이 주가를 후행하는가.
패널: 종목 × 거래일, 종목 고정효과, 표준오차는 종목·날짜 이중 군집. 시장 수준은 시계열 OLS(Newey-West).
입력: index_out/daily_stock.csv, index_out/daily_market.csv, ohlcv.json. 출력: krx_results.json"""
import json
import numpy as np, pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

s = pd.read_csv("index_out/daily_stock.csv", dtype={"code": str})
mk = pd.read_csv("index_out/daily_market.csv")
ohl = json.load(open("ohlcv.json"))
idx = json.load(open("krx_index.json"))   # KRX 로그인 자료: 코스피·코스닥 지수 일봉
ohl["KOSPI"], ohl["KOSDAQ"] = idx["KOSPI"], idx["KOSDAQ"]
KOSDAQ = {"086520","196170","000250","028300","058470","005290","036930","403870","032820","277810","108490","222800"}
import glob
COVER = max(open(f).read().strip().split("\n")[-1].split(",")[0] for f in glob.glob("apply_out4/*_2026-*.csv") if open(f).read().strip().count("\n"))   # 집계된 마지막 30분 칸
live = set(mk.loc[(mk.n_posts > 0) & (mk.date + "T08:30" <= COVER), "date"])   # 그날 09:00 전 글까지 다 모인 거래일만
s = s[s.date.isin(live)].sort_values(["code", "date"]).copy()
px = lambda c, d, k: (ohl[c].get(d) or [None]*5)[k]
s["open"] = [px(c, d, 0) for c, d in zip(s.code, s.date)]; s["close"] = [px(c, d, 3) for c, d in zip(s.code, s.date)]
s["vol"] = [px(c, d, 4) for c, d in zip(s.code, s.date)]
s["etf"] = np.where(s.code.isin(KOSDAQ), "KOSDAQ", "KOSPI")
s["m_open"] = [px(e, d, 0) for e, d in zip(s.etf, s.date)]; s["m_close"] = [px(e, d, 3) for e, d in zip(s.etf, s.date)]
g = s.groupby("code")
s["ret"] = s.close / g.close.shift(1) - 1                          # 당일 수익률 (전일 종가 → 당일 종가)
s["gap"] = np.where(s.open > 0, s.open / g.close.shift(1) - 1, np.nan)                           # 갭 (전일 종가 → 당일 시가)
s["intra"] = np.where(s.open > 0, s.close / s.open - 1, np.nan)                                  # 장중 (당일 시가 → 종가)
s["mret"] = s.m_close / g.m_close.shift(1) - 1
s["exret"] = s.ret - s.mret
s["up"] = (s.ret > 0).astype(float)
s["night"] = (s.pre_n_greed - s.pre_n_fear) / (s.pre_n_posts + 10)  # 밤사이 감성 (분모 +10, 기획안 S와 같은 꼴)
s["night8"] = (s.pre8_n_greed - s.pre8_n_fear) / (s.pre8_n_posts + 10)  # 강건성: 08:00 전까지
s["vr"] = s.vol / g.vol.transform(lambda v: v.shift(1).rolling(20, min_periods=5).mean())
for c in ["ret", "mret", "S", "night", "vr"]:
    s[c + "_1"] = g[c].shift(1)
s["ret_next"] = g.ret.shift(-1)
d = s.dropna(subset=["ret", "ret_1", "mret_1", "S_1", "night", "night_1", "vr_1", "gap", "intra"]).copy()
d = d[d.pre_n_posts >= 5]                                          # 밤 글 5건 이상인 종목·일만
# 단위: 감성은 표준편차 1 단위로 (해석 쉽게), 수익률은 %
for c in ["night", "night_1", "S_1", "S", "night8"]:
    d[c + "_z"] = (d[c] - d[c].mean()) / d[c].std()
for c in ["ret", "ret_1", "mret", "mret_1", "gap", "intra", "exret"]:
    d[c + "_p"] = d[c] * 100
d["date_id"] = d.date.astype("category").cat.codes; d["code_id"] = d.code.astype("category").cat.codes
groups = np.column_stack([d.code_id, d.date_id])

def fe(formula, data=d):
    # 식에 쓰인 변수에 결측이 있는 행은 statsmodels가 빼므로, 군집 배열도 실제 쓰인 행 기준으로 만든다 (장중 실행 시 당일 지수 일봉 없음 → exret 결측)
    m0 = smf.ols(formula + " + C(code)", data=data, missing="drop")
    idx = m0.data.row_labels
    g = np.column_stack([data.loc[idx, "code_id"], data.loc[idx, "date_id"]])
    return m0.fit(cov_type="cluster", cov_kwds={"groups": g})

res = {"n": int(len(d)), "stocks": int(d.code.nunique()), "days": int(d.date.nunique()), "period": [d.date.min(), d.date.max()]}
def keep(m, names):
    return {k: {"b": float(m.params[k]), "se": float(m.bse[k]), "t": float(m.tvalues[k]), "p": float(m.pvalues[k])} for k in names}

# H1 선행: 밤사이 감성 → 당일 수익률 (전일 수익률·전일 장중 감성·전일 시장 수익률·전일 거래량 비율 통제)
m1 = fe("ret_p ~ night_z + ret_1_p + S_1_z + mret_1_p + vr_1")
res["lead_ret"] = keep(m1, ["night_z", "ret_1_p", "S_1_z", "mret_1_p"])
m1x = fe("exret_p ~ night_z + ret_1_p + S_1_z + mret_1_p + vr_1")
res["lead_exret"] = keep(m1x, ["night_z"])
m1g = fe("gap_p ~ night_z + ret_1_p + S_1_z + mret_1_p + vr_1"); res["lead_gap"] = keep(m1g, ["night_z"])
m1i = fe("intra_p ~ night_z + ret_1_p + S_1_z + mret_1_p + vr_1"); res["lead_intra"] = keep(m1i, ["night_z"])
# 방향(상승 여부) 선형확률모형
m1u = fe("up ~ night_z + ret_1_p + S_1_z + mret_1_p + vr_1"); res["lead_up"] = keep(m1u, ["night_z"])
m8 = fe("ret_p ~ night8_z + ret_1_p + S_1_z + mret_1_p + vr_1"); res["lead_ret_0800"] = keep(m8, ["night8_z"])
m8g = fe("gap_p ~ night8_z + ret_1_p + S_1_z + mret_1_p + vr_1"); res["lead_gap_0800"] = keep(m8g, ["night8_z"])
m8i = fe("intra_p ~ night8_z + ret_1_p + S_1_z + mret_1_p + vr_1"); res["lead_intra_0800"] = keep(m8i, ["night8_z"])
# H2 후행: 전일 수익률 → 밤사이 감성 (전 밤사이 감성·전일 시장 수익률 통제)
m2 = fe("night_z ~ ret_1_p + night_1_z + mret_1_p + vr_1")
res["lag_night"] = keep(m2, ["ret_1_p", "night_1_z", "mret_1_p"])
# 표준화 계수 비교: 같은 단위(표준편차)로 선행 vs 후행
d["ret_z"] = (d.ret - d.ret.mean()) / d.ret.std(); d["ret_1_z"] = (d.ret_1 - d.ret_1.mean()) / d.ret_1.std()
a = fe("ret_z ~ night_z + ret_1_z + S_1_z + mret_1_p + vr_1"); b = fe("night_z ~ ret_1_z + night_1_z + mret_1_p + vr_1")
res["std_compare"] = {"lead_night_to_ret": keep(a, ["night_z"])["night_z"], "lag_ret_to_night": keep(b, ["ret_1_z"])["ret_1_z"]}
# 방향 적중률: 밤사이 감성 부호만으로 당일 상승/하락
sgn = d[d.night.abs() > 0]
res["hit_sign"] = {"all": float(((sgn.night > 0) == (sgn.ret > 0)).mean()), "n": int(len(sgn)),
                   "base_up": float((d.ret > 0).mean())}
q = d.groupby(pd.qcut(d.night, 5, labels=False, duplicates="drop")).agg(night=("night", "mean"), ret=("ret_p", "mean"), up=("up", "mean"), n=("up", "size"))
res["quintile"] = q.reset_index(drop=True).to_dict("records")

# 시장 수준: 45종목 밤사이 감성(글 수 가중) → 코스피 지수 당일 수익률, 그리고 후행
m = s.groupby("date").apply(lambda x: pd.Series({"night": ((x.pre_n_greed - x.pre_n_fear).sum()) / (x.pre_n_posts.sum() + 10)})).reset_index()
k = pd.DataFrame({"date": list(ohl["KOSPI"])}); k["c"] = [ohl["KOSPI"][t][3] for t in k.date]; k["ret"] = k.c.pct_change() * 100
m = m.merge(k[["date", "ret"]], on="date").sort_values("date"); m = m[m.date.isin(live)]
m["ret_1"] = m.ret.shift(1); m["night_1"] = m.night.shift(1)
m["night_z"] = (m.night - m.night.mean()) / m.night.std(); m["night_1_z"] = (m.night_1 - m.night.mean()) / m.night.std()
mm = m.dropna()
r1 = smf.ols("ret ~ night_z + ret_1", data=mm).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
r2 = smf.ols("night_z ~ ret_1 + night_1_z", data=mm).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
res["market_lead"] = keep(r1, ["night_z", "ret_1"]); res["market_lag"] = keep(r2, ["ret_1", "night_1_z"])
res["market_n"] = int(len(mm)); res["market_hit"] = float(((mm.night_z > 0) == (mm.ret > 0)).mean())
json.dump(res, open("krx_results.json", "w"), ensure_ascii=False, indent=1)
f = lambda x: f"b={x['b']:.4f} t={x['t']:.2f} p={x['p']:.4f}"
print("표본", res["n"], res["stocks"], res["days"], res["period"])
print("선행 당일수익률(%) ← 밤감성 1sd:", f(res["lead_ret"]["night_z"]))
print("   초과수익률:", f(res["lead_exret"]["night_z"]), "| 갭:", f(res["lead_gap"]["night_z"]), "| 장중:", f(res["lead_intra"]["night_z"]), "| 상승확률:", f(res["lead_up"]["night_z"]))
print("08:00 전까지:", f(res["lead_ret_0800"]["night8_z"]), "| 갭", f(res["lead_gap_0800"]["night8_z"]), "| 장중", f(res["lead_intra_0800"]["night8_z"]))
print("후행 밤감성(sd) ← 전일수익률 1%p:", f(res["lag_night"]["ret_1_p"]))
print("표준화 비교 선행", f(res["std_compare"]["lead_night_to_ret"]), "/ 후행", f(res["std_compare"]["lag_ret_to_night"]))
print("부호 적중률", res["hit_sign"], "\n5분위", q.round(3).to_string())
print("시장 선행", f(res["market_lead"]["night_z"]), "시장 후행", f(res["market_lag"]["ret_1"]), "n", res["market_n"], "적중", round(res["market_hit"], 3))
# 쉬운 화면용: 오늘 등락 구간별 그날 밤 감성(후행), 밤사이 감성 5분위별 갭·장중
b = d.copy(); b["bin"] = pd.cut(b.ret_1 * 100, [-100, -3, -1, 1, 3, 100], labels=["−3% 이하", "−3~−1%", "−1~+1%", "+1~+3%", "+3% 이상"])
lagb = b.groupby("bin", observed=True).agg(night=("night", "mean"), pos=("pre_n_greed", "sum"), neg=("pre_n_fear", "sum"), allp=("pre_n_posts", "sum"), n=("night", "size")).reset_index()
lagb["pos_share"] = lagb.pos / lagb.allp; lagb["neg_share"] = lagb.neg / lagb.allp
res["lag_bins"] = [{"bin": str(r.bin), "night": float(r.night), "pos_share": float(r.pos_share), "neg_share": float(r.neg_share), "n": int(r.n)} for r in lagb.itertuples()]
qq = d.groupby(pd.qcut(d.night, 5, labels=False, duplicates="drop")).agg(gap=("gap_p", "mean"), intra=("intra_p", "mean"), up=("up", "mean"), n=("up", "size")).reset_index(drop=True)
res["quintile_gap_intra"] = qq.to_dict("records")
json.dump(res, open("krx_results.json", "w"), ensure_ascii=False, indent=1)
print(lagb[["bin", "night", "pos_share", "neg_share", "n"]].round(3).to_string()); print(qq.round(3).to_string())
