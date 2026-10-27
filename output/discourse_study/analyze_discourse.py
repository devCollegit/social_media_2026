from pathlib import Path
import csv,json,collections,statistics,hashlib
O=Path(__file__).parent;R=O.parents[1];S=R/'조현호/hyundai_ls_study/shared/snapshot_20261027';X=R/'output/session_experiment'
a=[r for r in csv.DictReader((X/'session_daily.csv').open(encoding='utf-8-sig')) if r['stock_id']=='010120'];dates=sorted(set(r['date'] for r in a))
def direction(v):return 'up' if v>.5 else 'down' if v<-.5 else 'flat'
daily=[]
for date in dates:
 rr=[r for r in a if r['date']==date];ret=float(rr[0]['same_day_open_close_return_pct']);d={'date':date,'open_close_return_pct':ret,'group':direction(ret),'posts':sum(int(r['observed_posts']) for r in rr)}
 for r in rr:d[r['session']+'_posts']=int(r['observed_posts']);d[r['session']+'_score']=float(r['score'])
 daily.append(d)
summary={}
for name in ['up','down','flat']:
 rr=[r for r in daily if r['group']==name];summary[name]={'n_days':len(rr),'total_posts':sum(r['posts'] for r in rr),'mean_posts_per_day':statistics.mean(r['posts'] for r in rr),'median_posts_per_day':statistics.median(r['posts'] for r in rr),'min_posts':min(r['posts'] for r in rr),'max_posts':max(r['posts'] for r in rr),'session_daily_mean_score':{se:statistics.mean(r[se+'_score'] for r in rr) for se in ['pre','during','after']}}
# Selection uses price alone, independent of which wording looks persuasive.
cases=[max(daily,key=lambda r:r['open_close_return_pct']),min(daily,key=lambda r:r['open_close_return_pct']),min(daily,key=lambda r:abs(r['open_close_return_pct']))]
samples=json.loads((O/'표본_검토용.json').read_text());assert len(samples)==36 and len({r['record_id'] for r in samples})==36
codes=[['하락우려'],['시장참조'],['하락우려'],['저점매수기대'],['수급해석'],['호재와가격의괴리','원인탐색'],['기대회복','주식의인화'],['매수권유','저점매수기대'],['다른투자자이탈평가'],['놓칠불안'],['저점매수축하'],['상승기대'],['수급추종','상승기대'],['추세지속요구'],['상승기대'],['추세불확실','보유언급'],['밈','위험경고'],['이탈언급'],['실망불만'],['동종비교','원인탐색'],['실망불만','기대반전'],['기대반전'],['재진입욕구','갈등'],['장기보유언급'],['기대반전'],['동종비교','상대박탈'],['하락불안'],['수급참조','상승요구'],['기회비용','불만'],['수급비교','상승기대'],['불신','추가매수주저'],['타인매도권유','하락예상'],['이탈의향','불만'],['기대반전','불신'],['동종비교','상대박탈'],['수급참조','상승기대']]
for row,labels in zip(samples,codes):row['qualitative_codes']=labels
(O/'검토표본_36건.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2)+'\n')
with (O/'daily_activity_and_mood.csv').open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(daily[0]),lineterminator='\n');w.writeheader();w.writerows(daily)
result={'dataset':'frozen LS ELECTRIC; 5878 classified posts, 5805 trading-day posts, 73 nontrading-day posts','grouping':'same-day open-to-close return >0.5% up, <-0.5% down, otherwise flat; descriptive outcome grouping, not a forecast','score_average':'equal-weight mean of daily session scores; not pooled text-weighted index','groups':summary,'cases':cases,'qualitative_method':'3 price-selected extreme/near-flat days, each 3 sessions, 4 chronological quantile positions per session among public-screen-passing texts of 12..220 characters; 36 total; purposive nonrepresentative sample. Codes are direct AI qualitative reading by the assistant, not new gpt-6-luna batch labels, no human/intercoder validation. Original sentiment labels unchanged.','qualitative_codes':dict(collections.Counter(c for r in samples for c in r['qualitative_codes'])),'limitations':['outcome-conditioned group selection cannot establish prediction','32 days, no news/market controls, no causal or significance claim','posts are not unique authors, no audience size or author-level trajectory','privacy withholding and length filters affect qualitative sample','no actual replies; no interaction-network or diffusion analysis','NXT trading may occur in pre/after KRX clock windows','Naver daily prices, adjustment convention unverified']}
(O/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
