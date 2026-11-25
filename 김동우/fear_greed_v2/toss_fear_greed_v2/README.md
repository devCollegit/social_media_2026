# toss_fear_greed_v2

류창민 `toss_fear_greed`(devCollegit/social_media_2026, 커밋 3e5e57b)에 붙이는 보완 코드입니다.
보완 제안서(`../docs/공포탐욕지수_보완제안.html`)의 항목 번호(A·B·C)를 그대로 따릅니다.

- 기존 코드와 파일은 고치지 않습니다. 기존 폴더를 `--base`로 읽고 결과는 `--out` 폴더에만 씁니다.
- 규칙(전처리, 27일 기준 달, 20:00 거래일 경계, 0.7 기준점)은 기존 코드와 같습니다.
- GPU가 필요 없습니다. 판정 추가(A6·A7)는 Claude Code로 합니다.
- 글 입력은 류창민 님 최신 코드(11/25, 커밋 64f15aa)와 같은 김정기 수집기 형식 `data/raw/posts/<종목>.csv`를 읽습니다. 예전 `data/posts/<종목>.jsonl`도 읽습니다.

## 류창민 님 코드와의 관계 (11/25 기준)

류창민 님이 11/25 커밋(1a91b88, 28ba19f, 64f15aa)에서 지수·분석 쪽 보완을 직접 반영했습니다. 그래서 v2에서 새로 더하는 것은 주로 **모델(라벨링·분류) 쪽, 보정 집계·행동 축, C1 추가 통제, 예상 범위, 대시보드**입니다.

| 항목 | 류창민 코드에 반영됨 | v2에만 있음 |
|---|---|---|
| C1 시가 갭 | 날짜 FE, 지수 갭, 08시 전 글, 출범 전 구간 | 전일 시간외 수익률·미국 증시 통제 (`analysis_v2.py`) |
| C2~C8, B2·B3·B4·B6·B7 | 반영 (`analysis_extra.py`, `analysis_presentation.py`, `build_index.py`) | 같은 분석을 이중 FE 패키지(linearmodels)로 교차 확인 |
| C5 예측 비교 | 릿지·HistGB, DM 검정 | LightGBM, 다음 날 시가 방향, **개인 순매수 예상 범위(분위 회귀)** |
| A1~A5 모델 | 미반영 (0.7 기준 판정, 3분류, 본문만) | 확률 합, 5개 라벨, 부모 글·인증·보유·단어 특징, 확률 보정 |
| A6·A7 추가 판정 | 미반영 | 헷갈리는 글 묶음, 판정 일치도 |
| B1 보정 집계, B5 행동 축 | 미반영 (인증·보유는 표본에만) | PACC, 매수 인증 비율·보유 비율·좋아요 합 |
| 결론 UI | 미반영 | `ui/dashboard.html` |

## 바로 돌려 보기 (합성 데이터)

```bash
pip install -r requirements.txt
./run_all.sh --synthetic synthetic_run     # 합성 데이터 생성 → 전체 실행, 약 3분
```

`make_synthetic.py`는 기존 입력과 같은 형식(글은 김정기 수집기 CSV)의 가짜 데이터를 만듭니다(15종목, 327거래일, 글 27만 건).
분석이 찾아내야 할 관계를 일부러 심어 두었습니다. 예를 들어 밤 글과 시가 갭이 미국 증시·전일 시간외 가격을 함께 반영하게 해서, 통제하지 않으면 밤 글이 갭을 예측하는 것처럼 보이게 했습니다.
실행 예시는 `reports/synthetic_*.md`에 있습니다.

## 실제 데이터로 돌리기

```bash
./run_all.sh <toss_fear_greed 폴더> v2_out
```

`<toss_fear_greed 폴더>`에 필요한 파일

| 파일 | 만드는 기존 코드 | 쓰는 v2 단계 |
|---|---|---|
| `sample_30k_clean.json`, `sample_prev12_clean.json`, `labels/` | make_sample.py, make_batches.py, LLM 판정 | train_v2 |
| `data/raw/posts/<종목>.csv` (김정기 수집기 형식) | 수집 | apply_v2, make_active_batch |
| `trading_days.csv`, `ohlcv.json` | fetch_krx.py | build_index_v2 이후 전부 |
| `krx_index.json`, `krx_investor.json`, `krx_short.json` | fetch_krx_login.py | analysis_v2, predict_v2 |
| `us_overnight.csv` (date, us_ret) | **새로 필요**. 전날 밤 미국 지수 수익률(%) | C1 통제 (없으면 그 열만 빠짐) |
| `nxt_after.json` ({종목: {날짜: 그날 15:30~20:00 수익률 %}}) | **새로 필요**. 대체거래소 시간외 | C1 통제 (없으면 그 열만 빠짐) |
| `rotation_keywords.json` | rotation_keywords.py | 대시보드 대표 단어 (선택) |

원문(`data/raw/posts/`)을 넘기기 어려우면, 원문이 있는 PC에서 `apply_v2.py`까지 돌리고 `v2_out/apply_out_v2/`만 넘겨도 3단계부터 진행됩니다.
`build_index_v2.py --apply <기존 apply_out2 폴더>`로 기존 집계에도 지수·분석을 바로 적용할 수 있습니다. 이때 확률·행동 열이 없으니 판정 수를 대신 씁니다.

## 파일과 보완 항목

| 파일 | 항목 | 하는 일 | 결과 |
|---|---|---|---|
| `common.py` | — | 기존 규칙(전처리, 달, 거래일 경계) | |
| `featurize_v2.py` | A4, A5 | 본문 글자 + 본문 단어(kiwipiepy) + 부모 글 + 메타(대댓글·인증·보유) 특징 | |
| `train_v2.py` | A1~A5, 모델 표 1·2 | 기존 모델과 v2 후보 4개를 같은 채점 묶음으로 비교. 확률 보정 모델을 전체 판정으로 다시 학습 | `model_v2.joblib`, `quantify.json`, `reports/train_report.md` |
| `apply_v2.py` | A1, A4, B5 | 전체 글에 적용. 30분 칸마다 확률 합, 0.7 기준 판정 수, 대댓글·인증·보유 수 | `apply_out_v2/` |
| `build_index_v2.py` | B1~B7 | 확률 합 감성, 보정 집계(PACC), 평소 수준 쪽으로 당긴 감성, 관심도 통일, 60일 백분위, 잔차 심리, 행동 축, 0~100 지수·국면. 기존 S·20일 백분위도 같은 표에 | `index_v2/` |
| `analysis_v2.py` | C1~C4, C6~C8, B5 | 이중 고정효과 패널 회귀(linearmodels). 밤 글 → 시가 갭 통제 7단계, 지수 구간별 이후 성과, 거래량·변동폭·공매도, 반응 경로, 다음 날 수급, 급락일 위약 검정, 말과 행동 | `reports/analysis_report.md` |
| `predict_v2.py` | C5 | 시장 자료만 vs + 커뮤니티 변수, 날짜 순 확장 창, 릿지·LightGBM, Diebold–Mariano 검정. 다음 날 개인 순매수 예상 범위(분위 회귀) | `reports/predict_report.md`, `predictions/` |
| `make_active_batch.py` | A6 | 모델이 헷갈려 하는 글을 글 많은 종목에 더 배정해 뽑고 기존 묶음 형식으로 내보냄 | `active/batches/b40~` |
| `batch_task_active.md` | A6, A7 | Claude Code 판정 작업 지시 (기존 batch_task.md와 같은 절차) | |
| `label_agreement.py` | A7 | 두 판정의 일치율·κ·혼동표, 갈린 글을 상위 모델 재판정 묶음으로 | `agreement/` |
| `build_ui_data.py` | 결론 확장 | 대시보드용 `data.js` | `../ui/data.js` |
| `make_synthetic.py` | 검증 | 같은 형식의 합성 데이터 | |

## 판정을 늘리는 흐름 (A6 → A7 → 재학습)

1. `make_active_batch.py`로 `b40~` 묶음을 만들고, `sample_active_clean.json`과 `batches/`를 기존 폴더로 옮깁니다.
2. Claude Code에서 `batch_task_active.md` 절차로 `labels/b40.jsonl` …을 씁니다 (Haiku).
3. 일부 묶음을 다른 에이전트나 상위 모델로 다시 판정해 `labels_recheck/`에 쓰고 `label_agreement.py`로 일치도를 봅니다.
4. `train_v2.py`를 다시 돌리면 `sample_*_clean.json`과 새 라벨을 함께 학습합니다.

## 알아 둘 점

- 합성 데이터 결과는 코드가 동작하고 심어 둔 관계를 찾는지 확인한 것일 뿐입니다. 실제 수치는 실제 데이터로 돌려야 나옵니다.
- 합성 실행에서 A6가 고른 글의 약 90%가 대댓글이었습니다. 실제 데이터에서도 쏠리면 `make_active_batch.py`에 대댓글 상한을 두는 것이 좋습니다.
- 단어 특징(kiwipiepy)은 1,257만 건 적용 시간을 늘립니다. 시간이 부족하면 `train_v2.py --no-words`로 학습하세요.
- KcELECTRA 등 사전학습 모델(A9)은 GPU가 필요해 여기에 넣지 않았습니다. 같은 `train_report` 지표로 비교하면 됩니다.
