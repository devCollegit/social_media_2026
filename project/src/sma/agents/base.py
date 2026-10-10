"""에이전트 실행 기반 골격.

에이전트 = 순차적인 Step 목록 + 공유 컨텍스트.
각 Step 은 컨텍스트를 받아 산출물(artifact)을 남기고 요약 문자열을 반환한다.
실패한 Step 은 기록만 남기고 다음 Step 으로 넘어갈지(continue_on_error) 선택할 수 있다.
"""

from __future__ import annotations

import json
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import ResearchPlan
from ..models import now_iso
from ..storage import DocumentStore


@dataclass
class AgentContext:
    plan: ResearchPlan
    store: DocumentStore
    output_dir: Path
    logger: Callable[[str], None] = print
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, relative_path: str, content: str) -> Path:
        path = self.output_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def write_json(self, relative_path: str, payload: Any) -> Path:
        return self.write(relative_path, json.dumps(payload, ensure_ascii=False, indent=2))

    def read_json(self, relative_path: str) -> Any:
        path = self.output_dir / relative_path
        if not path.exists():
            raise FileNotFoundError(f"선행 산출물이 없습니다: {path}")
        return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class StepResult:
    name: str
    ok: bool
    summary: str
    artifacts: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class Step:
    name: str
    description: str
    action: Callable[[AgentContext], StepResult]


@dataclass
class AgentRun:
    agent: str
    started_at: str
    finished_at: str = ""
    results: list[StepResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    def artifacts(self) -> list[str]:
        return [a for r in self.results for a in r.artifacts]

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "ok": self.ok,
            "steps": [
                {
                    "name": r.name,
                    "ok": r.ok,
                    "summary": r.summary,
                    "artifacts": r.artifacts,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


class Agent:
    name = "agent"
    description = ""
    continue_on_error = False

    def steps(self) -> list[Step]:
        raise NotImplementedError

    def run(self, ctx: AgentContext) -> AgentRun:
        run = AgentRun(agent=self.name, started_at=now_iso())
        ctx.logger(f"\n=== {self.name} 시작 ===")
        for index, step in enumerate(self.steps(), start=1):
            ctx.logger(f"[{index}] {step.name} - {step.description}")
            try:
                result = step.action(ctx)
            except Exception as exc:  # 단계 실패를 전체 실패로 만들지 않는다
                result = StepResult(
                    name=step.name,
                    ok=False,
                    summary=f"실패: {exc}",
                    error=traceback.format_exc(limit=3),
                )
            run.results.append(result)
            ctx.logger(f"    → {result.summary}")
            for artifact in result.artifacts:
                ctx.logger(f"    · 산출물: {artifact}")
            if not result.ok and not self.continue_on_error:
                ctx.logger("    중단 조건 충족 → 에이전트 종료")
                break
        run.finished_at = now_iso()
        ctx.write_json(f"runs/{self.name}.json", run.to_dict())
        ctx.logger(f"=== {self.name} 종료 (성공={run.ok}) ===")
        return run
