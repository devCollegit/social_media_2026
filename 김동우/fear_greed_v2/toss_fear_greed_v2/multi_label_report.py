"""여러 축 판정(보완안 A8) 결과 정리. 기존 탐욕·공포 라벨이 실제로 어떤 감정·행동·대상으로 이뤄져 있는지 센다.

보는 것
1. 축별 분포 (감정, 행동 의도, 대상)
2. 기존 라벨 × 감정: 공포 판정 글 중 겁(불안·패닉) / 분노 / 후회 비율, 탐욕 판정 글 중 기대·흥분 / 후회(못 산 아쉬움) 비율
   → 발표 13장 "감성 = 방향 의견" 설명이 맞는지 확인
3. 기존 라벨 × 행동 의도: 탐욕 글이 실제로 사겠다는 글인가, 공포 글이 팔겠다는 글인가
4. 본문 행동 의도 × 매수·매도 인증 표시: 말한 행동과 체결 인증이 같은 방향인가
5. 두 번 판정했으면(--recheck) 축별 일치율·Cohen κ

입력: --base (sample_*_clean.json, labels/), --labels 여러 축 판정 폴더(mNN.jsonl), --recheck 두 번째 판정 폴더(선택)
출력 (--out): multi_report.json, multi_report.md
사용: python multi_label_report.py --base <toss_fear_greed 폴더> --labels v2_out/multi/labels [--recheck v2_out/multi/labels_recheck] --out v2_out/multi
"""
import argparse
import glob
import json
import os

import pandas as pd
from sklearn.metrics import cohen_kappa_score

from common import LABELS5, write_json

AXES = {"emotion": ["hope", "excitement", "anxiety", "panic", "anger", "regret", "mockery", "none"],
        "intent": ["buy", "add", "hold", "sell", "wait", "none"],
        "target": ["stock", "market", "players", "company", "investors", "none"]}
KO = {"hope": "기대", "excitement": "흥분", "anxiety": "불안", "panic": "패닉", "anger": "분노", "regret": "후회", "mockery": "조롱",
      "none": "없음", "buy": "매수", "add": "추가 매수", "hold": "보유", "sell": "매도", "wait": "관망", "stock": "종목",
      "market": "시장", "players": "세력·기관·외국인", "company": "회사", "investors": "다른 투자자",
      "greed": "탐욕", "fear": "공포", "neutral": "중립", "irrelevant": "무관", "unsure": "애매"}
P = argparse.ArgumentParser()
P.add_argument("--base", required=True)
P.add_argument("--labels", required=True)
P.add_argument("--recheck", default="")
P.add_argument("--out", default="v2_out/multi")
A = P.parse_args()


def load_multi(d):
    rows = []
    for f in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            if line.strip():
                rows.append(json.loads(line))
    x = pd.DataFrame(rows)
    for ax, vals in AXES.items():                 # 기준표 밖의 값은 none으로 세고 개수를 남김
        x[ax] = x[ax].where(x[ax].isin(vals), "none") if ax in x else "none"
    return x.drop_duplicates("id").set_index("id")


m = load_multi(A.labels)
side, old = {}, {}
for f in glob.glob(os.path.join(A.base, "sample_*_clean.json")):
    for r in json.load(open(f, encoding="utf-8")):
        side[r["id"]] = r.get("execution_side")
for f in glob.glob(os.path.join(A.base, "labels", "*.jsonl")):
    for line in open(f, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            old[r["id"]] = r["label"]
m["old"] = m.index.map(old)
m["badge"] = m.index.map(side).fillna("없음")
R = {"n": len(m), "n_with_old_label": int(m.old.notna().sum())}
for ax in AXES:
    R[f"dist_{ax}"] = m[ax].value_counts(normalize=True).reindex(AXES[ax], fill_value=0).round(4).to_dict()


def share_tab(row, col, cols):
    t = pd.crosstab(m[row], m[col], normalize="index").reindex(columns=cols, fill_value=0)
    return t.reindex([i for i in LABELS5 if i in t.index] if row == "old" else t.index)


T = {"old_x_emotion": share_tab("old", "emotion", AXES["emotion"]), "old_x_intent": share_tab("old", "intent", AXES["intent"]),
     "old_x_target": share_tab("old", "target", AXES["target"]),
     "badge_x_intent": pd.crosstab(m.badge, m.intent, normalize="index").reindex(columns=AXES["intent"], fill_value=0)}
for k, t in T.items():
    R[k] = t.round(4).to_dict(orient="index")
f = m[m.old == "fear"]
g = m[m.old == "greed"]
if len(f):
    R["fear_breakdown"] = {"scared(anxiety+panic)": float(f.emotion.isin(["anxiety", "panic"]).mean()), "anger": float((f.emotion == "anger").mean()),
                           "regret": float((f.emotion == "regret").mean()), "sell_intent": float((f.intent == "sell").mean())}
if len(g):
    R["greed_breakdown"] = {"hope+excitement": float(g.emotion.isin(["hope", "excitement"]).mean()), "regret": float((g.emotion == "regret").mean()),
                            "buy_or_add_intent": float(g.intent.isin(["buy", "add"]).mean())}
if A.recheck and os.path.isdir(A.recheck):
    r2 = load_multi(A.recheck)
    ids = m.index.intersection(r2.index)
    R["recheck"] = {"n": int(len(ids))}
    for ax in AXES:
        a, b = m.loc[ids, ax], r2.loc[ids, ax]
        R["recheck"][ax] = {"agree": float((a == b).mean()), "kappa": float(cohen_kappa_score(a, b))}
os.makedirs(A.out, exist_ok=True)
write_json(os.path.join(A.out, "multi_report.json"), R)

def pct(t):
    """비율 표 → 마크다운 표 (tabulate 없이)."""
    cols = [KO.get(c, c) for c in t.columns]
    out = ["| | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for i, row in t.iterrows():
        out.append(f"| {KO.get(i, i)} | " + " | ".join(f"{v:.0%}" for v in row) + " |")
    return "\n".join(out)



L = [f"# 여러 축 판정 결과 ({R['n']:,}건, 기존 라벨과 연결 {R['n_with_old_label']:,}건)", ""]
for ax, title in (("emotion", "감정"), ("intent", "행동 의도"), ("target", "대상")):
    L.append(f"- {title}: " + ", ".join(f"{KO[k]} {v:.0%}" for k, v in R[f"dist_{ax}"].items() if v > 0))
if "fear_breakdown" in R:
    fb = R["fear_breakdown"]
    L += ["", f"**공포 판정 글**: 겁(불안·패닉) {fb['scared(anxiety+panic)']:.0%}, 분노 {fb['anger']:.0%}, 후회 {fb['regret']:.0%}, 팔겠다는 글 {fb['sell_intent']:.0%}"]
if "greed_breakdown" in R:
    gb = R["greed_breakdown"]
    L += [f"**탐욕 판정 글**: 기대·흥분 {gb['hope+excitement']:.0%}, 후회(못 산 아쉬움) {gb['regret']:.0%}, 사겠다는 글 {gb['buy_or_add_intent']:.0%}"]
for k, title in (("old_x_emotion", "기존 라벨 × 감정 (행 기준 비율)"), ("old_x_intent", "기존 라벨 × 행동 의도"),
                 ("old_x_target", "기존 라벨 × 대상"), ("badge_x_intent", "매수·매도 인증 × 본문 행동 의도")):
    L += ["", f"## {title}", "", pct(T[k])]
if "recheck" in R:
    rc = R["recheck"]
    L += ["", f"## 두 판정의 일치도 ({rc['n']:,}건)", ""] + [f"- {t}: 일치 {rc[a]['agree']:.0%}, κ {rc[a]['kappa']:.2f}"
                                                         for a, t in (("emotion", "감정"), ("intent", "행동 의도"), ("target", "대상"))]
open(os.path.join(A.out, "multi_report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L))
