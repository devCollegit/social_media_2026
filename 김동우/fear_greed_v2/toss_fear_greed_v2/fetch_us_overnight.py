"""C1 통제 변수 us_overnight.csv 만들기. 한국 거래일마다 "그날 아침 9시 전까지 끝난 미국 장"의 수익률(%)을 붙인다.

미국 장은 한국 시각 새벽(05:00~06:00)에 끝나므로, 한국 거래일 d의 시가에 반영되는 것은 d 이전 날짜의 미국 종가다.
한국 휴장일 사이에 미국 장이 여러 번 열렸으면 그 사이 수익률을 모두 누적한다.
  us_ret(d) = 미국 종가(d 전 마지막 장) ÷ 미국 종가(직전 한국 거래일 전 마지막 장) − 1

자료: FRED(미국 세인트루이스 연방준비은행)의 일별 종가 CSV. 로그인·API 키가 필요 없다.
  SP500 (S&P 500), NASDAQCOM (나스닥 종합). FRED의 S&P 500은 최근 10년치만 제공된다.
출력 (--base): us_overnight.csv — date, us_ret(S&P 500), us_ret_ndx(나스닥). analysis_v2.py·predict_v2.py는 us_ret을 쓴다.
사용: python fetch_us_overnight.py --base <toss_fear_greed 폴더>   (trading_days.csv를 읽음)
     python fetch_us_overnight.py --base <폴더> --cache us_raw.csv     (받은 원자료를 저장해 두고 다시 씀)
"""
import argparse
import bisect
import io
import os
import time
import urllib.request

import pandas as pd

from common import load_trading_days

P = argparse.ArgumentParser()
P.add_argument("--base", required=True)
P.add_argument("--dest", default="", help="비우면 <base>/us_overnight.csv")
P.add_argument("--cache", default="", help="FRED 원자료를 이 파일에 저장하고, 있으면 다시 받지 않음")
A = P.parse_args()
SERIES = {"us_ret": "SP500", "us_ret_ndx": "NASDAQCOM"}


def fetch(sid):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    for k in range(3):                         # FRED가 가끔 늦게 응답해서 두 번 더 시도
        try:
            raw = urllib.request.urlopen(url, timeout=90).read().decode()
            break
        except OSError as e:
            if k == 2:
                raise SystemExit(f"{sid} 받기 실패: {e}. 잠시 뒤 다시 실행하세요")
            time.sleep(5)
    x = pd.read_csv(io.StringIO(raw))
    x.columns = ["date", "close"]
    x["close"] = pd.to_numeric(x.close, errors="coerce")       # 휴장일은 '.'로 와서 NaN이 된다
    return x.dropna().assign(series=sid)


if A.cache and os.path.exists(A.cache):
    raw = pd.read_csv(A.cache, dtype={"date": str})
else:
    raw = pd.concat([fetch(s) for s in SERIES.values()], ignore_index=True)
    if A.cache:
        raw.to_csv(A.cache, index=False)

td = load_trading_days(A.base)
out = pd.DataFrame({"date": td})
for col, sid in SERIES.items():
    x = raw[raw.series == sid].sort_values("date")
    dates, close = x.date.astype(str).tolist(), x.close.tolist()

    def last_before(d):                       # d보다 앞선 마지막 미국 장의 종가
        i = bisect.bisect_left(dates, d) - 1
        return close[i] if i >= 0 else None

    vals = []
    for k, d in enumerate(td):
        if k == 0:
            vals.append(None)
            continue
        a, b = last_before(td[k - 1]), last_before(d)
        vals.append(round((b / a - 1) * 100, 4) if a and b else None)
    out[col] = vals
dest = A.dest or os.path.join(A.base, "us_overnight.csv")
out.to_csv(dest, index=False)
ok = out.us_ret.notna()
print(f"{dest}: 거래일 {len(out):,}일 중 {ok.sum():,}일 채움 ({out.date[ok].min()}~{out.date[ok].max()}), "
      f"미국 장이 없던 날(0%) {int((out.us_ret[ok] == 0).sum())}일")
