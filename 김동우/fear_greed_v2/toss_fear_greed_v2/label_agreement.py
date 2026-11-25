"""두 판정의 일치도 (보완안 A7). 같은 묶음을 서로 다른 에이전트(또는 Haiku와 상위 모델)가 판정한 결과를 비교한다.
사람 정답이 없을 때 라벨 품질의 하한을 가늠하는 용도다. 갈린 글은 상위 모델 재판정용 묶음으로 내보낸다.

입력: --a, --b 판정 폴더(labels 형식: bNN.jsonl, 한 줄에 {"id", "label"}), --samples 표본 파일들(갈린 글 재판정 묶음을 만들 때)
출력 (--out): agreement_report.json, agreement_report.md, adjudicate.jsonl(갈린 글, make_batches.py 형식)
사용: python label_agreement.py --a labels --b labels_recheck --batches "b17-b22" --samples sample_30k_clean.json --out v2_out/agreement
"""
import argparse
import json
import os
from collections import Counter

import pandas as pd
from sklearn.metrics import cohen_kappa_score

from common import LABELS5, batches, write_json

P = argparse.ArgumentParser()
P.add_argument("--a", required=True)
P.add_argument("--b", required=True)
P.add_argument("--batches", default="all")
P.add_argument("--samples", nargs="*", default=[])
P.add_argument("--out", default="v2_out/agreement")
A = P.parse_args()


def load(d, bs):
    out = {}
    for b in bs:
        p = os.path.join(d, f"{b}.jsonl")
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                if line.strip():
                    r = json.loads(line)
                    out[r["id"]] = r["label"]
    return out


bs = batches(A.batches, A.a)
a, b = load(A.a, bs), load(A.b, bs)
ids = sorted(set(a) & set(b))
ya, yb = [a[i] for i in ids], [b[i] for i in ids]
to3 = lambda x: x if x in ("greed", "fear") else "other"
R = {"batches": bs, "n_a": len(a), "n_b": len(b), "n_common": len(ids),
     "agree5": sum(x == y for x, y in zip(ya, yb)) / max(len(ids), 1),
     "kappa5": float(cohen_kappa_score(ya, yb)) if ids else None,
     "agree3": sum(to3(x) == to3(y) for x, y in zip(ya, yb)) / max(len(ids), 1),
     "kappa3": float(cohen_kappa_score([to3(x) for x in ya], [to3(y) for y in yb])) if ids else None,
     "opposite_greed_fear": sum({x, y} == {"greed", "fear"} for x, y in zip(ya, yb)),
     "dist_a": Counter(ya), "dist_b": Counter(yb)}
cm = pd.crosstab(pd.Series(ya, name="A"), pd.Series(yb, name="B")).reindex(index=LABELS5, columns=LABELS5, fill_value=0)
R["confusion"] = cm.to_dict()
os.makedirs(A.out, exist_ok=True)
write_json(os.path.join(A.out, "agreement_report.json"), R)
post = {}
for f in A.samples:
    for r in json.load(open(f, encoding="utf-8")):
        post[r["id"]] = r
dis = [i for i in ids if a[i] != b[i]]
with open(os.path.join(A.out, "adjudicate.jsonl"), "w", encoding="utf-8") as f:
    for i in dis:
        p = post.get(i)
        if p:
            f.write(json.dumps({k: p.get(k) for k in ["id", "stock_name", "is_reply", "execution_side", "text", "parent_text"]}, ensure_ascii=False) + "\n")
L = [f"# 판정 일치도 ({len(ids):,}건)", "", f"- 5개 라벨 일치 {R['agree5']:.1%}, Cohen κ {R['kappa5']:.2f}",
     f"- 탐욕/공포/그 외 일치 {R['agree3']:.1%}, κ {R['kappa3']:.2f}", f"- 탐욕↔공포 정반대 판정 {R['opposite_greed_fear']}건",
     f"- 갈린 글 {len(dis)}건 → adjudicate.jsonl (상위 모델 재판정용)", "", "혼동표 (행 = A, 열 = B)", "", "```", cm.to_string(), "```"]
open(os.path.join(A.out, "agreement_report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L))
