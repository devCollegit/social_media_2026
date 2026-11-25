"""v2 특징: 본문 글자 조각 TF-IDF(기존과 같음) + 본문 단어 TF-IDF + 부모 글 글자 조각 TF-IDF + 메타(대댓글·인증·보유).
학습(train_v2.py), 전체 적용(apply_v2.py), 추가 판정 표본(make_active_batch.py)이 모두 이 모듈을 쓴다.
"""
import re

import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer

try:
    from kiwipiepy import Kiwi
except ImportError:          # 단어 특징 없이도 돈다
    Kiwi = None

_KIWI = None
PRICE = re.compile(r"\d|^(만원|천원|억|조|프로|퍼센트|퍼)$")
SLANG = ("손절 익절 본절 물타기 불타기 존버 떡상 떡락 줍줍 상한가 하한가 가즈아 개미털기 설거지 추매 풀매수 몰빵 영끌 빚투 "
         "공매도 평단 신고가 신저가 탈출 반등 폭락 폭등 급등 급락 호재 악재 개미 세력 나락").split()


def kiwi():
    global _KIWI
    if _KIWI is None and Kiwi is not None:
        _KIWI = Kiwi(num_workers=-1)
        for w in SLANG:
            _KIWI.add_user_word(w, "NNG")
    return _KIWI


def word_tokens(texts):
    """extract_keywords.py의 from_toks와 같은 규칙: 용언은 '~다', '안/못 + 용언'은 따로, ㅋ·ㅠ·이모지 보존. 공백으로 이은 문자열을 돌려준다."""
    k = kiwi()
    if k is None:
        return [""] * len(texts)
    out = []
    for toks in k.tokenize(list(texts)):
        ws = []
        for i, t in enumerate(toks):
            f, tag = t.form, t.tag
            if tag.startswith(("VV", "VA")):
                w = f + "다"
                if i > 0 and toks[i - 1].form in ("안", "못") and toks[i - 1].tag == "MAG":
                    w = toks[i - 1].form + "_" + w
                ws.append(w)
            elif tag in ("NNG", "NNP", "XR", "MAG", "IC") and len(f) >= 2 and f not in ("안", "못"):
                ws.append(f)
            elif tag == "SW" and re.fullmatch(r"[ㅋㅎㅠㅜ]+", f):
                ws.append("ㅠㅠ" if f[0] in "ㅠㅜ" else "ㅋㅋ")
            elif tag == "W_EMOJI":
                ws.append(f)
            elif tag == "SL" and len(f) >= 2:
                ws.append(f.lower())
        out.append(" ".join(w for w in ws if not PRICE.search(w)))
    return out


def meta_matrix(is_reply, side, holding):
    """대댓글·매수 인증·매도 인증·보유 표시 → 0/1 열 4개."""
    m = np.column_stack([np.asarray(is_reply, float),
                         np.array([s == "BUY" for s in side], float),
                         np.array([s == "SELL" for s in side], float),
                         np.array([bool(h) for h in holding], float)])
    return csr_matrix(m)


class Featurizer:
    def __init__(self, use_words=True, use_parent=True, use_meta=True, parent_weight=0.5, meta_weight=1.0):
        self.use_words = use_words and Kiwi is not None
        self.use_parent, self.use_meta = use_parent, use_meta
        self.parent_weight, self.meta_weight = parent_weight, meta_weight
        self.vc = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, sublinear_tf=True)
        self.vw = TfidfVectorizer(token_pattern=r"\S+", ngram_range=(1, 2), min_df=3, sublinear_tf=True)
        self.vp = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, sublinear_tf=True)

    def _blocks(self, text, parent, is_reply, side, holding, fit):
        f = (lambda v, x: v.fit_transform(x)) if fit else (lambda v, x: v.transform(x))
        b = [f(self.vc, text)]
        if self.use_words:
            b.append(f(self.vw, word_tokens(text)))
        if self.use_parent:
            b.append(self.parent_weight * f(self.vp, [p or "" for p in parent]))
        if self.use_meta:
            b.append(self.meta_weight * meta_matrix(is_reply, side, holding))
        return hstack(b).tocsr()

    def fit_transform(self, *a):
        return self._blocks(*a, fit=True)

    def transform(self, *a):
        return self._blocks(*a, fit=False)

    def describe(self):
        return {"char": True, "words": self.use_words, "parent": self.use_parent, "meta": self.use_meta,
                "parent_weight": self.parent_weight}
