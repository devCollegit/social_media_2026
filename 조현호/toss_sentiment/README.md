# 토스증권 커뮤니티 감성 분석 파이프라인

중간보고서 원고(`토스증권_감성분석_중간보고서_원고.md`)에 적은 연구 설계를
그대로 실행 가능한 단계로 옮긴 파이프라인이다.
커뮤니티 텍스트의 감성을 거래일 단위로 집계해 수익률·거래량과의 시간적 관계를 검토한다.

## 설치

```bash
pip install -r requirements.txt
```

## 실행

```bash
python run_pipeline.py plan      # 무엇이 실행될지 먼저 확인
python run_pipeline.py run       # 전체 단계 실행
python run_pipeline.py status    # 단계별 산출물 상태 확인
```

```bash
python run_pipeline.py run --from analyze    # analyze 단계부터
python run_pipeline.py run --only sentiment  # 특정 단계만
python run_pipeline.py run --until merge     # merge 단계까지
python run_pipeline.py run --force           # 캐시 무시하고 재실행
python run_pipeline.py -c config/other.yaml run
```

산출물이 입력보다 새것이면 해당 단계는 자동으로 건너뛴다.
설정이나 앞 단계 결과를 바꾸면 그 뒤 단계만 다시 돌면 된다.

## 단계

| 단계 | 하는 일 | 주요 산출물 |
| --- | --- | --- |
| `collect` | 커뮤니티 텍스트 확보 | `data/raw/posts.csv` |
| `clean` | 중복·홍보 제거, 시간 기준 정리 | `data/interim/posts_clean.csv`, `02_정제_요약.csv` |
| `sentiment` | 감성 분류와 성능 검수 | `data/interim/posts_scored.csv`, `03_감성분류_성능.csv`, `03_혼동행렬.csv` |
| `market` | 수정주가·거래량·시장지수 확보 | `data/interim/market.csv` |
| `aggregate` | 거래일 정렬과 감성 지수 산출 | `data/interim/daily_sentiment.csv` |
| `merge` | 분석용 패널 구성 | `data/processed/panel.csv`, `06_감성_커버리지.csv` |
| `analyze` | 기술통계·시차상관·회귀·Granger | `07_*.csv`, `07_시차상관.png` |
| `report` | 결과 요약 작성 | `output/보고서_결과요약.md` |

실행할 때마다 `runs/<실행ID>/manifest.json` 에 설정 지문, 단계별 소요 시간,
행 수와 주요 지표가 남는다. 보고서 수치를 어떤 실행에서 얻었는지 추적할 수 있다.

## 데이터 넣는 방법

### 1) 커뮤니티 텍스트

`config/pipeline.yaml` 에서 `collect.source` 를 `manual_csv` 로 바꾸고
`data/raw/posts/` 에 CSV를 넣는다.

| 컬럼 | 필수 | 설명 |
| --- | --- | --- |
| `stock_id` | O | 종목 코드 6자리 |
| `post_id` | O | 게시물 식별자 |
| `parent_id` | | 댓글이면 부모 게시물 ID, 게시글이면 비움 |
| `text` | O | 본문 |
| `created_at` | O | 작성 시각 (한국 표준시) |
| `collected_at` | | 수집 시각 |

계정명·닉네임·프로필 등 분석에 불필요한 개인정보는 넣지 않는다.
포함되어 있어도 `clean` 단계가 `clean.drop_columns` 설정에 따라 제거한다.

### 2) 시장 자료

`market.source` 를 `csv` 로 두고 `data/raw/market/` 에 아래 파일을 넣는다.

- `<종목코드>.csv` — `date`, `close`(수정주가), `volume`
- `index.csv` — `date`, `close` (코스피·코스닥 지수)

`FinanceDataReader` 를 설치했다면 `market.source: fdr` 로 자동 수집할 수 있다.

### 3) 감성 평가 표본

`data/labels/gold.csv` 에 `post_id`, `label`(긍정/중립/부정) 두 컬럼을 넣으면
`sentiment` 단계가 클래스별 정밀도·재현율, macro-F1, 혼동행렬을 산출한다.
원고 계획대로 예비 텍스트 300건을 두 명이 독립 라벨링하고 불일치를 조정한 결과를 쓴다.

## 수집 전 확인 사항

`collect.collection_approved` 는 기본값이 `false` 다.
토스증권 웹사이트에 커뮤니티 화면이 있다는 사실이 과거 전체 자료의 수집 가능성이나
수집 허용을 뜻하지는 않는다. 본격 수집 전에 아래를 확인하고 결과를 점검표로 남긴다.

- 이용약관과 robots 규칙상 허용되는 접근 범위
- 접근 가능한 기간·페이지 범위
- 작성 시각 정보의 정밀도
- 원문 저장·재배포 가능 여부

이 저장소에는 토스증권을 자동으로 긁는 코드를 넣지 않는다.
확인이 끝난 뒤 허용된 범위의 수집기를 만들어 `manual_csv` 입력 형식으로 저장한다.

## 분석 설계 요약

- **감성 지수** `S = (긍정 글 수 - 부정 글 수) / 전체 분류 글 수`, 중립을 분모에 포함한다.
- **집계 구간** 직전 거래일 종가 이후 ~ 당일 종가. 비거래일 글은 다음 거래일에 배정한다.
  `aggregate.market_close` 로 종가 시각을 바꿀 수 있다.
- **결측 처리** 글이 없거나 `aggregate.min_posts` 미만인 날의 감성은 0이 아니라 결측으로 둔다.
- **시차 상관** `k = -5 ~ +5` 거래일에서 `corr(S(t), r(t+k))` 를 탐색하고
  Benjamini-Hochberg 로 다중검정을 보정한다. `k > 0` 이 감성 선행이다.
- **회귀** 과거 수익률, 시장 수익률, 글 수를 통제하고 Newey-West HAC 표준오차를 쓴다.
- **Granger** 정상성(ADF)을 먼저 확인하고 보조적으로만 해석한다.
- **민감도** `analyze.sensitivity_min_posts` 의 최소 글 수 기준별로 결과를 비교한다.

## 합성 표본으로 먼저 점검하기

기본 설정(`collect.source: sample`, `market.source: sample`)은 합성 데이터로 돈다.
실제 자료를 확보하기 전에 전체 절차와 산출물 형식을 점검하는 용도다.
합성 표본에는 감성이 다음 거래일 수익률을 약하게 앞서는 관계를 일부러 심어 두었고,
`analyze` 단계가 `k=+1` 에서 이를 탐지하는지로 파이프라인 동작을 확인한다.

합성 표본으로 얻은 수치는 연구 결과가 아니다.
`report` 단계가 결과 요약 맨 위에 경고 문구를 자동으로 붙인다.

## 해석 시 지키는 것

- 커뮤니티 이용자는 전체 투자자를 대표하지 않는다.
- 시차를 반복 탐색한 결과는 탐색적 분석이며 보정값을 함께 보고한다.
- 관계가 없다는 결과도 유효한 연구 결과로 보고한다.
- 유의한 결과라도 인과관계나 투자 수익을 보장하는 근거로 해석하지 않는다.

실행 중 기록된 한계와 확인 사항은 `output/보고서_결과요약.md` 6절에 모인다.
