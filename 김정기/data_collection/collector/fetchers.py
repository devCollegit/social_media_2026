"""응답을 가져오는 쪽. 수집 로직(run.py)은 이 인터페이스만 안다.

- FixtureFetcher: 저장된 JSON 파일로 동작을 점검한다. 네트워크를 쓰지 않는다.
- TossFetcher   : 비로그인 공개 API. 실행 간격과 재시도는 RequestController가 담당한다.
"""

from __future__ import annotations

import json
import csv
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Protocol

from collector.http import PermanentError, TransientError
from collector.parser import parse_page, now_kst, unwrap


class Fetcher(Protocol):
    def list_page(self, stock_id: str, cursor: Any | None) -> dict[str, Any]:
        """종목 게시판 최신순 목록 1페이지. cursor=None 이면 첫 페이지."""

    def reply_page(self, stock_id: str, post_id: str, cursor: Any | None) -> dict[str, Any]:
        """글 1건의 댓글 1페이지."""


class FixtureFetcher:
    """<fixture_dir>/<stock_id>/list_start.json, list_<cursor>.json,
    replies_<post_id>_start.json, replies_<post_id>_<cursor>.json 을 읽는다."""

    def __init__(self, fixture_dir: Path) -> None:
        self.dir = fixture_dir
        self.calls: list[str] = []

    def _read(self, stock_id: str, name: str) -> dict[str, Any]:
        self.calls.append(f"{stock_id}/{name}")
        path = self.dir / stock_id / f"{name}.json"
        if not path.exists():
            raise PermanentError(f"fixture 없음: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_page(self, stock_id: str, cursor: Any | None) -> dict[str, Any]:
        return self._read(stock_id, f"list_{cursor if cursor is not None else 'start'}")

    def reply_page(self, stock_id: str, post_id: str, cursor: Any | None) -> dict[str, Any]:
        return self._read(stock_id, f"replies_{post_id}_{cursor if cursor is not None else 'start'}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _numeric(value: Any) -> str:
    text = str(value)
    if not re.fullmatch(r"[0-9]{1,30}", text):
        raise PermanentError("숫자 ID/커서 형식 오류")
    return text


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        if value.isdigit():
            return float(value)
        return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


class TossFetcher:
    """인증·쿠키·리다이렉트 없는 공개 GET. 원문은 메모리에만 보관한다.

    reply cursor는 (lastCommentId, lastLikeCount) 쌍이다. 합성 응답 및
    2026-10-21 실제 댓글 3페이지(31건)에서 연속 조회를 검증했다.
    """

    def __init__(self, master_path: Path, max_requests: int = 100, timeout: float = 25.0,
                 opener=None) -> None:
        if max_requests < 1 or timeout <= 0:
            raise ValueError("요청 예산과 timeout은 양수여야 합니다.")
        self.max_requests = max_requests
        self.requests = 0
        self.timeout = timeout
        self.opener = opener or urllib.request.build_opener(_NoRedirect())
        self.subjects = {}
        with master_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                code, isin = row.get("stock_id", ""), row.get("isin", "")
                if re.fullmatch(r"[0-9A-Z]{6}", code) and re.fullmatch(r"[A-Z]{2}[A-Z0-9]{10}", isin):
                    self.subjects[code] = isin

    def _get(self, path: str, params: dict) -> dict:
        if self.requests >= self.max_requests:
            raise PermanentError("전체 실행 요청 예산 소진")
        req = urllib.request.Request(
            "https://wts-cert-api.tossinvest.com" + path + "?" + urllib.parse.urlencode(params),
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0",
                     "Origin": "https://www.tossinvest.com", "Referer": "https://www.tossinvest.com/"},
        )
        self.requests += 1
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                if response.status != 200:
                    raise PermanentError("예상하지 않은 HTTP 상태")
                data = response.read(2_000_001)
        except urllib.error.HTTPError as exc:
            status = exc.code
            retry_after = _retry_after(exc.headers.get("Retry-After"))
            exc.close()
            if status == 429 or 500 <= status < 600:
                raise TransientError(f"HTTP {status}", retry_after=retry_after) from None
            raise PermanentError(f"HTTP {status}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            raise TransientError("네트워크 연결 오류") from None
        if len(data) > 2_000_000:
            raise PermanentError("응답 크기 제한 초과")
        try:
            payload = json.loads(data)
            if not isinstance(payload, dict):
                raise ValueError
            page = unwrap(payload)
            if not isinstance(page.get("results"), list) or not isinstance(page.get("hasNext"), bool):
                raise ValueError
            for item in page["results"]:
                _numeric(item["commentId"])
            # 기존 파서와 맞지 않는 응답은 원문·예외 문자열 없이 실패 처리한다.
            parse_page(page, now_kst(), "005930")
            if page["hasNext"]:
                _numeric(page.get("key"))
                if not page["results"]:
                    raise ValueError
        except (ValueError, TypeError, KeyError, AttributeError, PermanentError):
            raise PermanentError("커뮤니티 응답 형식 오류") from None
        return page

    def list_page(self, stock_id: str, cursor: Any | None) -> dict[str, Any]:
        subject = self.subjects.get(stock_id)
        if subject is None:
            raise PermanentError("종목 마스터에 유효한 ISIN 없음")
        params = {"subjectType": "STOCK", "subjectId": subject, "commentSortType": "RECENT"}
        if cursor is not None:
            params["lastCommentId"] = _numeric(cursor)
        return self._get("/api/v4/comments", params)

    def reply_page(self, stock_id: str, post_id: str, cursor: Any | None) -> dict[str, Any]:
        post_id = _numeric(post_id)
        params = {"replySortType": "NEWEST"}
        if cursor is not None:
            if not isinstance(cursor, (tuple, list)) or len(cursor) != 2:
                raise PermanentError("댓글 커서는 ID·공감 수 쌍이어야 합니다.")
            params.update(lastCommentId=_numeric(cursor[0]), lastLikeCount=_numeric(cursor[1]))
        page = self._get(f"/api/v2/comments/{post_id}/replies", params)
        if page["hasNext"]:
            try:
                likes = _numeric(page["results"][-1]["statistic"]["likeCount"])
            except (KeyError, TypeError, PermanentError):
                raise PermanentError("댓글 다음 페이지 공감 수 누락") from None
            page["key"] = (_numeric(page["key"]), likes)
        return page
