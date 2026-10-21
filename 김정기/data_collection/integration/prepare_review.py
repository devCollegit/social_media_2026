"""정제된 텍스트에서 재현 가능한 단순무작위 검수 표본을 만든다."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20261021)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root / "data"):
        raise ValueError("원문 검수 표본은 Git 제외 data 폴더에 저장하세요.")
    frame = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    if not 0 < args.size <= len(frame):
        raise ValueError("표본 수는 1 이상, 입력 행 수 이하여야 합니다.")
    if frame.duplicated(["stock_id", "post_id"]).any():
        raise ValueError("중복 ID가 있는 입력입니다.")
    sample = frame.sort_values(["stock_id", "post_id"]).sample(
        n=args.size, random_state=args.seed
    )[["stock_id", "post_id", "parent_id", "text_norm"]].copy()
    # 예측값과 이후 가격을 숨겨 검수자가 분류 결과에 영향받지 않도록 한다.
    sample["label"] = ""
    sample["review_note"] = ""
    args.output.mkdir(parents=True, exist_ok=False)
    sample.to_csv(args.output / "review.csv", index=False, encoding="utf-8-sig")
    (args.output / "manifest.json").write_text(json.dumps({
        "input": str(args.input.resolve()),
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "population": len(frame), "size": args.size, "seed": args.seed,
        "sampling": "simple_random_without_replacement",
        "labels": ["긍정", "중립", "부정"],
        "status": "unlabeled",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"검수 표본 {len(sample)}건 생성: {args.output}")


if __name__ == "__main__":
    main()
