"""KRX 로그인 필요 자료 (환경 변수 KRX_ID, KRX_PW). 파일에 계정 정보를 남기지 않는다.
출력: krx_index.json (코스피 1001·코스닥 2001 일봉), krx_investor.json (종목별 일별 투자자 순매수 대금), krx_short.json (종목별 공매도 거래량)"""
import json, sys, datetime as dt
from pykrx import stock
end = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y%m%d"); start = "20241001"
codes = [c for v in json.load(open("sectors.json")).values() for c in v]
idx = {}
for k, t in (("KOSPI", "1001"), ("KOSDAQ", "2001")):
    d = stock.get_index_ohlcv_by_date(start, end, t)
    idx[k] = {i.strftime("%Y-%m-%d"): [float(r["시가"]), float(r["고가"]), float(r["저가"]), float(r["종가"]), int(r["거래량"])] for i, r in d.iterrows()}
    print(k, len(idx[k]), flush=True)
json.dump(idx, open("krx_index.json", "w"))
inv, sht = {}, {}
for c in codes:
    d = stock.get_market_trading_value_by_date(start, end, c)            # 투자자별 순매수 대금(원)
    inv[c] = {i.strftime("%Y-%m-%d"): {k: int(v) for k, v in r.items()} for i, r in d.iterrows()}
    try:
        s = stock.get_shorting_volume_by_date(start, end, c)
        sht[c] = {i.strftime("%Y-%m-%d"): {k: float(v) for k, v in r.items()} for i, r in s.iterrows()}
    except Exception as e:
        sht[c] = {}; print("공매도 실패", c, type(e).__name__, flush=True)
    print(c, len(inv[c]), len(sht[c]), list(d.columns)[:6] if c == codes[0] else "", flush=True)
json.dump(inv, open("krx_investor.json", "w"), ensure_ascii=False)
json.dump(sht, open("krx_short.json", "w"), ensure_ascii=False)
