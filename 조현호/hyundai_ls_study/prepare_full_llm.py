"""현재 확보분을 정제하고 ID당 불변 LLM 묶음을 발행한다. 재실행 시 이미 발행한 ID는 유지."""
import sqlite3,json,re,hashlib,collections
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'private/full_20260701_20261020';L=D/'llm';inp=L/'input'
if (D/'frozen_snapshot.json').exists():raise SystemExit('사용자 요청으로 확보분을 고정했습니다. AI 입력을 추가하지 않습니다.')
inp.mkdir(parents=True,exist_ok=True)
for worker in range(3):(L/f'worker_{worker}').mkdir(exist_ok=True)
prompt=(R/'분류지침.md').read_bytes()
if (L/'prompt.md').exists():
 if (L/'prompt.md').read_bytes()!=prompt:raise ValueError('기존 실행과 분류지침 불일치: 입력을 추가하지 않음')
else:(L/'prompt.md').write_bytes(prompt)
con=sqlite3.connect(D/'collection.sqlite');raw=[json.loads(x[0]) for x in con.execute('SELECT payload FROM posts ORDER BY code,at,id')]
def norm(t):return re.sub(r'\s+',' ',re.sub(r'(.)\1{3,}',r'\1\1',re.sub(r'https?://\S+',' ',t))).strip()
rows=[]
for r in raw:
 if '2026-09-01'<=r['created_at'][:10]<='2026-10-20':
  r['text_norm']=norm(r['text'])
  if len(r['text_norm'])>=2:rows.append(r)
# 동일 시간 동일 본문 제거. 반복 홍보 판정은 원문 흐름 보존을 위해 최종 집계 때 별도 적용.
seen=set();clean=[]
for r in rows:
 key=(r['stock_id'],r['created_at'],r['text_norm'])
 if key not in seen:clean.append(r);seen.add(key)
lookup={(r['stock_id'],r['post_id']):r['text_norm'] for r in clean}
emitted=set();files=sorted(inp.glob('batch-*.jsonl'))
for f in files:
 for line in f.read_text().splitlines():
  r=json.loads(line);emitted.add((r['stock_id'],r['post_id']))
new=[]
for r in clean:
 if (r['stock_id'],r['post_id']) in emitted:continue
 parent=lookup.get((r['stock_id'],r['parent_id']),'')
 # 아직 수집 중인 부모 맥락은 나중에 포함하도록 댓글은 부모 확보 시에만 발행
 if r['parent_id'] and not parent:
  done=con.execute("SELECT v FROM state WHERE k='run_complete'").fetchone()
  if not done or done[0]!='true':continue
 new.append(dict(stock_id=r['stock_id'],post_id=r['post_id'],target_name={'005380':'현대차','010120':'LS ELECTRIC'}[r['stock_id']],text_norm=r['text_norm'],parent_text=parent,context_status='parent_available' if parent else 'parent_missing' if r['parent_id'] else 'top_level'))
for i in range(0,len(new),30):
 part=new[i:i+30]
 # 마지막 소묶음도 불변 파일로 발행해 동일 입력을 보장
 f=inp/f'batch-{len(files)+i//30:05d}.jsonl';tmp=f.with_suffix('.tmp');tmp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in part));tmp.replace(f)
(L/'input_progress.json').write_text(json.dumps({'emitted_rows':len(emitted)+len(new),'new_rows':len(new),'batches':len(list(inp.glob('batch-*.jsonl'))),'prompt_sha256':hashlib.sha256((L/'prompt.md').read_bytes()).hexdigest()},ensure_ascii=False,indent=2))
print('input rows',len(emitted)+len(new),'new',len(new),'batches',len(list(inp.glob('batch-*.jsonl'))))
