"""김동우 제안 A6 비교: 헷갈리는 글을 추가로 판정해 학습에 더하면 나아지나 (eval_features_cv.py 와 같은 5겹 나눔·채점).
채점은 원래 무작위 표본 29개 묶음으로만 한다. 추가 판정 글(a01~a05)은 골라 뽑은 글이라 채점에 넣지 않고 모든 겹의 학습에만 더한다.
비교: (d) A4+A5 (지금 최종) / (e) + A6 5,000건 전체 / (f) + A6 애매한 글 4,000건만
사용: uv run --python 3.10 --with scikit-learn==1.7.2 --with scipy --with kiwipiepy python eval_a6_cv.py"""
import json
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import numpy as np
from scipy.sparse import hstack, csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from featurize import D, clean
from extract_keywords import tokens_batch

posts = {r["id"]: r for f in ("sample_30k_clean.json", "sample_prev12_clean.json") for r in json.load(open(f"{D}/{f}"))}
SEL = json.load(open(f"{D}/a6_selection.json")); UNC = set(SEL["uncertain_ids"])
def month_of(ts):
    t = datetime.fromisoformat(ts) + timedelta(hours=9)
    if t.day >= 27: return f"{t.year}-{t.month:02d}"
    y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    return f"{y}-{m:02d}"
lab = lambda l: l if l in ("greed", "fear") else "other"
B = [f"b{i:02d}" for i in list(range(0, 23)) + list(range(31, 37))]
rows, y, grp = [], [], []
for gi_, b in enumerate(B):   # 원래 묶음: eval_features_cv.py 와 같은 5무리
    for line in open(f"{D}/labels/{b}.jsonl"):
        r = json.loads(line); rows.append(posts[r["id"]]); y.append(lab(r["label"])); grp.append(gi_ % 5)
n0 = len(rows); a6_raw = Counter()
for b in ["a01", "a02", "a03", "a04", "a05"]:   # 추가 판정: 무리 번호 -1 (채점 안 함)
    for line in open(f"{D}/labels/{b}.jsonl"):
        r = json.loads(line); rows.append(posts[r["id"]]); y.append(lab(r["label"])); grp.append(-1); a6_raw[r["label"]] += 1
y, grp = np.array(y), np.array(grp); mon = np.array([month_of(p["published_at"]) for p in rows])
is_a6 = grp == -1; is_unc = np.array([p["id"] in UNC for p in rows]) & is_a6
TX = [clean(p["text"]) for p in rows]; PX = [clean(p["parent_text"]) if p["is_reply"] and p["parent_text"] else "" for p in rows]
WX = tokens_batch(TX)
META = csr_matrix(np.array([[float(bool(p["is_reply"])), float(p["execution_side"] == "BUY"), float(p["execution_side"] == "SELL"), float(p["holding"] == "HOLDING")] for p in rows]))
CFG = {"(d) A4+A5": lambda f: (grp >= 0) & (grp != f), "(e) + A6 전체": lambda f: (grp != f), "(f) + A6 애매한 글만": lambda f: ((grp >= 0) & (grp != f)) | is_unc}
res = defaultdict(lambda: defaultdict(list))
for f in range(5):
    te = grp == f
    for name, trf in CFG.items():
        tr = trf(f)
        vt = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, sublinear_tf=True).fit([t for t, k in zip(TX, tr) if k])
        vp = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, sublinear_tf=True).fit([t for t, k in zip(PX, tr) if k])
        vw = TfidfVectorizer(analyzer=lambda s: list(s), min_df=3, sublinear_tf=True).fit([w for w, k in zip(WX, tr) if k])
        X = hstack([vt.transform(TX), 0.5 * vp.transform(PX), META, vw.transform(WX)]).tocsr()
        lr = LogisticRegression(C=2.0, class_weight="balanced", max_iter=4000).fit(X[tr], y[tr]); P = lr.predict_proba(X[te]); c = list(lr.classes_)
        pred = np.where(P[:, c.index("greed")] >= .7, "greed", np.where(P[:, c.index("fear")] >= .7, "fear", "")); yt = y[te]; mt = mon[te]
        dec = pred != ""; ok = dec & (pred == yt); opp = dec & (yt != "other") & (pred != yt)
        bm = defaultdict(lambda: defaultdict(int))
        for mm, pr, yy in zip(mt, pred, yt):
            if yy != "other": bm[mm]["l_" + yy] += 1
            if pr: bm[mm]["k_" + pr] += 1
        err = np.mean([abs(v["k_greed"] / max(v["k_greed"] + v["k_fear"], 1) - v["l_greed"] / max(v["l_greed"] + v["l_fear"], 1)) for v in bm.values()])
        for k, v in (("decided", dec.mean()), ("acc", ok.sum() / dec.sum()), ("dir_acc", ok.sum() / (ok.sum() + opp.sum())), ("ratio_err", err)): res[name][k].append(float(v))
        print(f, name, round(err * 100, 2), flush=True)
out = {k: {m: {"mean": float(np.mean(v)), "folds": v} for m, v in d.items()} for k, d in res.items()}
out["_a6_labels"] = dict(a6_raw); out["_a6_labels_uncertain"] = dict(Counter(y[is_unc])); out["_n_train_orig"] = int(n0); out["_n_a6"] = int(is_a6.sum())
json.dump(out, open(f"{D}/eval_a6_cv.json", "w"), ensure_ascii=False, indent=1)
for k, d in out.items():
    if k.startswith("_"): continue
    print(f"{k:22s} 판정 {d['decided']['mean']:.1%} | 정확도 {d['acc']['mean']:.1%} | 방향 {d['dir_acc']['mean']:.1%} | 월별 비율 오차 {d['ratio_err']['mean']*100:.2f}%p  겹별 {[round(x*100,1) for x in d['ratio_err']['folds']]}")
a = np.array(out["(d) A4+A5"]["ratio_err"]["folds"])
for k in ["(e) + A6 전체", "(f) + A6 애매한 글만"]:
    b = np.array(out[k]["ratio_err"]["folds"]); print(f"  {k} − (d): 겹별 {np.round((b - a) * 100, 2).tolist()}, 5겹 중 더 나은 겹 {(b < a).sum()}")
print("A6 라벨", out["_a6_labels"])
