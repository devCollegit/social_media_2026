"""오프라인 샘플 수집기.

API 키 없이도 전체 파이프라인(수집 → 분석 → 산출물)을 돌려볼 수 있도록
`data/samples/*.jsonl` 을 읽어 Document 로 변환한다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from ..models import Document, QueryTask
from .base import BaseCollector, CollectorUnavailable


class SampleCollector(BaseCollector):
    name = "sample"

    def __init__(self, sample_dir: str | Path) -> None:
        self.sample_dir = Path(sample_dir)

    def available(self) -> tuple[bool, str]:
        if not self.sample_dir.exists():
            return False, f"샘플 디렉터리 없음: {self.sample_dir}"
        if not list(self.sample_dir.glob("*.jsonl")):
            return False, f"샘플 파일(*.jsonl) 없음: {self.sample_dir}"
        return True, ""

    def _records(self) -> Iterator[dict]:
        for path in sorted(self.sample_dir.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    yield json.loads(line)

    def collect(self, task: QueryTask) -> Iterator[Document]:
        ok, reason = self.available()
        if not ok:
            raise CollectorUnavailable(reason)

        needle = task.query.lower()
        count = 0
        for record in self._records():
            if record.get("segment") != task.segment:
                continue
            haystack = " ".join(
                str(record.get(k, "")) for k in ("title", "text", "place_name", "region", "tags")
            ).lower()
            if needle and not any(token in haystack for token in needle.split()):
                continue
            yield Document(
                source=self.name,
                query=task.query,
                segment=task.segment,
                title=record.get("title", ""),
                text=record.get("text", ""),
                url=record.get("url", ""),
                place_name=record.get("place_name", ""),
                region=record.get("region", ""),
                category=record.get("category", ""),
                lang=record.get("lang", "ko"),
                rating=record.get("rating"),
                published_at=record.get("published_at"),
                raw=record,
            )
            count += 1
            if count >= task.limit:
                return
