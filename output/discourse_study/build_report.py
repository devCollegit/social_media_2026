from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import json,zipfile
O=Path(__file__).parent;J=json.loads((O/'results.json').read_text());S=json.loads((O/'검토표본_36건.json').read_text());FONT='/System/Library/Fonts/AppleSDGothicNeo.ttc';BLUE='#3182F6';RED='#E84655';INK='#191F28';SUB='#4E5968'
def f(s,b=False):return ImageFont.truetype(FONT,s,index=2 if b else 0)
def t(d,x,y,s,n=28,c=INK,b=False):d.text((x,y),s,font=f(n,b),fill=c)
def base(i,tag,title,sub):
 im=Image.new('RGB',(1800,1140),'#F2F4F6');d=ImageDraw.Draw(im);t(d,75,42,'TEAM 06 / SOCIAL MEDIA ANALYSIS',25,BLUE,True);t(d,1640,42,f'0{i}',27,INK,True)
 t(d,75,108,tag,28,BLUE,True);t(d,75,163,title,55,INK,True);t(d,75,245,sub,28,SUB)
 return im,d
def footer(d,a,b):
 d.line((75,1010,1725,1010),fill='#D1D6DB',width=2);t(d,75,1030,a,24,SUB);t(d,75,1071,b,23,SUB)
im,d=base(1,'LS ELECTRIC / 32거래일','하락일에는 장중·장후 감성이 더 부정적이었습니다','상승 13일 · 하락 16일 · 보합 3일  |  당일 시가 대비 종가 ±0.5%로 구분')
d.rounded_rectangle((75,325,1725,960),24,fill='white');x=[310,850,1390];y=lambda v:845-(v+.7)/1.0*420
for v in [-.6,-.4,-.2,0,.2]:
 yy=y(v);d.line((220,yy,1550,yy),fill='#D1D6DB' if v==0 else '#E5E8EB',width=2);t(d,115,yy-15,f'{v:+.1f}',23,SUB)
for g,col,name in [('up',BLUE,'상승일 평균'),('down',RED,'하락일 평균')]:
 vals=[J['groups'][g]['session_daily_mean_score'][s] for s in ['pre','during','after']];d.line([(xx,y(v)) for xx,v in zip(x,vals)],fill=col,width=6)
 for xx,v in zip(x,vals):d.ellipse((xx-7,y(v)-7,xx+7,y(v)+7),fill=col);t(d,xx-43,y(v)+(15 if (g=='up' and xx==310) or (g=='down' and xx!=310) else -47),f'{v:+.2f}',31,col,True)
for xx,s in zip(x,['개장 전','장중','장후']):t(d,xx-58,867,s,30,INK,True)
t(d,112,350,'감성 지수: 음수일수록 부정 우세',27,SUB);t(d,1060,350,'● 상승일 평균',25,BLUE,True);t(d,1380,350,'● 하락일 평균',25,RED,True)
t(d,112,920,'하루 글 수  평균: 상승일 157건 / 하락일 206건   ·   중앙값: 172건 / 183건',28,INK)
footer(d,'날짜별 시간대 지수의 단순 평균입니다. 보합 3일은 선 그래프에서 제외했습니다.','하락일의 글 수 평균은 일부 다게시일의 영향을 받습니다. 표본은 32일이며 인과·유의성을 주장하지 않습니다.')
im.save(O/'01_상승일과하락일.png')
case_info=[(2,'2026-10-07','기대가 실망으로 바뀌어 나타난 날',['상승 기대','위험을 밈으로 표현','아침 기대와 결과의 괴리'],['오눌 오른다','너... 납치된거야...','아침에 5프로 플러스였는데 분명히..., .']), (3,'2026-10-19','하락 우려 속에서도 저점 매수 축하가 등장했습니다',['추가 하락 우려','의심에서 기대 회복으로','저점 매수 축하'],['기어코 7월 저점 보러가네 ㅡㅡ','미안하다 8시에 일어나서 널 의심했다','바닥 찍으신 분들 축하']), (4,'2026-10-02','주가가 보합이어도 불만은 남아 있었습니다',['다른 종목과 비교','기대와 불신이 공존','다른 종목 상승에 대한 아쉬움'],['일진전기도 7프로 상승이던데','신뢰가 없으니 더태우질 못하겟누','산일이 날라간다.넌 뭐하니?잠자는. 일렉'])]
for idx,day,title,themes,quotes in case_info:
 c=next(c for c in J['cases'] if c['date']==day);ret=c['open_close_return_pct'];im,d=base(idx,'LS ELECTRIC / 사례 읽기',title,f'{day}  |  시가 → 종가 {ret:+.2f}%  |  확보 게시글 {c["posts"]:,}건')
 for j,se in enumerate(['pre','during','after']):
  xx=75+j*560;d.rounded_rectangle((xx,335,xx+530,950),24,fill='white');score=c[se+'_score'];col=BLUE if score>=0 else RED
  t(d,xx+30,375,['개장 전','장중','장후'][j],35,INK,True);t(d,xx+30,439,f'감성 지수 {score:+.2f}',40,col,True);t(d,xx+30,505,f'게시글 {c[se+"_posts"]:,}건',27,SUB)
  # Deterministic wrapping by rendered pixel width.
  def wrap(s,width,n):
   out=[];line=''
   for char in s:
    if d.textlength(line+char,font=f(n))>width:out.append(line);line=char
    else:line+=char
   if line:out.append(line)
   return out
  for k,line in enumerate(wrap(themes[j],460,31)):t(d,xx+30,592+k*43,line,31,INK,True)
  for k,line in enumerate(wrap('“'+quotes[j]+'”',460,30)):t(d,xx+30,733+k*44,line,30,SUB)
 footer(d,'게시글 발췌는 36건의 목적 표본에서 골랐습니다. 전체 게시글의 대표 발언이나 동일 이용자의 변화는 아닙니다.','지수는 해당 시간대 전체 유효 글로 계산 · 주가와 말의 변화 사례이며 원인·예측력을 입증하지 않습니다.')
 im.save(O/f'{idx:02d}_{day}_사례.png')
# Text report with sampling and limits, so selected quotes are not confused with prevalence.
lines=['# 주가 변화 전후 커뮤니티의 감성과 담론: 추가 탐색','', '## 핵심 결과','', 'LS ELECTRIC에서는 가격 변화에 따라 단순 긍정·부정의 양뿐 아니라 기대, 실망, 저점 해석, 동종 종목 비교 등 표현 방식이 달라지는 사례가 관찰됐다. 이번 결과는 소셜미디어를 예측 신호만이 아니라 시장 변화를 해석하고 감정을 표현하는 공간으로 분석할 근거가 된다. 단, 댓글·동일 이용자 추적 자료가 없어 상호작용이나 개인의 태도 전환을 입증하지 않는다.','', '## 데이터와 방법','', '- 고정 공유본 LS ELECTRIC 5,878건 중 거래일의 게시글 5,805건, 휴장일 73건 별도. 추가 수집이나 기존 감성 라벨 수정 없음.','- 정규장 시계 기준 개장 전 00~09시 미만, 장중 09~15:30 포함, 장후 15:30 초과~24시 미만. 전후 구간에도 NXT 거래가 있을 수 있다.','- 32거래일을 시가→종가 수익률 +0.5% 초과 상승, -0.5% 미만 하락, 그 사이는 보합으로 구분했다. 결과를 보고 나눈 기술적 비교이며 예측 평가가 아니다.','- 아래 감성 평균은 매일의 시간대 지수를 같은 가중치로 평균한 것이다. 전체 글을 합친 가중 지수와 다르다.','', '## 1. 상승일과 하락일의 반응','', '|구분|날짜 수|하루 평균 글 수|중앙값|장전 평균 감성|장중 평균 감성|장후 평균 감성|','|---|---:|---:|---:|---:|---:|---:|']
for key,name in [('up','상승일'),('down','하락일'),('flat','보합일')]:
 g=J['groups'][key];v=g['session_daily_mean_score'];lines.append(f'|{name}|{g["n_days"]}|{g["mean_posts_per_day"]:.1f}|{g["median_posts_per_day"]:.0f}|{v["pre"]:+.3f}|{v["during"]:+.3f}|{v["after"]:+.3f}|')
lines+=['', '상승일도 장전·장중 감성 평균은 음수였다. 따라서 긍정이면 상승, 부정이면 하락이라는 단순 대응은 성립하지 않는다. 상승일에는 장후 감성이 평균적으로 거의 0에 가까워졌지만, 하락일에는 장중·장후 부정 우세가 더 컸다.','', '하락일의 게시글 수 평균은 더 높았지만, 중앙값 차이는 작았다(183 대 172). 10/7처럼 글이 575건인 일부 날짜가 평균을 끌어올리므로 하락이 언제나 참여를 늘린다고 단정할 수 없다. 조회수·고유 작성자 수가 아닌 확보 게시글 수다.','', '## 2. 가격만으로 고른 세 날짜의 표현 읽기','', '시가→종가 최대 상승일(10/19), 최대 하락일(10/7), 절대 수익률이 가장 작은 날(10/2)을 선택했다. 각 날짜를 세 시간대로 나누고, 공유 본문이 남아 있으며 길이가 12~220자인 글 가운데 시간순 0·1/3·2/3·마지막 위치에서 4건씩 총 36건을 읽었다. 무작위·대표 표본이 아니며 길이 및 공유 검사에 따른 제외 편향이 있다.','', '정성 주제는 이번 응답의 AI 도우미가 원문을 직접 읽고 부여했다. 기존 gpt-6-luna의 감성 라벨과 별개의 탐색적 해석이며 사람 검수·두 명 간 코딩 일치도는 없다. 정성 주제 빈도는 36건 표본에만 해당한다.','']
for _,day,title,themes,quotes in case_info:
 c=next(c for c in J['cases'] if c['date']==day);lines+=['### '+day+' — '+title,'',f'당일 시가→종가 {c["open_close_return_pct"]:+.2f}%, 게시글 {c["posts"]}건.','', '|구간|감성 지수|표현의 주제|발췌|','|---|---:|---|---|']
 for j,se in enumerate(['pre','during','after']):lines.append(f'|{["장전","장중","장후"][j]}|{c[se+"_score"]:+.3f}|{themes[j]}|{quotes[j]}|')
 lines+=['']
lines+=['## 3. 소셜미디어 분석으로 볼 수 있는 것','', '1. **기대와 결과의 괴리:** 상승 기대가 있던 장전과 장중·장후 실망 표현이 함께 나타날 수 있다. 가격 예측의 성공 여부보다 기대가 어떻게 표현·재해석되는지 볼 수 있다.','2. **가격을 해석하는 말:** 저점·추가 하락·수급·다른 종목 비교가 같은 가격 변화에 대한 상이한 해석으로 나타난다.','3. **플랫폼 표현 방식:** 주식을 의인화한 사과, 납치 같은 밈, 저점 매수 축하 등은 감성 점수 하나로 충분히 설명되지 않는다.','4. **상대적 불만:** 거의 보합인 날에도 다른 종목 상승과 비교하는 아쉬움이 관찰된다. 불만이 반드시 해당 종목 당일 하락만을 뜻하지 않는다.','', '이 주제들은 사례 해석이며 전체 게시판에서 얼마나 흔한지 확정한 결과가 아니다. 같은 사람이 장전과 장후에 말을 바꿨다는 뜻도 아니다.','', '## 라벨 해석 시 주의','', '예를 들어 “지금 안사면 언제사게…”는 기존 라벨이 중립이지만 매수 권유라는 발화 기능으로 읽을 수 있다. “기어코 7월 저점…”의 하락 우려와 “역대급 저점…”의 매수 기대처럼 저점이라는 같은 단어도 방향이 다르다. 따라서 단어 개수만으로 담론을 확정하지 않았고 기존 감성 라벨도 수정하지 않았다. 이는 정식 정확도 평가가 아닌 질적 점검 사례다.','', '## 보고서에 넣을 문장','', '> LS ELECTRIC의 거래일 게시글을 시간대별로 분석한 결과, 하락일에는 장중·장후 부정 감성이 더 강한 경향이 관찰되었다. 가격 변화가 큰 날과 보합일의 게시글 사례에서는 기대의 반전, 저점에 대한 상반된 해석, 동종 종목 비교, 밈과 의인화 등의 표현이 확인되었다. 이는 커뮤니티를 단순한 주가 예측 신호뿐 아니라 시장 변화에 대한 해석과 감정 표현의 공간으로 분석할 필요성을 보여준다. 다만 짧은 관측 기간과 목적 표본의 한계로 인과관계나 전체 이용자의 특성으로 일반화하지 않는다.','', '## 한계와 후속 확인','', '사람 기준 감성 정확도 미측정, 짧은 32일, 부분 수집, 시장·공시·뉴스 통제 부재, 사후 날짜 선택, 자동/홍보 글과 동일 작성자 반복 가능성, 공유 검사·본문 길이로 제외된 글이 남아 있다. 실제 답글과 작성자 네트워크가 없어 전파·상호작용·공감대 형성을 검증하지 못했다. Naver 일봉은 수정주가 대조 전이다. 현대차는 미분류가 많아 이번 담론 사례 실험에서 제외했다. 향후 사람 두 명이 독립적으로 표본을 코딩해 발화 기능·감정·매매 의도를 구분하는 것이 적절하다.','', '## 파일','', '- daily_activity_and_mood.csv: 32일의 글 수·수익률·세 시간대 지수.','- 검토표본_36건.json: 임의 공개 ID·본문·기존 감성·이번 정성 주제. 원래 ID·정확한 시각 없음.','- results.json: 모든 집계와 방법·한계.','- 01~04 PNG: 팀 공유용 요약과 세 사례.']
(O/'추가분석_결과보고서.md').write_text('\n'.join(lines)+'\n')
with zipfile.ZipFile(O/'소셜미디어_추가분석_결과.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in O.iterdir():
  if p.suffix in ['.png','.csv','.json','.md','.py'] and p.name!='표본_검토용.json':z.write(p,p.name)
print('4 images, qualitative sample, report and ZIP created.')
