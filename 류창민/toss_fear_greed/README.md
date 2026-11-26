# 토스증권 커뮤니티 공포탐욕지수

토스증권 종목 커뮤니티 글로 종목마다 매일 공포탐욕지수(0~100)를 만들고 KRX 주가·투자자별 수급과 맞대 본 코드다.
45종목(15섹터 × 3종목), 2024-10-28 ~ 2026-11-11, 글 약 1,260만 건을 분석했다.

원문 글, 판정 라벨, 학습된 모델 파일은 저장소에 올리지 않았다. 아래 형식으로 글 파일을 준비하면 처음부터 다시 돌릴 수 있다.

## 입력 데이터

`data/raw/posts/<stock_id>.csv` — 김정기 수집기(`김정기/data_collection/collector`)와 같은 형식, 한 줄에 글 하나

| 컬럼 | 내용 |
|---|---|
| `stock_id` | 종목코드 6자리 |
| `post_id` | 글 id |
| `parent_id` | 대댓글이면 부모 원글 id, 원글이면 빈 값 |
| `text` | 제목·본문 (멘션은 지움) |
| `created_at` | 작성 시각 (KST, ISO 8601) |
| `collected_at` | 수집 시각 |
| `source` | `tossinvest` |
| `badge` | 매수·매도 인증 `BUY`/`SELL` (없으면 빈 값) |
| `like_count`, `reply_count` | 공감 수, 대댓글 수 |
| `is_holder` | 작성자가 보유자면 1 |

종목 목록은 `sectors.json`에 있다.

## 실행 순서

| 단계 | 파일 | 하는 일 | 결과 |
|---|---|---|---|
| 1. 표본 | `make_sample.py` | 종목·월마다 56건씩 고르게 뽑는다. 대댓글엔 부모 글을 붙이고 작성자 정보는 넣지 않는다 | `sample_30k.jsonl` 등 |
| | `make_batches.py` | 멘션을 `@사용자`로 가리고 섞은 뒤 1,000건씩 묶는다 | `*_clean.json`, `batches/` |
| 2. LLM 판정 | `label_guide.md`, `batch_task.md` | 판정 기준(탐욕·공포·중립·무관·애매, 규칙 11개)과 작업 지시. Claude Haiku로 묶음마다 판정했다 | `labels/` |
| | `check_batch.py` | 판정 결과의 줄 수·id·라벨 값 검사 | |
| 3. 키워드 | `extract_keywords.py` | 같은 달 안에서 탐욕 글과 공포 글을 비교해 키워드를 뽑는다 | 키워드 사전 |
| | `score_heldout.py` | 키워드만으로 분류했을 때의 성능 채점 (정확도 68%) | |
| 4. 분류 모델 | `featurize.py` | 학습·적용 공통 전처리 (멘션 → `@사용자`, 종목명 → `종목`, 숫자 → `0`) | |
| | `lr_trial.py` | 글자 조각(2~4) TF-IDF + 로지스틱 회귀 시험. 확률 0.7 이상만 판정 (정확도 85%, 판정 28%) | |
| | `lr_prevyear.py` | 최근 1년으로 학습한 모델이 이전 1년에도 통하는지 비교 | |
| | `train_final.py` | 이전 모델 학습(본문 글자 조각만, 비교용): LLM 판정 29,000건 (최근 1년 23,000 + 이전 1년 6,000) | `model.joblib` |
| | `eval_quant.py` | 판정을 세는 방식 비교: 확률 합산, 5분류 확률 보정, 보정 집계 vs 확률 0.7 이상 개수. 낫지 않아 지금 방식 유지 | `eval_quant.json` |
| | `eval_features_cv.py` | 입력 추가 비교(5겹 교차검증): 부모 글 · 대댓글 · 매수/매도 인증 · 보유, 단어(형태소, '안·못' 부정 처리). 월별 탐욕 비율 오차 5.47 → 4.33%p | `eval_features_cv.json` |
| | `train_final2.py` | 이전 모델 학습(글자 조각 + 부모 글 + 단어 + 대댓글 · 인증 · 보유 → 로지스틱 회귀, 비교용) | `model_v2.joblib` |
| | `make_a6_batches.py`, `eval_a6_cv.py` | 애매한 글(확률 0.4~0.7) 4,000건 + 글 많은 종목 1,000건을 더 판정해 학습에 더하는 시험. 월별 탐욕 비율 오차가 줄지 않아 쓰지 않음 | `batches/a01~a05`, `eval_a6_cv.json` |
| | `a9_kcelectra.py` | **최종 모델.** 한국어 댓글로 사전학습된 KcELECTRA(`beomi/KcELECTRA-base-v2022`)를 LLM 판정 29,000건으로 미세조정. `speed`는 속도 측정, `fold0`~`fold4`는 5겹 채점, `final`은 전체 학습. 입력은 [대댓글][매수인증][매도인증][보유] 표시 + 본문 [SEP] 부모 글 | `model_a9/`, `a9_fold*.json` |
| | `a9_cv_summary.py` | 5겹 결과를 모아 이전 모델과 비교: 월별 탐욕 비율 오차 4.33 → 3.08%p, 판정 비율 35.7 → 59.4% | `a9_cv.json` |
| 5. 전체 적용 | `apply_all4.py` | 최종 모델로 전체 글을 판정해 종목·30분 단위로 집계(맥북 GPU로 약 6시간). 매수·매도 인증 글 수, 보유자 글 수와 그 탐욕·공포 수도 센다. 원문은 저장하지 않는다. 멈추면 끝난 달부터 이어서 돈다 | `apply_out4/` |
| | `apply_all3.py` | 이전 모델(`model_v2.joblib`)로 같은 집계 (비교용) | `apply_out3/` |
| | `apply_all2.py` | 이전 모델(`model.joblib`)로 같은 집계 (비교용) | `apply_out2/` |
| 6. 지수 | `build_index.py` | `apply_out4/`을 읽어 거래일 배정(20:00 경계), 감성 점수 S = (탐욕 − 공포 + 10 × 그 종목 평소 수준) ÷ (전체 + 10), 60거래일 백분위, 방향·강도 축(주성분 가중치), 국면 | `index_out/` |
| 7. KRX | `fetch_krx.py` | 종목 일봉과 거래일 달력 (로그인 불필요) | `ohlcv.json` 등 |
| | `fetch_krx_login.py` | 코스피·코스닥 지수, 투자자별 순매수, 공매도(2025-03-31 재개 이후) (환경 변수 `KRX_ID`·`KRX_PW` 필요) | `krx_index.json`, `krx_investor.json`, `krx_short.json` |
| 8. 분석 | `analysis_krx.py` | 밤사이 심리 → 다음 날 시가·장중(선행), 주가 → 심리(후행) | `krx_results.json` |
| | `analysis_presentation.py` | 글 수와 개인 수급, 투자자별 수급과 심리, 급락일 전후(무작위 날짜와 비교하는 위약 검정 포함), 주간·야간 비교(밤사이 미국 증시 통제 포함) | `pres_results.json` |
| | `analysis_rotation.py` | 분기·월별 섹터 순매수 이동, 대표 12종목 | `rotation_results.json` |
| | `rotation_keywords.py` | 섹터·분기별 토론글 대표 단어 (단어와 빈도만 저장) | `rotation_keywords.json` |
| | `analysis_extra.py` | 지수 구간별 이후 성과, 심리 → 다음 날 거래량·변동폭·공매도, 탐욕·공포 반응 경로, 잔차 심리, 다음 날 예측 비교, 커뮤니티 안 인증 · 보유 행동과 실제 수급, 알림 규칙 3개 검증, 다음 날 시가 방향 예측(장 열기 전 정보만) | `extra_results.json` |
| | `compare_a9.py` | 모델을 바꾸기 전후 결과 파일의 회귀 계수를 모두 비교해 부호·유의성이 바뀐 것을 찾는다 | `a9_compare.json` |
| 9. 발표자료 | `presentation/build_presentation.py` | 분석 결과로 HTML 발표자료를 만든다. 본편은 메시지와 핵심 숫자만, 검정 통계는 부록의 상세판에 둔다 | `.html` |
| | 시연 대시보드 | 발표 때 직접 보여 주는 화면. `김동우/fear_greed_v2/toss_fear_greed_v2/run_all.sh --from-apply <이 폴더> <이 폴더>/apply_out4 <결과 폴더>`로 `data.js`를 만들어 `김동우/fear_greed_v2/ui/`에 넣으면 열린다. 실제 데이터로 만든 파일은 저장소에 올리지 않는다 | |
| | `presentation/export_pdf.py` | HTML을 PDF로 바꾼다 | `.pdf` |

## 환경

Python 3.10. 사용한 패키지는 numpy, pandas, scipy, scikit-learn 1.7.2, statsmodels, joblib, kiwipiepy, pykrx, matplotlib, playwright, torch, transformers다. 최종 모델 학습·적용은 GPU(맥북은 MPS)가 있어야 시간이 적당하다.

시가 갭의 미국 증시 통제와 시가 방향 예측은 `us_overnight.csv`(한국 거래일마다 그날 09시 전에 끝난 미국 장 수익률)를 쓴다. `김동우/fear_greed_v2/toss_fear_greed_v2/fetch_us_overnight.py --base <이 폴더>`로 FRED 공개 종가에서 만든다.

```bash
uv run --python 3.10 --with 'torch>=2.6' --with 'transformers>=4.46,<5' --with numpy python a9_kcelectra.py final
```

## 참고

- `make_batches.py`의 단계는 실제 분석 때 한 번에 처리했다. 섞는 순서가 달라 묶음 구성은 원래와 같지 않을 수 있다.
- 감성 정답은 LLM 판정이고 사람 검수는 거치지 않았다.
