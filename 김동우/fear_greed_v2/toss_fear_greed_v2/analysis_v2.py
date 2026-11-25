"""v2 분석 (보완안 C1~C4, C6~C8과 행동 축). 회귀는 linearmodels PanelOLS: 종목 고정효과(+날짜 고정효과), 종목·날짜 이중 군집 표준오차.

C1 밤 글 → 시가 갭: 류창민 사양 그대로 → 지수 갭 통제 → 날짜 고정효과 → 전일 시간외 수익률 → 미국 증시 → 대체거래소 출범 전 구간
C2 지수 구간·국면 → 이후 1·5·20일 초과수익률, 변동폭, 다음 날 개인 순매수
C3 심리·관심 → 다음 날 거래량 비율, 일중 변동폭, 공매도 비중
C4 쏠림(의견 일치) → 다음 날 거래량
C6 반응 경로: 심리 1표준편차 → 0~10일 뒤 누적 초과수익률·개인 순매수 (탐욕·공포 비율을 따로도)
C7 다음 날 수급: 개인 vs 기관+외국인 한 축
C8 급락일: 10거래일 안 첫 급락만, 무작위 날짜와 비교(위약 검정)
B5 말과 행동: 매수 인증 비율과 심리, 다음 날 개인 순매수

입력 (--base): ohlcv.json, krx_index.json, krx_investor.json, krx_short.json(있으면), us_overnight.csv(있으면, date,us_ret),
             nxt_after.json(있으면, {종목:{날짜: 그날 15:30~20:00 수익률 %}}) / (--out) index_v2/daily_stock.csv
출력: reports/analysis_report.json, reports/analysis_report.md
사용: python analysis_v2.py --base <toss_fear_greed 폴더> --out v2_out [--crash -3]
"""
import argparse
import json
import os
import warnings

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

from common import NXT_START, write_json

warnings.filterwarnings("ignore")
P = argparse.ArgumentParser()
P.add_argument("--base", required=True)
P.add_argument("--out", default="v2_out")
P.add_argument("--crash", type=float, default=-3.0, help="코스피 급락일 기준 (%%)")
P.add_argument("--min-night", type=int, default=5)
P.add_argument("--placebo", type=int, default=2000)
A = P.parse_args()
B = A.base
KOSDAQ = {"086520", "196170", "000250", "028300", "058470", "005290", "036930", "403870", "032820", "277810", "108490", "222800"}
rng = np.random.default_rng(0)

s = pd.read_csv(os.path.join(A.out, "index_v2", "daily_stock.csv"), dtype={"code": str})
ohl = json.load(open(os.path.join(B, "ohlcv.json")))
kidx = json.load(open(os.path.join(B, "krx_index.json")))
inv = json.load(open(os.path.join(B, "krx_investor.json")))
sht = json.load(open(os.path.join(B, "krx_short.json"))) if os.path.exists(os.path.join(B, "krx_short.json")) else {}
usf = os.path.join(B, "us_overnight.csv")
us = pd.read_csv(usf, dtype={"date": str}).set_index("date").us_ret.to_dict() if os.path.exists(usf) else None
ahf = os.path.join(B, "nxt_after.json")
ah = json.load(open(ahf)) if os.path.exists(ahf) else None

px = lambda c, t, k: (ohl.get(c, {}).get(t) or [np.nan] * 5)[k]
for k, n in enumerate(["open", "high", "low", "close", "vol"]):
    s[n] = [px(c, t, k) for c, t in zip(s.code, s.date)]
s = s[s.close.notna() & (s.open > 0)].sort_values(["code", "date"]).reset_index(drop=True)
mk = np.where(s.code.isin(KOSDAQ), "KOSDAQ", "KOSPI")
s["m_open"] = [(kidx[m].get(t) or [np.nan] * 5)[0] for m, t in zip(mk, s.date)]
s["m_close"] = [(kidx[m].get(t) or [np.nan] * 5)[3] for m, t in zip(mk, s.date)]
g = s.groupby("code")
s["ret"] = (s.close / g.close.shift(1) - 1) * 100
s["gap"] = (s.open / g.close.shift(1) - 1) * 100
s["intra"] = (s.close / s.open - 1) * 100
s["mret"] = (s.m_close / g.m_close.shift(1) - 1) * 100
s["mgap"] = (s.m_open / g.m_close.shift(1) - 1) * 100
s["exret"] = s.ret - s.mret
s["range"] = (s.high - s.low) / s.open * 100
s["lvr"] = np.log(s.vol / g.vol.transform(lambda v: v.shift(1).rolling(20, min_periods=5).mean()))
s["tv"] = s.close * s.vol
for w, k in [("priv", "개인"), ("inst", "기관합계"), ("frgn", "외국인합계")]:
    s[w] = [(inv.get(c, {}).get(t) or {}).get(k) for c, t in zip(s.code, s.date)]
    s[w] = s[w].astype(float) / s.tv * 100
s["pro"] = s.inst + s.frgn
s["short"] = [((sht.get(c, {}).get(t) or {}).get("공매도", np.nan)) for c, t in zip(s.code, s.date)]
s["short"] = s.short.astype(float) / s.vol * 100
s["us_ret"] = s.date.map(us) if us else np.nan
s["ah_prev"] = [((ah.get(c) or {}).get(p, 0.0) if isinstance(p, str) else np.nan) for c, p in zip(s.code, g.date.shift(1))] if ah else np.nan
s["lattn"] = np.log(s.attn_ratio.clip(lower=0.05))
s["absret"] = s.ret.abs()
Ne = (s.n_posts - s.p_irrelevant).clip(lower=1)
s["greed_sh"], s["fear_sh"] = s.p_greed / Ne, s.p_fear / Ne
z = lambda v: (v - v.mean()) / v.std()
s["S_z"], s["night_z"], s["day_z"] = z(s.S_shr), z(s.S_night_shr), z(s.S_day_shr)
s["conc_z"], s["greed_z"], s["fear_z"], s["resid_z"] = z(s.concentration), z(s.greed_sh), z(s.fear_sh), z(s.resid)
g = s.groupby("code")
for c in ["ret", "mret", "S_z", "day_z", "priv", "pro", "lvr", "range", "absret", "lattn", "night_z"]:
    s[c + "_1"] = g[c].shift(1)
for c in ["lvr", "range", "short", "priv", "pro", "exret", "ret"]:
    s[c + "_n1"] = g[c].shift(-1)
s["dt"] = pd.to_datetime(s.date)
PNL = s.set_index(["code", "dt"])


def fe(y, xs, data=None, time=False, cond=None):
    data = PNL if data is None else data     # 전역 PNL을 매번 새로 읽음 (열을 추가한 뒤에도 반영)
    dd = data if cond is None else data[cond.reindex(data.index).fillna(False).astype(bool)]
    dd = dd[[y] + xs].replace([np.inf, -np.inf], np.nan).dropna()
    if len(dd) < 50:
        return None
    m = PanelOLS(dd[y], dd[xs], entity_effects=True, time_effects=time, drop_absorbed=True, check_rank=False)
    r = m.fit(cov_type="clustered", cluster_entity=True, cluster_time=True)
    return {k: {"b": float(r.params[k]), "t": float(r.tstats[k]), "p": float(r.pvalues[k])} for k in r.params.index} | {"_n": int(r.nobs)}


R = {"n_rows": int(len(s)), "period": [s.date.min(), s.date.max()], "stocks": int(s.code.nunique())}

# ---------------- C1 ----------------
night_ok = (PNL.night_n_posts >= A.min_night)
base_x = ["night_z", "day_z_1", "ret_1", "mret_1"]
specs = [("① 류창민 사양 (종목 FE)", base_x, False, None),
         ("② + 지수 시가 갭", base_x + ["mgap"], False, None),
         ("③ 종목+날짜 FE", base_x, True, None)]
if ah is not None:
    specs.append(("④ ③ + 전일 시간외 수익률", base_x + ["ah_prev"], True, None))
if us is not None:
    specs.append(("⑤ ① + 미국 증시", base_x + ["us_ret"], False, None))
specs.append(("⑥ ③, 대체거래소 출범 전만", base_x, True, PNL.date < NXT_START))
specs.append(("⑦ ③, 출범 후만", base_x, True, PNL.date >= NXT_START))
R["C1_gap"] = {}
for name, xs, tm, cond in specs:
    c = night_ok if cond is None else (night_ok & cond)
    R["C1_gap"][name] = fe("gap", xs, time=tm, cond=c)
R["C1_intra"] = fe("intra", base_x, time=True, cond=night_ok)
R["C1_gap_after_all_controls"] = fe("gap", base_x + (["ah_prev"] if ah else []), time=True, cond=night_ok)

# ---------------- C2 ----------------
s["fwd1"] = s.exret_n1
for h in (5, 20):
    s[f"fwd{h}"] = s.groupby("code").exret.transform(lambda v: v[::-1].rolling(h, min_periods=h).sum()[::-1].shift(-1))
s["vol5"] = s.groupby("code").absret.transform(lambda v: v[::-1].rolling(5, min_periods=5).mean()[::-1].shift(-1))
s["bucket"] = pd.cut(s.fg_index, [-1, 25, 45, 55, 75, 101], labels=["극단적 공포", "공포", "중립", "탐욕", "극단적 탐욕"])
tab = s.groupby("bucket", observed=True).agg(n=("fwd1", "size"), fwd1=("fwd1", "mean"), fwd5=("fwd5", "mean"), fwd20=("fwd20", "mean"),
                                            vol5=("vol5", "mean"), priv_next=("priv_n1", "mean"))
R["C2_buckets"] = {str(k): {a: float(b) for a, b in r.items()} for k, r in tab.iterrows()}
reg = s.groupby("regime_v2").agg(n=("fwd1", "size"), fwd5=("fwd5", "mean"), vol5=("vol5", "mean"), priv_next=("priv_n1", "mean"))
R["C2_regimes"] = {str(k): {a: float(b) for a, b in r.items()} for k, r in reg.iterrows()}
s["ext_fear"] = (s.fg_index <= 25).astype(float)
s["ext_greed"] = (s.fg_index >= 75).astype(float)
PNL = s.set_index(["code", "dt"])
R["C2_reg"] = {h: fe(h, ["ext_fear", "ext_greed"], time=True) for h in ("fwd1", "fwd5", "fwd20", "vol5")}

# ---------------- C3·C4 ----------------
ctrl = ["ret", "absret", "lvr", "range", "mret"]
R["C3"] = {y: fe(y, ["S_z", "lattn"] + ctrl, time=True) for y in ("lvr_n1", "range_n1", "short_n1")}
R["C4"] = fe("lvr_n1", ["conc_z", "lattn", "S_z"] + ctrl, time=True)

# ---------------- C6 반응 경로 ----------------
R["C6"] = {"exret_cum": {}, "priv": {}}
for h in range(0, 11):
    if h == 0:
        s["_y"] = s.exret
        s["_q"] = s.priv
    else:
        s["_y"] = s.groupby("code").exret.transform(lambda v, h=h: v[::-1].rolling(h, min_periods=h).sum()[::-1].shift(-1))
        s["_q"] = s.groupby("code").priv.shift(-h)
    PNL = s.set_index(["code", "dt"])
    a = fe("_y", ["S_z", "ret_1", "lattn"], time=True)
    b = fe("_q", ["S_z", "ret", "lattn", "priv_1"], time=True)
    R["C6"]["exret_cum"][h] = a["S_z"] if a else None
    R["C6"]["priv"][h] = b["S_z"] if b else None
R["C6_split_next"] = {"priv_n1": fe("priv_n1", ["greed_z", "fear_z", "ret", "lattn", "priv"], time=True),
                      "exret_n1": fe("exret_n1", ["greed_z", "fear_z", "ret", "lattn"], time=True)}

# ---------------- C7 ----------------
R["C7"] = {y: fe(y, ["S_z", "lattn", "ret", "priv", "pro"], time=True) for y in ("priv_n1", "pro_n1")}
R["C7_same_day_corr"] = float(s[["priv", "pro"]].corr().iloc[0, 1])

# ---------------- C8 급락일 ----------------
kd = sorted(kidx["KOSPI"])
kc = {t: kidx["KOSPI"][t][3] for t in kd}
kret = {t: (kc[t] / kc[p] - 1) * 100 for p, t in zip(kd, kd[1:])}
days = sorted(s.date.unique())
crash_all = [t for t in days if kret.get(t, 0) <= A.crash]
crash, last = [], None
for t in crash_all:                                         # 10거래일 안 첫 급락만
    if last is None or days.index(t) - days.index(last) >= 10:
        crash.append(t)
    last = t
agg = s.groupby("date").apply(lambda x: pd.Series({"priv": np.nansum(x.priv * x.tv) / x.tv.sum(), "inst": np.nansum(x.inst * x.tv) / x.tv.sum(),
                                                   "frgn": np.nansum(x.frgn * x.tv) / x.tv.sum(),
                                                   "S": np.average(x.S_shr, weights=x.n_posts.clip(lower=1))})).reindex(days)


def pre5(ts):
    out = []
    for t in ts:
        i = days.index(t)
        if i >= 5:
            out.append(agg.iloc[i - 5:i].mean())
    return pd.DataFrame(out).mean()


R["C8"] = {"n_crash_raw": len(crash_all), "n_crash_clean": len(crash), "threshold": A.crash}
if crash:
    actual = pre5(crash)
    excl = set()
    for t in crash_all:
        i = days.index(t)
        excl |= set(days[max(0, i - 10): i + 11])
    pool = [t for t in days[5:] if t not in excl]
    sims = np.array([pre5(list(rng.choice(pool, len(crash), replace=False)))[["priv", "frgn"]].to_numpy() for _ in range(A.placebo)])
    R["C8"]["pre5_actual"] = {k: float(v) for k, v in actual.items()}
    R["C8"]["pre5_placebo_mean"] = {"priv": float(sims[:, 0].mean()), "frgn": float(sims[:, 1].mean())}
    R["C8"]["placebo_p_priv_high"] = float((sims[:, 0] >= actual["priv"]).mean())
    R["C8"]["placebo_p_frgn_low"] = float((sims[:, 1] <= actual["frgn"]).mean())
    prof = []
    for k in range(-5, 6):
        v = [agg.iloc[days.index(t) + k] for t in crash if 0 <= days.index(t) + k < len(days)]
        prof.append({"k": k, **{a: float(b) for a, b in pd.DataFrame(v).mean().items()}})
    R["C8"]["profile"] = prof

# ---------------- B5 말과 행동 ----------------
dm = s[["buy_ratio", "S_shr", "code"]].dropna()
dm2 = dm[["buy_ratio", "S_shr"]] - dm.groupby("code")[["buy_ratio", "S_shr"]].transform("mean")
R["B5_corr_within"] = float(dm2.corr().iloc[0, 1]) if len(dm2) > 30 else None
s["buy_z"] = z(s.buy_ratio)
PNL = s.set_index(["code", "dt"])
R["B5_priv_next"] = fe("priv_n1", ["buy_z", "S_z", "ret", "lattn", "priv"], time=True)

write_json(os.path.join(A.out, "reports", "analysis_report.json"), R)


# ---------------- 보고서 ----------------
def cell(r, k):
    if not r or k not in r:
        return "—"
    x = r[k]
    star = "***" if x["p"] < 0.01 else "**" if x["p"] < 0.05 else "*" if x["p"] < 0.1 else ""
    return f"{x['b']:+.3f}{star} (t={x['t']:.1f})"


L = [f"# 분석 결과 ({R['period'][0]} ~ {R['period'][1]}, {R['stocks']}종목)", "",
     "회귀는 모두 종목 고정효과, 종목·날짜 이중 군집 표준오차. *** p<0.01, ** p<0.05, * p<0.1", "",
     "## C1. 밤 글 심리(1σ) → 당일 시가 갭(%p)", "", "| 사양 | 밤 심리 계수 | 표본 |", "|---|---|---|"]
for k, r in R["C1_gap"].items():
    L.append(f"| {k} | {cell(r, 'night_z')} | {r['_n'] if r else '—'} |")
L += ["", f"장중(시가→종가), 종목+날짜 FE: {cell(R['C1_intra'], 'night_z')}", "",
      "## C2. 0~100 지수 구간별 이후 성과", "", "| 구간 | 종목·일 | 다음 날 초과수익률 | 5일 | 20일 | 5일 평균 |등락| | 다음 날 개인 순매수 |", "|---|---|---|---|---|---|---|"]
for k, r in R["C2_buckets"].items():
    L.append(f"| {k} | {int(r['n']):,} | {r['fwd1']:+.2f}% | {r['fwd5']:+.2f}% | {r['fwd20']:+.2f}% | {r['vol5']:.2f}% | {r['priv_next']:+.2f}% |")
L += ["", "극단 구간 더미 회귀 (종목+날짜 FE, 기준 = 그 외)", "", "| 결과 | 극단적 공포 | 극단적 탐욕 |", "|---|---|---|"]
for k, r in R["C2_reg"].items():
    L.append(f"| {k} | {cell(r, 'ext_fear')} | {cell(r, 'ext_greed')} |")
L += ["", "## C3·C4. 다음 날 거래량·변동폭·공매도 (종목+날짜 FE)", "", "| 결과 | 심리 1σ | log 관심도 | 의견 일치(쏠림) 1σ |", "|---|---|---|---|"]
for k, r in R["C3"].items():
    L.append(f"| {k} | {cell(r, 'S_z')} | {cell(r, 'lattn')} | — |")
L.append(f"| lvr_n1 (C4) | {cell(R['C4'], 'S_z')} | {cell(R['C4'], 'lattn')} | {cell(R['C4'], 'conc_z')} |")
L += ["", "## C6. 심리 1σ의 반응 경로 (종목+날짜 FE)", "", "| h일 | 누적 초과수익률(t+1..t+h) | h일 뒤 개인 순매수 |", "|---|---|---|"]
for h in range(0, 11):
    a, b = R["C6"]["exret_cum"][h], R["C6"]["priv"][h]
    fa = lambda x: "—" if not x else f"{x['b']:+.3f} (t={x['t']:.1f})"
    L.append(f"| {h} | {fa(a)} | {fa(b)} |")
L += ["", "탐욕·공포 비율을 따로 넣었을 때 (다음 날)", "", "| 결과 | 탐욕 비율 1σ | 공포 비율 1σ |", "|---|---|---|"]
for k, r in R["C6_split_next"].items():
    L.append(f"| {k} | {cell(r, 'greed_z')} | {cell(r, 'fear_z')} |")
L += ["", "## C7. 다음 날 수급 (개인 vs 기관+외국인)", "", "| 결과 | 심리 1σ | log 관심도 |", "|---|---|---|"]
for k, r in R["C7"].items():
    L.append(f"| {k} | {cell(r, 'S_z')} | {cell(r, 'lattn')} |")
L += ["", f"같은 날 개인과 기관+외국인 순매수 상관: {R['C7_same_day_corr']:.2f}", "", "## C8. 급락일"]
c8 = R["C8"]
L.append(f"기준 {c8['threshold']}% 이하: {c8['n_crash_raw']}일, 10거래일 안 첫 급락만 {c8['n_crash_clean']}일")
if "pre5_actual" in c8:
    L.append(f"- 급락 전 5일 개인 순매수 {c8['pre5_actual']['priv']:+.2f}% (무작위 날짜 평균 {c8['pre5_placebo_mean']['priv']:+.2f}%, 위약 p={c8['placebo_p_priv_high']:.3f})")
    L.append(f"- 급락 전 5일 외국인 순매수 {c8['pre5_actual']['frgn']:+.2f}% (무작위 날짜 평균 {c8['pre5_placebo_mean']['frgn']:+.2f}%, 위약 p={c8['placebo_p_frgn_low']:.3f})")
L += ["", "## B5. 말과 행동", "", f"- 매수 인증 비율과 심리의 종목 내 상관: {R['B5_corr_within']:.2f}" if R["B5_corr_within"] is not None else "- 인증 자료 부족",
      f"- 다음 날 개인 순매수 ← 매수 인증 비율 1σ: {cell(R['B5_priv_next'], 'buy_z')}, 심리 1σ: {cell(R['B5_priv_next'], 'S_z')}"]
open(os.path.join(A.out, "reports", "analysis_report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L))
