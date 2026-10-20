#!/usr/bin/env bash
# 연동 점검: 합성 커뮤니티 응답 → 수집기 → 조현호 파이프라인 (collect ~ merge)
# 시세는 data/raw/market 의 실제 데이터를 쓴다 (먼저 python -m market.cli prices 실행).
# 실행 위치: 김정기/data_collection
set -euo pipefail
PY=${PY:-.venv/bin/python}
STOCKS=005930,000660,035720

rm -rf integration/work integration/data integration/runs integration/output
$PY integration/make_synthetic_pages.py --out integration/work/fixtures \
    --stocks "$STOCKS" --start 2026-07-01 --end 2026-10-19
$PY -m collector.cli -c integration/collector.yaml run --stocks "$STOCKS"
$PY ../../조현호/toss_sentiment/run_pipeline.py -c integration/config/pipeline.yaml run --until merge
