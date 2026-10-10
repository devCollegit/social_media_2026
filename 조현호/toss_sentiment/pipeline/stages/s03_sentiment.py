"""03. 감성 분류와 검수.

사전 기반 기준선을 기본으로 두고, 한국어 감성 모델은 선택 경로로 둔다.
사람이 라벨링한 평가 표본이 있으면 클래스별 정밀도·재현율, macro-F1,
혼동행렬을 산출한다(원고 03장 "분류 및 검수 계획").
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import Config
from ..context import RunContext, StageError
from ..lexicon import NEGATIVE, NEGATORS, NEUTRAL_MARKERS, POSITIVE

NAME = "sentiment"
TITLE = "감성 분류와 성능 검수"

LABELS = ["긍정", "중립", "부정"]


def inputs(config: Config) -> list[Path]:
    paths = [config.data_path("interim", "posts_clean.csv")]
    gold = config.get("sentiment.gold_path")
    if gold:
        paths.append(config.resolve(gold))
    return paths


def outputs(config: Config) -> list[Path]:
    return [config.data_path("interim", "posts_scored.csv")]


def run(ctx: RunContext) -> dict[str, Any]:
    cfg = ctx.config
    df = ctx.read_table(inputs(cfg)[0], dtype={"stock_id": str, "post_id": str, "parent_id": str})

    method = cfg.get("sentiment.method", "lexicon")
    if method == "lexicon":
        scored = _score_lexicon(df, float(cfg.get("sentiment.neutral_band", 0.08)))
    elif method == "model":
        scored = _score_model(ctx, df)
    else:
        raise StageError(f"sentiment.method '{method}' 을 지원하지 않습니다. lexicon 또는 model.")

    scored["sentiment_method"] = method
    ctx.write_table(scored, outputs(cfg)[0])

    dist = scored["sentiment"].value_counts().to_dict()
    metrics: dict[str, Any] = {
        "method": method,
        "rows": int(len(scored)),
        "distribution": {k: int(v) for k, v in dist.items()},
        "mean_confidence": round(float(scored["confidence"].mean()), 4),
    }

    evaluation = _evaluate(ctx, scored)
    if evaluation:
        metrics["evaluation"] = evaluation
    else:
        ctx.note(
            "사람이 검수한 평가 표본(gold.csv)이 없어 분류 성능을 보고할 수 없다. "
            "원고 03장 계획대로 예비 텍스트 300건을 두 명이 독립 라벨링해야 한다."
        )
    return metrics


def _score_lexicon(df: pd.DataFrame, band: float) -> pd.DataFrame:
    scores, confidences = [], []
    for text in df["text_norm"].astype(str):
        score = _lexicon_score(text)
        scores.append(score)
        confidences.append(min(1.0, abs(score)))

    out = df.copy()
    out["sentiment_score"] = scores
    out["confidence"] = confidences
    out["sentiment"] = [
        "긍정" if s > band else ("부정" if s < -band else "중립") for s in scores
    ]
    return out


def _lexicon_score(text: str) -> float:
    pos = _match_score(text, POSITIVE)
    neg = _match_score(text, NEGATIVE)
    raw = pos - neg

    # 부정어가 있으면 방향을 약화하거나 뒤집는다.
    if any(n in text for n in NEGATORS):
        raw *= -0.6

    # 방향성이 없는 질문·정보 전달은 중립 쪽으로 끌어당긴다.
    if any(marker in text for marker in NEUTRAL_MARKERS):
        raw *= 0.35

    total = pos + neg
    return float(raw / total) if total else 0.0


def _match_score(text: str, table: dict[str, float]) -> float:
    return float(sum(weight for term, weight in table.items() if term in text))


def _score_model(ctx: RunContext, df: pd.DataFrame) -> pd.DataFrame:
    try:
        from transformers import pipeline as hf_pipeline
    except ImportError as exc:
        raise StageError(
            "sentiment.method=model 은 transformers 설치가 필요합니다.\n"
            "  pip install transformers torch  또는 config 에서 method 를 lexicon 으로 바꾸세요."
        ) from exc

    model_name = ctx.config.get("sentiment.model_name")
    ctx.logger.info("      모델 로딩: %s", model_name)
    classifier = hf_pipeline("sentiment-analysis", model=model_name, truncation=True)

    texts = df["text_norm"].astype(str).tolist()
    preds = classifier(texts, batch_size=32)

    mapping = {
        "positive": "긍정", "negative": "부정", "neutral": "중립",
        "label_0": "부정", "label_1": "중립", "label_2": "긍정",
    }
    out = df.copy()
    out["sentiment"] = [mapping.get(str(p["label"]).lower(), "중립") for p in preds]
    out["confidence"] = [float(p["score"]) for p in preds]
    sign = out["sentiment"].map({"긍정": 1, "중립": 0, "부정": -1})
    out["sentiment_score"] = sign * out["confidence"]
    return out


def _evaluate(ctx: RunContext, scored: pd.DataFrame) -> dict[str, Any] | None:
    """사람이 라벨링한 평가 표본과 비교한다."""
    gold_cfg = ctx.config.get("sentiment.gold_path")
    if not gold_cfg:
        return None
    gold_path = ctx.config.resolve(gold_cfg)
    if not gold_path.exists():
        return None

    gold = pd.read_csv(gold_path, dtype={"post_id": str})
    if "post_id" not in gold.columns or "label" not in gold.columns:
        ctx.note(f"{ctx.rel(gold_path)} 에 post_id, label 컬럼이 필요하다. 성능 평가를 건너뛴다.")
        return None

    merged = gold.merge(scored[["post_id", "sentiment"]], on="post_id", how="inner")
    if merged.empty:
        ctx.note("평가 표본의 post_id 가 분석용 데이터와 일치하지 않는다. 성능 평가를 건너뛴다.")
        return None

    per_class: dict[str, dict[str, float]] = {}
    f1s = []
    for label in LABELS:
        tp = int(((merged["label"] == label) & (merged["sentiment"] == label)).sum())
        fp = int(((merged["label"] != label) & (merged["sentiment"] == label)).sum())
        fn = int(((merged["label"] == label) & (merged["sentiment"] != label)).sum())
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        f1s.append(f1)
        per_class[label] = {
            "support": int((merged["label"] == label).sum()),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    confusion = pd.crosstab(
        merged["label"], merged["sentiment"], rownames=["정답"], colnames=["예측"]
    ).reindex(index=LABELS, columns=LABELS, fill_value=0)

    ctx.write_table(
        pd.DataFrame(per_class).T.rename_axis("클래스").reset_index(),
        ctx.config.output_path("tables", "03_감성분류_성능.csv"),
    )
    ctx.write_table(
        confusion.reset_index(), ctx.config.output_path("tables", "03_혼동행렬.csv")
    )

    accuracy = float((merged["label"] == merged["sentiment"]).mean())
    return {
        "n": int(len(merged)),
        "accuracy": round(accuracy, 4),
        "macro_f1": round(float(np.mean(f1s)), 4),
        "per_class": per_class,
    }
