from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from pypdf import PdfReader
import pathlib
for n,f in [('R','Regular'),('B','Bold'),('X','ExtraBold')]:pdfmetrics.registerFont(TTFont(n,f'/Users/billy/Library/Fonts/NanumGothic-{f}.ttf'))
pdfmetrics.registerFontFamily('R',normal='R',bold='B',italic='R',boldItalic='B')
OUT=str(pathlib.Path(__file__).resolve().parent/'output'/'토스증권_감성분석_중간보고서.pdf')
pathlib.Path(OUT).parent.mkdir(parents=True,exist_ok=True)
c=canvas.Canvas(OUT,pagesize=(960,540));c.setTitle('Market Voice | 가로형 프로젝트 제안서')
BLUE='#3182F6';INK='#191F28';GRAY='#4E5968';PALE='#F2F6FC';LINE='#E5E8EB'
def text(x,y,s,size=12,font='R',color=INK):c.setFillColor(HexColor(color));c.setFont(font,size);c.drawString(x,y,s)
def p(x,y,w,s,size=13,font='R',color=INK):
 st=ParagraphStyle('p',fontName=font,fontSize=size,leading=size*1.55,textColor=HexColor(color),wordWrap='CJK');a=Paragraph(s,st);_,h=a.wrap(w,500);a.drawOn(c,x,y-h);return h

def box(x,y,w,h,col=PALE):c.setFillColor(HexColor(col));c.roundRect(x,y,w,h,12,fill=1,stroke=0)
def line(x,y,w):c.setStrokeColor(HexColor(LINE));c.setLineWidth(.8);c.line(x,y,x+w,y)
def base(n,label,title,sub):
 text(42,507,'market voice',12,'X',BLUE);text(747,507,'소셜미디어 분석 6조',10,color=GRAY)
 text(42,471,['I','II','III','IV','V','VI'][n-1]+'  '+label,12,'B',BLUE)
 text(42,429,title,29,'X');p(42,405,876,sub,12,color=GRAY)
 text(42,22,'토스증권 커뮤니티 공포탐욕지수 · 프로젝트 제안 · 2026.10.13',9,color=GRAY);text(876,22,f'{n} / 6',9,'B',GRAY)
def end():c.showPage()
base(1,'제안 개요','게시판의 반응을, 시장의 정보로','커뮤니티 공포탐욕지수를 검증하고, 대시보드와 정기 리포트로 제공합니다.')
box(42,116,400,253,BLUE);text(63,338,'우리가 제안하는 서비스',12,'B','#E8F3FF');p(63,306,350,'투자자들이<br/>무엇에 반응하는지,<br/>데이터로 읽고<br/>리포트로 전합니다.',25,'X','#FFFFFF')
text(474,346,'대시보드',17,'B',BLUE);p(474,323,437,'개인투자자: 종목별 심리와 가격 흐름을 살펴보고<br/>반응이 바뀐 시점의 공시·뉴스를 확인합니다.',13)
line(474,263,444);text(474,236,'정기 리포트',17,'B',BLUE);p(474,214,437,'금융 미디어·투자교육 운영자: 사건별 반응을<br/>기사·뉴스레터·교육 콘텐츠의 근거로 활용합니다.',13)
for y,a,b in [(136,'검증 가설','감성 → 다음 날 거래량 (기준 사전 고정)'),(105,'검증 대상','5개 지표의 타당성 · 분류 방식 정확도와 비용'),(74,'결과물','대시보드 · 월간 리포트 · 사례집')]:
 text(474,y,a,12,'B',BLUE);text(563,y,b,12,'B')
text(42,76,'현재: 주제 선정·기획안·HTML 예시 제작 완료',11,'B');text(42,53,'실증 분석·분류 성능·사업화는 계획 단계',10,color=GRAY)
end()
base(2,'서비스 시안','공포와 탐욕을 읽는 화면','팀 HTML의 정보 구조를 기준으로 종목 → 섹터 → 시장의 3계층 지수를 구성합니다.')
box(42,103,557,268);box(42,335,557,36,BLUE);text(58,348,'토스 커뮤니티 공포탐욕지수',14,'B','#FFFFFF');text(420,348,'실제 주가 · 지표는 합성',10,'B','#FFFFFF')
box(58,236,205,83,'#FFFFFF');text(73,297,'시장 요약',12,'B',BLUE)
for i,col in enumerate(['#F04452','#F0B5BB','#B0B8C1','#90C2FF',BLUE]):box(74+i*34,264,31,13,col)
text(73,247,'공포 ← 0~100 → 탐욕',11)
box(279,236,304,83,'#FFFFFF');text(294,297,'섹터 비교',12,'B',BLUE);p(294,280,274,'반도체 · 2차전지 · 바이오 · 플랫폼<br/>방산·조선 · 금융 · 엔터',11)
text(58,212,'종목 패널 / 두 축 · 5개 하위 지표',13,'B')
for i,(s,t) in enumerate([('스탠스','방향'),('키워드','방향'),('인증','방향'),('관심도','과열'),('쏠림','과열')]):
 x=58+i*107;box(x,167,99,29,'#FFFFFF');text(x+12,183,s,11,'B',BLUE);text(x+12,171,t,8.5,color=GRAY)
text(58,145,'종목 상세: 지수·종가 추이 → 선행/후행 교차상관',11,'B');text(58,123,'국면 판정: 과열매수 · 낙관 · 중립 · 비관 · 패닉',11)
text(631,347,'지수 산출',16,'B');p(631,324,287,'S = (긍정 - 부정) ÷ (전체 글 수 + 10)<br/>분모의 10은 글이 적은 날의 변동을 줄입니다.<br/>S를 직전 20거래일 안에서 0~100 백분위로<br/>변환하고, 섹터·시장 지수는 글 수로 가중합니다.',11.5)
text(631,211,'두 축으로 나눈 이유',16,'B');p(631,189,287,'관심도·쏠림에는 방향이 없습니다. 폭락일에도<br/>값이 커지므로 다섯 지표를 하나로 합치면<br/>공포가 극심한 날이 탐욕으로 찍힙니다.<br/>방향 ≥ 56 &amp; 강도 ≥ 80은 과열매수,<br/>방향 ≤ 45 &amp; 강도 ≥ 80은 패닉입니다.',11)
p(42,82,876,'데모 설명: KRX 일봉(2026.06.01~10.02, 12종목) + 합성 커뮤니티 지표. 후행 관계는 설계된 결과이며 실증 성과가 아닙니다.<br/>시장 비교는 KODEX 200 ETF 대리값을 사용합니다. 주가 원출처 대조는 별도로 수행합니다.',9.2,color=GRAY)
end()
base(3,'MoA 및 실증 검증','한 문장을 여러 관점으로 읽고, 효과를 비교합니다','분류 방식 비교와 주가 관계 검증을 분리해 분석 품질과 추가 정보를 평가합니다.')
for i,(a,b) in enumerate([('투자 방향','강세·약세·중립 판별'),('은어·반어','문맥과 표현 해석'),('근거 검토','종목 전망·감정 구분')]):
 x=42+i*183;box(x,289,170,74);text(x+13,338,a,14,'B',BLUE);p(x+13,316,144,b,11)
box(42,229,536,43,BLUE);text(58,245,'원문 + 독립 판단 → 종합 판정 → 사람 검수',14,'B','#FFFFFF')
p(42,211,536,'분류 방식은 셋 중 선택합니다. <b>1</b> 사람 라벨 → 모델 학습 &nbsp; <b>2</b> LLM 라벨 + 사람 검수 → 모델 학습 &nbsp; <b>3</b> LLM 직접 분류.<br/>같은 평가 표본에서 사전·금융 감성 모델·단일 LLM·MoA를 비교합니다. MoA는 응답 종합 방식이며 모델 내부 MoE와 구분합니다.',9.6,color=GRAY)
for y,a,b in [(132,'품질','macro-F1 · 은어/반어 오류 · 미판정 비율'),(97,'운영','글 1,000건당 비용 · 처리 시간')]:
 text(42,y,a,13,'B',BLUE);text(101,y,b,12)
text(631,366,'가설과 검증 방식',17,'B')
text(631,342,'가설 검정 · 판정 기준은 데이터 확인 전 고정',10,'B',BLUE);line(631,334,287)
p(631,328,287,'<b>H1</b>  오늘 감성지수는 <b>다음 날 거래량</b>을 설명한다',11)
p(631,308,287,'검증 · 오늘 수익률·거래량 비율·시장 수익률 통제<br/>패널 회귀 (종목 고정효과 · 종목별 군집 표준오차)',9.5,color=GRAY)
p(631,277,287,'채택 조건 · 감성 계수 b &gt; 0, p &lt; 0.05',9.5,color=GRAY)
text(631,243,'지수 검증 · 판정 없이 수치만 보고',10,'B',BLUE);line(631,235,287)
for y,a,b in [(222,'상식 점검','급등일 평균 감성 &gt; 급락일'),(201,'말과 행동','개인 순매수 비율과의 상관')]:
 text(631,y,a,10,'B');p(748,y+11,170,b,9.5,color=GRAY)
text(631,180,'추가 분석 · 판정 없이 수치만 보고',10,'B',BLUE);line(631,172,287)
for y,a,b in [(159,'후행','수익률 → 다음 날 감성'),(138,'과열 후 반전','국면별 이후 5일 초과수익률'),(117,'맞은편 투자자','개인 대비 외국인 순매수'),(96,'머신러닝 비교','KRX 단독 vs KRX+감성'),(75,'밤사이 심리','장전 감성 vs 장중 감성')]:
 text(631,y,a,10,'B');p(748,y+11,170,b,9.5,color=GRAY)
p(42,61,876,'거래량을 판정 대상으로 둔 이유: 커뮤니티 활동은 수익률 방향보다 거래량을 더 잘 설명합니다(Antweiler &amp; Frank, 2004). 수익률 버전은 참고로 보고합니다.<br/>오늘 수익률을 통제하지 않으면 "주가가 크게 움직여 글도 늘고 거래량도 늘어난 것"이 감성의 예측력처럼 보입니다. 약 60거래일은 짧아, 기각하지 못함이 관계 없음은 아닙니다.',9.3,color=GRAY)
end()
base(4,'사업 및 출판 전략','분석은 서비스로, 사례는 책으로','종목 심리 리포트를 시범 제작하고, 독자와 구매자 후보의 반응으로 발행 범위를 정합니다.')
text(42,346,'상품과 구매자',16,'B');box(42,295,525,31,BLUE)
for x,s in [(55,'판매 상품'),(242,'구매자 가설'),(444,'과금 가설')]:text(x,306,s,11,'B','#FFFFFF')
for i,(a,b,d) in enumerate([('종목·사건별 리포트','금융 미디어·뉴스레터','건별 제작'),('정기 브리핑·대시보드','투자교육 운영자','월·분기 구독'),('사례집·전자책','투자심리·분석 독자','책 판매')]):
 y=267-i*49;line(42,y-23,525);text(55,y,a,11,'B');text(242,y,b,11);text(444,y,d,11)
p(42,132,525,'이용 조건·제작 비용·구매자 인터뷰를 확인해 판매 가능성과 가격을<br/>정합니다. 샘플과 단순 지표 시안을 비교해 유용성·지불 의향을 묻습니다.',11)
box(606,115,312,254);box(623,150,114,198,BLUE);text(636,321,'MARKET',17,'X','#FFFFFF');text(636,296,'VOICE',17,'X','#FFFFFF');p(636,258,88,'투자자의 말,<br/>시장의 움직임',12,'B','#FFFFFF');text(636,168,'표지 시안',10,color='#FFFFFF')
for y,a,b in [(323,'심리 브리핑','지수·가격 흐름'),(252,'사건별 해설','반응 변화·공시'),(181,'방법과 근거','MoA 비교·출처')]:text(755,y,a,13,'B',BLUE);text(755,y-23,b,11)
box(42,59,876,31);text(56,69,'수요 확인 → 정기 발행 시험    /    수요 부족 → 교육용 사례집으로 범위 조정',12,'B',BLUE)
end()
base(5,'수집 및 팀 실행','실제 데이터로 완성하는 계획','100~200종목 × 약 60거래일 목표 · 일평균 글·댓글 20건 이상 종목을 우선 검토합니다.')
text(42,354,'이우창 · 조현호 · 김동우 · 류창민 · 송이현 · 김정기 · 탁채린',13,'B',BLUE)
text(42,320,'역할과 수행 순서',16,'B')
for i,(a,b,d) in enumerate([('1 커뮤니티 수집','토스 종목 게시판 글·댓글','종목코드·작성시각·본문·매수/매도 인증 뱃지'),('2 감성 분석','기준표 · 분류 방식 선택 · 검수','라벨 300건 / 분류 모델 / macro-F1·혼동행렬'),('3 KRX 수집·연계','pykrx 일봉 · 투자자 동향 · 공매도','종목코드+거래일 결합 패널 / 가설 검정·지수 검증'),('4 UI 설계·구축','시장 요약 · 종목 상세 · 회귀 화면','대시보드 / 국면 지도 / 급등·급락일 목록')]):
 y=281-i*45;line(42,y+15,564);text(42,y,a,11,'B',BLUE);text(170,y,b,11,'B');text(170,y-17,d,9.5,color=GRAY)
p(42,118,564,'1과 3은 처음부터 병렬. 2는 1의 산출물을, 3의 연계 분석은 2의 결과를 받아 이어집니다. 5 발표는 처음부터 끝까지 병행합니다.',9.5,color=GRAY)
text(638,318,'시간 정렬',16,'B');p(638,294,280,'15:30 이후 글 → 다음 거래일.<br/>장전 감성은 15:30~익일 08:30 글로 별도 산출.<br/>종목코드·실제 거래일로 시세 결합.',11.5)
text(638,213,'KRX 지표',16,'B');p(638,189,280,'수익률 · 초과수익률(KODEX 200/코스닥150)<br/>일중 변동폭 · 거래량 비율(20일 평균 대비)<br/>갭·장중 수익률 · 급등락일(±5%)<br/>개인·외국인 순매수 비율 · 공매도 비중 (로그인)',10.5)
p(42,91,876,'남은 결정: 과거 글 수집 범위(불가 시 지금부터 매일 수집 + 종목 수 확대) · 인증 뱃지 수집 여부(불가 시 방향 지수를 스탠스·키워드 2지표로) · 분류 방식 선택 · 담당자 배정.<br/>자료: <link href="https://app.notion.com/p/3f1b5370280b80af9256c02bfb73fdf6">팀 기획안</link> 및 공포탐욕지수 개정안(류창민) / <link href="https://arxiv.org/abs/2406.04692">Wang 외, Mixture-of-Agents(2024)</link> / <link href="https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.grangercausalitytests.html">statsmodels Granger 문서</link> / <link href="https://tossmini-docs.toss.im/tds-mobile/foundation/colors/">Toss Design System</link>.<br/>실증 분석·분류 성능·사업화는 계획 단계입니다. 패널 행 수가 늘어도 시장 관측일 수는 늘지 않습니다. 크롤링은 요청 간격을 제한하고 원문을 재배포하지 않습니다.',9.2,color=GRAY)
end()
base(6,'구현 현황','기획을 실행 코드로 옮겼습니다','설계한 분석 절차를 8단계 파이프라인으로 구현하고, 합성 표본과 실데이터 입력 형식 양쪽에서 동작을 점검했습니다.')
text(42,352,'파이프라인 8단계',16,'B')
for i,(a,b) in enumerate([('수집','어댑터 분리'),('정제','중복·홍보 제거'),('감성 분류','사전 기준선'),('시장 자료','시세·지수')]):
 x=42+i*141;box(x,296,129,46,'#FFFFFF');line(x,296,129);text(x+13,323,a,12,'B',BLUE);text(x+13,305,b,10,color=GRAY)
for i,(a,b) in enumerate([('거래일 집계','종가 기준 배정'),('패널 병합','감성 × 시세'),('통계 검증','상관·회귀·Granger'),('결과 요약','표·그림·한계')]):
 x=42+i*141;box(x,240,129,46,'#FFFFFF');line(x,240,129);text(x+13,267,a,12,'B',BLUE);text(x+13,249,b,10,color=GRAY)
box(42,183,564,43,BLUE);text(58,208,'하나의 컨트롤러에서 단계 선택 · 재실행 · 산출물 캐싱',13,'B','#FFFFFF');text(58,190,'실행마다 설정 지문과 단계별 지표를 기록해 결과를 추적합니다.',10,color='#D6E7FF')
text(42,164,'설계 원칙의 코드 반영',14,'B')
for y,a,b in [(138,'시간 정렬','직전 거래일 기준 시각 ~ 당일 기준 시각. 이후 글은 다음 거래일.'),(114,'결측 처리','글이 없거나 기준 미달인 날은 0이 아닌 결측. 기준별 민감도 비교.'),(90,'통계 처리','시차 탐색에 BH 보정, 회귀에 Newey-West HAC, Granger 는 보조.')]:
 text(42,y,a,11,'B',BLUE);text(134,y,b,11)
text(638,352,'동작 점검',16,'B')
p(638,330,280,'합성 표본에 <b>감성 선행</b> 관계를 심고 전체 단계를 실행해<br/>분석 코드가 이를 탐지하는지 확인했습니다.',11,color=GRAY)
for y,a,b in [(272,'시차 상관','k=+1 최대'),(243,'선행 회귀','3종목 유의'),(214,'Granger 감성→수익률','유의'),(185,'Granger 수익률→감성','유의하지 않음')]:
 line(638,y-9,280);text(638,y,a,11,'B');c.setFillColor(HexColor(BLUE));c.setFont('B',11);c.drawRightString(918,y,b)
p(638,166,280,'선행과 후행이 <b>구분되어</b> 보고되는 것을 확인했습니다.<br/>합성 자료 점검 결과이며 연구 결과가 아닙니다.',10,color=GRAY)
text(638,110,'수집 전 확인',14,'B')
p(638,90,280,'자동 수집 코드는 포함하지 않았습니다.<br/>이용 조건·접근 범위 확인 전에는 수집을 막는<br/>설정을 기본값으로 두었습니다.',11)
box(42,30,564,52);p(58,76,532,'<b>남은 작업</b>  수집 가능 여부 확인 · 종목·기간 확정 · 예비 수집 · 2인 독립 라벨링.<br/><b>개정안 미반영</b>  분모 평활(+10)·20일 백분위 · 두 축 분해 · 패널 회귀(고정효과·군집 SE) · 거래량 목표변수 · 장전 감성 · 추가 분석.<br/><b>구현 상세</b>  조현호/toss_sentiment/ (README.md, docs/개발기록.md)',9,color=GRAY)
end();c.save();r=PdfReader(OUT);assert len(r.pages)==6;assert all(float(pg.mediabox.width)==960 and float(pg.mediabox.height)==540 for pg in r.pages);print(f'Verified {len(r.pages)} landscape pages, 16:9 → {OUT}')
