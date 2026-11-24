"""섹터 · 종목 순매수 이동(로테이션)과 커뮤니티 글. 45종목·15섹터 안에서.
분기별: 투자자(개인·기관·외국인)별 순매수 비율(섹터 거래대금 대비) 상위 섹터·종목, 같은 분기 섹터 글 점유율·심리.
월별 패널: 이번 달 수급 → 다음 달 글 점유율 변화 / 이번 달 글 점유율 변화 → 다음 달 수급 (누가 먼저인가)
출력: rotation_results.json
사용: uv run --python 3.10 --with pandas --with statsmodels python analysis_rotation.py"""
import json, os
import numpy as np, pandas as pd
import statsmodels.formula.api as smf

os.chdir(os.path.dirname(os.path.abspath(__file__)))
S = json.load(open("sectors.json")); NAME = {c: n for v in S.values() for c, n in v.items()}
ohl = json.load(open("ohlcv.json")); inv = json.load(open("krx_investor.json"))
d = pd.read_csv("index_out/daily_stock.csv", dtype={"code": str})[["date", "code", "sector", "n_posts", "n_greed", "n_fear"]]
d["close"] = [(ohl[c].get(t) or [None] * 5)[3] for c, t in zip(d.code, d.date)]
d["vol"] = [(ohl[c].get(t) or [None] * 5)[4] for c, t in zip(d.code, d.date)]
d["tv"] = d.close * d.vol
for w, k in [("priv", "개인"), ("inst", "기관합계"), ("frgn", "외국인합계")]:
    d[w] = [(inv.get(c, {}).get(t) or {}).get(k) for c, t in zip(d.code, d.date)]
d = d.dropna(subset=["close", "priv"])
d = d[d.date <= "2026-11-11"]
d["month"] = d.date.str[:7]
d["q"] = d.date.str[:4] + "Q" + ((d.date.str[5:7].astype(int) - 1) // 3 + 1).astype(str)
R = {}

def agg(df, key):
    g = df.groupby(key).agg(tv=("tv", "sum"), priv=("priv", "sum"), inst=("inst", "sum"), frgn=("frgn", "sum"),
                            n=("n_posts", "sum"), g=("n_greed", "sum"), f=("n_fear", "sum"), c0=("close", "first"), c1=("close", "last")).reset_index()
    for w in ["priv", "inst", "frgn"]: g[w + "_r"] = g[w] / g.tv * 100; g[w + "_eok"] = g[w] / 1e8
    g["S"] = (g.g - g.f) / (g.n + 10)
    return g

# ---------- 분기 × 섹터 ----------
# 섹터 수익률: 종목별 분기 수익률(첫 종가→마지막 종가) 평균
stq = agg(d, ["q", "sector", "code"]); stq["ret"] = (stq.c1 / stq.c0 - 1) * 100
secq = agg(d, ["q", "sector"]).merge(stq.groupby(["q", "sector"]).ret.mean().reset_index(), on=["q", "sector"])
secq["share"] = secq.n / secq.groupby("q").n.transform("sum") * 100          # 그 분기 45종목 글 중 이 섹터 비중
secq["S_rank"] = secq.groupby("q").S.rank(pct=True) * 100
quarters = sorted(secq.q.unique())
R["quarters"] = quarters
R["sectors"] = list(S.keys())
R["heat"] = {w: {s: [float(secq[(secq.q == q) & (secq.sector == s)][w + "_r"].iloc[0]) if len(secq[(secq.q == q) & (secq.sector == s)]) else None for q in quarters] for s in S} for w in ["priv", "inst", "frgn"]}
R["heat_share"] = {s: [float(secq[(secq.q == q) & (secq.sector == s)].share.iloc[0]) for q in quarters] for s in S}
R["heat_S"] = {s: [float(secq[(secq.q == q) & (secq.sector == s)].S.iloc[0]) for q in quarters] for s in S}
R["heat_ret"] = {s: [float(secq[(secq.q == q) & (secq.sector == s)].ret.iloc[0]) for q in quarters] for s in S}
rows = []
for q in quarters:
    x = secq[secq.q == q]
    r = {"q": q}
    for w in ["priv", "inst", "frgn"]:
        t = x.sort_values(w + "_r", ascending=False)
        r[w + "_top"] = [{"sector": a, "r": float(b), "share": float(c), "S": float(e), "ret": float(f)} for a, b, c, e, f in zip(t.sector[:2], t[w + "_r"][:2], t.share[:2], t.S[:2], t.ret[:2])]
        r[w + "_bot"] = [{"sector": a, "r": float(b)} for a, b in zip(t.sector[-2:], t[w + "_r"][-2:])]
    t = x.sort_values("share", ascending=False); r["talk_top"] = [{"sector": a, "share": float(b)} for a, b in zip(t.sector[:2], t.share[:2])]
    t = x.sort_values("S", ascending=False); r["greed_top"] = [{"sector": a, "S": float(b)} for a, b in zip(t.sector[:2], t.S[:2])]
    rows.append(r)
R["quarter_table"] = rows

# 분기 상위 종목: 투자자별 순매수 대금(억원) 1위 종목과 그 종목의 글 수·심리
stq["share_in_q"] = stq.n / stq.groupby("q").n.transform("sum") * 100
stq["name"] = stq.code.map(NAME)
srow = []
for q in quarters:
    x = stq[stq.q == q]; r = {"q": q}
    for w in ["priv", "inst", "frgn"]:
        t = x.sort_values(w + "_eok", ascending=False).iloc[0]
        r[w] = {"name": t["name"], "sector": t.sector, "eok": float(t[w + "_eok"]), "posts": int(t.n), "share": float(t.share_in_q), "S": float(t.S), "ret": float(t.ret)}
    srow.append(r)
R["stock_table"] = srow

# ---------- 월 × 섹터 패널: 누가 먼저인가 ----------
m = agg(d, ["month", "sector"])
stm = agg(d, ["month", "sector", "code"]); stm["ret"] = (stm.c1 / stm.c0 - 1) * 100
m = m.merge(stm.groupby(["month", "sector"]).ret.mean().reset_index(), on=["month", "sector"])
m["share"] = m.n / m.groupby("month").n.transform("sum") * 100
m = m.sort_values(["sector", "month"])
g = m.groupby("sector")
m["dshare"] = g.share.diff()                                   # 글 점유율 변화(%p)
m["share_next_d"] = g.share.shift(-1) - m.share
for w in ["priv", "inst", "frgn"]:
    m[w + "_next"] = g[w + "_r"].shift(-1)
m["ret_next"] = g.ret.shift(-1)
x = m.dropna(subset=["dshare", "share_next_d", "priv_next", "inst_next", "frgn_next"])
def fit(f):
    r = smf.ols(f + " + C(sector) + C(month)", data=x).fit(cov_type="cluster", cov_kwds={"groups": x.sector.astype("category").cat.codes})
    return r
z = lambda v: (v - v.mean()) / v.std()
for c in ["priv_r", "inst_r", "frgn_r", "ret", "dshare", "S"]: x[c + "_z"] = z(x[c])
# ① 수급(이번 달) → 다음 달 글 점유율 변화
r1 = fit("share_next_d ~ priv_r_z + inst_r_z + frgn_r_z + ret_z")
R["flow_to_talk"] = {k: {"b": float(r1.params[k]), "t": float(r1.tvalues[k]), "p": float(r1.pvalues[k])} for k in ["priv_r_z", "inst_r_z", "frgn_r_z", "ret_z"]}
# ② 글 점유율 변화(이번 달) → 다음 달 투자자별 순매수
R["talk_to_flow"] = {}
for w in ["priv", "inst", "frgn"]:
    r2 = fit(f"{w}_next ~ dshare_z + S_z + ret_z + {w}_r")
    R["talk_to_flow"][w] = {k: {"b": float(r2.params[k]), "t": float(r2.tvalues[k]), "p": float(r2.pvalues[k])} for k in ["dshare_z", "S_z", "ret_z"]}
# ③ 같은 달 상관 (섹터 안 변화끼리: 섹터 평균 뺀 값)
dm = m.dropna(subset=["dshare"]).copy()
for c in ["priv_r", "inst_r", "frgn_r", "share", "S", "ret"]: dm[c + "_dm"] = dm[c] - dm.groupby("sector")[c].transform("mean")
R["same_month_corr"] = {f"{a}~{b}": float(dm[a + "_dm"].corr(dm[b + "_dm"])) for a in ["share", "S"] for b in ["priv_r", "inst_r", "frgn_r", "ret"]}
# ④ 다음 달 섹터 수익률: 이번 달 누가 샀나 (기관이 산 섹터가 다음 달에 오르나)
r4 = fit("ret_next ~ priv_r_z + inst_r_z + frgn_r_z + ret_z + dshare_z + S_z")
R["flow_to_next_ret"] = {k: {"b": float(r4.params[k]), "t": float(r4.tvalues[k]), "p": float(r4.pvalues[k])} for k in ["priv_r_z", "inst_r_z", "frgn_r_z", "ret_z", "dshare_z", "S_z"]}
R["panel_n"] = {"rows": int(len(x)), "months": int(x.month.nunique())}
# 분기 순위 겹침: 개인 상위 3섹터와 기관 상위 3섹터가 겹친 수
ov = []
for q in quarters:
    t = secq[secq.q == q]
    a = set(t.nlargest(3, "priv_r").sector); b = set(t.nlargest(3, "inst_r").sector); c = set(t.nlargest(3, "frgn_r").sector); tk = set(t.nlargest(3, "share").sector)
    ov.append({"q": q, "priv_inst": len(a & b), "priv_talk": len(a & tk), "inst_talk": len(b & tk), "frgn_talk": len(c & tk)})
R["overlap"] = ov
json.dump(R, open("rotation_results.json", "w"), ensure_ascii=False, indent=1, default=float)
for k in ["flow_to_talk", "talk_to_flow", "same_month_corr", "flow_to_next_ret", "panel_n", "overlap"]:
    print(k, json.dumps(R[k], ensure_ascii=False, default=float)[:700])
for r in rows:
    print(r["q"], "개인", [(t["sector"], round(t["r"], 1)) for t in r["priv_top"]], "기관", [(t["sector"], round(t["r"], 1)) for t in r["inst_top"]],
          "외국인", [(t["sector"], round(t["r"], 1)) for t in r["frgn_top"]], "글", [(t["sector"], round(t["share"], 1)) for t in r["talk_top"]], "탐욕", [t["sector"] for t in r["greed_top"]])
for r in srow:
    print(r["q"], {w: (r[w]["name"], round(r[w]["eok"]), r[w]["posts"], round(r[w]["S"], 3), round(r[w]["ret"], 1)) for w in ["priv", "inst", "frgn"]})

# ---------- 대표 12종목 예시: 분기마다 누가 가장 많이 샀나 (순매수 비율 기준) ----------
tot_posts = d.groupby("code").n_posts.sum().sort_values(ascending=False)
top12 = list(tot_posts.index[:12])
LAB = {"priv": "개인", "inst": "기관", "frgn": "외국인"}
ex = []
for c in top12:
    row = {"code": c, "name": NAME[c], "sector": d.loc[d.code == c, "sector"].iloc[0], "posts": int(tot_posts[c]), "q": []}
    for q in quarters:
        t = stq[(stq.code == c) & (stq.q == q)]
        if t.empty: row["q"].append(None); continue
        t = t.iloc[0]; rs = {w: float(t[w + "_r"]) for w in ["priv", "inst", "frgn"]}
        w = max(rs, key=rs.get)
        row["q"].append({"top": LAB[w], "r": rs[w], "priv": rs["priv"], "inst": rs["inst"], "ret": float(t.ret), "S": float(t.S)})
    ex.append(row)
R["top12"] = ex
# 12종목 요약: 분기별 1위 매수 주체가 그 분기 주가와 어떻게 맞물렸나
cells = [x for r in ex for x in r["q"] if x]
R["top12_summary"] = {k: {"n": sum(1 for x in cells if x["top"] == k), "ret": float(np.median([x["ret"] for x in cells if x["top"] == k])),
                          "S": float(np.mean([x["S"] for x in cells if x["top"] == k]))} for k in ["개인", "기관", "외국인"]}
R["top12_opp"] = float(np.mean([(x["priv"] > 0) != (x["inst"] > 0) for x in cells]))
json.dump(R, open("rotation_results.json", "w"), ensure_ascii=False, indent=1, default=float)
for r in ex: print(r["name"], r["posts"], [x["top"][0] if x else "-" for x in r["q"]])
print(R["top12_summary"], R["top12_opp"])
