"""요청 간격 제한과 재시도/백오프.

네트워크 라이브러리와 분리해 두어 실제 호출 없이 테스트할 수 있다.
병렬 요청은 지원하지 않는다. 모든 요청은 한 줄로 순서대로 나간다.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")
log = logging.getLogger("collector")


class TransientError(Exception):
    """재시도할 가치가 있는 오류 (429, 5xx, 연결 끊김 등)."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class PermanentError(Exception):
    """재시도해도 소용없는 오류 (400, 403, 404, 응답 형식 오류 등)."""


class RequestController:
    def __init__(
        self,
        min_interval: float = 2.0,
        max_retries: int = 4,
        backoff_base: float = 2.0,
        backoff_max: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        if min_interval < 1.0:
            raise ValueError("요청 간격은 1초 이상이어야 합니다.")
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self._sleep = sleep
        self._clock = clock
        self._jitter = jitter
        self._last: float | None = None
        self.requests = 0

    def _pace(self) -> None:
        if self._last is not None:
            gap = self._clock() - self._last
            if gap < self.min_interval:
                self._sleep(self.min_interval - gap)
        self._last = self._clock()

    def backoff(self, attempt: int, retry_after: float | None = None) -> float:
        if retry_after is not None:
            return max(retry_after, self.min_interval)
        delay = self.backoff_base * (2 ** attempt)
        return min(self.backoff_max, delay + self._jitter() * self.backoff_base)

    def call(self, fn: Callable[[], T], what: str = "") -> T:
        attempt = 0
        while True:
            self._pace()
            self.requests += 1
            try:
                return fn()
            except TransientError as exc:
                if attempt >= self.max_retries:
                    raise
                delay = self.backoff(attempt, exc.retry_after)
                log.warning("일시 오류 %s (%s), %.1f초 후 재시도 %d/%d", what, exc, delay,
                            attempt + 1, self.max_retries)
                self._sleep(delay)
                attempt += 1
