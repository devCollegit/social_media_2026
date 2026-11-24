"""남겨 둔 묶음으로 키워드 분류기 채점. 글의 점수 = 들어 있는 키워드 log_odds 합. 점수 >= t 탐욕, <= -t 공포, 사이는 보류.
사용: uv run --with kiwipiepy python score_heldout.py [채점 묶음...]  (기본 b17-b22)"""
import json, sys
from collections import Counter, defaultdict
from extract_keywords import D, batches, month_of, tokens

lex = json.load(open(f"{D}/lexicon_draft.json"))["keywords"]
posts = {r["id"]: r for r in json.load(open(f"{D}/sample_30k_clean.json"))}
rows = []
for b in batches(sys.argv[1:] or ["b17-b22"]):
    for line in open(f"{D}/labels/{b}.jsonl"):
        r = json.loads(line); p = posts[r["id"]]
        rows.append((month_of(p["published_at"]), r["label"], tokens(p["text"])))

GREED_ERA = {"2025-10", "2025-11", "2025-12", "2026-01", "2026-02"}
FEAR_ERA = {"2026-07", "2026-08", "2026-09"}
VARIANTS = {"전체 67개": lex, "정밀도 80%+ 만": [k for k in lex if k["precision"] >= 0.8]}

def run(words, t, subset=None):
    w = {k["word"]: k["log_odds"] for k in words}
    n = dec = ok = 0; kinds = Counter(); by_m = defaultdict(Counter)
    for m, lab, ts in rows:
        if subset and m not in subset:
            continue
        n += 1
        s = sum(w.get(x, 0) for x in ts)
        pred = "greed" if s >= t else "fear" if s <= -t else None
        if lab in ("greed", "fear"):
            by_m[m]["llm_" + lab] += 1
        if pred:
            dec += 1; ok += pred == lab; kinds[lab] += 1; by_m[m]["kw_" + pred] += 1
    return n, dec, ok, kinds, by_m

print(f"채점 글 {len(rows):,}건, 라벨 분포 {dict(Counter(l for _, l, _ in rows))}")
for name, words in VARIANTS.items():
    print(f"\n=== {name} ({len(words)}개) ===")
    print("기준점 | 판정 비율 | 정확도(전체) | 탐욕기 정확도 | 공포기 정확도 | 틀린 것의 실제 라벨")
    for t in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        n, dec, ok, kinds, _ = run(words, t)
        _, dg, og, _, _ = run(words, t, GREED_ERA)
        _, df, of, _, _ = run(words, t, FEAR_ERA)
        wrong = {k: v for k, v in kinds.items() if k not in ("greed", "fear") or True}
        print(f"{t} | {dec/n:.0%} | {ok/dec:.0%} | {og/max(dg,1):.0%} | {of/max(df,1):.0%} | "
              f"{ {k: kinds[k] for k in ('neutral','irrelevant','unsure')} } + 반대쪽 {dec-ok-sum(kinds[k] for k in ('neutral','irrelevant','unsure'))}")

# 치우침: 달별 탐욕 비율 (LLM 판정 vs 키워드 판정)
for name, words in VARIANTS.items():
    for t in (1.0, 2.0):
        _, _, _, _, by_m = run(words, t)
        print(f"\n[치우침] {name}, 기준점 {t}: 달 | LLM 탐욕비율 | 키워드 탐욕비율")
        for m in sorted(by_m):
            c = by_m[m]
            llm = c["llm_greed"] / max(c["llm_greed"] + c["llm_fear"], 1)
            kw = c["kw_greed"] / max(c["kw_greed"] + c["kw_fear"], 1)
            print(f"{m} | {llm:.0%} | {kw:.0%} | (키워드 판정 {c['kw_greed']+c['kw_fear']}건)")
