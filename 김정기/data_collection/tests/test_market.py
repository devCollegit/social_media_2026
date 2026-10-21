"""합성 응답만 사용하며 실제 인증 파일과 네트워크에 접근하지 않는다."""

import argparse
import logging
import socket
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

import settings
from market import cli, sources


@pytest.fixture
def providers(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("오프라인 테스트에서 네트워크 접근 금지")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(sources, "load_krx_env", lambda: None)
    monkeypatch.setattr(sources.Throttle, "wait", lambda self: None)
    stock = SimpleNamespace(
        get_market_ohlcv=Mock(side_effect=AssertionError("예상하지 않은 OHLCV 요청")),
        get_market_cap=Mock(side_effect=AssertionError("예상하지 않은 시총 요청")),
        get_market_sector_classifications=Mock(),
    )
    fdr = SimpleNamespace(StockListing=Mock(), DataReader=Mock())
    monkeypatch.setitem(sys.modules, "pykrx", SimpleNamespace(stock=stock))
    monkeypatch.setitem(sys.modules, "FinanceDataReader", fdr)
    monkeypatch.setattr(settings, "setup_logging", lambda *args: logging.getLogger("test_market"))
    return stock, fdr


def ohlcv():
    return pd.DataFrame(
        {"시가": [100, 102], "고가": [105, 103], "저가": [99, 98],
         "종가": [102, 100], "거래량": [10, 20], "등락률": [2.0, -1.96]},
        index=pd.to_datetime(["2026-07-01", "2026-07-02"]),
    )


@pytest.mark.parametrize("use_krx", [True, False])
def test_stock_daily_schema_returns_and_date_join(providers, use_krx):
    stock, _ = providers
    stock.get_market_ohlcv.side_effect = None
    stock.get_market_ohlcv.return_value = ohlcv()
    stock.get_market_cap.side_effect = None
    # 날짜 순서가 달라도 행 위치가 아닌 날짜로 결합해야 한다.
    stock.get_market_cap.return_value = pd.DataFrame(
        {"거래대금": [2000, 1020], "시가총액": [10000, 10200], "상장주식수": [100, 100]},
        index=pd.to_datetime(["2026-07-02", "2026-07-01"]),
    )
    result = sources.MarketSource(use_krx=use_krx).stock_daily("005930", "2026-07-01", "2026-07-02")
    assert set(result.columns) == set(cli.STOCK_COLUMNS)
    assert result.date.tolist() == ["2026-07-01", "2026-07-02"]
    assert result.close.tolist() == [102, 100]
    assert result.change.tolist() == pytest.approx([0.02, -0.0196])
    stock.get_market_ohlcv.assert_called_once_with("20260701", "20260702", "005930", adjusted=True)
    if use_krx:
        assert result.value.tolist() == [1020, 2000]
        assert result.market_cap.tolist() == [10200, 10000]
        assert result.shares.tolist() == [100, 100]
    else:
        stock.get_market_cap.assert_not_called()
        assert result[["value", "market_cap", "shares"]].isna().all().all()


@pytest.mark.parametrize("empty", [None, pd.DataFrame()])
def test_stock_daily_rejects_missing_prices(providers, empty):
    stock, _ = providers
    stock.get_market_ohlcv.side_effect = None
    stock.get_market_ohlcv.return_value = empty
    with pytest.raises(ValueError, match="OHLCV 가 비어"):
        sources.MarketSource(use_krx=True).stock_daily("005930", "2026-07-01", "2026-07-02")
    stock.get_market_cap.assert_not_called()


@pytest.mark.parametrize("use_krx", [True, False])
def test_master_normalizes_market_and_preserves_codes(providers, use_krx):
    stock, fdr = providers
    listing = pd.DataFrame({
        "Code": ["005930", "000010"], "ISU_CD": ["KR7005930003", "SYNTHETIC"],
        "Name": ["삼성전자", "합성보통주"], "Market": ["KOSPI", "KOSDAQ GLOBAL"],
        "Dept": ["", "우량기업부"], "Marcap": [1000, 500], "Stocks": [100, 50], "Amount": [100, 50],
    })
    desc = pd.DataFrame({"Code": ["000010", "005930"], "Industry": ["합성업종", "전자"],
                         "ListingDate": ["2000-01-01", "1975-06-11"]})
    fdr.StockListing.side_effect = lambda kind: {"KRX": listing, "KRX-DESC": desc}[kind].copy()
    stock.get_market_sector_classifications.side_effect = lambda day, market: pd.DataFrame(
        {"업종명": ["전기·전자" if market == "KOSPI" else "IT 서비스"]},
        index=pd.Index(["005930" if market == "KOSPI" else "000010"], name="종목코드"),
    )
    result = sources.MarketSource(use_krx=use_krx).stock_master(as_of="2026-10-20").set_index("stock_id")
    assert result.index.tolist() == ["000010", "005930"]
    assert result.loc["000010", "market"] == "KOSDAQ"
    assert result.loc["005930", "isin"] == "KR7005930003"
    assert result.loc["005930", "industry"] == "전자"
    if use_krx:
        assert result.loc["000010", "krx_sector"] == "IT 서비스"
        assert result.loc["005930", "krx_sector"] == "전기·전자"
    else:
        assert result.krx_sector.isna().all()
        stock.get_market_sector_classifications.assert_not_called()


@pytest.mark.parametrize("top,expected", [(10, ["000010", "005930"]), (1, ["000010"])])
def test_candidates_filters_and_limits_output(providers, tmp_path, top, expected):
    entries = [
        ("005930", "보통주", "KOSPI", 100),
        ("000010", "합성코스닥", "KOSDAQ GLOBAL", 200),
        ("005935", "우선주", "KOSPI", 900),
        ("000020", "합성스팩", "KOSDAQ", 900),
        ("000030", "합성리츠", "KOSPI", 900),
        ("000040", "합성ETN", "KOSPI", 900),
        ("000050", "합성코넥스", "KONEX", 900),
    ]
    master = pd.DataFrame([
        {"stock_id": code, "name": name, "market": market, "isin": "SYNTHETIC" + code,
         "industry": "합성", "value_snapshot": rank, "market_cap_snapshot": rank,
         "snapshot_date": "2026-10-20"}
        for code, name, market, rank in entries
    ])
    master.to_csv(tmp_path / "stock_master.csv", index=False)
    cfg = settings.Settings(raw={"paths": {"meta_dir": "."}}, base=tmp_path)
    assert cli.cmd_candidates(argparse.Namespace(top=top), cfg) == 0
    result = pd.read_csv(tmp_path / "candidates.csv", dtype=str)
    assert result.stock_id.tolist() == expected
    assert result.loc[0, "market"] == "KOSDAQ"
    assert result.columns.tolist() == ["stock_id", "isin", "name", "market", "industry",
                                       "market_cap_snapshot", "value_snapshot", "snapshot_date"]


def test_provider_credentials_are_not_printed_or_in_exceptions(providers, capsys):
    stock, _ = providers
    def unsafe_provider(*args, **kwargs):
        print("dummy-login-id")
        print("dummy-password", file=sys.stderr)
        raise ValueError("dummy-login-id dummy-password")
    stock.get_market_ohlcv.side_effect = unsafe_provider
    src = sources.MarketSource(use_krx=True)
    with pytest.raises(RuntimeError) as error:
        src.stock_daily("005930", "2026-07-01", "2026-07-02")
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert "dummy" not in str(error.value)
    assert "ValueError" in str(error.value)


def test_provider_import_output_is_suppressed(providers, monkeypatch, capsys):
    import builtins
    original = builtins.__import__
    def noisy_import(name, *args, **kwargs):
        if name == "pykrx":
            print("dummy-login-id")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", noisy_import)
    sources.MarketSource(use_krx=False)
    assert capsys.readouterr().out == ""
