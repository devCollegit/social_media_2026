"""키워드 보정 에이전트.

1차 분석 결과를 받아 불용어 후보와 표본 편향을 진단하고,
바로 적용 가능한 `stopwords.suggested.txt` 를 만들어 둔다.
"""

from __future__ import annotations

from ..analysis.tuning import render_tuning_report, sample_balance, suggest_stopwords
from .base import Agent, AgentContext, Step, StepResult

TUNING_DIR = "tuning"


class TuningAgent(Agent):
    name = "tuning_agent"
    description = "불용어·검색어 세트를 반복 보정하기 위한 진단 에이전트"
    continue_on_error = True

    def __init__(self, top_n: int = 30, max_abs_z: float = 1.0, min_total: int = 5) -> None:
        self.top_n = top_n
        self.max_abs_z = max_abs_z
        self.min_total = min_total

    def steps(self) -> list[Step]:
        return [
            Step("balance", "표본 균형 진단", self._balance),
            Step("stopwords", "불용어 후보 추출", self._stopwords),
            Step("report", "보정 리포트 생성", self._report),
        ]

    def _balance(self, ctx: AgentContext) -> StepResult:
        report = ctx.data.get("collection_report")
        report_dict = report.to_dict() if hasattr(report, "to_dict") else report
        if report_dict is None:
            try:
                report_dict = ctx.read_json("collection_report.json")
            except FileNotFoundError:
                report_dict = None
        balance = sample_balance(ctx.store.documents(), ctx.plan, report_dict)
        ctx.data["balance"] = balance
        path = ctx.write_json(f"{TUNING_DIR}/표본균형.json", balance)
        summary = "균형" if balance["balanced"] else f"경고 {len(balance['warnings'])}건"
        return StepResult("balance", True, f"{summary} / 문서 {balance['total_documents']}건", [str(path)])

    def _stopwords(self, ctx: AgentContext) -> StepResult:
        names = ctx.plan.segment_names()
        if len(names) < 2:
            return StepResult("stopwords", False, "비교 집단이 2개 미만이라 후보를 낼 수 없습니다.")
        candidates = suggest_stopwords(
            ctx.store.documents(),
            names[0],
            names[1],
            top_n=self.top_n,
            max_abs_z=self.max_abs_z,
            min_total=self.min_total,
        )
        ctx.data["stopword_candidates"] = candidates
        listing = "\n".join(
            ["# 자동 추출된 불용어 후보", "# config/stopwords.txt 로 옮겨 붙인 뒤 분석을 재실행하세요.", ""]
            + [c["term"] for c in candidates]
        )
        path = ctx.write(f"{TUNING_DIR}/stopwords.suggested.txt", listing + "\n")
        return StepResult("stopwords", True, f"후보 {len(candidates)}개", [str(path)])

    def _report(self, ctx: AgentContext) -> StepResult:
        balance = ctx.data.get("balance") or ctx.read_json(f"{TUNING_DIR}/표본균형.json")
        candidates = ctx.data.get("stopword_candidates", [])
        labels = {n: ctx.plan.label_of(n) for n in ctx.plan.segment_names()}
        md = render_tuning_report(candidates, balance, labels)
        path = ctx.write(f"{TUNING_DIR}/키워드_보정.md", md)
        return StepResult("report", True, "보정 리포트 생성", [str(path)])
