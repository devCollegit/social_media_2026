"""발표자료 만들기: HTML(파일 하나, 외부 공유용) 발표자료를 만든다. PDF는 export_pdf.py.
입력: ../pres_results.json, ../krx_results.json   출력: 토스증권_공포탐욕지수_발표.html
사용: cd presentation && uv run --quiet --python 3.10 --with matplotlib python build_presentation.py"""
import base64, html, io, json, os, re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, "../pres_results.json")))
K = json.load(open(os.path.join(HERE, "../krx_results.json")))
OUT = "토스증권_공포탐욕지수_발표"

# ---------------- 색 ----------------
INK, MUTED, LINE, BG, PANEL = "1B2230", "5B6474", "D9DEE7", "FFFFFF", "F2F4F8"
DARK = "131A2A"
GREED, FEAR, NEU = "D6453D", "2F6FDE", "8A94A6"          # 국내 관례: 상승·탐욕 빨강, 하락·공포 파랑
PRIV, INST, FRGN = "E8892B", "138A72", "7451C9"         # 개인·기관·외국인
NIGHT, DAY = "3B3F8F", "E3A72F"

# ---------------- 숫자 ----------------
f1 = lambda v: f"{v:+.1f}"
pct = lambda v: f"{v*100:.0f}%"
lb = R["posts_vs_priv_bins"]; bd = R["posts_vs_priv_by_dir"]; q5 = R["sent_quint_flows"]
nq, dq = R["night_quint"], R["day_quint"]; lag = R["lag_bins_daynight"]; cp = R["crash_profile"]; cs = R["crash_summary"]
N_POSTS = R["posts_total"]; DN = R["daynight_n"]
# 모델 v2(A4+A5) 성능: 5겹 교차검증(eval_features_cv.json), 전체 적용 결과: index_out/daily_stock.csv, 적용 시간: apply_out3_meta.json
import csv as _csv
MV = json.load(open(os.path.join(HERE, "../eval_features_cv.json"))); MV_OLD, MV_NEW = MV["(a) 지금"], MV["(d) A4+A5"]
_ds = list(_csv.DictReader(open(os.path.join(HERE, "../index_out/daily_stock.csv"))))
_tp, _tg, _tf = (sum(float(r[k]) for r in _ds) for k in ("n_posts", "n_greed", "n_fear"))
APPLY_DEC, APPLY_GREED = (_tg + _tf) / _tp, _tg / (_tg + _tf)
_meta = os.path.join(HERE, "../apply_out3_meta.json"); APPLY_MIN = json.load(open(_meta))["minutes"] if os.path.exists(_meta) else 15
ACC_NEW = MV_NEW["acc"]["mean"] * 100
dirv = {(r["dir"], r["bin"]): r["priv"] for r in bd}
SEC = R["sector_greed_vs_fear"]
SEC_TXT = json.load(open(os.path.join(HERE, "../sectors.json")))
man = lambda n: f"{n/1e4:,.0f}만"
SEC_SECS = 12_574_144 * 0.42 if False else N_POSTS * 0.42     # 1건 0.42초(Haiku, 1,000건 약 7분)
DAYS_SEQ = SEC_SECS / 86400
# API 비용 추정 가정: 글 1건 입력 약 105토큰(본문·부모 글 평균 37자 + 필드 + 기준 문서 분담), 출력 약 10토큰. Claude Haiku 5.5 단가 입력 $0.10, 출력 $0.50 / 100만 토큰
IN_TOK, OUT_TOK = N_POSTS * 105, N_POSTS * 10
COST = IN_TOK / 1e6 * 0.10 + OUT_TOK / 1e6 * 0.50

# ---------------- 차트 정의 ----------------
CH = {}
CH["hour"] = dict(type="bar", cats=[f"{r['hour']}" for r in R["by_hour"]], series=[("글 수(만 건)", [r["posts"] / 1e4 for r in R["by_hour"]], NEU)],
                  ylabel="글 수(만 건)", xlabel="작성 시각(시)", fmt="{:.0f}", labels=False, hl={str(h): NIGHT for h in list(range(0, 9)) + [20, 21, 22, 23]})
CH["perf"] = dict(type="bar", cats=["글자 조각만 (이전)", "+ 부모 글 · 단어 · 인증 · 보유 (최종)"], series=[("판정한 글 정확도", [MV_OLD["acc"]["mean"] * 100, ACC_NEW], INK), ("판정 비율", [MV_OLD["decided"]["mean"] * 100, MV_NEW["decided"]["mean"] * 100], NEU), ("월별 탐욕 비율 오차(%p)", [MV_OLD["ratio_err"]["mean"] * 100, MV_NEW["ratio_err"]["mean"] * 100], GREED)], ylabel="%", fmt="{:.1f}", labels=True, legend=dict(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3))
CH["posts_dir"] = dict(type="bar", cats=["평소(1.25배 미만)", "1.25~2배", "2배 이상"],
                       series=[("하락일", [dirv[("하락일", c)] for c in ["평소(1.25배 미만)", "1.25~2배", "2배 이상"]], FEAR),
                               ("상승일", [dirv[("상승일", c)] for c in ["평소(1.25배 미만)", "1.25~2배", "2배 이상"]], GREED)],
                       ylabel="개인 순매수 비율(%)", xlabel="그날 글 수(직전 20거래일 평균 대비)", fmt="{:+.1f}", labels=True)
CH["posts_next"] = dict(type="bar", cats=[r["bin"] for r in lb], series=[("다음 날 개인 순매수 비율", [r["priv_next"] for r in lb], PRIV)],
                        ylabel="다음 날 개인 순매수 비율(%)", xlabel="그날 글 수(직전 20거래일 평균 대비)", fmt="{:+.1f}", labels=True)
CH["quint_flow"] = dict(type="bar", cats=[r["q"] for r in q5], series=[("개인", [r["priv"] for r in q5], PRIV), ("기관+외국인", [r["instfrgn"] for r in q5], INST)],
                        ylabel="순매수 비율(%)", xlabel="그날 커뮤니티 심리(종목·일 5분위)", fmt="{:+.1f}", labels=False)
CH["sector"] = dict(type="bar", cats=["개인", "기관+외국인"],
                    series=[("커뮤니티 탐욕 상위 3섹터", [SEC["탐욕 상위 3섹터"][w] for w in ["priv", "instfrgn"]], GREED),
                            ("커뮤니티 공포 하위 3섹터", [SEC["공포 하위 3섹터"][w] for w in ["priv", "instfrgn"]], FEAR)],
                    ylabel="섹터 순매수 비율(%)", fmt="{:+.1f}", labels=True)
CH["crash"] = dict(type="line", cats=[("급락일" if r["k"] == 0 else f"{r['k']:+d}일") for r in cp],
                   series=[("개인", [r["priv"] for r in cp], PRIV), ("기관", [r["inst"] for r in cp], INST), ("외국인", [r["frgn"] for r in cp], FRGN)],
                   ylabel="45종목 순매수 비율(%)", xlabel="코스피 −3% 이하 급락일 기준(거래일)", fmt="{:+.1f}", labels=False)
QL = ["가장 공포", "2분위", "3분위", "4분위", "가장 탐욕"]
CH["dn_gap"] = dict(type="line", cats=QL, series=[("야간 심리(전일 20:00~당일 09:00)", [r["gap"] for r in nq], NIGHT), ("전일 주간 심리(09:00~20:00)", [r["gap"] for r in dq], DAY)],
                    ylabel="당일 시가 갭(%)", xlabel="심리 5분위", fmt="{:+.2f}", labels=True)
CH["gap_intra"] = dict(type="bar", cats=QL, series=[("시가 갭(전일 종가→시가)", [r["gap"] for r in nq], NIGHT), ("장중(시가→종가)", [r["intra"] for r in nq], NEU)],
                       ylabel="평균 수익률(%)", xlabel="야간 심리 5분위", fmt="{:+.2f}", labels=True)
CH["lag"] = dict(type="bar", cats=[r["bin"] for r in lag],
                 series=[("그날 주간 글", [(r["day_greed"] - r["day_fear"]) * 100 for r in lag], DAY), ("그날 밤 글", [(r["night_greed"] - r["night_fear"]) * 100 for r in lag], NIGHT)],
                 ylabel="탐욕 글 − 공포 글 (%p)", xlabel="그날 주가 등락", fmt="{:+.1f}", labels=True)

# ---------------- 슬라이드 내용 ----------------
reg = lambda d, k: d[k]
S = []
def add(**kw): S.append(kw)

add(kind="cover", title="토스증권 커뮤니티 공포탐욕지수", sub="커뮤니티 심리는 주가를 앞서는가, 따라가는가", meta="소셜미디어 분석 6조 · 2026")
add(kind="abc", section="", title="한 장 요약",
    lead="종목마다 매일 바뀌는 커뮤니티 공포탐욕지수를 만들고, 실제 주가 · 수급과 맞대 봤다",
    made=("① 만든 것", f"토스증권 커뮤니티 글로 만든 종목별 공포탐욕지수. 45종목 · 2년 · 글 {man(N_POSTS)} 건, 종목마다 매일 0~100"),
    how=("② 만든 방법", f"LLM이 글 2.9만 건의 감성을 판정하고, 그 판정으로 학습한 분류 모델이 나머지 글 전체를 판정(판정한 글 기준 정확도 {ACC_NEW:.0f}%)"),
    found=("③ 확인한 것", [
        ("주가가 먼저 움직이고, 글이 따라간다", "주가가 오른 날은 그날 글이 낙관적으로 바뀐다"),
        ("밤사이 글 분위기는 다음 날 시가에만 반영된다", f"밤 분위기가 1표준편차 좋으면 시가 {R['dfe_lead_gap']['Snz']['b']:+.2f}%p(그날 시장 전체 움직임을 뺀 값). 장이 열린 뒤엔 오히려 조금 되돌린다"),
        ("글은 낙관적인데 개인은 판다", f"글이 가장 낙관적인 날 개인은 순매도({q5[-1]['priv']:+.1f}%), 기관 · 외국인은 순매수({q5[-1]['instfrgn']:+.1f}%). 말과 행동이 반대")]))

# 1 개념
add(kind="section", num="01", title="공포탐욕지수란", sub="RSI와 CNN Fear & Greed Index, 그리고 이번 지수")
add(kind="cnn", section="01 개념", title="CNN Fear & Greed Index",
    lead="미국 주식시장 전체의 심리를 7개 시장 지표로 재서 0~100 숫자 하나로 보여준다",
    items=[("주가 모멘텀", "S&P 500이 125일 이동평균보다 얼마나 위에 있나"), ("주가 강도", "52주 신고가 종목 수 vs 신저가 종목 수"),
           ("주가 폭", "오르는 종목 거래량 vs 내리는 종목 거래량"), ("풋·콜 옵션", "하락에 거는 풋옵션이 콜옵션보다 많은가"),
           ("정크본드 수요", "위험한 회사채와 우량 회사채의 금리 차"), ("시장 변동성", "VIX(변동성 지수)가 평소보다 높은가"),
           ("안전자산 수요", "최근 20일 주식 수익률 vs 국채 수익률")],
    bands=[("극단적 공포", 0, 25, "1F4FAF"), ("공포", 25, 45, "6E9BEA"), ("중립", 45, 55, "B7BEC9"), ("탐욕", 55, 75, "EA8A80"), ("극단적 탐욕", 75, 100, "B5302A")],
    note="7개 지표를 각각 평소 범위 안에서 0~100으로 바꾼 뒤 평균한다.")
add(kind="rsi", section="01 개념", title="RSI (상대강도지수)",
    lead="가격만으로 과열을 잰다: 최근 14일 동안 오른 폭이 내린 폭보다 얼마나 컸나",
    steps=[("입력", "최근 14거래일 종가 변화"), ("계산 ①", "오른 날 상승폭 평균, 내린 날 하락폭 평균"), ("계산 ②", "RSI = 100 × 평균 상승폭 ÷ (평균 상승폭 + 평균 하락폭)"), ("출력", "0~100. 70 이상 과매수, 30 이하 과매도")],
    example=["예) 평균 상승폭 2,000원, 평균 하락폭 1,000원", "RSI = 100 × 2,000 ÷ (2,000 + 1,000)", "     = 100 × 0.667 = 66.7 → 과매수 기준(70) 바로 아래"])
add(kind="table", section="01 개념", title="세 지표 비교와 활용",
    lead="세 지표 모두 '극단'에 주목한다. 다른 점은 무엇으로 심리를 읽느냐다",
    head=["", "RSI", "CNN Fear & Greed", "이번 지수"],
    rows=[["재는 것", "가격 움직임", "시장 전체 심리", "투자자가 쓴 글의 방향"], ["단위", "종목", "미국 시장 하나", "종목 · 섹터 · 시장"],
          ["입력", "14일 종가", "7개 시장 지표", "커뮤니티 글 + 글 수"], ["읽는 법", "70↑ 과매수, 30↓ 과매도", "극단적 공포·탐욕", "백분위 0~100, 국면 5개"]],
    bullets=["역발상: 극단적 공포를 매수 기회, 극단적 탐욕을 경고로 읽는다 (일반적인 활용법. 이번 지수에선 근거가 확인되지 않았다)", "심리 온도계: 지금 시장 분위기가 평소보다 어느 쪽에 있는지 본다",
             "확인 지표: 가격 신호(RSI 등)와 심리 신호가 같은 방향인지 맞춰 본다"])
IW = json.load(open(os.path.join(HERE, "../index_out/index_weights.json")))
add(kind="formula", section="01 개념", title="이번 지수를 만드는 방법",
    lead="커뮤니티 글로 종목마다 매일 0~100 점수를 만든다",
    steps=[("① 판정", "글마다 탐욕 · 공포 · 중립"), ("② 하루 점수", "S = (탐욕 − 공포 + 10 × 평소 수준) ÷ (전체 글 + 10)"), ("③ 백분위", "그 종목 직전 60거래일 안에서 0~100"), ("④ 묶기", "섹터 · 시장은 글 수로 가중 평균")],
    example=["예) 글 100건, 탐욕 30, 공포 10, 평소 수준 +0.05", "S = (30 − 10 + 10 × 0.05) ÷ (100 + 10) = 20.5 ÷ 110 = 0.19",
             "글이 3건뿐이고 모두 탐욕이면 (3 + 0.5) ÷ 13 = 0.27", "→ 글이 적은 날은 그 종목의 평소 수준 쪽으로 당겨진다"],
    axes=[("방향", f"감성 S + 키워드 강도 (상관 {IW['direction']['corr']:.2f}, 같은 비중) → 공포 ↔ 탐욕"), ("강도", f"관심도(글 수 ÷ 20일 평균) + 쏠림 (상관 {IW['strength']['corr']:.2f}) → 조용 ↔ 과열"), ("국면", "과열 매수 · 낙관 · 중립 · 비관 · 패닉")])

# 2 데이터
add(kind="section", num="02", title="데이터", sub="토스증권 커뮤니티 크롤링 + KRX 시장 데이터")
add(kind="data", section="02 데이터", title="두 가지 데이터를 종목 · 거래일로 맞춘다",
    lead="커뮤니티 글은 '무엇을 말했나', KRX는 '실제로 어떻게 움직였고 누가 샀나'",
    cards=[("토스증권 커뮤니티 (크롤링)", ["종목 게시판의 글 · 댓글 · 대댓글과 작성 시각", "게시판을 최신순으로 넘기며 수집, 요청 사이 간격을 둠", "작성자 · 프로필 정보는 저장하지 않음"]),
           ("KRX (한국거래소)", ["종목 일봉: 시가 · 종가 · 거래량", "코스피 · 코스닥 지수", "투자자별 순매수 대금: 개인 · 기관 · 외국인"])],
    stats=[("45종목", "15섹터 × 3종목"), (f"{DN['days']}거래일", "2024-10-28 ~ 2026-11-11"), (f"{man(N_POSTS)} 건", "분석에 쓴 글")])
add(kind="sectors", section="02 데이터", title="15개 섹터, 45종목",
    lead="국내 커뮤니티에서 글이 많은 업종을 15개로 나누고, 업종마다 대표 종목 3개를 골랐다",
    sectors=[(s, list(v.values())) for s, v in SEC_TXT.items()])
add(kind="chart", chart="hour", section="02 데이터", title="글을 어느 거래일에 넣을까",
    lead=f"글의 {R['posts_day_share']*100:.0f}%는 장이 열린 09:00~20:00에 쓰인다. 나머지 밤 글은 다음 거래일 '야간'으로 묶는다",
    bullets=["대체거래소 거래가 20:00까지 열려 하루 경계를 20:00으로 잡았다", "20:00 이후 글과 휴장일 글 → 다음 거래일", "주간 = 당일 09:00~20:00, 야간 = 전일 20:00~당일 09:00", "남색 막대가 야간 시간대"])

# 3 감성
add(kind="section", num="03", title="감성 분석", sub="1,257만 건을 어떻게 판정했나")
add(kind="labels", section="03 감성 분석", title="감성 = 이 종목 주가를 두고 품은 기대와 두려움",
    lead="글쓴이의 기분이 아니라 이 종목 주가에 대한 기대(탐욕)와 두려움(공포)을 본다. 물려서 하는 한탄 · 분노는 공포, 못 산 아쉬움은 탐욕으로 친다",
    ex=[("“오늘 기분 최악인데 이 종목은 간다”", "탐욕", GREED, "기분은 나쁘지만 전망은 상승"), ("“손절하고 나니 속이 시원하다”", "공포", FEAR, "기분은 좋지만 전망은 하락"),
        ("“내일 실적 발표 있네요”", "중립", NEU, "방향 없는 정보 전달"), ("“지금 사도 되나요?”", "중립", NEU, "질문 · 확신 없음")],
    note="예시 문장은 설명을 위해 만든 문장이다. 판정 기준은 반어 · 자조 · 혼합 의견 규칙까지 11개 규칙으로 정했다.")
add(kind="cost", section="03 감성 분석", title="전부 LLM으로 읽으면",
    lead="비용(약 $195)보다 시간과 재현성이 문제다. 새 글이 들어올 때마다 다시 판정해야 하고, 같은 판정을 다시 내기 어렵다",
    calc=[("데이터 양", f"{N_POSTS:,}건 (글 평균 37자)"), ("1건당 시간", "약 0.42초 (Claude Haiku, 1,000건에 약 7분)"),
          ("전체 시간", f"{N_POSTS:,} × 0.42초 = {SEC_SECS:,.0f}초 ≈ {DAYS_SEQ:.0f}일 (한 줄로 처리할 때)"),
          ("API 비용 추정", f"입력 {IN_TOK/1e8:.1f}억 토큰 → 약 ${IN_TOK/1e6*0.10:,.0f} + 출력 {OUT_TOK/1e8:.1f}억 토큰 → 약 ${OUT_TOK/1e6*0.50:,.0f} = 약 ${COST:,.0f}")],
    note="비용은 글 1건에 입력 약 105토큰 · 출력 약 10토큰, Claude Haiku 5.5 단가(100만 토큰당 입력 $0.10 · 출력 $0.50)로 잡은 추정치다. 새 글이 들어올 때마다 같은 비용이 다시 든다.",
    vs=[("전부 LLM", f"약 {DAYS_SEQ:.0f}일"), ("실제 방법", f"LLM 2.9만 건 + 모델 적용 {APPLY_MIN:.0f}분")])
add(kind="flow", section="03 감성 분석", title="실제 방법: LLM으로 가르치고, 모델로 전부 읽는다",
    lead="LLM은 표본만 판정하고, 그 판정으로 학습한 분류 모델이 전체를 읽는다",
    steps=[("① 표본", "2년 글에서 종목 · 월마다 같은 수로 5.9만 건"), ("② LLM 판정", "Claude Haiku가 기준표대로 29,000건 판정 (최근 1년 2.3만 + 이전 1년 0.6만)"),
           ("③ 학습", "본문 글자 조각 · 단어, 부모 글, 매수 · 매도 인증, 보유 여부 → 로지스틱 회귀"), ("④ 기준점", f"확률 0.7 이상일 때만 탐욕 · 공포로 판정 (전체 글의 약 {APPLY_DEC*100:.0f}%)"), ("⑤ 전체 적용", f"{man(N_POSTS)} 건을 {APPLY_MIN:.0f}분에 분류")],
    bullets=["글자 조각을 쓴 이유: 띄어쓰기가 엉망이고 은어가 많은 글도 조각 단위로는 잡힌다", "부모 글을 함께 읽어 '저도요' 같은 대댓글도 판정하고, 단어 특징으로 '안 오르다' 같은 부정 표현을 구분한다", "판정하지 못한 글은 중립으로 센다. 그래야 전체 글 수가 분모로 남는다", "키워드 71개는 분류에 쓰지 않고, 지수의 '키워드 강도' 지표에만 쓴다"])
add(kind="chart", chart="perf", section="03 감성 분석", title="분류 모델 성능",
    lead="부모 글 · 단어 · 인증 · 보유를 더하니 더 많은 글을 판정하고, 월별 탐욕 비율 오차가 줄었다",
    bullets=["정확도 = 판정한 글 가운데 LLM 판정과 같은 비율. 29개 묶음을 5무리로 나눠 학습에 안 쓴 무리로 채점(5겹 평균)",
             f"최종 모델: {MV_NEW['decided']['mean']*100:.0f}%를 판정했고 그 안에서 정확도 {ACC_NEW:.0f}%. 월별 탐욕 비율 오차 {MV_OLD['ratio_err']['mean']*100:.1f} → {MV_NEW['ratio_err']['mean']*100:.1f}%p, 5겹 모두 줄어듦",
             "키워드 규칙만으로는 데이터를 늘려도 정확도 68%에서 멈춤",
             f"전체 적용 결과: 판정 {APPLY_DEC*100:.0f}%, 그중 탐욕 {APPLY_GREED*100:.0f}%"])

# 4 분석
add(kind="section", num="04", title="분석", sub="KRX 수급 · 주가와 커뮤니티 심리")
add(kind="chart", chart="posts_dir", section="4-1 글 수 ↔ 개인 수급", key="posts_dir", title="글이 몰린 날, 내리면 개인은 더 사고 오르면 더 판다",
    lead="글이 몰린 날 주가가 내렸으면 개인은 더 샀고, 올랐으면 더 팔았다",
    bullets=[f"하락일 + 글 2배 이상: 개인 순매수 {dirv[('하락일','2배 이상')]:+.1f}% (평소 하락일 {dirv[('하락일','평소(1.25배 미만)')]:+.1f}%)",
             f"상승일 + 글 2배 이상: {dirv[('상승일','2배 이상')]:+.1f}% (평소 상승일 {dirv[('상승일','평소(1.25배 미만)')]:+.1f}%)",
             f"그날 수익률을 통제해도 글이 2배면 개인 순매수 +{R['posts_priv_reg_same']['lpr']['b']*0.693:.1f}%p (t={R['posts_priv_reg_same']['lpr']['t']:.1f})",
             "순매수 비율 = 개인 순매수 대금 ÷ 거래대금(종가 × 거래량)"])
add(kind="chart", chart="posts_next", section="4-1 글 수 ↔ 개인 수급", key="posts_next", title="글이 몰린 다음 날, 개인 매수가 따라 들어온다",
    lead=f"글이 3배 이상 몰린 다음 날 개인 순매수는 {lb[-1]['priv_next']:+.1f}%로 평소({lb[2]['priv_next']:+.1f}%)의 두 배를 넘는다",
    bullets=[f"글 수가 평소의 3배 이상인 날: {lb[-1]['n']:,}개 종목·일, 그날 평균 수익률 {lb[-1]['ret']:+.1f}%",
             f"그날 수익률·순매수를 통제해도 글 2배 → 다음 날 개인 순매수 +{R['posts_priv_reg_next']['lpr']['b']*0.693:.1f}%p (t={R['posts_priv_reg_next']['lpr']['t']:.1f})",
             "관심이 쏠린 종목에 개인 매수가 하루 늦게 따라 들어온다"])
add(kind="chart", chart="quint_flow", section="4-2 투자자별 수급 ↔ 심리", key="quint", title="커뮤니티가 탐욕일수록 개인은 팔고 기관 · 외국인은 산다",
    lead="그날 주가 등락을 빼고 봐도 기관은 사고 개인은 판다",
    bullets=[f"가장 탐욕: 개인 {q5[-1]['priv']:+.1f}% · 기관+외국인 {q5[-1]['instfrgn']:+.1f}% (기관 {q5[-1]['inst']:+.1f}%, 외국인 {q5[-1]['frgn']:+.1f}%)",
             f"그날 수익률을 통제해도 심리 1σ당 개인 {R['flow_reg_priv']['Sz']['b']:+.1f}%p (t={R['flow_reg_priv']['Sz']['t']:.1f}), 기관+외국인 {R['flow_reg_instfrgn']['Sz']['b']:+.1f}%p (t={R['flow_reg_instfrgn']['Sz']['t']:.1f})",
             (lambda a, b: f"다음 날 {'되돌림은 뚜렷하지 않다' if max(abs(a['t']), abs(b['t'])) < 1.96 else '조금 되돌린다'}: 개인 {a['b']:+.1f}%p (t={a['t']:.1f}), 기관+외국인 {b['b']:+.1f}%p (t={b['t']:.1f})")(R['flow_next_reg_priv']['Sz'], R['flow_next_reg_instfrgn']['Sz']),
             "개인과 기관+외국인의 순매수는 합이 0에 가까워, 서로 반대로 움직이는 부분은 계산상 생긴다"])
add(kind="chart", chart="sector", section="4-2 투자자별 수급 ↔ 심리", key="sector", title="개인과 기관은 반대 섹터를 산다",
    lead="커뮤니티가 탐욕인 섹터에서 실제로 파는 쪽은 개인, 사는 쪽은 기관이다",
    bullets=[f"기관 순매수 1위 섹터의 그날 커뮤니티 심리 순위: 평균 {R['inst_top_sector_sent_pct']:.0f}백분위 (탐욕 쪽)",
             f"개인 순매수 1위 섹터: 평균 {R['priv_top_sector_sent_pct']:.0f}백분위 (공포 쪽), 외국인 1위: {R['frgn_top_sector_sent_pct']:.0f}백분위",
             f"개인 1위 섹터와 기관 1위 섹터가 같았던 날: {R['sector_top_overlap']['days']}일 중 0일",
             "단, 순매수는 서로가 맞은편이라 개인과 기관이 반대로 움직이는 부분은 구조적으로 생긴다"])
# ---- 4-2 추가: 섹터 · 종목 순매수 이동과 토론글 (rotation_results.json, rotation_keywords.json) ----
RR = json.load(open(os.path.join(HERE, "../rotation_results.json"))); KW = json.load(open(os.path.join(HERE, "../rotation_keywords.json")))
QS = RR["quarters"]; qlab = lambda q: q[2:4] + "Q" + q[-1] + (" *" if q == "2026Q4" else "")
SECS = RR["sectors"]; heat = RR["heat"]
def heat_cell(v, lim=8.0):
    if v is None: return {"t": "", "bg": BG}
    a = min(abs(v) / lim, 1.0); base_ = (214, 69, 61) if v > 0 else (47, 111, 222)
    bgc = "".join(f"{int(255 - (255 - c) * a * 0.85):02X}" for c in base_)
    return {"t": "0" if abs(v) < 0.5 else f"{v:+.0f}", "bg": bgc, "fg": "FFFFFF" if a > 0.6 else INK}
opp = sum((a > 0) != (b > 0) for s_ in SECS for a, b in zip(heat["priv"][s_], heat["inst"][s_]) if a is not None and b is not None)
tot_cells = sum(1 for s_ in SECS for a, b in zip(heat["priv"][s_], heat["inst"][s_]) if a is not None and b is not None)
qt = RR["quarter_table"]; ovl = RR["overlap"]
semi_top = sum(1 for r in qt if r["talk_top"][0]["sector"] == "반도체")
same_top = sum(1 for r in qt if r["priv_top"][0]["sector"] == r["inst_top"][0]["sector"])
add(kind="grid", section="4-2 투자자별 수급 ↔ 심리", key="ex1", title="예시 ① 분기마다 개인과 기관은 다른 섹터를 1위로 샀다",
    lead=f"개인과 기관이 가장 많이 산 섹터는 {len(QS)}분기 동안 한 번도 같지 않았다. 커뮤니티 글은 거의 늘 반도체에 몰렸다",
    tables=[{"head": ["분기", "개인 1위", "기관 1위", "외국인 1위", "글이 가장 많은 섹터"], "colw": [0.8, 1.75, 1.75, 1.75, 1.75],
             "rows": [[qlab(r["q"])] + [{"t": f"{r[w + '_top'][0]['sector']} {r[w + '_top'][0]['r']:+.1f}%", "fg": c} for w, c in [("priv", PRIV), ("inst", INST), ("frgn", FRGN)]]
                      + [f"{r['talk_top'][0]['sector']} {r['talk_top'][0]['share']:.0f}%"] for r in qt]}],
    bullets=[f"개인 1위 섹터 = 기관 1위 섹터인 분기: {len(QS)}분기 중 {same_top}번",
             f"섹터 · 분기 {tot_cells}칸 중 {opp}칸({opp/tot_cells*100:.0f}%)에서 개인과 기관의 순매수 방향이 반대",
             f"글이 가장 많은 섹터: {len(QS)}분기 중 {semi_top}분기가 반도체",
             f"{len(QS)}분기 기록이라 통계 검정이 아니라 흐름을 보여 주는 묘사다",
             f"분기별 상위 3섹터가 '글 많은 상위 3섹터'와 겹친 수(27칸 중): 개인 {sum(o['priv_talk'] for o in ovl)}, 외국인 {sum(o['frgn_talk'] for o in ovl)}, 기관 {sum(o['inst_talk'] for o in ovl)}",
             "% = 섹터 순매수 ÷ 섹터 거래대금 / 글 % = 45종목 글 중 비중. * 26Q4는 10/1~11/11"])
add(kind="grid", section="4-2 투자자별 수급 ↔ 심리", key="heat", title="섹터 순매수 지도: 개인 vs 기관",
    lead=f"같은 섹터 · 같은 분기에 개인이 사면(빨강) 기관은 파는(파랑) 칸이 3분의 2({opp/tot_cells*100:.0f}%)다",
    tables=[{"title": f"개인 순매수 비율(%)", "head": ["섹터"] + [qlab(q) for q in QS], "colw": [1.15] + [0.48] * len(QS), "small": True,
             "rows": [[s_.replace("서비스", "")] + [heat_cell(v) for v in heat["priv"][s_]] for s_ in SECS]},
            {"title": f"기관 순매수 비율(%)", "head": ["섹터"] + [qlab(q) for q in QS], "colw": [1.15] + [0.48] * len(QS), "small": True,
             "rows": [[s_.replace("서비스", "")] + [heat_cell(v) for v in heat["inst"][s_]] for s_ in SECS]}],
    bullets=[])
kw = lambda q, s_: " · ".join(w for w, _ in KW.get(f"{q}|{s_}", {"words": []})["words"][:3]) or "(두드러진 단어 없음)"
retq = lambda q, s_: RR["heat_ret"][s_][QS.index(q)]
shq = lambda q, s_: RR["heat_S"][s_][QS.index(q)]
topret = {w: [retq(r["q"], r[w + "_top"][0]["sector"]) for r in qt] for w in ["priv", "inst", "frgn"]}
add(kind="grid", section="4-2 투자자별 수급 ↔ 심리", key="ex3", title="예시 ③ 그때 토론방에서는 무슨 이야기를 했나",
    lead=f"개인이 가장 많이 산 섹터는 그 분기에 대개 내렸고(평균 {sum(topret['priv'])/len(qt):+.1f}%), 기관이 산 섹터는 대개 올랐다(평균 {sum(topret['inst'])/len(qt):+.1f}%)",
    tables=[{"head": ["분기", "개인이 가장 많이 산 섹터", "그 섹터 토론글 단어", "기관이 가장 많이 산 섹터", "그 섹터 토론글 단어"], "colw": [0.75, 2.05, 2.2, 2.05, 2.2],
             "rows": [[qlab(r["q"]),
                       {"t": f"{r['priv_top'][0]['sector']} (분기 {retq(r['q'], r['priv_top'][0]['sector']):+.0f}%)", "fg": PRIV}, kw(r["q"], r["priv_top"][0]["sector"]),
                       {"t": f"{r['inst_top'][0]['sector']} (분기 {retq(r['q'], r['inst_top'][0]['sector']):+.0f}%)", "fg": INST}, kw(r["q"], r["inst_top"][0]["sector"])] for r in qt if r["q"] != "2026Q4"]}],
    bullets=[f"{len(qt)}분기 중 1위 섹터가 그 분기에 내린 횟수: 개인 {sum(v < 0 for v in topret['priv'])}번, 기관 {sum(v < 0 for v in topret['inst'])}번 (같은 분기 기록이라 예측이 아니라 '내릴 때 개인이 받아 산다'는 뜻)",
             "단어: 섹터 · 분기마다 약 500건씩 뽑은 표본 글(2년 5.9만 건)에서, 다른 분기 · 섹터보다 유독 많이 나온 명사 3개",
             "종목 이름 · 별명, '매수 · 탈출 · 가즈아' 같은 늘 나오는 말은 뺐다. 글 원문은 싣지 않는다",
             "분기 % = 그 섹터 3종목의 분기 수익률 평균. 26Q4는 표본 글이 적어 뺐다. 통계 검정이 아니라 묘사다"])
sm = RR["same_month_corr"]; tf = RR["talk_to_flow"]; ft = RR["flow_to_talk"]
CH["rot_corr"] = dict(type="bar", cats=["개인 순매수", "기관 순매수", "외국인 순매수", "섹터 수익률"],
                      series=[("커뮤니티 심리", [sm["S~priv_r"], sm["S~inst_r"], sm["S~frgn_r"], sm["S~ret"]], GREED),
                              ("글 점유율", [sm["share~priv_r"], sm["share~inst_r"], sm["share~frgn_r"], sm["share~ret"]], NEU)],
                      ylabel="같은 달 상관계수(섹터 안 변화)", fmt="{:+.2f}", labels=True, ylim=(-0.6, 0.8))
add(kind="chart", chart="rot_corr", section="4-2 투자자별 수급 ↔ 심리", key="month", title="월 단위로 봐도 기관은 달아오른 섹터를 그 달에 사고 다음 달에 판다",
    lead="같은 달엔 심리가 높은 섹터를 기관이 사고, 다음 달엔 그 섹터를 판다",
    bullets=[f"같은 달: 섹터 심리가 높을수록 개인은 팔고(r={sm['S~priv_r']:+.2f}) 기관 · 외국인은 산다(r={sm['S~inst_r']:+.2f}, {sm['S~frgn_r']:+.2f})",
             f"다음 달: 심리가 1σ 높았던 섹터에서 기관 순매수 {tf['inst']['S_z']['b']:+.1f}%p (t={tf['inst']['S_z']['t']:.1f}). 개인 · 외국인은 의미 없음",
             f"글 점유율 변화는 다음 달 누구의 수급도 설명하지 못한다 (|t| < 0.5)",
             f"순매수가 몰린 섹터는 다음 달 글 점유율이 오히려 준다 (개인 {ft['priv_r_z']['b']:+.1f}%p, 기관 {ft['inst_r_z']['b']:+.1f}%p / 1σ)",
             f"15섹터 × {RR['panel_n']['months']}개월, 섹터 · 월 고정효과, 섹터 군집 표준오차"])
st = RR["stock_table"]
pc = lambda n: f"{n/1e4:.1f}만" if n >= 1e4 else f"{n:,}"
won = lambda e: f"{e/1e4:+.1f}조" if abs(e) >= 1e4 else f"{e:+,.0f}억"
add(kind="grid", section="4-2 투자자별 수급 ↔ 심리", key="ex4", title="예시 ④ 금액 1위 종목은 대형 반도체주에 몰린다",
    lead="금액 기준으론 개인 · 기관 모두 대형 반도체주에 몰리고, 토론글도 그 종목에 몰린다",
    tables=[{"head": ["분기", "개인 1위", "기관 1위", "외국인 1위"], "colw": [0.7, 2.3, 2.3, 2.3],
             "rows": [[qlab(r["q"])] + [{"t": f"{r[w]['name']} {won(r[w]['eok'])}\n분기 {r[w]['ret']:+.0f}% · 글 {pc(r[w]['posts'])}", "fg": c} for w, c in [("priv", PRIV), ("inst", INST), ("frgn", FRGN)]] for r in st]}],
    bullets=["순매수 대금(원) 기준이라 시가총액이 큰 종목이 위로 온다", "분기 % = 그 분기 주가 변화, 글 = 그 분기 그 종목 토론글 수",
             "같은 종목을 개인 · 기관이 함께 1위로 산 분기: " + (", ".join(f"{qlab(r['q'])} {r['priv']['name']}" for r in st if r['priv']['name'] == r['inst']['name']) or "없음"),
             f"외국인 1위가 글이 적은 종목인 경우: 25Q2 효성중공업(글 {st[2]['frgn']['posts']:,}건, 분기 {st[2]['frgn']['ret']:+.0f}%)"])
pre = R["crash_pre5_mean"]; base = R["flow_baseline"]
add(kind="chart", chart="crash", section="4-2 투자자별 수급 ↔ 심리", key="crash", title="급락 전에 먼저 판 쪽은 외국인이다",
    lead="급락 전 5일 동안 외국인은 평소보다 더 팔았고 개인은 더 샀다. 커뮤니티 심리는 급락 직전까지 평소보다 밝다가 당일에 꺾인다",
    bullets=[f"코스피 −3% 이하 급락일 중 직전 10거래일에 다른 급락이 없던 {cs['n']}일 (전체 {R['crash_all_n']}일, 45종목 합, 거래대금 대비)",
             f"급락 전 5일 평균: 외국인 {pre['frgn']:+.1f}% (평소 {base['frgn']:+.1f}%), 개인 {pre['priv']:+.1f}% (평소 {base['priv']:+.1f}%), 기관 {pre['inst']:+.1f}% (평소 {base['inst']:+.1f}%)",
             f"커뮤니티 심리 S: 평소 {base['S']:+.3f} → 급락 전 5일 {pre['S']:+.3f} → 급락일 {cp[5]['S']:+.3f}",
             f"기관이 급락 전에 산 섹터 vs 판 섹터: 급락일 {cs['top_day']:+.1f}% vs {cs['bot_day']:+.1f}%, 이후 5일 {cs['top_after']:+.1f}% vs {cs['bot_after']:+.1f}% → 뚜렷한 차이 없음",
             f"급락일이 {cs['n']}일뿐이라 참고용이다"])
add(kind="chart", chart="dn_gap", section="4-3 선행 · 후행", key="dn", title="다음 날 시가를 설명하는 건 낮 글이 아니라 밤 글이다",
    lead="다음 날 시가와 함께 움직이는 건 밤 글이다. 낮 글의 정보는 밤 글에 이미 들어 있다",
    bullets=[f"야간 심리 1σ ↑ → 당일 시가 갭 {R['dfe_lead_gap']['Snz']['b']:+.2f}%p (t={R['dfe_lead_gap']['Snz']['t']:.1f}), 그날 시장 전체 움직임을 뺀 값",
             f"시장 움직임을 빼지 않으면 {R['daynight_lead_gap']['Snz']['b']:+.2f}%p. 차이는 밤사이 시장 전체 재료가 글과 시가를 함께 움직인 몫",
             f"전일 주간 심리는 야간 심리와 함께 넣으면 {R['dfe_lead_gap']['Sd1z']['b']:+.2f}%p (t={R['dfe_lead_gap']['Sd1z']['t']:.1f})",
             f"5분위 사이 시가 갭 차이: 야간 {nq[-1]['gap']-nq[0]['gap']:.1f}%p, 주간 {dq[-1]['gap']-dq[0]['gap']:.1f}%p",
             f"{DN['stocks']}종목 · {DN['days']}거래일, 밤 글 5건 이상인 {DN['rows']:,}개 종목·일. 종목 · 날짜 고정효과, 전일 수익률 통제. 그래프는 단순 평균"])
add(kind="chart", chart="gap_intra", section="4-3 선행 · 후행", key="gap", title="밤 글의 효과는 시가에서 끝난다",
    lead="밤 글이 낙관적일수록 높게 시작하지만, 시가 이후 장중엔 효과가 없고 오히려 조금 되돌린다",
    bullets=[f"상승 출발 비율: 가장 공포인 밤 {nq[0]['up_gap']*100:.0f}% → 가장 탐욕인 밤 {nq[-1]['up_gap']*100:.0f}%",
             f"장중(시가→종가) 효과 {R['dfe_lead_intra']['Snz']['b']:+.2f}%p (t={R['dfe_lead_intra']['Snz']['t']:.1f}): 작은 되돌림",
             f"08:00 프리마켓 전 글만 써도 시가 갭 {R['dfe_lead_gap_0800']['Sn8z']['b']:+.2f}%p (t={R['dfe_lead_gap_0800']['Sn8z']['t']:.1f})",
             f"대체거래소 출범(25-03) 전 구간만 보면 {R['dfe_lead_gap_prenxt']['Snz']['b']:+.2f}%p (t={R['dfe_lead_gap_prenxt']['Snz']['t']:.1f}, {R['dfe_lead_gap_prenxt']['n']:,}건)",
             "분봉이 없어 '장초'는 시가 갭(전일 종가 → 당일 시가)으로 봤다"])
add(kind="chart", chart="lag", section="4-3 선행 · 후행", key="lag", title="주가가 먼저 움직이고, 글이 따라간다",
    lead="오른 날은 글이 낙관적으로, 내린 날은 비관적으로 바뀐다. 낮 글이 더 크게 반응한다",
    bullets=[f"당일 수익률 1%p → 같은 날 주간 심리 +{R['lag_ret_to_day']['ret']['b']:.3f}σ (t={R['lag_ret_to_day']['ret']['t']:.1f})",
             f"같은 날 밤 심리 +{R['lag_ret_to_night']['ret']['b']:.3f}σ (t={R['lag_ret_to_night']['ret']['t']:.1f})",
             f"−3% 이하인 날 낮 글: 탐욕 {lag[0]['day_greed']*100:.1f}% vs 공포 {lag[0]['day_fear']*100:.1f}%",
             f"+3% 이상인 날 낮 글: 탐욕 {lag[-1]['day_greed']*100:.1f}% vs 공포 {lag[-1]['day_fear']*100:.1f}%"])

# 4-4 보완 분석 (extra_results.json)
XR = json.load(open(os.path.join(HERE, "../extra_results.json")))
cb = XR["c2_bucket"]; c5 = XR["c5"]; c6 = XR["c6_path"]
CH["c2"] = dict(type="bar", cats=[b["bucket"].split(" ", 1)[1] for b in cb], series=[("이후 5일", [b["fwd5"] for b in cb], NEU), ("이후 20일", [b["fwd20"] for b in cb], INK)],
                ylabel="누적 초과수익률(%p, 지수 대비)", xlabel="방향 지수 구간 (0~100)", fmt="{:+.1f}", labels=True)
CH["c6"] = dict(type="line", cats=[f"+{r['h']}일" for r in c6[1:]], series=[("탐욕 글 비율 1σ↑", [r["priv_g"] for r in c6[1:]], GREED), ("공포 글 비율 1σ↑", [r["priv_f"] for r in c6[1:]], FEAR)],
                ylabel="그날 개인 순매수 비율 반응(%p)", xlabel="충격 이후 거래일", fmt="{:+.2f}", labels=True)
C5N = {"priv_n1": "다음 날 개인 순매수", "vr_n1": "다음 날 거래량 비율", "range_n1": "다음 날 변동폭"}
CH["c5"] = dict(type="bar", cats=[C5N[k] for k in C5N], series=[("시장 자료만", [c5[k]["mkt_gbm"]["r2"] for k in C5N], NEU), ("+ 커뮤니티 변수", [c5[k]["com_gbm"]["r2"] for k in C5N], GREED)],
                ylabel="표본 밖 설명력 R²", fmt="{:.3f}", labels=True)
reg = lambda k, v: XR[k][v]
fx = lambda d, u="%p": f"{d['b']:+.2f}{u} (t={d['t']:.1f})"
add(kind="chart", chart="c2", section="4-4 보완 분석", key="c2", title="극단적 공포를 매수 기회로 볼 근거는 없었다",
    lead="지수가 낮은 날 뒤에 더 오르지 않았다. 오히려 공포 쪽일수록 이후 성과가 조금 낮다",
    bullets=[f"이후 20일 초과수익률: 극단적 공포 {cb[0]['fwd20']:+.1f}%p, 중립 {cb[2]['fwd20']:+.1f}%p, 극단적 탐욕 {cb[-1]['fwd20']:+.1f}%p",
             f"같은 날 다른 종목과 비교하면(날짜 효과) 극단적 공포 {fx(reg('c2_reg_fwd20', 'xfear'))}, 극단적 탐욕 {fx(reg('c2_reg_fwd20', 'xgreed'))}: 둘 다 유의하지 않다",
             f"5일 뒤 오른 비율은 구간마다 {min(b['up5'] for b in cb)*100:.0f}~{max(b['up5'] for b in cb)*100:.0f}%로 비슷하다",
             "표본 종목이 기간 내내 지수보다 많이 올라 초과수익률이 모두 플러스다. 구간 사이 차이만 본다"])
add(kind="grid", section="4-4 보완 분석", key="c3", title="심리가 높은 날 다음 날엔 변동폭과 거래량이 커지고 공매도는 준다",
    lead="커뮤니티 심리와 글 수는 다음 날 주가 방향보다 '얼마나 움직이나'와 더 관계가 있다",
    tables=[{"head": ["다음 날 값", "심리 1σ ↑", "글 수 2배"], "colw": [2.6, 2.3, 2.3],
             "rows": [["거래량 (20일 평균 대비, 배)", fx(reg("c3_vr_n1", "Sz"), ""), f"{reg('c3_vr_n1', 'lint')['b']*0.693:+.2f} (t={reg('c3_vr_n1', 'lint')['t']:.1f})"],
                      ["일중 변동폭 (%p)", fx(reg("c3_range_n1", "Sz")), f"{reg('c3_range_n1', 'lint')['b']*0.693:+.2f}%p (t={reg('c3_range_n1', 'lint')['t']:.1f})"],
                      [f"공매도 비중 (%p, 25-03-31 재개 뒤)", fx(reg("c3_short_n1", "Sz")), f"{reg('c3_short_n1', 'lint')['b']*0.693:+.2f}%p (t={reg('c3_short_n1', 'lint')['t']:.1f})"],
                      ["의견 갈림 1σ ↑ → 그날 거래량", fx(reg("c4_same", "dis_z"), ""), ""],
                      ["의견 갈림 1σ ↑ → 다음 날 거래량", fx(reg("c4_next", "dis_z"), ""), ""]]}],
    bullets=["종목 · 날짜 고정효과, 그날 등락폭과 그 값의 당일 수준을 통제했다",
             "글 수는 다음 날 거래량을, 심리는 다음 날 변동폭을 더 잘 설명한다",
             "의견이 갈린 날 거래량이 늘어난다는 선행 연구와 달리, 이 데이터에선 관계가 없었다",
             f"공매도는 재개 뒤 {XR['c3_short_n1']['n']:,}개 종목·일만 썼다 (2023-11 ~ 2025-03 전면 금지)"])
add(kind="chart", chart="c6", section="4-4 보완 분석", key="c6", title="공포 글이 많았던 종목은 그 뒤 며칠 더 개인이 사들인다",
    lead="탐욕과 공포를 따로 보면, 공포 쪽의 흔적이 더 오래 남는다",
    bullets=[f"그날: 탐욕 글 비율 1σ↑ → 개인 {c6[0]['priv_g']:+.1f}%p, 공포 글 비율 1σ↑ → 개인 {c6[0]['priv_f']:+.1f}%p (차트는 다음 날부터)",
             f"공포 글이 많았던 날 뒤 2~5일 동안 개인 순매수 {min(r['priv_f'] for r in c6[2:6]):+.2f}~{max(r['priv_f'] for r in c6[2:6]):+.2f}%p (t {min(r['priv_f_t'] for r in c6[2:6]):.1f}~{max(r['priv_f_t'] for r in c6[2:6]):.1f})",
             f"주가: 공포 글 비율 1σ↑ 날 {c6[0]['ret_f']:+.2f}%p, 이후 5일 누적 {c6[5]['ret_f']:+.2f}%p (t={c6[5]['ret_f_t']:.1f}). 탐욕은 그날 {c6[0]['ret_g']:+.2f}%p 뒤 유의한 움직임 없음",
             "충격 뒤 0~10일 각각에 같은 회귀를 반복했다(종목 · 날짜 고정효과, 전일 수익률 통제)"])
b5d = XR["b5_desc"]; hv = XR["b5_hold_vs_non"]
add(kind="grid", section="4-4 보완 분석", key="b5", title="커뮤니티 안에서도 말과 행동은 반대다",
    lead="심리가 탐욕적인 날일수록 매수 인증은 줄고 매도 인증이 는다. 그리고 인증 행동은 실제 개인 수급과 같은 방향이다",
    tables=[{"head": ["관계 (그날 수익률 통제)", "효과", "t"], "colw": [4.0, 1.6, 0.9],
             "rows": [["심리 1σ ↑ → 매수 인증 비율", f"{XR['b5_buy_S']['Sz']['b']:+.2f}σ", f"{XR['b5_buy_S']['Sz']['t']:.1f}"],
                      ["매수 인증 비율 1σ ↑ → 그날 개인 순매수", f"{XR['b5_buy_priv']['buy_z']['b']:+.1f}%p", f"{XR['b5_buy_priv']['buy_z']['t']:.1f}"],
                      ["매수 인증 비율 1σ ↑ → 다음 날 개인 순매수", f"{XR['b5_buy_priv_n1']['buy_z']['b']:+.1f}%p", f"{XR['b5_buy_priv_n1']['buy_z']['t']:.1f}"],
                      ["매수 인증 비율 1σ ↑ → 다음 날 초과수익률", f"{XR['b5_buy_fwd1']['buy_z']['b']:+.2f}%p", f"{XR['b5_buy_fwd1']['buy_z']['t']:.1f}"],
                      ["보유자 심리 1σ ↑ → 그날 개인 순매수", f"{hv['priv']['hz']['b']:+.1f}%p", f"{hv['priv']['hz']['t']:.1f}"],
                      ["비보유자 심리 1σ ↑ → 그날 개인 순매수", f"{hv['priv']['nz']['b']:+.1f}%p", f"{hv['priv']['nz']['t']:.1f}"]]}],
    bullets=[f"매수 · 매도 인증 글은 전체의 {b5d['badge_rate']:.1f}%. 인증 글이 5건 이상인 {b5d['days_with_badges']:,}개 종목·일로 계산했다",
             "커뮤니티가 탐욕적인 날 인증 글은 매도 쪽으로 기운다. 글로 하는 말과 인증으로 보이는 행동이 커뮤니티 안에서도 엇갈린다",
             "매수 인증 비율은 그날 실제 개인 순매수와 함께 움직인다. 인증은 실제 매매를 비추는 거울에 가깝다",
             f"글의 {b5d['hold_share']:.0f}%가 보유자 글이고, 보유자 심리가 높을수록 개인은 더 판다. 다음 날 수익률 · 수급은 인증과 보유 어느 쪽도 설명하지 못했다",
             "종목 · 날짜 고정효과, 그날 수익률을 통제했다"])
add(kind="bullets2", section="4-4 보완 분석", key="b4", title="주가로 설명되는 부분을 빼고 남은 심리는 예측력이 약하다",
    lead=f"그날 심리의 {XR['b4_fit']['r2']*100:.0f}%는 그날 · 전날 주가와 시장 움직임으로 설명된다. 나머지가 '잔차 심리'다",
    bullets=[f"주가가 1% 넘게 올랐는데 잔차 심리가 하위 20%인 날: {XR['b4_cases']['up_but_fear']*100:.1f}%, 1% 넘게 내렸는데 상위 20%인 날: {XR['b4_cases']['down_but_greed']*100:.1f}%",
             f"잔차 심리 1σ ↑ → 다음 날 초과수익률 {fx(reg('b4_fwd1', 'Sres_z'))}, 이후 5일 {fx(reg('b4_fwd5', 'Sres_z'))}",
             f"잔차 심리 1σ ↑ → 다음 날 개인 순매수 {fx(reg('b4_priv_n1', 'Sres_z'))}, 거래량 {fx(reg('b4_vr_n1', 'Sres_z'), '')}",
             "모두 5% 유의수준에 못 미친다. 심리의 정보는 대부분 주가와 함께 이미 움직인 부분에 있다"])
add(kind="chart", chart="c5", section="4-4 보완 분석", key="c5", title="커뮤니티 변수를 더하면 다음 날 거래량 · 변동폭 · 개인 수급 예측이 나아진다",
    lead="주가 방향은 못 맞히지만, 내일 얼마나 움직이고 개인이 얼마나 살지는 더 잘 맞힌다",
    bullets=[f"{XR['c5_test'][0]} ~ {XR['c5_test'][1]} 매달, 그 전 자료로만 학습해 다음 달을 예측했다 (그래디언트 부스팅)",
             "시장 자료: 그날 · 전날 수익률, 시장 수익률, 거래량 비율, 변동폭, 개인 · 기관 · 외국인 순매수",
             "커뮤니티 변수: 심리, 키워드 강도, 관심도, 의견 갈림, 밤 심리, 탐욕 · 공포 비율, 잔차 심리, 글 수",
             "예측 오차 차이 검정(Diebold–Mariano): " + ", ".join(f"{C5N[k].replace('다음 날 ', '')} t={c5[k]['dm_gbm']['t']:.1f}" for k in C5N) + " — 모두 개선",
             "설명력 자체는 작다. 매매 신호가 아니라 '내일 얼마나 붐빌지'를 알려 주는 정도다"])

# 5 정리
add(kind="section", num="05", title="정리", sub="")
add(kind="summary", section="05 정리", title="정리",
    lead="커뮤니티 심리는 주가를 예측하기보다 따라간다. 그리고 말과 행동은 반대다",
    cards=[("개념", "RSI · CNN 지수처럼 '극단'을 읽는 지표를, 종목 단위 커뮤니티 글로 만들었다"),
           ("데이터 · 감성", f"45종목 · 2년 · {man(N_POSTS)} 건. LLM 2.9만 건으로 가르친 모델이 전체를 판정(판정한 글 기준 정확도 {ACC_NEW:.0f}%)"),
           ("수급", "탐욕인 날·섹터에서 개인은 팔고 기관 · 외국인은 산다. 분기로 보면 개인은 내린 섹터, 기관은 오른 섹터를 샀다. 글이 몰린 하락일엔 개인이 사들인다"),
           ("선행 · 후행", f"밤 심리는 시가 갭만 설명({R['dfe_lead_gap']['Snz']['b']:+.2f}%p/σ, 시장 움직임 제외). 장중엔 오히려 조금 되돌린다. 주가가 오르면 글이 따라 낙관적으로 바뀐다")],
    bullets=["매매 신호가 아니라 '심리 온도계'로 쓰는 것이 맞다. 극단적 공포를 매수 기회로 볼 근거는 없었다", "밤사이 공포가 큰 종목은 낮게 시작할 가능성이 높다는 정도까지만 말할 수 있다", "대신 다음 날 거래량 · 변동폭 · 개인 수급을 예측하는 데는 보탬이 된다"])
add(kind="bullets2", section="05 정리", title="한계",
    lead="숫자를 읽을 때 함께 봐야 할 것",
    bullets=["라벨 품질: 정답은 LLM 판정이고 사람 검수를 거치지 않았다", "대표성: 커뮤니티에 글을 쓰는 사람이 전체 투자자를 대표하지 않는다",
             "공통 원인: 날짜 효과로 시장 전체 움직임은 걸렀지만, 그 종목만의 밤사이 뉴스가 글과 시가를 함께 움직였을 수 있다 (선후 관계 ≠ 인과)",
             "프리마켓: 08:00 이후엔 가격이 보이는 상태에서 글이 쓰인다. 08:00 전 글만으로도 결과는 같은 방향", "수급 비율: 거래대금을 종가 × 거래량으로 근사했다",
             f"강도 축: 관심도와 쏠림은 상관 {IW['strength']['corr']:.2f}로 거의 따로 움직여, 한 축으로 묶는 근거가 약하다",
             "수집 약관: 토스증권 약관은 자동 수집을 따로 허용하지도 금지하지도 않는다. 원문은 공개하지 않고 작성자 정보는 저장하지 않았다"])
add(kind="end", title="감사합니다", sub="Q & A")

# ---- 대표 12종목 예시 (글이 가장 많은 12종목) ----
T12 = RR["top12"]; t12s = RR["top12_summary"]
ICOL = {"개인": PRIV, "기관": INST, "외국인": FRGN}
def who_cell(x):
    if not x: return {"t": ""}
    return {"t": x["top"], "bg": ICOL[x["top"]], "fg": "FFFFFF"}
S.append(dict(kind="grid", key="ex2", section="4-2 예시", title="예시 ② 대표 12종목: 분기마다 누가 가장 많이 샀나",
    lead=f"같은 종목도 분기마다 주인이 바뀐다. 개인이 1위였던 분기는 주가가 제자리였고(중앙값 {t12s['개인']['ret']:+.1f}%), 기관 · 외국인이 1위였던 분기는 올랐다",
    tables=[{"head": ["종목"] + [qlab(q) for q in QS], "colw": [1.45] + [0.6] * len(QS), "small": True,
             "rows": [[r["name"]] + [who_cell(x) for x in r["q"]] for r in T12]}],
    bullets=[f"토론글이 가장 많은 12종목, 칸마다 그 분기 순매수 비율(순매수 ÷ 거래대금)이 가장 큰 투자자",
             f"1위 횟수: 개인 {t12s['개인']['n']}칸, 기관 {t12s['기관']['n']}칸, 외국인 {t12s['외국인']['n']}칸 (전체 {sum(v['n'] for v in t12s.values())}칸)",
             f"그 분기 주가(중앙값): 개인 1위 {t12s['개인']['ret']:+.1f}%, 기관 1위 {t12s['기관']['ret']:+.1f}%, 외국인 1위 {t12s['외국인']['ret']:+.1f}%",
             f"그 분기 글 분위기 S(평균): 개인 1위 {t12s['개인']['S']:+.3f}로 가장 밋밋, 외국인 1위 {t12s['외국인']['S']:+.3f}",
             f"개인과 기관의 순매수 방향이 반대였던 칸: {RR['top12_opp']*100:.0f}%"]))

# ---- 순서: 4-2는 결과 → 월 단위 → 반대 섹터 → 예시 ①~④ → 급락. 섹터 지도는 부록 ----
by = {x.get("key"): x for x in S if x.get("key")}
order42 = ["quint", "month", "sector", "ex1", "ex2", "ex3", "ex4", "crash"]
for k in order42 + ["heat"]: S.remove(by[k])
pos = S.index(by["posts_next"]) + 1
for k in reversed(order42): S.insert(pos, by[k])
for k in ["ex1", "ex3", "ex4"]: by[k]["section"] = "4-2 예시"
end = S.pop()                       # 감사합니다
S.append(dict(kind="section", num="부록", title="근거 자료", sub="발표 본문에서 요약한 표의 원자료"))
by["heat"]["section"] = "부록"; S.append(by["heat"]); S.append(end)
# ---- 4장 목차: 04 구분 장 바로 뒤 ----
toc = dict(kind="toc", section="04 분석", title="분석 결과 한눈에", lead="4장에서 확인한 것을 먼저 문장으로 보여 주고, 그 근거를 차례로 본다",
           groups=[("4-1 글 수와 개인 수급", ["posts_dir", "posts_next"]),
                   ("4-2 투자자별 수급과 심리", ["quint", "month", "sector", "crash"]),
                   ("4-3 선행 · 후행", ["dn", "gap", "lag"]),
                   ("4-4 보완 분석", ["c2", "c3", "c6", "b5", "b4", "c5"])])
sec4 = next(i for i, x in enumerate(S) if x.get("kind") == "section" and x.get("num") == "04")
S.insert(sec4 + 1, toc)
for g, keys in toc["groups"]: pass
toc["items"] = [(g, [(by[k]["title"], S.index(by[k]) + 1) for k in keys]) for g, keys in toc["groups"]]


# ---- 윤문 결과 적용: humanize_map.json(원문 → 윤문) 이 있으면 슬라이드 문장을 바꿔 끼운다 ----
PROSE_KEYS = ["title", "lead", "sub", "note", "bullets"]
def prose_walk(fn):
    for x in S:
        for k in PROSE_KEYS:
            if k not in x: continue
            if isinstance(x[k], list): x[k] = [fn(v) if isinstance(v, str) else v for v in x[k]]
            elif isinstance(x[k], str): x[k] = fn(x[k])
        if "cards" in x and x["kind"] in ("summary",): x["cards"] = [(t, fn(c)) for t, c in x["cards"]]
        if x["kind"] == "abc":
            x["made"] = (x["made"][0], fn(x["made"][1])); x["how"] = (x["how"][0], fn(x["how"][1]))
            x["found"] = (x["found"][0], [(fn(a), fn(c)) for a, c in x["found"][1]])
        if x["kind"] == "labels": x["ex"] = [(t, l, c, fn(w)) for t, l, c, w in x["ex"]]
if os.environ.get("DUMP_PROSE"):
    seen = []
    prose_walk(lambda v: (seen.append(v) if v not in seen else None) or v)
    json.dump(seen, open(os.path.join(HERE, "prose_src.json"), "w"), ensure_ascii=False, indent=1); raise SystemExit(f"dumped {len(seen)}")
HMAP = os.path.join(HERE, "humanize_map.json")
if os.path.exists(HMAP):
    hm = json.load(open(HMAP)); prose_walk(lambda v: hm.get(v, v))
    for x in S:
        if x.get("kind") == "toc": x["items"] = [(g, [(hm.get(t, t), n_) for t, n_ in items]) for g, items in x["items"]]

# =============== HTML ===============
plt.rcParams.update({"font.family": ["Apple SD Gothic Neo", "AppleGothic"], "svg.fonttype": "path", "axes.unicode_minus": False})
def svg_chart(c, w=7.0, h=4.3):
    fig, ax = plt.subplots(figsize=(w, h), dpi=100)
    cats, ser = [t.replace("−", "-") for t in c["cats"]], c["series"]; n = len(ser); x = range(len(cats))   # 차트 글꼴에 '−' 글리프가 없음
    hl = {k.replace("−", "-"): v for k, v in c.get("hl", {}).items()}
    if c["type"] == "bar":
        bw = 0.8 / n
        for i, (name, vals, col) in enumerate(ser):
            xs = [j - 0.4 + bw * (i + 0.5) for j in x]
            cols = [("#" + hl.get(cat, col)) for cat in cats] if hl else "#" + col
            bars = ax.bar(xs, vals, bw * 0.92, color=cols, label=name)
            if c.get("labels"):
                for b, v in zip(bars, vals):
                    ax.annotate(c["fmt"].format(v), (b.get_x() + b.get_width() / 2, v), xytext=(0, 3 if v >= 0 else -11), textcoords="offset points", ha="center", fontsize=11, color="#" + INK)
    else:
        for name, vals, col in ser:
            ax.plot(list(x), vals, marker="o", lw=2.4, ms=5, color="#" + col, label=name)
            if c.get("labels"):
                for j, v in zip(x, vals):
                    ax.annotate(c["fmt"].format(v), (j, v), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=11, color="#" + col)
    ax.axhline(0, color="#" + MUTED, lw=0.8)
    ax.set_xticks(list(x)); ax.set_xticklabels(cats, fontsize=11.5, color="#" + INK)
    if len(cats) > 12: ax.tick_params(axis="x", labelsize=9.5)
    ax.tick_params(axis="y", labelsize=11, colors="#" + MUTED)
    if c.get("ylim"): ax.set_ylim(*c["ylim"])
    ax.set_ylabel(c.get("ylabel", "").replace("−", "-"), fontsize=11.5, color="#" + MUTED)
    if c.get("xlabel"): ax.set_xlabel(c["xlabel"].replace("−", "-"), fontsize=11.5, color="#" + MUTED)
    for s in ["top", "right"]: ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]: ax.spines[s].set_color("#" + LINE)
    ax.grid(axis="y", color="#" + LINE, lw=0.6); ax.set_axisbelow(True)
    if n > 1: ax.legend(frameon=False, fontsize=11.5, **c.get("legend", {"loc": "best"}))   # 막대를 가리면 차트별로 위치 지정
    fig.tight_layout()
    b = io.StringIO(); fig.savefig(b, format="svg", transparent=True); plt.close(fig)
    s = b.getvalue(); s = s[s.index("<svg"):]
    return re.sub(r'(<svg[^>]*?) width="[^"]+" height="[^"]+"', r'\1 width="100%" height="100%" preserveAspectRatio="xMidYMid meet"', s, count=1)

E = html.escape
def ul(items): return "<ul>" + "".join(f"<li>{E(i)}</li>" for i in items) + "</ul>"
def slide_html(i, s):
    k = s["kind"]; head = ""
    if k not in ("cover", "section", "end"):
        head = f'<div class="eyebrow">{E(s.get("section",""))}</div><h2>{E(s["title"])}</h2><p class="lead">{E(s.get("lead",""))}</p>'
    if k == "cover":
        body = f'<div class="cover"><div class="eyebrow light">{E(s["meta"])}</div><h1>{E(s["title"])}</h1><p class="sub">{E(s["sub"])}</p><div class="gauge">' + \
               "".join(f'<span style="background:#{c}">{t}</span>' for t, c in [("극단적 공포", "1F4FAF"), ("공포", "6E9BEA"), ("중립", "8A94A6"), ("탐욕", "EA8A80"), ("극단적 탐욕", "B5302A")]) + "</div></div>"
        return f'<section class="slide dark">{body}</section>'
    if k == "section":
        return f'<section class="slide dark"><div class="sec"><div class="num">{s["num"]}</div><h1>{E(s["title"])}</h1><p class="sub">{E(s["sub"])}</p></div></section>'
    if k == "end":
        return f'<section class="slide dark"><div class="sec"><h1>{E(s["title"])}</h1><p class="sub">{E(s["sub"])}</p></div></section>'
    if k == "stats":
        b = '<div class="stats4">' + "".join(f'<div class="stat"><div class="big">{E(a)}</div><div class="lab">{E(l)}</div><div class="cap">{E(c)}</div></div>' for a, l, c in s["stats"]) + "</div>"
    elif k == "cnn":
        b = '<div class="two"><div class="items">' + "".join(f'<div class="it"><b>{E(a)}</b><span>{E(c)}</span></div>' for a, c in s["items"]) + '</div><div><div class="band">' + \
            "".join(f'<div style="flex:{hi-lo};background:#{c}"><b>{E(t)}</b><span>{lo}–{hi}</span></div>' for t, lo, hi, c in s["bands"]) + f'</div><p class="note">{E(s["note"])}</p></div></div>'
    elif k in ("rsi", "formula"):
        b = '<div class="two"><div class="steps">' + "".join(f'<div class="step"><b>{E(a)}</b><span>{E(c)}</span></div>' for a, c in s["steps"]) + '</div><div><div class="example">' + \
            "".join(f"<div>{E(x)}</div>" for x in s["example"]) + "</div>"
        if k == "formula": b += '<div class="axes">' + "".join(f'<div><b>{E(a)}</b><span>{E(c)}</span></div>' for a, c in s["axes"]) + "</div>"
        else: b += '<div class="rsibar"><div style="flex:30;background:#6E9BEA">과매도 0–30</div><div style="flex:40;background:#C9CFD9">30–70</div><div style="flex:30;background:#EA8A80">과매수 70–100</div></div>'
        b += "</div></div>"
    elif k == "table":
        b = '<div class="two w"><table><thead><tr>' + "".join(f"<th>{E(h)}</th>" for h in s["head"]) + "</tr></thead><tbody>" + \
            "".join("<tr>" + "".join(f"<td>{E(c)}</td>" for c in r) + "</tr>" for r in s["rows"]) + f'</tbody></table><div class="box"><h3>활용 방식</h3>{ul(s["bullets"])}</div></div>'
    elif k == "data":
        b = '<div class="cards2">' + "".join(f'<div class="card"><h3>{E(t)}</h3>{ul(l)}</div>' for t, l in s["cards"]) + '</div><div class="stats3">' + \
            "".join(f'<div class="stat"><div class="big">{E(a)}</div><div class="lab">{E(l)}</div></div>' for a, l in s["stats"]) + "</div>"
    elif k == "sectors":
        b = '<div class="secgrid">' + "".join(f'<div class="sc"><b>{E(t)}</b><span>{E(" · ".join(n))}</span></div>' for t, n in s["sectors"]) + "</div>"
    elif k == "labels":
        b = '<div class="exs">' + "".join(f'<div class="ex"><q>{E(t[1:-1])}</q><em style="background:#{c}">{E(l)}</em><span>{E(w)}</span></div>' for t, l, c, w in s["ex"]) + f'</div><p class="note">{E(s["note"])}</p>'
    elif k == "cost":
        b = '<div class="two"><div class="calc">' + "".join(f'<div class="step"><b>{E(a)}</b><span>{E(c)}</span></div>' for a, c in s["calc"]) + f'</div><div><div class="vs">' + \
            "".join(f'<div class="stat"><div class="lab">{E(a)}</div><div class="big">{E(c)}</div></div>' for a, c in s["vs"]) + f'</div><p class="note">{E(s["note"])}</p></div></div>'
    elif k == "flow":
        b = '<div class="flow">' + "".join(f'<div class="fs"><b>{E(a)}</b><span>{E(c)}</span></div>' for a, c in s["steps"]) + f'</div>{ul(s["bullets"])}'
    elif k == "chart":
        b = f'<div class="two c"><div class="chart">{svg_chart(CH[s["chart"]])}</div><div class="box">{ul(s["bullets"])}</div></div>'
    elif k == "summary":
        b = '<div class="cards4">' + "".join(f'<div class="card"><h3>{E(t)}</h3><p>{E(c)}</p></div>' for t, c in s["cards"]) + f'</div><div class="box">{ul(s["bullets"])}</div>'
    elif k == "abc":
        b = '<div class="abc"><div class="abl">' + "".join(f'<div class="card"><h3>{E(t)}</h3><p>{E(c)}</p></div>' for t, c in (s["made"], s["how"])) + \
            f'</div><div class="card found"><h3>{E(s["found"][0])}</h3>' + "".join(f'<div class="fd"><b>{E(a)}</b><span>{E(c)}</span></div>' for a, c in s["found"][1]) + "</div></div>"
    elif k == "toc":
        b = f'<div class="toc" style="grid-template-columns:repeat({len(s["items"])},1fr)">' + "".join(f'<div class="tg"><h3>{E(g)}</h3>' + "".join(f'<div class="ti"><span>{E(t)}</span><em>{n}</em></div>' for t, n in items) + "</div>" for g, items in s["items"]) + "</div>"
    elif k == "grid":
        def cell(c, tag="td"):
            if isinstance(c, dict):
                st_ = (f"background:#{c['bg']};" if c.get("bg") else "") + (f"color:#{c['fg']};" if c.get("fg") else "")
                return f'<{tag} style="{st_}">{E(c["t"]).replace(chr(10), "<br>")}</{tag}>'
            return f"<{tag}>{E(c)}</{tag}>"
        tbls = ""
        for t in s["tables"]:
            cls = "gt small" if t.get("small") else "gt"
            tbls += '<div class="gtw">' + (f'<h3>{E(t["title"])}</h3>' if t.get("title") else "") + f'<table class="{cls}"><thead><tr>' + "".join(cell(h, "th") for h in t["head"]) + "</tr></thead><tbody>" + \
                "".join("<tr>" + "".join(cell(c) for c in r) + "</tr>" for r in t["rows"]) + "</tbody></table></div>"
        side = len(s["tables"]) == 1 and sum(s["tables"][0]["colw"]) <= 8.2 and s["bullets"]
        if side: b = f'<div class="two g"><div>{tbls}</div><div class="box">{ul(s["bullets"])}</div></div>'
        else: b = f'<div class="gts">{tbls}</div>' + (f'<div class="box">{ul(s["bullets"])}</div>' if s["bullets"] else "")
    elif k == "bullets2":
        b = f'<div class="box big">{ul(s["bullets"])}</div>'
    return f'<section class="slide">{head}<div class="body">{b}</div><div class="foot"><span>토스증권 커뮤니티 공포탐욕지수 · 소셜미디어 분석 6조</span><span>{i+1}</span></div></section>'

CSS = f"""
:root{{--ink:#{INK};--muted:#{MUTED};--line:#{LINE};--panel:#{PANEL};--dark:#{DARK}}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#E6E9EF;color:var(--ink);font-family:Pretendard,"Apple SD Gothic Neo","Malgun Gothic","맑은 고딕",sans-serif;-webkit-font-smoothing:antialiased}}
.deck{{display:flex;flex-direction:column;align-items:center;gap:24px;padding:24px 16px}}
.slide{{position:relative;width:min(100%,1280px);aspect-ratio:16/9;background:#fff;container-type:inline-size;padding:3.6cqw 4.4cqw 3.4cqw;display:flex;flex-direction:column;overflow:hidden;border-radius:6px;box-shadow:0 2px 10px rgba(20,30,50,.08)}}
.slide.dark{{background:var(--dark);color:#fff;justify-content:center}}
.eyebrow{{font-size:1.15cqw;font-weight:700;color:#{GREED};letter-spacing:.02em}} .eyebrow.light{{color:#9AA6BC}}
h1{{font-size:4.6cqw;line-height:1.2;font-weight:800}} h2{{font-size:2.65cqw;line-height:1.25;font-weight:800;margin-top:.4cqw}}
h3{{font-size:1.45cqw;font-weight:700;margin-bottom:.7cqw}}
.lead{{font-size:1.5cqw;color:var(--muted);margin-top:.7cqw;line-height:1.45}}
.sub{{font-size:1.9cqw;color:#B8C2D6;margin-top:1.2cqw}}
.body{{flex:1;display:flex;flex-direction:column;justify-content:center;gap:1.6cqw;min-height:0;margin-top:1.6cqw}}
ul{{list-style:none;display:flex;flex-direction:column;gap:.9cqw}} li{{font-size:1.32cqw;line-height:1.45;padding-left:1.3cqw;position:relative}}
li:before{{content:"";position:absolute;left:0;top:.62cqw;width:.5cqw;height:.5cqw;border-radius:50%;background:#{GREED}}}
.foot{{position:absolute;left:4.4cqw;right:4.4cqw;bottom:1.4cqw;display:flex;justify-content:space-between;font-size:.9cqw;color:#9AA3B2}}
.cover h1{{margin-top:1cqw}} .gauge{{display:flex;margin-top:3.2cqw;width:62%;border-radius:.6cqw;overflow:hidden}} .gauge span{{flex:1;font-size:1.05cqw;padding:.8cqw .6cqw;text-align:center;font-weight:700}}
.sec .num{{font-size:7cqw;font-weight:800;color:#{GREED};line-height:1}} .sec h1{{margin-top:1cqw}}
.two{{display:grid;grid-template-columns:1.15fr 1fr;gap:2.6cqw;align-items:center;min-height:0}} .two.c{{grid-template-columns:1.45fr 1fr}} .two.w{{grid-template-columns:1.4fr 1fr}}
.chart{{height:30cqw;min-height:0}} .chart svg{{display:block}}
.box{{background:var(--panel);border-radius:.8cqw;padding:1.8cqw}} .box.big li{{font-size:1.55cqw}}
.stats4{{display:grid;grid-template-columns:repeat(4,1fr);gap:1.4cqw}} .stats3{{display:grid;grid-template-columns:repeat(3,1fr);gap:1.4cqw}}
.stat{{background:var(--panel);border-radius:.8cqw;padding:1.8cqw 1.6cqw}} .big{{font-size:3.3cqw;font-weight:800;color:var(--ink);line-height:1.1}}
.lab{{font-size:1.25cqw;margin-top:.8cqw;line-height:1.4;font-weight:600}} .cap{{font-size:1.05cqw;color:var(--muted);margin-top:.6cqw;line-height:1.4}}
.items{{display:grid;grid-template-columns:1fr 1fr;gap:.9cqw}} .it{{background:var(--panel);border-radius:.6cqw;padding:1cqw 1.2cqw}} .it b{{display:block;font-size:1.25cqw}} .it span{{font-size:1.05cqw;color:var(--muted);line-height:1.4}}
.band{{display:flex;border-radius:.6cqw;overflow:hidden;color:#fff}} .band div{{padding:1.4cqw .5cqw;text-align:center}} .band b{{display:block;font-size:1.1cqw}} .band span{{font-size:1cqw;opacity:.9}}
.note{{font-size:1.1cqw;color:var(--muted);margin-top:1.2cqw;line-height:1.5}}
.steps,.calc{{display:flex;flex-direction:column;gap:.9cqw}} .step{{display:grid;grid-template-columns:8.5cqw 1fr;gap:1cqw;align-items:baseline;background:var(--panel);border-radius:.6cqw;padding:1.1cqw 1.3cqw}}
.step b{{font-size:1.25cqw;color:#{GREED}}} .step span{{font-size:1.3cqw;line-height:1.4}}
.example{{background:var(--dark);color:#E9EDF5;border-radius:.8cqw;padding:1.8cqw;font-size:1.3cqw;line-height:1.75;font-variant-numeric:tabular-nums;white-space:pre-wrap}}
.axes{{display:flex;flex-direction:column;gap:.6cqw;margin-top:1.2cqw}} .axes div{{font-size:1.15cqw}} .axes b{{display:inline-block;width:4cqw;color:#{GREED}}}
.rsibar{{display:flex;margin-top:1.4cqw;border-radius:.6cqw;overflow:hidden;font-size:1.05cqw;font-weight:700;color:#fff;text-align:center}} .rsibar div{{padding:1cqw .3cqw}} .rsibar div:nth-child(2){{color:var(--ink)}}
table{{border-collapse:collapse;width:100%;font-size:1.22cqw}} th,td{{padding:1cqw 1cqw;border-bottom:1px solid var(--line);text-align:left;line-height:1.35}} th{{font-size:1.15cqw;color:var(--muted)}} td:first-child{{font-weight:700;color:var(--muted)}} td:last-child,th:last-child{{color:#{GREED};font-weight:700}}
.cards2{{display:grid;grid-template-columns:1fr 1fr;gap:1.6cqw}} .cards4{{display:grid;grid-template-columns:repeat(4,1fr);gap:1.2cqw}}
.card{{background:var(--panel);border-radius:.8cqw;padding:1.8cqw}} .card p{{font-size:1.25cqw;line-height:1.5}}
.secgrid{{display:grid;grid-template-columns:repeat(5,1fr);gap:.9cqw}} .sc{{background:var(--panel);border-radius:.6cqw;padding:1.1cqw 1.1cqw}} .sc b{{display:block;font-size:1.25cqw;margin-bottom:.4cqw}} .sc span{{font-size:1.02cqw;color:var(--muted);line-height:1.45}}
.exs{{display:grid;grid-template-columns:1fr 1fr;gap:1.2cqw}} .ex{{background:var(--panel);border-radius:.8cqw;padding:1.6cqw;display:grid;grid-template-columns:1fr auto;gap:.6cqw 1cqw;align-items:center}}
.ex q{{font-size:1.45cqw;font-weight:600}} .ex em{{font-style:normal;color:#fff;font-weight:700;font-size:1.2cqw;padding:.35cqw 1cqw;border-radius:2cqw}} .ex span{{grid-column:1/3;font-size:1.1cqw;color:var(--muted)}}
.vs{{display:grid;grid-template-columns:1fr 1fr;gap:1.2cqw}} .vs .stat:last-child .big{{color:#{INST};font-size:2.1cqw}}
.flow{{display:grid;grid-template-columns:repeat(5,1fr);gap:.9cqw}} .fs{{background:var(--panel);border-radius:.8cqw;padding:1.4cqw 1.2cqw;position:relative}} .fs b{{display:block;font-size:1.3cqw;color:#{GREED};margin-bottom:.5cqw}} .fs span{{font-size:1.15cqw;line-height:1.45}}
.gts{{display:flex;gap:1.6cqw}} .gtw{{flex:1;min-width:0}} .two.g{{grid-template-columns:1.9fr 1fr;align-items:start}}
table.gt{{font-size:1.08cqw}} table.gt th,table.gt td{{padding:.55cqw .7cqw;border-bottom:1px solid var(--line)}} table.gt td:first-child{{color:var(--muted)}} table.gt td:last-child,table.gt th:last-child{{color:inherit;font-weight:inherit}} table.gt th:last-child{{color:var(--muted)}}
table.gt td{{font-weight:600}} table.gt.small{{font-size:.92cqw}} table.gt.small td,table.gt.small th{{padding:.32cqw .3cqw;text-align:center;border-bottom:1px solid #fff}} table.gt.small td:first-child{{text-align:left;font-weight:700}}
.abc{{display:grid;grid-template-columns:1fr 1.35fr;gap:1.4cqw}} .abl{{display:flex;flex-direction:column;gap:1.4cqw}} .abc h3{{color:#{GREED}}}
.found .fd{{margin-top:1.3cqw}} .found .fd b{{display:block;font-size:1.55cqw}} .found .fd span{{font-size:1.2cqw;color:var(--muted);line-height:1.45}}
.toc{{display:grid;grid-template-columns:repeat(3,1fr);gap:1.4cqw}} .tg{{background:var(--panel);border-radius:.8cqw;padding:1.8cqw}} .tg h3{{color:#{GREED}}}
.ti{{display:flex;justify-content:space-between;gap:1cqw;padding:.8cqw 0;border-bottom:1px solid var(--line);font-size:1.3cqw;line-height:1.4;font-weight:600}} .ti em{{font-style:normal;color:var(--muted);font-weight:400}}
@media (max-width:700px){{.deck{{padding:12px 0;gap:12px}}.slide{{border-radius:0}}}}
@media print{{*{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}body{{background:#fff}}.deck{{padding:0;gap:0}}.slide{{width:100%;box-shadow:none;border-radius:0;page-break-after:always}}.slide:last-child{{page-break-after:auto}}@page{{size:1280px 720px;margin:0}}}}
"""
desc = "토스증권 커뮤니티 글과 KRX 수급·주가로 만든 공포탐욕지수 발표 자료"
doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>토스증권 공포탐욕지수 발표</title><meta name="description" content="{desc}">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>{CSS}</style></head><body><main class="deck">{''.join(slide_html(i, s) for i, s in enumerate(S))}</main>
<script>/* ←·→ 또는 PageUp·PageDown으로 슬라이드 이동 */
(function(){{const sl=[...document.querySelectorAll('.slide')];let cur=0;
function go(n){{cur=Math.max(0,Math.min(sl.length-1,n));sl[cur].scrollIntoView({{behavior:'smooth',block:'center'}});}}
addEventListener('keydown',e=>{{if(['ArrowRight','PageDown',' '].includes(e.key)){{e.preventDefault();go(cur+1)}}if(['ArrowLeft','PageUp'].includes(e.key)){{e.preventDefault();go(cur-1)}}}});
const io=new IntersectionObserver(es=>es.forEach(x=>{{if(x.isIntersecting&&x.intersectionRatio>.6)cur=sl.indexOf(x.target)}}),{{threshold:.6}});sl.forEach(s=>io.observe(s));}})();</script>
</body></html>"""
open(os.path.join(HERE, OUT + ".html"), "w").write(doc)

print("ok", len(S), "slides")
