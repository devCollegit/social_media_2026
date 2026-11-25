"""대시보드(ui/dashboard.html)용 데이터 파일 만들기. index_v2·시세·수급·예상 범위를 ui/data.js 하나로 묶는다.
파일을 브라우저에서 바로 열 수 있게 JSON이 아니라 자바스크립트(window.FG_DATA = ...)로 쓴다. 원문은 들어가지 않는다.

입력 (--base): ohlcv.json, krx_investor.json, sectors.json, rotation_keywords.json(있으면 섹터 대표 단어)
      (--out): index_v2/daily_stock.csv, predictions/latest_priv_interval.csv(있으면)
출력 (--dest): data.js
사용: python build_ui_data.py --base <toss_fear_greed 폴더> --out v2_out --dest ../ui/data.js [--days 140] [--label 실제]
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

from common import load_sectors

P = argparse.ArgumentParser()
P.add_argument("--base", required=True)
P.add_argument("--out", default="v2_out")
P.add_argument("--dest", default="../ui/data.js")
P.add_argument("--days", type=int, default=140, help="화면에 실을 최근 거래일 수 (과거 기록 카드도 이 기간으로 계산)")
P.add_argument("--label", default="합성", help="화면 상단에 표시할 데이터 이름 (예: 합성, 실제)")
A = P.parse_args()

SECT = load_sectors(A.base)
s = pd.read_csv(os.path.join(A.out, "index_v2", "daily_stock.csv"), dtype={"code": str})
ohl = json.load(open(os.path.join(A.base, "ohlcv.json")))
inv = json.load(open(os.path.join(A.base, "krx_investor.json")))
dates = sorted(s.date.unique())[-A.days:]
s = s[s.date.isin(dates)]
pi = {}
pf = os.path.join(A.out, "predictions", "latest_priv_interval.csv")
if os.path.exists(pf):
    for r in pd.read_csv(pf, dtype={"code": str}).itertuples():
        pi[r.code] = [round(r.q10, 2), round(r.q50, 2), round(r.q90, 2)]
words = {}
rk = os.path.join(A.base, "rotation_keywords.json")
if os.path.exists(rk):                       # 가장 최근 분기의 섹터별 대표 단어
    j = json.load(open(rk, encoding="utf-8"))
    last_q = max(k.split("|")[0] for k in j)
    words = {k.split("|")[1]: [w for w, _ in v["words"][:4]] for k, v in j.items() if k.startswith(last_q)}


def arr(x, nd=2):
    return [None if (v is None or (isinstance(v, float) and not np.isfinite(v))) else round(float(v), nd) for v in x]


stocks = {}
for code, g in s.groupby("code"):
    g = g.set_index("date").reindex(dates)
    o = [ohl.get(code, {}).get(t) or [None] * 5 for t in dates]
    close = [r[3] for r in o]
    opn = [r[0] for r in o]
    vol = [r[4] for r in o]
    prev = [None] + close[:-1]
    ret = [(c / p - 1) * 100 if c and p else None for c, p in zip(close, prev)]
    gap = [(op / p - 1) * 100 if op and p else None for op, p in zip(opn, prev)]
    tv = [c * v if c and v else None for c, v in zip(close, vol)]
    priv = [((inv.get(code, {}).get(t) or {}).get("개인") / x * 100) if x and (inv.get(code, {}).get(t) or {}).get("개인") is not None else None
            for t, x in zip(dates, tv)]
    stocks[code] = {"close": arr(close, 0), "ret": arr(ret), "gap": arr(gap), "posts": arr(g.n_posts.fillna(0), 0),
                    "ratio": arr(g.attn_ratio), "idx": arr(g.fg_index, 1), "nidx": arr(g.p60_S_night_shr, 1),
                    "nposts": arr(g.night_n_posts.fillna(0), 0), "priv": arr(priv), "buy": arr(g.buy_ratio, 3),
                    "resid": arr(g.p60_resid, 1), "pi": pi.get(code)}
D = {"label": A.label, "asof": dates[-1], "dates": dates, "sectors": {k: list(v) for k, v in SECT.items() if any(c in stocks for c in v)},
     "names": {c: n for v in SECT.values() for c, n in v.items() if c in stocks}, "stocks": stocks, "words": words}
os.makedirs(os.path.dirname(os.path.abspath(A.dest)), exist_ok=True)
with open(A.dest, "w", encoding="utf-8") as f:
    f.write("/* build_ui_data.py로 생성. 원문 없음 */\nwindow.FG_DATA = ")
    json.dump(D, f, ensure_ascii=False, separators=(",", ":"))
    f.write(";\n")
print(f"{A.dest}: 종목 {len(stocks)}개, 거래일 {len(dates)}일 ({dates[0]}~{dates[-1]}), 예상 범위 {len(pi)}종목, {os.path.getsize(A.dest) / 1024:.0f}KB")
