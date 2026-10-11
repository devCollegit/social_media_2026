"""08. 결과 요약.

분석 표를 모아 중간·최종 보고서에 옮길 수 있는 마크다운 요약을 만든다.
수치는 모두 산출된 표에서 가져오며, 없는 결과는 "미산출"로 남긴다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import Config
from ..context import RunContext

NAME = "report"
TITLE = "결과 요약 작성"


def inputs(config: Config) -> list[Path]:
    return [
        config.output_path("tables", "07_기술통계.csv"),
        config.output_path("tables", "07_시차상관.csv"),
        config.output_path("tables", "07_회귀결과.csv"),
    ]


def outputs(config: Config) -> list[Path]:
    return [config.output_path("보고서_결과요약.md")]


def run(ctx: RunContext) -> dict[str, Any]:
    cfg = ctx.config
    descriptive = _read(inputs(cfg)[0])
    lags = _read(inputs(cfg)[1])
    regression = _read(inputs(cfg)[2])
    sensitivity = _read(cfg.output_path("tables", "07_민감도분석.csv"))
    performance = _read(cfg.output_path("tables", "03_감성분류_성능.csv"))

    lines: list[str] = []
    add = lines.append

    add("# 토스증권 커뮤니티 감성 분석 — 결과 요약")
    add("")
    add(f"- 생성 시각: {datetime.now():%Y-%m-%d %H:%M}")
    add(f"- 실행 ID: {ctx.run_id} / 설정 지문: {cfg.fingerprint}")
    add(f"- 분석 기간: {cfg.get('scope.start_date')} ~ {cfg.get('scope.end_date')}")
    add(f"- 분석 종목: {', '.join(f'{n}({i})' for i, n in cfg.stock_names.items())}")
    add(f"- 수집 경로: {cfg.get('collect.source')} / 감성 분류: {cfg.get('sentiment.method')}")
    add("")

    if str(cfg.get("collect.source")) == "sample" or str(cfg.get("market.source")) == "sample":
        add("> **주의.** 합성 표본으로 실행한 결과다. 아래 수치는 파이프라인 동작 점검 결과이며")
        add("> 연구 결과로 보고할 수 없다. 실제 수집본으로 다시 실행한 뒤 보고서에 반영한다.")
        add("")

    add("## 1. 기술통계")
    add("")
    add(_table(descriptive, "기술통계가 아직 산출되지 않았다."))
    add("")

    add("## 2. 시차 상관 (RQ1·RQ2·RQ3)")
    add("")
    if lags is None:
        add("시차 상관이 아직 산출되지 않았다.")
    else:
        add("보정 후 유의한 시차만 추린 결과다. k>0 은 감성이 수익률보다 앞선 비교다.")
        add("")
        significant = lags[lags.get("유의(보정후)") == "예"] if "유의(보정후)" in lags else lags.iloc[0:0]
        if significant.empty:
            add("다중검정 보정 후 유의한 시차는 없었다. 관계가 없다는 결과도 유효한 연구 결과로 보고한다.")
        else:
            add(_table(significant, ""))
        add("")
        add("종목별 최대 상관 시차:")
        add("")
        add(_table(_peak_lags(lags), ""))
    add("")

    add("## 3. 회귀 분석 (H1·H2·H3)")
    add("")
    if regression is None or regression.empty:
        add("회귀 결과가 아직 산출되지 않았다. statsmodels 설치 여부를 확인한다.")
    else:
        focus = regression[regression["변수"].isin(["sentiment_index", "ret_prev"])]
        add("감성과 과거 수익률의 계수만 추린 결과다. 표준오차는 Newey-West HAC 기준이다.")
        add("")
        add(_table(focus, ""))
    add("")

    add("## 4. 민감도 분석")
    add("")
    add(_table(sensitivity, "민감도 분석이 아직 산출되지 않았다."))
    add("")

    add("## 5. 감성 분류 성능")
    add("")
    if performance is None:
        add("사람이 검수한 평가 표본이 없어 분류 성능을 보고할 수 없다.")
        add("예비 텍스트 300건을 두 명이 독립 라벨링하고 불일치를 조정한 뒤 다시 실행한다.")
    else:
        add(_table(performance, ""))
    add("")

    add("## 6. 실행 중 기록한 한계와 확인 사항")
    add("")
    recorded = ctx.load_notes()
    if recorded:
        for stage_name, messages in recorded.items():
            for message in messages:
                add(f"- ({stage_name}) {message}")
    elif ctx.notes:
        for note in ctx.notes:
            add(f"- {note}")
    else:
        add("- 기록된 항목 없음.")
    add("")
    add("## 7. 해석 범위")
    add("")
    add("- 커뮤니티 이용자는 전체 투자자를 대표하지 않는다.")
    add("- 뉴스·공시·시장 급변이 감성과 가격 모두에 영향을 줄 수 있다.")
    add("- 시차를 반복 탐색한 결과는 탐색적 분석이며 인과관계의 근거가 아니다.")
    add("- 유의한 관계가 확인되더라도 투자 수익을 보장하는 근거로 해석하지 않는다.")
    add("")

    path = ctx.write_text("\n".join(lines), outputs(cfg)[0])
    return {"path": ctx.rel(path), "notes": sum(len(v) for v in recorded.values()) or len(ctx.notes)}


def _read(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    # 종목 코드의 앞자리 0이 사라지지 않도록 문자열로 읽는다.
    df = pd.read_csv(path, dtype={"stock_id": str})
    return df if not df.empty else None


def _table(df: pd.DataFrame | None, fallback: str) -> str:
    if df is None or df.empty:
        return fallback
    return df.to_markdown(index=False)


def _peak_lags(lags: pd.DataFrame) -> pd.DataFrame:
    valid = lags.dropna(subset=["상관계수"])
    if valid.empty:
        return valid
    idx = valid.groupby("stock_id")["상관계수"].apply(lambda s: s.abs().idxmax())
    return valid.loc[idx]
