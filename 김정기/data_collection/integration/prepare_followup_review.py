"""기존 검수 표본 및 같은 본문·부모 글을 제외한 후속 미라벨 표본 생성."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import pandas as pd

from integration.prepare_context_review import attach_context

KEYS = ["stock_id", "post_id"]


def canonical(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(text))).strip()


def select_followup(clean, previous, size=300, seed=20261022):
    if clean.duplicated(KEYS).any() or previous.duplicated(KEYS).any():
        raise ValueError("중복 ID")
    # 이미 읽은 부모 글도 직접 평가 표본에서 제외한다.
    seen_text = {canonical(t) for col in ("text_norm", "parent_text") if col in previous
                 for t in previous[col] if canonical(t)}
    seen_ids = set(map(tuple, previous[KEYS].to_numpy()))
    eligible = clean[[tuple(k) not in seen_ids for k in clean[KEYS].to_numpy()]].copy()
    eligible = eligible[~eligible.text_norm.map(canonical).isin(seen_text)]
    # 후속 표본 자체에서도 같은 본문이 여러 번 나오는 것을 방지한다.
    eligible = eligible.sort_values(KEYS).assign(_text=eligible.text_norm.map(canonical))
    eligible = eligible[eligible._text != ""].drop_duplicates("_text").drop(columns="_text")
    if not 0 < size <= len(eligible):
        raise ValueError("후속 표본 크기가 후보 범위를 벗어납니다.")
    sampled = eligible.sample(n=size, random_state=seed)
    result = attach_context(sampled, clean)
    # 이전 검수 본문이 새 댓글의 부모 맥락으로 노출되지 않도록 한다.
    seen_body = {canonical(t) for t in previous.text_norm if canonical(t)}
    eligible_context = ~result.parent_text.map(canonical).isin(seen_body)
    if not eligible_context.all():
        # 같은 seed로 충분한 후보를 섞은 뒤 맥락까지 검사하여 표본을 고른다.
        all_context = attach_context(eligible.sample(frac=1, random_state=seed), clean)
        all_context = all_context[~all_context.parent_text.map(canonical).isin(seen_body)]
        if len(all_context) < size:
            raise ValueError("맥락 제외 후 후보 부족")
        result = all_context.head(size).copy()
    return result, len(eligible)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clean", type=Path, required=True)
    ap.add_argument("--previous", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--size", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20261022)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root / "data"):
        raise ValueError("검수 원문은 data 아래 저장하세요.")
    result, eligible = select_followup(
        pd.read_csv(args.clean, dtype=str, keep_default_na=False),
        pd.read_csv(args.previous, dtype=str, keep_default_na=False), args.size, args.seed)
    manifest = dict(rows=len(result), eligible_unique_texts_before_context_filter=eligible,
                    seed=args.seed, status="unlabeled; do not inspect labels or tune on this sample",
                    sampling="unique normalized texts after prior IDs/text/context exclusions; not original row distribution",
                    context=result.context_status.value_counts().to_dict(),
                    limitations=["동일 기간·동일 종목의 내부 후속 표본", "유사 문장·같은 대화방 맥락의 완전 독립성을 보장하지 않음"],
                    inputs=[dict(path=str(p.resolve()), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                            for p in [args.clean, args.previous]])
    args.output.mkdir(parents=True, exist_ok=False)
    result.to_csv(args.output / "review.csv", index=False, encoding="utf-8-sig")
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({k:v for k,v in manifest.items() if k != "inputs"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
