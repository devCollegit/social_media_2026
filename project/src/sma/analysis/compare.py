"""집단(내국인 vs 외국인) 비교 분석.

핵심 산출물
1. 집단별 상위 키워드 / 감성 분포
2. 로그 오즈비 기반 '변별 키워드' (한쪽에서만 두드러지는 말)
3. 장소·지역 겹침 지표(자카드) 와 공유 장소 목록 → 교류 공간 후보
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable

from ..models import Document
from .sentiment import score_corpus
from .text import term_freq, top_terms


def _log_odds(
    counter_a: Counter[str], counter_b: Counter[str], alpha: float = 0.5
) -> dict[str, float]:
    """정보 없는 디리클레 사전(alpha)을 쓴 로그 오즈비. 양수면 A쪽 특징어."""
    vocab = set(counter_a) | set(counter_b)
    total_a = sum(counter_a.values()) + alpha * len(vocab)
    total_b = sum(counter_b.values()) + alpha * len(vocab)
    scores: dict[str, float] = {}
    for term in vocab:
        a = counter_a.get(term, 0) + alpha
        b = counter_b.get(term, 0) + alpha
        ratio = math.log(a / (total_a - a)) - math.log(b / (total_b - b))
        variance = 1 / a + 1 / b
        scores[term] = ratio / math.sqrt(variance)
    return scores


def region_key(region: str) -> str:
    """'서울 성동구' 처럼 시도+시군구 2단계까지를 비교 단위로 삼는다."""
    return " ".join(region.split()[:2])


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def segment_profile(documents: list[Document], top_n: int = 15) -> dict:
    texts = [d.body for d in documents]
    places = Counter(d.place_name for d in documents if d.place_name)
    regions = Counter(region_key(d.region) for d in documents if d.region)
    ratings = [d.rating for d in documents if d.rating is not None]
    return {
        "documents": len(documents),
        "sources": dict(Counter(d.source for d in documents)),
        "top_terms": [{"term": t, "count": c} for t, c in top_terms(term_freq(texts), top_n, 1)],
        "top_places": [{"place": p, "count": c} for p, c in places.most_common(top_n)],
        "top_regions": [{"region": r, "count": c} for r, c in regions.most_common(top_n)],
        "mean_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "sentiment": score_corpus(texts),
    }


def compare_segments(
    documents: Iterable[Document],
    segment_a: str,
    segment_b: str,
    labels: dict[str, str] | None = None,
    top_n: int = 15,
) -> dict:
    labels = labels or {}
    buckets: dict[str, list[Document]] = defaultdict(list)
    for doc in documents:
        buckets[doc.segment].append(doc)

    docs_a, docs_b = buckets.get(segment_a, []), buckets.get(segment_b, [])
    freq_a = term_freq(d.body for d in docs_a)
    freq_b = term_freq(d.body for d in docs_b)
    scores = _log_odds(freq_a, freq_b)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

    places_a = {d.place_name for d in docs_a if d.place_name}
    places_b = {d.place_name for d in docs_b if d.place_name}
    regions_a = {region_key(d.region) for d in docs_a if d.region}
    regions_b = {region_key(d.region) for d in docs_b if d.region}

    shared_places = sorted(places_a & places_b)
    place_counts = Counter(d.place_name for d in docs_a + docs_b if d.place_name)

    return {
        "segments": {
            segment_a: {"label": labels.get(segment_a, segment_a), **segment_profile(docs_a, top_n)},
            segment_b: {"label": labels.get(segment_b, segment_b), **segment_profile(docs_b, top_n)},
        },
        "distinctive_terms": {
            segment_a: [
                {"term": t, "z": round(z, 2), "count": freq_a.get(t, 0)}
                for t, z in ranked[:top_n]
                if freq_a.get(t, 0) >= 2
            ],
            segment_b: [
                {"term": t, "z": round(z, 2), "count": freq_b.get(t, 0)}
                for t, z in reversed(ranked[-top_n * 3 :])
                if freq_b.get(t, 0) >= 2
            ][:top_n],
        },
        "overlap": {
            "place_jaccard": round(_jaccard(places_a, places_b), 4),
            "region_jaccard": round(_jaccard(regions_a, regions_b), 4),
            "shared_places": [
                {"place": p, "mentions": place_counts[p]} for p in shared_places
            ],
            "only_a_places": sorted(places_a - places_b),
            "only_b_places": sorted(places_b - places_a),
            "shared_regions": sorted(regions_a & regions_b),
        },
    }


def exchange_candidates(analysis: dict, top_n: int = 10) -> list[dict]:
    """두 집단이 함께 언급한 장소 = 교류 공간 1순위 후보."""
    shared = analysis.get("overlap", {}).get("shared_places", [])
    return sorted(shared, key=lambda s: s["mentions"], reverse=True)[:top_n]
