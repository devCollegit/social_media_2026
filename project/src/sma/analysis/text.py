"""한국어/영어 혼합 텍스트용 경량 토크나이저와 빈도 분석."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

TOKEN_RE = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z']{2,}")

#: 어떤 주제에서도 변별력이 없는 기본 불용어
BASE_STOPWORDS = {
    # 한국어 일반
    "그리고", "하지만", "그래서", "정말", "너무", "진짜", "조금", "약간", "이번", "다음",
    "오늘", "어제", "내일", "우리", "저희", "여기", "거기", "저기", "이곳", "그곳",
    "같이", "같은", "있는", "없는", "하는", "되는", "이런", "저런", "그런", "많이",
    "다시", "생각", "느낌", "정도", "경우", "때문", "사람", "하나", "해서", "에서",
    # 리뷰/블로그 상투어
    "방문", "사진", "포스팅", "블로그", "후기", "리뷰", "추천", "소개", "이상", "이하",
    # 영어 일반
    "the", "and", "for", "with", "that", "this", "was", "were", "have", "has",
    "but", "you", "your", "they", "there", "here", "what", "when", "where",
    "from", "about", "very", "really", "just", "some", "more", "most", "such",
    "been", "will", "would", "could", "should", "also", "than", "then", "into",
}

_ACTIVE: set[str] = set(BASE_STOPWORDS)

#: 하위 호환용 별칭
STOPWORDS = BASE_STOPWORDS


def active_stopwords() -> set[str]:
    """현재 적용 중인 불용어 집합(복사본)."""
    return set(_ACTIVE)


def set_stopwords(words: Iterable[str]) -> None:
    global _ACTIVE
    _ACTIVE = {w.strip().lower() for w in words if w.strip()}


def add_stopwords(words: Iterable[str]) -> None:
    _ACTIVE.update(w.strip().lower() for w in words if w.strip())


def reset_stopwords() -> None:
    set_stopwords(BASE_STOPWORDS)


def load_stopwords(path: str | Path, replace: bool = False) -> set[str]:
    """불용어 파일을 읽어 적용한다. `#` 로 시작하는 줄은 주석 처리된다.

    replace=False 이면 기본 불용어 + 파일 내용, True 이면 파일 내용만 사용한다.
    """
    file_path = Path(path)
    if not file_path.exists():
        return active_stopwords()
    words = [
        line.strip().lower()
        for line in file_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if replace:
        set_stopwords(words)
    else:
        reset_stopwords()
        add_stopwords(words)
    return active_stopwords()


def tokenize(text: str, stopwords: set[str] | None = None) -> list[str]:
    stops = _ACTIVE if stopwords is None else stopwords
    return [t.lower() for t in TOKEN_RE.findall(text) if t.lower() not in stops]


def term_freq(texts: Iterable[str], stopwords: set[str] | None = None) -> Counter[str]:
    counter: Counter[str] = Counter()
    for text in texts:
        counter.update(tokenize(text, stopwords))
    return counter


def top_terms(counter: Counter[str], n: int = 20, min_count: int = 2) -> list[tuple[str, int]]:
    return [(t, c) for t, c in counter.most_common() if c >= min_count][:n]
