"""실행 맥락: 로깅, 산출물 입출력, 실행 기록(manifest)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .config import Config

LOGGER_NAME = "toss_pipeline"


class StageError(Exception):
    """단계 실행이 전제 조건을 만족하지 못했을 때 발생한다."""


def setup_logging(log_file: Path | None = None, verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%H:%M:%S")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s")
        )
        logger.addHandler(file_handler)
    return logger


@dataclass
class RunContext:
    config: Config
    run_id: str
    run_dir: Path
    logger: logging.Logger
    force: bool = False
    dry_run: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    current_stage: str | None = None

    @classmethod
    def create(
        cls,
        config: Config,
        force: bool = False,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> "RunContext":
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = config.dir("runs") / run_id
        if not dry_run:
            run_dir.mkdir(parents=True, exist_ok=True)
        logger = setup_logging(None if dry_run else run_dir / "pipeline.log", verbose)
        return cls(
            config=config,
            run_id=run_id,
            run_dir=run_dir,
            logger=logger,
            force=force,
            dry_run=dry_run,
        )

    # --- 산출물 입출력 -------------------------------------------------
    def read_table(self, path: Path, **kwargs: Any) -> pd.DataFrame:
        if not path.exists():
            raise StageError(
                f"필요한 입력 파일이 없습니다: {self.rel(path)}\n"
                f"  이전 단계를 먼저 실행하세요."
            )
        return pd.read_csv(path, **kwargs)

    def write_table(self, df: pd.DataFrame, path: Path, index: bool = False) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=index, encoding="utf-8-sig")
        self.logger.info("저장: %s (%d행)", self.rel(path), len(df))
        return path

    def write_json(self, payload: Any, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2, default=str)
        self.logger.info("저장: %s", self.rel(path))
        return path

    def write_text(self, text: str, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.logger.info("저장: %s", self.rel(path))
        return path

    def rel(self, path: Path) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.config.root))
        except ValueError:
            return str(path)

    def note(self, message: str) -> None:
        """보고서에 그대로 옮길 수 있는 한계·주의사항을 기록한다.

        단계별로 파일에 남겨 두어, 이후 report 단계만 따로 실행해도
        직전 단계들이 남긴 기록을 그대로 반영할 수 있게 한다.
        """
        self.notes.append(message)
        self.logger.warning(message)
        if not self.dry_run:
            self._persist_note(message)

    @property
    def notes_path(self) -> Path:
        return self.config.dir("runs") / "notes.json"

    def _persist_note(self, message: str) -> None:
        store = self.load_notes()
        stage = self.current_stage or "기타"
        bucket = store.setdefault(stage, [])
        if message not in bucket:
            bucket.append(message)
        self.notes_path.parent.mkdir(parents=True, exist_ok=True)
        with self.notes_path.open("w", encoding="utf-8") as fp:
            json.dump(store, fp, ensure_ascii=False, indent=2)

    def load_notes(self) -> dict[str, list[str]]:
        if not self.notes_path.exists():
            return {}
        try:
            with self.notes_path.open(encoding="utf-8") as fp:
                return json.load(fp)
        except (json.JSONDecodeError, OSError):
            return {}

    def reset_stage_notes(self, stage: str) -> None:
        """단계를 다시 실행할 때 그 단계의 이전 기록을 지운다."""
        if self.dry_run:
            return
        store = self.load_notes()
        if store.pop(stage, None) is not None:
            self.notes_path.parent.mkdir(parents=True, exist_ok=True)
            with self.notes_path.open("w", encoding="utf-8") as fp:
                json.dump(store, fp, ensure_ascii=False, indent=2)

    # --- 실행 기록 -----------------------------------------------------
    def write_manifest(self, stage_results: list[dict[str, Any]]) -> Path | None:
        if self.dry_run:
            return None
        payload = {
            "run_id": self.run_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "config_path": str(self.config.path),
            "config_fingerprint": self.config.fingerprint,
            "scope": self.config.get("scope"),
            "stages": stage_results,
            "notes": self.notes,
        }
        return self.write_json(payload, self.run_dir / "manifest.json")


class Timer:
    def __init__(self) -> None:
        self.elapsed = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.elapsed = time.perf_counter() - self._start
