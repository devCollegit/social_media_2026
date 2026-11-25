"""알림 규칙 검증 (보완안 7장 '로직 요소'). 대시보드 알림 문구가 과거 기록으로 뒷받침되는지 전체 기간에서 확인하고,
알림마다 "이런 날 과거에는" 기록(사례 수, 분포)을 만든다. 예측이 아니라 기록을 보여 주기 위한 표다.

규칙 (글이 적은 종목·일은 판정하지 않음: 일 글 수 --min-posts 미만, 밤 글 수 --min-night 미만)
R1 개인 매수 집중 구간 : 하락일(종목 수익률 < 0)에 글 수가 평소(직전 20거래일 평균)의 2배 이상
                        → 그날·다음 날 개인 순매수 비율. 비교군은 글이 평소 수준인 하락일
R2 말과 행동이 다름     : 0~100 지수 75 이상(탐욕)인데 그날 개인이 순매도
                        → 다음 날 개인 순매수, 다음 날·5일 초과수익률. 비교군은 지수 75 이상이고 개인 순매수인 날
R3 약세 출발 가능성     : 밤사이 심리(60일 백분위)가 하위 15%
                        → 그날 시가 갭과 장중(시가→종가) 수익률. 비교군은 밤 심리 15~85%인 날.
                          '시가까지만 유효' 문구가 맞는지(장중 효과가 없는지) 함께 본다
효과는 종목·날짜 이중 고정효과 회귀(이중 군집 표준오차)로 잰다. 날짜 고정효과가 시장 전체 움직임을 지운다.

입력 (--base): ohlcv.json, krx_index.json, krx_investor.json / (--out): index_v2/daily_stock.csv
출력 (--out): reports/alerts_report.json, reports/alerts_report.md, alerts_v2/history.csv(알림이 켜진 종목·일과 결과), alerts_v2/latest.csv(마지막 거래일)
사용: python alerts_v2.py --base <toss_fear_greed 폴더> --out v2_out
"""
import argparse
import json
import os
import warnings

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

from common import write_json

warnings.filterwarnings("ignore")
P = argparse.ArgumentParser()
P.add_argument("--base", required=True)
P.add_argument("--out", default="v2_out")
P.add_argument("--min-posts", type=int, default=20)
P.add_argument("--min-night", type=int, default=5)
P.add_argument("--attn", type=float, default=2.0, help="R1 글 수 배수 기준")
P.add_argument("--greed", type=float, default=75, help="R2 지수 기준")
P.add_argument("--night-low", type=float, default=15, help="R3 밤 심리 백분위 기준")
A = P.parse_args()
KOSDAQ = {"086520", "196170", "000250", "028300", "058470", "005290", "036930", "403870", "032820", "277810", "108490", "222800"}

s = pd.read_csv(os.path.join(A.out, "index_v2", "daily_stock.csv"), dtype={"code": str})
ohl = json.load(open(os.path.join(A.base, "ohlcv.json")))
kidx = json.load(open(os.path.join(A.base, "krx_index.json")))
inv = json.load(open(os.path.join(A.base, "krx_investor.json")))
px = lambda c, t, k: (ohl.get(c, {}).get(t) or [np.nan] * 5)[k]
for k, n in enumerate(["open", "high", "low", "close", "vol"]):
    s[n] = [px(c, t, k) for c, t in zip(s.code, s.date)]
s = s[s.close.notna() & (s.open > 0)].sort_values(["code", "date"]).reset_index(drop=True)
mk = np.where(s.code.isin(KOSDAQ), "KOSDAQ", "KOSPI")
s["m_close"] = [(kidx[m].get(t) or [np.nan] * 5)[3] for m, t in zip(mk, s.date)]
g = s.groupby("code")
s["ret"] = (s.close / g.close.shift(1) - 1) * 100
s["gap"] = (s.open / g.close.shift(1) - 1) * 100
s["intra"] = (s.close / s.open - 1) * 100
s["mret"] = (s.m_close / g.m_close.shift(1) - 1) * 100
s["exret"] = s.ret - s.mret
tv = s.close * s.vol
s["priv"] = [(inv.get(c, {}).get(t) or {}).get("개인") for c, t in zip(s.code, s.date)]
s["priv"] = s.priv.astype(float) / tv * 100
g = s.groupby("code")
s["priv_n1"] = g.priv.shift(-1)
s["exret_n1"] = g.exret.shift(-1)
s["exret_5"] = sum(g.exret.shift(-h) for h in range(1, 6))
enough = s.n_posts >= A.min_posts
night_ok = s.night_n_posts >= A.min_night

# ---------------- 규칙 정의: (알림 켜짐, 비교군) ----------------
RULES = {
    "R1": {"name": "개인 매수 집중 구간", "text": f"하락일에 글이 평소의 {A.attn:g}배 이상",
           "on": enough & (s.ret < 0) & (s.attn_ratio >= A.attn),
           "ref": enough & (s.ret < 0) & (s.attn_ratio < 1.5),
           "y": {"priv": "그날 개인 순매수 비율(%)", "priv_n1": "다음 날 개인 순매수 비율(%)"}},
    "R2": {"name": "말과 행동이 다름", "text": f"지수 {A.greed:g} 이상(탐욕)인데 그날 개인 순매도",
           "on": enough & (s.fg_index >= A.greed) & (s.priv < 0),
           "ref": enough & (s.fg_index >= A.greed) & (s.priv >= 0),
           "y": {"priv_n1": "다음 날 개인 순매수 비율(%)", "exret_n1": "다음 날 초과수익률(%)", "exret_5": "5일 누적 초과수익률(%)"}},
    "R3": {"name": "약세 출발 가능성", "text": f"밤사이 심리가 하위 {A.night_low:g}%",
           "on": night_ok & (s.p60_S_night_shr <= A.night_low),
           "ref": night_ok & s.p60_S_night_shr.between(A.night_low, 100 - A.night_low, inclusive="neither"),
           "y": {"gap": "그날 시가 갭(%)", "intra": "그날 장중 수익률(시가→종가, %)"}},
}


def fe_effect(y, on, ref):
    """알림 더미의 효과 (비교군 대비). 종목·날짜 이중 고정효과, 이중 군집 표준오차."""
    d = s.loc[on | ref, ["code", "date", y]].assign(alert=on[on | ref].astype(float)).dropna()
    if d.alert.sum() < 10 or (1 - d.alert).sum() < 10:
        return None
    d = d.set_index(["code", pd.to_datetime(d.date)])
    try:
        r = PanelOLS(d[y], d[["alert"]], entity_effects=True, time_effects=True, drop_absorbed=True).fit(
            cov_type="clustered", cluster_entity=True, cluster_time=True)
        return {"coef": float(r.params["alert"]), "t": float(r.tstats["alert"]), "p": float(r.pvalues["alert"]), "n": int(r.nobs)}
    except Exception:
        return None


def dist(v):
    v = v.dropna()
    if len(v) == 0:
        return None
    return {"n": int(len(v)), "mean": float(v.mean()), "p10": float(v.quantile(.1)), "p50": float(v.median()),
            "p90": float(v.quantile(.9)), "share_pos": float((v > 0).mean())}


R, hist = {"period": [s.date.min(), s.date.max()], "stocks": int(s.code.nunique()), "rules": {}}, []
for k, rule in RULES.items():
    on, ref = rule["on"].fillna(False), rule["ref"].fillna(False)
    rr = {"name": rule["name"], "text": rule["text"], "n_on": int(on.sum()), "n_ref": int(ref.sum()),
          "stocks_on": int(s.loc[on, "code"].nunique()), "share_of_days": float(on.sum() / max(enough.sum(), 1)), "y": {}}
    for y, label in rule["y"].items():
        rr["y"][y] = {"label": label, "on": dist(s.loc[on, y]), "ref": dist(s.loc[ref, y]), "fe": fe_effect(y, on, ref)}
    R["rules"][k] = rr
    h = s.loc[on, ["date", "code", "stock_name", "sector"] + list(rule["y"])].assign(rule=k)
    hist.append(h)

os.makedirs(os.path.join(A.out, "alerts_v2"), exist_ok=True)
H = pd.concat(hist, ignore_index=True).sort_values(["date", "rule", "code"])
H.to_csv(os.path.join(A.out, "alerts_v2", "history.csv"), index=False, float_format="%.4f")
last = s.date.max()
H[H.date == last].to_csv(os.path.join(A.out, "alerts_v2", "latest.csv"), index=False, float_format="%.4f")
R["latest"] = {"date": last, "alerts": H[H.date == last][["rule", "code", "stock_name"]].to_dict("records")}
write_json(os.path.join(A.out, "reports", "alerts_report.json"), R)

# ---------------- 보고서 ----------------
star = lambda p: "***" if p < .01 else "**" if p < .05 else "*" if p < .1 else ""
fmt = lambda x: "—" if x is None else f"{x['mean']:+.2f} (중앙 {x['p50']:+.2f}, 10~90% {x['p10']:+.2f}~{x['p90']:+.2f}, n={x['n']:,})"
L = [f"# 알림 규칙 검증 ({R['period'][0]} ~ {R['period'][1]}, {R['stocks']}종목)", "",
     f"글이 적은 종목·일은 판정하지 않음: 일 글 수 {A.min_posts}건 미만, 밤 글 수 {A.min_night}건 미만.",
     "효과 = 비교군 대비 차이, 종목·날짜 이중 고정효과, 이중 군집 표준오차. *** p<0.01, ** p<0.05, * p<0.1", ""]
for k, rr in R["rules"].items():
    L += [f"## {k}. {rr['name']}: {rr['text']}", "",
          f"알림 {rr['n_on']:,}건 ({rr['stocks_on']}종목, 판정 대상 종목·일의 {rr['share_of_days']:.1%}), 비교군 {rr['n_ref']:,}건", "",
          "| 결과 | 알림 켜진 날 | 비교군 | 효과 (FE) |", "|---|---|---|---|"]
    for y, v in rr["y"].items():
        fe = v["fe"]
        L.append(f"| {v['label']} | {fmt(v['on'])} | {fmt(v['ref'])} | "
                 + ("—" if fe is None else f"{fe['coef']:+.3f}{star(fe['p'])} (t={fe['t']:.1f})") + " |")
    L.append("")
L += [f"마지막 거래일({last}) 켜진 알림: {len(R['latest']['alerts'])}건 → alerts_v2/latest.csv",
      "알림별 과거 사례 전체: alerts_v2/history.csv (대시보드 '이런 날 과거에는' 카드에 쓸 수 있음)"]
open(os.path.join(A.out, "reports", "alerts_report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L))
