"""v2 분류 모델 학습·비교 (보완안 A1~A5, 모델 표 1·2번).
기준선은 류창민 train_final.py와 같은 모델(본문 글자 조각 TF-IDF + 로지스틱 회귀, 탐욕/공포/그 외 3분류, 0.7 기준)이다.
같은 채점 묶음으로 v2 후보를 비교하고, 고른 모델을 전체 판정으로 다시 학습해 저장한다.

입력 (--base): sample_*_clean.json (sample_30k, sample_prev12, 추가 판정 sample_active), labels/bNN.jsonl, sectors.json, data/raw/posts/(있으면 종목별 글 수 가중에 사용)
출력 (--out): model_v2.joblib, quantify.json, reports/train_report.{json,md}
사용: python train_v2.py --base <toss_fear_greed 폴더> --out v2_out [--holdout "b17-b22"] [--choose v2_lr5_cal]
"""
import argparse
import glob
import json
import os
from collections import Counter, defaultdict

import joblib
import numpy as np
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.svm import LinearSVC

from common import LABELS5, batches, load_sectors, make_cleaner, month_of, posts_path, write_json
from featurize_v2 import Featurizer

P = argparse.ArgumentParser()
P.add_argument("--base", required=True)
P.add_argument("--out", default="v2_out")
P.add_argument("--holdout", default="", help="채점 묶음. 비우면 b17-b22가 있으면 그것, 없으면 최근 1년 묶음의 마지막 20%%")
P.add_argument("--choose", default="v2_lr5_cal", help="저장할 모델 이름. auto면 달별 탐욕 비율 오차(확률 합)가 가장 작은 v2 모델")
P.add_argument("--threshold", type=float, default=0.7)
P.add_argument("--no-words", action="store_true")
A = P.parse_args()
os.makedirs(f"{A.out}/reports", exist_ok=True)

SECT = load_sectors(A.base)
clean = make_cleaner(SECT)
posts = {}
for p in sorted(glob.glob(os.path.join(A.base, "sample_*_clean.json"))):   # 기존 표본 + 추가 판정 표본(sample_active_clean.json)
    for r in json.load(open(p, encoding="utf-8")):
        posts[r["id"]] = r
lab_dir = os.path.join(A.base, "labels")
all_b = batches("all", lab_dir)
recent_b = [b for b in all_b if int(b[1:]) <= 30]
if A.holdout:
    hold_b = batches(A.holdout)
elif all(f"b{i}" in all_b for i in range(17, 23)):
    hold_b = batches("b17-b22")
else:
    k = max(1, round(len(recent_b) * 0.2))
    hold_b = recent_b[-k:]
train_b = [b for b in all_b if b not in hold_b]


def load(bs):
    rows = []
    for b in bs:
        for line in open(os.path.join(lab_dir, f"{b}.jsonl"), encoding="utf-8"):
            r = json.loads(line)
            p = posts.get(r["id"])
            if p is None or r["label"] not in LABELS5:
                continue
            rows.append({**p, "label": r["label"]})
    return rows


TR, HO = load(train_b), load(hold_b)
print(f"학습 {len(TR):,}건 ({train_b[0]}~{train_b[-1]}, {len(train_b)}묶음) / 채점 {len(HO):,}건 ({', '.join(hold_b)})")


def cols(rows):
    return ([clean(r["text"]) for r in rows], [clean(r.get("parent_text") or "") for r in rows],
            [bool(r.get("is_reply")) for r in rows], [r.get("execution_side") for r in rows], [r.get("holding") for r in rows])


y5_tr = np.array([r["label"] for r in TR])
y5_ho = np.array([r["label"] for r in HO])
to3 = np.vectorize(lambda x: x if x in ("greed", "fear") else "other")
y3_tr, y3_ho = to3(y5_tr), to3(y5_ho)
months_ho = np.array([month_of(r["published_at"]) for r in HO])
reply_ho = np.array([bool(r.get("is_reply")) for r in HO])
stock_ho = np.array([r["stock_code"] for r in HO])

# 종목별 실제 글 수 (글이 몰린 종목의 성능을 따로 보기 위해)
vol = {}
for c in {r["stock_code"] for r in TR + HO}:
    p = posts_path(A.base, c)
    if p:
        vol[c] = sum(1 for _ in open(p, encoding="utf-8"))

# ---------------- 후보 모델 ----------------
Xtr_c, Ptr, Rtr, Str, Htr = cols(TR)
Xho_c, Pho, Rho, Sho, Hho = cols(HO)
cands = {}

v = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, sublinear_tf=True)
lr = LogisticRegression(C=2.0, class_weight="balanced", max_iter=3000).fit(v.fit_transform(Xtr_c), y3_tr)
cands["base3"] = {"desc": "기준선: 본문 글자 TF-IDF + LR, 3분류 (류창민 train_final.py와 같음)",
                  "proba": lr.predict_proba(v.transform(Xho_c)), "classes": [str(x) for x in lr.classes_]}


def fit_v2(name, desc, est, **fz):
    F = Featurizer(use_words=not A.no_words, **fz)
    Xtr = F.fit_transform(Xtr_c, Ptr, Rtr, Str, Htr)
    m = est.fit(Xtr, y5_tr)
    cands[name] = {"desc": desc, "proba": m.predict_proba(F.transform(Xho_c, Pho, Rho, Sho, Hho)),
                   "classes": [str(x) for x in m.classes_], "features": F.describe(), "_fz": fz, "_est": clone(est)}


LR5 = lambda: LogisticRegression(C=2.0, class_weight="balanced", max_iter=3000)
fit_v2("v2_lr5", "v2 특징 전부 + LR, 5분류", LR5())
fit_v2("v2_lr5_cal", "v2 특징 전부 + LR + 확률 보정(sigmoid, 5겹), 5분류", CalibratedClassifierCV(LR5(), method="sigmoid", cv=5))
fit_v2("v2_svm5_cal", "v2 특징 전부 + LinearSVC + 확률 보정, 5분류",
       CalibratedClassifierCV(LinearSVC(C=0.3, class_weight="balanced"), method="sigmoid", cv=5))
fit_v2("v2_lr5_noctx", "본문 글자+단어만 (부모 글·메타 제외) + LR 보정, 5분류",
       CalibratedClassifierCV(LR5(), method="sigmoid", cv=5), use_parent=False, use_meta=False)


# ---------------- 채점 ----------------
def ece(p, y, bins=10):
    idx = np.minimum((p * bins).astype(int), bins - 1)
    return float(sum(abs(p[idx == b].mean() - y[idx == b].mean()) * (idx == b).mean() for b in range(bins) if (idx == b).any()))


def greed_share(g, f):
    return g / (g + f) if (g + f) > 0 else np.nan


def evaluate(c):
    P_, cl = c["proba"], c["classes"]
    pg, pf = P_[:, cl.index("greed")], P_[:, cl.index("fear")]
    out = {"desc": c["desc"]}
    am = np.array(cl)[P_.argmax(1)]
    am3 = to3(am)
    out["acc3_argmax"] = float(accuracy_score(y3_ho, am3))
    out["macroF1_3"] = float(f1_score(y3_ho, am3, average="macro"))
    if "neutral" in cl:
        out["acc5"] = float(accuracy_score(y5_ho, am))
        out["macroF1_5"] = float(f1_score(y5_ho, am, average="macro"))
    hard = np.where(pg >= A.threshold, "greed", np.where(pf >= A.threshold, "fear", ""))
    dec = hard != ""
    out["decided_share_at_thr"] = float(dec.mean())
    out["acc_decided_at_thr"] = float((hard[dec] == y3_ho[dec]).mean()) if dec.any() else None
    out["ece_greed"], out["ece_fear"] = ece(pg, (y5_ho == "greed").astype(float)), ece(pf, (y5_ho == "fear").astype(float))
    errs_hard, errs_prob = [], []
    for m in sorted(set(months_ho)):
        s = months_ho == m
        truth = greed_share((y5_ho[s] == "greed").sum(), (y5_ho[s] == "fear").sum())
        errs_hard.append(abs(greed_share((hard[s] == "greed").sum(), (hard[s] == "fear").sum()) - truth))
        errs_prob.append(abs(greed_share(pg[s].sum(), pf[s].sum()) - truth))
    out["month_greed_share_mae_hard"] = float(np.nanmean(errs_hard))
    out["month_greed_share_mae_prob"] = float(np.nanmean(errs_prob))
    out["acc3_reply"] = float(accuracy_score(y3_ho[reply_ho], am3[reply_ho])) if reply_ho.any() else None
    out["acc3_original"] = float(accuracy_score(y3_ho[~reply_ho], am3[~reply_ho]))
    per = {s: float(accuracy_score(y3_ho[stock_ho == s], am3[stock_ho == s])) for s in sorted(set(stock_ho))}
    out["acc3_stock_uniform"] = float(np.mean(list(per.values())))
    if vol:
        w = np.array([vol.get(s, 0) for s in per])
        out["acc3_stock_volume_weighted"] = float(np.average(list(per.values()), weights=w)) if w.sum() else None
    return out


R = {"train_batches": train_b, "holdout_batches": hold_b, "n_train": len(TR), "n_holdout": len(HO),
     "label_dist_holdout": dict(Counter(y5_ho)), "threshold": A.threshold, "models": {}}
for k, c in cands.items():
    R["models"][k] = evaluate(c)
    print(k, {a: (round(b, 3) if isinstance(b, float) else b) for a, b in R["models"][k].items() if a != "desc"})

# ---------------- 보정 집계(PACC) 계수: 채점 묶음에서 잰 클래스별 평균 확률 ----------------
choose = A.choose
if choose == "auto":
    choose = min((k for k in cands if k.startswith("v2")), key=lambda k: R["models"][k]["month_greed_share_mae_prob"])
c = cands[choose]
cl = c["classes"]
Q = {}
for lab in ("greed", "fear", "irrelevant"):
    if lab not in cl:
        continue
    p = c["proba"][:, cl.index(lab)]
    pos = y5_ho == lab
    Q[lab] = {"tpr": float(p[pos].mean()), "fpr": float(p[~pos].mean()), "n_pos": int(pos.sum())}


def pacc(mean_p, q):
    d = q["tpr"] - q["fpr"]
    return float(np.clip((mean_p - q["fpr"]) / d, 0, 1)) if d > 0.05 else float(mean_p)


errs = []
for m in sorted(set(months_ho)):
    s = months_ho == m
    truth = greed_share((y5_ho[s] == "greed").sum(), (y5_ho[s] == "fear").sum())
    g = pacc(c["proba"][s, cl.index("greed")].mean(), Q["greed"])
    f = pacc(c["proba"][s, cl.index("fear")].mean(), Q["fear"])
    errs.append(abs(greed_share(g, f) - truth))
R["models"][choose]["month_greed_share_mae_pacc"] = float(np.nanmean(errs))
R["chosen"] = choose
R["quantify"] = Q
write_json(f"{A.out}/quantify.json", {"model": choose, "params": Q, "note": "채점 묶음 기준. apply/build_index_v2의 PACC 보정에 쓴다"})

# ---------------- 최종 모델: 전체 판정으로 다시 학습 ----------------
ALL = TR + HO
Xa, Pa, Ra, Sa, Ha = cols(ALL)
ya = np.array([r["label"] for r in ALL])
if choose == "base3":
    vf = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, sublinear_tf=True)
    m = LogisticRegression(C=2.0, class_weight="balanced", max_iter=3000).fit(vf.fit_transform(Xa), to3(ya))
    bundle = {"kind": "base3", "vectorizer": vf, "model": m}
else:
    F = Featurizer(use_words=not A.no_words, **c["_fz"])
    est = clone(c["_est"])
    m = est.fit(F.fit_transform(Xa, Pa, Ra, Sa, Ha), ya)
    bundle = {"kind": "v2", "featurizer": F, "model": m}
bundle.update({"name": choose, "classes": [str(x) for x in m.classes_], "threshold": A.threshold, "trained_on": len(ALL)})
joblib.dump(bundle, f"{A.out}/model_v2.joblib")
write_json(f"{A.out}/reports/train_report.json", R)

# ---------------- 보고서 ----------------
fmt = lambda x: "—" if x is None else (f"{x:.1%}" if isinstance(x, float) and x <= 1 else str(x))
L = [f"# 분류 모델 비교 ({len(TR):,}건 학습 / {len(HO):,}건 채점)", "",
     f"채점 묶음: {', '.join(hold_b)} · 기준점 {A.threshold} · 정답 = LLM 판정 · 저장한 모델: **{choose}**", "",
     "| 모델 | 3분류 정확도 | 3분류 macro-F1 | 5분류 macro-F1 | 기준점 판정 비율 | 판정분 정확도 | 달별 탐욕비율 오차(판정 수) | 달별 탐욕비율 오차(확률 합) | 탐욕 확률 보정오차 | 대댓글 정확도 | 원글 정확도 | 종목 글 수 가중 정확도 |",
     "|---|---|---|---|---|---|---|---|---|---|---|---|"]
for k, r in R["models"].items():
    L.append(f"| {k} | {fmt(r['acc3_argmax'])} | {fmt(r['macroF1_3'])} | {fmt(r.get('macroF1_5'))} | {fmt(r['decided_share_at_thr'])} | "
             f"{fmt(r['acc_decided_at_thr'])} | {r['month_greed_share_mae_hard']*100:.1f}%p | {r['month_greed_share_mae_prob']*100:.1f}%p | "
             f"{r['ece_greed']:.3f} | {fmt(r['acc3_reply'])} | {fmt(r['acc3_original'])} | {fmt(r.get('acc3_stock_volume_weighted'))} |")
L += ["", f"보정 집계(PACC) 적용 시 {choose}의 달별 탐욕비율 오차: {R['models'][choose]['month_greed_share_mae_pacc']*100:.1f}%p", "",
      "모델 설명", ""] + [f"- **{k}**: {r['desc']}" for k, r in R["models"].items()]
open(f"{A.out}/reports/train_report.md", "w", encoding="utf-8").write("\n".join(L) + "\n")
print(f"저장: {A.out}/model_v2.joblib ({choose}), quantify.json, reports/train_report.md")
