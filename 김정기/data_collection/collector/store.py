"""종목별 CSV 저장, 증분 수집 상태, 실패 기록."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from collector.parser import COLUMNS, KST


def _atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8")
    os.replace(tmp, path)


class PostStore:
    """data/raw/posts/<stock_id>.csv 에 글·댓글을 post_id 기준으로 upsert 한다.

    같은 post_id 가 다시 수집되면 최신 값(공감 수·댓글 수·수집 시각)으로 바꾼다.
    작성 시각과 본문은 같은 글이면 변하지 않으므로 행 수는 늘지 않는다.
    """

    def __init__(self, posts_dir: Path) -> None:
        self.dir = posts_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, stock_id: str) -> Path:
        return self.dir / f"{stock_id}.csv"

    def load(self, stock_id: str) -> pd.DataFrame:
        p = self.path(stock_id)
        if not p.exists():
            return pd.DataFrame(columns=COLUMNS)
        # 모든 값을 문자열로 다룬다. 종목코드 앞자리 0, 빈 parent_id·badge 를 그대로 보존하기 위해서다.
        return pd.read_csv(p, dtype=str, keep_default_na=False)

    def upsert(self, stock_id: str, rows: Iterable[dict[str, Any]]) -> tuple[int, int]:
        """(신규 행 수, 갱신 행 수)를 돌려준다."""
        new = pd.DataFrame(list(rows), columns=COLUMNS).astype(str)
        if new.empty:
            return 0, 0
        new = new.drop_duplicates("post_id", keep="last")
        old = self.load(stock_id)
        known = set(old["post_id"])
        added = int((~new["post_id"].isin(known)).sum())
        updated = len(new) - added
        merged = pd.concat([old, new], ignore_index=True)
        merged = merged.drop_duplicates("post_id", keep="last")
        merged = merged.sort_values(["created_at", "post_id"]).reset_index(drop=True)
        _atomic_write_csv(merged[COLUMNS], self.path(stock_id))
        return added, updated

    def reply_counts(self, stock_id: str) -> dict[str, int]:
        """재수집 판단용 댓글 수. 서버 표시 수와 실제 저장 수 중 작은 값."""
        df = self.load(stock_id)
        if df.empty:
            return {}
        counts = pd.to_numeric(df["reply_count"], errors="coerce").fillna(0).astype(int)
        saved_replies = df[df["parent_id"] != ""]["parent_id"].value_counts()
        # 부분 실패 후 부모의 서버 reply_count만 저장되어 재시도가 생략되는 것을 막는다.
        return {post_id: min(count, int(saved_replies.get(post_id, 0)))
                for post_id, count in zip(df["post_id"], counts)}


class CollectorState:
    """종목별 마지막 수집 지점. state/collector_state.json."""

    def __init__(self, state_dir: Path) -> None:
        state_dir.mkdir(parents=True, exist_ok=True)
        self.path = state_dir / "collector_state.json"
        self.data: dict[str, dict[str, Any]] = (
            json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        )

    def get(self, stock_id: str) -> dict[str, Any]:
        return self.data.get(stock_id, {})

    def update(self, stock_id: str, max_post_id: int | None, max_created_at: str | None) -> None:
        cur = self.data.setdefault(stock_id, {})
        if max_post_id is not None:
            cur["max_post_id"] = max(int(cur.get("max_post_id", 0)), int(max_post_id))
        if max_created_at is not None:
            cur["max_created_at"] = max(str(cur.get("max_created_at", "")), max_created_at)
        cur["last_run"] = datetime.now(KST).isoformat(timespec="seconds")

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)


class FailureLog:
    """실패한 요청을 logs/failures.csv 에 한 줄씩 남긴다. 다음 실행 때 재시도 대상 확인용."""

    FIELDS = ["time", "stock_id", "stage", "cursor", "error"]

    def __init__(self, logs_dir: Path) -> None:
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.path = logs_dir / "failures.csv"

    def add(self, stock_id: str, stage: str, cursor: Any, error: Exception | str) -> None:
        new_file = not self.path.exists()
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=self.FIELDS)
            if new_file:
                w.writeheader()
            w.writerow({
                "time": datetime.now(KST).isoformat(timespec="seconds"),
                "stock_id": stock_id, "stage": stage, "cursor": "" if cursor is None else cursor,
                "error": str(error)[:500],
            })
