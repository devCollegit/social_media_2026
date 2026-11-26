"""김동우 제안 A6: 헷갈리는 글만 골라 추가 판정. 원래 표본(5.9만) 중 아직 판정하지 않은 글에서 고른다 (형식·전처리가 학습 글과 같음).
① 애매한 글 4,000건: 지금 모델(model_v2)의 탐욕 또는 공포 확률이 0.4 이상 0.7 미만 (기준점 0.7 바로 아래)
② 글 많은 종목 1,000건: 삼성전자 · SK하이닉스 각 500건 무작위 (①과 겹치지 않게)
섞어서 1,000건씩 batches/a01~a05.jsonl (필드는 기존 묶음과 같음). 선택 기록: a6_selection.json
사용: uv run --python 3.10 --with scikit-learn==1.7.2 --with joblib --with scipy --with kiwipiepy python make_a6_batches.py"""
import json, glob, random
from collections import Counter
import joblib, numpy as np
from featurize import D
from train_final2 import features, _ident   # 모델 안 단어 분석기(_ident)를 불러오기 위해 필요

random.seed(20261125)
posts = {r["id"]: r for f in ("sample_30k_clean.json", "sample_prev12_clean.json") for r in json.load(open(f"{D}/{f}"))}
done = {json.loads(l)["id"] for f in glob.glob(f"{D}/labels/*.jsonl") for l in open(f)}
pool = [p for i, p in posts.items() if i not in done]
M = joblib.load(f"{D}/model_v2.joblib"); LR = M["model"]; c = list(LR.classes_); GI, FI = c.index("greed"), c.index("fear")
X = features(M, [p["text"] for p in pool], [p["parent_text"] if p["is_reply"] and p["parent_text"] else "" for p in pool],
             [p["is_reply"] for p in pool], [p["execution_side"] or "" for p in pool], [p["holding"] == "HOLDING" for p in pool])
P = LR.predict_proba(X); top = np.maximum(P[:, GI], P[:, FI])
band = [p for p, t in zip(pool, top) if 0.4 <= t < 0.7]
pick1 = random.sample(band, 4000); s1 = {p["id"] for p in pick1}
pick2 = []
for name in ("삼성전자", "SK하이닉스"):
    pick2 += random.sample([p for p in pool if p["stock_name"] == name and p["id"] not in s1], 500)
picked = pick1 + pick2; random.shuffle(picked)
KEYS = ["id", "stock_name", "is_reply", "execution_side", "text", "parent_text"]
for b in range(5):
    with open(f"{D}/batches/a{b + 1:02d}.jsonl", "w") as f:
        for p in picked[b * 1000:(b + 1) * 1000]: f.write(json.dumps({k: p[k] for k in KEYS}, ensure_ascii=False) + "\n")
info = {"pool": len(pool), "band_0.4_0.7": len(band), "decided_in_pool": float((top >= 0.7).mean()), "pick_uncertain": len(pick1), "pick_bigstock": len(pick2),
        "uncertain_ids": sorted(s1), "bigstock_ids": sorted(p["id"] for p in pick2),
        "year": dict(Counter(p["published_at"][:4] for p in picked)), "reply_share": float(np.mean([p["is_reply"] for p in picked]))}
json.dump(info, open(f"{D}/a6_selection.json", "w"), ensure_ascii=False)
print({k: v for k, v in info.items() if not k.endswith("_ids")})
