# 토스증권 커뮤니티 공포탐욕지수

토스증권 종목 커뮤니티 글로 종목마다 매일 공포탐욕지수(0~100)를 만들고 KRX 주가·투자자별 수급과 맞대 본 코드다.
45종목(15섹터 × 3종목), 2024-10-28 ~ 2026-11-11, 글 약 1,257만 건을 분석했다.

원문 글, 판정 라벨, 학습된 모델 파일은 저장소에 올리지 않았다. 아래 형식으로 글 파일을 준비하면 처음부터 다시 돌릴 수 있다.

## 입력 데이터

`data/posts/<종목코드>.jsonl` — 한 줄에 글 하나

| 필드 | 내용 |
|---|---|
| `post_id` | 글 id |
| `parent_post_id` | 대댓글이면 부모 원글 id, 원글이면 `null` |
| `published_at` | 작성 시각 (ISO 8601, 시간대 포함) |
| `holding` | 작성자 보유 여부 표시 (없으면 `null`) |
| `execution_side` | 매수·매도 인증 `BUY`/`SELL` (없으면 `null`) |
| `title`, `body` | 제목·본문 |

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
| | `train_final.py` | 최종 학습: LLM 판정 29,000건 (최근 1년 23,000 + 이전 1년 6,000) | `model.joblib` |
| 5. 전체 적용 | `apply_all2.py` | 전체 글을 판정해 종목·30분 단위로 집계. 원문은 저장하지 않는다 | `apply_out2/` |
| 6. 지수 | `build_index.py` | 거래일 배정(20:00 경계), 감성 점수 S = (탐욕 − 공포 + 10 × 그 종목 평소 수준) ÷ (전체 + 10), 60거래일 백분위, 방향·강도 축(주성분 가중치), 국면 | `index_out/` |
| 7. KRX | `fetch_krx.py` | 종목 일봉과 거래일 달력 (로그인 불필요) | `ohlcv.json` 등 |
| | `fetch_krx_login.py` | 코스피·코스닥 지수, 투자자별 순매수, 공매도(2025-03-31 재개 이후) (환경 변수 `KRX_ID`·`KRX_PW` 필요) | `krx_index.json`, `krx_investor.json`, `krx_short.json` |
| 8. 분석 | `analysis_krx.py` | 밤사이 심리 → 다음 날 시가·장중(선행), 주가 → 심리(후행) | `krx_results.json` |
| | `analysis_presentation.py` | 글 수와 개인 수급, 투자자별 수급과 심리, 급락일 전후, 주간·야간 비교 | `pres_results.json` |
| | `analysis_rotation.py` | 분기·월별 섹터 순매수 이동, 대표 12종목 | `rotation_results.json` |
| | `rotation_keywords.py` | 섹터·분기별 토론글 대표 단어 (단어와 빈도만 저장) | `rotation_keywords.json` |
| | `analysis_extra.py` | 지수 구간별 이후 성과, 심리 → 다음 날 거래량·변동폭·공매도, 탐욕·공포 반응 경로, 잔차 심리, 다음 날 예측 비교 | `extra_results.json` |
| 9. 발표자료 | `presentation/build_presentation.py` | 분석 결과로 HTML 발표자료를 만든다 | `.html` |
| | `presentation/export_pdf.py` | HTML을 PDF로 바꾼다 | `.pdf` |

## 환경

Python 3.10. 사용한 패키지는 numpy, pandas, scipy, scikit-learn 1.7.2, statsmodels, joblib, kiwipiepy, pykrx, matplotlib, playwright다.

```bash
uv run --python 3.10 --with scikit-learn==1.7.2 --with joblib python train_final.py
```

## 참고

- `make_batches.py`의 단계는 실제 분석 때 한 번에 처리했다. 섞는 순서가 달라 묶음 구성은 원래와 같지 않을 수 있다.
- 감성 정답은 LLM 판정이고 사람 검수는 거치지 않았다.
