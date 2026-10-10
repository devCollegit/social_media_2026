"""소셜 정보 수집 컨트롤러.

여러 수집기를 등록해 두고 연구 계획(ResearchPlan)에 정의된 작업을
- 소스별 호출 간격 제어
- 실패 시 재시도(백오프)
- 중복 제거
- SQLite 저장
- 수집 리포트 생성
까지 한 번에 처리한다.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable

from ..collectors.base import BaseCollector, CollectorError, CollectorUnavailable
from ..config import ResearchPlan
from ..models import CollectionReport, Document, QueryTask, now_iso
from ..storage import DocumentStore

Logger = Callable[[str], None]


class CollectionController:
    def __init__(
        self,
        store: DocumentStore,
        collectors: Iterable[BaseCollector] | None = None,
        logger: Logger | None = None,
    ) -> None:
        self.store = store
        self.collectors: dict[str, BaseCollector] = {}
        self.logger: Logger = logger or (lambda msg: None)
        self._last_call: dict[str, float] = {}
        for collector in collectors or []:
            self.register(collector)

    # --- 등록 ---------------------------------------------------------
    def register(self, collector: BaseCollector) -> None:
        self.collectors[collector.name] = collector

    def available_sources(self) -> dict[str, str]:
        """사용 가능한 소스 -> "" / 사용 불가 소스 -> 사유."""
        status = {}
        for name, collector in self.collectors.items():
            ok, reason = collector.available()
            status[name] = "" if ok else reason
        return status

    # --- 호출 제어 ----------------------------------------------------
    def _throttle(self, collector: BaseCollector) -> None:
        interval = collector.min_interval
        if interval <= 0:
            return
        last = self._last_call.get(collector.name)
        if last is not None:
            wait = interval - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_call[collector.name] = time.monotonic()

    def _fetch(self, collector: BaseCollector, task: QueryTask, retries: int) -> list[Document]:
        attempt = 0
        while True:
            self._throttle(collector)
            try:
                return list(collector.collect(task))
            except CollectorUnavailable:
                raise
            except CollectorError as exc:
                attempt += 1
                if attempt > retries:
                    raise
                backoff = 2**attempt * 0.5
                self.logger(f"  재시도 {attempt}/{retries} ({exc}) - {backoff:.1f}s 대기")
                time.sleep(backoff)

    # --- 실행 ---------------------------------------------------------
    def run(self, plan: ResearchPlan, sources: list[str] | None = None) -> CollectionReport:
        report = CollectionReport(started_at=now_iso())
        tasks = plan.tasks(sources)
        report.tasks = len(tasks)

        disabled: dict[str, str] = {}
        for name, reason in self.available_sources().items():
            if reason:
                disabled[name] = reason
        report.skipped_sources.update(disabled)

        for task in tasks:
            collector = self.collectors.get(task.source)
            if collector is None:
                report.skipped_sources.setdefault(task.source, "등록되지 않은 수집기")
                continue
            if task.source in disabled:
                continue

            stat = report.stat(task.source)
            stat.requested += 1
            self.logger(f"[수집] {task.key} (limit={task.limit})")

            try:
                documents = self._fetch(collector, task, plan.max_retries)
            except CollectorUnavailable as exc:
                disabled[task.source] = str(exc)
                report.skipped_sources[task.source] = str(exc)
                self.logger(f"  사용 불가 → 이후 작업 건너뜀: {exc}")
                continue
            except CollectorError as exc:
                stat.errors.append(f"{task.query}: {exc}")
                report.task_stats.append(
                    {
                        "source": task.source,
                        "segment": task.segment,
                        "query": task.query,
                        "fetched": 0,
                        "stored": 0,
                        "duplicated": 0,
                        "error": str(exc),
                    }
                )
                self.logger(f"  실패: {exc}")
                continue

            stored, duplicated = self.store.add_many(documents)
            report.task_stats.append(
                {
                    "source": task.source,
                    "segment": task.segment,
                    "query": task.query,
                    "fetched": len(documents),
                    "stored": stored,
                    "duplicated": duplicated,
                }
            )
            stat.fetched += len(documents)
            stat.stored += stored
            stat.duplicated += duplicated
            report.fetched += len(documents)
            report.stored += stored
            report.duplicated += duplicated
            self.logger(f"  수집 {len(documents)}건 / 신규 {stored}건 / 중복 {duplicated}건")

            if plan.request_interval:
                time.sleep(plan.request_interval)

        report.finished_at = now_iso()
        return report
