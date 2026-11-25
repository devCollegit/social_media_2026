"""발표용 분석 (4장). 입력: apply_out3/ (종목·30분 집계), index_out/daily_stock.csv·daily_sector.csv, ohlcv.json, krx_index.json, krx_investor.json, trading_days.csv
4-1 글 수 ↔ 개인 수급 / 4-2 투자자별 수급 vs 커뮤니티 심리(종목·섹터, 급락일 전후) / 4-3 주간 vs 야간 감성의 선행·후행 (장초 = 시가 갭)
출력: pres_results.json
사용: uv run --python 3.10 --with pandas --with statsmodels python analysis_presentation.py"""
import bisect, glob, json, os
import numpy as np, pandas as pd
import statsmodels.formula.api as smf

D = os.path.dirname(os.path.abspath(__file__)); os.chdir(D)
TD = pd.read_csv("trading_days.csv")["date"].tolist()
S = json.load(open("sectors.json")); SECTOR = {c: s for s, v in S.items() for c in v}
ohl = json.load(open("ohlcv.json")); kidx = json.load(open("krx_index.json")); inv = json.load(open("krx_investor.json"))
KOSDAQ = {"086520","196170","000250","028300","058470","005290","036930","403870","032820","277810","108490","222800"}
R = {}

# ---------- 공통: 종목·거래일 패널 (주간/야간 글 분리) ----------
def to_tday(slot):   # build_index.py와 같은 규칙: 20:00 이후 → 다음 거래일, 09:00 전·휴장일 → 그 거래일의 '야간'
    d, hm = slot[:10], slot[11:]
    if hm >= "20:00":
        i = bisect.bisect_right(TD, d); return (TD[i] if i < len(TD) else None), "night"
    i = bisect.bisect_left(TD, d)
    if i >= len(TD): return None, None
    td = TD[i]
    return td, ("night" if (td != d or hm < "09:00") else "day")

rows, hours = [], []
for f in sorted(glob.glob("apply_out3/*.csv")):
    x = pd.read_csv(f)
    if x.empty: continue
    x["code"] = os.path.basename(f).split("_")[0]
    m = x.slot_kst.map(to_tday); x["date"] = [a for a, _ in m]; x["part"] = [b for _, b in m]
    rows.append(x.dropna(subset=["date"]))
x = pd.concat(rows)
x = x[x.date >= "2024-10-28"]
# 시간대별 글 분포 (30분 칸 → 시)
x["hour"] = x.slot_kst.str[11:13].astype(int)
h = x.groupby("hour")[["n_posts", "n_greed", "n_fear"]].sum()
R["by_hour"] = [{"hour": int(i), "posts": int(r.n_posts), "greed_share": float(r.n_greed / max(r.n_greed + r.n_fear, 1))} for i, r in h.iterrows()]
pv = x.groupby(["code", "date", "part"])[["n_posts", "n_greed", "n_fear"]].sum().unstack("part").fillna(0)
pv.columns = [f"{p}_{c}" for c, p in pv.columns]; pv = pv.reset_index()
R["posts_total"] = int(x.n_posts.sum()); R["posts_day_share"] = float(x.loc[x.part == "day", "n_posts"].sum() / x.n_posts.sum())

s = pd.read_csv("index_out/daily_stock.csv", dtype={"code": str})[["date", "code", "sector", "n_posts", "n_greed", "n_fear", "S", "direction", "pre8_n_posts", "pre8_n_greed", "pre8_n_fear"]]
s = s.merge(pv, on=["code", "date"], how="left").fillna({c: 0 for c in pv.columns if c not in ("code", "date")})
px = lambda c, d, k: (ohl.get(c, {}).get(d) or [None] * 5)[k]
s["open"] = [px(c, d, 0) for c, d in zip(s.code, s.date)]; s["close"] = [px(c, d, 3) for c, d in zip(s.code, s.date)]
s["vol"] = [px(c, d, 4) for c, d in zip(s.code, s.date)]
s = s[s.close.notna() & (s.open > 0)].sort_values(["code", "date"]).copy()
s["mk"] = np.where(s.code.isin(KOSDAQ), "KOSDAQ", "KOSPI")
s["m_close"] = [(kidx[m].get(d) or [None] * 5)[3] for m, d in zip(s.mk, s.date)]
g = s.groupby("code")
s["ret"] = (s.close / g.close.shift(1) - 1) * 100
s["gap"] = (s.open / g.close.shift(1) - 1) * 100
s["intra"] = (s.close / s.open - 1) * 100
s["mret"] = (s.m_close / g.m_close.shift(1) - 1) * 100
s["tv"] = s.close * s.vol                                           # 거래대금 근사 (종가 × 거래량)
for who, k in [("priv", "개인"), ("inst", "기관합계"), ("frgn", "외국인합계")]:
    s[who + "_amt"] = [(inv.get(c, {}).get(d) or {}).get(k) for c, d in zip(s.code, s.date)]
    s[who] = s[who + "_amt"] / s.tv * 100                           # 순매수 비율(% of 거래대금)
K = 10
s["S_day"] = (s.day_n_greed - s.day_n_fear) / (s.day_n_posts + K)        # 주간(09:00~20:00) 감성
s["S_night"] = (s.night_n_greed - s.night_n_fear) / (s.night_n_posts + K)  # 야간(전일 20:00~당일 09:00) 감성
s["post_ratio"] = s.n_posts / g.n_posts.transform(lambda v: v.shift(1).rolling(20, min_periods=10).mean())   # 관심도 배수
for c in ["ret", "S_day", "S_night", "priv", "inst", "frgn", "post_ratio", "mret"]:
    s[c + "_1"] = s.groupby("code")[c].shift(1)
s["priv_next"] = s.groupby("code").priv.shift(-1)
s["ret_next"] = s.groupby("code").ret.shift(-1)

def fe(formula, data, cluster=True):
    m0 = smf.ols(formula + " + C(code)", data=data, missing="drop")
    idx = m0.data.row_labels
    gg = np.column_stack([data.loc[idx, "code"].astype("category").cat.codes, data.loc[idx, "date"].astype("category").cat.codes])
    return m0.fit(cov_type="cluster", cov_kwds={"groups": gg})
def keep(m, names): return {k: {"b": float(m.params[k]), "t": float(m.tvalues[k]), "p": float(m.pvalues[k])} for k in names}
z = lambda v: (v - v.mean()) / v.std()

# ---------- 4-1 글 수 ↔ 개인 수급 ----------
a = s.dropna(subset=["post_ratio", "priv", "ret"]).copy()
a = a[np.isfinite(a.post_ratio) & (a.n_posts > 0)]
a["bin"] = pd.cut(a.post_ratio, [0, 0.5, 0.8, 1.25, 2, 3, 1e9], labels=["0.5배 미만", "0.5~0.8배", "0.8~1.25배", "1.25~2배", "2~3배", "3배 이상"])
t = a.groupby("bin", observed=True).agg(n=("priv", "size"), priv=("priv", "mean"), priv_next=("priv_next", "mean"), ret=("ret", "mean"), absret=("ret", lambda v: v.abs().mean())).reset_index()
R["posts_vs_priv_bins"] = [{"bin": str(r.bin), "n": int(r.n), "priv": float(r.priv), "priv_next": float(r.priv_next), "ret": float(r.ret), "absret": float(r.absret)} for r in t.itertuples()]
# 오른 날 / 내린 날로 나눠서
a["dir"] = np.where(a.ret > 0, "상승일", "하락일")
t2 = a.groupby(["dir", pd.cut(a.post_ratio, [0, 1.25, 2, 1e9], labels=["평소(1.25배 미만)", "1.25~2배", "2배 이상"])], observed=True).priv.agg(["mean", "size"]).reset_index()
R["posts_vs_priv_by_dir"] = [{"dir": r.dir, "bin": str(r.post_ratio), "priv": float(r[3]), "n": int(r[4])} for r in t2.itertuples()]
a["lpr"] = np.log(a.post_ratio)
m = fe("priv ~ lpr + ret + mret", a); R["posts_priv_reg_same"] = keep(m, ["lpr", "ret"])
b = a.dropna(subset=["priv_next"])
m = fe("priv_next ~ lpr + ret + priv + mret", b); R["posts_priv_reg_next"] = keep(m, ["lpr", "ret", "priv"])
R["posts_priv_n"] = int(len(a))

# ---------- 4-2 투자자별 수급 vs 커뮤니티 심리 ----------
c = s.dropna(subset=["S", "priv", "inst", "frgn", "ret"]).copy()
c["Sz"] = z(c.S)
# 같은 날 상관 (종목 안에서: 종목 평균을 뺀 값끼리)
dm = c.groupby("code")[["S", "priv", "inst", "frgn", "ret"]].transform(lambda v: v - v.mean())
R["corr_within"] = {k: float(dm.S.corr(dm[k])) for k in ["priv", "inst", "frgn", "ret"]}
R["corr_pooled"] = {k: float(c.S.corr(c[k])) for k in ["priv", "inst", "frgn"]}
# 감성 5분위별 투자자 순매수 비율
c["instfrgn"] = c.inst + c.frgn                                    # C7: 개인의 맞은편 = 기관 + 외국인
c["q"] = pd.qcut(c.S, 5, labels=["가장 공포", "공포", "중간", "탐욕", "가장 탐욕"])
t = c.groupby("q", observed=True)[["priv", "inst", "frgn", "instfrgn", "ret"]].mean().reset_index()
R["sent_quint_flows"] = [{"q": str(r.q), "priv": float(r.priv), "inst": float(r.inst), "frgn": float(r.frgn), "instfrgn": float(r.instfrgn), "ret": float(r.ret)} for r in t.itertuples()]
# 수익률을 통제해도 남는가
for who in ["priv", "inst", "frgn", "instfrgn"]:
    R[f"flow_reg_{who}"] = keep(fe(f"{who} ~ Sz + ret + mret", c), ["Sz", "ret"])
# 다음 날 수급
for who in ["priv", "inst", "frgn", "instfrgn"]:
    c[who + "_next"] = c.groupby("code")[who].shift(-1)
    R[f"flow_next_reg_{who}"] = keep(fe(f"{who}_next ~ Sz + ret + {who} + mret", c.dropna(subset=[who + "_next"])), ["Sz", "ret"])

# 섹터 단위: 3종목 합산
sec = s.dropna(subset=["priv_amt", "inst_amt", "frgn_amt"]).groupby(["sector", "date"]).agg(
    n_posts=("n_posts", "sum"), g=("n_greed", "sum"), f=("n_fear", "sum"), tv=("tv", "sum"),
    priv=("priv_amt", "sum"), inst=("inst_amt", "sum"), frgn=("frgn_amt", "sum"), close_ret=("ret", "mean")).reset_index()
sec["S"] = (sec.g - sec.f) / (sec.n_posts + K)
for w in ["priv", "inst", "frgn"]: sec[w + "_r"] = sec[w] / sec.tv * 100
# 그날 섹터끼리 순위: 커뮤니티가 가장 탐욕인 섹터 3개 vs 가장 공포인 섹터 3개에서 기관·외국인·개인 순매수
sec["rk"] = sec.groupby("date").S.rank(ascending=False)
nsec = sec.groupby("date").sector.transform("size")
top, bot = sec[sec.rk <= 3], sec[sec.rk > nsec - 3]
sec["instfrgn_r"] = sec.inst_r + sec.frgn_r
top, bot = sec[sec.rk <= 3], sec[sec.rk > nsec - 3]
R["sector_greed_vs_fear"] = {grp: {w: float(dd[w + "_r"].mean()) for w in ["priv", "inst", "frgn", "instfrgn"]} | {"ret": float(dd.close_ret.mean())} for grp, dd in [("탐욕 상위 3섹터", top), ("공포 하위 3섹터", bot)]}
# 같은 날 '개인 순매수가 가장 큰 섹터'와 '기관 순매수가 가장 큰 섹터'가 겹치는 비율
pk = sec.loc[sec.groupby("date").priv_r.idxmax(), ["date", "sector"]].rename(columns={"sector": "p"})
ik = sec.loc[sec.groupby("date").inst_r.idxmax(), ["date", "sector"]].rename(columns={"sector": "i"})
ov = pk.merge(ik, on="date"); R["sector_top_overlap"] = {"same": float((ov.p == ov.i).mean()), "chance": 1 / 15, "days": int(len(ov))}
# 개인 탐욕 섹터에서 기관이 팔 때, 기관은 어디를 샀나: 기관 순매수 1위 섹터의 커뮤니티 감성 순위
sec["S_pct"] = sec.groupby("date").S.rank(pct=True) * 100
R["inst_top_sector_sent_pct"] = float(sec.loc[sec.groupby("date").inst_r.idxmax(), "S_pct"].mean())
R["priv_top_sector_sent_pct"] = float(sec.loc[sec.groupby("date").priv_r.idxmax(), "S_pct"].mean())
R["frgn_top_sector_sent_pct"] = float(sec.loc[sec.groupby("date").frgn_r.idxmax(), "S_pct"].mean())

# 급락일 전후: 코스피 −3% 이하인 날. 직전 5거래일 기관 순매수 상위 3섹터 vs 하위 3섹터의 급락일·이후 5일 수익률, 커뮤니티 감성
kd = sorted(kidx["KOSPI"]); kc = {d: kidx["KOSPI"][d][3] for d in kd}
kret = {d: (kc[d] / kc[p] - 1) * 100 for p, d in zip(kd, kd[1:])}
crash_all = [d for d in kd if kret.get(d, 0) <= -3 and d >= "2024-11-05"]
crash = []                                   # C8: 직전 10거래일 안에 다른 급락일이 있으면 뺀다(첫 급락일만)
for d in crash_all:
    i = kd.index(d)
    if not any(x in crash_all for x in kd[max(0, i - 10):i]): crash.append(d)
R["crash_all_n"] = len(crash_all)
secp = sec.pivot(index="date", columns="sector", values="inst_r").sort_index()
secS = sec.pivot(index="date", columns="sector", values="S").sort_index()
secret = s.groupby(["date", "sector"]).ret.mean().unstack().sort_index()
dates = list(secret.index)
ev = []
for d in crash:
    if d not in dates: continue
    i = dates.index(d)
    if i < 5 or i + 5 >= len(dates): continue
    pre = secp.iloc[i - 5:i].mean()                                  # 직전 5거래일 기관 순매수 비율 평균
    top3, bot3 = pre.nlargest(3).index, pre.nsmallest(3).index
    day = secret.iloc[i]; after = secret.iloc[i + 1:i + 6].sum()      # 급락일 수익률, 이후 5일 누적(단순합)
    sday = secS.iloc[i]; sbefore = secS.iloc[i - 5:i].mean()
    ev.append({"date": d, "kospi": kret[d], "top_day": float(day[top3].mean()), "bot_day": float(day[bot3].mean()),
               "top_after": float(after[top3].mean()), "bot_after": float(after[bot3].mean()),
               "top_S_drop": float((sday[top3] - sbefore[top3]).mean()), "bot_S_drop": float((sday[bot3] - sbefore[bot3]).mean()),
               "top": list(top3), "bot": list(bot3)})
R["crash_events"] = ev
e = pd.DataFrame(ev)
R["crash_summary"] = {"n": int(len(e)), "top_day": float(e.top_day.mean()), "bot_day": float(e.bot_day.mean()),
                      "top_after": float(e.top_after.mean()), "bot_after": float(e.bot_after.mean()),
                      "top_better_day_share": float((e.top_day > e.bot_day).mean()), "top_better_after_share": float((e.top_after > e.bot_after).mean()),
                      "top_S_drop": float(e.top_S_drop.mean()), "bot_S_drop": float(e.bot_S_drop.mean())}
# 급락 전 5일 개인·기관·외국인 순매수(45종목 합, 거래대금 대비)와 커뮤니티 감성 흐름 (급락일 = 0)
allf = s.dropna(subset=["priv_amt"]).groupby("date").agg(tv=("tv", "sum"), priv=("priv_amt", "sum"), inst=("inst_amt", "sum"), frgn=("frgn_amt", "sum"), g=("n_greed", "sum"), f=("n_fear", "sum"), n=("n_posts", "sum")).sort_index()
allf["S"] = (allf.g - allf.f) / (allf.n + K)
for w in ["priv", "inst", "frgn"]: allf[w] = allf[w] / allf.tv * 100
fd = list(allf.index); prof = []
for k in range(-5, 6):
    vals = [allf.iloc[fd.index(d) + k] for d in crash if d in fd and 0 <= fd.index(d) + k < len(fd)]
    v = pd.DataFrame(vals)
    prof.append({"k": k, "priv": float(v.priv.mean()), "inst": float(v.inst.mean()), "frgn": float(v.frgn.mean()), "S": float(v.S.mean())})
R["crash_profile"] = prof; R["crash_days"] = crash

# ---------- 4-3 주간 vs 야간 감성: 선행·후행 ----------
d = s.dropna(subset=["ret", "ret_1", "gap", "intra", "S_day_1", "S_night", "mret_1"]).copy()
d = d[(d.night_n_posts >= 5) & (d.day_n_posts_1 if "day_n_posts_1" in d else True)] if False else d[d.night_n_posts >= 5]
d["Sd1z"] = z(d.S_day_1); d["Snz"] = z(d.S_night)
d["up"] = (d.ret > 0).astype(float)
d["date_fe"] = d.date
d["m_open"] = [(kidx[m].get(t) or [None] * 5)[0] for m, t in zip(d.mk, d.date)]
d["mgap"] = (d.m_open / d.groupby("code").m_close.shift(1) - 1) * 100
R["c1_mgap"] = keep(fe("gap ~ Snz + Sd1z + ret_1 + mret_1 + mgap", d.dropna(subset=["mgap"])), ["Snz", "mgap"])
for y in ["gap", "intra", "ret", "up"]:
    R[f"dfe_lead_{y}"] = keep(fe(f"{y} ~ Snz + Sd1z + ret_1 + C(date_fe)", d), ["Snz", "Sd1z"])
d["S_n8"] = (d.pre8_n_greed - d.pre8_n_fear) / (d.pre8_n_posts + K); d["Sn8z"] = z(d.S_n8)
R["dfe_lead_gap_0800"] = keep(fe("gap ~ Sn8z + Sd1z + ret_1 + C(date_fe)", d), ["Sn8z"])
pre_nxt = d[d.date < "2025-03-04"]
R["dfe_lead_gap_prenxt"] = keep(fe("gap ~ Snz + Sd1z + ret_1 + C(date_fe)", pre_nxt), ["Snz"]) | {"n": len(pre_nxt)}
R["daynight_n"] = {"rows": int(len(d)), "stocks": int(d.code.nunique()), "days": int(d.date.nunique()), "period": [d.date.min(), d.date.max()]}
for y in ["gap", "intra", "ret", "up"]:
    m = fe(f"{y} ~ Sd1z + Snz + ret_1 + mret_1", d)
    R[f"daynight_lead_{y}"] = keep(m, ["Sd1z", "Snz"])
# 후행: 당일 수익률 → 그날 주간 감성(동시), 다음 밤 감성
d2 = s.dropna(subset=["ret", "S_day", "S_night_1"]).copy(); d2 = d2[d2.day_n_posts >= 5]
d2["Sdz"] = z(d2.S_day)
R["lag_ret_to_day"] = keep(fe("Sdz ~ ret + mret", d2), ["ret"])
s["S_night_next"] = s.groupby("code").S_night.shift(-1); s["night_n_next"] = s.groupby("code").night_n_posts.shift(-1)
d3 = s.dropna(subset=["ret", "S_night_next"]).copy(); d3 = d3[d3.night_n_next >= 5]; d3["Snnz"] = z(d3.S_night_next)
R["lag_ret_to_night"] = keep(fe("Snnz ~ ret + mret", d3), ["ret"])
# 야간 감성 5분위별 시가 갭·장중 (장초 = 시가 갭)
q = d.groupby(pd.qcut(d.S_night, 5, labels=False, duplicates="drop")).agg(gap=("gap", "mean"), intra=("intra", "mean"), up_gap=("gap", lambda v: (v > 0).mean()), n=("gap", "size")).reset_index(drop=True)
R["night_quint"] = q.to_dict("records")
qd = d.groupby(pd.qcut(d.S_day_1, 5, labels=False, duplicates="drop")).agg(gap=("gap", "mean"), intra=("intra", "mean"), up_gap=("gap", lambda v: (v > 0).mean()), n=("gap", "size")).reset_index(drop=True)
R["day_quint"] = qd.to_dict("records")
# 수익률 구간별 그날 주간 감성 / 그날 밤 감성 (후행 그림용)
d4 = s.dropna(subset=["ret"]).copy(); d4["bin"] = pd.cut(d4.ret, [-100, -3, -1, 1, 3, 100], labels=["−3% 이하", "−3~−1%", "−1~+1%", "+1~+3%", "+3% 이상"])
t = d4.groupby("bin", observed=True).agg(dg=("day_n_greed", "sum"), df=("day_n_fear", "sum"), dn=("day_n_posts", "sum")).reset_index()
nn = s.dropna(subset=["ret"]).copy(); nn["bin"] = d4.bin
nn["ng"] = s.groupby("code").night_n_greed.shift(-1); nn["nf"] = s.groupby("code").night_n_fear.shift(-1); nn["nn"] = s.groupby("code").night_n_posts.shift(-1)
t2 = nn.groupby("bin", observed=True)[["ng", "nf", "nn"]].sum().reset_index()
R["lag_bins_daynight"] = [{"bin": str(a.bin), "day_greed": float(a.dg / a.dn), "day_fear": float(a.df / a.dn), "night_greed": float(b.ng / b.nn), "night_fear": float(b.nf / b.nn)} for a, b in zip(t.itertuples(), t2.itertuples())]

json.dump(R, open("pres_results.json", "w"), ensure_ascii=False, indent=1, default=float)
pr = lambda k: print(k, json.dumps(R[k], ensure_ascii=False, default=float)[:900])
for k in ["posts_total", "posts_day_share", "posts_vs_priv_bins", "posts_vs_priv_by_dir", "posts_priv_reg_same", "posts_priv_reg_next", "corr_within", "sent_quint_flows",
          "flow_reg_priv", "flow_reg_inst", "flow_reg_frgn", "flow_next_reg_priv", "flow_next_reg_inst", "flow_next_reg_frgn", "sector_greed_vs_fear", "sector_top_overlap",
          "inst_top_sector_sent_pct", "priv_top_sector_sent_pct", "frgn_top_sector_sent_pct", "crash_summary", "crash_profile", "daynight_n",
          "daynight_lead_gap", "daynight_lead_intra", "daynight_lead_ret", "daynight_lead_up", "lag_ret_to_day", "lag_ret_to_night", "night_quint", "day_quint", "lag_bins_daynight"]:
    pr(k)

# 급락 프로필 비교 기준: 전체 거래일 평균 (45종목 합, 거래대금 대비 %)
R["flow_baseline"] = {w: float(allf[w].mean()) for w in ["priv", "inst", "frgn", "S"]}
R["crash_pre5_mean"] = {w: float(pd.DataFrame(prof).query("-5<=k<=-1")[w].mean()) for w in ["priv", "inst", "frgn", "S"]}
json.dump(R, open("pres_results.json", "w"), ensure_ascii=False, indent=1, default=float)
print("baseline", R["flow_baseline"], "pre5", R["crash_pre5_mean"])
