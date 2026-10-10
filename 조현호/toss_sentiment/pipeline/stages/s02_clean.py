"""02. 정제.

중복·홍보성 글을 제거하되 부정어, 이모티콘, 주식 은어는 보존한다.
제거 사유별 건수를 기록해 표본 편향을 보고할 수 있게 한다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import Config
from ..context import RunContext

NAME = "clean"
TITLE = "중복·홍보 제거와 시간 기준 정리"

# 공백과 반복 문자만 정규화한다. 부정어·이모티콘·은어는 감성 판단에 필요하므로 지우지 않는다.
_WS = re.compile(r"\s+")
_REPEAT = re.compile(r"(.)\1{3,}")
_URL = re.compile(r"https?://\S+")


def inputs(config: Config) -> list[Path]:
    return [config.data_path("raw", "posts.csv")]


def outputs(config: Config) -> list[Path]:
    return [
        config.data_path("interim", "posts_clean.csv"),
        config.output_path("tables", "02_정제_요약.csv"),
    ]


def run(ctx: RunContext) -> dict[str, Any]:
    cfg = ctx.config
    df = ctx.read_table(inputs(cfg)[0], dtype={"stock_id": str, "post_id": str, "parent_id": str})
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    before = len(df)
    reasons: dict[str, int] = {}

    def drop(mask: pd.Series, reason: str) -> pd.DataFrame:
        n = int(mask.sum())
        if n:
            reasons[reason] = reasons.get(reason, 0) + n
        return df.loc[~mask].copy()

    # 분석에 불필요한 개인정보 컬럼은 저장하지 않는다.
    drop_cols = [c for c in cfg.get("clean.drop_columns", []) if c in df.columns]
    if drop_cols:
        df = df.drop(columns=drop_cols)
        ctx.logger.info("      개인정보 컬럼 제거: %s", ", ".join(drop_cols))

    df["text"] = df["text"].astype(str)
    df["text_norm"] = (
        df["text"].str.replace(_URL, " ", regex=True).str.replace(_REPEAT, r"\1\1", regex=True)
    )
    df["text_norm"] = df["text_norm"].str.replace(_WS, " ", regex=True).str.strip()

    df = drop(df["text_norm"].str.len() < int(cfg.get("clean.min_chars", 2)), "길이 미달")

    # 기간 밖의 글은 분석 범위에서 제외한다.
    start = pd.Timestamp(cfg.require("scope.start_date"))
    end = pd.Timestamp(cfg.require("scope.end_date")) + pd.Timedelta(days=1)
    df = drop(~df["created_at"].between(start, end, inclusive="left"), "분석 기간 밖")

    # 분석 대상 종목이 아닌 글을 제외한다(종목 관련성 확인).
    df = drop(~df["stock_id"].isin(cfg.stock_ids), "대상 종목 아님")

    df = drop(df["post_id"].duplicated(keep="first"), "식별자 중복")

    if cfg.get("clean.drop_duplicate_text", True):
        df = drop(
            df.duplicated(subset=["stock_id", "text_norm", "created_at"], keep="first"),
            "동일 시각 동일 본문",
        )

    threshold = int(cfg.get("clean.promo_repeat_threshold", 4))
    if threshold > 0:
        # 홍보성 판정은 같은 종목·같은 날 안에서만 본다.
        # 분석 기간 전체로 보면 "상한가 가자" 같은 일상적 표현까지 제거되어 표본이 왜곡된다.
        df["_day"] = df["created_at"].dt.normalize()
        group_size = df.groupby(["stock_id", "_day", "text_norm"])["post_id"].transform("size")
        dup_within_day = df.duplicated(subset=["stock_id", "_day", "text_norm"], keep="first")
        df = drop(
            (group_size >= threshold) & dup_within_day,
            f"동일 일자 반복 홍보({threshold}회 이상)",
        )
        df = df.drop(columns=["_day"])

    df = df.sort_values(["stock_id", "created_at"]).reset_index(drop=True)
    ctx.write_table(df, outputs(cfg)[0])

    summary = pd.DataFrame(
        [{"항목": "수집 원본", "건수": before}]
        + [{"항목": f"제외 - {k}", "건수": v} for k, v in reasons.items()]
        + [{"항목": "분석용 텍스트", "건수": len(df)}]
    )
    summary["건수"] = summary["건수"].astype(int)
    summary["비율(%)"] = (summary["건수"] / before * 100).round(2) if before else 0.0
    ctx.write_table(summary, outputs(cfg)[1])

    if before and (before - len(df)) / before > 0.5:
        ctx.note("정제 과정에서 원본의 절반 이상이 제외되었다. 표본 편향 가능성을 보고서에 명시한다.")

    return {"before": before, "after": int(len(df)), "dropped": reasons}
