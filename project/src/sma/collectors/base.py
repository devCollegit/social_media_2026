"""수집기 공통 인터페이스."""

from __future__ import annotations

import abc
from collections.abc import Iterator

from ..models import Document, QueryTask


class CollectorError(RuntimeError):
    """수집 중 복구 가능한 오류(재시도 대상)."""


class CollectorUnavailable(CollectorError):
    """API 키 누락 등으로 아예 사용할 수 없는 상태(재시도 불가)."""


class BaseCollector(abc.ABC):
    name: str = "base"
    #: 초당 과도한 호출을 막기 위한 최소 요청 간격(초)
    min_interval: float = 0.0

    def available(self) -> tuple[bool, str]:
        """사용 가능 여부와 사유를 반환."""
        return True, ""

    @abc.abstractmethod
    def collect(self, task: QueryTask) -> Iterator[Document]:
        """QueryTask 하나를 처리해 Document를 흘려보낸다."""
        raise NotImplementedError
