"""글자 조각(2~4) TF-IDF + 로지스틱 회귀. 3분류(탐욕/공포/그 외). 확률이 기준점 이상일 때만 판정, 나머지 보류.
사용: uv run --with scikit-learn python lr_trial.py"""
import os
import json, re
from collections import Counter, defaultdict
import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

D = os.path.dirname(os.path.abspath(__file__))  # 이 폴더
from datetime import datetime, timedelta
def month_of(ts):
    t = datetime.fromisoformat(ts) + timedelta(hours=9)
    if t.day >= 27: return f"{t.year}-{t.month:02d}"
    y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    return f"{y}-{m:02d}"
def blist(a, b): return [f"b{i:02d}" for i in range(a, b + 1)]

names = sorted({n for v in json.load(open(f"{D}/sectors.json")).values() for n in v.values()}, key=len, reverse=True)
NAME = re.compile("|".join(map(re.escape, names + "삼전 하닉 하이닉스 에코프로 엘지 현차".split())))
def clean(s):  # 종목명·숫자 가림 (특정 종목·가격대에 붙는 신호 제거)
    return re.sub(r"\d+", "0", NAME.sub("종목", s or ""))

posts = {r["id"]: r for r in json.load(open(f"{D}/sample_30k_clean.json"))}
def load(bs):
    X, P, y, m = [], [], [], []
    for b in bs:
        for line in open(f"{D}/labels/{b}.jsonl"):
            r = json.loads(line); p = posts[r["id"]]
            X.append(clean(p["text"])); P.append(clean(p["parent_text"]) if p["is_reply"] else "")
            y.append(r["label"] if r["label"] in ("greed", "fear") else "other"); m.append(month_of(p["published_at"]))
    return X, P, np.array(y), m

Xtr, Ptr, ytr, _ = load(blist(0, 16)); Xte, Pte, yte, mte = load(blist(17, 22))
GREED_ERA = {"2025-10", "2025-11", "2025-12", "2026-01", "2026-02"}; FEAR_ERA = {"2026-07", "2026-08", "2026-09"}

def evaluate(name, proba, classes):
    gi, fi = list(classes).index("greed"), list(classes).index("fear")
    print(f"\n=== {name} ===\n기준점 | 판정 비율 | 정확도 | 탐욕·공포끼리 | 탐욕기 | 공포기 | 달별 비율 평균오차")
    for t in (0.5, 0.6, 0.7, 0.8, 0.85, 0.9):
        pred = np.where(proba[:, gi] >= t, "greed", np.where(proba[:, fi] >= t, "fear", ""))
        dec = pred != ""; ok = dec & (pred == yte); opp = dec & (yte != "other") & (pred != yte)
        era = lambda E: (lambda s: f"{(ok & s).sum()/max((dec & s).sum(),1):.0%}")(np.array([x in E for x in mte]))
        bm = defaultdict(Counter)
        for mm, pr, yy in zip(mte, pred, yte):
            if yy != "other": bm[mm]["l_" + yy] += 1
            if pr: bm[mm]["k_" + pr] += 1
        err = np.mean([abs(c["k_greed"]/max(c["k_greed"]+c["k_fear"],1) - c["l_greed"]/max(c["l_greed"]+c["l_fear"],1)) for c in bm.values()])
        print(f"{t} | {dec.mean():.0%} | {ok.sum()/max(dec.sum(),1):.0%} | {ok.sum()/max(ok.sum()+opp.sum(),1):.0%} | {era(GREED_ERA)} | {era(FEAR_ERA)} | {err:.1%}p")
    return bm

v = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, sublinear_tf=True)
A = v.fit_transform(Xtr); At = v.transform(Xte)
for C in (0.5, 2.0):
    lr = LogisticRegression(C=C, class_weight="balanced", max_iter=3000).fit(A, ytr)
    evaluate(f"본문만, C={C}", lr.predict_proba(At), lr.classes_)

vp = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, sublinear_tf=True)
B = hstack([A, 0.5 * vp.fit_transform(Ptr)]).tocsr(); Bt = hstack([At, 0.5 * vp.transform(Pte)]).tocsr()
lr = LogisticRegression(C=2.0, class_weight="balanced", max_iter=3000).fit(B, ytr)
bm = evaluate("본문+부모글(가중 0.5), C=2.0", lr.predict_proba(Bt), lr.classes_)
