"""v2 지수 만들기 (보완안 B1~B7). 류창민 build_index.py의 지수(S, 20일 백분위, 방향·강도·국면)도 같은 표에 함께 낸다.

거래일 배정은 기존과 같다: 20:00 이후 글과 휴장일 글은 다음 거래일, 09:00 전 글은 그 거래일의 야간.
새로 내는 값
- S_prob   : 확률 합으로 만든 감성 (탐욕 확률 합 − 공포 확률 합) ÷ (관련 글 수 + 10). 관련 글 수 = 전체 − 무관 확률 합 (A1, A3)
- S_pacc   : 보정 집계(PACC)로 추정한 탐욕 비율 − 공포 비율 (B1). quantify.json의 채점 묶음 기준 계수 사용
- S_shr    : 글 적은 날을 종목의 평소 수준(직전 20거래일) 쪽으로 10건분 당긴 값 (B7). 낮·밤 각각도 계산
- attn_ratio, attn_z : 글 수의 직전 20거래일 평균 대비 배수와, 중앙값·MAD 기준 강건한 표준점수 (B2)
- p60_*    : 60거래일 백분위 (B3). 기존 20일 백분위(p20_*)도 함께
- resid    : 그날 종목·시장 수익률로 설명되는 부분을 뺀 잔차 심리 (B4)
- buy_ratio, holding_share : 매수 인증 ÷ (매수 + 매도 인증), 보유 표시 비율 (B5)
- fg_index : 0~100 공포탐욕 지수 = S_shr의 60일 백분위. direction_v2·strength_v2·regime_v2 (B6)

입력 (--base): trading_days.csv, sectors.json, ohlcv.json, krx_index.json / (--out) apply_out_v2/ 또는 --apply 로 기존 apply_out2/
출력 (--out): index_v2/daily_stock.csv, daily_sector.csv, daily_market.csv, reports/index_report.json
사용: python build_index_v2.py --base <toss_fear_greed 폴더> --out v2_out
"""
import argparse
import glob
import json
import os

import numpy as np
import pandas as pd

from common import load_sectors, load_trading_days, make_tday, stock_maps, write_json

P = argparse.ArgumentParser()
P.add_argument("--base", required=True)
P.add_argument("--out", default="v2_out")
P.add_argument("--apply", default="", help="집계 폴더. 비우면 <out>/apply_out_v2")
P.add_argument("--start", default="")
A = P.parse_args()
K, W20, W60 = 10, 20, 60
KOSDAQ = {"086520", "196170", "000250", "028300", "058470", "005290", "036930", "403870", "032820", "277810", "108490", "222800"}

SECT = load_sectors(A.base)
SECTOR, NAME = stock_maps(SECT)
TD = load_trading_days(A.base)
to_tday = make_tday(TD)
ap = A.apply or os.path.join(A.out, "apply_out_v2")
qpath = os.path.join(A.out, "quantify.json")
Q = json.load(open(qpath))["params"] if os.path.exists(qpath) else None

# ---------------- 30분 집계 → 종목·거래일·낮/밤 ----------------
rows = []
for f in sorted(glob.glob(os.path.join(ap, "*.csv"))):
    x = pd.read_csv(f)
    if x.empty:
        continue
    x["code"] = os.path.basename(f).split("_")[0]
    m = x.slot_kst.map(to_tday)
    x["date"] = [a for a, _ in m]
    x["part"] = [b for _, b in m]
    rows.append(x.dropna(subset=["date"]))
x = pd.concat(rows, ignore_index=True)
if "p_greed" not in x:                       # 기존 apply_out2 형식이면 판정 수를 확률 합 자리에 쓴다
    x["p_greed"], x["p_fear"], x["p_irrelevant"] = x.n_greed, x.n_fear, 0.0
    for c in ("n_reply", "n_buy", "n_sell", "n_holding"):
        x[c] = 0
if "n_likes" not in x:
    x["n_likes"] = 0
VAL = ["n_posts", "n_reply", "n_buy", "n_sell", "n_holding", "n_likes", "p_greed", "p_fear", "p_irrelevant", "n_greed", "n_fear"]
day = x.groupby(["code", "date"])[VAL].sum()
part = x.groupby(["code", "date", "part"])[["n_posts", "p_greed", "p_fear", "p_irrelevant"]].sum().unstack("part").fillna(0)
part.columns = [f"{p}_{c}" for c, p in part.columns]
d = day.join(part, how="left").fillna(0).reset_index()
full = []
for code, g in d.groupby("code"):            # 글이 없는 거래일도 0으로 채움 (첫 글 이후 구간)
    days = [t for t in TD if g.date.min() <= t <= g.date.max()]
    full.append(g.set_index("date").reindex(days).fillna(0).assign(code=code).rename_axis("date").reset_index())
d = pd.concat(full, ignore_index=True).sort_values(["code", "date"]).reset_index(drop=True)


def pct_rank(s, w):
    """직전 w거래일(오늘 포함) 안에서 오늘 값의 백분위. build_index.py의 pct_rank와 같은 식."""
    return s.rolling(w, min_periods=w).apply(lambda a: (np.sum(a < a[-1]) + 0.5 * (np.sum(a == a[-1]) - 1)) / (len(a) - 1) * 100, raw=True)


def ent1(g, f):
    n = g + f
    p = np.where(n > 0, g / np.where(n > 0, n, 1), 0.5)
    p = np.clip(p, 1e-12, 1 - 1e-12)
    h = -(p * np.log2(p) + (1 - p) * np.log2(1 - p))
    return np.where(n > 0, 1 - h, np.nan)


def pacc(mean_p, q):
    dd = q["tpr"] - q["fpr"]
    return np.clip((mean_p - q["fpr"]) / dd, 0, 1) if dd > 0.05 else mean_p


def shrink(G, F, N, base):
    return (G - F + K * base) / (N + K)


out = []
for code, g in d.groupby("code"):
    g = g.copy()
    N, G, F, I = g.n_posts, g.p_greed, g.p_fear, g.p_irrelevant
    Ne = (N - I).clip(lower=0)
    g["S_orig"] = (g.n_greed - g.n_fear) / (N + K)                     # 류창민 지수와 같은 식
    g["S_prob"] = (G - F) / (Ne + K)
    if Q:
        mg, mf = G / N.where(N > 0), F / N.where(N > 0)
        g["S_pacc"] = pacc(mg, Q["greed"]) - pacc(mf, Q["fear"])
    raw = (G - F) / Ne.where(Ne > 0)
    base = raw.shift(1).rolling(W20, min_periods=5).mean().fillna(0)  # 종목의 평소 감성 (오늘 제외)
    g["S_shr"] = shrink(G, F, Ne, base)
    for p in ("day", "night"):
        Np = (g[f"{p}_n_posts"] - g[f"{p}_p_irrelevant"]).clip(lower=0)
        g[f"S_{p}_shr"] = shrink(g[f"{p}_p_greed"], g[f"{p}_p_fear"], Np, base)
    prev = N.shift(1).rolling(W20, min_periods=10)
    g["attn_ratio"] = N / prev.mean()
    ln = np.log1p(N)
    med = ln.shift(1).rolling(W20, min_periods=10).median()
    mad = (ln.shift(1) - med).abs().rolling(W20, min_periods=10).median()
    g["attn_z"] = (ln - med) / (1.4826 * mad.replace(0, np.nan))
    g["concentration"] = ent1(G, F)
    nb = g.n_buy + g.n_sell
    g["buy_ratio"] = (g.n_buy / nb).where(nb >= 5)
    g["holding_share"] = (g.n_holding / N).where(N > 0)
    for c in ("S_orig",):
        g[f"p20_{c}"] = pct_rank(g[c].fillna(0), W20)
    for c in ("S_shr", "S_night_shr", "S_day_shr", "concentration"):
        g[f"p60_{c}"] = pct_rank(g[c].fillna(g[c].median()), W60)
    g["p60_attn"] = pct_rank(np.log(g.attn_ratio.clip(lower=0.05)).fillna(0), W60)
    out.append(g)
d = pd.concat(out, ignore_index=True)

# ---------------- 잔차 심리 (B4): 종목 고정효과 회귀로 그날 수익률이 설명하는 부분을 뺀다 ----------------
ohl = json.load(open(os.path.join(A.base, "ohlcv.json")))
kidx = json.load(open(os.path.join(A.base, "krx_index.json")))
px = lambda c, t, k: (ohl.get(c, {}).get(t) or [np.nan] * 5)[k]
d["close"] = [px(c, t, 3) for c, t in zip(d.code, d.date)]
d["ret"] = d.groupby("code").close.transform(lambda s: s / s.shift(1) - 1) * 100
mk = np.where(d.code.isin(KOSDAQ), "KOSDAQ", "KOSPI")
d["m_close"] = [(kidx[m].get(t) or [np.nan] * 5)[3] for m, t in zip(mk, d.date)]
d["mret"] = d.groupby("code").m_close.transform(lambda s: s / s.shift(1) - 1) * 100
ok = d[["S_shr", "ret", "mret"]].notna().all(axis=1)
dm = d.loc[ok, ["S_shr", "ret", "mret"]].sub(d.loc[ok].groupby("code")[["S_shr", "ret", "mret"]].transform("mean"))
beta, *_ = np.linalg.lstsq(dm[["ret", "mret"]].to_numpy(), dm.S_shr.to_numpy(), rcond=None)
d.loc[ok, "resid"] = dm.S_shr - dm[["ret", "mret"]].to_numpy() @ beta
d["p60_resid"] = d.groupby("code").resid.transform(lambda s: pct_rank(s.fillna(0), W60))
r2 = 1 - np.var(dm.S_shr - dm[["ret", "mret"]].to_numpy() @ beta) / np.var(dm.S_shr)

# ---------------- 0~100 지수와 국면 (B6) ----------------
d["fg_index"] = d.p60_S_shr
d["direction_v2"] = d.p60_S_shr
d["strength_v2"] = d[["p60_attn", "p60_concentration"]].mean(axis=1, skipna=False)


def regime(a, b):
    if pd.isna(a) or pd.isna(b):
        return None
    if a >= 56:
        return "과열 매수" if b >= 80 else "낙관"
    if a <= 45:
        return "패닉" if b >= 80 else "비관"
    return "중립"


d["regime_v2"] = [regime(a, b) for a, b in zip(d.direction_v2, d.strength_v2)]
# 하위 지표의 주성분 (가중치를 데이터로 정하는 참고값, B6)
comp = ["p60_S_shr", "p60_attn", "p60_concentration", "p60_resid"]
Z = d[comp].dropna()
Z = (Z - Z.mean()) / Z.std()
w, V = np.linalg.eigh(np.cov(Z.T))
pc1 = dict(zip(comp, np.round(V[:, -1] * np.sign(V[:, -1].sum()), 3)))
if A.start:
    d = d[d.date >= A.start]
d.insert(1, "stock_name", d.code.map(NAME))
d.insert(2, "sector", d.code.map(SECTOR))
os.makedirs(os.path.join(A.out, "index_v2"), exist_ok=True)
d.to_csv(os.path.join(A.out, "index_v2", "daily_stock.csv"), index=False, float_format="%.5f")

# ---------------- 섹터·시장: 글 수 가중 평균 ----------------
VALS = ["S_orig", "S_prob", "S_shr", "S_night_shr", "resid", "fg_index", "direction_v2", "strength_v2", "buy_ratio"]


def wavg(g):
    r = {"n_posts": g.n_posts.sum(), "n_stocks": g.code.nunique()}
    for c in VALS:
        okk = g[c].notna() & (g.n_posts > 0)
        r[c] = np.average(g.loc[okk, c], weights=g.loc[okk, "n_posts"]) if okk.any() else np.nan
    r["regime_v2"] = regime(r["direction_v2"], r["strength_v2"])
    return pd.Series(r)


sec = d.groupby(["sector", "date"]).apply(wavg).reset_index()
mkt = d.groupby("date").apply(wavg).reset_index()
sec.to_csv(os.path.join(A.out, "index_v2", "daily_sector.csv"), index=False, float_format="%.5f")
mkt.to_csv(os.path.join(A.out, "index_v2", "daily_market.csv"), index=False, float_format="%.5f")

# ---------------- 요약 ----------------
cc = d[["S_orig", "S_prob", "S_pacc", "S_shr", "resid"]].corr().round(3) if "S_pacc" in d else d[["S_orig", "S_prob", "S_shr", "resid"]].corr().round(3)
rep = {"rows": len(d), "stocks": int(d.code.nunique()), "dates": [d.date.min(), d.date.max()],
       "residual_model": {"beta_ret": float(beta[0]), "beta_mret": float(beta[1]), "r2_within": float(r2)},
       "pc1_loadings": pc1, "corr": cc.to_dict(), "regime_v2": d.regime_v2.value_counts(dropna=False).to_dict(),
       "pacc_used": bool(Q), "share_days_no_posts": float((d.n_posts == 0).mean())}
write_json(os.path.join(A.out, "reports", "index_report.json"), rep)
print(f"종목·일 {len(d):,}행 ({rep['dates'][0]}~{rep['dates'][1]}), 섹터·일 {len(sec):,}, 시장·일 {len(mkt):,}")
print("잔차 모형: 수익률 1%p → S_shr", round(beta[0], 4), "/ 설명력(종목 내)", round(r2, 3))
print("상관:\n", cc)
