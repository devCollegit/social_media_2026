"""연구 계획(수집 대상·키워드·소스) 설정."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import QueryTask

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAN_PATH = PROJECT_ROOT / "config" / "research_plan.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "collected.sqlite3"


@dataclass
class SegmentPlan:
    """내국인/외국인 같은 비교 집단 단위 수집 계획."""

    name: str
    label: str
    queries: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    lang: str = "ko"


@dataclass
class ResearchPlan:
    topic: str
    question: str
    regions: list[str] = field(default_factory=list)
    segments: list[SegmentPlan] = field(default_factory=list)
    limit_per_query: int = 30
    request_interval: float = 0.2
    max_retries: int = 2

    @classmethod
    def load(cls, path: str | Path | None = None) -> "ResearchPlan":
        path = Path(path) if path else DEFAULT_PLAN_PATH
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        segments = [SegmentPlan(**seg) for seg in data.pop("segments", [])]
        return cls(segments=segments, **data)

    def tasks(self, sources: list[str] | None = None) -> list[QueryTask]:
        tasks: list[QueryTask] = []
        for segment in self.segments:
            for source in segment.sources:
                if sources and source not in sources:
                    continue
                for query in segment.queries:
                    tasks.append(
                        QueryTask(
                            query=query,
                            segment=segment.name,
                            source=source,
                            limit=self.limit_per_query,
                            extra={"lang": segment.lang, "label": segment.label},
                        )
                    )
        return tasks

    def segment_names(self) -> list[str]:
        return [s.name for s in self.segments]

    def label_of(self, name: str) -> str:
        for segment in self.segments:
            if segment.name == name:
                return segment.label
        return name
