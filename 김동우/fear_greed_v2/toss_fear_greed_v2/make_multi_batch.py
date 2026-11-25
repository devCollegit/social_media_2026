"""여러 축 판정(보완안 A8)용 묶음 만들기. 이미 탐욕·공포 판정을 받은 표본 글에서 뽑아, 같은 글에 감정·행동 의도·대상을 따로 붙인다.
기존 판정과 같은 글이어야 "공포 판정 글 중 실제 겁먹은 글은 몇 %인가"를 셀 수 있다.

뽑는 방법: 기존 라벨(탐욕·공포·중립·무관·애매)마다 같은 수를 목표로 뽑고(--n ÷ 5), 모자라면 다른 라벨에서 채운다.
대댓글과 매수·매도 인증 글이 섞이도록 종목·라벨 안에서 무작위로 고른다.

입력 (--base): sample_*_clean.json, labels/bNN.jsonl (류창민 make_batches.py·LLM 판정 형식)
출력 (--dest): batches/mNN.jsonl (500건 묶음), multi_manifest.json
  → 판정은 batch_task_multi.md 절차로 Claude Code에서. 결과는 <dest>/labels/mNN.jsonl
사용: python make_multi_batch.py --base <toss_fear_greed 폴더> --dest v2_out/multi --n 2000
"""
import argparse
import glob
import json
import os
import random
from collections import Counter, defaultdict
from datetime import datetime

from common import KST, LABELS5, MENTION, write_json

P = argparse.ArgumentParser()
P.add_argument("--base", required=True)
P.add_argument("--dest", default="v2_out/multi")
P.add_argument("--n", type=int, default=2000)
P.add_argument("--size", type=int, default=500, help="묶음 크기")
P.add_argument("--seed", type=int, default=0)
A = P.parse_args()
random.seed(A.seed)

posts = {}
for f in glob.glob(os.path.join(A.base, "sample_*_clean.json")):
    for r in json.load(open(f, encoding="utf-8")):
        posts[r["id"]] = r
label = {}
for f in glob.glob(os.path.join(A.base, "labels", "*.jsonl")):
    for line in open(f, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            if r["id"] in posts:
                label[r["id"]] = r["label"]
by = defaultdict(list)
for i, lab in label.items():
    by[lab].append(i)
for v in by.values():
    random.shuffle(v)
target = A.n // len(LABELS5)
picked = []
for lab in LABELS5:
    picked += by[lab][:target]
rest = [i for lab in LABELS5 for i in by[lab][target:]]
random.shuffle(rest)
picked += rest[: max(0, A.n - len(picked))]
random.shuffle(picked)

clip = lambda t, n: MENTION.sub("@사용자", t or "")[:n] if t else None
os.makedirs(os.path.join(A.dest, "batches"), exist_ok=True)
names = []
for k in range(0, len(picked), A.size):
    b = f"m{k // A.size:02d}"
    names.append(b)
    with open(os.path.join(A.dest, "batches", f"{b}.jsonl"), "w", encoding="utf-8") as f:
        for i in picked[k:k + A.size]:
            p = posts[i]
            f.write(json.dumps({"id": i, "stock_name": p.get("stock_name"), "is_reply": p.get("is_reply"),
                                "execution_side": p.get("execution_side"), "text": clip(p.get("text"), 400),
                                "parent_text": clip(p.get("parent_text"), 300)}, ensure_ascii=False) + "\n")
write_json(os.path.join(A.dest, "multi_manifest.json"), {
    "made_at": datetime.now(KST).isoformat(timespec="seconds"), "n": len(picked), "batches": names,
    "by_label": Counter(label[i] for i in picked), "reply_share": sum(bool(posts[i].get("is_reply")) for i in picked) / max(len(picked), 1),
    "badge_share": sum(bool(posts[i].get("execution_side")) for i in picked) / max(len(picked), 1)})
print(f"{len(picked):,}건 → {A.dest}/batches/{names[0]}~{names[-1]}.jsonl (기존 라벨별 {dict(Counter(label[i] for i in picked))})")
