"""수집기 레지스트리."""

from __future__ import annotations

from pathlib import Path

from ..config import PROJECT_ROOT
from .base import BaseCollector, CollectorError, CollectorUnavailable
from .naver import (
    NaverBlogCollector,
    NaverCafeCollector,
    NaverLocalCollector,
    NaverSearchCollector,
)
from .sample import SampleCollector

__all__ = [
    "BaseCollector",
    "CollectorError",
    "CollectorUnavailable",
    "NaverBlogCollector",
    "NaverCafeCollector",
    "NaverLocalCollector",
    "NaverSearchCollector",
    "SampleCollector",
    "default_collectors",
]


def default_collectors(sample_dir: str | Path | None = None) -> list[BaseCollector]:
    sample_dir = Path(sample_dir) if sample_dir else PROJECT_ROOT / "data" / "samples"
    return [
        SampleCollector(sample_dir),
        NaverBlogCollector(),
        NaverCafeCollector(),
        NaverLocalCollector(),
    ]
