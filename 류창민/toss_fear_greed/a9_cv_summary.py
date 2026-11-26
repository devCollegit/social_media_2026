"""A9 2단계: a9_fold0~4.json(KcELECTRA 5겹)을 모아 지금 모델(A4+A5, eval_features_cv.json · eval_a6_cv.json 의 (d))과 겹마다 비교 → a9_cv.json
기본 비교는 미리 정한 기준점 0.7. 0.8은 '정확도를 지금 모델과 맞췄을 때' 참고값."""
import json
import numpy as np
from featurize import D
F = [json.load(open(f"{D}/a9_fold{f}.json")) for f in range(5)]
assert [x["fold"] for x in F] == [0, 1, 2, 3, 4]
base = json.load(open(f"{D}/eval_features_cv.json"))["(d) A4+A5"]; base_dir = json.load(open(f"{D}/eval_a6_cv.json"))["(d) A4+A5"]["dir_acc"]["folds"]
M = ["decided", "acc", "dir_acc", "ratio_err"]
cur = {m: (base[m]["folds"] if m != "dir_acc" else base_dir) for m in M}
a9 = {m: [x["final_epoch3"][m] for x in F] for m in M}
a9_08 = {m: [x["thr_sweep"]["0.8"][m] for x in F] for m in M}
out = {"current": {m: {"mean": float(np.mean(v)), "folds": v} for m, v in cur.items()},
       "a9_thr0.7": {m: {"mean": float(np.mean(v)), "folds": v} for m, v in a9.items()},
       "a9_thr0.8": {m: {"mean": float(np.mean(v)), "folds": v} for m, v in a9_08.items()},
       "better_folds_ratio_err_0.7": int(sum(a < b for a, b in zip(a9["ratio_err"], cur["ratio_err"]))),
       "train_min_mean": float(np.mean([x["train_min"] for x in F]))}
json.dump(out, open(f"{D}/a9_cv.json", "w"), indent=1)
for k in ("current", "a9_thr0.7", "a9_thr0.8"):
    d = out[k]; print(f"{k:10s} 판정 {d['decided']['mean']:.1%} | 정확도 {d['acc']['mean']:.1%} | 방향 {d['dir_acc']['mean']:.1%} | 월별 비율 오차 {d['ratio_err']['mean']*100:.2f}%p  겹별 {[round(v*100, 1) for v in d['ratio_err']['folds']]}")
print("기준점 0.7에서 비율 오차가 지금보다 작은 겹:", out["better_folds_ratio_err_0.7"], "/ 5,  학습 평균", round(out["train_min_mean"], 1), "분")
