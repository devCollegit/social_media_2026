from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
import csv,zipfile,json
R=Path(__file__).resolve().parents[3];O=Path(__file__).parent
rows=list(csv.DictReader((R/'조현호/hyundai_ls_study/shared/snapshot_20261027/daily_summary.csv').open(encoding='utf-8-sig')))
W,H=1600,1060;BLUE='#3182F6';RED='#E84655';INK='#191F28';SUB='#4E5968';BG='#F2F4F6';FT='/System/Library/Fonts/AppleSDGothicNeo.ttc'
def f(n,b=False):return ImageFont.truetype(FT,n,index=2 if b else 0)
def t(d,x,y,s,n=30,c=INK,b=False):d.text((x,y),s,font=f(n,b),fill=c)
def base(i,label,title):
 im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im);t(d,70,40,'TEAM 06  /  COMMUNITY × PRICE',23,BLUE,True);t(d,1440,40,f'0{i}',26,INK,True)
 t(d,70,105,label,27,BLUE,True)
 for j,line in enumerate(title.split('\n')):t(d,70,158+j*70,line,54,INK,True)
 return im,d

def box(d,xy):d.rounded_rectangle(xy,24,fill='white')
def foot(d,a,b):
 d.line((70,945,1530,945),fill='#D1D6DB',width=2);t(d,70,965,a,24,SUB);t(d,70,1003,b,22,SUB)
def save(im,n):im.save(O/n)
im,d=base(1,'무엇을 확인했나','두 종목의 주가가 하락한 구간에서\n부정 감성이 함께 관찰됐습니다')
box(d,(70,345,1530,690));t(d,115,383,'같은 기간으로 맞춰 본 8거래일',36,INK,True);t(d,115,443,'2026.10.08 → 10.20',58,BLUE,True)
t(d,115,547,'현대차',34,INK,True);t(d,440,547,'주가 -5.9%',42,RED,True);t(d,1030,552,'8일 모두 부정 우세',31,INK,True)
t(d,115,615,'LS ELECTRIC',34,INK,True);t(d,440,615,'주가 -22.7%',42,RED,True);t(d,1030,620,'8일 모두 부정 우세',31,INK,True)
t(d,80,757,'아직 “감성이 주가를 예측했다”는 뜻은 아닙니다.',37,INK,True)
t(d,80,827,'확보 게시글 32,091건 · AI 분류 16,866건의 부분 분석',29,SUB)
foot(d,'현대차의 일별 지수를 산출할 수 있는 공통 기간을 사용했습니다.','등락률은 10/8 종가 대비 10/20 종가 · 추가 수집 종료 · 실제 답글 미포함')
save(im,'01_핵심요약.png')
# Identical chart scales for sentiment; separate stock-price scales, explicitly labelled.
for i,code,label,title,file in [(2,'005380','현대차','주가는 반등하기도 했지만,\n부정 감성은 8일 모두 이어졌습니다','02_현대차.png'),(3,'010120','LS ELECTRIC','주가가 하락한 구간에서\n부정 감성이 계속 관찰됐습니다','03_LSELECTRIC.png')]:
 a=[r for r in rows if r['stock_id']==code and r['trading_date']>='2026-10-08'];assert len(a)==8 and all(r['sentiment_score']!='' for r in a)
 vals=[float(r['close']) for r in a];scores=[float(r['sentiment_score']) for r in a];assert all(v<0 for v in scores)
 pct=(vals[-1]/vals[0]-1)*100
 im,d=base(i,label,title);box(d,(70,337,1530,925))
 t(d,110,365,f'종가 변화  {pct:+.1f}%',36,RED,True);t(d,870,371,f'{vals[0]:,.0f}원 → {vals[-1]:,.0f}원',30,INK)
 x0,x1=235,1440;xs=[x0+(x1-x0)*j/7 for j in range(8)];top,bottom=465,635
 lo=min(vals)*.96;hi=max(vals)*1.04;py=lambda v:bottom-(v-lo)/(hi-lo)*(bottom-top)
 for v in [min(vals),max(vals)]:
  y=py(v);d.line((x0,y,x1,y),fill='#E5E8EB',width=2);t(d,110,y-16,f'{v/10000:.1f}만',24,SUB)
 d.line(list(zip(xs,map(py,vals))),fill=BLUE,width=6)
 for x,v in zip(xs,vals):y=py(v);d.ellipse((x-6,y-6,x+6,y+6),fill=BLUE)
 t(d,110,683,'일별 감성',29,INK,True);t(d,890,683,'음수 = 긍정보다 부정이 많음',26,SUB)
 zero,low=755,845;d.line((x0,zero,x1,zero),fill='#9CA8B6',width=2);t(d,165,zero-16,'0',23,SUB);t(d,153,low-15,'-1',23,SUB)
 for x,v in zip(xs,scores):d.rectangle((x-25,zero,x+25,zero+abs(v)*(low-zero)),fill=RED)
 for x,r in zip(xs,a):t(d,x-31,865,r['trading_date'][5:].replace('-','/'),24,SUB)
 foot(d,'같은 8거래일 비교 · 주가와 감성의 날짜 축은 동일합니다.', 'AI 판정, 사람 기준 정확도 미측정 · 감성 지수: (긍정 - 부정)/(긍정 + 중립 + 부정)')
 save(im,file)
im,d=base(4,'어떻게 해석하면 될까','하락을 미리 예고한 것인지,\n하락한 뒤 나온 반응인지는 아직 모릅니다')
box(d,(70,350,1530,565));t(d,115,390,'이번에 확인한 것',31,BLUE,True);t(d,115,451,'하락한 구간에서도 부정 반응이 이어졌음',40,INK,True)
box(d,(70,600,1530,815));t(d,115,638,'아직 확인하지 않은 것',31,BLUE,True);t(d,115,702,'감성이 먼저?    주가가 먼저?',43,INK,True)
t(d,82,865,'다음 분석은 두 신호의 시간차를 검증하는 일입니다.',31,INK,True)
foot(d,'현재 자료는 예측 성능이나 인과관계를 검증한 결과가 아닙니다.','현대차는 전체 확보분의 41.9%만 AI 분류 · 시세: 네이버 일봉, 수정주가 대조 전')
save(im,'04_해석과한계.png')
(O/'팀채팅_공유문구.txt').write_text('현대차와 LS ELECTRIC을 같은 8거래일(10/8~10/20)로 맞춰 봤습니다. 이 구간의 종가는 각각 약 5.9%, 22.7% 하락했고, 일별 감성은 두 종목 모두 8일 내내 부정 우세였습니다. 다만 반등한 날에도 부정 감성이 남아 있어 매일 같은 방향으로 움직였다는 뜻은 아닙니다. 감성이 하락을 예고했는지, 하락에 반응한 것인지는 아직 검증하지 않았습니다.\n')
with zipfile.ZipFile(O/'팀공유_간단그래프_4장.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(O.glob('*.png')):z.write(p,p.name)
 z.write(O/'팀채팅_공유문구.txt','팀채팅_공유문구.txt')
print('4 images exported; common 8-day coverage and endpoint changes verified.')
