"""06. 병합.

일별 감성과 시장 자료를 거래일 기준으로 합쳐 분석용 패널을 만든다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import Config
from ..context import RunContext

NAME = "merge"
TITLE = "감성·시장 패널 구성"


def inputs(config: Config) -> list[Path]:
    return [
        config.data_path("interim", "daily_sentiment.csv"),
        config.data_path("interim", "market.csv"),
    ]


def outputs(config: Config) -> list[Path]:
    return [config.data_path("processed", "panel.csv")]


def run(ctx: RunContext) -> dict[str, Any]:
    cfg = ctx.config
    sentiment = ctx.read_table(inputs(cfg)[0], dtype={"stock_id": str})
    market = ctx.read_table(inputs(cfg)[1], dtype={"stock_id": str})

    for df in (sentiment, market):
        df["trading_date"] = pd.to_datetime(df["trading_date"])

    panel = market.merge(sentiment, on=["stock_id", "trading_date"], how="left")
    panel = panel.sort_values(["stock_id", "trading_date"]).reset_index(drop=True)

    panel["post_count"] = panel["post_count"].fillna(0).astype(int)
    panel["stock_name"] = panel["stock_id"].map(cfg.stock_names)

    grouped = panel.groupby("stock_id")
    panel["ret_next"] = grouped["ret"].shift(-1)
    panel["ret_prev"] = grouped["ret"].shift(1)
    panel["sentiment_prev"] = grouped["sentiment_index"].shift(1)
    panel["log_post_count"] = np.log(panel["post_count"] + 1)

    columns = [
        "stock_id", "stock_name", "trading_date",
        "positive_count", "neutral_count", "negative_count", "post_count",
        "log_post_count", "sentiment_index", "sentiment_prev", "is_sparse",
        "close", "volume", "log_volume", "volume_ratio",
        "ret", "ret_prev", "ret_next", "market_return",
    ]
    panel = panel[[c for c in columns if c in panel.columns]]
    ctx.write_table(panel, outputs(cfg)[0])

    coverage = (
        panel.groupby("stock_id")
        .agg(
            거래일수=("trading_date", "count"),
            감성관측일=("sentiment_index", lambda s: int(s.notna().sum())),
        )
        .assign(커버리지=lambda d: (d["감성관측일"] / d["거래일수"]).round(4))
        .reset_index()
    )
    ctx.write_table(coverage, cfg.output_path("tables", "06_감성_커버리지.csv"))

    low = coverage.loc[coverage["커버리지"] < 0.5, "stock_id"].tolist()
    if low:
        ctx.note(
            f"감성 관측 커버리지가 50% 미만인 종목: {', '.join(low)}. "
            "표본이 희박한 종목은 해석 범위를 제한하거나 분석 대상에서 제외하는 것을 검토한다."
        )

    return {
        "rows": int(len(panel)),
        "stocks": int(panel["stock_id"].nunique()),
        "sentiment_observed": int(panel["sentiment_index"].notna().sum()),
        "market_return_available": bool(panel.get("market_return", pd.Series(dtype=float)).notna().any()),
    }
