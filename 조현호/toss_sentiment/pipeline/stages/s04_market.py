"""04. 시장 자료 확보.

수정주가·거래량과 시장 지수를 확보하고 거래일 달력을 만든다.
이후 집계 단계가 이 거래일 달력을 기준으로 글을 배정한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import Config
from ..context import RunContext, StageError

NAME = "market"
TITLE = "수정주가·거래량·시장지수 확보"


def inputs(config: Config) -> list[Path]:
    if config.get("market.source") == "csv":
        input_dir = config.resolve(config.get("market.input_dir", "data/raw/market"))
        return sorted(input_dir.glob("*.csv")) if input_dir.exists() else []
    return [config.data_path("raw", "posts.csv")]


def outputs(config: Config) -> list[Path]:
    return [config.data_path("interim", "market.csv")]


def run(ctx: RunContext) -> dict[str, Any]:
    source = ctx.config.get("market.source", "csv")
    if source == "csv":
        df = _from_csv(ctx)
    elif source == "fdr":
        df = _from_fdr(ctx)
    elif source == "sample":
        df = _sample(ctx)
    else:
        raise StageError(f"market.source '{source}' 을 지원하지 않습니다. csv, fdr, sample 중 하나.")

    df = _derive(df)
    ctx.write_table(df, outputs(ctx.config)[0])

    return {
        "source": source,
        "rows": int(len(df)),
        "stocks": int(df["stock_id"].nunique()),
        "trading_days": int(df["trading_date"].nunique()),
        "date_min": str(df["trading_date"].min()),
        "date_max": str(df["trading_date"].max()),
    }


def _derive(df: pd.DataFrame) -> pd.DataFrame:
    """수익률과 거래량 지표를 계산한다."""
    df = df.copy()
    df["trading_date"] = pd.to_datetime(df["trading_date"]).dt.date
    df = df.sort_values(["stock_id", "trading_date"]).reset_index(drop=True)

    # 수익률은 수정주가의 로그 변화로 계산한다(원고 03장).
    df["ret"] = df.groupby("stock_id")["close"].transform(lambda s: np.log(s).diff())
    df["log_volume"] = np.log(df["volume"].clip(lower=1))
    # 평소 대비 거래량 비율. 20거래일 이동 중앙값을 기준으로 본다.
    median20 = df.groupby("stock_id")["volume"].transform(
        lambda s: s.rolling(20, min_periods=5).median()
    )
    df["volume_ratio"] = df["volume"] / median20

    if "market_close" in df.columns:
        idx = df[["trading_date", "market_close"]].drop_duplicates().sort_values("trading_date")
        idx["market_return"] = np.log(idx["market_close"]).diff()
        df = df.drop(columns=["market_close"]).merge(
            idx[["trading_date", "market_return"]], on="trading_date", how="left"
        )
    elif "market_return" not in df.columns:
        df["market_return"] = np.nan
    return df


def _from_csv(ctx: RunContext) -> pd.DataFrame:
    cfg = ctx.config
    input_dir = cfg.resolve(cfg.get("market.input_dir", "data/raw/market"))
    price_col = cfg.get("market.price_column", "close")
    volume_col = cfg.get("market.volume_column", "volume")

    index_path = input_dir / "index.csv"
    index_df = None
    if index_path.exists():
        index_df = pd.read_csv(index_path)
        index_df = index_df.rename(
            columns={"date": "trading_date", price_col: "market_close"}
        )[["trading_date", "market_close"]]
    else:
        ctx.note(
            f"{ctx.rel(index_path)} 가 없어 시장 수익률을 통제 변수로 사용할 수 없다. "
            "회귀에서 시장 통제 변수가 빠진 점을 보고서에 기록한다."
        )

    frames = []
    for stock_id in cfg.stock_ids:
        path = input_dir / f"{stock_id}.csv"
        if not path.exists():
            raise StageError(
                f"{ctx.rel(path)} 가 없습니다.\n"
                f"  필요한 컬럼: date, {price_col}, {volume_col}\n"
                f"  자동 수집을 원하면 market.source 를 fdr 로 바꾸고 FinanceDataReader 를 설치하세요."
            )
        raw = pd.read_csv(path)
        raw = raw.rename(
            columns={"date": "trading_date", price_col: "close", volume_col: "volume"}
        )
        missing = [c for c in ["trading_date", "close", "volume"] if c not in raw.columns]
        if missing:
            raise StageError(f"{ctx.rel(path)} 에 컬럼이 없습니다: {', '.join(missing)}")
        raw["stock_id"] = stock_id
        frames.append(raw[["stock_id", "trading_date", "close", "volume"]])

    df = pd.concat(frames, ignore_index=True)
    if index_df is not None:
        df = df.merge(index_df, on="trading_date", how="left")
    return _clip_period(ctx, df)


def _from_fdr(ctx: RunContext) -> pd.DataFrame:
    try:
        import FinanceDataReader as fdr
    except ImportError as exc:
        raise StageError(
            "market.source=fdr 은 FinanceDataReader 설치가 필요합니다.\n"
            "  pip install finance-datareader"
        ) from exc

    cfg = ctx.config
    start, end = cfg.require("scope.start_date"), cfg.require("scope.end_date")
    frames = []
    for stock_id in cfg.stock_ids:
        raw = fdr.DataReader(stock_id, start, end).reset_index()
        raw.columns = [str(c).lower() for c in raw.columns]
        raw = raw.rename(columns={"date": "trading_date"})
        raw["stock_id"] = stock_id
        frames.append(raw[["stock_id", "trading_date", "close", "volume"]])

    df = pd.concat(frames, ignore_index=True)
    index_name = cfg.get("scope.market_index", "KS11")
    symbol = {"KOSPI": "KS11", "KOSDAQ": "KQ11"}.get(str(index_name).upper(), index_name)
    idx = fdr.DataReader(symbol, start, end).reset_index()
    idx.columns = [str(c).lower() for c in idx.columns]
    idx = idx.rename(columns={"date": "trading_date", "close": "market_close"})
    return df.merge(idx[["trading_date", "market_close"]], on="trading_date", how="left")


def _sample(ctx: RunContext) -> pd.DataFrame:
    """파이프라인 점검용 합성 시세.

    수집 단계의 합성 글에서 얻은 일별 분위기를 다음 거래일 수익률에 약하게 반영한다.
    분석 단계가 선행 관계를 실제로 탐지하는지 확인하기 위한 장치이며 실제 시세가 아니다.
    """
    ctx.note(
        "market.source=sample 로 실행했다. 합성 시세이므로 수익률·거래량 수치는 "
        "연구 결과가 아니라 파이프라인 동작 점검 결과다."
    )
    cfg = ctx.config
    rng = np.random.default_rng(int(cfg.get("collect.sample.seed", 20261006)) + 7)

    days = pd.bdate_range(cfg.require("scope.start_date"), cfg.require("scope.end_date"))
    mood = _daily_mood(ctx, days)

    market_shock = rng.normal(0, 0.009, len(days))
    market_close = 2500 * np.exp(np.cumsum(market_shock))

    frames = []
    for stock_id in cfg.stock_ids:
        m = mood.get(stock_id, pd.Series(0.0, index=days)).reindex(days).fillna(0.0).to_numpy()
        # 전일 분위기가 당일 수익률을 약하게 설명하도록 한 거래일 시프트한다.
        lead = np.concatenate([[0.0], m[:-1]])
        ret = 0.9 * market_shock + 0.02 * lead + rng.normal(0, 0.010, len(days))
        close = 60000 * np.exp(np.cumsum(ret))
        volume = (8_000_000 * np.exp(rng.normal(0, 0.3, len(days)) + 0.8 * np.abs(ret) * 10)).round()
        frames.append(
            pd.DataFrame(
                {
                    "stock_id": stock_id,
                    "trading_date": days,
                    "close": close.round(0),
                    "volume": volume,
                    "market_close": market_close.round(2),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def _daily_mood(ctx: RunContext, days: pd.DatetimeIndex) -> dict[str, pd.Series]:
    """합성 시세에 반영할 일별 분위기를 수집 결과에서 거칠게 추정한다."""
    posts_path = ctx.config.data_path("raw", "posts.csv")
    if not posts_path.exists():
        return {}
    posts = pd.read_csv(posts_path, dtype={"stock_id": str}, usecols=["stock_id", "text", "created_at"])
    posts["day"] = pd.to_datetime(posts["created_at"]).dt.normalize()
    positive_hint = posts["text"].str.contains("상승|반등|매수|수익|우상향|기대", na=False)
    negative_hint = posts["text"].str.contains("하락|손절|물렸|손실|부진|빠질", na=False)
    posts["hint"] = positive_hint.astype(int) - negative_hint.astype(int)
    grouped = posts.groupby(["stock_id", "day"])["hint"].mean()
    return {sid: grouped.loc[sid].reindex(days).ffill().fillna(0.0) for sid in grouped.index.levels[0]}


def _clip_period(ctx: RunContext, df: pd.DataFrame) -> pd.DataFrame:
    start = str(ctx.config.require("scope.start_date"))
    end = str(ctx.config.require("scope.end_date"))
    dates = pd.to_datetime(df["trading_date"])
    return df.loc[(dates >= start) & (dates <= end)].copy()
