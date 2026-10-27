"""같은 기간의 과거 목록·댓글 수집. 순차 요청·재개·원문 Git 제외."""
import os,sys,json,csv,sqlite3,time,hashlib,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parent;D=ROOT/'private/full_20260701_20261020';D.mkdir(parents=True,exist_ok=True)
if (D/'frozen_snapshot.json').exists():raise SystemExit('사용자 요청으로 수집 범위를 고정했습니다. 추가 수집하지 않습니다.')
os.environ['SSL_CERT_FILE']=str(ROOT/'private/system_ca.pem');sys.path.insert(0,str(ROOT/'private/source'))
from collector.fetchers import TossFetcher
from collector.http import RequestController
from collector.parser import parse_page,now_kst,COLUMNS
START='2026-09-01T00:00:00.000000+09:00';END='2026-10-20T23:59:59.999999+09:00'
con=sqlite3.connect(D/'collection.sqlite');con.execute('CREATE TABLE IF NOT EXISTS posts(code TEXT,id TEXT,parent TEXT,at TEXT,payload TEXT,PRIMARY KEY(code,id))');con.execute('CREATE TABLE IF NOT EXISTS state(k TEXT PRIMARY KEY,v TEXT)');con.commit()
def get(k,default=None):
 r=con.execute('SELECT v FROM state WHERE k=?',(k,)).fetchone();return json.loads(r[0]) if r else default
def put(k,v):con.execute('INSERT OR REPLACE INTO state VALUES(?,?)',(k,json.dumps(v,ensure_ascii=False)));con.commit()
def save(rs):
 for r in rs:con.execute('INSERT OR REPLACE INTO posts VALUES(?,?,?,?,?)',(r['stock_id'],r['post_id'],r['parent_id'],r['created_at'],json.dumps(r,ensure_ascii=False)))
 con.commit()
def dump():
 out={'requested_start':START,'requested_end':END,'as_of':now_kst(),'source_commit':'7ae6250','request_interval_sec':2,'stocks':{}}
 for code in ['005380','010120']:
  rows=[json.loads(x[0]) for x in con.execute('SELECT payload FROM posts WHERE code=? ORDER BY at,id',(code,))]
  with (D/f'{code}_raw.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=COLUMNS);w.writeheader();w.writerows(rows)
  target=[r for r in rows if START<=r['created_at']<=END]
  out['stocks'][code]={'fetched_rows':len(rows),'target_rows':len(target),'target_posts':sum(not r['parent_id'] for r in target),'target_comments':sum(bool(r['parent_id']) for r in target),'earliest':min((r['created_at'] for r in rows),default=None),'latest':max((r['created_at'] for r in rows),default=None),'list_state':get(code+':list',{}),'reply_parents_complete':con.execute("SELECT COUNT(*) FROM state WHERE k LIKE ? AND v='true'",(code+':reply_done:%',)).fetchone()[0]}
 (D/'progress.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));return out
argp=argparse.ArgumentParser(description=__doc__)
argp.add_argument('--max-list-pages',type=int,default=1000)
args=argp.parse_args()
if not 1<=args.max_list_pages<=5000:argp.error('max-list-pages must be 1..5000')
f=TossFetcher(ROOT/'private/stock_master.csv',max_requests=3000,timeout=25);ctl=RequestController(min_interval=2,max_retries=0)
with (D/'collection_runs.jsonl').open('a') as audit:
 audit.write(json.dumps({'started_at':now_kst(),'max_requests':3000,'max_list_pages':args.max_list_pages,'interval_sec':2,'scope':[START,END]},ensure_ascii=False)+'\n')
try:
 # commentId 최신순 공개 커서에서 종료일 직후 위치를 탐색한다. 경계의 상단에서 시작해 대상 글 누락을 피한다.
 for code in ['005380','010120']:
  if get(code+':seek_done',False):continue
  st=get(code+':list',{'cursor':None,'pages':0,'complete':False})
  if st.get('complete') or (st.get('earliest_page') and st['earliest_page']<=END):put(code+':seek_done',True);continue
  high=int(st.get('cursor') or 0)
  if not high:
   page=ctl.call(lambda:f.list_page(code,None));rs,_,_,_=parse_page(page,now_kst(),code);save(rs);high=max(int(r['post_id']) for r in rs)
  low=0
  while high-low>100:
   mid=(low+high)//2
   page=ctl.call(lambda:f.list_page(code,mid));rs,_,_,_=parse_page(page,now_kst(),code)
   valid=[r for r in rs if int(r['post_id'])<mid]
   if not valid or max(r['created_at'] for r in valid)<=END:low=mid
   else:high=mid
  st['cursor']=high;st['seek_upper_cursor']=high;st['seek_lower_cursor']=low;put(code+':list',st);put(code+':seek_done',True)
  print(json.dumps({'phase':'seek_end_boundary','code':code,'cursor_range':high-low,'requests':f.requests}),flush=True)
 # 완결된 한 종목에 치우치지 않게 25페이지 단위로 두 종목을 번갈아 수집
 while True:
  active=False
  for code in ['005380','010120']:
   st=get(code+':list',{'cursor':None,'pages':0,'complete':False})
   if st['complete']:continue
   if st['pages']>=args.max_list_pages:raise RuntimeError(f'종목 목록 안전한도 {args.max_list_pages}페이지; 범위 미완료')
   active=True
   for _ in range(25):
    cursor=st['cursor'];page=ctl.call(lambda:f.list_page(code,cursor));rs,key,more,_=parse_page(page,now_kst(),code);save(rs)
    st['pages']+=1;st['cursor']=key;st['earliest_page']=min((r['created_at'] for r in rs),default=None)
    if any(r['created_at']<START for r in rs) or not more:st['complete']=True
    if more and key==cursor:raise RuntimeError('목록 커서 반복')
    put(code+':list',st)
    if st['complete']:break
   progress=dump();print(json.dumps({'phase':'list','code':code,'pages':st['pages'],'earliest':st.get('earliest_page'),'target_rows':progress['stocks'][code]['target_rows'],'complete':st['complete'],'requests':f.requests},ensure_ascii=False),flush=True)
  if not active:break
 # 부모 시점과 댓글 시점은 다를 수 있어 시작 이전으로 넘어간 경계 페이지 부모도 포함
 for code in ['005380','010120']:
  parents=[json.loads(x[0]) for x in con.execute("SELECT payload FROM posts WHERE code=? AND parent='' ORDER BY at,id",(code,))]
  for j,parent in enumerate(parents):
   pid=parent['post_id']
   if parent['created_at']>END or not int(parent['reply_count']) or get(code+':reply_done:'+pid,False):continue
   cursor=get(code+':reply_cursor:'+pid,None)
   while True:
    page=ctl.call(lambda:f.reply_page(code,pid,cursor));rs,key,more,_=parse_page(page,now_kst(),code)
    for r in rs:r['parent_id']=r['parent_id'] or pid
    save(rs)
    if not more:put(code+':reply_done:'+pid,True);break
    if key==cursor:raise RuntimeError('댓글 커서 반복')
    cursor=key;put(code+':reply_cursor:'+pid,cursor)
   if j%20==0:
    progress=dump();print(json.dumps({'phase':'replies','code':code,'parent_index':j,'parents_total':len(parents),'target_rows':progress['stocks'][code]['target_rows'],'requests':f.requests},ensure_ascii=False),flush=True)
 put('run_complete',True);dump();print('COLLECTION_COMPLETE',flush=True)
except Exception as e:
 put('last_error',{'type':type(e).__name__,'message':str(e)[:200],'at':now_kst()});dump();print('COLLECTION_STOP '+type(e).__name__+': '+str(e)[:200],flush=True);sys.exit(1)
