#!/usr/bin/env bash
# v2 전체 실행. 류창민 toss_fear_greed 폴더(입력)를 읽고 결과는 OUT 폴더에만 쓴다. 기존 파일은 고치지 않는다.
#   실제 데이터:        ./run_all.sh <toss_fear_greed 폴더> <결과 폴더>
#   기존 집계에서 바로: ./run_all.sh --from-apply <toss_fear_greed 폴더> <집계 폴더(예: apply_out3)> <결과 폴더>
#                       원문·라벨 없이 지수부터 돈다 (분류 모델 학습·적용·추가 판정 묶음은 건너뜀)
#   합성 데이터:        ./run_all.sh --synthetic <작업 폴더>
set -euo pipefail
cd "$(dirname "$0")"
CRASH=-3
FROM_APPLY=""
if [ "${1:-}" = "--synthetic" ]; then
  WORK="${2:-synthetic_run}"
  python3 make_synthetic.py --out "$WORK/data"
  BASE="$WORK/data"; OUT="$WORK/out"; LABEL="합성"; CRASH=-1.8
elif [ "${1:-}" = "--from-apply" ]; then
  BASE="${2:?toss_fear_greed 폴더를 지정하세요}"; FROM_APPLY="${3:?집계 폴더를 지정하세요 (예: <폴더>/apply_out3)}"; OUT="${4:-v2_out}"; LABEL="실제"
else
  BASE="${1:?toss_fear_greed 폴더를 지정하세요}"; OUT="${2:-v2_out}"; LABEL="실제"
fi
mkdir -p "$OUT/reports"
if [ -z "$FROM_APPLY" ]; then
  echo "== 1. 분류 모델 학습·비교 (A1~A5)";   python3 train_v2.py --base "$BASE" --out "$OUT"
  echo "== 2. 전체 글 적용 (A1, A4, B5)";      python3 apply_v2.py --base "$BASE" --model "$OUT/model_v2.joblib" --out "$OUT"
  APPLY="$OUT/apply_out_v2"
else
  echo "== 1~2. 건너뜀: 기존 집계 $FROM_APPLY 사용"
  APPLY="$FROM_APPLY"
fi
echo "== 3. 지수 (B1~B7)";                   python3 build_index_v2.py --base "$BASE" --out "$OUT" --apply "$APPLY"
echo "== 4. 분석 (C1~C4, C6~C8, B5)";        python3 analysis_v2.py --base "$BASE" --out "$OUT" --crash "$CRASH"
echo "== 5. 예측 비교 (C5)";                  python3 predict_v2.py --base "$BASE" --out "$OUT"
echo "== 6. 알림 규칙 검증";                  python3 alerts_v2.py --base "$BASE" --out "$OUT"
echo "== 7. 30분 장중 지수";                  python3 intraday_v2.py --apply "$APPLY" --out "$OUT"
if [ -z "$FROM_APPLY" ]; then
  echo "== 8. 추가 판정 묶음 (A6)";           python3 make_active_batch.py --base "$BASE" --model "$OUT/model_v2.joblib" --dest "$OUT/active" --n 5000
fi
echo "== 9. 대시보드 데이터";                  python3 build_ui_data.py --base "$BASE" --out "$OUT" --dest "$OUT/data.js" --label "$LABEL"
echo "완료. 보고서: $OUT/reports/*.md, 대시보드 데이터: $OUT/data.js (ui/ 폴더로 복사하면 dashboard.html이 읽음)"
