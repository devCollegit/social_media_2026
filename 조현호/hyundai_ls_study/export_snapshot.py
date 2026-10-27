"""사용자 요청으로 현재 확보분을 고정·검사해 공개 가능한 자료를 발행한다.
검사 규칙은 김정기 export_shared_dataset.py (7ae6250)에서 재사용했다.
완전한 익명화를 보장하지 않는다. 원문·원래 ID·정확한 시각·AI 자유서술 근거는 제외한다.
"""
import re,json,csv,sqlite3,uuid,hashlib,datetime,bisect,collections,shutil
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'private/full_20260701_20261020';L=D/'llm';O=R/'shared/snapshot_20261027';O.mkdir(parents=True,exist_ok=True)
PATTERNS={
    'contact':r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\d)(?:01[016789]|0\d{1,2})[- .]?\d{3,4}[- .]?\d{4}(?!\d)',
    'link_or_mention':r'https?://\S+|www\.\S+|#\[[^\]]*\]\([^)]*\)|@[A-Za-z0-9_]{2,}',
    'address':r'[가-힣]+(?:로|길)\s*\d+|\d+동\s*\d+호',
    'person_reference':r'(?<![가-힣])[가-힣A-Za-z0-9_]{2,15}(?:님|씨|형님|언니|누나|오빠|아저씨)(?![가-힣])',
    'financial_detail':r'평단|보유|물렸|손실|수익률|계좌|매수가|매입가|손익|평가손|[0-9,]+\s*(?:주|만원|억)',
    'private_life':r'(?:우리|저희|제)\s*(?:엄마|아빠|아버지|어머니|가족|아내|남편|여친|남친|딸|아들)|제\s*이름|주민등록|생년월일|계좌번호|입원|수술|암진단|암\s*진단',
}
COMPILED={k:re.compile(v,re.I) for k,v in PATTERNS.items()}


def screen(text):
    return sorted(k for k,pattern in COMPILED.items() if pattern.search(str(text)))


def excel_safe(text):
    text=str(text)
    escaped=text.lstrip().startswith(('=','+','-','@'))
    return ("'"+text if escaped else text),escaped

con=sqlite3.connect(D/'collection.sqlite')
raw=[json.loads(x[0]) for x in con.execute('SELECT payload FROM posts ORDER BY code,at,id')]
pred={(r['stock_id'],r['post_id']):r for r in map(json.loads,(L/'predictions.jsonl').read_text().splitlines())}
norm=lambda t:re.sub(r'\s+',' ',re.sub(r'(.)\1{3,}',r'\1\1',re.sub(r'https?://\S+',' ',t))).strip()
clean=[];seen=set();stats=collections.Counter()
for r in raw:
 if not '2026-09-01'<=r['created_at'][:10]<='2026-10-20':continue
 r['text_norm']=norm(r['text'])
 if len(r['text_norm'])<2:continue
 k=(r['stock_id'],r['created_at'],r['text_norm'])
 if k in seen:continue
 seen.add(k);clean.append(r)
counts=collections.Counter((r['stock_id'],r['created_at'][:10],r['text_norm']) for r in clean);seen=set();rows=[]
for r in clean:
 k=(r['stock_id'],r['created_at'][:10],r['text_norm'])
 if counts[k]>=4 and k in seen:continue
 seen.add(k);rows.append(r)
mapfile=D/'share_id_mapping.json'
ids=json.loads(mapfile.read_text()) if mapfile.exists() else {}
for r in rows:ids.setdefault(r['stock_id']+':'+r['post_id'],uuid.uuid4().hex)
mapfile.write_text(json.dumps(ids))
daily={(r['stock_id'],r['trading_date']):r for r in csv.DictReader((D/'daily_llm.csv').open())}
dates={code:sorted(d for c,d in daily if c==code) for code in ['005380','010120']}
public=[]
for r in rows:
 code=r['stock_id'];key=(code,r['post_id']);p=pred.get(key,{});flags=screen(r['text_norm'])
 text,escaped=excel_safe(r['text_norm']) if not flags else ('',False)
 assert not screen(text)
 day=r['created_at'][:10];ds=dates[code];i=bisect.bisect_left(ds,day)
 if i<len(ds) and ds[i]==day and r['created_at'][11:26]>'15:30:00.000000':i+=1
 trade=ds[i] if i<len(ds) else '';m=daily.get((code,trade),{})
 status='classified' if p else 'unclassified';stats[status]+=1;stats['text_withheld']+=bool(flags)
 stats.update('flag_'+x for x in flags)
 public.append(dict(record_id=ids[code+':'+r['post_id']],stock_id=code,name={'005380':'현대차','010120':'LS ELECTRIC'}[code],created_date=day,trading_date=trade,
 record_type='댓글' if r['parent_id'] else '게시글',parent_record_id=ids.get(code+':'+r['parent_id'],''),
 text_norm=text,text_status='withheld_privacy_screen' if flags else 'available',text_excel_escaped=escaped,
 classification_status=status,relevance=p.get('relevance',''),sentiment=p.get('sentiment',''),model='gpt-6-luna' if p else '',
 same_day_return_pct=m.get('same_day_return_pct',''),next_day_return_pct=m.get('next_day_return_pct','')))
with (O/'records.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=list(public[0]),lineterminator='\n');w.writeheader();w.writerows(public)
(O/'daily_summary.csv').write_text((D/'daily_llm.csv').read_text(),encoding='utf-8-sig')
by={}
for code in dates:
 rs=[r for r in public if r['stock_id']==code]
 by[code]={'rows':len(rs),'posts':sum(r['record_type']=='게시글' for r in rs),'comments':sum(r['record_type']=='댓글' for r in rs),'classified':sum(r['classification_status']=='classified' for r in rs),'unclassified':sum(r['classification_status']=='unclassified' for r in rs),'from':min(r['created_date'] for r in rs),'to':max(r['created_date'] for r in rs),'sentiments':dict(collections.Counter(r['sentiment'] for r in rs if r['sentiment']))}
manifest={'frozen_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),'status':'frozen_partial_collection_partial_classification','requested_scope':['2026-09-01','2026-10-20'],'freeze_reason':'user requested stop and share data already collected','rows':len(public),'stocks':by,'screening_stats':dict(stats),'model':'gpt-6-luna','reasoning_effort':'medium','workers':3,'is_MoA':False,'prompt_origin':'reconstructed public teammate rules','human_accuracy_evaluated':False,'collection_complete':False,'classification_complete':stats['unclassified']==0,'original_ids_shared':False,'exact_times_shared':False,'ai_reasons_and_evidence_shared':False,'privacy_screening':'whole text withheld on rule match; not complete anonymization','market_source':'Naver public daily; KRX adjustment convention not verified','limitations':['stock coverage periods differ','reply collection phase not performed','unclassified is not neutral','labels refer to original text before privacy withholding'],'sha256':{n:hashlib.sha256((O/n).read_bytes()).hexdigest() for n in ['records.csv','daily_summary.csv']}}
(O/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(D/'frozen_snapshot.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps(manifest,ensure_ascii=False))
