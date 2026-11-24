"""pykrx 일봉(로그인 없이 되는 것만): 45종목 + KODEX 200(069500)·코스닥150(229200). 거래일 달력은 삼성전자 일봉 날짜.
출력: ohlcv.json, closes.json, trading_days.csv"""
import json, datetime as dt
from pykrx import stock
end = (dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))).strftime("%Y%m%d")
codes = [c for v in json.load(open("sectors.json")).values() for c in v] + ["069500", "229200"]
out = {}
for c in codes:
    d = stock.get_market_ohlcv_by_date("20241001", end, c)
    out[c] = {i.strftime("%Y-%m-%d"): [int(r["시가"]), int(r["고가"]), int(r["저가"]), int(r["종가"]), int(r["거래량"])] for i, r in d.iterrows()}
json.dump(out, open("ohlcv.json", "w"))
json.dump({c: {d: v[3] for d, v in x.items()} for c, x in out.items()}, open("closes.json", "w"))
days = sorted(out["005930"])
open("trading_days.csv", "w").write("date\n" + "\n".join(days) + "\n")
print("거래일", len(days), days[-1])
