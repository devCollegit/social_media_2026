"""최종 모델: 판정한 29,000건(b00~b22, b31~b36) 전부로 학습. 글자 2~4 조각 TF-IDF + 로지스틱 회귀(C=2.0, 3분류).
사용: uv run --python 3.10 --with scikit-learn==1.7.2 --with joblib python train_final.py (적용 환경과 버전 맞춤)  -> model.joblib"""
import json, joblib
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from featurize import D, clean
posts = {r["id"]: r for f in ("sample_30k_clean.json", "sample_prev12_clean.json") for r in json.load(open(f"{D}/{f}"))}
BATCHES = [f"b{i:02d}" for i in list(range(0, 23)) + list(range(31, 37))]
X, y = [], []
for b in BATCHES:
    for line in open(f"{D}/labels/{b}.jsonl"):
        r = json.loads(line)
        X.append(clean(posts[r["id"]]["text"])); y.append(r["label"] if r["label"] in ("greed", "fear") else "other")
v = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, sublinear_tf=True)
lr = LogisticRegression(C=2.0, class_weight="balanced", max_iter=3000).fit(v.fit_transform(X), y)
joblib.dump({"vectorizer": v, "model": lr, "batches": BATCHES}, f"{D}/model.joblib")
print(f"학습 {len(y):,}건 {dict(Counter(y))}, 특징 {len(v.vocabulary_):,}개 -> model.joblib")
