"""최종 모델 v3 (김동우 제안 A9: KcELECTRA-base-v2022 미세조정, model_a9/)를 전체 글(김정기 수집기 형식)에 적용 -> 종목·30분(KST)별 집계. 원문은 저장하지 않음.
출력: apply_out4/<종목코드>_<YYYY-MM>.csv — apply_out3 와 같은 열(slot_kst, n_posts, n_greed, n_fear, n_kw_greed, n_kw_fear, n_buy, n_sell, n_holder, h_greed, h_fear)
입력 = 표지([대댓글][매수인증][매도인증][보유]) + clean(본문 400자) [SEP] clean(부모 글 300자), 128토큰. 확률 0.7 이상만 탐욕·공포 (a9_kcelectra.py 와 같음).
이미 있는 달 파일은 건너뜀(중간에 멈춰도 이어서 실행). 진행 기록: apply_all4.log, 끝나면 apply_out4_meta.json
사용: python apply_all4.py [종목코드]   (macOS에서 오래 돌릴 땐 caffeinate -i 를 앞에 붙임. 모델은 a9_kcelectra.py final 로 먼저 만든다)"""
import csv, json, os, sys, time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import numpy as np, torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from featurize import D, THRESHOLD, MENTION, clean
from extract_keywords import tokens_batch

csv.field_size_limit(10 ** 8)
KST = timezone(timedelta(hours=9)); DEV = torch.device("mps" if torch.backends.mps.is_available() else "cpu"); MAXLEN = 128
POSTS = os.path.join(D, "data", "raw", "posts"); OUT = f"{D}/apply_out4"; os.makedirs(OUT, exist_ok=True)
LEX = [k for k in json.load(open(f"{D}/lexicon_all29k.json"))["keywords"] if k["precision"] >= 0.8]
KW_G = {k["word"] for k in LEX if k["side"] == "greed"}; KW_F = {k["word"] for k in LEX if k["side"] == "fear"}
tok = AutoTokenizer.from_pretrained(f"{D}/model_a9"); model = AutoModelForSequenceClassification.from_pretrained(f"{D}/model_a9").to(DEV).eval()
STOCKS = [c for v in json.load(open(f"{D}/sectors.json")).values() for c in v]
TOTAL = json.load(open(f"{D}/apply_out3_meta.json"))["posts"] if os.path.exists(f"{D}/apply_out3_meta.json") else None   # 남은 시간 추정용 (없으면 생략)
COLS = ["slot_kst", "n_posts", "n_greed", "n_fear", "n_kw_greed", "n_kw_fear", "n_buy", "n_sell", "n_holder", "h_greed", "h_fear"]
LOG = open(f"{D}/apply_all4.log", "a")

def month_key(t):
    if t.day >= 27: return f"{t.year}-{t.month:02d}"
    y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    return f"{y}-{m:02d}"
slot = lambda t: t.strftime("%Y-%m-%dT%H:") + ("30" if t.minute >= 30 else "00")
def mark(r):   # 학습 때와 같은 표지 (a9_kcelectra.py mark)
    return ("[대댓글] " if r["parent_id"] else "") + ("[매수인증] " if r["badge"] == "BUY" else "[매도인증] " if r["badge"] == "SELL" else "") + ("[보유] " if r["is_holder"] == "1" else "")
@torch.no_grad()
def classify(texts, parents, rs):
    enc = [tok(mark(r) + clean(t), clean(p), truncation="longest_first", max_length=MAXLEN) if p else tok(mark(r) + clean(t), truncation=True, max_length=MAXLEN)
           for t, p, r in zip(texts, parents, rs)]
    order = sorted(range(len(enc)), key=lambda j: len(enc[j]["input_ids"])); P = np.zeros((len(enc), 3), np.float32)
    for i in range(0, len(order), 256):
        ix = order[i:i + 256]; ch = [enc[j] for j in ix]; n = max(len(e["input_ids"]) for e in ch)
        ids = torch.tensor([e["input_ids"] + [tok.pad_token_id] * (n - len(e["input_ids"])) for e in ch], device=DEV)
        att = torch.tensor([[1] * len(e["input_ids"]) + [0] * (n - len(e["input_ids"])) for e in ch], device=DEV)
        tt = torch.tensor([e["token_type_ids"] + [0] * (n - len(e["input_ids"])) for e in ch], device=DEV)
        P[ix] = torch.softmax(model(input_ids=ids, attention_mask=att, token_type_ids=tt).logits.float(), -1).cpu().numpy()
    return np.where(P[:, 0] >= THRESHOLD, 1, np.where(P[:, 1] >= THRESHOLD, -1, 0))   # 0=greed, 1=fear (학습 때 L3 순서)

only = sys.argv[1] if len(sys.argv) > 1 else None
t0 = time.time(); total = 0; done_posts = 0
for si, code in enumerate(STOCKS):
    if only and code != only: continue
    # 메모리 절약: 파일을 한 줄씩 읽고 쓰는 필드만, 본문 400자 · 부모 글 300자로 잘라 둔다 (결과는 전체를 읽던 때와 같음)
    parent = {}; by_month = defaultdict(list); seen = set()
    for r in csv.DictReader(open(f"{POSTS}/{code}.csv", encoding="utf-8")):
        if not r["parent_id"]: parent[r["post_id"]] = r["text"][:300]
        if r["post_id"] in seen or not r["text"].strip(): continue
        seen.add(r["post_id"]); t = datetime.fromisoformat(r["created_at"]).astimezone(KST)
        by_month[month_key(t)].append((slot(t), {"parent_id": r["parent_id"], "text": r["text"][:400], "badge": r["badge"], "is_holder": r["is_holder"]}))
    for ym in sorted(by_month):
        items = by_month[ym]; total += len(items)
        if os.path.exists(f"{OUT}/{code}_{ym}.csv"): continue   # 이어하기
        agg = defaultdict(lambda: [0] * 10)
        for i in range(0, len(items), 20000):
            ch = items[i:i + 20000]; rs = [r for _, r in ch]
            texts = [r["text"][:400] for r in rs]; pars = [parent.get(r["parent_id"], "")[:300] if r["parent_id"] else "" for r in rs]
            s = classify(texts, pars, rs)
            kws = tokens_batch([MENTION.sub("@사용자", t) for t in texts])
            for (h, r), sv, tk in zip(ch, s, kws):
                g = agg[h]; hold = r["is_holder"] == "1"
                g[0] += 1; g[1] += sv == 1; g[2] += sv == -1; g[3] += bool(tk & KW_G); g[4] += bool(tk & KW_F)
                g[5] += r["badge"] == "BUY"; g[6] += r["badge"] == "SELL"; g[7] += hold; g[8] += hold and sv == 1; g[9] += hold and sv == -1
        with open(f"{OUT}/{code}_{ym}.csv.tmp", "w", newline="") as f:
            w = csv.writer(f); w.writerow(COLS)
            for h in sorted(agg): w.writerow([h, *[int(x) for x in agg[h]]])
        os.replace(f"{OUT}/{code}_{ym}.csv.tmp", f"{OUT}/{code}_{ym}.csv"); done_posts += len(items)
    el = (time.time() - t0) / 60; rate = done_posts / max(el, 1e-9)
    msg = f"{datetime.now():%H:%M} {si + 1}/{len(STOCKS)} {code} 누적 {total:,}건 {el:.0f}분" + (f", 남은 예상 {(TOTAL - total) / rate:.0f}분" if done_posts and not only and TOTAL else "")
    print(msg, flush=True); LOG.write(msg + "\n"); LOG.flush()
if not only:   # 전체를 돌렸을 때만 처리 건수·시간 기록
    json.dump({"minutes": round((time.time() - t0) / 60, 1), "posts": total, "model": "model_a9 (KcELECTRA-base-v2022 미세조정, A9)", "source": "data/raw/posts (김정기 수집기 형식)"}, open(f"{D}/apply_out4_meta.json", "w"), ensure_ascii=False)
    LOG.write("완료\n"); LOG.flush()
