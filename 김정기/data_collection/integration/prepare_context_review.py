"""예측·가격 없이 부모 글 맥락을 붙인 미라벨 검수 파일 생성."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import pandas as pd


def parent_key(value):
    # 외부 clean CSV의 결측 포함 숫자형 parent_id가 '123.0'으로 저장된 경우.
    # float 변환을 피하여 큰 정수 ID의 정밀도를 보존한다.
    value = str(value).strip()
    return value[:-2] if re.fullmatch(r"\d+\.0", value) else value


def attach_context(sample, clean):
    if clean.duplicated(["stock_id", "post_id"]).any():
        raise ValueError("중복 부모 후보 ID")
    lookup = clean.set_index(["stock_id", "post_id"]).text_norm.to_dict()
    result = sample[["stock_id", "post_id", "parent_id", "text_norm"]].copy()
    result["parent_id"] = result.parent_id.map(parent_key)
    result["parent_text"] = [lookup.get((r.stock_id, r.parent_id), "") if r.parent_id else ""
                             for r in result.itertuples()]
    result["context_status"] = ["parent_available" if r.parent_text else "parent_missing" if r.parent_id else "top_level"
                                for r in result.itertuples()]
    result["label"] = ""
    result["review_note"] = ""
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=Path, required=True)
    ap.add_argument("--clean", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root / "data"):
        raise ValueError("검수 원문은 Git 제외 data 아래 저장하세요.")
    result = attach_context(pd.read_csv(args.sample, dtype=str, keep_default_na=False),
                            pd.read_csv(args.clean, dtype=str, keep_default_na=False))
    args.output.mkdir(parents=True, exist_ok=False)
    result.to_csv(args.output / "review.csv", index=False, encoding="utf-8-sig")
    summary = {"rows": len(result), "context": result.context_status.value_counts().to_dict(),
               "status": "unlabeled; human review not performed",
               "inputs": [{"path": str(p.resolve()), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                          for p in [args.sample, args.clean]]}
    (args.output / "manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
