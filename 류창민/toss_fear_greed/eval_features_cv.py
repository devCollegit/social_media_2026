"""A4·A5 비교를 묶음 단위 5겹 교차검증으로 반복 (한 번 나눔의 우연 확인). 29개 묶음을 5무리로 나눠 차례로 채점."""
import json, sys
from collections import defaultdict
from datetime import datetime, timedelta
import numpy as np
from scipy.sparse import hstack, csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from featurize import D, clean
from extract_keywords import tokens_batch
posts = {r["id"]: r for f in ("sample_30k_clean.json", "sample_prev12_clean.json") for r in json.load(open(f"{D}/{f}"))}
def month_of(ts):
    t = datetime.fromisoformat(ts) + timedelta(hours=9)
    if t.day >= 27: return f"{t.year}-{t.month:02d}"
    y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    return f"{y}-{m:02d}"
B = [f"b{i:02d}" for i in list(range(0, 23)) + list(range(31, 37))]
rows, y, grp = [], [], []
for gi_, b in enumerate(B):
    for line in open(f"{D}/labels/{b}.jsonl"):
        r = json.loads(line); rows.append(posts[r["id"]]); y.append(r["label"] if r["label"] in ("greed", "fear") else "other"); grp.append(gi_ % 5)
y, grp = np.array(y), np.array(grp); mon = np.array([month_of(p["published_at"]) for p in rows])
TX = [clean(p["text"]) for p in rows]; PX = [clean(p["parent_text"]) if p["is_reply"] and p["parent_text"] else "" for p in rows]
WX = tokens_batch(TX)
META = csr_matrix(np.array([[float(bool(p["is_reply"])), float(p["execution_side"] == "BUY"), float(p["execution_side"] == "SELL"), float(p["holding"] == "HOLDING")] for p in rows]))
res = defaultdict(lambda: defaultdict(list))
for f in range(5):
    tr, te = grp != f, grp == f
    vt = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, sublinear_tf=True).fit([t for t, k in zip(TX, tr) if k])
    vp = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, sublinear_tf=True).fit([t for t, k in zip(PX, tr) if k])
    vw = TfidfVectorizer(analyzer=lambda s: list(s), min_df=3, sublinear_tf=True).fit([w for w, k in zip(WX, tr) if k])
    A, Pm, W = vt.transform(TX), vp.transform(PX), vw.transform(WX)
    CFG = {"(a) 지금": [A], "(b) A4": [A, 0.5 * Pm, META], "(c) A5": [A, W], "(d) A4+A5": [A, 0.5 * Pm, META, W]}
    for name, parts in CFG.items():
        X = hstack(parts).tocsr()
        lr = LogisticRegression(C=2.0, class_weight="balanced", max_iter=4000).fit(X[tr], y[tr]); P = lr.predict_proba(X[te]); c = list(lr.classes_)
        pred = np.where(P[:, c.index("greed")] >= .7, "greed", np.where(P[:, c.index("fear")] >= .7, "fear", "")); yt = y[te]; mt = mon[te]
        dec = pred != ""; ok = dec & (pred == yt)
        bm = defaultdict(lambda: defaultdict(int))
        for mm, pr, yy in zip(mt, pred, yt):
            if yy != "other": bm[mm]["l_" + yy] += 1
            if pr: bm[mm]["k_" + pr] += 1
        err = np.mean([abs(v["k_greed"] / max(v["k_greed"] + v["k_fear"], 1) - v["l_greed"] / max(v["l_greed"] + v["l_fear"], 1)) for v in bm.values()])
        for k, v in (("decided", dec.mean()), ("acc", ok.sum() / dec.sum()), ("ratio_err", err)): res[name][k].append(float(v))
out = {k: {m: {"mean": float(np.mean(v)), "folds": v} for m, v in d.items()} for k, d in res.items()}
json.dump(out, open(f"{D}/eval_features_cv.json", "w"), ensure_ascii=False, indent=1)
for k, d in out.items():
    print(f"{k:10s} 판정 {d['decided']['mean']:.1%} | 정확도 {d['acc']['mean']:.1%} | 월별 비율 오차 {d['ratio_err']['mean']*100:.2f}%p  겹별 {[round(x*100,1) for x in d['ratio_err']['folds']]}")
a = np.array(out["(a) 지금"]["ratio_err"]["folds"])
for k in ["(b) A4", "(c) A5", "(d) A4+A5"]:
    b = np.array(out[k]["ratio_err"]["folds"]); print(f"  {k} − 지금: 겹별 {np.round((b - a) * 100, 1).tolist()}, 5겹 중 더 나은 겹 {(b < a).sum()}")
