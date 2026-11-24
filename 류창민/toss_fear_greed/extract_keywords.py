"""판정 결과로 탐욕·공포 키워드 뽑기. 같은 달 안에서 탐욕 글과 공포 글을 비교하고(달별 층화), 달마다 나온 차이를 합친다.
사용: uv run --with kiwipiepy python extract_keywords.py [학습 묶음...]  (기본 b00-b16)"""
import os
import json, math, re, sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from kiwipiepy import Kiwi

D = os.path.dirname(os.path.abspath(__file__))  # 이 폴더
SLANG = ("손절 익절 본절 물타기 불타기 존버 떡상 떡락 줍줍 상한가 하한가 가즈아 개미털기 설거지 추매 풀매수 몰빵 영끌 빚투 "
         "공매도 평단 쩜상 점상 신고가 신저가 탈출 반등 폭락 폭등 급등 급락 호재 악재 개미 세력 나락 손절각 익절각").split()

def batches(spec):
    out = []
    for s in spec:
        if "-" in s:
            a, b = (int(x[1:]) for x in s.split("-"))
            out += [f"b{i:02d}" for i in range(a, b + 1)]
        else:
            out.append(s)
    return out

def month_of(ts):  # 27일~다음 달 27일 창, KST
    t = datetime.fromisoformat(ts) + timedelta(hours=9)
    if t.day >= 27:
        return f"{t.year}-{t.month:02d}"
    y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    return f"{y}-{m:02d}"

kiwi = Kiwi(num_workers=-1)
for w in SLANG:
    kiwi.add_user_word(w, "NNG")
names = {n for v in json.load(open(f"{D}/sectors.json")).values() for n in v.values()}
STOP = set()
for n in names | set("삼전 하닉 하이닉스 에코 엘지 현차 한화 두산 삼성 현대 기아 네이버 카카오 효성 레인보우 알테 한미 이수 리노 심텍 후성 hd ls sk lg gs".split()):
    STOP.add(n.lower())
    STOP |= {t.form.lower() for t in kiwi.tokenize(n) if len(t.form) >= 2}
PRICE = re.compile(r"\d|^(만원|천원|억|조|프로|퍼센트|퍼)$")

def tokens(text):
    return from_toks(kiwi.tokenize(text))

def tokens_batch(texts):  # 여러 글을 한 번에 (멀티스레드)
    return [from_toks(t) for t in kiwi.tokenize(texts)]

def from_toks(toks):
    out = set()
    for i, t in enumerate(toks):
        f, tag = t.form, t.tag
        if tag.startswith(("VV", "VA")):
            w = f + "다"
            if i > 0 and toks[i - 1].form in ("안", "못") and toks[i - 1].tag == "MAG":
                w = toks[i - 1].form + " " + w      # 부정: '안 오르다'는 '오르다'와 따로 센다
            out.add(w)
        elif tag in ("NNG", "NNP", "XR", "MAG", "IC") and len(f) >= 2 and f not in ("안", "못"):
            out.add(f)
        elif tag == "SW" and re.fullmatch(r"[ㅋㅎㅠㅜ]+", f):
            out.add("ㅠㅠ" if f[0] in "ㅠㅜ" else "ㅋㅋ")
        elif tag == "W_EMOJI":
            out.add(f)
        elif tag == "SL" and len(f) >= 2:
            out.add(f.lower())
    return {w for w in out if w.lower() not in STOP and not PRICE.search(w)}

def main():
    posts = {r["id"]: r for f in ("sample_30k_clean.json", "sample_prev12_clean.json") for r in json.load(open(f"{D}/{f}"))}
    train = sys.argv[1:] or ["b00-b16"]
    docs = []  # (월, 라벨, 토큰집합)
    for b in batches(train):
        for line in open(f"{D}/labels/{b}.jsonl"):
            r = json.loads(line)
            if r["label"] in ("greed", "fear"):
                p = posts[r["id"]]
                docs.append((month_of(p["published_at"]), r["label"], tokens(p["text"])))

    # 달별 2x2 표 -> 로그 오즈비를 역분산 가중으로 합침 (같은 달끼리만 비교하므로 시기 효과가 빠진다)
    tot = defaultdict(Counter); cnt = defaultdict(lambda: defaultdict(Counter))
    for m, lab, ts in docs:
        tot[m][lab] += 1
        for w in ts:
            cnt[w][m][lab] += 1
    rows = []
    for w, bym in cnt.items():
        g_all = sum(c["greed"] for c in bym.values()); f_all = sum(c["fear"] for c in bym.values())
        if g_all + f_all < 15:
            continue
        num = den = 0.0; mg = mf = 0
        for m, c in bym.items():
            g, f, G, F = c["greed"], c["fear"], tot[m]["greed"], tot[m]["fear"]
            lor = math.log((g + .5) / (G - g + .5)) - math.log((f + .5) / (F - f + .5))
            var = 1 / (g + .5) + 1 / (G - g + .5) + 1 / (f + .5) + 1 / (F - f + .5)
            num += lor / var; den += 1 / var
            mg += g > f; mf += f > g
        lor = num / den
        rows.append({"word": w, "side": "greed" if lor > 0 else "fear", "log_odds": round(lor, 2), "z": round(lor * math.sqrt(den), 1),
                     "greed_docs": g_all, "fear_docs": f_all, "precision": round(max(g_all, f_all) / (g_all + f_all), 2),
                     "months_greed_more": mg, "months_fear_more": mf})
    keep = sorted((r for r in rows if abs(r["z"]) >= 3 and r["precision"] >= 0.7), key=lambda r: -abs(r["z"]))
    json.dump({"train_batches": train, "docs": len(docs), "months": sorted(tot), "keywords": keep},
              open(f"{D}/lexicon_draft.json", "w"), ensure_ascii=False, indent=1)
    print(f"학습 글 {len(docs):,}건(탐욕 {sum(l=='greed' for _,l,_ in docs):,} / 공포 {sum(l=='fear' for _,l,_ in docs):,}), {len(tot)}개월, "
          f"후보 {len(rows):,}개 -> 채택 {len(keep)}개 (탐욕 {sum(r['side']=='greed' for r in keep)}, 공포 {sum(r['side']=='fear' for r in keep)})")
    for side in ("greed", "fear"):
        print(f"\n[{side}] 단어 | z | 정밀도 | 탐욕글/공포글 | 이쪽이 많았던 달")
        for r in [r for r in keep if r["side"] == side][:40]:
            print(f"{r['word']} | {r['z']} | {r['precision']} | {r['greed_docs']}/{r['fear_docs']} | "
                  f"{r['months_greed_more'] if side == 'greed' else r['months_fear_more']}/{len(tot)}")

if __name__ == "__main__":
    main()
