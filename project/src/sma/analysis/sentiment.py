"""사전 기반 감성 점수(베이스라인).

형태소 분석기나 학습 모델 없이도 돌아가는 기준선이다. 정교한 분석이 필요하면
KNU 감성사전이나 KoBERT 계열 모델로 교체하고 동일한 인터페이스를 유지하면 된다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .text import tokenize

POSITIVE = {
    "맛있", "맛집", "친절", "최고", "좋아", "좋았", "만족", "훌륭", "깔끔", "재방문",
    "분위기좋", "가성비", "신선", "편안", "따뜻", "인생", "감동", "넉넉", "활기",
    "good", "great", "nice", "best", "love", "loved", "friendly", "delicious",
    "authentic", "amazing", "clean", "cozy", "recommend", "welcoming",
}
NEGATIVE = {
    "별로", "불친절", "실망", "최악", "비싸", "맛없", "아쉽", "불편", "시끄럽", "좁",
    "오래기다", "웨이팅길", "더럽", "눈치", "차별", "거절", "어렵",
    "bad", "worst", "rude", "dirty", "expensive", "disappointed", "awkward",
    "unfriendly", "confusing", "barrier", "refused",
}


@dataclass
class SentimentScore:
    positive: int
    negative: int
    score: float
    label: str

    def to_dict(self) -> dict:
        return {
            "positive": self.positive,
            "negative": self.negative,
            "score": round(self.score, 4),
            "label": self.label,
        }


def _match(token: str, lexicon: set[str]) -> bool:
    return any(token.startswith(word) or word in token for word in lexicon)


def score_text(text: str) -> SentimentScore:
    tokens = tokenize(text, stopwords=set())
    pos = sum(1 for t in tokens if _match(t, POSITIVE))
    neg = sum(1 for t in tokens if _match(t, NEGATIVE))
    raw = (pos - neg) / (pos + neg + 1)
    label = "positive" if raw > 0.1 else "negative" if raw < -0.1 else "neutral"
    return SentimentScore(positive=pos, negative=neg, score=raw, label=label)


def score_corpus(texts: list[str]) -> dict:
    scores = [score_text(t) for t in texts]
    if not scores:
        return {"count": 0, "mean_score": 0.0, "distribution": {}}
    dist: dict[str, int] = {"positive": 0, "neutral": 0, "negative": 0}
    for s in scores:
        dist[s.label] += 1
    return {
        "count": len(scores),
        "mean_score": round(sum(s.score for s in scores) / len(scores), 4),
        "distribution": dist,
    }
