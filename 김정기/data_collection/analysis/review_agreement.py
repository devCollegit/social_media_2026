"""AI 검토 라벨과 사전 예측의 일치도를 계산한다. 사람 정답 정확도가 아니다."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

LABELS = ["긍정", "중립", "부정"]


def compare(review, scored):
    keys = ["stock_id", "post_id"]
    if review.duplicated(keys).any() or scored.duplicated(keys).any():
        raise ValueError("중복 평가 ID")
    if not review.ai_label.isin(LABELS).all():
        raise ValueError("허용되지 않은 AI 라벨")
    if not scored.sentiment.isin(LABELS).all():
        raise ValueError("허용되지 않은 사전 라벨")
    joined = review.merge(scored[keys + ["sentiment"]], on=keys, how="left", validate="one_to_one")
    if joined.sentiment.isna().any():
        raise ValueError("예측과 연결되지 않은 평가 ID")
    joined["agreement"] = joined.ai_label == joined.sentiment
    joined["difference_type"] = "agreement"
    different = ~joined.agreement
    joined.loc[different & (joined.sentiment == "중립"), "difference_type"] = "lexicon_neutral_ai_directional"
    joined.loc[different & (joined.ai_label == "중립"), "difference_type"] = "lexicon_directional_ai_neutral"
    joined.loc[different & (joined.ai_label != "중립") & (joined.sentiment != "중립"), "difference_type"] = "opposite_direction"
    return joined


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--review", type=Path, required=True)
    ap.add_argument("--scored", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root / "state"):
        raise ValueError("본문이 포함된 결과는 state 아래 저장하세요.")
    review = pd.read_csv(args.review, dtype={"stock_id": str, "post_id": str})
    scored = pd.read_csv(args.scored, dtype={"stock_id": str, "post_id": str})
    joined = compare(review, scored)
    confusion = pd.crosstab(joined.ai_label, joined.sentiment).reindex(index=LABELS, columns=LABELS, fill_value=0)
    clear = joined[~joined.needs_context]
    neutral = joined[joined.sentiment == "중립"]
    by_stock = joined.groupby("stock_id").agg(n=("post_id", "size"), agreements=("agreement", "sum"),
                                               agreement_with_ai=("agreement", "mean"))
    summary = {"n": len(joined), "agreement_with_ai": float(joined.agreement.mean()),
               "context_ambiguous": int(joined.needs_context.sum()),
               "clear_n": len(clear), "clear_agreement_with_ai": float(clear.agreement.mean()),
               "lexicon_neutral_n": len(neutral),
               "lexicon_neutral_ai_directional": int((neutral.ai_label != "중립").sum()),
               "human_accuracy": None, "human_gold_available": False,
               "inputs": [{"path": str(p.resolve()), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                          for p in [args.review, args.scored]],
               "difference_types": {str(k): int(v) for k, v in joined.difference_type.value_counts().items()},
               "limitations": [f"단일 AI 검토 {len(joined)}건 점검", "AI도 오판할 수 있음", "사람 정답 기반 정확도나 평가자 간 신뢰도로 해석 금지"]}
    args.output.mkdir(parents=True, exist_ok=False)
    joined.to_csv(args.output / "review_comparison.csv", index=False, encoding="utf-8-sig")
    confusion.to_csv(args.output / "confusion_ai_vs_lexicon.csv", encoding="utf-8-sig")
    by_stock.to_csv(args.output / "agreement_by_stock.csv", encoding="utf-8-sig")
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
