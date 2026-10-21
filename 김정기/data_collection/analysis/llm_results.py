"""Validate low-cost model sentiment output and summarize eligible comparisons."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

KEYS = ["stock_id", "post_id"]
RELEVANCE = {"related", "unrelated", "unclear"}
SENTIMENTS = {"긍정", "중립", "부정", "혼합", "판단유보"}
DIRECTIONAL = ["긍정", "중립", "부정"]
ELIGIBLE = set(DIRECTIONAL)
PREDICTION_FIELDS = {"stock_id", "post_id", "relevance", "sentiment", "reason",
                     "evidence", "context_used"}


def _ids(frame, name):
    missing = set(KEYS) - set(frame.columns)
    if missing:
        raise ValueError(f"{name}: ID 컬럼 누락 {sorted(missing)}")
    if frame[KEYS].isna().any().any() or (frame[KEYS].astype(str) == "").any().any():
        raise ValueError(f"{name}: 빈 ID")
    if frame.duplicated(KEYS).any():
        raise ValueError(f"{name}: 중복 ID")


def _read_predictions(path):
    rows = []
    try:
        with Path(path).open(encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, 1):
                if not line.strip():
                    raise ValueError(f"predictions.jsonl:{line_no}: 빈 행")
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"predictions.jsonl:{line_no}: JSON 오류") from exc
                if not isinstance(item, dict) or set(item) != PREDICTION_FIELDS:
                    raise ValueError(f"predictions.jsonl:{line_no}: 필드 집합 불일치")
                rows.append(item)
    except UnicodeDecodeError as exc:
        raise ValueError("예측 파일은 UTF-8이어야 합니다") from exc
    frame = pd.DataFrame(rows, columns=sorted(PREDICTION_FIELDS))
    _ids(frame, "예측")
    for row in rows:
        if not all(isinstance(row[k], str) for k in KEYS + ["relevance", "sentiment"]):
            raise ValueError("ID와 enum은 문자열이어야 합니다")
        if row["relevance"] not in RELEVANCE or row["sentiment"] not in SENTIMENTS:
            raise ValueError("예측 enum 오류")
        if not isinstance(row["reason"], str) or not row["reason"].strip() or len(row["reason"]) > 1000:
            raise ValueError("reason은 1~1000자 문자열이어야 합니다")
        if not isinstance(row["evidence"], str) or len(row["evidence"]) > 300:
            raise ValueError("evidence는 0~300자 문자열이어야 합니다")
        if type(row["context_used"]) is not bool:
            raise ValueError("context_used는 boolean이어야 합니다")
        if row["relevance"] != "related" and row["sentiment"] != "판단유보":
            raise ValueError("unrelated/unclear는 판단유보여야 합니다")
        if row["sentiment"] in ELIGIBLE and not row["evidence"]:
            raise ValueError("방향성 라벨에는 evidence가 필요합니다")
    return frame


def _check_predictions(source, predictions):
    _ids(source, "source")
    _ids(predictions, "예측")
    source_keys = set(map(tuple, source[KEYS].astype(str).to_numpy()))
    prediction_keys = set(map(tuple, predictions[KEYS].astype(str).to_numpy()))
    if source_keys != prediction_keys:
        raise ValueError(f"예측 ID 집합 불일치 (누락 {len(source_keys-prediction_keys)}, 추가 {len(prediction_keys-source_keys)})")
    if not {"text_norm", "parent_text", "context_status"}.issubset(source.columns):
        raise ValueError("source 문맥 컬럼 누락")
    source_index = source.set_index(KEYS)
    for row in predictions.itertuples(index=False):
        key = (str(row.stock_id), str(row.post_id))
        src = source_index.loc[key]
        evidence = row.evidence
        if row.context_used and not str(src.parent_text):
            raise ValueError("부모 문맥이 없는데 context_used가 true입니다")
        if evidence:
            in_target = evidence in str(src.text_norm)
            in_parent = evidence in str(src.parent_text)
            if not in_target and not in_parent:
                raise ValueError("evidence가 source 원문에 없습니다")
            if in_parent and not in_target and not row.context_used:
                raise ValueError("부모에서만 찾은 evidence는 context_used가 true여야 합니다")


def _metrics(gold, predicted):
    if not len(gold):
        return {"n": 0, "matches": 0, "agreement_rate": None, "macro_f1": None,
                "per_class_recall": {label: None for label in DIRECTIONAL}}
    recalls, f1s = {}, []
    for label in DIRECTIONAL:
        tp = sum(g == label and p == label for g, p in zip(gold, predicted))
        actual = sum(g == label for g in gold)
        guessed = sum(p == label for p in predicted)
        recall = tp / actual if actual else 0.0
        precision = tp / guessed if guessed else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        recalls[label] = recall
        f1s.append(f1)
    matches = sum(g == p for g, p in zip(gold, predicted))
    return {"n": len(gold), "matches": matches, "agreement_rate": matches / len(gold),
            "macro_f1": sum(f1s) / 3, "per_class_recall": recalls}


def analyze(source, predictions, gold=None, baseline=None):
    _check_predictions(source, predictions)
    merged = source[KEYS].merge(predictions, on=KEYS, validate="one_to_one")
    merged["eligible"] = merged.relevance.eq("related") & merged.sentiment.isin(DIRECTIONAL)
    eligible = merged[merged.eligible].copy()
    summary = {
        "rows": len(merged),
        "relevance_counts": {key: int(merged.relevance.eq(key).sum()) for key in sorted(RELEVANCE)},
        "sentiment_counts": {key: int(merged.sentiment.eq(key).sum()) for key in sorted(SENTIMENTS)},
        "coverage": len(eligible) / len(merged) if len(merged) else None,
        "eligible_count": len(eligible),
        "abstain_count": int(merged.sentiment.eq("판단유보").sum()),
        "mixed_count": int(merged.sentiment.eq("혼합").sum()),
        "gold": None,
        "baseline": None,
    }
    comparison = eligible[KEYS + ["relevance", "sentiment", "reason", "evidence", "context_used"]].copy()
    if gold is not None:
        _ids(gold, "gold")
        if "label" not in gold or not gold.label.isin(SENTIMENTS).all():
            raise ValueError("gold label 컬럼 또는 라벨 오류")
        source_keys = set(map(tuple, source[KEYS].astype(str).to_numpy()))
        gold_keys = set(map(tuple, gold[KEYS].astype(str).to_numpy()))
        if not gold_keys.issubset(source_keys):
            raise ValueError("gold ID가 source와 매칭되지 않습니다")
        gold_joined = eligible.merge(gold[KEYS + ["label"]], on=KEYS, how="inner", validate="one_to_one")
        human_rows = gold_joined[gold_joined.label.isin(DIRECTIONAL)]
        summary["gold"] = _metrics(human_rows.label.tolist(), human_rows.sentiment.tolist())
        summary["gold"]["eligible_gold_rows"] = len(human_rows)
        all_gold = merged.merge(gold[KEYS + ["label"]], on=KEYS, how="inner", validate="one_to_one")
        summary["gold"]["overall"] = {
            "rows": len(all_gold), "matches": int(all_gold.label.eq(all_gold.sentiment).sum()),
            "agreement_rate": float(all_gold.label.eq(all_gold.sentiment).mean()) if len(all_gold) else None,
        }
        comparison = comparison.merge(gold[KEYS + ["label"]], on=KEYS, how="left", validate="one_to_one")
        comparison["human_agreement"] = comparison.label.eq(comparison.sentiment)
        if baseline is not None:
            b = baseline[KEYS + ["sentiment"]].rename(columns={"sentiment": "baseline_sentiment"})
            _ids(b.rename(columns={"baseline_sentiment": "sentiment"}), "baseline")
            same = human_rows.merge(b, on=KEYS, how="inner", validate="one_to_one")
            if len(same) != len(human_rows):
                raise ValueError("baseline이 eligible gold ID 전체와 매칭되지 않습니다")
            all_baseline = all_gold.merge(b, on=KEYS, how="inner", validate="one_to_one")
            if len(all_baseline) != len(all_gold):
                raise ValueError("baseline이 gold ID 전체와 매칭되지 않습니다")
            summary["baseline"] = {
                "same_eligible_subset": _metrics(same.label.tolist(), same.baseline_sentiment.tolist()),
                "overall_gold": {"rows": len(all_baseline),
                                 "matches": int(all_baseline.label.eq(all_baseline.baseline_sentiment).sum()),
                                 "agreement_rate": float(all_baseline.label.eq(all_baseline.baseline_sentiment).mean())
                                 if len(all_baseline) else None}
            }
            comparison = comparison.merge(b, on=KEYS, how="left", validate="one_to_one")
    summary["interpretation"] = "모델과 gold의 일치 지표이며 객관적 정확도로 해석하지 않습니다."
    return summary, comparison


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--gold", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    state_root = (root / "state").resolve()
    output = args.output.resolve()
    if not output.is_relative_to(state_root) or output == state_root:
        raise ValueError("출력 폴더는 state 하위의 새 폴더여야 합니다")
    source = pd.read_csv(args.source, dtype=str, keep_default_na=False)
    predictions = _read_predictions(args.predictions)
    gold = pd.read_csv(args.gold, dtype=str, keep_default_na=False) if args.gold else None
    baseline = pd.read_csv(args.baseline, dtype=str, keep_default_na=False) if args.baseline else None
    if baseline is not None and not baseline.sentiment.isin(SENTIMENTS).all():
        raise ValueError("baseline sentiment 라벨 오류")
    summary, comparison = analyze(source, predictions, gold, baseline)
    inputs = {name: {"path": str(path.resolve()), "sha256": _sha(path)}
              for name, path in (("source", args.source), ("predictions", args.predictions),
                                 ("gold", args.gold), ("baseline", args.baseline)) if path}
    summary["inputs"] = inputs
    output.mkdir(parents=True, exist_ok=False)
    comparison.to_csv(output / "comparison.csv", index=False, encoding="utf-8-sig")
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    printable = {k: v for k, v in summary.items() if k != "inputs"}
    print(json.dumps(printable, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
