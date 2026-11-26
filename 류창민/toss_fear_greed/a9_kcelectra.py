"""김동우 제안 A9 1단계: 한국어 사전학습 모델(KcELECTRA-base-v2022)을 LLM 판정으로 미세조정해 지금 모델(A4+A5)과 비교. 맥북 GPU(MPS).
입력 = 표지 + 본문 [SEP] 부모 글. 표지: [대댓글] [매수인증] [매도인증] [보유] (해당할 때만). 전처리는 지금 모델과 같은 clean() (멘션·종목명·숫자).
3분류(탐욕·공포·그 외), 클래스 가중(지금 모델의 class_weight=balanced 와 같은 식), 확률 0.7 이상만 판정 — 지금 모델과 같은 규칙.
  speed : 표본 글 10만 건(5.9만 건을 반복)으로 판정 속도를 재고 전체 1,260만 건 걸리는 시간을 추정 → a9_speed.json
  foldN : eval_features_cv.py 와 같은 5무리 중 N번(0~4)을 채점, 나머지 4무리로 학습 (3회 반복, 미리 고정) → a9_foldN.json
사용: uv run --python 3.10 --with 'torch>=2.6' --with 'transformers>=4.46,<5' --with numpy python a9_kcelectra.py speed|fold0|fold1|…|fold4|final"""
import json, sys, time, math, random
from collections import defaultdict
from datetime import datetime, timedelta
import numpy as np, torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup
from featurize import D, clean

NAME = "beomi/KcELECTRA-base-v2022"; MAXLEN = 128; DEV = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
L3 = ["greed", "fear", "other"]
torch.manual_seed(0); random.seed(0); np.random.seed(0)
posts = {r["id"]: r for f in ("sample_30k_clean.json", "sample_prev12_clean.json") for r in json.load(open(f"{D}/{f}"))}

def mark(p):
    m = ("[대댓글] " if p["is_reply"] else "") + ("[매수인증] " if p["execution_side"] == "BUY" else "[매도인증] " if p["execution_side"] == "SELL" else "") + ("[보유] " if p["holding"] == "HOLDING" else "")
    return m + clean(p["text"])
def parent(p): return clean(p["parent_text"]) if p["is_reply"] and p["parent_text"] else None
tok = AutoTokenizer.from_pretrained(NAME)
def encode(ps):
    a, b = [mark(p) for p in ps], [parent(p) for p in ps]
    out = [tok(x, y, truncation="longest_first", max_length=MAXLEN) if y else tok(x, truncation=True, max_length=MAXLEN) for x, y in zip(a, b)]   # 긴 쪽부터 자름(보통 부모 글)
    return out
def batches(enc, idx, bs):   # 길이 비슷한 글끼리 묶어 빈칸 채우기를 줄임
    for i in range(0, len(idx), bs):
        ch = [enc[j] for j in idx[i:i + bs]]; n = max(len(e["input_ids"]) for e in ch)
        ids = torch.tensor([e["input_ids"] + [tok.pad_token_id] * (n - len(e["input_ids"])) for e in ch])
        att = torch.tensor([[1] * len(e["input_ids"]) + [0] * (n - len(e["input_ids"])) for e in ch])
        tt = torch.tensor([e.get("token_type_ids", [0] * len(e["input_ids"])) + [0] * (n - len(e["input_ids"])) for e in ch])
        yield idx[i:i + bs], ids.to(DEV), att.to(DEV), tt.to(DEV)
@torch.no_grad()
def predict(model, enc, bs=256):
    model.eval(); order = sorted(range(len(enc)), key=lambda j: len(enc[j]["input_ids"])); P = np.zeros((len(enc), 3), np.float32)
    for ix, ids, att, tt in batches(enc, order, bs):
        P[ix] = torch.softmax(model(input_ids=ids, attention_mask=att, token_type_ids=tt).logits.float(), -1).cpu().numpy()
    return P
def load_model():
    return AutoModelForSequenceClassification.from_pretrained(NAME, num_labels=3, use_safetensors=False).to(DEV)

mode = sys.argv[1]
if mode == "speed":
    ps = list(posts.values()); ps = (ps * 2)[:100000]
    t0 = time.time(); enc = encode(ps); t_tok = time.time() - t0
    model = load_model(); predict(model, enc[:2000])   # 예열
    if DEV.type == "mps": torch.mps.synchronize()
    t0 = time.time(); predict(model, enc); t_inf = time.time() - t0
    per = (t_tok + t_inf) / len(ps); total = 12597740 * per
    out = {"device": DEV.type, "n": len(ps), "tokenize_sec": t_tok, "infer_sec": t_inf, "posts_per_sec": len(ps) / (t_tok + t_inf),
           "mean_tokens": float(np.mean([len(e["input_ids"]) for e in enc])), "est_full_hours": total / 3600}
    json.dump(out, open(f"{D}/a9_speed.json", "w"), indent=1); print(out)

if mode.startswith("fold") or mode == "final":
    F = int(mode[4:]) if mode != "final" else -1   # 채점할 무리 번호 (0~4). final 은 채점 없이 29묶음 전부로 학습해 model_a9/ 에 저장
    def month_of(ts):
        t = datetime.fromisoformat(ts) + timedelta(hours=9)
        if t.day >= 27: return f"{t.year}-{t.month:02d}"
        y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
        return f"{y}-{m:02d}"
    B = [f"b{i:02d}" for i in list(range(0, 23)) + list(range(31, 37))]
    rows, y, grp = [], [], []
    for gi_, b in enumerate(B):   # eval_features_cv.py 와 같은 5무리
        for line in open(f"{D}/labels/{b}.jsonl"):
            r = json.loads(line); rows.append(posts[r["id"]]); y.append(L3.index(r["label"]) if r["label"] in ("greed", "fear") else 2); grp.append(gi_ % 5)
    y, grp = np.array(y), np.array(grp); mon = np.array([month_of(p["published_at"]) for p in rows])
    enc = encode(rows); tr = np.where(grp != F)[0]; te = np.where(grp == F)[0]
    cnt = np.bincount(y[tr], minlength=3); w = torch.tensor(len(tr) / (3 * cnt), dtype=torch.float32, device=DEV)
    model = load_model(); EPOCHS, BS, LR = 3, 32, 5e-5
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    steps = EPOCHS * math.ceil(len(tr) / BS); sch = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)
    lossf = torch.nn.CrossEntropyLoss(weight=w); log = []; t0 = time.time()
    def score(P, thr=0.7):
        pred = np.where(P[:, 0] >= thr, 0, np.where(P[:, 1] >= thr, 1, -1)); yt = y[te]; mt = mon[te]
        dec = pred >= 0; ok = dec & (pred == yt); opp = dec & (yt < 2) & (pred != yt)
        bm = defaultdict(lambda: defaultdict(int))
        for mm, pr, yy in zip(mt, pred, yt):
            if yy < 2: bm[mm]["l" + str(yy)] += 1
            if pr >= 0: bm[mm]["k" + str(pr)] += 1
        err = np.mean([abs(v["k0"] / max(v["k0"] + v["k1"], 1) - v["l0"] / max(v["l0"] + v["l1"], 1)) for v in bm.values()])
        return {"decided": float(dec.mean()), "acc": float(ok.sum() / max(dec.sum(), 1)), "dir_acc": float(ok.sum() / max(ok.sum() + opp.sum(), 1)), "ratio_err": float(err)}
    for ep in range(EPOCHS):
        model.train(); order = list(tr); random.shuffle(order)
        # 길이 비슷한 글끼리: 100묶음 단위로 섞은 뒤 안에서 길이 정렬
        chunks = [sorted(order[i:i + BS * 100], key=lambda j: len(enc[j]["input_ids"])) for i in range(0, len(order), BS * 100)]
        bl = [c[i:i + BS] for c in chunks for i in range(0, len(c), BS)]; random.shuffle(bl); run = 0.0
        for k, bidx in enumerate(bl):
            _, ids, att, tt = next(batches(enc, bidx, BS))
            loss = lossf(model(input_ids=ids, attention_mask=att, token_type_ids=tt).logits, torch.tensor(y[bidx], device=DEV))
            loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step(); sch.step(); opt.zero_grad(); run += loss.item()
            if k % 200 == 0: print(f"ep{ep} {k}/{len(bl)} loss {run / (k + 1):.3f} {(time.time() - t0) / 60:.1f}분", flush=True)
        if F < 0: print(f"ep{ep} 끝 {(time.time() - t0) / 60:.1f}분", flush=True); continue
        P = predict(model, [enc[j] for j in te]); s = score(P); s["epoch"] = ep + 1; s["min"] = (time.time() - t0) / 60; log.append(s); print(s, flush=True)
    if F < 0:
        model.save_pretrained(f"{D}/model_a9"); tok.save_pretrained(f"{D}/model_a9")
        json.dump({"n_train": int(len(tr)), "train_min": (time.time() - t0) / 60, "epochs": EPOCHS, "lr": LR, "batch": BS, "maxlen": MAXLEN, "base": NAME}, open(f"{D}/model_a9/train_info.json", "w"), indent=1)
        print("저장: model_a9/", flush=True); raise SystemExit
    base = json.load(open(f"{D}/eval_features_cv.json"))["(d) A4+A5"]
    out = {"final_epoch3": log[-1], "per_epoch": log, "thr_sweep": {str(t): score(P, t) for t in (0.6, 0.7, 0.8, 0.9)},
           "fold": F, "baseline_d": {k: base[k]["folds"][F] for k in ("decided", "acc", "ratio_err")}, "n_train": int(len(tr)), "n_test": int(len(te)), "train_min": (time.time() - t0) / 60}
    json.dump(out, open(f"{D}/a9_fold{F}.json", "w"), indent=1, ensure_ascii=False)
    print("A9 3회 반복:", log[-1]); print("지금 모델 같은 겹:", out["baseline_d"])
