"""A9 적용 전(_v3_before_a9/) · 후 결과 비교: 회귀 계수(b, t)를 전부 펼쳐서 부호가 뒤집혔거나 유의성(|t| 1.96)이 바뀐 것을 찾는다."""
import json
from featurize import D
FILES = ["pres_results.json", "krx_results.json", "extra_results.json", "rotation_results.json"]
def flat(x, p=""):
    if isinstance(x, dict):
        if "b" in x and "t" in x and isinstance(x["b"], (int, float)) and isinstance(x["t"], (int, float)): yield p, x["b"], x["t"]; return
        for k, v in x.items(): yield from flat(v, f"{p}.{k}" if p else k)
    elif isinstance(x, list):
        for i, v in enumerate(x): yield from flat(v, f"{p}[{i}]")
rows = []
for f in FILES:
    a = dict((k, (b, t)) for k, b, t in flat(json.load(open(f"{D}/_v3_before_a9/{f}"))))
    n = dict((k, (b, t)) for k, b, t in flat(json.load(open(f"{D}/{f}"))))
    for k in sorted(set(a) & set(n)):
        (b0, t0), (b1, t1) = a[k], n[k]
        sig0, sig1 = abs(t0) >= 1.96, abs(t1) >= 1.96
        flip = (b0 > 0) != (b1 > 0)
        if flip or sig0 != sig1: rows.append((f.split("_")[0], k, b0, t0, b1, t1, ("부호" if flip else "") + (" 유의성" if sig0 != sig1 else "")))
    print(f"{f}: 계수 {len(set(a) & set(n))}개 비교")
print(f"\n바뀐 것 {len(rows)}개 (부호가 바뀌었거나 |t|가 1.96을 넘나듦)")
for r in rows: print(f"  [{r[0]}] {r[1]}: {r[2]:+.3f} (t {r[3]:.1f}) → {r[4]:+.3f} (t {r[5]:.1f})  {r[6]}")
n_total = 0
for f in FILES:
    a = dict((k, (b, t)) for k, b, t in flat(json.load(open(f"{D}/_v3_before_a9/{f}"))))
    n = dict((k, (b, t)) for k, b, t in flat(json.load(open(f"{D}/{f}"))))
    n_total += len(set(a) & set(n))
both_ns = sum(1 for r in rows if abs(r[3]) < 1.96 and abs(r[5]) < 1.96)
json.dump({"n_compared": n_total, "n_changed": len(rows), "n_flip_both_ns": both_ns,
           "changed": [{"file": r[0], "key": r[1], "b0": r[2], "t0": r[3], "b1": r[4], "t1": r[5], "what": r[6].strip()} for r in rows]},
          open(f"{D}/a9_compare.json", "w"), ensure_ascii=False, indent=1)
print("비교", n_total, "개, 바뀐 것", len(rows), "개, 그중 전후 모두 유의하지 않은 부호 변화", both_ns, "개 → a9_compare.json")
