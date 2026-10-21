# AGENTS.md — 김정기 데이터 수집 파이프라인 (Codex 인계 문서)

이 문서는 이 폴더(`김정기/data_collection/`)에서 일하는 코딩 에이전트(Codex 등)용 인계 문서다.
**작업을 시작하기 전에 끝까지 읽는다.** 사람용 상세 기록은 `docs/` 에 있다.

- 마지막 갱신: 2026-10-21 (Claude Code 세션에서 인계)
- 브랜치: `kimjunggee-data-collection` (fork 와의 동기화 여부는 `git status -sb` 로 확인)
- 사용자(담당자): 김정기 — 소셜미디어분석 수업 6조, 역할 A "커뮤니티 수집"

---

## 0. 한 줄 요약

토스증권 커뮤니티 글·댓글로 종목×거래일 공포탐욕지수를 만드는 팀 과제에서, **데이터 수집**을 맡은 폴더다.
최종 산출물은 팀원 조현호의 분석 파이프라인(`../../조현호/toss_sentiment/`)이 그대로 읽는 CSV다.
시세 수집과 수집기의 네트워크 외 부분은 끝났다. **토스증권 네트워크 수집은 이용 허락이 없어 보류 중이다.**

---

## 1. 절대 규칙 (어기면 안 됨)

1. **토스증권 서버에 요청하지 않는다.** `wts-*.tossinvest.com`, `www.tossinvest.com` 을 스크립트·curl·브라우저 자동화로 호출하지 않는다.
   점검용 한 번의 요청도 하지 않는다. 이유는 `docs/수집가능성_점검표.md` 5절. `TossFetcher` 구현, `collection_approved: true` 변경은
   **사용자가 "토스증권 허락을 받았다"고 명시하고 허락 조건을 점검표에 기록한 뒤에만** 한다. 우회 방법을 제안하거나 쓰지 않는다.
2. **이 폴더(`김정기/`) 밖은 수정하지 않는다.** 특히 `../../조현호/` 는 읽기·import만 한다. 호환 문제는 `docs/개발기록.md` 에 제안 패치로만 남긴다.
   레포 루트 `README.md`, 다른 팀원 폴더도 수정 금지.
3. **개인정보를 저장하지 않는다.** 닉네임, `userProfileId`, 프로필 URL, 자기소개, 작성자 뱃지(`author.badge`), 체결 수량·금액은
   파서(`collector/parser.py`)의 화이트리스트를 거치며 버려진다. 컬럼을 추가할 때도 이 원칙을 지키고 `tests/test_parser.py::test_no_personal_fields_leak` 를 통과시킨다.
4. **커밋 금지 대상:** `data/`, `logs/`, `state/`, `.venv/`, `.env`, 쿠키, 토큰, `integration/work|runs|output|data`. (`.gitignore` 에 있음. `git add` 전에 `git status` 로 확인)
5. **비밀값을 다루지 않는다.** KRX 계정(`KRX_ID`/`KRX_PW`), GitHub 토큰은 사용자가 직접 셸에 넣는다. 파일·커밋·로그에 쓰지 않는다. 대신 입력해 주지 않는다.
6. **서버 부담 금지.** 모든 수집은 순차 실행, 요청 간격 ≥1초(코드가 강제, 기본 2초). 병렬화하지 않는다.
7. **git:** `main` 에 직접 push 금지. 이 브랜치에서 작업하고 fork 로 push → PR. 커밋 메시지·문서는 **한국어**, 기술 용어는 영어 그대로.
   push·PR 생성처럼 밖으로 나가는 동작은 사용자 확인 후에 한다.
8. **단계마다 보고하고 확인받는다.** 사용자는 각 단계 결과(실행 출력 포함)를 보고 승인한 뒤 다음 단계로 가길 원한다.

---

## 2. 환경

```bash
cd 김정기/data_collection          # 모든 명령은 여기서 실행 (settings·collector·market 을 import 경로로 씀)
python3 -m venv .venv               # 이미 있으면 생략
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r ../../조현호/toss_sentiment/requirements.txt   # 연동 점검(integration/)용: statsmodels 등
.venv/bin/python -m pytest -q       # 기대값: 22 passed, 네트워크 불필요
```

- Python 3.13, pandas 2.3, pykrx 1.2.9, finance-datareader 0.9.x
- **네트워크가 필요한 명령:** `pip install`, `market.cli` (KRX/네이버/FDR). Codex 샌드박스에서 네트워크가 막혀 있으면 사용자에게 승인을 요청한다.
  pytest, `collector.cli` (fixture), `integration/run_check.sh` 는 시세 CSV가 이미 있으면 네트워크 없이 돈다.

### git remote

| 노트북 | 팀 레포 `devCollegit/social_media_2026` | 개인 fork `junggee9711/social_media_2026` |
| --- | --- | --- |
| 원래 노트북 | `origin` (읽기만, push 시 403) | `fork` |
| fork 를 clone 한 경우 | `upstream` | `origin` |

`git remote -v` 로 먼저 확인한다. push 는 항상 **fork** 쪽으로. `junggee9711` 은 팀 레포 쓰기 권한이 없다.

---

## 3. 구조

```
data_collection/
├── AGENTS.md              이 문서
├── config.yaml            경로·종목·기간·요청 간격·재시도·collection_approved
├── settings.py            설정 로딩(상대 경로 = config 파일 폴더 기준), 로깅, 종목 목록 파싱
├── market/
│   ├── sources.py         MarketSource: pykrx(수정주가) + KRX 로그인 시 시총·거래대금·지수·업종, 없으면 FDR 보조
│   └── cli.py             prices / master / candidates
├── collector/
│   ├── parser.py          응답 JSON → CSV 행. 화이트리스트, created_at 정규화, badge(BUY/SELL)
│   ├── store.py           PostStore(종목별 CSV upsert, 전부 str 로 읽고 씀), CollectorState(JSON), FailureLog(CSV)
│   ├── http.py            RequestController: 간격 ≥1초, 지수 백오프+지터, Retry-After, Transient/PermanentError
│   ├── fetchers.py        Fetcher Protocol, FixtureFetcher(파일), TossFetcher(미구현 — NotImplementedError)
│   ├── run.py             collect_stock: 최신순 페이지 넘김, 증분 cutoff, 댓글 수 증가한 글만 댓글 재요청
│   └── cli.py             cron 진입점. 실패 종목 있으면 exit 1
├── integration/           조현호 파이프라인 연동 점검 (합성 커뮤니티 + 실제 시세)
│   ├── run_check.sh       생성 → 수집 → run_pipeline.py run --until merge
│   ├── make_synthetic_pages.py
│   ├── collector.yaml
│   └── config/pipeline.yaml   조현호 설정 복사본 (기간·source·input_dir 만 변경)
├── tests/                 pytest 22건 + fixtures/toss/005930/*.json (합성, 실제 사용자 데이터 아님)
└── docs/
    ├── 수집가능성_점검표.md   약관·robots·API 조사, 응답 구조 관찰, 보류 결론
    ├── 개발기록.md           결정·발견한 문제·검증 결과 (날짜별로 이어 씀)
    └── 작업이관.md           사람용 이관 메모, PR 본문 초안
```

---

## 4. 출력 계약 (바꾸면 조현호 파이프라인이 깨질 수 있음)

### `data/raw/posts/<stock_id>.csv` → 조현호 `collect.source: manual_csv`

필수 `stock_id, post_id, parent_id, text, created_at` + 선택 `collected_at, source` + 추가 `badge, like_count, reply_count, is_holder`.
컬럼 순서는 `collector/parser.py::COLUMNS`. 추가 컬럼은 조현호 `s01_collect._normalize` 가 뒤에 보존한다.

- `created_at` 은 반드시 `YYYY-MM-DDTHH:MM:SS.ffffff+09:00` **고정 형식**. 원본은 나노초/초 단위가 섞여 오고,
  형식이 섞이면 pandas 가 일부를 NaT 로 만들어 조현호 쪽에서 글이 **조용히** 빠진다 (개발기록 3.1).
- `parent_id` 게시글은 빈 값(CSV에서 NaN 으로 읽힘), 댓글은 부모 `post_id`.
- `stock_id` 앞자리 0 유지 (문자열).
- 장 마감 15:30 기준 거래일 배정은 조현호 `aggregate` 가 한다. 수집기는 원본 시각만 정확히 남긴다.

### `data/raw/market/` → 조현호 `market.source: csv`

- `<stock_id>.csv`: `date, close(수정주가), volume, open, high, low, change(소수), value, market_cap, shares`
- `index.csv`: `date, close(config market.market_index, 기본 KOSPI), kospi_*, kosdaq_*`
- 수정주가는 소급 변경되므로 매 실행 전체 기간을 다시 받아 덮어쓴다 (이어 붙이지 않음).

### `data/raw/meta/`

`stock_master.csv` (`isin` = 토스 커뮤니티 `subjectId`, 예 `KR7005930003`), `candidates.csv` (예비 수집 후보 300).

---

## 5. 현재 상태 (2026-10-21)

| 단계 | 상태 |
| --- | --- |
| 1 수집 가능성 점검 | 완료. 약관에 금지·허용 모두 명시 없음, 공식 API 없음, 온라인 서비스 이용약관 제10조 리스크 → **보류**. 팀이 토스증권(support@tossinvest.com)에 문의 예정/진행 중 |
| 2 수집기 | 네트워크 외 전부 완료. `TossFetcher` 미구현(의도적) |
| 3 시세 | 완료. 단 **KRX 로그인이 없어** `value, market_cap, shares, krx_sector` 가 비어 있음 |
| 3 종목 선정 | 후보 300종목만. 일평균 글+댓글 ≥20건 측정은 커뮤니티 수집 후 |
| 4 연동 검증 | 합성 커뮤니티 + 실제 시세로 `run --until merge` 통과 (개발기록 7절). 실데이터는 수집 후 |
| PR | **아직 안 열림.** fork 브랜치에 push 된 상태 (최신 커밋 반영 여부는 `git status -sb`) |

---

## 6. 다음 작업 (우선순위 순, 각 항목 끝나면 사용자에게 보고)

1. **PR 생성 안내·리뷰 대응** — 본문 초안은 `docs/작업이관.md` 6절 (2026-10-21 연동 점검까지 반영됨).
   PR 생성은 사용자가 웹에서 한다 (gh CLI 없음). 리뷰 코멘트가 오면 반영 후 fork 로 push. 링크:
   `https://github.com/devCollegit/social_media_2026/compare/main...junggee9711:social_media_2026:kimjunggee-data-collection?expand=1`
2. **KRX 로그인 환경 검증** (사용자가 `KRX_ID/KRX_PW` 를 셸에 설정한 뒤) — `market.cli prices`, `master` 재실행.
   완료 기준: `value, market_cap, shares` 결측 0, `krx_sector` 채워짐. pykrx 반환 컬럼명이 코드 가정과 다르면 `market/sources.py` 수정 + 테스트 추가.
   (`get_market_cap` → `시가총액, 거래량, 거래대금, 상장주식수` / `get_index_ohlcv` → `종가, 거래량, 거래대금` / `get_market_sector_classifications` → `종목코드, 업종명` 가정. 로그인 상태로 실제 검증된 적 없음)
3. **market 모듈 테스트 추가** — 현재 테스트는 collector 위주. pykrx/FDR 을 monkeypatch 한 오프라인 테스트로
   `stock_daily` 컬럼·`change` 소수 변환·`KOSDAQ GLOBAL→KOSDAQ`·`candidates` 필터(보통주, 스팩·리츠 제외)를 검증.
4. **(허락 후에만)** 점검표에 허락 조건 기록 → `TossFetcher` 구현:
   목록 `GET https://wts-cert-api.tossinvest.com/api/v4/comments?subjectType=STOCK&subjectId=<ISIN>&commentSortType=RECENT` (+ 커서 `key`),
   댓글 요청 형식은 **아직 관찰하지 않았다** — 허락 범위 안에서 확인. 429/5xx → `TransientError(retry_after=...)`, 4xx → `PermanentError`.
   종목코드→ISIN 은 `stock_master.csv`. 그다음 후보 300종목 소량 예비 수집 → 일평균 ≥20건 종목 확정 → 실데이터로 `integration` 경로 재실행 → `06_감성_커버리지.csv` 보고.

하지 말 것: 조현호 코드 수정, 토스 요청, 대량·병렬 수집, 원문 데이터 커밋, 사용자 확인 없는 push.

---

## 7. 알려진 함정

- **pykrx 1.2.x 는 import 시 KRX 로그인을 시도**하고 실패하면 `KRX 로그인 실패...` 를 출력한다. 정상이다. 로그인 없이 되는 건 수정주가 OHLCV뿐.
- **FDR `StockListing('KRX')`** 은 시장을 `KOSDAQ GLOBAL` 로 표기하는 50종목이 있다 → `KOSDAQ` 으로 합침 (이미 처리).
- **조현호 `clean` 단계의 반복 홍보 판정**(같은 종목·같은 날 같은 문장 4회 이상 → 홍보)이 큰 게시판의 짧은 상용 문장을 지울 수 있다.
  합성 데이터에서 50% 제외됨. 실데이터에서 `02_정제_요약.csv` 제외 비율을 꼭 확인. 제안만 개발기록 7.1에 있음 (조현호 코드 수정 금지).
- **조현호 `s04_market` 은 지수 하나**로 모든 종목의 시장 수익률을 계산한다. 코스닥 종목도 KOSPI 로 통제됨. 제안 패치는 개발기록 4.1.
- **aggregate 는 시세의 마지막 거래일 15:30 이후 글을 버린다.** 매일 운영 시 시세 → 커뮤니티 → 파이프라인 순서로 돌리면 다음 날 배정된다.
- 시세를 장중에 받으면 당일 봉이 미완성. 16시 이후 실행.
- `RequestController(min_interval<1)` 은 ValueError. fixture 모드에서만 CLI가 생성 후 `min_interval=0` 으로 바꾼다.
- 증분 수집은 `commentId` 가 시간순으로 증가한다는 관찰에 기대고, 실제 cutoff 판단은 `created_at` 으로 한다.
- 종목코드 앞자리 0: CSV 읽을 때 항상 `dtype=str`.

---

## 8. 작업 마무리 체크리스트

```bash
.venv/bin/python -m pytest -q                 # 전부 통과
./integration/run_check.sh                    # 수집기·파서·스키마를 건드렸다면 (merge 까지 통과해야 함)
git status --short                            # data/ logs/ state/ integration/work 등이 없는지
```

- `docs/개발기록.md` 에 날짜 섹션으로 결정·발견·검증 결과를 이어 쓴다 (기존 형식: 표 + 짧은 문단, 한국어).
- 상태가 바뀌면 이 문서 5·6절과 `docs/작업이관.md` 3·4절을 갱신한다.
- 커밋 메시지: 한국어 제목 한 줄 + 빈 줄 + 본문 요점.
