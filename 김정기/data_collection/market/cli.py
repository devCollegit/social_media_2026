"""시세 수집 CLI.

    python -m market.cli prices                  # 설정의 종목 + 지수
    python -m market.cli prices --stocks 005930,000660 --start 2026-07-01
    python -m market.cli master                  # 종목 마스터 (시장·업종·ISIN)
    python -m market.cli candidates --top 300    # 커뮤니티 예비 수집용 후보 종목

출력 형식은 조현호 파이프라인 market.source: csv 와 호환된다.
  <market_dir>/<종목코드>.csv  date, close, volume (+ open, high, low, change, value, market_cap, shares)
  <market_dir>/index.csv       date, close (+ kospi_*, kosdaq_*)
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

import settings as settings_mod
from market.sources import MarketSource

STOCK_COLUMNS = ["date", "close", "volume", "open", "high", "low", "change", "value", "market_cap", "shares"]


def cmd_prices(args: argparse.Namespace, cfg: settings_mod.Settings) -> int:
    log = settings_mod.setup_logging(cfg, "market")
    out_dir = cfg.path("paths.market_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    start = args.start or cfg.start
    end = args.end or cfg.end
    codes = settings_mod.parse_stock_list(args.stocks, args.stocks_file, cfg)

    src = MarketSource(interval=float(cfg.get("market.request_interval_sec", 1.0)))
    log.info("시세 수집 시작: %d종목, %s ~ %s, KRX 조회 활성화=%s", len(codes), start, end, src.use_krx)
    if not src.use_krx:
        log.warning("KRX_ID/KRX_PW 가 없어 value, market_cap, shares 컬럼은 비워 둡니다.")

    failed: list[str] = []
    for i, code in enumerate(codes, 1):
        try:
            df = src.stock_daily(code, start, end)
        except Exception as exc:
            log.warning("[%d/%d] %s 실패: %s", i, len(codes), code, exc)
            failed.append(code)
            continue
        # 수정주가는 과거 값이 소급 변경되므로 매번 전체 기간을 다시 받아 덮어쓴다.
        df[STOCK_COLUMNS].to_csv(out_dir / f"{code}.csv", index=False)
        log.info("[%d/%d] %s %d행 (%s ~ %s)", i, len(codes), code, len(df), df["date"].min(), df["date"].max())

    idx = src.index_daily(start, end)
    main = str(cfg.get("market.market_index", "KOSPI")).lower()
    idx.insert(1, "close", idx[f"{main}_close"])
    idx.to_csv(out_dir / "index.csv", index=False)
    log.info("지수 %d행 저장 (close = %s)", len(idx), main.upper())

    if failed:
        log.warning("실패 종목 %d개: %s", len(failed), ",".join(failed))
        return 1
    return 0


def cmd_master(args: argparse.Namespace, cfg: settings_mod.Settings) -> int:
    log = settings_mod.setup_logging(cfg, "market")
    meta_dir = cfg.path("paths.meta_dir")
    meta_dir.mkdir(parents=True, exist_ok=True)
    src = MarketSource(interval=float(cfg.get("market.request_interval_sec", 1.0)))
    df = src.stock_master()
    path = meta_dir / "stock_master.csv"
    df.to_csv(path, index=False)
    log.info("종목 마스터 %d종목 저장: %s", len(df), path)
    log.info("시장별: %s", df["market"].value_counts().to_dict())
    return 0


def cmd_candidates(args: argparse.Namespace, cfg: settings_mod.Settings) -> int:
    """커뮤니티 예비 수집 후보. 보통주·KOSPI/KOSDAQ 중 거래대금·시가총액 상위 종목.

    커뮤니티 활동량은 거래대금과 관심도에 비례할 것으로 보고 넉넉히 뽑는다.
    최종 종목은 예비 수집으로 일평균 글 수 20건 이상인지 확인해 확정한다.
    """
    log = settings_mod.setup_logging(cfg, "market")
    meta_dir = cfg.path("paths.meta_dir")
    master_path = meta_dir / "stock_master.csv"
    if not master_path.exists():
        cmd_master(args, cfg)
    m = pd.read_csv(master_path, dtype={"stock_id": str})
    # KRX 목록은 코스닥 우량주 50종목을 'KOSDAQ GLOBAL' 로 따로 표기한다. 코스닥으로 합친다.
    m["market"] = m["market"].replace({"KOSDAQ GLOBAL": "KOSDAQ"})
    pool = m[m["market"].isin(["KOSPI", "KOSDAQ"])].copy()
    # 우선주·스팩·리츠 등 제외: 보통주 코드는 끝자리가 0
    pool = pool[pool["stock_id"].str.endswith("0")]
    pool = pool[~pool["name"].str.contains("스팩|리츠|ETN", na=False)]
    pool["rank_value"] = pool["value_snapshot"].rank(ascending=False)
    pool["rank_cap"] = pool["market_cap_snapshot"].rank(ascending=False)
    pool["rank_mix"] = pool[["rank_value", "rank_cap"]].min(axis=1)
    top = pool.sort_values("rank_mix").head(args.top)
    cols = ["stock_id", "isin", "name", "market", "industry", "market_cap_snapshot", "value_snapshot", "snapshot_date"]
    path = meta_dir / "candidates.csv"
    top[cols].to_csv(path, index=False)
    log.info("후보 %d종목 저장: %s (KOSPI %d / KOSDAQ %d)", len(top), path,
             (top["market"] == "KOSPI").sum(), (top["market"] == "KOSDAQ").sum())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="market.cli", description="pykrx 시세 수집")
    parser.add_argument("-c", "--config", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prices", help="종목 일봉 + 지수")
    p.add_argument("--stocks")
    p.add_argument("--stocks-file")
    p.add_argument("--start")
    p.add_argument("--end")
    p.set_defaults(func=cmd_prices)

    m = sub.add_parser("master", help="종목 마스터")
    m.set_defaults(func=cmd_master)

    c = sub.add_parser("candidates", help="예비 수집 후보 종목")
    c.add_argument("--top", type=int, default=300)
    c.set_defaults(func=cmd_candidates)

    args = parser.parse_args(argv)
    cfg = settings_mod.load(args.config)
    return args.func(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
