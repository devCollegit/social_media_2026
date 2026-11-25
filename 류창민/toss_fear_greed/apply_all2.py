"""45종목 2년치 전체 글에 최종 모델 + 키워드 적용 -> 종목·30분(KST)별 집계. 원문은 저장하지 않음.
30분 단위: 거래일 경계(20:00)·장전 구간(08:30 등)을 나중에 자유롭게 자르기 위함.
키워드: lexicon_all29k.json 중 정밀도 0.8 이상. 글 하나에 탐욕 단어가 하나라도 있으면 n_kw_greed +1 (공포도 같음, 둘 다일 수 있음).
입력: data/raw/posts/<stock_id>.csv (김정기 수집기 형식, make_sample.py 설명 참고), model.joblib (train_final.py 결과). post_id 중복 제거.
출력: apply_out2/<종목코드>_<YYYY-MM>.csv  (slot_kst, n_posts, n_greed, n_fear, n_kw_greed, n_kw_fear) — 한 달 = 전월 27일 ~ 당월 27일 전, 이미 있으면 건너뜀(이어하기).
사용: python apply_all2.py [종목코드 [YYYY-MM]]"""
import csv, json, os, sys, time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import joblib, numpy as np
from featurize import D, clean, THRESHOLD, MENTION
from extract_keywords import tokens_batch

KST = timezone(timedelta(hours=9))
POSTS = os.path.join(D, "data", "raw", "posts")
LEX = [k for k in json.load(open(f"{D}/lexicon_all29k.json"))["keywords"] if k["precision"] >= 0.8]
KW_G = {k["word"] for k in LEX if k["side"] == "greed"}; KW_F = {k["word"] for k in LEX if k["side"] == "fear"}
M = joblib.load(f"{D}/model.joblib"); V, LR = M["vectorizer"], M["model"]
GI, FI = list(LR.classes_).index("greed"), list(LR.classes_).index("fear")
S = json.load(open(f"{D}/sectors.json"))
STOCKS = [c for v in S.values() for c in v]
os.makedirs(f"{D}/apply_out2", exist_ok=True)

def classify(texts):
    p = LR.predict_proba(V.transform([clean(t) for t in texts]))
    return np.where(p[:, GI] >= THRESHOLD, 1, np.where(p[:, FI] >= THRESHOLD, -1, 0))

def month_key(t):   # 27일부터 다음 달로 센다: 2026-04-27 ~ 2026-05-26 → "2026-04"
    if t.day >= 27: return f"{t.year}-{t.month:02d}"
    y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    return f"{y}-{m:02d}"

def slot(t):        # 30분 칸 (KST)
    return t.strftime("%Y-%m-%dT%H:") + ("30" if t.minute >= 30 else "00")

only_code = sys.argv[1] if len(sys.argv) > 1 else None
only_month = sys.argv[2] if len(sys.argv) > 2 else None
total = 0; t0 = time.time()
for code in STOCKS:
    if only_code and code != only_code: continue
    path_in = os.path.join(POSTS, f"{code}.csv")
    if not os.path.exists(path_in): print(f"{code} 입력 없음, 건너뜀"); continue
    seen, by_month = set(), defaultdict(list)
    for r in csv.DictReader(open(path_in, encoding="utf-8")):
        if r["post_id"] in seen or not (r.get("text") or "").strip(): continue
        seen.add(r["post_id"])
        t = datetime.fromisoformat(r["created_at"]).astimezone(KST)
        by_month[month_key(t)].append((slot(t), r["text"]))
    for ym in sorted(by_month):
        if only_month and ym != only_month: continue
        path = f"{D}/apply_out2/{code}_{ym}.csv"
        if os.path.exists(path): continue
        rows = by_month[ym]; agg = defaultdict(lambda: [0, 0, 0, 0, 0])
        for i in range(0, len(rows), 20000):
            chunk = rows[i:i + 20000]; texts = [t[:400] for _, t in chunk]
            for (h, _), s, tk in zip(chunk, classify(texts), tokens_batch([MENTION.sub("@사용자", t) for t in texts])):
                g = agg[h]; g[0] += 1; g[1] += s == 1; g[2] += s == -1
                g[3] += bool(tk & KW_G); g[4] += bool(tk & KW_F)
        with open(path + ".tmp", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["slot_kst", "n_posts", "n_greed", "n_fear", "n_kw_greed", "n_kw_fear"])
            for h in sorted(agg): w.writerow([h, *agg[h]])
        os.replace(path + ".tmp", path)
        total += len(rows)
        print(f"{code} {ym} {len(rows):,}건 | 누적 {total:,}건 {(time.time()-t0)/60:.1f}분", flush=True)
