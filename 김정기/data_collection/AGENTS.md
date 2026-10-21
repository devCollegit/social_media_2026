# AGENTS.md — 김정기 데이터 수집 파이프라인 (Codex 인계 문서)

> 최신 진행 (2026-10-21): 저비용 LLM 전체 7,632건 분류·일별 집계·탐색 분석 완료. 지수에 반영할 수 있는 글 4,849건(63.5%). 현재 사후 진단에서 주가 예측 개선은 확인되지 않았습니다. 추가 사람 검수는 보류합니다. [전체 결과와 한계](docs/저비용LLM_전체분석.md)

이 문서는 이 폴더(`김정기/data_collection/`)에서 일하는 코딩 에이전트(Codex 등)용 인계 문서다.
**작업을 시작하기 전에 끝까지 읽는다.** 사람용 상세 기록은 `docs/` 에 있다.

이 문서는 프로젝트의 현재 작업 지침이며 불변 규칙이 아니다. 사용자의 후속 명시적 지시로
범위와 절차를 변경할 수 있으며, 변경 이유와 근거는 개발기록에 남긴다.
기술적 접근 가능성, 운영자의 이용 허락, 사용자의 작업 승인은 각각 구분해 기록한다.

- 마지막 갱신: 2026-10-21 (Codex 실수집·연동 완료 반영)
- 브랜치: `kimjunggee-data-collection` (origin(팀 원본 저장소)과의 동기화 여부는 `git status -sb` 로 확인)
- 사용자(담당자): 김정기 — 소셜미디어분석 수업 6조. 수집·코드·도구·문서를 제공한다. 최신 사용자 지시로 사람 검수는 김정기 역할에서 제외하며 팀이 검수 담당자를 지정한다.

---

## 0. 한 줄 요약

토스증권 커뮤니티 글·댓글로 종목×거래일 공포탐욕지수를 만드는 팀 과제에서, **수집부터 분석·검증·보고까지** 진행하는 작업 폴더다.
최종 산출물은 팀원 조현호의 분석 파이프라인(`../../조현호/toss_sentiment/`)이 그대로 읽는 CSV다.
시세 수집 및 비로그인 API 소규모 검증은 완료했다. 사용자 지시에 따라 단계별 승인을 생략하고
구현·검증을 자율 진행한다. 운영자의 이용 허락 여부와 사용자의 작업 지시는 구분한다.

---

## 1. 현재 작업 규칙 (변경 시 근거 기록)

1. **공개 데이터 범위에서 자율 진행한다.** 2026-10-21 사용자 지시로 기존의 사전 허락·단계별 승인 절차를 폐지했다.
   `TossFetcher` 구현과 오프라인·연동 검증은 추가 확인 없이 진행한다. 비로그인 공개 GET만 사용하며
   인증·접근 제한을 우회하지 않는다. 네트워크 실행에는 요청 예산과 간격을 적용한다.
   사용자 승인과 토스증권의 이용 허락을 혼동하지 않는다. 운영자의 허락을 받았다는 증거는 아직 없다.
2. **이 폴더(`김정기/`) 밖은 수정하지 않는다.** 특히 `../../조현호/` 는 읽기·import만 한다. 호환 문제는 `docs/개발기록.md` 에 제안 패치로만 남긴다.
   레포 루트 `README.md`, 다른 팀원 폴더도 수정 금지.
3. **개인정보를 저장하지 않는다.** 닉네임, `userProfileId`, 프로필 URL, 자기소개, 작성자 뱃지(`author.badge`), 체결 수량·금액은
   파서(`collector/parser.py`)의 화이트리스트를 거치며 버려진다. 본문 구조화 멘션도 제거한다. 자유 서술의 개인정보까지 완전 제거한 것은 아니므로 공유 전 검수한다. 컬럼을 추가할 때도 이 원칙을 지키고 `tests/test_parser.py::test_no_personal_fields_leak` 를 통과시킨다.
4. **커밋 금지 대상:** `data/`, `logs/`, `state/`, `.venv/`, `.env`, 쿠키, 토큰, `integration/work|runs|output|data`. (`.gitignore` 에 있음. `git add` 전에 `git status` 로 확인)
5. **비밀값을 다루지 않는다.** KRX 계정(`KRX_ID`/`KRX_PW`)은 사용자가 직접 셸 또는 이 폴더의 Git 제외 `.env`에 입력한다(사용자 승인으로 허용). 에이전트는 실제 인증값을 읽거나 출력·대신 입력하지 않는다. 인증값을 커밋·로그·문서에 남기지 않는다. GitHub 토큰은 계속 셸에서만 직접 설정한다. `.env.example`에는 빈 값만 둔다. 시세 수집은 `.env`의 KRX 항목만 자동으로 읽고 기존 셸 환경변수를 우선한다.
6. **서버 부담 금지.** 모든 수집은 순차 실행, 요청 간격 ≥1초(코드가 강제, 기본 2초). 병렬화하지 않는다.
7. **git:** `main` 에 직접 push 금지. 이 브랜치에서 작업하고 원본 저장소 origin으로 push한다. fork는 개발·push 대상으로 사용하지 않는다. PR은 요청 시에만 생성한다. 커밋 메시지·문서는 **한국어**, 기술 용어는 영어 그대로.
   커밋·push·PR은 해당 작업 요청 범위에 포함된 경우 수행한다.
8. **단계별 승인 없이 자율 진행한다.** 합리적으로 판단 가능한 구현·수정·테스트·문서 갱신을 이어서 수행하고 결과를 정리한다.

---

## 2. 환경

```bash
cd 김정기/data_collection          # 모든 명령은 여기서 실행 (settings·collector·market 을 import 경로로 씀)
python3 -m venv .venv               # 이미 있으면 생략
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r ../../조현호/toss_sentiment/requirements.txt   # 연동 점검(integration/)용: statsmodels 등
.venv/bin/python -m pytest -q       # 기대값: 96 passed, 네트워크 불필요
```

- Python 3.13, pandas 2.3, pykrx 1.2.9, finance-datareader 0.9.x
- **네트워크가 필요한 명령:** `pip install`, `market.cli` (KRX/네이버/FDR), toss 모드 `collector.cli`, `collector.activity`, `collector.replies`. 환경 제약이 있으면 원인과 미완료 범위를 기록한다.
  pytest, `collector.cli` (fixture), `integration/run_check.sh` 는 시세 CSV가 이미 있으면 네트워크 없이 돈다.

### git remote

| remote | 저장소 | 용도 |
| --- | --- | --- |
| origin | devCollegit/social_media_2026 | 개발 기준 및 push 대상 |
| fork | junggee9711/social_media_2026 | 과거 참조용, 자동 push하지 않음 |

2026-10-21 초대 수락 후 원본 저장소 브랜치 push 성공으로 쓰기 권한을 확인했다.
사용자 지시에 따라 앞으로 원본 저장소에서 개발한다.
현재 브랜치는 `origin/kimjunggee-data-collection`을 추적하며 기본 push 대상도 origin이다.
새 checkout에서도 `git remote -v`로 URL을 확인한다.

---

## 3. 구조

```
data_collection/
├── AGENTS.md              이 문서
├── config.yaml            기본 fixture 설정
├── config.research.yaml   검증된 두 종목의 명시적 네트워크 실행 설정
├── settings.py            설정 로딩(상대 경로 = config 파일 폴더 기준), 로깅, 종목 목록 파싱
├── market/
│   ├── sources.py         MarketSource: pykrx(수정주가) + KRX 로그인 시 시총·거래대금·지수·업종, 없으면 FDR 보조
│   └── cli.py             prices / master / candidates
├── collector/
│   ├── parser.py          응답 JSON → CSV 행. 화이트리스트, created_at 정규화, badge(BUY/SELL)
│   ├── store.py           PostStore(종목별 CSV upsert, 전부 str 로 읽고 씀), CollectorState(JSON), FailureLog(CSV)
│   ├── http.py            RequestController: 간격 ≥1초, 지수 백오프+지터, Retry-After, Transient/PermanentError
│   ├── fetchers.py        Fetcher Protocol, FixtureFetcher(파일), TossFetcher(비로그인 GET, 요청 예산)
│   ├── run.py             collect_stock: 최신순 페이지 넘김, 증분 cutoff, 댓글 수 증가한 글만 댓글 재요청
│   ├── activity.py        후보별 활동량 하한 측정·재개
│   ├── replies.py         저장된 부모의 댓글만 보충·재개
│   └── cli.py             cron 진입점. 네트워크 오류 시 중단, exit 1
├── integration/           조현호 파이프라인 연동 점검 (합성 커뮤니티 + 실제 시세)
│   ├── run_check.sh       합성 생성 → 수집 → run_pipeline.py run --until merge
│   ├── run_real_check.py  저장된 실데이터로 격리된 연동 실행
│   ├── make_synthetic_pages.py
│   ├── collector.yaml
│   └── config/pipeline.yaml   조현호 설정 복사본 (기간·source·input_dir 만 변경)
├── review_tool/           로컬 사람 검수 UI·서버·사용 안내
├── tests/                 pytest 96건 + fixtures/toss/005930/*.json (합성, 실제 사용자 데이터 아님)
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
| 1 수집 가능성 점검 | 비로그인 공개 API 실동작 확인. 사용자 지시로 제한된 실제 수집 진행. 운영자의 이용 허락 여부는 미확인(점검표 부록 D) |
| 2 수집기 | `TossFetcher` 구현 및 합성 응답·연동 검증 완료. 전체 96 passed. 기본 source는 fixture |
| 3 시세 | KRX 로그인 검증 완료(2026-10-21). 3종목 × 74거래일(07-01~10-20)의 `value, market_cap, shares` 결측 0. KOSPI/KOSDAQ 2,762종목 `krx_sector` 결측 0. KONEX 105종목은 업종 조회 대상 밖 |
| 3 종목 선정 | 300종목 하루 예비 조사: 통과 134, 추가 관찰 166. 기간 확장 검증 3종목 중 003670·450080은 112달력일 평균 ≥20건 확인. 267250은 관찰량 미달로 비교용 보존 |
| 4 연동 검증 | 실데이터 최종 2종목 7,759행 → merge 148행, 각 74/74일 커버리지 100%. 비교용 포함 3종목은 9,232행 → 222행. 개발기록 16절 |
| market 오프라인 테스트 | 컬럼·등락률·시장명·후보 필터·인증정보 출력 차단 검증 완료. 전체 테스트 96 passed |
| 비로그인 API 검증 | 새 fetcher의 3종목 목록·댓글 확인, 실제 댓글 3페이지 31건 중복 없이 확인. 후보 300종목 및 검증용 3종목 과거 수집으로 확장 |
| 후속 검증 | 멘션 제거 후 정제 7,632행, 전체8단계 재실행. HAC·순차 예측·AI 300건 검토 완료. 최신 경로는 개발기록19절 |
| 저비용 LLM | gpt-6-luna medium 3에이전트로 7,632건 전체 판정. source/prompt/결과 SHA·ID·인용 검증. 유효 판정 4,849건, 147/148일 유효 지수. `state/llm_full_20261021`, 일별 결과는 daily_corrected만 사용 |
| Git | 사용자 요청 범위는 이 브랜치의 코드·문서 커밋 및 원본 origin push. PR 생성 제외. 실제 동기화는 `git status -sb`로 확인 |
| 검수 역할 | 김정기는 수집·도구 제공. 사람 검수는 팀이 지정할 담당자 업무. 명세는 `docs/검수명세.md` |
| 사람 검수 도구 | `python -m review_tool.server` → `http://127.0.0.1:8768`. 저장·재개·보류·완료 CSV 내보내기 구현. 데이터는 Git 제외 |

---

## 6. 작업 상태 및 다음 작업 (단계별 승인 불필요)

2026-10-21 최신 지시: 첫 300건 사람 검수는 완료했고 추가 사람 검수는 보류한다. 저비용 LLM 전체 분석을 완료했으므로 결과와 한계를 연구 보고에 반영한다. 추가 라벨 입력을 요구하지 않는다.
기존 외부 소스는 읽기/import로 재사용하고 이 폴더에서 전체 분석을 수행한다.
`state/full_analysis_20261021`에 8단계 실행 완료. 검수 표본 300건은
`data/labels/review_20261021/review.csv`에 생성했다. 강건성 점검은 `state/robustness_20261021`에 완료했다(개발기록 18절). 후속 시계열 진단과 AI 60건 예비 검수까지 완료했다(개발기록 19절). 본문 멘션 제거 후 최신 결과는 `state/temporal_20261021/검증요약.md`에 있다. 300건 AI 검토는 완료했다(개발기록 20절). 사전과 일치 38.0%이며 사람 정답 정확도가 아니다. 첫 300건 단독 사람 검수 완료(58%, Macro-F1 0.3561). 후보 후속 검증은 미완료다. 최신 검수본은 `data/labels/human_review_context_20261021`이다.
첫 300건 사람 기준 일치율은 측정했고, 독립 평가자 간 일치도는 미측정이다. 두 종목·약 3.7개월의
예비 분석이며 원고의 3~5종목·약 6개월 설계와 차이가 있다.


0. **전체 LLM 분석 완료, 다음은 결과·한계의 연구 보고 반영** — `docs/저비용LLM_전체분석.md` 참고.
   추가 사람 검수는 재개 지시 전까지 보류한다. 전체 실행은 `state/llm_full_20261021`에 보존했다.
   종목·날짜 총량 검사를 통과한 `daily_corrected`와 `study`만 권위 결과로 사용한다.
   첫 `daily`는 시간대 구현 오류로 SUPERSEDED 표시했으며 사용하지 않는다.
   기존 사전 결과와 사람 검수 라벨은 유지한다. 세션 모델의 정확한 API snapshot·비용·temperature는 미확인이다.
   후속 자동화는 동일 지시문·입력 단위·사용량 기록을 고정하는 방향으로 설계하고, 추가 라벨링을 요구하지 않는다.

1. **PR 생성 안내·리뷰 대응(현재 요청 범위 밖)** — 본문 초안은 `docs/작업이관.md` 6절 (2026-10-21 연동 점검까지 반영됨).
   PR 생성은 사용자가 웹에서 한다 (gh CLI 없음). 리뷰 코멘트가 오면 반영 후 원본 origin으로 push. 링크:
   `https://github.com/devCollegit/social_media_2026/compare/main...kimjunggee-data-collection?expand=1`
2. **KRX 로그인 환경 검증** (사용자가 `KRX_ID/KRX_PW` 를 셸 또는 `.env`에 설정한 뒤) — `market.cli prices`, `master` 재실행.
   **2026-10-21 완료:** 인증 세션 성공, 두 명령 exit 0. 시세·KOSPI/KOSDAQ 업종 완료 기준 통과(개발기록 10절).
   완료 기준: `value, market_cap, shares` 결측 0, `krx_sector` 채워짐. pykrx 반환 컬럼명이 코드 가정과 다르면 `market/sources.py` 수정 + 테스트 추가.
   (`get_market_cap`, `get_index_ohlcv`, `get_market_sector_classifications` 반환 데이터는 현재 코드로 실제 로그인 후 처리 성공)
3. **market 모듈 테스트 추가 — 2026-10-21 완료(개발기록 11절).** pykrx/FDR 을 monkeypatch 한 오프라인 테스트로
   `stock_daily` 컬럼·`change` 소수 변환·`KOSDAQ GLOBAL→KOSDAQ`·`candidates` 필터(보통주, 스팩·리츠 제외)를 검증.
4. **TossFetcher 구현 완료(개발기록 14절).** 목록 v4의 `lastCommentId`, 댓글 v2의
   `replySortType=NEWEST`와 `(lastCommentId, lastLikeCount)` 커서를 지원한다.
   `--source toss`로 명시 실행하며 기본 source는 fixture. 종목별 기본 5페이지, 전체 기본 100요청
   (재시도·댓글 포함). 요청 예산/페이지 제한으로 중단하면 증분 체크포인트를 진행시키지 않는다.
   실제 목록·댓글 다음 페이지, 후보 300종목 예비 조사, 3종목 기간 확장 수집·연동까지 완료했다.
   게시글 5,651 + 댓글 3,581 = 9,232건. 112달력일 평균 기준으로 확인된 2종목만
   `data/raw/posts/003670.csv`, `450080.csv`에 최종 내보냈다(총 7,759행).
   `config.research.yaml`은 검증된 2종목용 명시 실행 설정이며, 기본 `config.yaml`은 fixture 설정이다.
   원자료·메타데이터·SHA 및 비교용 보존 경로는 `state/final_collection_manifest_20261021.json`과
   `docs/작업이관.md` 4절 참고. 실행 중인 수집 작업은 없다. 후속 운영은 기존 상태를 이용한 증분 실행이다.

하지 말 것: 조현호 코드 수정, 인증·접근 제한 우회, 무제한·병렬 수집, 원문 데이터 커밋.

---

## 7. 알려진 함정

- **pykrx 1.2.x 는 import 시 KRX 로그인을 시도**하고 인증 아이디를 print한다. `MarketSource`는 초기화·호출 stdout/stderr를 폐기하고 예외를 종류만 전달하여 인증값 노출을 막는다. 실제 로그인 성공은 변수 존재 여부와 별개다.
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
