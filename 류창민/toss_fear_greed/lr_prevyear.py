"""이전 1년(b31~b36) 채점. 최근 1년으로만 학습한 모델이 그대로 통하는지, 이전 1년 일부를 학습에 넣으면 나아지는지 비교.
사용: uv run --with scikit-learn python lr_prevyear.py"""
import os
import json, re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

D = os.path.dirname(os.path.abspath(__file__))  # 이 폴더
def month_of(ts):
    t = datetime.fromisoformat(ts) + timedelta(hours=9)
    if t.day >= 27: return f"{t.year}-{t.month:02d}"
    y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    return f"{y}-{m:02d}"
def bl(a, b): return [f"b{i:02d}" for i in range(a, b + 1)]
names = sorted({n for v in json.load(open(f"{D}/sectors.json")).values() for n in v.values()}, key=len, reverse=True)
NAME = re.compile("|".join(map(re.escape, names + "삼전 하닉 하이닉스 에코프로 엘지 현차".split())))
clean = lambda s: re.sub(r"\d+", "0", NAME.sub("종목", s or ""))
posts = {r["id"]: r for f in ("sample_30k_clean.json", "sample_prev12_clean.json") for r in json.load(open(f"{D}/{f}"))}

def load(bs):
    X, y, m = [], [], []
    for b in bs:
        for line in open(f"{D}/labels/{b}.jsonl"):
            r = json.loads(line); p = posts[r["id"]]
            X.append(clean(p["text"])); y.append(r["label"] if r["label"] in ("greed", "fear") else "other"); m.append(month_of(p["published_at"]))
    return X, np.array(y), m

def fit(bs, C):
    X, y, _ = load(bs)
    v = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, sublinear_tf=True)
    return v, LogisticRegression(C=C, class_weight="balanced", max_iter=3000).fit(v.fit_transform(X), y)

def score(name, v, lr, bs, ts=(0.6, 0.7, 0.8), show_months=None):
    X, y, mo = load(bs); pr = lr.predict_proba(v.transform(X)); cl = list(lr.classes_)
    print(f"\n=== {name} | 채점 {len(y):,}건 ===\n기준점 | 판정 비율 | 정확도 | 탐욕·공포끼리 | 달별 비율 평균오차 | 전체기간 탐욕비율 LLM→모델")
    for t in ts:
        pred = np.where(pr[:, cl.index("greed")] >= t, "greed", np.where(pr[:, cl.index("fear")] >= t, "fear", ""))
        dec = pred != ""; ok = dec & (pred == y); opp = dec & (y != "other") & (pred != y)
        bm = defaultdict(Counter)
        for mm, p_, yy in zip(mo, pred, y):
            if yy != "other": bm[mm]["l_" + yy] += 1
            if p_: bm[mm]["k_" + p_] += 1
        r = lambda c, k: c[k + "greed"] / max(c[k + "greed"] + c[k + "fear"], 1)
        err = np.mean([abs(r(c, "k_") - r(c, "l_")) for c in bm.values()])
        tot = sum(bm.values(), Counter())
        print(f"{t} | {dec.mean():.0%} | {ok.sum()/dec.sum():.0%} | {ok.sum()/(ok.sum()+opp.sum()):.0%} | {err:.1%}p | {r(tot,'l_'):.0%}→{r(tot,'k_'):.0%}")
        if t == show_months:
            print("   달: LLM 탐욕비율 / 모델 탐욕비율")
            print("   " + "  ".join(f"{m[2:]} {r(bm[m],'l_'):.0%}/{r(bm[m],'k_'):.0%}" for m in sorted(bm)))

PREV = bl(31, 36)
for C in (0.5, 2.0):
    v, lr = fit(bl(0, 16), C)
    score(f"A. 최근 1년(b00~b16)으로 학습, C={C} → 최근 1년 채점(b17~b22)", v, lr, bl(17, 22))
    score(f"A. 같은 모델 → 이전 1년 채점(b31~b36)", v, lr, PREV, show_months=0.7)
# 이전 1년 일부를 학습에 넣으면? (b31~b33 학습, b34~b36 채점) vs 같은 채점셋에 A 모델
for C in (0.5, 2.0):
    v, lr = fit(bl(0, 16), C)
    score(f"B0. 최근 1년만 학습, C={C} → 이전 1년 b34~b36", v, lr, bl(34, 36))
    v, lr = fit(bl(0, 22) + bl(31, 33), C)
    score(f"B1. 최근 1년 전부+이전 1년 b31~b33 학습, C={C} → 이전 1년 b34~b36", v, lr, bl(34, 36))
