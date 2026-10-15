"""Build the proposal with measured text layout and fail on layout errors."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


BASE = Path(__file__).resolve().parent
OUT = BASE / "output" / "6조_토스증권_감성분석_중간보고서.pdf"
WIDTH, HEIGHT = 960, 540
BLUE = "#1B64DA"
INK = "#191F28"
GRAY = "#4E5968"
PALE = "#F2F6FC"
LINE = "#D8DFE8"
RED = "#B52A38"
MINT = "#E8F3FF"
WHITE = "#FFFFFF"
ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX")


def contrast_ratio(foreground, background):
    def luminance(value):
        channels = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
                  for v in channels]
        return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    values = sorted((luminance(foreground), luminance(background)))
    return (values[1] + 0.05) / (values[0] + 0.05)


@dataclass(frozen=True)
class TextRegion:
    left: float
    bottom: float
    right: float
    top: float
    label: str


class Deck:
    def __init__(self):
        for name, weight in (("R", "Regular"), ("B", "Bold"), ("X", "ExtraBold")):
            path = Path.home() / "Library" / "Fonts" / f"NanumGothic-{weight}.ttf"
            pdfmetrics.registerFont(TTFont(name, str(path)))
        pdfmetrics.registerFontFamily("R", normal="R", bold="B", italic="R", boldItalic="B")
        self.buffer = BytesIO()
        self.canvas = canvas.Canvas(self.buffer, pagesize=(WIDTH, HEIGHT))
        self.canvas.setTitle("토스증권 커뮤니티 공포탐욕지수 | 서비스 제안 기획서")
        self.page = 0
        self.regions = []
        self.backgrounds = []
        self.page_regions = []

    def measure(self, value, width, size=12, font="R", color=INK):
        style = ParagraphStyle(
            "body", fontName=font, fontSize=size, leading=size * 1.35,
            textColor=HexColor(color), wordWrap="LTR", splitLongWords=True,
        )
        paragraph = Paragraph(value, style)
        # Bold spans may select another font; require coverage in every weight.
        for name in ("R", "B", "X"):
            supported = pdfmetrics.getFont(name).face.charToGlyph
            missing = sorted({ch for ch in paragraph.getPlainText()
                              if not ch.isspace() and ord(ch) not in supported})
            if missing:
                raise ValueError(f"Unsupported glyphs in {name}: {missing!r}")
        _, height = paragraph.wrap(width, HEIGHT)
        return paragraph, height

    def paragraph(self, x, top, width, value, size=12, font="R", color=INK, bottom=48):
        if size < 11.5 and bottom == 48:
            raise ValueError(f"Page {self.page}: body text is too small: {size}")
        paragraph, height = self.measure(value, width, size, font, color)
        region = TextRegion(x, top - height, x + width, top, paragraph.getPlainText())
        if x < 42 or x + width > 918 or region.bottom < bottom or top > 520:
            raise ValueError(f"Page {self.page}: text exceeds its area: {region}")
        background = WHITE
        for area in reversed(self.backgrounds):
            dx = min(region.right, area.right) - max(region.left, area.left)
            dy = min(region.top, area.top) - max(region.bottom, area.bottom)
            if dx > 0.5 and dy > 0.5:
                if (region.left < area.left or region.right > area.right
                        or region.bottom < area.bottom or region.top > area.top):
                    raise ValueError(f"Page {self.page}: text spills out of its box: {region.label!r}")
                background = area.label
                break
        if contrast_ratio(color, background) < (3 if size >= 18 else 4.5):
            raise ValueError(f"Page {self.page}: insufficient text contrast: {region.label!r}")
        for other in self.regions:
            dx = min(region.right, other.right) - max(region.left, other.left)
            dy = min(region.top, other.top) - max(region.bottom, other.bottom)
            if dx > 0.5 and dy > 0.5:
                raise ValueError(
                    f"Page {self.page}: overlapping text: "
                    f"{region.label!r} / {other.label!r}"
                )
        self.regions.append(region)
        paragraph.drawOn(self.canvas, x, top - height)
        return top - height

    def box(self, x, top, width, height, color=PALE):
        if x < 42 or x + width > 918 or top - height < 48 or top > 364:
            raise ValueError(f"Page {self.page}: box exceeds content area")
        for region in self.regions:
            dx = min(x + width, region.right) - max(x, region.left)
            dy = min(top, region.top) - max(top - height, region.bottom)
            if dx > 0.5 and dy > 0.5:
                raise ValueError(f"Page {self.page}: box obscures text: {region.label!r}")
        self.backgrounds.append(TextRegion(x, top - height, x + width, top, color))
        self.canvas.setFillColor(HexColor(color))
        self.canvas.roundRect(x, top - height, width, height, 10, fill=1, stroke=0)

    def rule(self, x, y, width):
        self.canvas.setStrokeColor(HexColor(LINE))
        self.canvas.setLineWidth(0.8)
        self.canvas.line(x, y, x + width, y)

    def table(self, x, top, widths, headers, rows, size=11.5, padding=8):
        for index, row in enumerate([headers, *rows]):
            if len(row) != len(widths):
                raise ValueError("Table column count does not match its widths")
            font = "B" if index == 0 else "R"
            heights = [self.measure(value, width - padding * 2, size, font)[1]
                       for width, value in zip(widths, row)]
            height = max(heights) + padding * 2
            if top - height < 48:
                raise ValueError(f"Page {self.page}: table exceeds content area")
            if index == 0:
                self.box(x, top, sum(widths), height, BLUE)
            else:
                self.rule(x, top, sum(widths))
            left = x
            for width, value in zip(widths, row):
                self.paragraph(left + padding, top - padding, width - padding * 2,
                               value, size, font, WHITE if index == 0 else INK)
                left += width
            top -= height
        return top

    def start(self, label, title, subtitle):
        self.page += 1
        self.regions = []
        self.backgrounds = []
        p = self.paragraph
        p(42, 518, 220, "market voice", 12, "X", BLUE)
        p(654, 518, 264, "소셜미디어 분석 6조 · 중간고사 제출", 11.5, color=GRAY)
        p(42, 482, 876, f"{ROMAN[self.page - 1]}  {label}", 12, "B", BLUE)
        p(42, 455, 876, title, 28, "X")
        p(42, 409, 876, subtitle, 12, color=GRAY, bottom=376)
        self.rule(42, 378, 876)
        p(42, 28, 820, "토스증권 커뮤니티 공포탐욕지수 · 서비스 제안 기획서 · 2026.10.15",
          10, color=GRAY, bottom=12)
        p(870, 28, 48, f"{self.page} / 9", 10, "B", GRAY, bottom=12)

    def end(self):
        self.page_regions.append(tuple(self.regions))
        self.canvas.showPage()

    def save(self, output):
        self.canvas.save()
        data = self.buffer.getvalue()
        reader = PdfReader(BytesIO(data))
        if len(reader.pages) != 9:
            raise ValueError(f"Expected 9 pages, got {len(reader.pages)}")
        if not all(float(page.mediabox.width) == WIDTH
                   and float(page.mediabox.height) == HEIGHT for page in reader.pages):
            raise ValueError("Unexpected page dimensions")
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)


def build_deck(output=OUT):
    deck = Deck()
    p, box, table = deck.paragraph, deck.box, deck.table

    deck.start(
        "제안 개요", "커뮤니티의 말은 시장보다 먼저 움직이는가",
        "종목별 투자 심리를 지수화하고, 다음 거래일 거래량과의 관계를 사전에 고정한 기준으로 검증합니다.",
    )
    box(42, 364, 360, 222, BLUE)
    p(60, 348, 324, "우리가 만드는 것", 12, "B", MINT)
    p(60, 316, 324, "종목마다<br/>공포와 탐욕을<br/>0~100 숫자로<br/>매일 보여줍니다.", 22, "X", WHITE)
    p(60, 181, 324, "감성은 기분이 아니라<br/>주가에 대한 방향 의견입니다.", 12, color=WHITE)
    p(430, 364, 488, "문제", 14, "B", BLUE)
    p(430, 340, 488, '개인 투자자는 종목별 "지금 분위기"를 숫자로 보기 어렵습니다. '
      "직접 글을 읽는 방식은 주관적이고 비교 기준도 다릅니다.")
    p(430, 290, 488, "해법", 14, "B", BLUE)
    p(430, 266, 488, "글을 방향 의견으로 분류해 매일 지수를 만듭니다.<br/>방향과 과열을 분리해 국면으로 보여줍니다.")
    p(430, 216, 488, "<b>검증 기준</b>  계수 b &gt; 0, p &lt; 0.05")
    p(430, 190, 488, "<b>차별점</b>  종목 단위 · 2축 분리 · 사전 고정 검증")
    p(430, 164, 488, "<b>결과물</b>  대시보드 · 정기 리포트 · 사례집")
    deck.rule(42, 125, 876)
    p(42, 112, 876, "<b>완료</b>  주제 확정 · 지수 설계 · 기존 분석 파이프라인 구현과 동작 점검", 12, color=BLUE)
    p(42, 84, 876, "<b>미완</b>  수집 가능 여부 · 종목/기간 확정 · 실제 수집과 라벨링 · 개정 분석 구현 · 실증 결과",
      12, color=GRAY)
    deck.end()

    deck.start(
        "문제 정의", '"지금 이 종목 분위기"를 비교하기 어렵다',
        "기존 대안이 제공하는 정보와 한계를 구분하고, 국내 종목별 커뮤니티 심리를 같은 기준으로 정리합니다.",
    )
    table(42, 364, [184, 348, 344], ["기존 대안", "한계", "본 서비스의 제안"], [
        ["CNN Fear &amp; Greed Index", "미국 시장 전체의 지수로, 국내 개별 종목을 직접 설명하지 않음",
         "국내 종목 단위로 매일 산출"],
        ["증권사 리포트 · 뉴스", "발행 주기와 커버 종목이 다르고, 커뮤니티 반응과는 관점이 다름",
         "당일 커뮤니티 발화를 집계"],
        ["커뮤니티 직접 열람", "읽는 사람과 시점에 따라 판단이 달라 동일한 기준의 비교가 어려움",
         "0~100 백분위로 시점별 위치 제시"],
    ], size=12)
    p(42, 171, 876, "왜 지금 시도하는가", 14, "B")
    for i, (title, body) in enumerate([
        ("종목별 발화", "종목 게시판의 글과 매수·매도 인증을 활용할 여지가 있습니다."),
        ("분류 방식의 선택", "사람 라벨·학습 모델·LLM을 비용과 품질에 따라 비교할 수 있습니다."),
        ("결합 가능한 시장 자료", "KRX 일봉·투자자 동향을 종목코드와 거래일로 결합합니다."),
    ]):
        x = 42 + i * 299
        box(x, 144, 278, 96)
        p(x + 14, 132, 250, title, 12, "B", BLUE)
        p(x + 14, 108, 250, body, 11.5, color=GRAY)
    deck.end()

    deck.start(
        "지수 설계", "방향과 과열, 두 축으로 나눕니다",
        "방향 없는 관심도까지 한 점수로 합치지 않습니다. 다섯 하위 지표를 두 축에 나눠 패닉과 과열 매수를 구분합니다.",
    )
    box(42, 364, 430, 88)
    p(56, 354, 402, "S = (긍정 - 부정) / (전체 글 수 + 10)", 15, "B", BLUE)
    p(56, 327, 402, "글이 적은 날은 +10으로 평활합니다. 직전 20거래일 안에서 "
      "0~100 백분위로 변환하고, 섹터·시장은 글 수로 가중 평균합니다.", 11.5, color=GRAY)
    p(42, 262, 430, "두 축과 다섯 하위 지표", 13, "B")
    table(42, 238, [58, 102, 270], ["축", "지표", "정의"], [
        ["방향", "스탠스", "위 감성 지수 S"],
        ["방향", "키워드 강도", "탐욕 글 비율 - 공포 글 비율"],
        ["방향", "인증 비율", "매수 인증 / (매수 + 매도 인증)"],
        ["과열", "관심도", "글 수의 전일 대비 변화율"],
        ["과열", "쏠림", "1 - 의견 분포의 엔트로피"],
    ], padding=7)
    p(496, 364, 422, "국면 판정", 14, "B")
    p(496, 337, 422, "열: 방향 지수  /  행: 과열 강도", 11.5, color=GRAY)
    for i, label in enumerate(["45 이하", "46~55", "56 이상"]):
        p(558 + i * 122, 308, 112, label, 12, "B", GRAY)
    for top, row_label, labels, colors in [
        (282, "80 이상", ["패닉", "과열", "과열 매수"], [RED, GRAY, BLUE]),
        (219, "80 미만", ["비관", "중립", "낙관"], ["#FDECEE", PALE, MINT]),
    ]:
        p(496, top - 16, 60, row_label, 11.5, "B")
        for i, (label, color) in enumerate(zip(labels, colors)):
            x = 558 + i * 122
            box(x, top, 112, 54, color)
            p(x + 12, top - 17, 88, label, 12, "B", WHITE if top == 282 else INK)
    p(496, 149, 422, "관심도와 쏠림은 방향이 없습니다. 폭락일에도 글이 몰리면 "
      "값이 커지므로 방향 지수와 따로 읽습니다.", 12, color=GRAY)
    p(496, 94, 422, "인증 뱃지를 수집할 수 없으면 방향 지수는 스탠스와 키워드 강도 두 지표로 구성합니다.",
      11.5, color=GRAY)
    deck.end()

    deck.start(
        "검증 설계", "판정 기준을 먼저 고정합니다",
        "H1만 채택 여부를 판정합니다. 지수 검증과 추가 분석은 판정 없이 수치로 보고하며, 인과관계로 해석하지 않습니다.",
    )
    box(42, 364, 536, 158, BLUE)
    p(58, 351, 504, "H1 · 가설 검정", 12, "B", WHITE)
    p(58, 326, 504, "오늘 감성 지수는 다음 거래일 거래량을 설명한다.", 16, "B", WHITE)
    p(58, 292, 504, "출발 가정: 관계가 없다.<br/>통제: 오늘 수익률·거래량 비율·시장 수익률<br/>방법: 종목 고정효과 패널 회귀 · 종목별 군집 표준오차",
      11.5, color=WHITE)
    p(58, 232, 504, "채택 조건: 감성 지수 계수 b &gt; 0, p &lt; 0.05", 12, "B", WHITE)
    p(42, 190, 536, "왜 거래량을 판정 대상으로 두는가", 13, "B")
    p(42, 164, 536, "커뮤니티 활동이 수익률 방향보다 거래량을 더 잘 설명한다는 선행 연구를 "
      "따릅니다(Antweiler &amp; Frank, 2004). 수익률 버전은 참고로만 보고합니다.", 12, color=GRAY)
    p(42, 106, 536, "오늘 수익률을 통제해 가격 급변의 영향을 구분합니다. "
      "약 60거래일은 짧으므로, 유의하지 않음을 관계 없음으로 단정하지 않습니다.", 11.5, color=GRAY)
    p(604, 364, 314, "지수 검증 · 수치만 보고", 13, "B", BLUE)
    p(604, 336, 314, "<b>상식 점검</b>  급등일·급락일 평균 감성<br/>"
      "<b>말과 행동</b>  개인 순매수 비율과 상관", 11.5)
    p(604, 283, 314, "추가 분석 · 수치만 보고", 13, "B", BLUE)
    for top, body in [
        (254, "<b>후행</b>  수익률 → 다음 날 감성"),
        (222, "<b>과열 후 반전</b>  이후 5일 초과수익률"),
        (190, "<b>맞은편 투자자</b>  개인·외국인 순매수"),
        (158, "<b>모델 비교</b>  KRX 단독 / KRX + 감성"),
        (126, "<b>밤사이 심리</b>  장전 / 장중 감성"),
    ]:
        p(604, top, 314, body, 11.5)
    p(604, 88, 314, "반복 탐색은 다중검정 보정 또는 탐색 결과임을 명시합니다.", 11.5, color=GRAY)
    deck.end()

    deck.start(
        "AI 활용 전략", "어디까지 AI에 맡길지 근거로 정합니다",
        "LLM의 대체 가능성은 전제가 아니라 확인할 대상입니다. 라벨 품질·검수량·비용을 비교해 분류 방식을 선택합니다.",
    )
    for i, (title, blocks) in enumerate([
        ("1  사람 라벨 + 학습", [
            ("흐름", "사람 라벨 → 모델 학습 → 전체 분류"),
            ("장점", "사람 기준으로 품질을 확인하고 학습한 분류 모델을 남김"),
            ("부담", "라벨 작업량이 큼. 시간·인원이 충분한 경우에 적합"),
        ]),
        ("2  LLM 라벨 + 검수 + 학습", [
            ("흐름", "LLM 라벨 → 사람 검수 → 모델 학습 → 전체 분류"),
            ("장점", "검수 후 학습 모델로 대량 처리. 사람의 초기 라벨 작업을 줄임"),
            ("부담", "LLM 오류가 학습될 수 있어 검수 표본과 기준이 필요"),
        ]),
        ("3  LLM 직접 분류", [
            ("흐름", "LLM이 전체 분류 → 라벨을 직접 사용"),
            ("장점", "별도 모델 학습 없이 빠르게 실행할 수 있음"),
            ("부담", "글마다 비용 발생. 별도 학습 모델이 남지 않아 기준 일관성 점검 필요"),
        ]),
    ]):
        x = 42 + i * 299
        box(x, 364, 278, 223)
        p(x + 14, 350, 250, title, 12, "B", BLUE)
        top = 314
        for label, body in blocks:
            top = p(x + 14, top, 250, f"<b>{label}</b>  {body}", 11.5, color=GRAY) - 15
    box(42, 124, 876, 76, MINT)
    p(58, 112, 844, "이미 구현한 범위 · 실증 결과 아님", 12, "B", BLUE)
    p(58, 87, 844, "수집 입력 → 정제 → 분류 → 시장 자료 → 거래일 집계 → 패널 병합 → 통계 → 요약의 "
      "8단계와 컨트롤러를 구현했습니다. 합성 표본의 선행 관계 탐지로 동작을 점검했으며, 개정안의 거래량 패널 검정은 아직 미구현입니다.",
      11.5, color=GRAY)
    deck.end()

    deck.start(
        "제품", "세 개의 화면으로 전달합니다",
        "개정안 데모를 읽기 쉬운 화면 구성도로 다시 그렸습니다. 실증 수치는 없으며, 원본 데모의 감성·매매동향도 합성 자료입니다.",
    )
    for i, (title, user) in enumerate([
        ("시장 요약", "금융 미디어 · 뉴스레터"),
        ("종목 상세", "개인 투자자"),
        ("선행·후행과 반전", "투자 교육 운영자"),
    ]):
        x = 42 + i * 299
        box(x, 364, 278, 224)
        p(x + 14, 350, 250, title, 14, "B", BLUE)
        p(x + 14, 322, 250, user, 11.5, color=GRAY)
    p(56, 285, 250, "방향 지수    -- / 100", 15, "B")
    p(56, 254, 250, "과열 강도    -- / 100", 15, "B")
    p(56, 216, 250, "종목별 국면 지도", 12, "B")
    p(56, 190, 250, "비관 · 중립 · 낙관<br/>패닉 · 과열 · 과열 매수", 12, color=GRAY)
    p(355, 285, 250, "종가와 감성의 일별 추이", 12, "B")
    box(355, 257, 250, 49, WHITE)
    p(367, 244, 226, "실제 수집 후 시계열 표시", 12, color=GRAY)
    p(355, 191, 250, "긍정 · 중립 · 부정 글 수<br/>장중 감성과 장전 감성 비교", 12, color=GRAY)
    p(654, 285, 250, "H1 계수·유의확률", 12, "B")
    p(654, 258, 250, "b = --    p = --", 15, "B")
    p(654, 216, 250, "국면별 이후 5일 수익률<br/>감성 선행·가격 후행 비교", 12, color=GRAY)
    p(654, 168, 250, "결과 미확보 · 판정하지 않음", 11.5, color=RED)
    box(42, 122, 876, 74, MINT)
    p(58, 110, 844, "화면별 사용 목적", 12, "B", BLUE)
    for i, body in enumerate([
        "시장 요약: 사건이 있던 날의<br/>커뮤니티 반응을 기사 근거로 정리",
        "종목 상세: 관심 종목의 심리와<br/>가격을 같은 시간축에서 확인",
        "분석 화면: 심리·시장 관계와<br/>검증의 한계를 교육 자료로 활용",
    ]):
        p(58 + i * 290, 85, 264, body, 11.5, color=GRAY)
    deck.end()

    deck.start(
        "차별화", "같은 심리 지수라도, 네 가지가 다릅니다",
        "예측력이 더 좋다고 주장하지 않습니다. 비교 대상의 공개 범위에서 차이를 정리하고, 검증 절차를 먼저 공개합니다.",
    )
    for i, (title, body) in enumerate([
        ("종목 단위", "시장 전체가 아니라<br/>종목별로 매일 산출"),
        ("두 축 분리", "방향과 과열을 나눠<br/>패닉·과열 매수 구분"),
        ("사전 고정 검증", "데이터 확인 전<br/>가설과 채택 조건 확정"),
        ("한국 커뮤니티", "주식 은어·반어와<br/>매수·매도 인증 반영"),
    ]):
        x = 42 + i * 223
        box(x, 364, 207, 104, MINT if i % 2 == 0 else PALE)
        p(x + 14, 350, 179, title, 13, "B", BLUE)
        p(x + 14, 319, 179, body, 11.5, color=GRAY)
    table(42, 241, [174, 150, 110, 198, 244],
          ["구분", "대상", "주기", "방향 / 과열", "검증 기준"], [
              ["CNN Fear &amp; Greed", "미국 시장 전체", "일", "7개 지표 합산", "지표 공개<br/>본 연구식 사전 가설과 다름"],
              ["증권사 심리 지표", "커버 범위별 상이", "리포트별", "서비스별 상이", "공개 범위가 달라<br/>일괄 단정하지 않음"],
              ["<b>본 서비스</b>", "국내 100~200종목<br/>(목표)", "일 + 장전", "방향 / 과열 2축", "가설과 채택 조건<br/>사전 공개"],
          ], padding=8)
    deck.end()

    deck.start(
        "수익 모델", "무엇을 팔고, 언제 손익이 맞는지",
        "숫자는 모두 가정이며 실측 전입니다. 아래 손익분기는 분류 변동비만 고려하며, 서버·인건비 등은 포함하지 않습니다.",
    )
    p(42, 364, 520, "판매 상품과 구매자 가설", 14, "B")
    table(42, 336, [187, 203, 130], ["상품", "구매자 가설", "과금"], [
        ["종목·사건별 리포트", "금융 미디어·뉴스레터", "건별 제작"],
        ["대시보드 구독", "개인 투자자·투자 교육", "월 구독"],
        ["사례집·전자책", "투자 심리 분석 독자", "책 판매"],
    ])
    p(42, 191, 520, "변동비 손익 계산 · 전부 가정", 13, "B", RED)
    box(42, 166, 520, 82)
    p(56, 155, 492, "<b>가정 A</b>  월 구독료 9,900원<br/>"
      "<b>가정 B</b>  월 분류 대상 40만 건<br/>"
      "<b>가정 C</b>  건당 0.3원 → 월 분류 변동비 12만원", 12)
    p(42, 72, 520, "12만원 ÷ 9,900원 → 변동비 손익분기 13명", 13, "B", BLUE)
    p(594, 364, 324, "가정을 어떻게 검증하는가", 14, "B")
    for top, label, body in [
        (332, "비용과 물량", "예비 수집량과 표본 1만 건 실행 비용으로 월 물량·건당 단가를 점검합니다."),
        (265, "구매 의향", "샘플 리포트를 보여주고 가격별 구매 의향을 인터뷰합니다."),
        (198, "대체 가능성", "단순 지표 시안과 비교해 추가 지불 의향을 확인합니다."),
    ]:
        p(594, top, 324, label, 12, "B", BLUE)
        p(594, top - 23, 324, body, 11.5, color=GRAY)
    box(594, 124, 324, 76, BLUE)
    p(608, 112, 296, "판단 분기", 12, "B", WHITE)
    p(608, 87, 296, "수요 확인 → 정기 발행 시험<br/>수요 부족 → 교육용 사례집으로 축소", 11.5, color=WHITE)
    deck.end()

    deck.start(
        "실행과 리스크", "확인한 것과 남은 결정을 나눕니다",
        "커뮤니티·KRX 수집은 병렬로 시작하고, 감성 분류 → 연계 분석 → 화면 구축으로 이어갑니다. 담당자 배정은 협의가 필요합니다.",
    )
    p(42, 364, 520, "역할과 순서", 14, "B")
    table(42, 336, [196, 324], ["역할", "산출물 / 범위"], [
        ["1  커뮤니티 수집·설계", "게시글·댓글·인증 뱃지"],
        ["2  감성 분석", "기준표·분류 방식·검수"],
        ["3  KRX·연계 분석", "일봉·투자자 동향·공매도·가설 검정"],
        ["4  UI 설계·구축", "시장 요약·종목 상세·분석 화면"],
        ["5  발표", "전체 과정 병행 · 보고서·발표자료"],
    ], padding=6)
    p(42, 153, 520, "4주 계획", 13, "B")
    p(42, 126, 520, "<b>1주</b>  수집 조건·종목/기간·예비 수집·라벨 기준<br/>"
      "<b>2주</b>  본 수집·정제·2인 라벨링·분류 평가<br/>"
      "<b>3주</b>  거래일 정렬·백분위 변환·패널 회귀<br/>"
      "<b>4주</b>  추가 분석·한계 정리·최종 보고와 발표", 12)
    p(594, 364, 324, "남은 결정과 리스크", 14, "B")
    for top, body in [
        (332, "<b>과거 글 범위</b>  확보 불가 시 매일 수집. 종목 수를 늘려도 시장 관측일은 늘지 않음."),
        (279, "<b>인증 뱃지</b>  수집 불가 시 방향 지수는 스탠스·키워드 두 지표로 구성."),
        (226, "<b>수집 조건</b>  허용 범위·요청 간격 확인, 개인정보 제거, 원문 재배포 금지."),
        (173, "<b>표본 기간</b>  약 60거래일은 짧음. 유의하지 않음을 무관계로 단정하지 않음."),
    ]:
        p(594, top, 324, body, 11.5, color=GRAY)
    box(594, 112, 324, 64, BLUE)
    p(608, 100, 296, "현재: 설계·기존 코드 동작 점검 완료<br/>남음: 실데이터·개정 분석 구현·실증", 11.5, "B", WHITE)
    deck.end()
    deck.save(output)
    return deck


if __name__ == "__main__":
    result = build_deck()
    print(f"Verified {result.page} landscape pages, text bounds/overlaps/glyphs -> {OUT}")
