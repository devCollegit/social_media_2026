"""네이버 검색 오픈 API 수집기 (블로그 / 카페글 / 지역).

환경변수 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` 이 필요하다.
표준 라이브러리(urllib)만 사용하므로 별도 설치가 필요 없다.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator

from ..models import Document, QueryTask
from .base import BaseCollector, CollectorError, CollectorUnavailable

API_BASE = "https://openapi.naver.com/v1/search"
MAX_DISPLAY = 100  # 네이버 API 한 번에 가져올 수 있는 최대 건수


class NaverSearchCollector(BaseCollector):
    """엔드포인트만 바꿔 블로그·카페글·지역을 모두 처리한다."""

    endpoint = "blog"
    min_interval = 0.1

    def __init__(self, client_id: str | None = None, client_secret: str | None = None) -> None:
        self.client_id = client_id or os.getenv("NAVER_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("NAVER_CLIENT_SECRET", "")

    @property
    def name(self) -> str:  # type: ignore[override]
        return f"naver_{self.endpoint}"

    def available(self) -> tuple[bool, str]:
        if not (self.client_id and self.client_secret):
            return False, "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수가 필요합니다."
        return True, ""

    def _request(self, query: str, display: int, start: int) -> dict:
        params = urllib.parse.urlencode(
            {"query": query, "display": display, "start": start, "sort": "sim"}
        )
        req = urllib.request.Request(
            f"{API_BASE}/{self.endpoint}.json?{params}",
            headers={
                "X-Naver-Client-Id": self.client_id,
                "X-Naver-Client-Secret": self.client_secret,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # 4xx/5xx
            body = exc.read().decode("utf-8", "ignore")[:200]
            raise CollectorError(f"{self.name} HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise CollectorError(f"{self.name} 네트워크 오류: {exc.reason}") from exc

    def _to_document(self, item: dict, task: QueryTask) -> Document:
        return Document(
            source=self.name,
            query=task.query,
            segment=task.segment,
            title=item.get("title", ""),
            text=item.get("description", ""),
            url=item.get("link", ""),
            place_name=item.get("title", "") if self.endpoint == "local" else "",
            region=item.get("address", "") or task.region,
            category=item.get("category", ""),
            lang=str(task.extra.get("lang", "ko")),
            published_at=item.get("postdate"),
            raw=item,
        )

    def collect(self, task: QueryTask) -> Iterator[Document]:
        ok, reason = self.available()
        if not ok:
            raise CollectorUnavailable(reason)

        remaining = task.limit
        start = 1
        while remaining > 0:
            display = min(MAX_DISPLAY, remaining) if self.endpoint != "local" else min(5, remaining)
            payload = self._request(task.query, display, start)
            items = payload.get("items", [])
            if not items:
                return
            for item in items:
                yield self._to_document(item, task)
            remaining -= len(items)
            start += len(items)
            if start > 1000 or self.endpoint == "local":
                return


class NaverBlogCollector(NaverSearchCollector):
    endpoint = "blog"


class NaverCafeCollector(NaverSearchCollector):
    endpoint = "cafearticle"


class NaverLocalCollector(NaverSearchCollector):
    """지역(장소) 검색. 한 번에 최대 5건만 반환된다."""

    endpoint = "local"
