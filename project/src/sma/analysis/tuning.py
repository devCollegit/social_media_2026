"""키워드 보정 도구.

1차 분석 결과를 보고 반복적으로 품질을 올리기 위한 두 가지 진단을 제공한다.

- `suggest_stopwords`: 양쪽 집단에서 똑같이 흔해 변별력이 없는 단어를 불용어 후보로 제시
- `sample_balance`: 집단별 검색어 수·수집량·문서 길이의 비대칭(표본 편향)을 점검
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable

from ..config import ResearchPlan
from ..models import Document
from .compare import log_odds
from .text import active_stopwords, term_freq, tokenize


def suggest_stopwords(
    documents: Iterable[Document],
    segment_a: str,
    segment_b: str,
    top_n: int = 30,
    max_abs_z: float = 1.0,
    min_total: int = 5,
    max_df_ratio: float = 0.5,
) -> list[dict]:
    """변별력이 없는 단어 후보.

    1) 두 집단 모두에서 비슷한 빈도로 등장하는 단어 (|z| <= max_abs_z)
    2) 두 집단 모두에서 문서의 max_df_ratio 이상에 등장하는 상투어

    한쪽 집단에서만 고빈도인 단어는 변별어이자 결론일 수 있으므로 후보로 보지 않는다.
    """
    buckets: dict[str, list[Document]] = defaultdict(list)
    for doc in documents:
        buckets[doc.segment].append(doc)

    freq_a = term_freq(d.body for d in buckets.get(segment_a, []))
    freq_b = term_freq(d.body for d in buckets.get(segment_b, []))
    scores = log_odds(freq_a, freq_b)
    current = active_stopwords()

    candidates = []
    for term, z in scores.items():
        if term in current:
            continue
        total = freq_a.get(term, 0) + freq_b.get(term, 0)
        if total < min_total or abs(z) > max_abs_z:
            continue
        # 한쪽에만 쏠린 단어는 변별어이므로 제외
        if min(freq_a.get(term, 0), freq_b.get(term, 0)) == 0:
            continue
        candidates.append(
            {
                "term": term,
                "total": total,
                "count_a": freq_a.get(term, 0),
                "count_b": freq_b.get(term, 0),
                "z": round(z, 3),
            }
        )
    for item in candidates:
        item["reason"] = "양측 공통 고빈도"

    # 두 집단 모두에서 문서 대부분에 등장하는 단어는 비교에 전혀 기여하지 않는다.
    # 한쪽에서만 고빈도인 단어는 오히려 결론일 수 있으므로(예: 외국인 리뷰의 english)
    # 의도적으로 제외한다.
    seen = {c["term"] for c in candidates}
    df_a = dict((t, r) for t, r, _ in _high_document_frequency(buckets.get(segment_a, []), max_df_ratio))
    df_b = dict((t, r) for t, r, _ in _high_document_frequency(buckets.get(segment_b, []), max_df_ratio))
    for term in sorted(set(df_a) & set(df_b)):
        if term in seen or term in current:
            continue
        seen.add(term)
        candidates.append(
            {
                "term": term,
                "total": freq_a.get(term, 0) + freq_b.get(term, 0),
                "count_a": freq_a.get(term, 0),
                "count_b": freq_b.get(term, 0),
                "z": round(scores.get(term, 0.0), 3),
                "reason": f"양측 문서빈도 과다 ({int(df_a[term] * 100)}% / {int(df_b[term] * 100)}%)",
            }
        )

    candidates.sort(key=lambda c: (-c["total"], abs(c["z"])))
    return candidates[:top_n]


def _high_document_frequency(
    documents: list[Document], min_ratio: float = 0.5, min_docs: int = 5
) -> list[tuple[str, float, int]]:
    """집단 내 문서의 min_ratio 이상에 등장하는 단어. 사실상 상투어다."""
    if len(documents) < min_docs:
        return []
    doc_freq: Counter[str] = Counter()
    total_freq: Counter[str] = Counter()
    for doc in documents:
        tokens = tokenize(doc.body)
        total_freq.update(tokens)
        doc_freq.update(set(tokens))
    n = len(documents)
    return sorted(
        (
            (term, count / n, total_freq[term])
            for term, count in doc_freq.items()
            if count / n >= min_ratio
        ),
        key=lambda item: -item[1],
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def sample_balance(
    documents: Iterable[Document],
    plan: ResearchPlan,
    collection_report: dict | None = None,
) -> dict:
    """집단 간 표본 대칭성 진단. 검색어 설계가 곧 표본 편향이므로 매 수집마다 확인한다.

    collection_report 를 주면 검색어별 수집량을 중복 제거 이전의 실제 수집 건수로 센다.
    저장된 문서만 세면 먼저 실행된 검색어가 결과를 독식해 나머지가 0건으로 보인다.
    """
    docs = list(documents)
    fetched_by_query: dict[tuple[str, str], int] = {}
    for task in (collection_report or {}).get("task_stats", []):
        key = (task.get("segment", ""), task.get("query", ""))
        fetched_by_query[key] = fetched_by_query.get(key, 0) + int(task.get("fetched", 0))
    buckets: dict[str, list[Document]] = defaultdict(list)
    for doc in docs:
        buckets[doc.segment].append(doc)

    profiles: dict[str, dict] = {}
    for segment in plan.segments:
        items = buckets.get(segment.name, [])
        if fetched_by_query:
            per_query = Counter(
                {q: fetched_by_query.get((segment.name, q), 0) for q in segment.queries}
            )
        else:
            per_query = Counter(d.query for d in items)
        lengths = [len(tokenize(d.body)) for d in items]
        profiles[segment.name] = {
            "label": segment.label,
            "planned_queries": len(segment.queries),
            "planned_sources": sorted(segment.sources),
            "documents": len(items),
            "documents_per_query": {q: per_query.get(q, 0) for q in segment.queries},
            "empty_queries": [q for q in segment.queries if per_query.get(q, 0) == 0],
            "query_counts_source": "수집 시도 기준" if fetched_by_query else "저장 문서 기준",
            "mean_tokens": round(_mean(lengths), 1),
            "sources": dict(Counter(d.source for d in items)),
        }

    warnings: list[str] = []
    names = list(profiles)
    if len(names) >= 2:
        a, b = profiles[names[0]], profiles[names[1]]

        if a["planned_queries"] != b["planned_queries"]:
            warnings.append(
                f"검색어 수가 다릅니다 ({a['label']} {a['planned_queries']}개 / "
                f"{b['label']} {b['planned_queries']}개). 집단별 검색어 수를 맞추세요."
            )
        if set(a["planned_sources"]) != set(b["planned_sources"]):
            warnings.append("집단별 수집 소스 구성이 다릅니다. 동일한 소스에서 수집해야 비교가 공정합니다.")

        counts = sorted([a["documents"], b["documents"]])
        if counts[0] == 0:
            warnings.append("한쪽 집단의 수집 결과가 0건입니다. 검색어 또는 소스를 점검하세요.")
        elif counts[1] / counts[0] > 1.5:
            warnings.append(
                f"수집량 비대칭이 큽니다 ({a['label']} {a['documents']}건 / "
                f"{b['label']} {b['documents']}건, 비율 {counts[1] / counts[0]:.2f}). "
                "많은 쪽을 표본 추출하거나 적은 쪽 검색어를 늘리세요."
            )

        tokens = sorted([a["mean_tokens"], b["mean_tokens"]])
        if tokens[0] > 0 and tokens[1] / tokens[0] > 2.0:
            warnings.append(
                f"평균 문서 길이 차이가 큽니다 ({a['label']} {a['mean_tokens']} / "
                f"{b['label']} {b['mean_tokens']} 토큰). 빈도 비교 시 길이 정규화를 고려하세요."
            )

    for name, profile in profiles.items():
        if profile["empty_queries"]:
            warnings.append(
                f"{profile['label']}: 결과가 없는 검색어 {len(profile['empty_queries'])}개 "
                f"({', '.join(profile['empty_queries'][:3])}…)"
            )

    total = len(docs)
    return {
        "total_documents": total,
        "segments": profiles,
        "warnings": warnings,
        "balanced": not warnings,
    }


def render_tuning_report(candidates: list[dict], balance: dict, labels: dict[str, str]) -> str:
    out = ["# 키워드 보정 리포트\n"]

    out.append("## 1. 표본 균형 진단\n")
    out.append(f"- 전체 문서: **{balance['total_documents']:,}건**")
    out.append(f"- 판정: **{'균형' if balance['balanced'] else '보정 필요'}**\n")
    out.append("| 집단 | 검색어 | 문서 | 평균 토큰 | 결과 없는 검색어 |")
    out.append("|---|---|---|---|---|")
    for name, profile in balance["segments"].items():
        out.append(
            f"| {profile['label']} | {profile['planned_queries']} | {profile['documents']} | "
            f"{profile['mean_tokens']} | {len(profile['empty_queries'])} |"
        )

    first = next(iter(balance["segments"].values()), {})
    basis = first.get("query_counts_source", "저장 문서 기준")
    out.append(f"\n### 검색어별 수집량 ({basis})\n")
    for name, profile in balance["segments"].items():
        out.append(f"**{profile['label']}**\n")
        for query, count in profile["documents_per_query"].items():
            flag = " ⚠️" if count == 0 else ""
            out.append(f"- `{query}`: {count}건{flag}")
        out.append("")

    out.append("### 경고\n")
    if balance["warnings"]:
        for warning in balance["warnings"]:
            out.append(f"- ⚠️ {warning}")
    else:
        out.append("- 발견된 문제 없음")

    out.append("\n## 2. 불용어 후보\n")
    out.append(
        "변별력이 낮아 보이는 단어입니다. 선정 사유는 두 가지입니다.\n\n"
        "- **양측 공통 고빈도**: 두 집단이 비슷한 빈도로 쓰는 단어라 비교에 기여하지 않음\n"
        "- **양측 문서빈도 과다**: 두 집단 모두 문서 대부분에 등장하는 상투어\n\n"
        "한쪽 집단에서만 자주 쓰이는 단어는 변별어이자 결론일 수 있어"
        "(예: 외국인 리뷰의 `english menu`) 후보에서 제외했습니다.\n"
        "제거하기로 했다면 `config/stopwords.txt` 에 추가하고 분석을 재실행합니다.\n"
    )
    if candidates:
        header = [labels.get(k, k) for k in list(balance["segments"])[:2]]
        name_a = header[0] if header else "A"
        name_b = header[1] if len(header) > 1 else "B"
        out.append(f"| 단어 | 전체 | {name_a} | {name_b} | z | 선정 사유 |")
        out.append("|---|---|---|---|---|---|")
        for item in candidates:
            out.append(
                f"| {item['term']} | {item['total']} | {item['count_a']} | "
                f"{item['count_b']} | {item['z']} | {item.get('reason', '-')} |"
            )
        out.append("\n### 바로 붙여 넣을 수 있는 형태\n")
        out.append("```")
        out.extend(item["term"] for item in candidates)
        out.append("```")
    else:
        out.append(
            "추가할 만한 불용어 후보가 없습니다. "
            "두 집단의 사용 언어가 다르면(한국어 vs 영어) 공통 어휘가 거의 없어 "
            "후보가 나오지 않는 것이 정상입니다."
        )

    out.append("")
    return "\n".join(out)
