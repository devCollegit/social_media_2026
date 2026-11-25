"""추가 판정할 글 고르기 (보완안 A6). 모델이 헷갈려 하는 글을, 글이 많은 종목에 더 많이 배정해 뽑는다.
뽑은 글은 류창민 make_batches.py와 같은 형식(1,000건 묶음)으로 내보낸다. 판정은 batch_task_active.md 절차로 Claude Code에서 한다.

고르는 기준
- 이미 판정한 글(sample_*_clean.json의 post_id)은 뺀다
- 후보 풀: 최근 --since 이후 글에서 종목마다 무작위로 뽑음
- 불확실도: 모델 확률 1위와 2위의 차이가 작을수록, 또는 탐욕·공포 확률이 0.4~0.7 사이일수록 우선
- 종목 배정: 실제 글 수 비율의 제곱근에 비례 (대형주를 더 보되 소형주도 남김)

입력 (--base): data/raw/posts/ (또는 예전 data/posts/), sample_*_clean.json, sectors.json / (--model) model_v2.joblib
출력 (--dest): sample_active_clean.json, batches/bNN.jsonl (번호는 --start부터, 기본 40), active_manifest.json
  → dest 폴더의 파일을 toss_fear_greed 폴더로 옮기고, 판정 결과를 labels/bNN.jsonl로 두면 train_v2.py가 함께 학습한다
사용: python make_active_batch.py --base <toss_fear_greed 폴더> --model v2_out/model_v2.joblib --dest v2_out/active --n 5000
"""
import argparse
import glob
import json
import os
import random
from collections import Counter
from datetime import datetime, timezone

import joblib
import numpy as np

from common import KST, MENTION, load_sectors, make_cleaner, posts_path, read_posts, stock_maps, write_json

P = argparse.ArgumentParser()
P.add_argument("--base", required=True)
P.add_argument("--model", required=True)
P.add_argument("--dest", default="v2_out/active")
P.add_argument("--n", type=int, default=5000)
P.add_argument("--pool-mult", type=int, default=6, help="최종 수의 몇 배를 후보로 볼지")
P.add_argument("--since", default="", help="이 날짜(YYYY-MM-DD) 이후 글만. 비우면 전체")
P.add_argument("--start", type=int, default=40, help="첫 묶음 번호")
P.add_argument("--seed", type=int, default=0)
A = P.parse_args()
random.seed(A.seed)
B = joblib.load(A.model)
CL = B["classes"]
SECT = load_sectors(A.base)
SECTOR, NAME = stock_maps(SECT)
clean = make_cleaner(SECT)
done = set()
for f in glob.glob(os.path.join(A.base, "sample_*_clean.json")):
    for r in json.load(open(f, encoding="utf-8")):
        done.add((r["stock_code"], str(r["post_id"])))

# 종목별 글 수 → 배정량
counts, files = {}, {}
for c in SECTOR:
    p = posts_path(A.base, c)
    if p:
        files[c] = p
        counts[c] = sum(1 for _ in read_posts(p))
w = {c: np.sqrt(n) for c, n in counts.items()}
quota = {c: max(5, round(A.n * w[c] / sum(w.values()))) for c in w}


def text_of(r, n):
    return MENTION.sub("@사용자", r["text"])[:n]


picked = []
for c, path in files.items():
    rows = [r for r in read_posts(path) if r["text"].strip() and (c, str(r["post_id"])) not in done
            and (not A.since or r["created_at"][:10] >= A.since)]
    parent = {r["post_id"]: r for r in rows if not r["parent_id"]}
    pool = random.sample(rows, min(len(rows), quota[c] * A.pool_mult))
    if not pool:
        continue
    txt = [clean(text_of(r, 400)) for r in pool]
    par = [clean(text_of(parent[r["parent_id"]], 300)) if r["parent_id"] in parent else "" for r in pool]
    if B["kind"] == "base3":
        pr = B["model"].predict_proba(B["vectorizer"].transform(txt))
    else:
        pr = B["model"].predict_proba(B["featurizer"].transform(txt, par, [bool(r["parent_id"]) for r in pool],
                                                                 [r["badge"] for r in pool], [r["is_holder"] for r in pool]))
    srt = np.sort(pr, 1)
    margin = srt[:, -1] - srt[:, -2]
    pg, pf = pr[:, CL.index("greed")], pr[:, CL.index("fear")]
    band = ((pg >= 0.4) & (pg < 0.7)) | ((pf >= 0.4) & (pf < 0.7))
    score = margin - 0.2 * band                     # 작을수록 먼저
    for j in np.argsort(score)[: quota[c]]:
        r = pool[j]
        pp = parent.get(r["parent_id"])
        picked.append({"sector": SECTOR[c], "stock_code": c, "stock_name": NAME[c], "post_id": r["post_id"],
                       "is_reply": bool(r["parent_id"]),
                       "published_at": datetime.fromisoformat(r["created_at"]).astimezone(timezone.utc).isoformat(),
                       "holding": "HOLDING" if r["is_holder"] else None, "execution_side": r["badge"],
                       "text": text_of(r, 400), "parent_text": text_of(pp, 300) if pp else None,
                       "_margin": float(margin[j]), "_pred": CL[int(pr[j].argmax())]})

random.shuffle(picked)
for i, r in enumerate(picked, 1):
    r["id"] = f"a{i:05d}"
os.makedirs(os.path.join(A.dest, "batches"), exist_ok=True)
KEEP = ["id", "stock_name", "is_reply", "execution_side", "text", "parent_text"]
names = []
for i in range(0, len(picked), 1000):
    b = f"b{A.start + i // 1000:02d}"
    names.append(b)
    with open(os.path.join(A.dest, "batches", f"{b}.jsonl"), "w", encoding="utf-8") as f:
        for r in picked[i:i + 1000]:
            f.write(json.dumps({k: r.get(k) for k in KEEP}, ensure_ascii=False) + "\n")
json.dump([{k: v for k, v in r.items() if not k.startswith("_")} for r in picked],
          open(os.path.join(A.dest, "sample_active_clean.json"), "w", encoding="utf-8"), ensure_ascii=False)
write_json(os.path.join(A.dest, "active_manifest.json"), {
    "made_at": datetime.now(KST).isoformat(timespec="seconds"), "n": len(picked), "batches": names, "model": B.get("name"),
    "by_stock": Counter(r["stock_name"] for r in picked), "model_pred_dist": Counter(r["_pred"] for r in picked),
    "mean_margin": float(np.mean([r["_margin"] for r in picked])), "reply_share": float(np.mean([r["is_reply"] for r in picked]))})
print(f"{len(picked):,}건 → {A.dest}/batches/{names[0]}~{names[-1]}.jsonl, sample_active_clean.json (평균 확률 차이 {np.mean([r['_margin'] for r in picked]):.2f})")
