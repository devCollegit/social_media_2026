"""단계 정의와 실행 순서."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import Config
from .context import RunContext, StageError, Timer


@dataclass(frozen=True)
class Stage:
    name: str
    title: str
    run: Callable[[RunContext], dict[str, Any]]
    inputs: Callable[[Config], list[Path]]
    outputs: Callable[[Config], list[Path]]

    def is_fresh(self, config: Config) -> bool:
        """산출물이 모두 있고 입력보다 새것이면 True."""
        outputs = self.outputs(config)
        if not outputs or not all(p.exists() for p in outputs):
            return False
        inputs = [p for p in self.inputs(config) if p.exists()]
        if not inputs:
            return True
        newest_input = max(p.stat().st_mtime for p in inputs)
        oldest_output = min(p.stat().st_mtime for p in outputs)
        return oldest_output >= newest_input


def build_stages() -> list[Stage]:
    from .stages import (
        s01_collect,
        s02_clean,
        s03_sentiment,
        s04_market,
        s05_aggregate,
        s06_merge,
        s07_analyze,
        s08_report,
    )

    modules = [
        s01_collect,
        s02_clean,
        s03_sentiment,
        s04_market,
        s05_aggregate,
        s06_merge,
        s07_analyze,
        s08_report,
    ]
    return [
        Stage(
            name=m.NAME,
            title=m.TITLE,
            run=m.run,
            inputs=m.inputs,
            outputs=m.outputs,
        )
        for m in modules
    ]


STAGE_ORDER = [
    "collect",
    "clean",
    "sentiment",
    "market",
    "aggregate",
    "merge",
    "analyze",
    "report",
]


def select_stages(
    stages: list[Stage],
    only: list[str] | None = None,
    start: str | None = None,
    until: str | None = None,
) -> list[Stage]:
    names = [s.name for s in stages]

    def index_of(name: str) -> int:
        if name not in names:
            raise StageError(
                f"알 수 없는 단계 '{name}'. 사용 가능한 단계: {', '.join(names)}"
            )
        return names.index(name)

    if only:
        for name in only:
            index_of(name)
        return [s for s in stages if s.name in only]

    lo = index_of(start) if start else 0
    hi = index_of(until) + 1 if until else len(stages)
    if lo >= hi:
        raise StageError("--from 단계가 --until 단계보다 뒤에 있습니다.")
    return stages[lo:hi]


def execute(ctx: RunContext, stages: list[Stage]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    total = len(stages)

    for i, stage in enumerate(stages, start=1):
        header = f"[{i}/{total}] {stage.name} — {stage.title}"

        if ctx.dry_run:
            state = "최신" if stage.is_fresh(ctx.config) else "실행 필요"
            ctx.logger.info("%s  (%s)", header, state)
            results.append({"stage": stage.name, "status": "dry-run", "state": state})
            continue

        if not ctx.force and stage.is_fresh(ctx.config):
            ctx.logger.info("%s  → 건너뜀 (산출물이 최신)", header)
            results.append({"stage": stage.name, "status": "skipped"})
            continue

        ctx.logger.info("%s", header)
        ctx.current_stage = stage.name
        ctx.reset_stage_notes(stage.name)
        with Timer() as timer:
            metrics = stage.run(ctx) or {}
        ctx.metrics[stage.name] = metrics
        results.append(
            {
                "stage": stage.name,
                "status": "ok",
                "seconds": round(timer.elapsed, 2),
                "metrics": metrics,
                "outputs": [ctx.rel(p) for p in stage.outputs(ctx.config)],
            }
        )
        ctx.logger.info("      완료 (%.2fs)", timer.elapsed)

    return results
