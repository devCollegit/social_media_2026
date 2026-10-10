"""수집·분석 전 구간에서 공유하는 데이터 모델."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")

KOREAN_SEGMENT = "korean"
FOREIGN_SEGMENT = "foreign"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return WS_RE.sub(" ", TAG_RE.sub(" ", value)).strip()


@dataclass(frozen=True)
class QueryTask:
    """컨트롤러가 수집기에 넘기는 단위 작업."""

    query: str
    segment: str
    source: str
    limit: int = 30
    region: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.segment}:{self.query}"


@dataclass
class Document:
    """소셜 게시물 / 리뷰 / 장소 정보를 담는 공통 레코드."""

    source: str
    query: str
    segment: str
    title: str = ""
    text: str = ""
    url: str = ""
    place_name: str = ""
    region: str = ""
    category: str = ""
    lang: str = "ko"
    rating: float | None = None
    published_at: str | None = None
    collected_at: str = field(default_factory=now_iso)
    doc_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.title = clean_text(self.title)
        self.text = clean_text(self.text)
        self.place_name = clean_text(self.place_name)
        if not self.doc_id:
            self.doc_id = self.fingerprint()

    def fingerprint(self) -> str:
        basis = self.url or f"{self.source}|{self.place_name}|{self.title}|{self.text[:120]}"
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]

    @property
    def body(self) -> str:
        return f"{self.title} {self.text}".strip()

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["raw"] = json.dumps(self.raw, ensure_ascii=False)
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Document":
        data = dict(row)
        raw = data.get("raw") or "{}"
        data["raw"] = json.loads(raw) if isinstance(raw, str) else raw
        return cls(**data)


@dataclass
class SourceStat:
    source: str
    requested: int = 0
    fetched: int = 0
    stored: int = 0
    duplicated: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class CollectionReport:
    started_at: str
    finished_at: str = ""
    tasks: int = 0
    fetched: int = 0
    stored: int = 0
    duplicated: int = 0
    by_source: dict[str, SourceStat] = field(default_factory=dict)
    skipped_sources: dict[str, str] = field(default_factory=dict)
    #: 검색어 단위 수집 내역. 중복 제거 때문에 저장된 문서만으로는
    #: 어떤 검색어가 실제로 결과를 냈는지 알 수 없어 따로 기록한다.
    task_stats: list[dict[str, Any]] = field(default_factory=list)

    def stat(self, source: str) -> SourceStat:
        return self.by_source.setdefault(source, SourceStat(source=source))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["by_source"] = {k: asdict(v) for k, v in self.by_source.items()}
        return data
