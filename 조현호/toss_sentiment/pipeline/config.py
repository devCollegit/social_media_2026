"""설정 로딩과 접근."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """설정 파일이 파이프라인 요구사항을 만족하지 않을 때 발생한다."""


@dataclass
class Config:
    raw: dict[str, Any]
    path: Path
    root: Path = field(init=False)

    def __post_init__(self) -> None:
        self.root = self.path.resolve().parents[1]

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.raw
        for key in dotted.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def require(self, dotted: str) -> Any:
        value = self.get(dotted, None)
        if value is None:
            raise ConfigError(f"설정에 '{dotted}' 항목이 필요합니다: {self.path}")
        return value

    def dir(self, kind: str) -> Path:
        """data/output/runs 디렉터리를 절대 경로로 돌려준다."""
        rel = self.get(f"paths.{kind}_dir", kind)
        return (self.root / rel).resolve()

    def data_path(self, *parts: str) -> Path:
        return self.dir("data").joinpath(*parts)

    def resolve(self, value: str | Path) -> Path:
        """설정에 적힌 경로를 프로젝트 루트 기준 절대 경로로 바꾼다."""
        path = Path(value)
        return path if path.is_absolute() else (self.root / path).resolve()

    def output_path(self, *parts: str) -> Path:
        return self.dir("output").joinpath(*parts)

    @property
    def stock_ids(self) -> list[str]:
        return [str(s["stock_id"]) for s in self.require("scope.stocks")]

    @property
    def stock_names(self) -> dict[str, str]:
        return {
            str(s["stock_id"]): s.get("name", str(s["stock_id"]))
            for s in self.require("scope.stocks")
        }

    @property
    def fingerprint(self) -> str:
        """설정 내용의 해시. 실행 기록에 남겨 재현성을 확인한다."""
        blob = json.dumps(self.raw, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"설정 파일을 찾을 수 없습니다: {path}")
    with path.open(encoding="utf-8") as fp:
        raw = yaml.safe_load(fp) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"설정 파일의 최상위는 매핑이어야 합니다: {path}")
    cfg = Config(raw=raw, path=path)
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    stocks = cfg.get("scope.stocks")
    if not stocks:
        raise ConfigError("scope.stocks 에 분석 대상 종목을 1개 이상 지정해야 합니다.")
    if len(set(cfg.stock_ids)) != len(cfg.stock_ids):
        raise ConfigError("scope.stocks 에 중복된 stock_id 가 있습니다.")

    start, end = cfg.require("scope.start_date"), cfg.require("scope.end_date")
    if str(start) >= str(end):
        raise ConfigError("scope.start_date 는 scope.end_date 보다 앞서야 합니다.")

    lo, hi = cfg.get("analyze.lag_range", [-5, 5])
    if lo > hi:
        raise ConfigError("analyze.lag_range 는 [최소, 최대] 순서여야 합니다.")

    if cfg.get("aggregate.min_posts", 0) < 0:
        raise ConfigError("aggregate.min_posts 는 0 이상이어야 합니다.")
