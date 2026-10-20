"""연동 점검용 합성 커뮤니티 응답 생성기.

2026-10-19 관찰한 목록·댓글 응답 구조를 본떠 기간 전체의 JSON 페이지를 만든다.
실제 토스증권 데이터가 아니며, 수집기 → 조현호 파이프라인 경로가 실데이터 규모에서
형식상 깨지지 않는지 확인하는 용도로만 쓴다. 감성·수익률 관계는 심어 두지 않았다.

    python integration/make_synthetic_pages.py --out integration/work/fixtures \
        --stocks 005930,000660,035720 --start 2026-07-01 --end 2026-10-19
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

KST = timezone(timedelta(hours=9))
PAGE_SIZE = 20

POSITIVE = ["반등 간다 추가 매수", "실적 기대된다 우상향", "저점 잡았다 수익 구간", "수급 들어온다 상승 가자"]
NEGATIVE = ["손절했다 더 빠질 듯", "물렸다 하락 무섭다", "고점에 물려서 손실", "실적 부진 비중 줄인다"]
NEUTRAL = ["오늘 거래량 얼마였나요", "공시 떴네요 확인해 보세요", "배당 기준일 아시는 분", "차트 질문 드립니다"]


def _created(dt: datetime, rng: np.random.Generator) -> str:
    # 실제 응답처럼 나노초 표기와 초 단위 표기를 섞는다.
    if rng.random() < 0.3:
        return dt.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(rng.integers(0, 10**9)):09d}+09:00"


def _item(cid: int, stock: str, created: str, text: str, rng, parent=None, reply_count=0) -> dict:
    side = rng.choice(["BUY", "SELL"]) if parent is None and rng.random() < 0.08 else None
    return {
        "type": "USER_COMMENT", "commentId": cid,
        "author": {"userProfileId": int(rng.integers(1, 10**6)), "nickname": "합성닉네임",
                   "profilePictureUrl": "https://example.invalid/p.png", "type": "USER", "badge": None},
        "parentId": parent,
        "message": {"title": "", "message": text, "representEmoji": ""},
        "board": {"topic": "합성", "subjectId": f"KR7{stock}00X", "subjectType": "STOCK", "stockCode": f"A{stock}"},
        "statistic": {"likeCount": int(rng.poisson(2)), "replyCount": reply_count, "readCount": 0},
        "execution": {"orderSide": side, "quantity": 1, "amountKrw": 1} if side else None,
        "holding": {"shareHoldingStatus": "HOLDING" if rng.random() < 0.6 else None},
        "createdAt": created, "status": "NORMAL",
    }


def build(stock: str, start: date, end: date, rng: np.random.Generator, out: Path, base_id: int) -> int:
    posts, replies = [], {}
    cid = base_id
    day = start
    while day <= end:
        n = int(rng.poisson(12 if day.weekday() >= 5 else 30))
        stamps = sorted(datetime(day.year, day.month, day.day, tzinfo=KST)
                        + timedelta(seconds=int(s)) for s in rng.integers(7 * 3600, 24 * 3600, n))
        for ts in stamps:
            cid += 1
            pool = [POSITIVE, NEGATIVE, NEUTRAL][int(rng.integers(0, 3))]
            n_rep = int(rng.integers(1, 4)) if rng.random() < 0.2 else 0
            posts.append(_item(cid, stock, _created(ts, rng), str(rng.choice(pool)), rng, reply_count=n_rep))
            reps = []
            for _ in range(n_rep):
                cid += 1
                rts = ts + timedelta(minutes=int(rng.integers(1, 180)))
                reps.append(_item(cid, stock, _created(rts, rng), str(rng.choice(NEUTRAL + POSITIVE)), rng, parent=posts[-1]["commentId"]))
            if reps:
                replies[posts[-1]["commentId"]] = reps
        day += timedelta(days=1)

    d = out / stock
    d.mkdir(parents=True, exist_ok=True)
    newest_first = posts[::-1]
    cursor = "start"
    for i in range(0, len(newest_first), PAGE_SIZE):
        chunk = newest_first[i:i + PAGE_SIZE]
        has_next = i + PAGE_SIZE < len(newest_first)
        page = {"results": chunk, "key": chunk[-1]["commentId"], "totalCount": len(posts), "hasNext": has_next}
        (d / f"list_{cursor}.json").write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
        cursor = str(chunk[-1]["commentId"])
    for pid, reps in replies.items():
        page = {"results": reps, "key": reps[-1]["commentId"], "hasNext": False}
        (d / f"replies_{pid}_start.json").write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
    return cid


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--stocks", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--seed", type=int, default=20261020)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    out = Path(args.out)
    next_id = 300_000_000
    for stock in args.stocks.split(","):
        next_id = build(stock, date.fromisoformat(args.start), date.fromisoformat(args.end), rng, out, next_id)
        print(stock, "pages:", len(list((out / stock).glob("list_*.json"))),
              "reply files:", len(list((out / stock).glob("replies_*.json"))))


if __name__ == "__main__":
    main()
