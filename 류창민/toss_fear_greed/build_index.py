"""기획안 4절 지수 만들기. 입력: apply_out3/ (종목·30분 집계, 모델 v2 = A4+A5, 김정기 형식 원문에 적용), trading_days.csv (KRX 거래일, pykrx 삼성전자 일봉 날짜).
거래일 배정: 그날 20:00 이전 글 -> 그 거래일, 20:00 이후 글 -> 다음 거래일 (주말·휴장일 글도 다음 거래일로).
장전(밤사이) 감성: 전 거래일 20:00 ~ 당일 09:00(정규장 개장) 전 글. 글이 적으면 그 종목 평소 감성(직전 20거래일 일간 (긍정-부정)/전체 평균)으로 10건분 당김.
출력: index_out/daily_stock.csv, daily_sector.csv, daily_market.csv
사용: uv run --with pandas python build_index.py"""
import bisect, glob, json, os
import numpy as np, pandas as pd

D = os.path.dirname(os.path.abspath(__file__))  # 이 폴더
OUT = f"{D}/index_out"; os.makedirs(OUT, exist_ok=True)
W, WMIN, K = 60, 20, 10    # 백분위 창 60거래일(B3, 앞부분은 20일부터 늘려 감), 평소 수준 쪽으로 당기는 크기(글 10건분, B7)
START = "2024-10-28"   # 2024-10-27 이후 첫 거래일. 끝은 집계에 있는 마지막 거래일(진행 중인 오늘 포함)
TD = pd.read_csv(f"{D}/trading_days.csv")["date"].tolist()
import datetime as _dt
_now = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9))); _today = _now.strftime("%Y-%m-%d")
if TD[-1] == _today and _now.hour >= 20:          # 장 마감(20:00) 뒤: 오늘 밤 글을 받을 다음 거래일(평일 기준)을 달력 끝에 붙임
    _n = _now + _dt.timedelta(days=1)
    while _n.weekday() >= 5: _n += _dt.timedelta(days=1)
    TD.append(_n.strftime("%Y-%m-%d"))
END = TD[-1]
S = json.load(open(f"{D}/sectors.json"))
SECTOR = {c: s for s, v in S.items() for c in v}; NAME = {c: n for v in S.values() for c, n in v.items()}

def to_tday(slot):   # 'YYYY-MM-DDTHH:MM' -> (거래일, 장전 여부)
    d, hm = slot[:10], slot[11:]
    if hm >= "20:00":
        i = bisect.bisect_right(TD, d)          # 다음 날 이후 첫 거래일
        return (TD[i] if i < len(TD) else None), True
    i = bisect.bisect_left(TD, d)               # 그날 또는 그 이후 첫 거래일
    if i >= len(TD): return None, False
    td = TD[i]
    pre = td != d or hm < "09:00"               # 휴장일 글이나 당일 09:00 전 글은 장전 구간
    return td, pre

rows = []
for f in sorted(glob.glob(f"{D}/apply_out3/*.csv")):
    code = os.path.basename(f).split("_")[0]
    x = pd.read_csv(f)
    if x.empty: continue
    m = x["slot_kst"].map(to_tday)
    x["date"] = [a for a, _ in m]; x["pre"] = [b for _, b in m]; x["code"] = code
    x["pre8"] = [b and not (sl[:10] == a and sl[11:] >= "08:00") for sl, (a, b) in zip(x["slot_kst"], m)]   # 강건성: NXT 프리마켓(08:00) 전까지만
    rows.append(x.dropna(subset=["date"]))
x = pd.concat(rows)
cols = ["n_posts", "n_greed", "n_fear", "n_kw_greed", "n_kw_fear"] + [c for c in ["n_buy", "n_sell", "n_holder", "h_greed", "h_fear"] if c in x.columns]   # B5 행동 축
day = x.groupby(["code", "date"])[cols].sum()
pre = x[x["pre"]].groupby(["code", "date"])[["n_posts", "n_greed", "n_fear"]].sum().add_prefix("pre_")
pre8 = x[x["pre8"]].groupby(["code", "date"])[["n_posts", "n_greed", "n_fear"]].sum().add_prefix("pre8_")
d = day.join(pre, how="left").join(pre8, how="left").fillna(0).reset_index()
# 글이 하나도 없는 거래일도 0으로 채움 (상장 전 구간 제외)
full = []
for code, g in d.groupby("code"):
    days = [t for t in TD if g["date"].min() <= t <= END]
    full.append(g.set_index("date").reindex(days).fillna({c: 0 for c in g.columns if c not in ("code", "date")}).assign(code=code).reset_index().rename(columns={"index": "date"}))
d = pd.concat(full).sort_values(["code", "date"]).reset_index(drop=True)

def pct_rank(s):   # 직전 20거래일(오늘 포함) 안에서 오늘 값의 백분위 0~100
    return s.rolling(W, min_periods=WMIN).apply(lambda a: (np.sum(a < a[-1]) + 0.5 * (np.sum(a == a[-1]) - 1)) / (len(a) - 1) * 100, raw=True)

def ent1(g, f):    # 쏠림 = 1 - 이진 엔트로피(긍정 vs 부정)
    n = g + f
    p = np.where(n > 0, g / n.where(n > 0, 1), 0.5)
    h = -(np.where(p > 0, p * np.log2(np.clip(p, 1e-12, 1)), 0) + np.where(p < 1, (1 - p) * np.log2(np.clip(1 - p, 1e-12, 1)), 0))
    return np.where(n > 0, 1 - h, 0.0)

out = []
for code, g in d.groupby("code"):
    g = g.copy()
    N, G, F = g["n_posts"], g["n_greed"], g["n_fear"]
    # B7: 글이 적은 날은 그 종목의 평소 수준(직전 60거래일 (탐욕-공포)/글 수 평균, 오늘 제외) 쪽으로 글 10건분 당긴다
    base = ((G - F) / N.where(N > 0)).shift(1).rolling(W, min_periods=5).mean().fillna(0)
    g["S"] = (G - F + K * base) / (N + K)                              # 스탠스 = 감성지수
    g["kw"] = (g["n_kw_greed"] - g["n_kw_fear"]) / N.where(N > 0)      # 키워드 강도
    m20 = N.shift(1).rolling(20, min_periods=10).mean()
    g["interest"] = N / m20.where(m20 > 0)                             # B2 관심도: 글 수 ÷ 직전 20거래일 평균
    g["concentration"] = ent1(G, F)                                    # 쏠림
    for c in ("S", "kw", "interest", "concentration"):
        g[f"p_{c}"] = pct_rank(g[c].fillna(0) if c != "interest" else g[c].fillna(0))
    # 장전 감성: 같은 평소 수준으로 K건 당김
    g["pre_S"] = (g["pre_n_greed"] - g["pre_n_fear"] + K * base) / (g["pre_n_posts"] + K)
    g["p_pre_S"] = pct_rank(g["pre_S"])                               # 밤끼리 비교
    out.append(g)
d = pd.concat(out)
PCA = {}
def pc1(cols):   # B6: 표준화한 두 하위 지표의 첫 주성분 가중치(합 1로 정규화)와 설명 비율
    x = d[cols].dropna(); z = (x - x.mean()) / x.std()
    val, vec = np.linalg.eigh(np.cov(z.T.values)); v = vec[:, -1] * np.sign(vec[:, -1].sum())
    w = v / v.sum(); return dict(zip(cols, w.round(4).tolist())), float(val[-1] / val.sum()), float(x.corr().iloc[0, 1])
for name, cols in (("direction", ["p_S", "p_kw"]), ("strength", ["p_interest", "p_concentration"])):
    w, ev, r = pc1(cols); PCA[name] = {"weights": w, "explained": ev, "corr": r}
    d[name] = sum(d[c] * w[c] for c in cols)
json.dump(PCA, open(f"{OUT}/index_weights.json", "w"), ensure_ascii=False, indent=1)
print("B6 가중치", PCA)

def regime(dir_, st):
    if pd.isna(dir_) or pd.isna(st): return None
    if dir_ >= 56: return "과열 매수" if st >= 80 else "낙관"
    if dir_ <= 45: return "패닉" if st >= 80 else "비관"
    return "중립"
d["regime"] = [regime(a, b) for a, b in zip(d["direction"], d["strength"])]
d = d[(d["date"] >= START) & (d["date"] <= END)]
d.insert(1, "stock_name", d["code"].map(NAME)); d.insert(2, "sector", d["code"].map(SECTOR))
d.to_csv(f"{OUT}/daily_stock.csv", index=False, float_format="%.4f")

# 섹터·시장: 종목 지수를 그날 글 수로 가중 평균
VALS = ["S", "kw", "direction", "strength", "pre_S", "p_pre_S"]
def wavg(g):
    r = {"n_posts": g["n_posts"].sum(), "n_stocks": g["code"].nunique()}
    for c in VALS:
        ok = g[c].notna() & (g["n_posts"] > 0)
        r[c] = np.average(g.loc[ok, c], weights=g.loc[ok, "n_posts"]) if ok.any() else np.nan
    r["regime"] = regime(r["direction"], r["strength"])
    return pd.Series(r)
sec = d.groupby(["sector", "date"]).apply(wavg).reset_index()
mkt = d.groupby("date").apply(wavg).reset_index()
sec.to_csv(f"{OUT}/daily_sector.csv", index=False, float_format="%.4f")
mkt.to_csv(f"{OUT}/daily_market.csv", index=False, float_format="%.4f")
print(f"종목·일 {len(d):,}행, 섹터·일 {len(sec):,}행, 시장·일 {len(mkt):,}행, 거래일 {d['date'].nunique()}개 ({d['date'].min()}~{d['date'].max()})")
print("국면 분포(종목·일):", d["regime"].value_counts(dropna=False).to_dict())
print("시장 국면 분포:", mkt["regime"].value_counts(dropna=False).to_dict())
