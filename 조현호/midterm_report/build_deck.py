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
 text(42,22,'토스증권 커뮤니티 공포탐욕지수 · 프로젝트 제안 · 2026.10.11',9,color=GRAY);text(876,22,f'{n} / 6',9,'B',GRAY)
def end():c.showPage()
base(1,'제안 개요','게시판의 반응을, 시장의 정보로','커뮤니티 공포탐욕지수를 검증하고, 대시보드와 정기 리포트로 제공합니다.')
box(42,116,400,253,BLUE);text(63,338,'우리가 제안하는 서비스',12,'B','#E8F3FF');p(63,306,350,'투자자들이<br/>무엇에 반응하는지,<br/>데이터로 읽고<br/>리포트로 전합니다.',25,'X','#FFFFFF')
text(474,346,'대시보드',17,'B',BLUE);p(474,323,437,'개인투자자: 종목별 심리와 가격 흐름을 살펴보고<br/>반응이 바뀐 시점의 공시·뉴스를 확인합니다.',13)
line(474,263,444);text(474,236,'정기 리포트',17,'B',BLUE);p(474,214,437,'금융 미디어·투자교육 운영자: 사건별 반응을<br/>기사·뉴스레터·교육 콘텐츠의 근거로 활용합니다.',13)
for y,a,b in [(136,'연구 질문','동행 · 선행 · 후행 · 극단 이후 역행'),(105,'검증 대상','5개 지표의 타당성 · MoA 정확도와 비용'),(74,'결과물','대시보드 · 월간 리포트 · 사례집')]:
 text(474,y,a,12,'B',BLUE);text(563,y,b,12,'B')
text(42,76,'현재: 주제 선정·기획안·HTML 예시 제작 완료',11,'B');text(42,53,'실증 분석·MoA 성능·사업화는 계획 단계',10,color=GRAY)
end()
base(2,'서비스 시안','공포와 탐욕을 읽는 화면','팀 HTML의 정보 구조를 기준으로 종목 → 섹터 → 시장의 3계층 지수를 구성합니다.')
box(42,103,557,268);box(42,335,557,36,BLUE);text(58,348,'토스 커뮤니티 공포탐욕지수',14,'B','#FFFFFF');text(420,348,'실제 주가 · 지표는 합성',10,'B','#FFFFFF')
box(58,236,205,83,'#FFFFFF');text(73,297,'시장 요약',12,'B',BLUE)
for i,col in enumerate(['#F04452','#F0B5BB','#B0B8C1','#90C2FF',BLUE]):box(74+i*34,264,31,13,col)
text(73,247,'공포 ← 0~100 → 탐욕',11)
box(279,236,304,83,'#FFFFFF');text(294,297,'섹터 비교',12,'B',BLUE);p(294,280,274,'반도체 · 2차전지 · 바이오 · 플랫폼<br/>방산·조선 · 금융 · 엔터',11)
text(58,212,'종목 패널 / 5개 하위 지표',13,'B')
for i,s in enumerate(['스탠스','관심도','쏠림','키워드','인증']):
 x=58+i*107;box(x,167,99,29,'#FFFFFF');text(x+12,177,s,11,'B',BLUE)
text(58,145,'종목 상세: 지수·종가 추이 → 선행/후행 교차상관',11,'B');text(58,123,'극단 구간: 이후 1·3·5일 수익률 비교',11)
text(631,347,'지수 산출',16,'B');p(631,324,287,'종목별 최근 20거래일 백분위로<br/>변환 → 동일 가중 평균.<br/>섹터·시장 지수는 글 수 가중.<br/>인증 수집이 어려우면 4개 지표안 검토.',12)
text(631,211,'해석 기준',16,'B');p(631,189,287,'관심도·쏠림은 공포에서도 높아집니다.<br/>방향과 활동 지표를 분리한 기준안과<br/>비교하고, 일부 종목의 지수를<br/>전체 시장 심리로 일반화하지 않습니다.',12)
p(42,82,876,'데모 설명: KRX 일봉(2026.06.01~10.02, 12종목) + 합성 커뮤니티 지표. 후행 관계는 설계된 결과이며 실증 성과가 아닙니다.<br/>시장 비교는 KODEX 200 ETF 대리값을 사용합니다. 주가 원출처 대조는 별도로 수행합니다.',9.2,color=GRAY)
end()
base(3,'MoA 및 실증 검증','한 문장을 여러 관점으로 읽고, 효과를 비교합니다','MoA 응용 실험과 주가 관계 검증을 분리해 분석 품질과 추가 정보를 평가합니다.')
for i,(a,b) in enumerate([('투자 방향','강세·약세·중립 판별'),('은어·반어','문맥과 표현 해석'),('근거 검토','종목 전망·감정 구분')]):
 x=42+i*183;box(x,289,170,74);text(x+13,338,a,14,'B',BLUE);p(x+13,316,144,b,11)
box(42,229,536,43,BLUE);text(58,245,'원문 + 독립 판단 → 종합 판정 → 사람 검수',14,'B','#FFFFFF')
p(42,211,536,'MoA는 에이전트 응답 종합 방식이며 모델 내부 MoE와 구분합니다.<br/>같은 평가 표본에서 사전·금융 감성 모델·단일 LLM·MoA를 비교합니다.',11,color=GRAY)
for y,a,b in [(132,'품질','macro-F1 · 은어/반어 오류 · 미판정 비율'),(97,'운영','글 1,000건당 비용 · 처리 시간')]:
 text(42,y,a,13,'B',BLUE);text(101,y,b,12)
text(631,344,'네 가지 검증 가설',17,'B')
for y,a,b in [(309,'H1 동행','당일 지수와 당일 목표변수'),(256,'H2 선행','지수 이후 수익률·거래량 변화'),(203,'H3 후행','가격 변화 이후 커뮤니티 반응'),(150,'H4 역행','극단 지수 이후 반대 방향 수익률')]:
 text(631,y,a,12,'B',BLUE);p(631,y-15,287,b,11)
p(42,61,876,'검증: 종목 고정효과·시장/과거 수익률 통제, 시차 상관(-5~+5일), 이벤트 분석. 다중검정·이벤트 중첩을 고려합니다.<br/>Granger는 조건 충족 시 보조 활용하며, 백테스트는 거래비용·시간순 검증을 적용합니다. 선행성은 인과관계를 뜻하지 않습니다.',9.3,color=GRAY)
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
text(42,320,'작업 분담과 산출물',16,'B')
for i,(a,b,d) in enumerate([('수집·결합','커뮤니티 / KRX 시세','글·댓글·인증 확인 / 일봉·종목 마스터'),('스탠스 분류','2인 수동 300건 / 모델 비교','라벨 데이터 / 정확도·비용 비교표'),('지수 계산','5개 지표 / 백분위 / 계층 집계','종목·일 패널 / 섹터·시장 시계열'),('분석·편집','4개 가설 / 화면 / 리포트','통계 결과 / 실제 데이터 화면 / 출판 시안')]):
 y=281-i*45;line(42,y+15,564);text(42,y,a,11,'B',BLUE);text(158,y,b,11,'B');text(158,y-17,d,10,color=GRAY)
text(638,318,'시간 정렬',16,'B');p(638,294,280,'장 마감 이후 글 → 다음 거래일.<br/>종목코드·실제 거래일로 시세 결합.<br/>결측·휴장일·접근 조건을 기록합니다.',12)
text(638,213,'분석 대상',16,'B');p(638,188,280,'초과수익률: 종목 - 소속 시장<br/>회전율: 거래량 / 상장주식수<br/>변동폭: (고가 - 저가) / 시가',12)
p(42,91,876,'현재 완료: 주제 선정·기획안·류창민의 HTML 예시. 담당·기한은 팀 협의로 확정하며 수집·시세·라벨링을 병행합니다.<br/>자료: <link href="https://app.notion.com/p/3f1b5370280b80af9256c02bfb73fdf6">팀 기획안</link> 및 HTML 수정본 / <link href="https://arxiv.org/abs/2406.04692">Wang 외, Mixture-of-Agents(2024)</link> / <link href="https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.grangercausalitytests.html">statsmodels Granger 문서</link> / <link href="https://tossmini-docs.toss.im/tds-mobile/foundation/colors/">Toss Design System</link>.<br/>실증 분석·MoA 성능·사업화는 계획 단계입니다. 패널 행 수가 늘어도 시장 관측일 수는 늘지 않습니다.',9.2,color=GRAY)
end()
base(6,'구현 현황','기획을 실행 코드로 옮겼습니다','설계한 분석 절차를 8단계 파이프라인으로 구현하고, 합성 표본과 실데이터 입력 형식 양쪽에서 동작을 점검했습니다.')
text(42,352,'파이프라인 8단계',16,'B')
for i,(a,b) in enumerate([('수집','어댑터 분리'),('정제','중복·홍보 제거'),('감성 분류','사전 기준선'),('시장 자료','시세·지수')]):
 x=42+i*141;box(x,296,129,46,'#FFFFFF');line(x,296,129);text(x+13,323,a,12,'B',BLUE);text(x+13,305,b,10,color=GRAY)
for i,(a,b) in enumerate([('거래일 집계','종가 기준 배정'),('패널 병합','감성 × 시세'),('통계 검증','상관·회귀·Granger'),('결과 요약','표·그림·한계')]):
 x=42+i*141;box(x,240,129,46,'#FFFFFF');line(x,240,129);text(x+13,267,a,12,'B',BLUE);text(x+13,249,b,10,color=GRAY)
box(42,183,564,43,BLUE);text(58,208,'하나의 컨트롤러에서 단계 선택 · 재실행 · 산출물 캐싱',13,'B','#FFFFFF');text(58,190,'실행마다 설정 지문과 단계별 지표를 기록해 결과를 추적합니다.',10,color='#D6E7FF')
text(42,164,'설계 원칙의 코드 반영',14,'B')
for y,a,b in [(138,'시간 정렬','직전 거래일 종가 이후 ~ 당일 종가. 종가 이후 글은 다음 거래일.'),(114,'결측 처리','글이 없거나 기준 미달인 날은 0이 아닌 결측. 기준별 민감도 비교.'),(90,'통계 처리','시차 탐색에 BH 보정, 회귀에 Newey-West HAC, Granger 는 보조.')]:
 text(42,y,a,11,'B',BLUE);text(134,y,b,11)
text(638,352,'동작 점검',16,'B')
p(638,330,280,'합성 표본에 <b>감성 선행</b> 관계를 심고 전체 단계를 실행해<br/>분석 코드가 이를 탐지하는지 확인했습니다.',11,color=GRAY)
for y,a,b in [(272,'시차 상관','k=+1 최대'),(243,'회귀 H2','3종목 유의'),(214,'Granger 감성→수익률','유의'),(185,'Granger 수익률→감성','유의하지 않음')]:
 line(638,y-9,280);text(638,y,a,11,'B');c.setFillColor(HexColor(BLUE));c.setFont('B',11);c.drawRightString(918,y,b)
p(638,166,280,'선행과 후행이 <b>구분되어</b> 보고되는 것을 확인했습니다.<br/>합성 자료 점검 결과이며 연구 결과가 아닙니다.',10,color=GRAY)
text(638,110,'수집 전 확인',14,'B')
p(638,90,280,'자동 수집 코드는 포함하지 않았습니다.<br/>이용 조건·접근 범위 확인 전에는 수집을 막는<br/>설정을 기본값으로 두었습니다.',11)
box(42,30,564,52);p(58,76,532,'<b>남은 작업</b>  수집 가능 여부 확인 · 종목·기간 확정 · 예비 수집 · 2인 독립 라벨링.<br/><b>미구현</b>  세부 지표 분해 · MoA 비교 · H4 역행 분석. 현재 범위는 단일 감성 지수의 H1·H2·H3.<br/><b>구현 상세</b>  조현호/toss_sentiment/ (README.md, docs/개발기록.md)',9,color=GRAY)
end();c.save();r=PdfReader(OUT);assert len(r.pages)==6;assert all(float(pg.mediabox.width)==960 and float(pg.mediabox.height)==540 for pg in r.pages);print(f'Verified {len(r.pages)} landscape pages, 16:9 → {OUT}')
