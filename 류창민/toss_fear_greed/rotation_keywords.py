"""섹터 · 분기별 토론글 대표 단어. 입력: 표본 글(sample_prev12_clean.json, sample_30k_clean.json: 종목·월마다 같은 수로 뽑은 글 약 5.8만 건).
명사만 뽑아(kiwipiepy), 같은 섹터의 다른 분기·다른 섹터 글과 비교해 그 섹터·분기에 유독 많이 나온 단어를 고른다(로그 오즈, 정보 사전분포).
원문은 저장하지 않고 단어와 빈도만 남긴다. 출력: rotation_keywords.json
사용: uv run --python 3.10 --with kiwipiepy python rotation_keywords.py"""
import json, math, os, re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from kiwipiepy import Kiwi

os.chdir(os.path.dirname(os.path.abspath(__file__)))
S = json.load(open("sectors.json"))
names = {n for v in S.values() for n in v.values()}
STOP = set("""주식 종목 오늘 내일 어제 지금 사람 형님 형들 개미 주주 생각 진짜 정말 그냥 이거 저거 여기 거기 우리 하나 때문 정도 이번 다음 시간 보고 얘기 말씀 글 댓글 질문 답변 분들 님들 놈들 새끼 시발 씨발 ㅋㅋ ㅎㅎ
주가 가격 매수 매도 수익 손실 손절 익절 상승 하락 급등 급락 존버 물타기 불타기 평단 장투 단타 차트 시장 코스피 코스닥 투자 투자자 거래 거래량 시가 종가 장중 오후 오전 아침 저녁 하루 이틀 내년 올해 작년 이후 이전 계속 다시 처음 마지막
사용자 감사 가즈 가즈아 탈출 마이너스 진입 조정 시작 이상 가능 얼마 동안 기관 외인 외인들 외국인 외국 개인 국장 미장 성투 금일 세력 반등 호재 악재 축하 요약 조금 정리 고민 소리 자리 그때 기회 본전 정신 이제 초반 예상 손해 대기 공부 다행 짜증 고고 깡통 인내 횡보 추세 고점 바닥 나락 장난 기준 대비 확인 참고 나머지 평가 가치 흐름 최고 성공 구매 판매 목표 고수 대장 잡주 하한 상한 장기 월요일 금요일 추천 욕심 줄먹 선장 이슈 소식 전망 기대 걱정 불안 반대 전환 나라 한국 이익 영향 증가 신규 관심 예정 발표 반영 사업 매출 실적 회사 기업 증권 토스 사이트 뉴스 기사 링크 사진 영상 유튜브 정보 내용 이유 문제 상황 결과 기분 마음 느낌 위 아래 쪽 번 개 원 만원 억 조 프로 퍼 퍼센트 배 주 년 월 일 분 초 달 해 날 때 것 수 등 중 전 후 안 밖 속 끝 뭐 왜 거 게 건 데 듯 줄 만 놈 분""".split())
ALIAS = set("윤석열 삼스디 스디 두빌 현일 현중 삼중 한오 현건 지건 동진이 주성이 철주 우기 삼전기 연진 대머리 불사조 삼전 하닉 하이닉스 에코프로 엘지 현차 엘지엔솔 엘엔솔 엔솔 두에빌 두산 한화 현대 삼성 에이치디 셀트 네이버 카카오 효성 대우 레인보우 로보 한미 주성 이수 리노 심텍 후성 기아 모비스 알테 삼천당 테오젠 에너빌리티 오션 중공업 일렉 시스템 에어로 로템 우리기술 한전 기술 전기 이노텍 콘덴서 쎄미켐 스퀘어 하이 닉스 전자 건설 화학".split())
kiwi = Kiwi()
def quarter(ts):
    t = datetime.fromisoformat(ts) + timedelta(hours=9)
    return f"{t.year}Q{(t.month - 1) // 3 + 1}"
cnt = defaultdict(Counter); docs = Counter()
rows = json.load(open("sample_prev12_clean.json")) + json.load(open("sample_30k_clean.json"))
texts = [(quarter(r["published_at"]), r["sector"], re.sub(r"#\[[^\]]*\]\(\d+\)|https?://\S+", " ", r.get("text") or "")) for r in rows]
for (q, s, t), toks in zip(texts, kiwi.tokenize([t for _, _, t in texts], normalize_coda=True)):
    seen = set()
    for tk in toks:
        if tk.tag not in ("NNG", "NNP", "SL"): continue
        w = tk.form.upper() if tk.tag == "SL" else tk.form
        if len(w) < 2 or w in STOP or w in ALIAS or any(w in n or n in w for n in names): continue
        seen.add(w)
    for w in seen: cnt[(q, s)][w] += 1           # 글 단위로 한 번만 센다
    docs[(q, s)] += 1
tot = Counter(); [tot.update(c) for c in cnt.values()]
N = sum(tot.values()); A = 0.01 * N                 # 사전분포 크기
out = {}
for key, c in cnt.items():
    n = sum(c.values()); rest = {w: tot[w] - c[w] for w in c}; nr = N - n
    sc = []
    for w, k in c.items():
        if k < 5: continue
        a = A * tot[w] / N
        d = math.log((k + a) / (n + A - k - a)) - math.log((rest[w] + a) / (nr + A - rest[w] - a))
        v = 1 / (k + a) + 1 / (rest[w] + a)
        sc.append((d / math.sqrt(v), w, k))
    sc.sort(reverse=True)
    out[f"{key[0]}|{key[1]}"] = {"posts": docs[key], "words": [(w, k) for _, w, k in sc[:8]]}
json.dump(out, open("rotation_keywords.json", "w"), ensure_ascii=False, indent=1)
for k in sorted(out)[:400]:
    if out[k]["posts"] >= 100: print(k, out[k]["posts"], [w for w, _ in out[k]["words"][:6]])
