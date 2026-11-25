"""검증용 합성 데이터 만들기. 류창민 toss_fear_greed의 입력·중간 파일과 같은 형식으로 만든다.
실제 데이터가 아니다. v2 스크립트가 처음부터 끝까지 돌아가는지, 그리고 분석이 심어 둔 관계를 찾아내는지 확인하는 용도다.

심어 둔 관계 (analysis_v2.py가 찾아내야 하는 것)
- 낮 글 심리는 그날 주가를 따라간다 (후행)
- 밤 글 심리는 ① 밤사이 미국 증시 ② 전일 시간외(15:30~20:00) 가격 ③ 종목 고유의 밤사이 소식을 반영한다.
  시가 갭도 같은 세 가지로 움직이므로, ①②를 통제하지 않으면 밤 글이 갭을 '예측'하는 것처럼 보인다. ③만 진짜 신호다.
- 글이 몰린 날과 그다음 날 개인 순매수가 늘고, 개인과 기관·외국인은 반대로 움직인다
- 의견이 갈린 날(쏠림이 낮은 날) 다음 날 거래량이 늘어난다
- 탐욕 글일수록 매도 인증이 많다 (말과 행동의 괴리)

출력 (--out 폴더): sectors.json, trading_days.csv, data/raw/posts/<종목>.csv (김정기 수집기 형식), sample_30k_clean.json, sample_prev12_clean.json,
labels/bNN.jsonl, ohlcv.json, closes.json, krx_index.json, krx_investor.json, krx_short.json, us_overnight.csv, nxt_after.json, TRUTH.json
사용: python make_synthetic.py --out synthetic --sectors 5 --scale 1.0
"""
import argparse
import csv
import json
import math
import os
import random
from datetime import date, datetime, timedelta

import numpy as np

from common import KST, NXT_START, load_sectors, month_of, read_posts, write_json

P = argparse.ArgumentParser()
P.add_argument("--out", default="synthetic")
P.add_argument("--sectors", type=int, default=5, help="sectors.json 앞에서부터 쓸 섹터 수 (섹터당 3종목)")
P.add_argument("--scale", type=float, default=1.0, help="글 수 배율")
P.add_argument("--start", default="2024-10-01")
P.add_argument("--end", default="2025-12-31")
P.add_argument("--seed", type=int, default=7)
A = P.parse_args()
rng = np.random.default_rng(A.seed)
random.seed(A.seed)
OUT = A.out
os.makedirs(f"{OUT}/data/raw/posts", exist_ok=True)
os.makedirs(f"{OUT}/labels", exist_ok=True)

ALL = load_sectors(os.path.dirname(os.path.abspath(__file__)))
SECTORS = {k: ALL[k] for k in list(ALL)[: A.sectors]}
write_json(f"{OUT}/sectors.json", SECTORS)
CODES = [c for v in SECTORS.values() for c in v]
NAME = {c: n for v in SECTORS.values() for c, n in v.items()}
SECTOR = {c: s for s, v in SECTORS.items() for c in v}

# ---------------- 거래일 ----------------
d0, d1 = date.fromisoformat(A.start), date.fromisoformat(A.end)
TD = [(d0 + timedelta(i)).isoformat() for i in range((d1 - d0).days + 1) if (d0 + timedelta(i)).weekday() < 5]
T = len(TD)
open(f"{OUT}/trading_days.csv", "w").write("date\n" + "\n".join(TD) + "\n")
nxt = np.array([d >= NXT_START for d in TD])

# ---------------- 시장 ----------------
us = rng.normal(0, 1.0, T)                      # 밤사이 미국 증시 (%), 당일 시가 전에 알려짐
m_gap = 0.5 * us + rng.normal(0, 0.2, T)        # 지수 시가 갭
m_intra = rng.normal(0, 0.8, T)                 # 지수 장중
m_ret = m_gap + m_intra
idx_close = 2500 * np.exp(np.cumsum(m_ret) / 100)
idx_open = np.r_[2500, idx_close[:-1]] * np.exp(m_gap / 100)

# ---------------- 종목 잠재 변수 ----------------
TRUTH = {"note": "합성 데이터에 심어 둔 계수", "night_genuine_info_to_gap": 0.8, "us_to_gap": 0.5, "after_hours_to_gap": 1.0}
S = {}
for c in CODES:
    big = 5.0 if c in ("005930", "000660") else 1.0
    base_posts = A.scale * big * math.exp(rng.normal(3.4, 0.45))
    o = rng.normal(0, 0.6, T)                                   # 종목 고유의 밤사이 소식
    ah = np.where(nxt, rng.normal(0, 0.7, T), 0.0)              # 그날 저녁 시간외 수익률 (출범 후만)
    ah_prev = np.r_[0, ah[:-1]]
    gap = m_gap + ah_prev + 0.8 * o + rng.normal(0, 0.45, T)
    intra = 1.1 * m_intra + rng.normal(0, 1.6, T)
    ret = gap + intra
    spike = np.where(rng.random(T) < 0.04, rng.uniform(0.7, 1.4, T), 0.0)
    latt = 0.18 * np.abs(ret) + 0.25 * rng.normal(0, 1, T) + spike
    latt = latt - latt.mean()
    dis = np.zeros(T)
    for t in range(1, T):
        dis[t] = 0.3 * dis[t - 1] + rng.normal(0, 1)
    e_day = rng.normal(0, 1, T)
    s_day = np.tanh(0.33 * ret + 0.08 * np.r_[0, ret[:-1]] + 0.25 * e_day)
    s_night = np.tanh(0.30 * us + 0.45 * ah_prev + 0.55 * o + 0.12 * np.r_[0, ret[:-1]] + 0.25 * rng.normal(0, 1, T))
    priv = -1.4 * ret + 3.0 * latt + 1.2 * np.r_[0, latt[:-1]] + rng.normal(0, 2.0, T)
    inst = -0.55 * priv + 0.5 * ret + rng.normal(0, 1.2, T)
    frgn = -priv - inst + rng.normal(0, 0.8, T)
    lvol = 0.10 * np.abs(ret) + 0.55 * latt + 0.15 * np.r_[0, dis[:-1]] + rng.normal(0, 0.15, T)
    close = rng.uniform(20000, 300000) * np.exp(np.cumsum(ret) / 100)
    prev_close = np.r_[close[0] / math.exp(ret[0] / 100), close[:-1]]
    opn = prev_close * np.exp(gap / 100)
    hi = np.maximum(opn, close) * (1 + np.abs(rng.normal(0, 0.008, T)))
    lo = np.minimum(opn, close) * (1 - np.abs(rng.normal(0, 0.008, T)))
    vol = (rng.uniform(2e5, 3e6) * np.exp(lvol)).astype(int)
    S[c] = dict(base=base_posts, latt=latt, dis=dis, s_day=s_day, s_night=s_night, ret=ret, gap=gap, ah=ah, o=o,
                priv=priv, inst=inst, frgn=frgn, open=opn, high=hi, low=lo, close=close, vol=vol)

# ---------------- 문장 ----------------
BANK = {
    "greed": ["가즈아", "내일 상한가 간다", "줍줍했습니다", "저점 매수 성공", "드디어 오른다", "추매 들어갑니다", "수익 실현 감사합니다",
              "그때 살걸 아쉽다", "실적 좋다 더 간다", "불타기 갑니다", "신고가 가자", "떡상 시작", "존버 승리", "풀매수 박았다", "날아간다"],
    "fear": ["손절했습니다", "물렸네요 ㅠㅠ", "이제 끝났다", "개미털기 끝이 없다", "평단 회복 언제", "더 떨어질듯", "탈출합니다", "무섭다 진짜",
             "원금 회복 어렵네요", "떡락 미쳤다", "한강 간다", "나락 가네", "공매도 세력 때문에", "하한가 각", "버티기 힘들다"],
    "neutral": ["실적 발표 언제예요?", "공시 떴네요", "거래량 많네", "외국인 순매수 1위", "오늘 몇시 마감인가요", "배당 기준일 언제죠",
                "다 같이 빠졌네", "뉴스 나왔네요", "목표가 리포트 나옴"],
    "irrelevant": ["점심 뭐 먹지", "무료 리딩방 오세요", "날씨 좋네요", "주말 잘 보내세요", "축구 보신 분", "@사용자 님 반가워요"],
    "unsure": ["ㅋㅋㅋ 역시", "오르든 말든", "흠", "그렇군", "이게 뭐지", "부럽다.. 그래도 버팁니다"],
}
FILL = ["", "", "", " ㅋㅋ", " ㅎㅎ", " 진짜", " 오늘", " 형님들", " 🚀", " 😭", " ...", "!!"]
REPLY_SHORT = ["저도요", "ㄹㅇ", "인정합니다", "ㅇㅈ", "222"]


def phrase(lab, name):
    a = random.choice(BANK[lab])
    if random.random() < 0.35:
        a = (name if random.random() < 0.5 else "이 종목") + " " + a
    if random.random() < 0.25:
        a += " " + random.choice(BANK[lab])
    if random.random() < 0.2:
        a += f" {random.randint(1, 99)}만원"
    return a + random.choice(FILL)


def draw_label(s, dis):
    u = random.random()
    if u < 0.30:
        return "neutral"
    if u < 0.40:
        return "irrelevant"
    if u < 0.52:
        return "unsure"
    p = (1 + s) / 2
    p = 0.5 + (p - 0.5) * (1 - 0.75 / (1 + math.exp(-dis)))     # 의견이 갈린 날은 탐욕·공포가 반반에 가까워짐
    return "greed" if random.random() < p else "fear"


def ts_between(a, b):
    return a + timedelta(seconds=random.random() * (b - a).total_seconds())


# ---------------- 글 ----------------
true_label = {}      # (code, post_id) -> 진짜 라벨
n_total = 0
for c in CODES:
    z = S[c]
    rows = []
    pid = 0
    for t, d in enumerate(TD):
        n = rng.poisson(z["base"] * math.exp(z["latt"][t]))
        day_n = int(round(n * 0.76))
        dd = datetime.fromisoformat(d).replace(tzinfo=KST)
        prev = datetime.fromisoformat(TD[t - 1]).replace(tzinfo=KST) if t else dd - timedelta(days=1)
        windows = [("day", dd.replace(hour=9), dd.replace(hour=20), day_n),
                   ("night", prev.replace(hour=20), dd.replace(hour=9), n - day_n)]
        for part, a, b, k in windows:
            s = z["s_day"][t] if part == "day" else z["s_night"][t]
            recent = []
            for _ in range(k):
                pid += 1
                when = ts_between(a, b)
                parent = None
                if recent and random.random() < 0.25:
                    parent = random.choice(recent)
                    lab = parent[1] if random.random() < 0.5 else draw_label(s, z["dis"][t])
                    body = random.choice(REPLY_SHORT) if lab == parent[1] else phrase(lab, NAME[c])
                else:
                    lab = draw_label(s, z["dis"][t])
                    body = phrase(lab, NAME[c])
                side = None
                if random.random() < 0.10:
                    side = "BUY" if random.random() < 0.5 - 0.3 * s else "SELL"
                rows.append({"stock_id": c, "post_id": str(pid), "parent_id": parent[0] if parent else "", "text": body,
                             "created_at": when.isoformat(timespec="seconds"), "collected_at": "", "source": "synthetic",
                             "badge": side or "", "like_count": int(rng.poisson(1.5)), "reply_count": 0,
                             "is_holder": 1 if random.random() < 0.5 else 0})
                true_label[(c, str(pid))] = lab
                if not parent:
                    recent.append((str(pid), lab))
                    recent = recent[-30:]
    rows.sort(key=lambda r: r["created_at"])
    with open(f"{OUT}/data/raw/posts/{c}.csv", "w", encoding="utf-8", newline="") as f:   # 김정기 수집기 형식 (11개 열)
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    n_total += len(rows)
    print(c, NAME[c], f"{len(rows):,}건", flush=True)

# ---------------- LLM 판정 표본 (make_sample.py + make_batches.py 형식) ----------------
NOISE = 0.08


def llm_label(lab):
    if random.random() < NOISE:
        return random.choice([x for x in ["greed", "fear", "neutral", "irrelevant", "unsure"] if x != lab])
    return lab


def sample(months, pfx, fname, start_batch):
    out = []
    n = 0
    for c in CODES:
        rows = list(read_posts(f"{OUT}/data/raw/posts/{c}.csv"))
        parent = {r["post_id"]: r for r in rows if not r["parent_id"]}
        bym = {}
        for r in rows:
            bym.setdefault(month_of(r["created_at"]), []).append(r)
        for m in months:
            pool = bym.get(m, [])
            for r in random.sample(pool, min(56, len(pool))):
                n += 1
                pp = parent.get(r["parent_id"])
                out.append({"id": f"{pfx}{n:05d}", "sector": SECTOR[c], "stock_code": c, "stock_name": NAME[c],
                            "post_id": r["post_id"], "is_reply": bool(r["parent_id"]),
                            "published_at": datetime.fromisoformat(r["created_at"]).astimezone().isoformat(),
                            "holding": "HOLDING" if r["is_holder"] else None, "execution_side": r["badge"],
                            "text": r["text"][:400], "parent_text": pp["text"][:300] if pp else None,
                            "_true": true_label[(c, r["post_id"])]})
    random.shuffle(out)
    for i in range(0, len(out), 1000):
        with open(f"{OUT}/labels/b{start_batch + i // 1000:02d}.jsonl", "w", encoding="utf-8") as f:
            for r in out[i:i + 1000]:
                f.write(json.dumps({"id": r["id"], "label": llm_label(r.pop("_true"))}) + "\n")
    json.dump(out, open(f"{OUT}/{fname}", "w", encoding="utf-8"), ensure_ascii=False)
    print(fname, f"{len(out):,}건, 묶음 b{start_batch:02d}~b{start_batch + (len(out) - 1) // 1000:02d}")


all_months = sorted({month_of(datetime.fromisoformat(d).replace(tzinfo=KST, hour=12).isoformat()) for d in TD})
recent, prev = [m for m in all_months if m >= "2025-01"], [m for m in all_months if m < "2025-01"]
sample(recent, "s", "sample_30k_clean.json", 0)
sample(prev, "t", "sample_prev12_clean.json", 31)

# ---------------- KRX 형식 ----------------
ohlcv = {c: {d: [int(S[c]["open"][t]), int(S[c]["high"][t]), int(S[c]["low"][t]), int(S[c]["close"][t]), int(S[c]["vol"][t])]
             for t, d in enumerate(TD)} for c in CODES}
json.dump(ohlcv, open(f"{OUT}/ohlcv.json", "w"))
json.dump({c: {d: v[3] for d, v in x.items()} for c, x in ohlcv.items()}, open(f"{OUT}/closes.json", "w"))
idx = {k: {d: [float(idx_open[t]), float(max(idx_open[t], idx_close[t])), float(min(idx_open[t], idx_close[t])), float(idx_close[t]), 0]
           for t, d in enumerate(TD)} for k in ("KOSPI", "KOSDAQ")}
json.dump(idx, open(f"{OUT}/krx_index.json", "w"))
inv, sht = {}, {}
for c in CODES:
    z = S[c]
    tv = z["close"] * z["vol"]
    inv[c] = {d: {"개인": int(z["priv"][t] / 100 * tv[t]), "기관합계": int(z["inst"][t] / 100 * tv[t]),
                  "외국인합계": int(z["frgn"][t] / 100 * tv[t])} for t, d in enumerate(TD)}
    sht[c] = {d: {"공매도": float(int(z["vol"][t] * max(0.005, rng.normal(0.03, 0.01)))), "매수": float(z["vol"][t])} for t, d in enumerate(TD)}
json.dump(inv, open(f"{OUT}/krx_investor.json", "w"), ensure_ascii=False)
json.dump(sht, open(f"{OUT}/krx_short.json", "w"), ensure_ascii=False)
open(f"{OUT}/us_overnight.csv", "w").write("date,us_ret\n" + "\n".join(f"{d},{us[t]:.4f}" for t, d in enumerate(TD)) + "\n")
json.dump({c: {d: float(S[c]["ah"][t]) for t, d in enumerate(TD) if nxt[t]} for c in CODES}, open(f"{OUT}/nxt_after.json", "w"))
write_json(f"{OUT}/TRUTH.json", TRUTH)
print(f"합계 글 {n_total:,}건, 종목 {len(CODES)}개, 거래일 {T}일 ({TD[0]}~{TD[-1]})")
