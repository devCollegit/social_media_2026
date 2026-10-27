"""Build a shareable SQLite snapshot from already-screened sources. No network or AI calls."""
import csv,io,json,sqlite3,subprocess,hashlib,zipfile,os
from pathlib import Path
R=Path(__file__).resolve().parents[2];P=Path(__file__).resolve().parent;O=P/'shared';O.mkdir(exist_ok=True)
OURS=R/'조현호/hyundai_ls_study/shared/snapshot_20261027'
def sha(b):return hashlib.sha256(b).hexdigest()
revision=subprocess.check_output(['git','rev-parse','origin/kimjunggee-data-collection'],cwd=R,text=True).strip()
def gitfile(name):return subprocess.check_output(['git','show',f'{revision}:김정기/data_collection/shared/analysis_7632/{name}'],cwd=R)
kbytes=gitfile('records.csv');km=json.loads(gitfile('manifest.json'));assert sha(kbytes)==km['records_sha256']
obytes=(OURS/'records.csv').read_bytes();om=json.loads((OURS/'manifest.json').read_text());assert sha(obytes)==om['sha256']['records.csv']
inputs=[('kim_7632',kbytes,revision,'포스코퓨처엠·에코프로머티 공유본','Original teammate gpt-6-luna labels; original IDs/times removed; parent text omitted from unified DB.'),('hyundai_ls_20261027',obytes,om['frozen_at'],'현대차·LS ELECTRIC 고정 공유본','Reconstructed public prompt, partial classification; not directly interchangeable with teammate run.')]
target=O/'community.sqlite';tmp=O/'community.building.sqlite'
if tmp.exists():tmp.unlink()
c=sqlite3.connect(tmp);c.executescript((P/'schema.sql').read_text());c.executemany('INSERT INTO stocks VALUES(?,?)',[('003670','포스코퓨처엠'),('450080','에코프로머티'),('005380','현대차'),('010120','LS ELECTRIC')])
for source,data,rev,desc,note in inputs:
 c.execute('INSERT INTO sources VALUES(?,?,?,?,?)',(source,desc,rev,sha(data),note));seen=set()
 for r in csv.DictReader(io.StringIO(data.decode('utf-8-sig'))):
  assert r['record_id'] not in seen;seen.add(r['record_id'])
  status=r.get('classification_status') or 'classified';kind='post' if r.get('record_type')=='게시글' else 'reply' if r.get('parent_record_id') else 'unknown'
  # Kim's empty parent ID cannot distinguish original posts from replies with missing parents.
  c.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(source,r['record_id'],r['stock_id'],r['created_date'],r['trading_date'] or None,kind,r.get('parent_record_id') or None,r['text_norm'],r['text_status'],str(r.get('text_excel_escaped','false')).lower()=='true',status,r['relevance'] or None,r['sentiment'] or None,r.get('model_name') or r.get('model') or None))
 assert len(seen)==(7632 if source=='kim_7632' else 32091)
for r in csv.DictReader((OURS/'daily_summary.csv').open(encoding='utf-8-sig')):
 c.execute('INSERT INTO market_daily VALUES(?,?,?,?,?,?,?,?)',('hyundai_ls_20261027',r['stock_id'],r['trading_date'],float(r['close']),int(r['volume']),float(r['same_day_return_pct']) if r['same_day_return_pct'] else None,float(r['next_day_return_pct']) if r['next_day_return_pct'] else None,r['market_source']))
se=R/'output/session_experiment/session_daily.csv'
assert se.exists(),'Run existing session analysis first; this build must include its aggregates.'
for r in csv.DictReader(se.open(encoding='utf-8-sig')):
 c.execute('INSERT INTO session_daily VALUES('+','.join('?'*15)+')',('hyundai_ls_20261027',r['stock_id'],r['date'],r['session'],*[int(r[k]) for k in ['observed_posts','classified','unclassified','eligible','positive','neutral','negative']],*[float(r[k]) if r[k] else None for k in ['score','same_day_open_close_return_pct','overnight_return_pct','next_day_open_close_return_pct']]))
c.commit();assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok';assert not c.execute('PRAGMA foreign_key_check').fetchall()
assert c.execute('SELECT COUNT(*) FROM records').fetchone()[0]==39723
assert c.execute("SELECT COUNT(*) FROM records WHERE classification_status='unclassified'").fetchone()[0]==15225
c.row_factory=sqlite3.Row;stats=[dict(r) for r in c.execute('SELECT * FROM stock_summary ORDER BY stock_id')]
c.execute('VACUUM');c.close();os.replace(tmp,target)
manifest={'records':39723,'classified':24498,'unclassified':15225,'stocks':stats,'market_rows':64,'session_rows':192,'db_sha256':sha(target.read_bytes()),'schema_version':1,'original_ids_and_exact_times':False,'new_collection_calls':0,'new_ai_calls':0,'source_inputs':{s:sha(b) for s,b,*_ in inputs},'limits':['Different periods, text types and prompts; retain source IDs.','Only Hyundai/LS market and session aggregates are included.','Text withheld for privacy is not blank sentiment or neutral.','Missing timestamps are not reconstructed.','No human accuracy guarantee.']}
(O/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
with zipfile.ZipFile(O/'community_db.zip','w',zipfile.ZIP_DEFLATED) as z:
 z.write(target,'community.sqlite');z.write(O/'manifest.json','manifest.json');z.write(P/'schema.sql','schema.sql')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
