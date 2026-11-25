"""최종 모델 v2(A4+A5, train_final2.py → model_v2.joblib)를 전체 글(data/raw/posts/<stock_id>.csv, 김정기 수집기 형식 — make_sample.py 설명 참고)에 적용 -> 종목·30분(KST)별 집계. 원문은 저장하지 않음.
출력: apply_out3/<종목코드>_<YYYY-MM>.csv — apply_out2 와 같은 열(slot_kst, n_posts, n_greed, n_fear, n_kw_greed, n_kw_fear)
  + B5 행동 축: n_buy, n_sell(매수·매도 인증 글 수), n_holder(보유자 글 수), h_greed, h_fear(보유자 글 중 탐욕·공포)
한 달 = 전월 27일 ~ 당월 27일 전. 본문 400자, 부모 글 300자까지 (학습 표본과 같은 길이).
사용: python apply_all3.py [종목코드]   (apply_out3_meta.json에 처리 건수·시간 기록)"""
import csv, json, os, sys, time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import joblib, numpy as np
from featurize import D, THRESHOLD, MENTION, clean
from extract_keywords import tokens_batch
from train_final2 import features, _ident   # 모델 안 단어 분석기(_ident)를 불러오기 위해 필요

csv.field_size_limit(10 ** 8)
KST = timezone(timedelta(hours=9))
POSTS = os.path.join(D, "data", "raw", "posts"); OUT = f"{D}/apply_out3"; os.makedirs(OUT, exist_ok=True)
LEX = [k for k in json.load(open(f"{D}/lexicon_all29k.json"))["keywords"] if k["precision"] >= 0.8]
KW_G = {k["word"] for k in LEX if k["side"] == "greed"}; KW_F = {k["word"] for k in LEX if k["side"] == "fear"}
M = joblib.load(f"{D}/model_v2.joblib"); LR = M["model"]; GI, FI = list(LR.classes_).index("greed"), list(LR.classes_).index("fear")
STOCKS = [c for v in json.load(open(f"{D}/sectors.json")).values() for c in v]
COLS = ["slot_kst", "n_posts", "n_greed", "n_fear", "n_kw_greed", "n_kw_fear", "n_buy", "n_sell", "n_holder", "h_greed", "h_fear"]

def month_key(t):
    if t.day >= 27: return f"{t.year}-{t.month:02d}"
    y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    return f"{y}-{m:02d}"
slot = lambda t: t.strftime("%Y-%m-%dT%H:") + ("30" if t.minute >= 30 else "00")

only = sys.argv[1] if len(sys.argv) > 1 else None
t0 = time.time(); total = 0
for code in STOCKS:
    if only and code != only: continue
    rows = list(csv.DictReader(open(f"{POSTS}/{code}.csv", encoding="utf-8")))
    parent = {r["post_id"]: r["text"] for r in rows if not r["parent_id"]}
    by_month = defaultdict(list); seen = set()
    for r in rows:
        if r["post_id"] in seen or not r["text"].strip(): continue
        seen.add(r["post_id"]); t = datetime.fromisoformat(r["created_at"]).astimezone(KST)
        by_month[month_key(t)].append((slot(t), r))
    del rows
    for ym in sorted(by_month):
        items = by_month[ym]; agg = defaultdict(lambda: [0] * 10)
        for i in range(0, len(items), 20000):
            ch = items[i:i + 20000]; rs = [r for _, r in ch]
            texts = [r["text"][:400] for r in rs]; pars = [parent.get(r["parent_id"], "")[:300] if r["parent_id"] else "" for r in rs]
            X = features(M, texts, pars, [bool(r["parent_id"]) for r in rs], [r["badge"] for r in rs], [r["is_holder"] == "1" for r in rs])
            p = LR.predict_proba(X); s = np.where(p[:, GI] >= THRESHOLD, 1, np.where(p[:, FI] >= THRESHOLD, -1, 0))
            kws = tokens_batch([MENTION.sub("@사용자", t) for t in texts])
            for (h, r), sv, tk in zip(ch, s, kws):
                g = agg[h]; hold = r["is_holder"] == "1"
                g[0] += 1; g[1] += sv == 1; g[2] += sv == -1; g[3] += bool(tk & KW_G); g[4] += bool(tk & KW_F)
                g[5] += r["badge"] == "BUY"; g[6] += r["badge"] == "SELL"; g[7] += hold; g[8] += hold and sv == 1; g[9] += hold and sv == -1
        with open(f"{OUT}/{code}_{ym}.csv.tmp", "w", newline="") as f:
            w = csv.writer(f); w.writerow(COLS)
            for h in sorted(agg): w.writerow([h, *[int(x) for x in agg[h]]])
        os.replace(f"{OUT}/{code}_{ym}.csv.tmp", f"{OUT}/{code}_{ym}.csv"); total += len(items)
    print(f"{code} 누적 {total:,}건 {(time.time()-t0)/60:.1f}분", flush=True)
if not only:   # 전체를 돌렸을 때만 처리 건수·시간 기록 (발표의 '전체 적용 N분'에 쓰임)
    json.dump({"minutes": round((time.time() - t0) / 60, 1), "posts": total}, open(f"{D}/apply_out3_meta.json", "w"))
