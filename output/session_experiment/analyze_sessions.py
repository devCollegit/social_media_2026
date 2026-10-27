from pathlib import Path
import csv,json,sqlite3,re,collections,math
import numpy as np
R=Path(__file__).resolve().parents[2];O=Path(__file__).parent;P=R/'조현호/hyundai_ls_study';F=P/'private/full_20260701_20261020';S=P/'shared/snapshot_20261027'
# Frozen public record IDs select the exact snapshot, while exact timestamps remain private.
ids=json.loads((F/'share_id_mapping.json').read_text());public=list(csv.DictReader((S/'records.csv').open(encoding='utf-8-sig')));pub={r['record_id']:r for r in public}
c=sqlite3.connect(F/'collection.sqlite');groups=collections.defaultdict(list);weekend=collections.Counter();seen=set()
for code,pid,at,payload in c.execute('SELECT code,id,at,payload FROM posts ORDER BY code,at,id'):
 rid=ids.get(code+':'+pid)
 if rid not in pub:continue
 r=pub[rid];assert rid not in seen;seen.add(rid)
 time=at[11:26];session='pre' if time<'09:00:00.000000' else 'during' if time<='15:30:00.000000' else 'after'
 groups[(code,at[:10],session)].append(r)
assert len(seen)==32091
sessions=['pre','during','after'];names={'pre':'개장 전','during':'정규장 중','after':'정규장 후'}
out=[];summary={};corrs=[]
def pearson(x,y):
 if len(x)<10 or np.std(x)==0 or np.std(y)==0:return None
 return float(np.corrcoef(x,y)[0,1])
for code in ['005380','010120']:
 market=list(csv.DictReader((P/'private'/f'{code}_market.csv').open()));all_days={r['date']:r for r in market};dates=[r['date'] for r in market if '2026-09-01'<=r['date']<='2026-10-20'];daily={};stats={}
 for i,day in enumerate(dates):
  m=all_days[day];prev=market[market.index(m)-1] if market.index(m)>0 else None;next_m=all_days[dates[i+1]] if i+1<len(dates) else None
  oc=(float(m['close'])/float(m['open'])-1)*100
  overnight=(float(m['open'])/float(prev['close'])-1)*100 if prev else None
  nextoc=(float(next_m['close'])/float(next_m['open'])-1)*100 if next_m else None
  for se in sessions:
   a=groups[(code,day,se)];classified=[r for r in a if r['classification_status']=='classified'];e=[r for r in classified if r['relevance']=='related' and r['sentiment'] in ['긍정','중립','부정']];ct=collections.Counter(r['sentiment'] for r in e)
   score=(ct['긍정']-ct['부정'])/len(e) if len(e)>=5 and len(classified)==len(a) else None
   row={'stock_id':code,'date':day,'session':se,'observed_posts':len(a),'classified':len(classified),'unclassified':len(a)-len(classified),'eligible':len(e),'positive':ct['긍정'],'neutral':ct['중립'],'negative':ct['부정'],'score':score,'same_day_open_close_return_pct':oc,'overnight_return_pct':overnight,'next_day_open_close_return_pct':nextoc}
   out.append(row);daily[(day,se)]=row
 for se in sessions:
  a=[r for (co,day,s),rr in groups.items() if co==code and s==se and day in dates for r in rr];cl=[r for r in a if r['classification_status']=='classified'];el=[r for r in cl if r['relevance']=='related' and r['sentiment'] in ['긍정','중립','부정']];ct=collections.Counter(r['sentiment'] for r in cl);ec=collections.Counter(r['sentiment'] for r in el)
  stats[se]={'posts':len(a),'classified':len(cl),'unclassified':len(a)-len(cl),'sentiments':dict(ct),'eligible':len(el),'pooled_score_classified_only':(ec['긍정']-ec['부정'])/len(el) if el else None,'valid_days':sum(daily[(d,se)]['score'] is not None for d in dates)}
  targets=[('same_day_open_close_return_pct','当日開終'),('overnight_return_pct','前夜'),('next_day_open_close_return_pct','翌日開終')]
  for key,_ in targets:
   pairs=[(daily[(day,se)]['score'],daily[(day,se)][key]) for day in dates if daily[(day,se)]['score'] is not None and daily[(day,se)][key] is not None]
   x=[a for a,b in pairs];y=[b for a,b in pairs];r=pearson(x,y)
   corrs.append({'stock_id':code,'session':se,'target':key,'n_days':len(pairs),'pearson_r':r})
 summary[code]={'sessions':stats,'nontrading_day_posts':sum(len(rr) for (co,day,se),rr in groups.items() if co==code and day not in dates)}
with (O/'session_daily.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=list(out[0]),lineterminator='\n');w.writeheader();w.writerows(out)
with (O/'correlations.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=list(corrs[0]),lineterminator='\n');w.writeheader();w.writerows(corrs)
result={'windows_KST':{'pre':'00:00 <= time < 09:00','during':'09:00 <= time <= 15:30','after':'15:30 < time < 24:00'},'market_reference':'KRX regular-session clock; pre/after may contain NXT trading','scope':'2026-09-01..2026-10-20, frozen snapshot only','method':'Trading dates only; nontrading dates separately counted. Daily score requires every observed post in group classified and >=5 eligible related positive/neutral/negative posts. Pearson only when n>=10; exploratory, no significance or causal claim. No intraday quotes used.','stocks':summary,'correlations':corrs}
(O/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
# Sensitivity checks for the main, predeclared descriptive contrasts.
def ranks(v):
 a=np.asarray(v);order=np.argsort(a);z=np.empty(len(a),float);i=0
 while i<len(a):
  j=i+1
  while j<len(a) and a[order[j]]==a[order[i]]:j+=1
  z[order[i:j]]=(i+j-1)/2;i=j
 return z
checks=[]
for se,target in [('pre','same_day_open_close_return_pct'),('during','same_day_open_close_return_pct'),('after','same_day_open_close_return_pct'),('after','next_day_open_close_return_pct')]:
 a=[r for r in out if r['stock_id']=='010120' and r['session']==se and r['score'] is not None and r[target] is not None];x=np.array([r['score'] for r in a]);y=np.array([r[target] for r in a]);loo=[float(np.corrcoef(np.delete(x,i),np.delete(y,i))[0,1]) for i in range(len(a))]
 checks.append({'session':se,'target':target,'n':len(a),'pearson':float(np.corrcoef(x,y)[0,1]),'spearman':float(np.corrcoef(ranks(x),ranks(y))[0,1]),'leave_one_day_out_min':min(loo),'leave_one_day_out_max':max(loo),'first_half_pearson':float(np.corrcoef(x[:len(a)//2],y[:len(a)//2])[0,1]),'second_half_pearson':float(np.corrcoef(x[len(a)//2:],y[len(a)//2:])[0,1])})
result['sensitivity_checks']=checks
assert sum(x['posts'] for x in summary['005380']['sessions'].values())+summary['005380']['nontrading_day_posts']==26213
assert sum(x['posts'] for x in summary['010120']['sessions'].values())+summary['010120']['nontrading_day_posts']==5878
(O/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('SENSITIVITY',json.dumps(checks))
