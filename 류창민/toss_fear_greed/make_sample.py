"""LLM 판정용 표본 뽑기. 섹터 15개 × 종목 3개 × 12개월, 종목·월마다 56건씩 고르게 뽑는다(원글·대댓글은 실제 비율대로 무작위).
대댓글은 부모 원글 본문을 같이 붙인다. 작성자 정보는 넣지 않는다. 한 달 = 전월 27일 ~ 당월 27일 전(KST).

입력: data/posts/<종목코드>.jsonl — 수집한 토스증권 커뮤니티 글, 한 줄에 글 하나
  post_id          글 id
  parent_post_id   대댓글이면 부모 원글 id, 원글이면 null
  published_at     작성 시각(ISO 8601, 시간대 포함. 예: 2026-04-15T16:14:00+09:00)
  holding          작성자 보유 여부 표시(없으면 null)
  execution_side   매수·매도 인증(BUY/SELL, 없으면 null)
  title, body      제목·본문 (본문이 빈 글은 쓰지 않는다)
출력: 한 줄에 표본 하나 — id, sector, stock_code, stock_name, post_id, is_reply, published_at(UTC로 저장 — 뒤 단계가 +9시간 해서 KST로 씀), holding, execution_side, text(최대 400자), parent_text(최대 300자)

사용: python make_sample.py [시작연도=2025] [id 접두어=s] [출력파일=sample_30k.jsonl]
  최근 1년: 2025 s sample_30k.jsonl / 그 전 1년: 2024 t sample_prev12.jsonl"""
import json, os, random, sys
from datetime import datetime, timedelta, timezone

D = os.path.dirname(os.path.abspath(__file__))  # 이 폴더
POSTS = os.path.join(D, "data", "posts")
KST = timezone(timedelta(hours=9))
S = json.load(open(f"{D}/sectors.json"))
Y0 = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
PFX = sys.argv[2] if len(sys.argv) > 2 else "s"
OUT = sys.argv[3] if len(sys.argv) > 3 else "sample_30k.jsonl"
PER = 56  # 종목·월당
_ym = [(Y0, 10), (Y0, 11), (Y0, 12)] + [(Y0 + 1, m) for m in range(1, 10)]
MONTHS = [(datetime(y, m, 27, tzinfo=KST), datetime(y + (m == 12), m % 12 + 1, 27, tzinfo=KST)) for y, m in _ym]
random.seed(0)

def text_of(p, n):
    t = ((p.get("title") or "").strip() + " " if (p.get("title") or "").strip() else "") + (p.get("body") or "")
    return t[:n]

def load(code):
    path = os.path.join(POSTS, f"{code}.jsonl")
    if not os.path.exists(path): return []
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    rows = [r for r in rows if (r.get("body") or "").strip()]
    for r in rows: r["_t"] = datetime.fromisoformat(r["published_at"]).astimezone(KST)
    return rows

out = open(f"{D}/{OUT}", "w", encoding="utf-8"); n = 0
for sector, stocks in S.items():
    for code, name in stocks.items():
        rows = load(code)
        parent = {r["post_id"]: r for r in rows if not r.get("parent_post_id")}
        for a, b in MONTHS:
            pool = [r for r in rows if a <= r["_t"] < b]
            for r in random.sample(pool, min(PER, len(pool))):
                n += 1
                pp = parent.get(r.get("parent_post_id"))
                out.write(json.dumps({"id": f"{PFX}{n:05d}", "sector": sector, "stock_code": code, "stock_name": name,
                    "post_id": r["post_id"], "is_reply": bool(r.get("parent_post_id")), "published_at": r["_t"].astimezone(timezone.utc).isoformat(),
                    "holding": r.get("holding"), "execution_side": r.get("execution_side"),
                    "text": text_of(r, 400), "parent_text": text_of(pp, 300) if pp else None}, ensure_ascii=False) + "\n")
    print(sector, n, flush=True)
out.close()
