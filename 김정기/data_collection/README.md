# 데이터 수집 (김정기)

토스증권 커뮤니티 글·댓글과 KRX 시세를 모아 조현호 파이프라인(`조현호/toss_sentiment/`) 입력 형식으로 저장한다.

| 구성 | 상태 |
| --- | --- |
| `market/` 시세·지수·종목 마스터 | 동작함 |
| `collector/` 커뮤니티 파서·저장·증분·재시도 | 동작함 (저장된 합성 JSON으로만 점검) |
| `collector/` 토스증권 네트워크 호출 | **보류.** 이용 허락 확인 전 ([수집가능성 점검표](docs/수집가능성_점검표.md)) |

## 설치

```bash
cd 김정기/data_collection
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### KRX 로그인 (선택)

pykrx 1.2.x는 거래대금·시가총액·상장주식수·지수·업종을 조회할 때 KRX 정보데이터시스템 로그인이 필요하다.
<https://data.krx.co.kr> 에서 무료 회원가입 후 **본인이 직접** 환경변수로 넣는다. 파일에 적거나 커밋하지 않는다.

```bash
export KRX_ID=...
export KRX_PW=...
```

로그인이 없으면 수정주가 OHLCV만 pykrx로 받고, 지수·종목 마스터는 FinanceDataReader로 받으며
`value`, `market_cap`, `shares` 컬럼은 비워 둔다.

## 실행

### 시세

```bash
.venv/bin/python -m market.cli prices                       # config.yaml 의 종목·기간
.venv/bin/python -m market.cli prices --stocks 005930,000660 --start 2026-07-01
.venv/bin/python -m market.cli prices --stocks-file data/raw/meta/candidates.csv
.venv/bin/python -m market.cli master                       # 종목 마스터
.venv/bin/python -m market.cli candidates --top 300         # 커뮤니티 예비 수집 후보
```

장중에 실행하면 당일 봉이 미완성 값으로 들어간다. 장 마감(15:30) 이후, 16시 이후 실행을 권장한다.

### 커뮤니티

```bash
.venv/bin/python -m collector.cli run                       # 증분 수집 (설정의 source, 기본 fixture)
.venv/bin/python -m collector.cli run --stocks 005930 --full
.venv/bin/python -m collector.cli run --since 2026-10-01T00:00:00+09:00
```

`--source toss` 는 `config.yaml` 의 `community.collection_approved: true` 가 아니면 실행되지 않는다.

cron 예시 (평일 16:10):

```cron
10 16 * * 1-5  cd <repo>/김정기/data_collection && .venv/bin/python -m market.cli prices >> logs/cron.log 2>&1
20 16 * * 1-5  cd <repo>/김정기/data_collection && .venv/bin/python -m collector.cli run >> logs/cron.log 2>&1
```

실패한 종목이 있으면 종료 코드 1로 끝난다.

### 조현호 파이프라인 연동 점검

```bash
./integration/run_check.sh     # 산출물은 integration/ 아래에만 생긴다 (git 제외)
```

### 테스트

```bash
.venv/bin/python -m pytest -q
```

네트워크를 쓰지 않는다. `tests/fixtures/toss/` 의 합성 JSON(관찰한 응답 구조를 본뜬 가짜 데이터)을 사용하며,
조현호 파이프라인 `s01_collect` 의 정규화 함수를 읽기 전용으로 불러와 출력 CSV가 통과하는지도 확인한다.

## 출력 스키마

### `data/raw/posts/<종목코드>.csv` — 조현호 `collect.source: manual_csv` 입력

| 컬럼 | 필수 | 설명 |
| --- | --- | --- |
| `stock_id` | O | 종목코드 6자리 |
| `post_id` | O | 글·댓글 ID (토스 `commentId`) |
| `parent_id` | O | 댓글이면 부모 글 ID, 게시글이면 빈 값 |
| `text` | O | 제목 + 줄바꿈 + 본문 (제목이 없으면 본문만) |
| `created_at` | O | 작성 시각, `YYYY-MM-DDTHH:MM:SS.ffffff+09:00` 고정 형식 (KST) |
| `collected_at` | | 수집 시각 (KST) |
| `source` | | `tossinvest` |
| `badge` | 추가 | 매수·매도 체결 인증. `BUY` / `SELL` / 빈 값 |
| `like_count` | 추가 | 공감 수 (마지막 수집 시점 값) |
| `reply_count` | 추가 | 댓글 수 (마지막 수집 시점 값) |
| `is_holder` | 추가 | 작성 시점 해당 종목 보유 표시("주주") 1/0 |

닉네임·프로필 ID·프로필 사진·자기소개·작성자 자산 뱃지·체결 수량·금액은 **파서 단계에서 버리고 저장하지 않는다.**
같은 `post_id` 가 다시 수집되면 행을 늘리지 않고 공감 수 등 최신 값으로 바꾼다.

### `data/raw/market/` — 조현호 `market.source: csv` 입력

| 파일 | 컬럼 |
| --- | --- |
| `<종목코드>.csv` | `date`, `close`(수정주가), `volume`, `open`, `high`, `low`, `change`(소수), `value`(거래대금), `market_cap`, `shares` |
| `index.csv` | `date`, `close`(설정 `market.market_index`, 기본 KOSPI), `kospi_close/volume/value`, `kosdaq_close/volume/value` |

### `data/raw/meta/`

| 파일 | 내용 |
| --- | --- |
| `stock_master.csv` | `stock_id`, `isin`(토스 커뮤니티 종목 식별자와 같음), `name`, `market`, `industry`(KSIC 업종), `krx_sector`(KRX 로그인 시), `listing_date`, `*_snapshot`(조회 시점 시총·주식수·거래대금) |
| `candidates.csv` | 보통주 중 거래대금·시총 상위 N종목. 커뮤니티 예비 수집 후보 |

## 구조

```
data_collection/
├── config.yaml            경로, 종목, 기간, 요청 간격·재시도 설정
├── settings.py            설정 로딩·로깅
├── market/
│   ├── sources.py         pykrx / FinanceDataReader 소스
│   └── cli.py             prices / master / candidates
├── collector/
│   ├── parser.py          응답 JSON → CSV 행 (개인정보 화이트리스트 제거, 시각 정규화)
│   ├── store.py           종목별 CSV upsert, 증분 상태, 실패 기록
│   ├── http.py            요청 간격(≥1초)·지수 백오프 재시도
│   ├── fetchers.py        FixtureFetcher (네트워크 없음) / TossFetcher (보류)
│   ├── run.py             종목 1개 수집 절차 (페이지 넘김, 증분 중단, 댓글)
│   └── cli.py             cron 진입점
├── integration/           조현호 파이프라인 연동 점검 (합성 커뮤니티 + 실제 시세 → collect~merge)
│   ├── run_check.sh       한 번에 실행
│   ├── make_synthetic_pages.py
│   ├── collector.yaml
│   └── config/pipeline.yaml  조현호 설정 복사본 (기간·입력 경로만 변경)
├── tests/                 pytest + 합성 fixture
└── docs/
    ├── 수집가능성_점검표.md
    └── 개발기록.md
```

`data/`, `logs/`, `state/`, `.env`, `.venv/` 는 `.gitignore` 로 제외한다.
