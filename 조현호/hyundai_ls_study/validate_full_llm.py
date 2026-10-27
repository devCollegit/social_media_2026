"""완성된 배치만 통합. 잘못된 파일은 거부·기록하며 의미 정확도는 주장하지 않는다."""
import json,hashlib
from pathlib import Path
from collections import Counter
R=Path(__file__).resolve().parent;D=R/'private/full_20260701_20261020';L=D/'llm'
FIELDS={'stock_id','post_id','relevance','sentiment','reason','evidence','context_used'}
EXPECTED={};PRED={};PROOFS=[];PENDING=[];REJECTED=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(rows,out):
 ix={(r['stock_id'],r['post_id']):r for r in rows}
 if len(ix)!=len(rows):raise ValueError('duplicate input')
 seen=set()
 for r in out:
  if set(r)!=FIELDS:raise ValueError('wrong schema')
  k=(r['stock_id'],r['post_id']);where=str(k)
  if k not in ix or k in seen:raise ValueError(where+' duplicate or extra ID')
  seen.add(k);a=ix[k]
  if r['relevance'] not in {'related','unrelated','unclear'} or r['sentiment'] not in {'긍정','중립','부정','혼합','판단유보'}:raise ValueError(where+' enum')
  if r['relevance']!='related' and r['sentiment']!='판단유보':raise ValueError(where+' unrelated must abstain')
  if type(r['context_used']) is not bool:raise ValueError(where+' context boolean')
  if r['context_used'] and not a['parent_text']:raise ValueError(where+' missing parent')
  if not isinstance(r['reason'],str) or not r['reason'].strip() or len(r['reason'])>1000:raise ValueError(where+' missing/long reason')
  e=r['evidence']
  if not isinstance(e,str) or len(e)>40:raise ValueError(where+' evidence must be <=40chars')
  if e and e not in a['text_norm'] and (not r['context_used'] or e not in a['parent_text']):raise ValueError(where+' evidence absent')
  if r['sentiment'] in {'긍정','중립','부정'} and not e:raise ValueError(where+' evidence required')
 if seen!=set(ix):raise ValueError('missing rows')
for f in sorted((L/'input').glob('batch-*.jsonl')):
 rows=[json.loads(t) for t in f.read_text().splitlines()]
 for r in rows:
  k=(r['stock_id'],r['post_id'])
  if k in EXPECTED:raise ValueError('duplicate across input batches')
  EXPECTED[k]=r
 files=list(L.glob('worker_*/'+f.name))
 if not files:PENDING.append(f.name);continue
 try:
  if len(files)!=1:raise ValueError('duplicate result files')
  out=[json.loads(t) for t in files[0].read_text().splitlines()];check(rows,out)
 except Exception as e:REJECTED.append({'batch':f.name,'error':str(e)[:250]});continue
 for r in out:PRED[(r['stock_id'],r['post_id'])]=r
 PROOFS.append({'batch':f.name,'rows':len(rows),'input_sha256':sha(f),'output_sha256':sha(files[0]),'worker':files[0].parent.name})
S={'input_rows':len(EXPECTED),'validated_predictions':len(PRED),'completed_batches':len(PROOFS),'pending_batches':len(PENDING),'rejected_batches':REJECTED,'model':'gpt-6-luna','reasoning_effort':'medium','prompt_sha256':sha(L/'prompt.md'),'prompt_origin':'reconstructed from public teammate rules; original private prompt unavailable','is_MoA':False,'human_accuracy_evaluated':False,'classification':dict(Counter(r['sentiment'] for r in PRED.values())),'relevance':dict(Counter(r['relevance'] for r in PRED.values())),'status':'complete_for_current_inputs' if not PENDING and not REJECTED else 'incomplete'}
(L/'validation_summary.json').write_text(json.dumps(S,ensure_ascii=False,indent=2));(L/'proofs.json').write_text(json.dumps(PROOFS,ensure_ascii=False,indent=2))
p=L/'predictions.jsonl';tmp=p.with_suffix('.tmp');tmp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for _,r in sorted(PRED.items())));tmp.replace(p)
print(json.dumps(S,ensure_ascii=False))
