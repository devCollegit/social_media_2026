from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import json,csv,numpy as np,zipfile,math
O=Path(__file__).parent;J=json.loads((O/'results.json').read_text());A=list(csv.DictReader((O/'session_daily.csv').open(encoding='utf-8-sig')))
FT='/System/Library/Fonts/AppleSDGothicNeo.ttc';BLUE='#3182F6';INK='#191F28';SUB='#4E5968';RED='#E84655'
def f(n,b=False):return ImageFont.truetype(FT,n,index=2 if b else 0)
def t(d,x,y,s,n=28,c=INK,b=False):d.text((x,y),s,font=f(n,b),fill=c)
names={'pre':'개장 전','during':'정규장 중','after':'정규장 후'};windows={'pre':'00:00~09:00 이전','during':'09:00~15:30','after':'15:30 이후~24:00'}
heads={'pre':'개장 전 감성과 이후 주가의\n관계는 약했습니다','during':'장중 감성은 그날의 주가 변화와\n함께 움직이는 경향이 있었습니다','after':'장후 감성은 다음 날보다\n그날 이미 끝난 등락과 가까웠습니다'}
for idx,se in enumerate(names,1):
 st=J['stocks']['010120']['sessions'][se];check=next(x for x in J['sensitivity_checks'] if x['session']==se and x['target']=='same_day_open_close_return_pct');r=check['pearson']
 im=Image.new('RGB',(1800,1160),'#F2F4F6');d=ImageDraw.Draw(im);t(d,75,40,'TEAM 06 / 시간대 분리 실험',25,BLUE,True);t(d,1640,40,f'0{idx}',27,INK,True)
 t(d,75,100,names[se]+'  |  '+windows[se],31,BLUE,True)
 for i,line in enumerate(heads[se].split('\n')):t(d,75,160+i*72,line,54,INK,True)
 d.rounded_rectangle((75,340,1120,1010),24,fill='white');d.rounded_rectangle((1150,340,1725,1010),24,fill='white')
 t(d,110,365,'LS ELECTRIC  ·  32거래일',31,INK,True);t(d,110,412,'세로: 당일 시가 → 종가 수익률(%)',26,SUB)
 x0,x1,y0,y1=210,1060,490,900;lo,hi=-12,12
 # Symmetric common axes across all three panels; all points must fit.
 xy=[(float(x['score']),float(x['same_day_open_close_return_pct'])) for x in A if x['stock_id']=='010120' and x['session']==se and x['score']!='']
 assert len(xy)==32 and all(-1<=x<=1 and lo<=y<=hi for x,y in xy)
 px=lambda x:x0+(x+1)/2*(x1-x0);py=lambda y:y1-(y-lo)/(hi-lo)*(y1-y0)
 for v in [-10,-5,0,5,10]:
  y=py(v);d.line((x0,y,x1,y),fill='#9CA8B6' if v==0 else '#E5E8EB',width=2);t(d,140,y-16,f'{v:+d}' if v else '0',23,SUB)
 for v in [-1,-.5,0,.5,1]:
  x=px(v);d.line((x,y0,x,y1),fill='#9CA8B6' if v==0 else '#E5E8EB',width=2);t(d,x-25,y1+15,f'{v:g}',23,SUB)
 for x,y in xy:d.ellipse((px(x)-7,py(y)-7,px(x)+7,py(y)+7),fill=BLUE)
 t(d,260,960,'가로: 시간대 감성 지수  (-1 부정 ↔ +1 긍정)',25,SUB)
 t(d,1190,380,'당일 수익률과의 상관',29,INK,True);t(d,1190,433,f'r = {r:+.2f}',66,BLUE,True)
 t(d,1190,538,f'분류된 게시글 {st["classified"]:,}건',28,INK)
 t(d,1190,590,f'통합 감성 지수 {st["pooled_score_classified_only"]:+.2f}',28,INK)
 t(d,1190,680,'날짜 하나씩 빼도',27,SUB);t(d,1190,723,f'r = {check["leave_one_day_out_min"]:+.2f} ~ {check["leave_one_day_out_max"]:+.2f}',30,INK,True)
 if se=='after':
  t(d,1190,820,'다음 날 시가→종가와는',26,SUB);t(d,1190,864,'r = -0.25  ·  31거래일',30,INK,True);t(d,1190,916,'예측 성능 검증 결과는 아님',24,SUB)
 else:
  t(d,1190,825,'현대차는 유효 날짜가',27,SUB);t(d,1190,870,'8일로 적어 해석 보류',29,INK,True)
 d.line((75,1035,1725,1035),fill='#D1D6DB',width=2)
 t(d,75,1050,'9/1~10/20 확보분 · 거래일만 분석 · 각 날짜 확보분 전부 분류 + 유효 글 5건 이상',24,SUB)
 t(d,75,1090,'KRX 정규장 시각을 기준으로 구분(NXT 거래가 포함될 수 있음) · 상관은 인과·예측력의 증명이 아닙니다.',23,SUB)
 im.save(O/f'{idx:02d}_{se}_결과.png')
# Report contains both stocks and all computed contrasts, including weak or withheld results.
lines=['# 커뮤니티 시간대 3구분 탐색 실험','', '추가 수집·추가 AI 판정 없이 2026-10-27 고정한 32,091건과 기존 일봉을 재집계했다. 수집과 분류의 미완료 상태를 유지하며 결과를 확대 해석하지 않는다.','', '## 요약','', 'LS ELECTRIC에서는 개장 전 감성과 이후 당일 시가→종가 수익률의 상관이 약했다(r=-0.11). 장중 감성과 당일 수익률은 r=+0.53, 장후 감성과 이미 끝난 당일 수익률은 r=+0.63이었다. 이 표본은 장전 예측 신호보다는 당일 가격 변화와 동반·사후 감성의 관계를 더 뚜렷하게 보여준다. 가격이 감성을 유발했다는 인과관계까지 입증한 것은 아니다.','', '## 시간 구분과 표본','', '- KST 달력 날짜 기준: 개장 전 00:00~09:00 미만 / 정규장 중 09:00~15:30 포함 / 정규장 후 15:30 초과~24:00 미만.','- KRX 정규장 시각을 분석 기준으로 정한 것이며 전후 구간에도 NXT 거래가 포함될 수 있다. 08~20시 전체를 하나로 묶지 않았다.','- 휴장일은 거래일 감성과 섞지 않고 별도 집계했다. 전일 장후+당일 장전을 합친 야간 구간 분석은 이번 실험에서 하지 않았다.','- 날짜·시간대별 확보분에 미분류가 하나라도 남거나 유효 글 5건 미만이면 지수를 비웠다. 유효 글은 related 중 긍정·중립·부정이며 혼합·판단유보는 제외한다.','- 통합 지수는 분류된 유효 글을 합쳐 계산한 참고값이다. 일별 지수의 단순 평균과 다르다.','', '|종목|시간대|확보 게시글|분류 완료|미분류|유효 일수|분류분 통합 지수|','|---|---|---:|---:|---:|---:|---:|']
for code,name in [('005380','현대차'),('010120','LS ELECTRIC')]:
 for se in names:
  s=J['stocks'][code]['sessions'][se];lines.append(f'|{name}|{names[se]}|{s["posts"]:,}|{s["classified"]:,}|{s["unclassified"]:,}|{s["valid_days"]}|{s["pooled_score_classified_only"]:+.3f}|')
lines+=['', '휴장일 제외 게시글: 현대차 982건, LS ELECTRIC 73건. 세 구간과 휴장일의 합은 고정 공유본의 종목별 행 수와 일치한다.','', '## 주가와의 관계: LS ELECTRIC','', '|시간대 감성|비교 가격 변화|거래일 수|Pearson r|해석|','|---|---|---:|---:|---|', '|개장 전|당일 시가→종가|32|-0.114|이후 당일 방향과 약한 관계|','|장중|당일 시가→종가|32|+0.527|같은 시간 구간의 동반 관계|','|장후|당일 시가→종가|32|+0.627|이미 끝난 가격 변화와의 사후 관계|','|장후|다음 거래일 시가→종가|31|-0.250|약한 역방향 관계; 예측력으로 간주하지 않음|','', '당일 수익률은 (당일 종가/당일 시가-1)×100이다. 이전 그림의 종가→종가 등락률과 다른 지표다. 다음 날 비교는 10/20까지의 시장 날짜 안에서만 계산해 마지막 날은 제외했다.','', '## 민감도 점검','', '|비교|순위상관 Spearman|하루씩 제외한 Pearson 범위|','|---|---:|---|']
for s in J['sensitivity_checks']:
 label=names[s['session']]+('→다음 날' if s['target'].startswith('next') else '↔당일');lines.append(f'|{label}|{s["spearman"]:+.3f}|{s["leave_one_day_out_min"]:+.3f}~{s["leave_one_day_out_max"]:+.3f}|')
lines+=['', '장중·장후의 당일 관계는 하루를 제외해도 양의 상관이 유지됐다. 장후→다음 날은 순위상관 -0.118이고 한 날짜를 제외하면 Pearson이 -0.053까지 약해져 안정적인 예측 신호로 보기는 어렵다. 기간 절반별 값은 results.json에 남겼다.','', '## 현대차 해석과 한계','', '현대차의 유효 날짜는 장전 8일·장중 8일·장후 9일뿐이다. 탐색용 표시 기준인 10일에 못 미쳐 상관계수 해석을 보류했다. 이 10일 기준은 통계적 검정력을 보장하는 기준이 아니다. 분류 완료분만 통합한 감성 수치는 미분류가 많은 전체 기간을 대표하지 않는다.','', '32거래일의 짧은 부분 표본, 사람 기준 분류 정확도 미측정, 시장·뉴스 통제 부재, 시계열 자기상관, 여러 시차 비교 및 선택 편향이 남아 있다. p값·유의성·인과관계·예측 성능을 주장하지 않는다. 장중 분봉 없이 시간 단위 선행·후행이나 변동성(장중 변동 폭)을 검증한 실험도 아니다. 수익률은 네이버 일봉 기준이며 수정주가 대조 전이다.','', '## 재현과 파일','', '- session_daily.csv: 개인정보·원문 없는 종목/날짜/세션별 집계와 수익률.','- correlations.csv: 표본 부족으로 비운 값까지 포함한 전체 탐색 상관표.','- results.json: 구분 기준, 표본 수, 모든 비교 및 민감도 결과.','- analyze_sessions.py: 고정 공유본의 행 소속·라벨을 사용하고 비공개 원자료의 정확한 시각만 결합.','- 01~03 PNG: 팀 공유용 그림.']
(O/'실험결과.md').write_text('\n'.join(lines)+'\n')
with zipfile.ZipFile(O/'시간대3구분_실험결과.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in O.iterdir():
  if p.suffix in ['.png','.md','.csv','.json','.py']:z.write(p,p.name)
print('Report, 3 figures and ZIP generated.')
