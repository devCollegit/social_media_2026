"""네이버 검색 API 수집기 (블로그 / 카페글 / 지역).

두 가지 백엔드를 지원한다.

- ``apihub`` (기본값): NAVER API HUB. 네이버 클라우드 플랫폼 콘솔에서 발급한다.
- ``developers``: 구 네이버 개발자센터. 2026-07-31 부로 신규 신청이 차단됐고
  2027-06-30 에 기존 키까지 사용이 중단된다. 기존 키 보유자만 쓸 수 있다.

환경변수 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` 이 필요하며
`NAVER_API_BACKEND` 로 백엔드를 고를 수 있다.
표준 라이브러리(urllib)만 사용하므로 별도 설치가 필요 없다.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator

from ..models import Document, QueryTask
from .base import BaseCollector, CollectorError, CollectorUnavailable

DEFAULT_BACKEND = "apihub"

BACKENDS = {
    # NAVER API HUB (네이버 클라우드 플랫폼)
    "apihub": {
        "base": "https://naverapihub.apigw.ntruss.com/search/v1",
        "id_header": "X-NCP-APIGW-API-KEY-ID",
        "secret_header": "X-NCP-APIGW-API-KEY",
        "suffix": "",
    },
    # 구 네이버 개발자센터 (2027-06-30 종료 예정)
    "developers": {
        "base": "https://openapi.naver.com/v1/search",
        "id_header": "X-Naver-Client-Id",
        "secret_header": "X-Naver-Client-Secret",
        "suffix": ".json",
    },
}

def _ssl_context() -> ssl.SSLContext:
    """macOS 파이썬은 루트 인증서가 없어 검증에 실패하는 경우가 잦다.

    certifi 가 설치돼 있으면 그 인증서 번들을 쓰고, 없으면 기본값을 그대로 쓴다.
    """
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


MAX_DISPLAY = 100  # 블로그·카페글을 한 번에 가져올 수 있는 최대 건수
MAX_START = 1000  # 검색 시작 위치 상한
LOCAL_MAX_DISPLAY = 5  # 지역 검색은 최대 5건만 반환된다


class NaverSearchCollector(BaseCollector):
    """엔드포인트만 바꿔 블로그·카페글·지역을 모두 처리한다."""

    endpoint = "blog"
    sort = "sim"
    min_interval = 0.1

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        backend: str | None = None,
    ) -> None:
        self.client_id = client_id or os.getenv("NAVER_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("NAVER_CLIENT_SECRET", "")
        self.backend = (backend or os.getenv("NAVER_API_BACKEND") or DEFAULT_BACKEND).lower()

    @property
    def name(self) -> str:  # type: ignore[override]
        return f"naver_{self.endpoint}"

    def available(self) -> tuple[bool, str]:
        if self.backend not in BACKENDS:
            return False, (
                f"알 수 없는 NAVER_API_BACKEND={self.backend!r}. "
                f"가능한 값: {', '.join(BACKENDS)}"
            )
        if not (self.client_id and self.client_secret):
            return False, (
                "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수가 필요합니다. "
                "NAVER API HUB(네이버 클라우드 플랫폼 콘솔)에서 발급하세요."
            )
        return True, ""

    def _url(self, query: str, display: int, start: int) -> str:
        spec = BACKENDS[self.backend]
        params = urllib.parse.urlencode(
            {"query": query, "display": display, "start": start, "sort": self.sort}
        )
        return f"{spec['base']}/{self.endpoint}{spec['suffix']}?{params}"

    def _request(self, query: str, display: int, start: int) -> dict:
        spec = BACKENDS[self.backend]
        req = urllib.request.Request(
            self._url(query, display, start),
            headers={
                spec["id_header"]: self.client_id,
                spec["secret_header"]: self.client_secret,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10, context=_ssl_context()) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # 4xx/5xx
            body = exc.read().decode("utf-8", "ignore")[:200]
            raise CollectorError(
                f"{self.name} HTTP {exc.code}: {self._hint(exc.code)}{body}"
            ) from exc
        except urllib.error.URLError as exc:
            hint = ""
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                hint = (
                    "[루트 인증서 없음 — macOS 라면 "
                    "`/Applications/Python 3.x/Install Certificates.command` 를 실행하거나 "
                    "`pip install certifi` 로 해결됩니다] "
                )
            raise CollectorError(f"{self.name} 네트워크 오류: {hint}{exc.reason}") from exc

    def _hint(self, code: int) -> str:
        """자주 겪는 오류에 원인 설명을 덧붙인다."""
        if code == 401:
            other = "developers" if self.backend == "apihub" else "apihub"
            return (
                f"[인증 실패 — 키가 현재 백엔드({self.backend})용이 맞는지, "
                f"Application 에 검색 API 권한이 있는지 확인하세요. "
                f"다른 쪽 키라면 NAVER_API_BACKEND={other}] "
            )
        if code == 429:
            return "[하루 호출 한도(25,000회) 초과] "
        return ""

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
            payload = self._request(task.query, min(MAX_DISPLAY, remaining), start)
            items = payload.get("items", [])
            if not items:
                return
            for item in items:
                yield self._to_document(item, task)
            remaining -= len(items)
            start += len(items)
            if start > MAX_START:
                return


class NaverBlogCollector(NaverSearchCollector):
    endpoint = "blog"


class NaverCafeCollector(NaverSearchCollector):
    endpoint = "cafearticle"


class NaverLocalCollector(NaverSearchCollector):
    """지역(장소) 검색.

    한 번에 최대 5건만 반환되고 `start` 는 1만 허용된다.
    정렬은 `random` 또는 `comment` 만 받는다(`sim` 은 오류).
    `comment` 는 블로그·카페 리뷰가 많은 순이라 생활권 분석에 더 적합하다.
    """

    endpoint = "local"
    sort = "comment"

    def collect(self, task: QueryTask) -> Iterator[Document]:
        ok, reason = self.available()
        if not ok:
            raise CollectorUnavailable(reason)

        payload = self._request(task.query, min(LOCAL_MAX_DISPLAY, task.limit), 1)
        for item in payload.get("items", []):
            yield self._to_document(item, task)
