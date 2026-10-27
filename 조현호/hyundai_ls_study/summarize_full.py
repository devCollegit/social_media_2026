"""수집분·AI판정을 거래일·분모와 함께 집계. 미래 가격을 분류에 사용하지 않는다."""
import json,csv,sqlite3,re,bisect,collections,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'private/full_20260701_20261020';L=D/'llm'
con=sqlite3.connect(D/'collection.sqlite');raw=[json.loads(x[0]) for x in con.execute('SELECT payload FROM posts ORDER BY code,at,id')]
completion_row=con.execute('SELECT v FROM state WHERE k=?',('run_complete',)).fetchone()
collection_complete=bool(completion_row and json.loads(completion_row[0]))
P={}
if (L/'predictions.jsonl').exists():P={(r['stock_id'],r['post_id']):r for r in map(json.loads,(L/'predictions.jsonl').read_text().splitlines())}
def norm(t):return re.sub(r'\s+',' ',re.sub(r'(.)\1{3,}',r'\1\1',re.sub(r'https?://\S+',' ',t))).strip()
rows=[];ex=collections.Counter();seen=set()
for r in raw:
 if not '2026-09-01'<=r['created_at'][:10]<='2026-10-20':ex['outside_period']+=1;continue
 r['text_norm']=norm(r['text'])
 if len(r['text_norm'])<2:ex['too_short']+=1;continue
 key=(r['stock_id'],r['created_at'],r['text_norm'])
 if key in seen:ex['same_time_text']+=1;continue
 rows.append(r);seen.add(key)
counts=collections.Counter((r['stock_id'],r['created_at'][:10],r['text_norm']) for r in rows);seen=set();clean=[]
for r in rows:
 key=(r['stock_id'],r['created_at'][:10],r['text_norm'])
 if counts[key]>=4 and key in seen:ex['same_day_repeat_ge4']+=1;continue
 clean.append(r);seen.add(key)
summary={'scope':['2026-09-01','2026-10-20'],'status':'in_progress_until_collection_and_classification_complete','raw_fetched_rows':len(raw),'clean_rows':len(clean),'excluded':dict(ex),'cleaning':'URL removed, repeat >=4 collapsed to 2, whitespace normalized, min2, same timestamp/text dedup, same-day >=4 repeats keep first','stocks':{},'model':'gpt-6-luna','reasoning_effort':'medium','comparison_limits':['private teammate prompt unavailable; reconstructed public schema/rules','new periods differ by stock-specific collection coverage','human accuracy not evaluated','3 agents partition data, not MoA voting'],'evidence_validation':'see llm/validation_summary.json'}
daily=[];final=[]
for code,name in [('005380','현대차'),('010120','LS ELECTRIC')]:
 rs=[r for r in clean if r['stock_id']==code];pred=[P[(code,r['post_id'])] for r in rs if (code,r['post_id']) in P]
 all_market=list(csv.DictReader((R/'private'/f'{code}_market.csv').open()));prior_return={m['date']:round((float(m['close'])/float(all_market[j-1]['close'])-1)*100,6) for j,m in enumerate(all_market) if j>0};market=[r for r in all_market if '2026-09-01'<=r['date']<='2026-10-20'];dates=[r['date'] for r in market];groups=collections.defaultdict(list);unassigned=0
 for r in rs:
  d=r['created_at'][:10];i=bisect.bisect_left(dates,d)
  if i<len(dates) and dates[i]==d and r['created_at'][11:26]>'15:30:00.000000':i+=1
  if i>=len(dates):unassigned+=1;continue
  groups[dates[i]].append(r)
 for i,m in enumerate(market):
  gr=groups[m['date']];pp=[P[(code,r['post_id'])] for r in gr if (code,r['post_id']) in P];ct=collections.Counter(r['sentiment'] for r in pp);rel=collections.Counter(r['relevance'] for r in pp)
  eligible=[r for r in pp if r['relevance']=='related' and r['sentiment'] in ['긍정','중립','부정']];cc=collections.Counter(r['sentiment'] for r in eligible);n=len(eligible);nall=len(gr)
  val=round((cc['긍정']-cc['부정'])/n,6) if n>=5 and len(pp)==nall else ''
  prev=[len(groups[d]) for d in dates[max(0,i-20):i]]
  # 수집 관측이 없는 날을 게시판 글0으로 바꾸지 않는다. 활동배수는 완전성 점검 후에만 계산.
  ret=lambda j:prior_return.get(market[j]['date'],'') if 0<=j<len(market) else ''
  daily.append({'stock_id':code,'name':name,'trading_date':m['date'],'observed_rows':nall,'classified':len(pp),'unclassified':nall-len(pp),'related':rel['related'],'unrelated':rel['unrelated'],'unclear':rel['unclear'],'positive':ct['긍정'],'negative':ct['부정'],'neutral':ct['중립'],'mixed':ct['혼합'],'abstained':ct['판단유보'],'eligible':n,'sentiment_score':val,'classified_coverage':round(len(pp)/nall,6) if nall else '', 'eligible_coverage':round(n/nall,6) if nall else '', 'close':m['close'],'volume':m['volume'],'same_day_return_pct':ret(i),'next_day_return_pct':ret(i+1) if i+1<len(market) else '', 'market_source':'Naver public daily; KRX adjustment convention not verified','collection_empty_is_unknown':not bool(nall)})
 summary['stocks'][code]={'name':name,'clean_rows':len(rs),'classified_rows':len(pred),'unclassified_rows':len(rs)-len(pred),'sentiments':dict(collections.Counter(r['sentiment'] for r in pred)),'relevance':dict(collections.Counter(r['relevance'] for r in pred)),'market_days':len(market),'observed_trading_days':sum(bool(v) for v in groups.values()),'after_last_close_unassigned':unassigned,'valid_index_days':sum(d['stock_id']==code and d['sentiment_score']!='' for d in daily),'collection_state':json.loads(con.execute('SELECT v FROM state WHERE k=?',(code+':list',)).fetchone()[0])}
 for r in rs:
  if (code,r['post_id']) in P:final.append(dict(r,**{k:v for k,v in P[(code,r['post_id'])].items() if k not in ['stock_id','post_id']}))
summary['collection_complete']=collection_complete
summary['classification_complete']=all(s['unclassified_rows']==0 for s in summary['stocks'].values())
if collection_complete and summary['classification_complete']:
 summary['status']='complete_for_collected_scope'
if (D/'frozen_snapshot.json').exists():summary['status']='frozen_partial_collection_partial_classification'
for row in daily:row['collection_complete']=collection_complete
with (D/'daily_llm.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(daily[0]));w.writeheader();w.writerows(daily)
with (D/'clean_classified.jsonl').open('w') as f:
 for r in final:f.write(json.dumps(r,ensure_ascii=False)+'\n')
(D/'analysis_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False))
