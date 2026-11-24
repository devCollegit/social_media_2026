"""표본 → LLM 판정 묶음. make_sample.py 결과를 받아
① 멘션(#[닉네임](id))을 @사용자로 가리고(본문·부모 글 모두) ② 순서를 섞어 <이름>_clean.json 으로 저장한 뒤
③ 앞에서부터 1,000건씩 batches/bNN.jsonl 로 나눈다(판정에 필요한 필드만: id, stock_name, is_reply, execution_side, text, parent_text).
LLM 판정 결과는 labels/bNN.jsonl 에 쓰고 check_batch.py 로 검사한다(작업 지시는 batch_task.md).
사용: python make_batches.py <표본.jsonl> <첫 묶음 번호>
  예) python make_batches.py sample_30k.jsonl 0     → sample_30k_clean.json, b00~b30
      python make_batches.py sample_prev12.jsonl 31 → sample_prev12_clean.json, b31~
※ 실제 분석 때는 이 단계를 따로 파일로 남기지 않고 한 번에 처리했다. 섞는 순서(seed)가 달라 묶음 구성은 원래와 같지 않을 수 있다."""
import json, os, random, sys
from featurize import D, MENTION

src, start = sys.argv[1], int(sys.argv[2])
rows = [json.loads(l) for l in open(os.path.join(D, src), encoding="utf-8") if l.strip()]
for r in rows:
    for k in ("text", "parent_text"):
        if r.get(k): r[k] = MENTION.sub("@사용자", r[k])
random.seed(0); random.shuffle(rows)
stem = os.path.splitext(src)[0]
json.dump(rows, open(os.path.join(D, f"{stem}_clean.json"), "w", encoding="utf-8"), ensure_ascii=False)
os.makedirs(os.path.join(D, "batches"), exist_ok=True)
KEEP = ["id", "stock_name", "is_reply", "execution_side", "text", "parent_text"]
for i in range(0, len(rows), 1000):
    with open(os.path.join(D, "batches", f"b{start + i // 1000:02d}.jsonl"), "w", encoding="utf-8") as f:
        for r in rows[i:i + 1000]: f.write(json.dumps({k: r.get(k) for k in KEEP}, ensure_ascii=False) + "\n")
print(f"{len(rows):,}건 → {stem}_clean.json, 묶음 b{start:02d}~b{start + (len(rows) - 1) // 1000:02d}")
