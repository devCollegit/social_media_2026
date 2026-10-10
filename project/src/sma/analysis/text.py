"""한국어/영어 혼합 텍스트용 경량 토크나이저와 빈도 분석."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

TOKEN_RE = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z']{2,}")

STOPWORDS = {
    # 한국어
    "그리고", "하지만", "그래서", "정말", "너무", "진짜", "조금", "약간", "이번", "다음",
    "오늘", "어제", "내일", "우리", "저희", "여기", "거기", "저기", "이곳", "그곳",
    "같이", "같은", "있는", "없는", "하는", "되는", "이런", "저런", "그런", "많이",
    "다시", "방문", "생각", "느낌", "정도", "경우", "때문", "사람", "사진", "포스팅",
    "블로그", "후기", "리뷰", "추천", "소개", "이상", "이하", "하나", "해서", "에서",
    # 영어
    "the", "and", "for", "with", "that", "this", "was", "were", "have", "has",
    "but", "you", "your", "they", "there", "here", "what", "when", "where",
    "from", "about", "very", "really", "just", "some", "more", "most", "such",
    "been", "will", "would", "could", "should", "also", "than", "then", "into",
}


def tokenize(text: str, stopwords: set[str] | None = None) -> list[str]:
    stops = STOPWORDS if stopwords is None else stopwords
    return [t.lower() for t in TOKEN_RE.findall(text) if t.lower() not in stops]


def term_freq(texts: Iterable[str], stopwords: set[str] | None = None) -> Counter[str]:
    counter: Counter[str] = Counter()
    for text in texts:
        counter.update(tokenize(text, stopwords))
    return counter


def top_terms(counter: Counter[str], n: int = 20, min_count: int = 2) -> list[tuple[str, int]]:
    return [(t, c) for t, c in counter.most_common() if c >= min_count][:n]
