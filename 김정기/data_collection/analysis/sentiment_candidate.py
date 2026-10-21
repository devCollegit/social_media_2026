"""중립으로 분류된 글의 명시적 주가·매매 표현을 보완하는 실험 후보.

기존 300건의 오류 진단을 참고한 개발용 규칙이다. 독립 평가 전에는 기본 분류를 대체하지 않는다.
이모지·욕설·응원만으로 종목 방향을 추측하지 않고, 부모 글의 감정도 상속하지 않는다.
"""
import argparse
from pathlib import Path
import re

import pandas as pd

VERSION = "neutral_phrase_v1"
POSITIVE = ("양전", "상치", "사고싶", "올라와주니좋", "지금가격괜")
NEGATIVE = ("마이너스", "음전", "괜히샀", "또빠지", "계속빠지", "왜떨어", "계좌녹")


def classify(text, baseline):
    if baseline not in ("긍정", "중립", "부정"):
        raise ValueError("허용되지 않은 기준 라벨")
    if baseline != "중립":
        return baseline, "baseline_directional"
    normalized = re.sub(r"\s+", "", str(text))
    pos = any(term in normalized for term in POSITIVE)
    neg = any(term in normalized for term in NEGATIVE)
    if pos and not neg:
        return "긍정", "explicit_positive_phrase"
    if neg and not pos:
        return "부정", "explicit_negative_phrase"
    return "중립", "mixed_phrases" if pos and neg else "no_added_phrase"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scored", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root / "state"):
        raise ValueError("실험 결과는 state 아래 저장하세요.")
    if args.output.exists():
        raise ValueError("기존 파일을 덮어쓰지 않습니다.")
    frame = pd.read_csv(args.scored, dtype=str, keep_default_na=False)
    frame = frame[["stock_id", "post_id", "text_norm", "sentiment"]].copy()
    frame["baseline_sentiment"] = frame.sentiment
    results = [classify(r.text_norm, r.sentiment) for r in frame.itertuples()]
    frame["sentiment"] = [r[0] for r in results]
    frame["candidate_reason"] = [r[1] for r in results]
    frame["candidate_version"] = VERSION
    # confidence/score는 재계산하지 않았으므로 출력하지 않는다.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"후보 생성: {len(frame)}행, 변경 {(frame.sentiment != frame.baseline_sentiment).sum()}행")


if __name__ == "__main__":
    main()
