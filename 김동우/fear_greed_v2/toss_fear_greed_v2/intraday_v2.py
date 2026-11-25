"""30분 단위 장중 지수 (보완안 2장 '30분 단위 집계', 4장 '30분 지수 평활'). 지금까지 버려지던 30분 칸 집계로
대시보드를 30분마다 갱신할 수 있는 지수를 만든다.

방법
- 30분 칸마다 탐욕·공포 확률 합(G, F)과 관련 글 수(Ne = 전체 − 무관). 기존 apply_out2/3 형식이면 판정 수를 쓴다
- 지수가중 평활: 반감기 H칸으로 G, F, Ne를 각각 감쇠 합산. 반감기 후보(--halflives) 중
  "다음 칸의 실제 감성"을 가장 잘 맞히는 값을 데이터로 고른다 (평균 절대오차, 다음 칸 관련 글 3건 이상만 채점)
- 글 적은 시간 안정화: S30 = (감쇠 G − 감쇠 F + K × 종목 평소 감성) ÷ (감쇠 Ne + K), 평소 감성 = 직전 20일 평균 (B7과 같은 식)
- 0~100: 같은 종목의 직전 60일 30분 값 분포 안에서의 백분위
- 회색: 감쇠 Ne가 --min-eff 미만이면 지수를 내지 않음 (글이 적은 종목·시간대)

입력 (--apply): 종목·30분 집계 폴더(apply_out_v2, 또는 류창민 apply_out2/apply_out3) / (--out) index_v2/daily_stock.csv(있으면 일 지수와 비교)
출력 (--out): intraday_v2/<종목>.csv (최근 --days일), reports/intraday_report.json, reports/intraday_report.md
사용: python intraday_v2.py --apply v2_out/apply_out_v2 --out v2_out [--days 20]
"""
import argparse
import glob
import os
from collections import defaultdict

import numpy as np
import pandas as pd

from common import write_json

P = argparse.ArgumentParser()
P.add_argument("--apply", required=True)
P.add_argument("--out", default="v2_out")
P.add_argument("--halflives", default="1,2,4,8,16", help="반감기 후보 (30분 칸 수)")
P.add_argument("--min-eff", type=float, default=5, help="이 감쇠 글 수 미만이면 회색")
P.add_argument("--days", type=int, default=20, help="종목별 파일에 남길 최근 일수")
A = P.parse_args()
K, W_BASE, W_PCT = 10, 20, 60
HLS = [float(h) for h in A.halflives.split(",")]

frames = defaultdict(list)
for f in sorted(glob.glob(os.path.join(A.apply, "*.csv"))):
    x = pd.read_csv(f)
    if not x.empty:
        frames[os.path.basename(f).split("_")[0]].append(x)


def decayed(v, hl):
    """반감기 hl칸 감쇠 합: s_t = v_t + a·s_(t-1), a = 0.5^(1/hl)"""
    a = 0.5 ** (1 / hl)
    out = np.empty_like(v)
    acc = 0.0
    for i, x in enumerate(v):
        acc = x + a * acc
        out[i] = acc
    return out


def prepare(xs):
    x = pd.concat(xs, ignore_index=True).groupby("slot_kst").sum(numeric_only=True)
    if "p_greed" in x:
        G, F, I = x.p_greed, x.p_fear, x.p_irrelevant
    else:                                      # apply_out2/3: 0.7 기준 판정 수
        G, F, I = x.n_greed, x.n_fear, 0 * x.n_posts
    x = pd.DataFrame({"n_posts": x.n_posts, "G": G, "F": F, "Ne": (x.n_posts - I).clip(lower=0)})
    x.index = pd.to_datetime(x.index)
    grid = pd.date_range(x.index.min().normalize(), x.index.max().normalize() + pd.Timedelta("23:30:00"), freq="30min")
    x = x.reindex(grid).fillna(0)
    x["day"] = x.index.normalize()
    d = x.groupby("day")[["G", "F", "Ne"]].sum()
    raw = (d.G - d.F) / d.Ne.where(d.Ne > 0)
    base = raw.shift(1).rolling(W_BASE, min_periods=5).mean().fillna(0)   # 종목의 평소 감성 (그날 제외)
    x["base"] = x.day.map(base)
    return x


def smooth(x, hl):
    sG, sF, sN = (decayed(x[c].to_numpy(float), hl) for c in ("G", "F", "Ne"))
    return (sG - sF + K * x.base.to_numpy()) / (sN + K), sN


# ---------------- 1) 반감기 고르기: 다음 칸 감성 맞히기 ----------------
X = {c: prepare(v) for c, v in frames.items()}
err = {hl: [] for hl in HLS}
for c, x in X.items():
    nxt = ((x.G - x.F) / x.Ne.where(x.Ne >= 3)).shift(-1).to_numpy()
    for hl in HLS:
        S, _ = smooth(x, hl)
        m = ~np.isnan(nxt)
        err[hl].append(np.abs(S[m] - nxt[m]))
mae = {hl: float(np.concatenate(v).mean()) for hl, v in err.items()}
HL = min(mae, key=mae.get)

# ---------------- 2) 지수 계산 ----------------
daily = None
dpath = os.path.join(A.out, "index_v2", "daily_stock.csv")
if os.path.exists(dpath):
    daily = pd.read_csv(dpath, dtype={"code": str}).set_index(["code", "date"])
os.makedirs(os.path.join(A.out, "intraday_v2"), exist_ok=True)
gray_by_hour, comp, moves = defaultdict(list), [], []
for c, x in X.items():
    S, sN = smooth(x, HL)
    x["S30"], x["eff_n"] = S, sN
    days = x.day.unique()
    idx = np.full(len(x), np.nan)
    dpos = x.day.to_numpy()
    for i, dday in enumerate(days):                         # 직전 60일 30분 값 분포 안의 백분위
        if i < W_PCT:
            continue
        ref = np.sort(S[(dpos >= days[i - W_PCT]) & (dpos < dday)])
        cur = dpos == dday
        idx[cur] = np.searchsorted(ref, S[cur], side="left") / len(ref) * 100
    x["idx30"] = idx
    x["gray"] = x.eff_n < A.min_eff
    x.loc[x.gray, "idx30"] = np.nan
    scored = x[~np.isnan(idx)]                              # 백분위를 낼 수 있는 구간(61일째부터)만 집계
    for h, gg in scored.groupby(scored.index.hour):
        gray_by_hour[h].append(gg.gray.to_numpy())
    moves.append(np.abs(np.diff(x.idx30.to_numpy()))[~np.isnan(np.diff(x.idx30.to_numpy()))])
    if daily is not None:                                   # 장 마감(15:30)·장 전(08:30) 값과 일 지수 비교
        for hm, col in (("15:30", "fg_index"), ("08:30", "p60_S_night_shr")):
            t = x.between_time(hm, hm)
            for ts, val in t.idx30.dropna().items():
                key = (c, ts.strftime("%Y-%m-%d"))
                if key in daily.index:
                    comp.append({"at": hm, "intraday": val, "daily": daily.loc[key, col]})
    keep = x[x.day >= days[max(0, len(days) - A.days)]]
    keep.assign(slot_kst=keep.index.strftime("%Y-%m-%dT%H:%M")).loc[:, ["slot_kst", "n_posts", "eff_n", "S30", "idx30", "gray"]].to_csv(
        os.path.join(A.out, "intraday_v2", f"{c}.csv"), index=False, float_format="%.4f")

C = pd.DataFrame(comp)
corr = {hm: float(g[["intraday", "daily"]].dropna().corr().iloc[0, 1]) for hm, g in C.groupby("at")} if len(C) else {}
gray = {int(h): float(np.concatenate(v).mean()) for h, v in sorted(gray_by_hour.items())}
mv = np.concatenate(moves) if moves else np.array([np.nan])
R = {"stocks": len(X), "halflife_slots": HL, "halflife_hours": HL / 2, "mae_by_halflife": mae, "min_eff": A.min_eff,
     "gray_share_by_hour": gray, "gray_share_market_hours": float(np.mean([gray[h] for h in range(9, 16) if h in gray])),
     "gray_share_night": float(np.mean([gray[h] for h in list(range(0, 9)) + list(range(20, 24)) if h in gray])),
     "median_abs_move_per_slot": float(np.nanmedian(mv)), "p90_abs_move_per_slot": float(np.nanpercentile(mv, 90)),
     "corr_with_daily": corr}
write_json(os.path.join(A.out, "reports", "intraday_report.json"), R)
L = [f"# 30분 장중 지수 ({R['stocks']}종목)", "",
     f"- 반감기: 다음 칸 감성을 가장 잘 맞힌 **{HL:g}칸({HL / 2:g}시간)** 선택. 후보별 평균 절대오차: "
     + ", ".join(f"{h:g}칸 {e:.3f}" for h, e in mae.items()),
     f"- 회색(감쇠 글 수 {A.min_eff:g}건 미만) 비율: 장중(09~15시) {R['gray_share_market_hours']:.1%}, 밤(20~09시) {R['gray_share_night']:.1%}",
     f"- 30분마다 지수가 움직이는 폭: 중앙값 {R['median_abs_move_per_slot']:.1f}점, 상위 10% {R['p90_abs_move_per_slot']:.1f}점 이상"]
for hm, lab in (("15:30", "15:30 장중 지수 ↔ 그날 0~100 일 지수"), ("08:30", "08:30 장중 지수 ↔ 그날 밤사이 심리 백분위")):
    if hm in corr:
        L.append(f"- 상관 {lab}: {corr[hm]:.2f}")
L += ["", "시간대별 회색 비율", "", "| 시 | " + " | ".join(str(h) for h in gray) + " |", "|---|" + "---|" * len(gray),
      "| 회색 | " + " | ".join(f"{v:.0%}" for v in gray.values()) + " |", "",
      f"종목별 최근 {A.days}일 30분 지수: intraday_v2/<종목>.csv (slot_kst, n_posts, eff_n, S30, idx30, gray)"]
open(os.path.join(A.out, "reports", "intraday_report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L))
