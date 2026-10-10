"""05. 거래일 단위 집계.

원고 02장의 시간 기준을 구현한다.
  집계 구간 = 직전 거래일 종가 이후 ~ 당일 종가
  비거래일 글은 다음 거래일에 배정한다.
  글이 없는 날의 감성은 0이 아니라 결측으로 둔다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import Config
from ..context import RunContext, StageError

NAME = "aggregate"
TITLE = "거래일 정렬과 감성 지수 산출"


def inputs(config: Config) -> list[Path]:
    return [
        config.data_path("interim", "posts_scored.csv"),
        config.data_path("interim", "market.csv"),
    ]


def outputs(config: Config) -> list[Path]:
    return [config.data_path("interim", "daily_sentiment.csv")]


def run(ctx: RunContext) -> dict[str, Any]:
    cfg = ctx.config
    posts = ctx.read_table(inputs(cfg)[0], dtype={"stock_id": str, "post_id": str})
    market = ctx.read_table(inputs(cfg)[1], dtype={"stock_id": str})

    if not cfg.get("aggregate.include_comments", True):
        before = len(posts)
        posts = posts[posts["parent_id"].isna()].copy()
        ctx.logger.info("      댓글 제외: %d → %d행", before, len(posts))

    posts["created_at"] = pd.to_datetime(posts["created_at"])
    market["trading_date"] = pd.to_datetime(market["trading_date"])

    close_time = str(cfg.get("aggregate.market_close", "15:30"))
    min_posts = int(cfg.get("aggregate.min_posts", 5))

    frames = []
    unassigned_total = 0
    for stock_id, group in posts.groupby("stock_id"):
        calendar = market.loc[market["stock_id"] == stock_id, "trading_date"].sort_values()
        if calendar.empty:
            ctx.note(f"종목 {stock_id} 의 시장 자료가 없어 집계에서 제외했다.")
            continue
        assigned, unassigned = _assign_trading_date(group, calendar, close_time)
        unassigned_total += unassigned
        frames.append(_aggregate_one(stock_id, assigned, calendar, min_posts))

    if not frames:
        raise StageError("집계할 수 있는 종목이 없습니다. 수집 결과와 시장 자료의 종목·기간을 확인하세요.")

    daily = pd.concat(frames, ignore_index=True)
    ctx.write_table(daily, outputs(cfg)[0])

    sparse = int((daily["post_count"] < min_posts).sum())
    if sparse:
        ctx.note(
            f"글 수가 {min_posts}건 미만인 거래일 {sparse}일의 감성 지수를 결측으로 처리했다. "
            "최소 글 수 기준을 바꾼 민감도 분석 결과를 함께 보고한다."
        )
    if unassigned_total:
        ctx.note(
            f"마지막 거래일 이후에 작성되어 배정할 거래일이 없는 글 {unassigned_total}건을 제외했다."
        )

    return {
        "rows": int(len(daily)),
        "stocks": int(daily["stock_id"].nunique()),
        "sparse_days": sparse,
        "missing_sentiment_rate": round(float(daily["sentiment_index"].isna().mean()), 4),
        "unassigned_posts": unassigned_total,
    }


def _assign_trading_date(
    group: pd.DataFrame, calendar: pd.Series, close_time: str
) -> tuple[pd.DataFrame, int]:
    """각 글을 "직전 거래일 종가 이후 ~ 당일 종가" 구간의 거래일에 배정한다."""
    hour, minute = (int(x) for x in close_time.split(":"))
    close_stamps = calendar.dt.normalize() + pd.Timedelta(hours=hour, minutes=minute)
    close_stamps = close_stamps.sort_values().reset_index(drop=True)
    trading_dates = calendar.sort_values().reset_index(drop=True)

    # 종가 시각보다 뒤에 작성된 글은 다음 거래일 구간에 들어간다.
    idx = np.searchsorted(close_stamps.to_numpy(), group["created_at"].to_numpy(), side="left")
    valid = idx < len(trading_dates)

    assigned = group.loc[valid].copy()
    assigned["trading_date"] = trading_dates.to_numpy()[idx[valid]]
    return assigned, int((~valid).sum())


def _aggregate_one(
    stock_id: str, assigned: pd.DataFrame, calendar: pd.Series, min_posts: int
) -> pd.DataFrame:
    counts = (
        assigned.pivot_table(
            index="trading_date", columns="sentiment", values="post_id", aggfunc="count"
        )
        .reindex(columns=["긍정", "중립", "부정"], fill_value=0)
        .fillna(0)
    )
    counts.columns = ["positive_count", "neutral_count", "negative_count"]

    # 글이 하나도 없는 거래일도 행으로 남긴다(글 수 0, 감성 결측).
    frame = counts.reindex(calendar.sort_values().to_numpy(), fill_value=0).rename_axis(
        "trading_date"
    ).reset_index()
    frame["stock_id"] = stock_id
    frame["post_count"] = (
        frame["positive_count"] + frame["neutral_count"] + frame["negative_count"]
    )

    # 일별 감성 지수 S = (긍정 - 부정) / 전체 분류 글 수. 중립을 분모에 포함한다.
    with np.errstate(invalid="ignore", divide="ignore"):
        frame["sentiment_index"] = (
            frame["positive_count"] - frame["negative_count"]
        ) / frame["post_count"].replace(0, np.nan)

    # 글 수가 기준에 못 미치는 날은 0이 아니라 결측으로 둔다.
    frame.loc[frame["post_count"] < min_posts, "sentiment_index"] = np.nan
    frame["is_sparse"] = frame["post_count"] < min_posts

    return frame[
        [
            "stock_id",
            "trading_date",
            "positive_count",
            "neutral_count",
            "negative_count",
            "post_count",
            "sentiment_index",
            "is_sparse",
        ]
    ]
