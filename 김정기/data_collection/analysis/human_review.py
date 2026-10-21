"""사람 검수와 저장된 자동 분류를 비교하고 오류 진단 자료를 만든다."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import pandas as pd

LABELS = ["긍정", "중립", "부정"]
KEYS = ["stock_id", "post_id"]


def evaluate(gold, scored):
    for frame in (gold, scored):
        if frame[KEYS].isna().any().any() or (frame[KEYS] == "").any().any():
            raise ValueError("빈 평가 ID")
        if frame.duplicated(KEYS).any():
            raise ValueError("중복 평가 ID")
    if not gold.label.isin(LABELS).all() or not scored.sentiment.isin(LABELS).all():
        raise ValueError("허용되지 않은 라벨")
    joined = gold[KEYS + ["label"]].merge(
        scored[KEYS + ["sentiment", "text_norm"]], on=KEYS, how="left", validate="one_to_one")
    if joined.sentiment.isna().any() or joined.empty:
        raise ValueError("예측과 연결되지 않은 평가 ID 또는 빈 표본")
    joined["agreement"] = joined.label == joined.sentiment
    rows = []
    for label in LABELS:
        actual = joined.label == label
        predicted = joined.sentiment == label
        tp = int((actual & predicted).sum())
        precision = tp / predicted.sum() if predicted.any() else 0.0
        recall = tp / actual.sum() if actual.any() else 0.0
        rows.append(dict(label=label, support=int(actual.sum()),
                         precision=float(precision), recall=float(recall),
                         f1=float(2 * precision * recall / (precision + recall))
                         if precision + recall else 0.0))
    metrics = dict(n=len(joined), matches=int(joined.agreement.sum()),
                   accuracy=float(joined.agreement.mean()),
                   macro_f1=sum(r["f1"] for r in rows) / 3,
                   always_neutral_accuracy=float((joined.label == "중립").mean()),
                   per_class=rows)
    return joined, metrics


def diagnose(text, positive, negative, negators, neutral_markers):
    """신호 존재 여부를 기록한다. 오분류의 원인을 확정하는 규칙은 아니다."""
    pos = [term for term in positive if term in text]
    neg = [term for term in negative if term in text]
    return dict(positive_hits="|".join(pos), negative_hits="|".join(neg),
                no_lexicon_hit=not pos and not neg,
                mixed_direction=bool(pos and neg),
                negator_present=any(t in text for t in negators),
                neutral_marker_present=any(t in text for t in neutral_markers))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--scored", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root / "state"):
        raise ValueError("진단 원문은 state 아래 저장하세요.")
    # 기존 팀 사전은 읽기/import만 한다.
    import sys
    sys.path.insert(0, str(root.parents[1] / "조현호/toss_sentiment"))
    from pipeline.lexicon import POSITIVE, NEGATIVE, NEGATORS, NEUTRAL_MARKERS
    gold = pd.read_csv(args.gold, dtype=str, keep_default_na=False)
    scored = pd.read_csv(args.scored, dtype=str, keep_default_na=False)
    joined, metrics = evaluate(gold, scored)
    signals = pd.DataFrame([diagnose(t, POSITIVE, NEGATIVE, NEGATORS, NEUTRAL_MARKERS)
                            for t in joined.text_norm])
    joined = pd.concat([joined, signals], axis=1)
    errors = joined[~joined.agreement].copy()
    metrics["error_signals_overlapping"] = {
        col: int(errors[col].sum()) for col in
        ["no_lexicon_hit", "mixed_direction", "negator_present", "neutral_marker_present"]}
    metrics["inputs"] = [{"path": str(p.resolve()),
                         "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                        for p in [args.gold, args.scored]]
    metrics["limitations"] = ["단독 검수자 기준 진단",
                              "신호는 중복 집계되며 원인 확정이 아님",
                              "기존 진단 표본으로 최종 독립 평가가 아님"]
    # 원문·토큰은 Git 제외 출력 안에만 저장한다.
    counts = Counter(token for text in errors.text_norm
                     for token in set(re.findall(r"[가-힣]{2,}", text)))
    args.output.mkdir(parents=True, exist_ok=False)
    errors.to_csv(args.output / "errors.csv", index=False, encoding="utf-8-sig")
    joined.drop(columns="text_norm").to_csv(args.output / "comparison.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(counts.most_common(), columns=["token", "error_rows"]).to_csv(
        args.output / "error_tokens.csv", index=False, encoding="utf-8-sig")
    pd.crosstab(joined.label, joined.sentiment).reindex(index=LABELS, columns=LABELS, fill_value=0).to_csv(
        args.output / "confusion.csv", encoding="utf-8-sig")
    (args.output / "summary.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in metrics.items() if k != "inputs"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
