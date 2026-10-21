"""커뮤니티 응답 JSON → manual_csv 행 변환.

응답 구조는 2026-10-19 WTS 화면 관찰 결과(점검표 3절)를 따른다.
필요한 필드만 화이트리스트로 꺼내므로 닉네임·프로필 ID·체결 수량·금액 같은
구조화된 작성자 정보와 본문 멘션 표식을 제거한다. 자유 서술에 포함된 개인정보를
모두 탐지하는 것은 아니므로 외부 공유 전 별도 검수가 필요하다.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

KST = timezone(timedelta(hours=9))

# 조현호 collect.manual_csv 필수·선택 컬럼 + 이 수집기가 덧붙이는 선택 컬럼
REQUIRED = ["stock_id", "post_id", "parent_id", "text", "created_at"]
OPTIONAL = ["collected_at", "source"]
EXTRA = ["badge", "like_count", "reply_count", "is_holder"]
COLUMNS = REQUIRED + OPTIONAL + EXTRA

SOURCE = "tossinvest"
BADGE_VALUES = {"BUY": "BUY", "SELL": "SELL"}

_FRACTION = re.compile(r"(\.\d+)")
MENTION = re.compile(r"#\[[^\]\r\n]*\]\(\d+\)")


def redact_mentions(text: str) -> str:
    """본문의 토스 멘션 닉네임·프로필 식별자를 제거한다."""
    return MENTION.sub(" ", text).strip()


def normalize_created_at(value: str) -> str:
    """ISO 문자열을 KST 'YYYY-MM-DDTHH:MM:SS.ffffff+09:00' 고정 형식으로 맞춘다.

    응답은 나노초(9자리)와 초 단위가 섞여 온다. 한 컬럼에 형식이 섞이면 pandas 가
    첫 값으로 형식을 추론해 나머지를 NaT 로 만들 수 있으므로 형식을 하나로 고정한다.
    """
    if not value:
        raise ValueError("createdAt 이 비어 있습니다.")
    s = value.strip().replace("Z", "+00:00")
    # 파이썬 fromisoformat 은 소수점 6자리까지만 받으므로 잘라 낸다.
    s = _FRACTION.sub(lambda m: m.group(1)[:7], s, count=1)
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST).isoformat(timespec="microseconds")


def stock_id_from(item: dict[str, Any], fallback: str | None = None) -> str:
    code = ((item.get("board") or {}).get("stockCode") or "").strip()
    if code.startswith("A"):
        code = code[1:]
    if re.fullmatch(r"[0-9A-Z]{6}", code) or code.isdigit():
        return code.zfill(6)
    if fallback:
        return str(fallback).zfill(6)
    raise ValueError(f"종목코드를 찾을 수 없습니다: commentId={item.get('commentId')}")


def text_from(item: dict[str, Any]) -> str:
    msg = item.get("message") or {}
    title = (msg.get("title") or "").strip()
    body = (msg.get("message") or "").strip()
    if title and body:
        return redact_mentions(f"{title}\n{body}")
    return redact_mentions(title or body)


def badge_from(item: dict[str, Any]) -> str:
    """매수·매도 체결 인증. 인증이 없는 글은 빈 문자열."""
    execution = item.get("execution") or {}
    return BADGE_VALUES.get(str(execution.get("orderSide") or "").upper(), "")


def parse_item(item: dict[str, Any], collected_at: str, fallback_stock_id: str | None = None) -> dict[str, Any] | None:
    """글 1건을 행으로 바꾼다. 본문이 없거나 정상 상태가 아닌 글은 None."""
    if item.get("status", "NORMAL") != "NORMAL":
        return None
    text = text_from(item)
    if not text:
        return None
    stat = item.get("statistic") or {}
    parent = item.get("parentId")
    holding = (item.get("holding") or {}).get("shareHoldingStatus")
    return {
        "stock_id": stock_id_from(item, fallback_stock_id),
        "post_id": str(item["commentId"]),
        "parent_id": "" if parent in (None, "", 0) else str(parent),
        "text": text,
        "created_at": normalize_created_at(item["createdAt"]),
        "collected_at": collected_at,
        "source": SOURCE,
        "badge": badge_from(item),
        "like_count": int(stat.get("likeCount") or 0),
        "reply_count": int(stat.get("replyCount") or 0),
        "is_holder": 1 if holding == "HOLDING" else 0,
    }


def parse_page(page: dict[str, Any], collected_at: str, fallback_stock_id: str | None = None):
    """목록 응답 1페이지 → (행 목록, 다음 커서, 다음 페이지 여부, 건너뛴 수)."""
    rows, skipped = [], 0
    for item in page.get("results") or []:
        row = parse_item(item, collected_at, fallback_stock_id)
        if row is None:
            skipped += 1
        else:
            rows.append(row)
    return rows, page.get("key"), bool(page.get("hasNext")), skipped


def unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    """응답이 {"result": {...}} 로 한 번 감싸져 오는 경우를 벗긴다."""
    if "results" not in payload and isinstance(payload.get("result"), dict):
        return payload["result"]
    return payload


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")
