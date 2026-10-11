"""01. 커뮤니티 텍스트 수집.

원고 02장의 원칙을 코드로 강제한다.
수집 허용 조건을 확인하기 전에는 자동 수집을 수행하지 않으며,
확보 경로는 어댑터로 분리해 교체할 수 있게 둔다.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import Config
from ..context import RunContext, StageError

NAME = "collect"
TITLE = "커뮤니티 텍스트 확보"

SCHEMA = ["stock_id", "post_id", "parent_id", "text", "created_at", "collected_at", "source"]


def inputs(config: Config) -> list[Path]:
    if config.get("collect.source") == "manual_csv":
        input_dir = config.resolve(config.get("collect.manual_csv.input_dir", "data/raw/posts"))
        return sorted(input_dir.glob("*.csv")) if input_dir.exists() else []
    return []


def outputs(config: Config) -> list[Path]:
    return [config.data_path("raw", "posts.csv")]


def run(ctx: RunContext) -> dict[str, Any]:
    source = ctx.config.get("collect.source", "sample")
    if source == "sample":
        df = _sample(ctx)
    elif source == "manual_csv":
        df = _manual_csv(ctx)
    else:
        raise StageError(
            f"collect.source 값 '{source}' 을 지원하지 않습니다. sample 또는 manual_csv 를 사용하세요."
        )

    df = _normalize(ctx, df)
    ctx.write_table(df, outputs(ctx.config)[0])

    per_stock = df.groupby("stock_id").size().to_dict()
    return {
        "source": source,
        "rows": int(len(df)),
        "posts": int((df["parent_id"].isna()).sum()),
        "comments": int((~df["parent_id"].isna()).sum()),
        "per_stock": {k: int(v) for k, v in per_stock.items()},
        "date_min": str(df["created_at"].min()),
        "date_max": str(df["created_at"].max()),
    }


def _normalize(ctx: RunContext, df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in ["stock_id", "post_id", "text", "created_at"] if c not in df.columns]
    if missing:
        raise StageError(f"수집 데이터에 필수 컬럼이 없습니다: {', '.join(missing)}")

    df = df.copy()
    df["stock_id"] = df["stock_id"].astype(str).str.zfill(6)
    if "parent_id" not in df.columns:
        df["parent_id"] = pd.NA
    if "collected_at" not in df.columns:
        df["collected_at"] = datetime.now().isoformat(timespec="seconds")
    if "source" not in df.columns:
        df["source"] = ctx.config.get("collect.source", "unknown")

    tz = ctx.config.get("project.timezone", "Asia/Seoul")
    created = pd.to_datetime(df["created_at"], errors="coerce")
    bad = int(created.isna().sum())
    if bad:
        ctx.note(f"작성 시각을 해석할 수 없는 {bad}건을 제외했다. 시각 정보 결측은 보고서에 기록한다.")
        df = df.loc[created.notna()].copy()
        created = created.loc[created.notna()]
    if getattr(created.dtype, "tz", None) is not None:
        created = created.dt.tz_convert(tz).dt.tz_localize(None)
    df["created_at"] = created

    known = [c for c in SCHEMA if c in df.columns]
    extra = [c for c in df.columns if c not in SCHEMA]
    return df[known + extra].sort_values(["stock_id", "created_at"]).reset_index(drop=True)


def _manual_csv(ctx: RunContext) -> pd.DataFrame:
    input_dir = ctx.config.resolve(
        ctx.config.get("collect.manual_csv.input_dir", "data/raw/posts")
    )
    files = sorted(input_dir.glob("*.csv")) if input_dir.exists() else []
    if not files:
        raise StageError(
            f"{ctx.rel(input_dir)} 에 수집 CSV가 없습니다.\n"
            f"  필수 컬럼: stock_id, post_id, parent_id, text, created_at\n"
            f"  수집 경로를 아직 확정하지 못했다면 collect.source 를 sample 로 두고 절차를 점검하세요."
        )
    if not ctx.config.get("collect.collection_approved", False):
        ctx.note(
            "collect.collection_approved 가 false 인 상태에서 수집본을 읽었다. "
            "이용 조건·접근 범위 확인 결과를 수집 가능성 점검표에 남겨야 한다."
        )
    frames = [pd.read_csv(f, dtype={"stock_id": str}) for f in files]
    ctx.logger.info("      수집 파일 %d개 병합", len(files))
    return pd.concat(frames, ignore_index=True)


def _sample(ctx: RunContext) -> pd.DataFrame:
    """파이프라인 점검용 합성 표본.

    실제 커뮤니티 자료가 아니며 어떤 결과도 연구 근거로 사용할 수 없다.
    감성과 수익률 사이에 약한 선행 관계를 일부러 심어 두어 분석 단계가
    관계를 탐지하는지 확인하는 용도다.
    """
    ctx.note(
        "collect.source=sample 로 실행했다. 합성 표본이므로 산출된 수치는 "
        "연구 결과가 아니라 파이프라인 동작 점검 결과다."
    )

    cfg = ctx.config
    rng = np.random.default_rng(int(cfg.get("collect.sample.seed", 20261006)))
    per_day = int(cfg.get("collect.sample.posts_per_day", 24))
    comment_ratio = float(cfg.get("collect.sample.comment_ratio", 0.45))

    start = pd.Timestamp(cfg.require("scope.start_date"))
    end = pd.Timestamp(cfg.require("scope.end_date"))
    days = pd.date_range(start, end, freq="D")

    positive = [
        "실적 발표 기대된다 추가 매수 갑니다",
        "저점 잡았다 여기서 반등 간다",
        "장기로 들고 간다 우상향 믿는다",
        "수급 들어오는 게 보인다 상승 가자",
        "물타기 끝 이제 수익 구간이다",
    ]
    negative = [
        "손절했다 더 빠질 것 같다",
        "물렸다 언제 회복되냐 답답하다",
        "외국인 계속 파는데 하락 각이다",
        "고점에 물려서 계좌가 녹는다",
        "이번 분기 실적 부진할 듯 비중 줄인다",
    ]
    neutral = [
        "오늘 거래량 얼마였나요",
        "배당 기준일이 언제인지 아시는 분",
        "공시 떴네요 확인해 보세요",
        "증권사 리포트 링크 공유합니다",
        "차트 보는 법 질문 드립니다",
    ]

    prefix = ["", "오늘 ", "솔직히 ", "개인적으로 ", "다시 봐도 ", "그래도 "]
    suffix = ["", " ㅎㅎ", " ㅠㅠ", "...", " 다들 어떻게 보시나요", " 의견 궁금합니다", "!!"]

    rows: list[dict[str, Any]] = []
    for stock_id in cfg.stock_ids:
        # 종목별로 다른 심리 흐름을 만든다.
        drift = rng.normal(0, 1, len(days)).cumsum() * 0.12
        mood = np.tanh(drift - drift.mean())
        for day, m in zip(days, mood):
            n = max(1, int(rng.poisson(per_day)))
            p_pos = float(np.clip(0.34 + 0.22 * m, 0.08, 0.72))
            p_neg = float(np.clip(0.34 - 0.22 * m, 0.08, 0.72))
            p_neu = max(0.06, 1.0 - p_pos - p_neg)
            total = p_pos + p_neg + p_neu
            labels = rng.choice(
                ["pos", "neg", "neu"], size=n, p=[p_pos / total, p_neg / total, p_neu / total]
            )
            for j, label in enumerate(labels):
                pool = {"pos": positive, "neg": negative, "neu": neutral}[label]
                minute = int(rng.integers(0, 24 * 60))
                created = day + timedelta(minutes=minute)
                seed_text = f"{stock_id}{day:%Y%m%d}{j}"
                post_id = hashlib.md5(seed_text.encode()).hexdigest()[:12]
                is_comment = j > 0 and rng.random() < comment_ratio
                text = f"{rng.choice(prefix)}{rng.choice(pool)}{rng.choice(suffix)}"
                rows.append(
                    {
                        "stock_id": stock_id,
                        "post_id": post_id,
                        "parent_id": rows[-1]["post_id"] if is_comment and rows else pd.NA,
                        "text": text,
                        "created_at": created,
                        "collected_at": datetime.now().isoformat(timespec="seconds"),
                        "source": "sample",
                    }
                )
    return pd.DataFrame(rows)
