"""최종 모델 v2 (김동우 제안 A4+A5): 판정한 29,000건(b00~b22, b31~b36) 전부로 학습. 3분류 로지스틱 회귀(C=2.0).
입력 특징(모두 김정기 수집 컬럼에서 나오는 정보): 본문 글자 2~4 조각 TF-IDF + 부모 글 글자 조각(가중 0.5) + 단어(형태소, '안·못' 부정 처리) TF-IDF
  + 대댓글 · 매수 인증 · 매도 인증 · 보유 0/1.  (5겹 교차검증에서 월별 탐욕 비율 오차 5.47 → 4.33%p, eval_features_cv.py)
사용: uv run --python 3.10 --with scikit-learn==1.7.2 --with joblib --with scipy --with kiwipiepy python train_final2.py  -> model_v2.joblib"""
import json, joblib
from collections import Counter
import numpy as np
from scipy.sparse import hstack, csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from featurize import D, clean
from extract_keywords import tokens_batch

def _ident(s): return list(s)
def meta(is_reply, badge, holder):   # 대댓글, 매수 인증, 매도 인증, 보유
    return csr_matrix(np.column_stack([np.asarray(is_reply, float), np.asarray([b == "BUY" for b in badge], float),
                                       np.asarray([b == "SELL" for b in badge], float), np.asarray(holder, float)]))
def features(M, texts, parents, is_reply, badge, holder, toks=None):
    T = [clean(t) for t in texts]; P = [clean(p) if p else "" for p in parents]
    W = tokens_batch(T) if toks is None else toks
    return hstack([M["vt"].transform(T), 0.5 * M["vp"].transform(P), meta(is_reply, badge, holder), M["vw"].transform(W)]).tocsr()

if __name__ == "__main__":
    posts = {r["id"]: r for f in ("sample_30k_clean.json", "sample_prev12_clean.json") for r in json.load(open(f"{D}/{f}"))}
    BATCHES = [f"b{i:02d}" for i in list(range(0, 23)) + list(range(31, 37))]
    rows, y = [], []
    for b in BATCHES:
        for line in open(f"{D}/labels/{b}.jsonl"):
            r = json.loads(line); rows.append(posts[r["id"]]); y.append(r["label"] if r["label"] in ("greed", "fear") else "other")
    texts = [p["text"] for p in rows]; parents = [p["parent_text"] if p["is_reply"] else "" for p in rows]
    T = [clean(t) for t in texts]; P = [clean(p) if p else "" for p in parents]; W = tokens_batch(T)
    M = {"vt": TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, sublinear_tf=True).fit(T),
         "vp": TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, sublinear_tf=True).fit(P),
         "vw": TfidfVectorizer(analyzer=_ident, min_df=3, sublinear_tf=True).fit(W)}
    X = features(M, texts, parents, [p["is_reply"] for p in rows], [p["execution_side"] or "" for p in rows], [p["holding"] == "HOLDING" for p in rows], toks=W)
    M["model"] = LogisticRegression(C=2.0, class_weight="balanced", max_iter=4000).fit(X, y); M["batches"] = BATCHES
    joblib.dump(M, f"{D}/model_v2.joblib")
    print(f"학습 {len(y):,}건 {dict(Counter(y))}, 특징 {X.shape[1]:,}개 -> model_v2.joblib")
