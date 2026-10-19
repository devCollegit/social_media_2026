"""설정 로딩과 로깅 공통 함수."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent


@dataclass
class Settings:
    raw: dict[str, Any]
    base: Path

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def path(self, dotted: str) -> Path:
        value = self.get(dotted)
        if value is None:
            raise KeyError(f"설정 {dotted} 이 없습니다.")
        p = Path(value)
        return p if p.is_absolute() else self.base / p

    @property
    def stocks(self) -> list[str]:
        return [str(s).zfill(6) for s in self.get("stocks", [])]

    @property
    def start(self) -> str:
        return str(self.get("period.start"))

    @property
    def end(self) -> str:
        return str(self.get("period.end") or date.today().isoformat())


def load(path: str | Path | None = None) -> Settings:
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return Settings(raw=raw, base=cfg_path.resolve().parent)


def setup_logging(settings: Settings, name: str) -> logging.Logger:
    """콘솔과 logs/<name>.log 에 함께 남긴다. 실패 로그는 WARNING 이상으로 기록한다."""
    logs_dir = settings.path("paths.logs_dir")
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    for handler in (logging.StreamHandler(), logging.FileHandler(logs_dir / f"{name}.log", encoding="utf-8")):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger


def parse_stock_list(arg: str | None, file: str | None, settings: Settings) -> list[str]:
    """--stocks 005930,000660 / --stocks-file 경로 / 설정값 순으로 종목 목록을 정한다."""
    if arg:
        return [s.strip().zfill(6) for s in arg.split(",") if s.strip()]
    if file:
        lines = Path(file).read_text(encoding="utf-8").splitlines()
        codes = []
        for line in lines:
            token = line.split(",")[0].strip()
            if token.isdigit():
                codes.append(token.zfill(6))
        return codes
    return settings.stocks
