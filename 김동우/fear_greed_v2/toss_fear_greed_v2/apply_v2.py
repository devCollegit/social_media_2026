"""전체 글에 v2 모델 적용 → 종목·30분(KST)별 집계 (보완안 A1·A4·B5).
류창민 apply_all2.py와 같은 형식에 열을 더한다. 원문은 저장하지 않는다.
- 확률 합(p_greed, p_fear, p_irrelevant ...): 0.7 기준으로 자르지 않고 확률을 그대로 더한 값 (A1)
- n_greed, n_fear: 기존과 같은 0.7 기준 판정 수 (비교용)
- 행동 열: 대댓글 수, 매수·매도 인증 수, 보유 표시 수, 좋아요 합 (B5)
- 대댓글은 같은 종목 파일에서 부모 원글 본문을 찾아 붙인다 (A4)

입력 (--base): data/raw/posts/<종목>.csv (김정기 수집기 형식, 없으면 예전 data/posts/<종목>.jsonl), sectors.json / (--model) model_v2.joblib
출력 (--out): apply_out_v2/<종목>_<YYYY-MM>.csv  (한 달 = 전월 27일 ~ 당월 27일 전, 이미 있으면 건너뜀)
사용: python apply_v2.py --base <toss_fear_greed 폴더> --model v2_out/model_v2.joblib --out v2_out [--codes 005930 000660]
"""
import argparse
import csv
import json
import os
import time
from collections import defaultdict
from datetime import datetime

import joblib
import numpy as np

from common import KST, load_sectors, make_cleaner, posts_path, read_posts, slot_of

P = argparse.ArgumentParser()
P.add_argument("--base", required=True)
P.add_argument("--model", required=True)
P.add_argument("--out", default="v2_out")
P.add_argument("--codes", nargs="*")
P.add_argument("--chunk", type=int, default=20000)
A = P.parse_args()

B = joblib.load(A.model)
CL = B["classes"]
THR = B.get("threshold", 0.7)
SECT = load_sectors(A.base)
clean = make_cleaner(SECT)
CODES = [c for v in SECT.values() for c in v]
OUT = os.path.join(A.out, "apply_out_v2")
os.makedirs(OUT, exist_ok=True)
COLS = ["slot_kst", "n_posts", "n_reply", "n_buy", "n_sell", "n_holding",
        "p_greed", "p_fear", "p_neutral", "p_irrelevant", "p_unsure", "n_greed", "n_fear", "n_greed_argmax", "n_fear_argmax", "n_likes"]


def proba(rows):
    text = [clean(r[1]) for r in rows]
    if B["kind"] == "base3":
        return B["model"].predict_proba(B["vectorizer"].transform(text))
    return B["model"].predict_proba(B["featurizer"].transform(
        text, [clean(r[2]) for r in rows], [r[3] for r in rows], [r[4] for r in rows], [r[5] for r in rows]))


def month_key(t):
    if t.day >= 27:
        return f"{t.year}-{t.month:02d}"
    y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    return f"{y}-{m:02d}"


ix = {c: CL.index(c) for c in CL}
total, t0 = 0, time.time()
for code in CODES:
    if A.codes and code not in A.codes:
        continue
    path = posts_path(A.base, code)
    if not path:
        print(code, "입력 없음, 건너뜀")
        continue
    seen, parent, by_month = set(), {}, defaultdict(list)
    for r in read_posts(path):
        if r["post_id"] in seen or not r["text"].strip():
            continue
        seen.add(r["post_id"])
        if not r["parent_id"]:
            parent[r["post_id"]] = r["text"]
        t = datetime.fromisoformat(r["created_at"]).astimezone(KST)
        by_month[month_key(t)].append([slot_of(t), r["text"][:400], r["parent_id"], bool(r["parent_id"]),
                                       r["badge"], r["is_holder"], r["like_count"]])
    for ym in sorted(by_month):
        out = os.path.join(OUT, f"{code}_{ym}.csv")
        if os.path.exists(out):
            continue
        rows = by_month[ym]
        for r in rows:                                  # 부모 원글 본문 (원문 파일 안에서 찾음)
            r[2] = (parent.get(r[2]) or "")[:300] if r[2] else ""
        agg = defaultdict(lambda: np.zeros(len(COLS) - 1))
        for i in range(0, len(rows), A.chunk):
            ch = rows[i:i + A.chunk]
            pr = proba(ch)
            pg = pr[:, ix["greed"]]
            pf = pr[:, ix["fear"]]
            am = pr.argmax(1)
            for j, r in enumerate(ch):
                g = agg[r[0]]
                g[0] += 1
                g[1] += r[3]
                g[2] += r[4] == "BUY"
                g[3] += r[4] == "SELL"
                g[4] += bool(r[5])
                for k, lab in enumerate(["greed", "fear", "neutral", "irrelevant", "unsure"]):
                    if lab in ix:
                        g[5 + k] += pr[j, ix[lab]]
                if "other" in ix:               # 3분류 모델이면 '그 외' 확률을 중립 칸에 넣음
                    g[7] += pr[j, ix["other"]]
                g[10] += pg[j] >= THR
                g[11] += pf[j] >= THR
                g[12] += CL[am[j]] == "greed"
                g[13] += CL[am[j]] == "fear"
                g[14] += r[6]
        with open(out + ".tmp", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(COLS)
            for h in sorted(agg):
                v = agg[h]
                w.writerow([h] + [int(x) for x in v[:5]] + [round(float(x), 3) for x in v[5:10]] + [int(x) for x in v[10:]])
        os.replace(out + ".tmp", out)
        total += len(rows)
    print(f"{code} 누적 {total:,}건 {(time.time() - t0) / 60:.1f}분", flush=True)
print(f"완료: {total:,}건 → {OUT}")
