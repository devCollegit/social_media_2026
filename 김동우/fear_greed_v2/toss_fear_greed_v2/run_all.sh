#!/usr/bin/env bash
# v2 전체 실행. 류창민 toss_fear_greed 폴더(입력)를 읽고 결과는 OUT 폴더에만 쓴다. 기존 파일은 고치지 않는다.
#   실제 데이터:  ./run_all.sh <toss_fear_greed 폴더> <결과 폴더>
#   합성 데이터:  ./run_all.sh --synthetic <작업 폴더>
set -euo pipefail
cd "$(dirname "$0")"
CRASH=-3
if [ "${1:-}" = "--synthetic" ]; then
  WORK="${2:-synthetic_run}"
  python3 make_synthetic.py --out "$WORK/data"
  BASE="$WORK/data"; OUT="$WORK/out"; LABEL="합성"; CRASH=-1.8
else
  BASE="${1:?toss_fear_greed 폴더를 지정하세요}"; OUT="${2:-v2_out}"; LABEL="실제"
fi
mkdir -p "$OUT/reports"
echo "== 1. 분류 모델 학습·비교 (A1~A5)";   python3 train_v2.py --base "$BASE" --out "$OUT"
echo "== 2. 전체 글 적용 (A1, A4, B5)";      python3 apply_v2.py --base "$BASE" --model "$OUT/model_v2.joblib" --out "$OUT"
echo "== 3. 지수 (B1~B7)";                   python3 build_index_v2.py --base "$BASE" --out "$OUT"
echo "== 4. 분석 (C1~C4, C6~C8, B5)";        python3 analysis_v2.py --base "$BASE" --out "$OUT" --crash "$CRASH"
echo "== 5. 예측 비교 (C5)";                  python3 predict_v2.py --base "$BASE" --out "$OUT"
echo "== 6. 추가 판정 묶음 (A6)";             python3 make_active_batch.py --base "$BASE" --model "$OUT/model_v2.joblib" --dest "$OUT/active" --n 5000
echo "== 7. 대시보드 데이터";                  python3 build_ui_data.py --base "$BASE" --out "$OUT" --dest "$OUT/data.js" --label "$LABEL"
echo "완료. 보고서: $OUT/reports/*.md, 대시보드 데이터: $OUT/data.js (ui/ 폴더로 복사하면 dashboard.html이 읽음)"
