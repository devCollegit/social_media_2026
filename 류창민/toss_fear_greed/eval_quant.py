"""김동우 제안 A1·A2·A3·B1 비교 실험. 학습: b00~b16 + b31~b33, 채점: b17~b22 + b34~b36 (두 해 모두).
비교: (a) 지금 방식 — 3분류 LR, 확률 0.7 이상만 개수 세기
      (b) A1 — 3분류 확률 그대로 합산
      (c) A1+A2+A3 — 5분류 + 확률 보정(시그모이드, 5겹) 합산, 무관은 분모에서 뺌
      (d) A1+A2+A3+B1 — (c)에 보정 집계(PACC: 교차검증으로 잰 '실제 라벨별 평균 확률' 행렬로 비율을 역산)
채점(월 단위, LLM 판정을 정답으로): ① 탐욕 비율 g/(g+f) 오차 ② 순심리 (g−f)/(무관 뺀 글 수) 오차
사용: uv run --python 3.10 --with scikit-learn==1.7.2 --with scipy python eval_quant.py"""
import json, os
from collections import defaultdict
import numpy as np
from scipy.optimize import nnls
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import cross_val_predict, StratifiedKFold
from featurize import D, clean
from datetime import datetime, timedelta

L5 = ["greed", "fear", "neutral", "irrelevant", "unsure"]
posts = {r["id"]: r for f in ("sample_30k_clean.json", "sample_prev12_clean.json") for r in json.load(open(f"{D}/{f}"))}
def month_of(ts):
    t = datetime.fromisoformat(ts) + timedelta(hours=9)
    if t.day >= 27: return f"{t.year}-{t.month:02d}"
    y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    return f"{y}-{m:02d}"
def load(bs):
    X, y, m = [], [], []
    for b in bs:
        for line in open(f"{D}/labels/{b}.jsonl"):
            r = json.loads(line); p = posts[r["id"]]; X.append(clean(p["text"])); y.append(r["label"]); m.append(month_of(p["published_at"]))
    return X, np.array(y), np.array(m)
bl = lambda a, b: [f"b{i:02d}" for i in range(a, b + 1)]
Xtr, ytr, _ = load(bl(0, 16) + bl(31, 33)); Xte, yte, mte = load(bl(17, 22) + bl(34, 36))
vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, sublinear_tf=True)
A = vec.fit_transform(Xtr); At = vec.transform(Xte)
y3 = lambda y: np.where(np.isin(y, ["greed", "fear"]), y, "other")
lr3 = LogisticRegression(C=2.0, class_weight="balanced", max_iter=3000).fit(A, y3(ytr)); P3 = lr3.predict_proba(At); c3 = list(lr3.classes_)
base5 = LogisticRegression(C=2.0, class_weight="balanced", max_iter=3000)
cal = CalibratedClassifierCV(base5, method="sigmoid", cv=5).fit(A, ytr); P5 = cal.predict_proba(At); c5 = list(cal.classes_)
P5 = P5[:, [c5.index(l) for l in L5]]
# B1: 학습 데이터 교차검증 확률로 M[i,j] = E[예측확률 i | 실제 j]
cvp = cross_val_predict(CalibratedClassifierCV(LogisticRegression(C=2.0, class_weight="balanced", max_iter=3000), method="sigmoid", cv=5),
                        A, ytr, cv=StratifiedKFold(5, shuffle=True, random_state=0), method="predict_proba")
cvp = cvp[:, [sorted(L5).index(l) for l in L5]]
M = np.column_stack([cvp[ytr == l].mean(0) for l in L5])
def pacc(q):   # q: 평균 예측확률(5) → 실제 비율 추정(합 1, 음수 없음)
    Aug = np.vstack([M, np.ones(5) * 10]); b = np.append(q, 10)
    p, _ = nnls(Aug, b); return p / p.sum()

res = defaultdict(lambda: defaultdict(list))
for mm in sorted(set(mte)):
    s = mte == mm; yt = yte[s]; n = s.sum()
    tg, tf, ti = (yt == "greed").sum(), (yt == "fear").sum(), (yt == "irrelevant").sum()
    truth = (tg / max(tg + tf, 1), (tg - tf) / (n - ti))
    est = {}
    gi, fi = c3.index("greed"), c3.index("fear")
    pred = np.where(P3[s, gi] >= .7, "g", np.where(P3[s, fi] >= .7, "f", ""))
    g, f = (pred == "g").sum(), (pred == "f").sum(); est["(a) 지금: 0.7 개수"] = (g / max(g + f, 1), (g - f) / n)
    g, f = P3[s, gi].sum(), P3[s, fi].sum(); est["(b) A1 확률 합산"] = (g / (g + f), (g - f) / n)
    q = P5[s].sum(0); est["(c) A1+A2+A3"] = (q[0] / (q[0] + q[1]), (q[0] - q[1]) / (n - q[3]))
    p = pacc(P5[s].mean(0)); est["(d) +B1 보정 집계"] = (p[0] / (p[0] + p[1]), (p[0] - p[1]) / (1 - p[3]))
    for k, (r1, r2) in est.items():
        res[k]["ratio"].append(abs(r1 - truth[0])); res[k]["net"].append(abs(r2 - truth[1])); res[k]["net_signed"].append(r2 - truth[1])
out = {k: {"ratio_err": float(np.mean(v["ratio"])), "net_err": float(np.mean(v["net"])), "net_bias": float(np.mean(v["net_signed"]))} for k, v in res.items()}
out["_n_test"] = int(len(yte)); out["_months"] = int(len(set(mte)))
# 5분류 보정 확률의 질: 확률 0.7 근처 글이 실제로 70% 맞나 (탐욕 기준)
pg = P5[:, 0]; bins = np.digitize(pg, [.2, .4, .6, .8]); out["_calib_greed"] = [{"bin": int(b), "mean_p": float(pg[bins == b].mean()), "actual": float((yte[bins == b] == "greed").mean()), "n": int((bins == b).sum())} for b in range(5)]
json.dump(out, open(f"{D}/eval_quant.json", "w"), ensure_ascii=False, indent=1)
for k, v in out.items():
    if not k.startswith("_"): print(f"{k:20s} 탐욕비율 오차 {v['ratio_err']*100:.1f}%p | 순심리 오차 {v['net_err']:.3f} (치우침 {v['net_bias']:+.3f})")
print("채점", out["_n_test"], "건,", out["_months"], "개월"); print("보정 확인(탐욕):", [(round(c["mean_p"], 2), round(c["actual"], 2), c["n"]) for c in out["_calib_greed"]])

# 큰 묶음으로도: 분기·전체 단위 (표본이 커질 때 보정 집계의 치우침 감소 효과 확인)
def quarter(m): y, mo = m.split("-"); return f"{y}Q{(int(mo) - 1) // 3 + 1}"
for unit, keyf in (("분기", quarter), ("전체", lambda m: "all")):
    acc = defaultdict(list)
    for key in sorted({keyf(m) for m in mte}):
        s = np.array([keyf(m) == key for m in mte]); yt = yte[s]; n = s.sum()
        tg, tf, ti = (yt == "greed").sum(), (yt == "fear").sum(), (yt == "irrelevant").sum(); truth = (tg / (tg + tf), (tg - tf) / (n - ti))
        gi, fi = c3.index("greed"), c3.index("fear")
        pred = np.where(P3[s, gi] >= .7, "g", np.where(P3[s, fi] >= .7, "f", "")); g, f = (pred == "g").sum(), (pred == "f").sum()
        e = {"(a)": (g / (g + f), (g - f) / n)}
        g, f = P3[s, gi].sum(), P3[s, fi].sum(); e["(b)"] = (g / (g + f), (g - f) / n)
        q = P5[s].sum(0); e["(c)"] = (q[0] / (q[0] + q[1]), (q[0] - q[1]) / (n - q[3]))
        p = pacc(P5[s].mean(0)); e["(d)"] = (p[0] / (p[0] + p[1]), (p[0] - p[1]) / (1 - p[3]))
        for k, (r1, r2) in e.items(): acc[k].append((abs(r1 - truth[0]), r2 - truth[1]))
        if unit == "전체": print("  정답 순심리", round(truth[1], 3), {k: round(v[1], 3) for k, v in e.items()}); out["_pooled_net"] = {"truth": float(truth[1]), **{k: float(v[1]) for k, v in e.items()}}
    out[f"_{unit}"] = {k: {"ratio_err": float(np.mean([a for a, _ in v])), "net_bias": float(np.mean([b for _, b in v]))} for k, v in acc.items()}
    print(unit, {k: f"비율오차 {np.mean([a for a, _ in v])*100:.1f}%p, 순심리 치우침 {np.mean([b for _, b in v]):+.3f}" for k, v in acc.items()})

json.dump(out, open(f"{D}/eval_quant.json", "w"), ensure_ascii=False, indent=1)
