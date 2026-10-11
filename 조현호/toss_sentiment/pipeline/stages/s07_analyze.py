"""07. 통계 검증.

원고 03장의 분석 절차를 순서대로 구현한다.
  ① 기술통계
  ② 시차 상관 탐색 (k = -5 ~ +5, 다중검정 보정)
  ③ 통제 변수를 포함한 회귀 (Newey-West HAC 표준오차)
  ④ 정상성 확인 후 Granger 검정 (보조적)
  ⑤ 최소 글 수 기준별 민감도 분석

유의한 결과라도 인과관계나 투자 수익의 근거로 해석하지 않는다.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import Config
from ..context import RunContext

NAME = "analyze"
TITLE = "기술통계·시차상관·회귀·Granger 검정"


def inputs(config: Config) -> list[Path]:
    return [config.data_path("processed", "panel.csv")]


def outputs(config: Config) -> list[Path]:
    return [
        config.output_path("tables", "07_기술통계.csv"),
        config.output_path("tables", "07_시차상관.csv"),
        config.output_path("tables", "07_회귀결과.csv"),
        config.output_path("tables", "07_민감도분석.csv"),
        config.output_path("figures", "07_시차상관.png"),
    ]


def run(ctx: RunContext) -> dict[str, Any]:
    cfg = ctx.config
    panel = ctx.read_table(inputs(cfg)[0], dtype={"stock_id": str})
    panel["trading_date"] = pd.to_datetime(panel["trading_date"])

    sm = _import_statsmodels(ctx)

    descriptive = _descriptive(panel)
    ctx.write_table(descriptive, outputs(cfg)[0])

    lo, hi = cfg.get("analyze.lag_range", [-5, 5])
    lag_table = _lag_correlation(panel, int(lo), int(hi))
    lag_table = _correct_multiple_testing(lag_table, str(cfg.get("analyze.multiple_testing", "bh")))
    ctx.write_table(lag_table, outputs(cfg)[1])
    _plot_lag(ctx, lag_table, outputs(cfg)[4])

    regression = _regressions(ctx, panel, sm)
    ctx.write_table(regression, outputs(cfg)[2])

    sensitivity = _sensitivity(panel, cfg.get("analyze.sensitivity_min_posts", [1, 5, 10]))
    ctx.write_table(sensitivity, outputs(cfg)[3])

    granger = _granger(ctx, panel, sm)
    if granger is not None and not granger.empty:
        ctx.write_table(granger, cfg.output_path("tables", "07_granger.csv"))

    significant = int((lag_table["유의(보정후)"] == "예").sum()) if "유의(보정후)" in lag_table else 0
    ctx.note(
        "시차를 반복 탐색한 결과는 탐색적 분석이다. 보정 후 유의한 관계라도 "
        "인과관계나 투자 수익의 근거로 해석하지 않는다."
    )

    return {
        "stocks": int(panel["stock_id"].nunique()),
        "lag_tests": int(len(lag_table)),
        "significant_after_correction": significant,
        "regressions": int(len(regression)),
        "granger": None if granger is None else int(len(granger)),
    }


def _import_statsmodels(ctx: RunContext):
    try:
        import statsmodels.api as sm

        return sm
    except ImportError:
        ctx.note(
            "statsmodels 가 설치되지 않아 HAC 회귀와 Granger 검정을 건너뛴다. "
            "pip install statsmodels 후 analyze 단계를 다시 실행한다."
        )
        return None


# --- ① 기술통계 ---------------------------------------------------------
def _descriptive(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (stock_id, name), g in panel.groupby(["stock_id", "stock_name"], dropna=False):
        rows.append(
            {
                "stock_id": stock_id,
                "종목명": name,
                "거래일수": int(len(g)),
                "총 글 수": int(g["post_count"].sum()),
                "일평균 글 수": round(float(g["post_count"].mean()), 2),
                "감성 결측률": round(float(g["sentiment_index"].isna().mean()), 4),
                "긍정 비율": round(
                    float(g["positive_count"].sum() / max(1, g["post_count"].sum())), 4
                ),
                "부정 비율": round(
                    float(g["negative_count"].sum() / max(1, g["post_count"].sum())), 4
                ),
                "감성지수 평균": round(float(g["sentiment_index"].mean()), 4),
                "감성지수 표준편차": round(float(g["sentiment_index"].std()), 4),
                "일수익률 평균": round(float(g["ret"].mean()), 6),
                "일수익률 표준편차": round(float(g["ret"].std()), 6),
                "누적수익률": round(float(g["ret"].sum()), 4),
            }
        )
    return pd.DataFrame(rows)


# --- ② 시차 상관 --------------------------------------------------------
def _lag_correlation(panel: pd.DataFrame, lo: int, hi: int) -> pd.DataFrame:
    rows = []
    for (stock_id, name), g in panel.groupby(["stock_id", "stock_name"], dropna=False):
        g = g.sort_values("trading_date")
        for k in range(lo, hi + 1):
            # k > 0 이면 감성 S(t) 와 이후 수익률 r(t+k) 의 비교다.
            shifted = g["ret"].shift(-k)
            pair = pd.concat([g["sentiment_index"], shifted], axis=1).dropna()
            pair.columns = ["s", "r"]
            n = len(pair)
            r, p = _pearson(pair["s"], pair["r"]) if n >= 10 else (np.nan, np.nan)
            rows.append(
                {
                    "stock_id": stock_id,
                    "종목명": name,
                    "시차 k": k,
                    "해석": _lag_label(k),
                    "표본수": n,
                    "상관계수": None if pd.isna(r) else round(float(r), 4),
                    "p값": None if pd.isna(p) else round(float(p), 4),
                }
            )
    return pd.DataFrame(rows)


def _lag_label(k: int) -> str:
    if k > 0:
        return f"감성이 수익률보다 {k}거래일 선행"
    if k < 0:
        return f"수익률이 감성보다 {abs(k)}거래일 선행"
    return "동일 거래일"


def _pearson(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    n = len(x)
    if n < 3:
        return float("nan"), float("nan")
    r = float(np.corrcoef(x, y)[0, 1])
    if not np.isfinite(r) or abs(r) >= 1.0:
        return r, float("nan")
    # t 분포 기반 양측 p값. scipy 의존을 피하려고 정규근사 대신 t 통계를 직접 쓴다.
    t = r * math.sqrt((n - 2) / (1 - r * r))
    try:
        from scipy import stats

        p = float(2 * stats.t.sf(abs(t), df=n - 2))
    except ImportError:
        p = float(2 * (1 - _normal_cdf(abs(t))))
    return r, p


def _normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _correct_multiple_testing(table: pd.DataFrame, method: str) -> pd.DataFrame:
    table = table.copy()
    if method != "bh" or table["p값"].isna().all():
        table["보정 p값"] = table["p값"]
        table["유의(보정후)"] = np.where(table["p값"] < 0.05, "예", "아니오")
        return table

    # Benjamini-Hochberg. 시차를 반복 탐색했으므로 보정값을 함께 보고한다.
    valid = table["p값"].notna()
    pvals = table.loc[valid, "p값"].to_numpy()
    order = np.argsort(pvals)
    m = len(pvals)
    adjusted = np.empty(m)
    running = 1.0
    for rank in range(m - 1, -1, -1):
        idx = order[rank]
        running = min(running, pvals[idx] * m / (rank + 1))
        adjusted[idx] = running

    table.loc[valid, "보정 p값"] = np.round(adjusted, 4)
    table["유의(보정후)"] = np.where(table["보정 p값"] < 0.05, "예", "아니오")
    return table


def _plot_lag(ctx: RunContext, table: pd.DataFrame, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for family in ["AppleGothic", "NanumGothic", "Malgun Gothic"]:
        if family in {f.name for f in matplotlib.font_manager.fontManager.ttflist}:
            plt.rcParams["font.family"] = family
            break
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for stock_id, g in table.groupby("stock_id"):
        label = g["종목명"].iloc[0] if g["종목명"].notna().any() else stock_id
        ax.plot(g["시차 k"], g["상관계수"], marker="o", linewidth=1.6, label=label)
    ax.axhline(0, color="#999999", linewidth=0.8)
    ax.axvline(0, color="#999999", linewidth=0.8, linestyle="--")
    ax.set_xlabel("시차 k (거래일)   ← 수익률 선행 | 감성 선행 →")
    ax.set_ylabel("감성 S(t) 와 수익률 r(t+k) 의 상관계수")
    ax.set_title("시차별 감성-수익률 상관")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    ctx.logger.info("저장: %s", ctx.rel(path))


# --- ③ 회귀 -------------------------------------------------------------
def _regressions(ctx: RunContext, panel: pd.DataFrame, sm) -> pd.DataFrame:
    if sm is None:
        return pd.DataFrame()

    maxlags = int(ctx.config.get("analyze.hac_maxlags", 5))
    specs = [
        # H2. 과거 수익률과 시장 수익률을 통제해도 이전 감성이 이후 수익률을 설명하는가.
        ("H2: 감성 → 다음 거래일 수익률", "ret_next", ["sentiment_index", "ret", "market_return", "log_post_count"]),
        # H1. 감성과 당일 수익률의 연관성.
        ("H1: 감성 ↔ 당일 수익률", "ret", ["sentiment_index", "market_return", "log_post_count"]),
        # H3. 이전 수익률이 이후 감성을 설명하는 사후 반응.
        ("H3: 수익률 → 다음 거래일 감성", "sentiment_index", ["ret_prev", "sentiment_prev", "log_post_count"]),
    ]

    rows = []
    for (stock_id, name), g in panel.groupby(["stock_id", "stock_name"], dropna=False):
        for label, dependent, regressors in specs:
            available = [c for c in regressors if c in g.columns and g[c].notna().any()]
            data = g[[dependent] + available].dropna()
            if len(data) < 20:
                rows.append(
                    {
                        "stock_id": stock_id, "종목명": name, "모형": label,
                        "변수": "-", "표본수": len(data),
                        "비고": "표본 부족(20 미만)으로 추정하지 않음",
                    }
                )
                continue

            y = data[dependent]
            X = sm.add_constant(data[available])
            # 시계열 의존성을 고려해 Newey-West HAC 표준오차를 사용한다.
            model = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})
            for var in X.columns:
                rows.append(
                    {
                        "stock_id": stock_id,
                        "종목명": name,
                        "모형": label,
                        "변수": var,
                        "표본수": int(model.nobs),
                        "계수": round(float(model.params[var]), 6),
                        "HAC 표준오차": round(float(model.bse[var]), 6),
                        "t값": round(float(model.tvalues[var]), 3),
                        "p값": round(float(model.pvalues[var]), 4),
                        "조정 R2": round(float(model.rsquared_adj), 4),
                        "비고": "",
                    }
                )
    return pd.DataFrame(rows)


# --- ④ Granger ----------------------------------------------------------
def _granger(ctx: RunContext, panel: pd.DataFrame, sm) -> pd.DataFrame | None:
    if sm is None:
        return None
    try:
        from statsmodels.tsa.stattools import grangercausalitytests
    except ImportError:
        return None

    maxlag = int(ctx.config.get("analyze.granger_maxlag", 5))
    rows = []
    for (stock_id, name), g in panel.groupby(["stock_id", "stock_name"], dropna=False):
        data = g[["sentiment_index", "ret"]].dropna()
        if len(data) < maxlag * 5 + 20:
            ctx.note(
                f"종목 {stock_id}: 연속 표본이 부족해 Granger 검정을 수행하지 않았다."
            )
            continue

        stationary = True
        for col in ["sentiment_index", "ret"]:
            p = _adf_pvalue(data[col])
            if not (p < 0.05):
                stationary = False
            rows.append(
                {
                    "stock_id": stock_id, "종목명": name, "검정": f"ADF({col})",
                    "lag": "-", "p값": None if pd.isna(p) else round(p, 4),
                    "비고": "정상성 충족" if p < 0.05 else "정상성 미충족",
                }
            )
        if not stationary:
            ctx.note(f"종목 {stock_id}: 정상성이 확인되지 않아 Granger 결과를 보조 참고로만 본다.")

        for direction, cols in [
            ("감성 → 수익률", ["ret", "sentiment_index"]),
            ("수익률 → 감성", ["sentiment_index", "ret"]),
        ]:
            try:
                result = grangercausalitytests(data[cols], maxlag=maxlag, verbose=False)
            except TypeError:
                result = grangercausalitytests(data[cols], maxlag=maxlag)
            except Exception as exc:
                ctx.note(f"종목 {stock_id} {direction}: Granger 검정 실패({exc}).")
                continue
            for lag, payload in result.items():
                p = float(payload[0]["ssr_ftest"][1])
                rows.append(
                    {
                        "stock_id": stock_id, "종목명": name, "검정": direction,
                        "lag": lag, "p값": round(p, 4),
                        "비고": "과거 값의 추가 예측 정보 유무를 검토한 결과",
                    }
                )
    return pd.DataFrame(rows)


def _adf_pvalue(series: pd.Series) -> float:
    """ADF 검정의 p값. statsmodels 버전에 따른 반환 형식 차이를 흡수한다."""
    from statsmodels.tsa.stattools import adfuller

    try:
        result = adfuller(series, autolag="AIC", result_object=False)
    except TypeError:
        result = adfuller(series, autolag="AIC")
    except Exception:
        return float("nan")
    try:
        return float(result[1])
    except (TypeError, IndexError):
        return float(getattr(result, "pvalue", float("nan")))


# --- ⑤ 민감도 ----------------------------------------------------------
def _sensitivity(panel: pd.DataFrame, candidates: list[int]) -> pd.DataFrame:
    rows = []
    for min_posts in candidates:
        subset = panel.copy()
        # 최소 글 수 기준을 바꿔 가며 감성 지수를 다시 정의한다.
        s = (subset["positive_count"] - subset["negative_count"]) / subset["post_count"].replace(0, np.nan)
        s = s.where(subset["post_count"] >= min_posts)
        subset["s_alt"] = s
        for (stock_id, name), g in subset.groupby(["stock_id", "stock_name"], dropna=False):
            pair = pd.concat([g["s_alt"], g["ret_next"]], axis=1).dropna()
            r, p = _pearson(pair.iloc[:, 0], pair.iloc[:, 1]) if len(pair) >= 10 else (np.nan, np.nan)
            rows.append(
                {
                    "최소 글 수": min_posts,
                    "stock_id": stock_id,
                    "종목명": name,
                    "관측 거래일": int(g["s_alt"].notna().sum()),
                    "표본수": int(len(pair)),
                    "corr(S(t), r(t+1))": None if pd.isna(r) else round(float(r), 4),
                    "p값": None if pd.isna(p) else round(float(p), 4),
                }
            )
    return pd.DataFrame(rows)
