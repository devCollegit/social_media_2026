"""Prepare a bounded review batch from existing unclassified public text. Does not call any AI."""
import argparse,sqlite3,json,hashlib
from pathlib import Path
P=Path(__file__).resolve().parent;ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--limit',type=int,default=50);args=ap.parse_args()
policy=json.loads((P/'cost_policy.json').read_text());limits=policy['configured_limits_for_manual_preparation']
if not 1<=args.limit<=limits['max_records_per_ai_batch']:ap.error('batch limit outside configured cap')
db=P/'shared/community.sqlite';c=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
jobs=[];chars=0;seen=set()
for r in c.execute("SELECT source_id,record_id,stock_id,text_norm FROM records WHERE classification_status='unclassified' AND text_status='available' ORDER BY stock_id,created_date,record_id"):
 text=r['text_norm'];digest=hashlib.sha256(text.encode()).hexdigest()
 if digest in seen or len(text)>limits['max_characters_per_record']:continue
 if chars+len(text)>limits['max_characters_per_ai_batch']:continue
 jobs.append(dict(r));seen.add(digest);chars+=len(text)
 if len(jobs)>=args.limit:break
O=P/'private';O.mkdir(exist_ok=True);path=O/'review_batch.jsonl'
path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in jobs))
print(json.dumps({'records':len(jobs),'text_characters':chars,'new_ai_calls':0,'actual_tokens_and_cost':'not measured; no AI call made','output':str(path),'note':'Preview queue only; repeated execution overwrites the same preview, not a scheduled job.'},ensure_ascii=False))
