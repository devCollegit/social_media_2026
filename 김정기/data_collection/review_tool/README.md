# 로컬 감성 검수 도구

본문과 부모 글을 읽고 사람이 라벨을 입력하는 도구다. AI 예측·라벨·가격은 표시하지 않는다.
원본 검수 CSV는 수정하지 않으며 모든 진행 결과는 Git 제외 `data/`에 저장한다.

## 실행

`김정기/data_collection` 폴더에서 실행한다.

```bash
.venv/bin/python -m review_tool.server
```

브라우저에서 `http://127.0.0.1:8768`을 연다. 서버 종료는 실행 터미널의 Ctrl+C.
같은 명령으로 다시 시작하면 저장된 결과를 이어서 읽는다. 다른 포트가 필요하면 `--port 8769`를 쓴다.
외부 호스트나 LAN에 노출하지 않는 로컬 도구다. 브라우저 주소는 localhost 대신 출력된 127.0.0.1을 사용한다.

기본 입력은 `data/labels/human_review_context_20261021/review.csv`이며 입력 원문은 Git에 없다.
다른 컴퓨터에서 사용할 때는 별도로 확보한 검수 CSV를 준비하고 경로를 지정한다.

```bash
.venv/bin/python -m review_tool.server \
  --input data/labels/human_review_context_20261021/review.csv \
  --output data/labels/human_review_session
```

입력에 필요한 컬럼: `stock_id, post_id, parent_id, text_norm, parent_text, context_status`.
`integration/prepare_context_review.py`로 생성할 수 있다. 외부 평가기가 post_id로 병합하므로
전체 표본에서 post_id가 유일한지 확인한다. 파일이 바뀌면 기존 검수와 섞지 않고 새 출력 경로를 사용한다.

## 사용 순서

1. 검수자 이름 또는 별칭을 입력한다.
2. 부모 글과 본문을 읽고 긍정·중립·부정을 선택한다. 키보드 1·2·3도 사용할 수 있다.
3. 맥락이 부족하면 보류를 표시하고 메모를 남긴다.
4. **저장하고 다음** 또는 Ctrl+Enter로 저장한다. 선택만 하고 이동하면 저장되지 않는다.
5. 전체·미완료·보류 보기로 돌아가 검수를 수정한다.
6. 모든 라벨을 저장하고 보류를 해결하면 **평가용 CSV 내보내기**가 활성화된다.

`progress.json`은 저장할 때마다 원자적으로 교체한다. 같은 출력 폴더를 쓰는 중복 프로세스는
차단하고, 다른 탭에서 먼저 저장했으면 덮어쓰지 않고 충돌을 알린다. 충돌 시 입력을 복사해 두고
새로고침한다. 브라우저 저장소에는 원문과 라벨을 따로 보관하지 않는다.

## 결과와 다음 분석

- 진행 상황: `data/labels/human_review_session/progress.json`
- 완료 결과: 같은 폴더의 `exports/gold-<시각>.csv` 및 검수자·SHA·입력 지문을 담은 JSON
- CSV 컬럼: `stock_id, post_id, label` (원문·메모 제외)

내보내기는 새 파일로 생성하고 브라우저 다운로드도 제공한다. 저장 경로를 화면에 표시한다.
사람이 입력한 것으로 기록하지만 도구 자체가 라벨의 정확성이나 독립 평가자 수를 보증하지는 않는다.
생성된 파일을 **자신의 분석 설정 복사본**의 `sentiment.gold_path`에 연결해 감성 성능을 평가한다.
이 도구는 기존 분석 설정을 자동 변경하거나 파이프라인을 재실행하지 않는다.

검수 표본 300건은 AI 진단에도 사용됐다. 모델 개선에 사용한 표본을 독립 평가 표본으로 재사용하지 않는다.
단독 검수라면 단독 검수라고 보고한다. 원문에는 자유 서술 개인정보가 남아 있을 수 있으므로 공개하지 않는다.

## 검증

```bash
.venv/bin/python -m pytest -q tests/test_review_tool.py
node --check review_tool/app.js
```

합성 표본으로 저장·재개·충돌·입력 변경·내보내기·HTTP 출처 검사를 검증한다.
실제 표본에 테스트 라벨을 저장하지 않는다.
