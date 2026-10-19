"""응답을 가져오는 쪽. 수집 로직(run.py)은 이 인터페이스만 안다.

- FixtureFetcher: 저장된 JSON 파일로 동작을 점검한다. 네트워크를 쓰지 않는다.
- TossFetcher   : 토스증권 이용 허락 확인 전까지 구현하지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from collector.http import PermanentError


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


class TossFetcher:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(
            "토스증권 네트워크 수집은 아직 구현하지 않았습니다. "
            "docs/수집가능성_점검표.md 5~6절: 이용 허락과 조건을 확인한 뒤 구현합니다."
        )
