"""시세 데이터 소스.

pykrx 1.2.x 는 KRX 정보데이터시스템 로그인(환경변수 KRX_ID / KRX_PW)이 있어야
거래대금·시가총액·상장주식수·지수·업종을 돌려준다. 로그인이 없을 때 동작하는 것은
수정주가 OHLCV(네이버 경유)뿐이다. 그래서 로그인 여부에 따라 소스를 나눈다.

| 항목                   | KRX 로그인 O        | KRX 로그인 X                     |
| ---------------------- | ------------------- | -------------------------------- |
| 수정주가 OHLCV         | pykrx               | pykrx                            |
| 거래대금·시총·주식수   | pykrx               | 비움 (마스터에 현재 스냅샷만)     |
| KOSPI·KOSDAQ 지수      | pykrx               | FinanceDataReader (KS11, KQ11)   |
| 종목 마스터·ISIN·업종  | FDR + pykrx 업종명  | FDR (KSIC 업종)                  |
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date

import pandas as pd

log = logging.getLogger("market")

INDEX_CODES = {"KOSPI": ("1001", "KS11"), "KOSDAQ": ("2001", "KQ11")}


def krx_login_available() -> bool:
    return bool(os.getenv("KRX_ID")) and bool(os.getenv("KRX_PW"))


def _ymd(d: str) -> str:
    return d.replace("-", "")


class Throttle:
    """연속 호출 사이에 최소 간격을 둔다."""

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self._last = 0.0

    def wait(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.interval:
            time.sleep(self.interval - gap)
        self._last = time.monotonic()


class MarketSource:
    def __init__(self, interval: float = 1.0, use_krx: bool | None = None) -> None:
        self.throttle = Throttle(interval)
        self.use_krx = krx_login_available() if use_krx is None else use_krx
        from pykrx import stock  # import 시점에 KRX 로그인을 시도하므로 여기서 불러온다

        self._stock = stock

    # ------------------------------------------------------------------ 종목 일봉
    def stock_daily(self, code: str, start: str, end: str) -> pd.DataFrame:
        """date, open, high, low, close(수정주가), volume, change, value, market_cap, shares."""
        self.throttle.wait()
        ohlcv = self._stock.get_market_ohlcv(_ymd(start), _ymd(end), code, adjusted=True)
        if ohlcv is None or ohlcv.empty:
            raise ValueError(f"{code}: OHLCV 가 비어 있습니다 ({start}~{end}).")
        df = ohlcv.rename(
            columns={"시가": "open", "고가": "high", "저가": "low", "종가": "close",
                     "거래량": "volume", "등락률": "change"}
        )
        df.index.name = "date"
        df = df.reset_index()[["date", "open", "high", "low", "close", "volume", "change"]]
        # pykrx 수정주가 등락률은 % 단위다. 소수로 맞춘다.
        df["change"] = df["change"] / 100.0

        cap = self._market_cap(code, start, end) if self.use_krx else None
        if cap is not None and not cap.empty:
            df = df.merge(cap, on="date", how="left")
        else:
            df["value"] = pd.NA
            df["market_cap"] = pd.NA
            df["shares"] = pd.NA
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return df

    def _market_cap(self, code: str, start: str, end: str) -> pd.DataFrame | None:
        self.throttle.wait()
        cap = self._stock.get_market_cap(_ymd(start), _ymd(end), code)
        if cap is None or cap.empty:
            log.warning("%s: 시가총액 조회 결과가 비었습니다. KRX 로그인 상태를 확인하세요.", code)
            return None
        cap = cap.rename(columns={"거래대금": "value", "시가총액": "market_cap", "상장주식수": "shares"})
        cap.index.name = "date"
        return cap.reset_index()[["date", "value", "market_cap", "shares"]]

    # ------------------------------------------------------------------ 지수
    def index_daily(self, start: str, end: str) -> pd.DataFrame:
        """date, kospi_close, kospi_volume, kospi_value, kosdaq_close, kosdaq_volume, kosdaq_value."""
        frames = []
        for name, (krx_code, fdr_code) in INDEX_CODES.items():
            df = self._index_krx(krx_code, start, end) if self.use_krx else None
            if df is None or df.empty:
                df = self._index_fdr(fdr_code, start, end)
            prefix = name.lower()
            df = df.rename(columns={c: f"{prefix}_{c}" for c in df.columns if c != "date"})
            frames.append(df.set_index("date"))
        out = pd.concat(frames, axis=1).reset_index()
        out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
        return out.sort_values("date").reset_index(drop=True)

    def _index_krx(self, code: str, start: str, end: str) -> pd.DataFrame | None:
        self.throttle.wait()
        try:
            raw = self._stock.get_index_ohlcv(_ymd(start), _ymd(end), code)
        except Exception as exc:  # pykrx 는 실패 시 KeyError 등을 던진다
            log.warning("pykrx 지수 %s 조회 실패, FDR 로 대체: %s", code, exc)
            return None
        raw = raw.rename(columns={"종가": "close", "거래량": "volume", "거래대금": "value"})
        raw.index.name = "date"
        return raw.reset_index()[["date", "close", "volume", "value"]]

    def _index_fdr(self, code: str, start: str, end: str) -> pd.DataFrame:
        import FinanceDataReader as fdr

        self.throttle.wait()
        raw = fdr.DataReader(code, start, end)
        raw = raw.rename(columns={"Close": "close", "Volume": "volume", "Amount": "value"})
        raw.index.name = "date"
        return raw.reset_index()[["date", "close", "volume", "value"]]

    # ------------------------------------------------------------------ 종목 마스터
    def stock_master(self, as_of: str | None = None) -> pd.DataFrame:
        """stock_id, isin, name, market, industry, krx_sector, dept, listing_date,
        market_cap_snapshot, shares_snapshot, value_snapshot, snapshot_date.

        isin 은 토스증권 커뮤니티의 종목 식별자(subjectId)와 같은 값이다.
        *_snapshot 컬럼은 조회 시점의 값이며 과거 일자별 값이 아니다.
        """
        import FinanceDataReader as fdr

        self.throttle.wait()
        listing = fdr.StockListing("KRX")
        self.throttle.wait()
        desc = fdr.StockListing("KRX-DESC")

        df = listing.rename(
            columns={"Code": "stock_id", "ISU_CD": "isin", "Name": "name", "Market": "market",
                     "Dept": "dept", "Marcap": "market_cap_snapshot", "Stocks": "shares_snapshot",
                     "Amount": "value_snapshot"}
        )[["stock_id", "isin", "name", "market", "dept", "market_cap_snapshot",
           "shares_snapshot", "value_snapshot"]]
        desc = desc.rename(
            columns={"Code": "stock_id", "Industry": "industry", "ListingDate": "listing_date"}
        )[["stock_id", "industry", "listing_date"]]
        df = df.merge(desc, on="stock_id", how="left")
        # 'KOSDAQ GLOBAL'(코스닥 우량주 구분)은 시장 지수 매칭을 위해 KOSDAQ 으로 합친다.
        df["market"] = df["market"].replace({"KOSDAQ GLOBAL": "KOSDAQ"})

        df["krx_sector"] = pd.NA
        if self.use_krx:
            sectors = self._krx_sectors(as_of or date.today().isoformat())
            if sectors is not None:
                df = df.drop(columns="krx_sector").merge(sectors, on="stock_id", how="left")

        df["snapshot_date"] = date.today().isoformat()
        cols = ["stock_id", "isin", "name", "market", "industry", "krx_sector", "dept", "listing_date",
                "market_cap_snapshot", "shares_snapshot", "value_snapshot", "snapshot_date"]
        return df[cols].sort_values("stock_id").reset_index(drop=True)

    def _krx_sectors(self, as_of: str) -> pd.DataFrame | None:
        frames = []
        for market in ("KOSPI", "KOSDAQ"):
            self.throttle.wait()
            try:
                raw = self._stock.get_market_sector_classifications(_ymd(as_of), market)
            except Exception as exc:
                log.warning("pykrx 업종 분류(%s) 조회 실패: %s", market, exc)
                return None
            raw = raw.reset_index()
            code_col = "종목코드" if "종목코드" in raw.columns else raw.columns[0]
            frames.append(raw.rename(columns={code_col: "stock_id", "업종명": "krx_sector"})[
                ["stock_id", "krx_sector"]])
        return pd.concat(frames, ignore_index=True)
