"""묶음 판정 결과 검사: 줄 수, id 일치·순서, 라벨 값. 사용: python3 check_batch.py b04 [b05 ...] (인자 없으면 전체)"""
import json, sys, os, glob, collections
D = os.path.dirname(os.path.abspath(__file__))
OK = {"greed", "fear", "neutral", "irrelevant", "unsure"}
names = sys.argv[1:] or sorted(os.path.basename(p)[:-6] for p in glob.glob(f"{D}/batches/*.jsonl"))
for b in names:
    ids = [json.loads(l)["id"] for l in open(f"{D}/batches/{b}.jsonl")]
    p = f"{D}/labels/{b}.jsonl"
    if not os.path.exists(p):
        print(b, "결과 없음"); continue
    got, bad = [], 0
    for l in open(p):
        l = l.strip()
        if not l: continue
        try:
            d = json.loads(l); got.append(d["id"]); bad += d["label"] not in OK
        except Exception:
            bad += 1
    c = collections.Counter(json.loads(l)["label"] for l in open(p) if l.strip())
    status = "OK" if got == ids and bad == 0 else f"문제: 입력 {len(ids)} / 결과 {len(got)} / 빠진 {len(set(ids)-set(got))} / 남는 {len(set(got)-set(ids))} / 잘못된 줄 {bad}"
    print(b, status, dict(c))
