"""이미 수집한 실데이터·시세로 격리된 연동 또는 전체 분석을 실행한다.

이 스크립트는 네트워크 수집을 하지 않는다. 외부 분석 코드는 읽기/import만 사용한다.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd
import yaml


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--posts", type=Path, required=True)
    ap.add_argument("--market", type=Path, required=True)
    ap.add_argument("--stocks", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--until", choices=["merge", "report"], default="merge")
    ap.add_argument("--posts-only", action="store_true", help="거래일 집계에서 댓글 제외")
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = args.output.resolve()
    if not destination.is_relative_to(root):
        raise ValueError("연동 출력은 data_collection 안에 지정해야 합니다.")
    if destination.exists():
        raise ValueError("기존 결과를 덮어쓰지 않도록 새 output 경로를 지정하세요.")
    config = yaml.safe_load((root / "integration/config/pipeline.yaml").read_text())
    master = pd.read_csv(root / "data/raw/meta/stock_master.csv", dtype=str).set_index("stock_id")
    codes = args.stocks.split(",")
    config["scope"].update(stocks=[{"stock_id": c, "name": master.loc[c, "name"]} for c in codes],
                            start_date=args.start, end_date=args.end)
    config["collect"]["manual_csv"]["input_dir"] = str(args.posts.resolve())
    config["market"]["input_dir"] = str(args.market.resolve())
    config["aggregate"]["include_comments"] = not args.posts_only
    (destination / "config").mkdir(parents=True)
    path = destination / "config/pipeline.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
    pipeline = root.parents[1] / "조현호/toss_sentiment/run_pipeline.py"
    subprocess.run([sys.executable, str(pipeline), "-c", str(path), "run", "--until", args.until],
                   check=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))


if __name__ == "__main__":
    main()
