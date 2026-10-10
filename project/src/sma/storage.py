"""수집 결과를 보관하는 SQLite 저장소."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path

from .models import Document

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id       TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    query        TEXT NOT NULL,
    segment      TEXT NOT NULL,
    title        TEXT,
    text         TEXT,
    url          TEXT,
    place_name   TEXT,
    region       TEXT,
    category     TEXT,
    lang         TEXT,
    rating       REAL,
    published_at TEXT,
    collected_at TEXT,
    raw          TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_segment ON documents(segment);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source);
CREATE INDEX IF NOT EXISTS idx_documents_place ON documents(place_name);
"""

COLUMNS = (
    "doc_id, source, query, segment, title, text, url, place_name, region, "
    "category, lang, rating, published_at, collected_at, raw"
)


class DocumentStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "DocumentStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def exists(self, doc_id: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM documents WHERE doc_id = ?", (doc_id,))
        return cur.fetchone() is not None

    def add(self, document: Document) -> bool:
        """신규 저장이면 True, 중복이면 False."""
        row = document.to_row()
        placeholders = ", ".join(f":{c.strip()}" for c in COLUMNS.split(","))
        cur = self.conn.execute(
            f"INSERT OR IGNORE INTO documents ({COLUMNS}) VALUES ({placeholders})", row
        )
        return cur.rowcount > 0

    def add_many(self, documents: Iterable[Document]) -> tuple[int, int]:
        stored = duplicated = 0
        for doc in documents:
            if self.add(doc):
                stored += 1
            else:
                duplicated += 1
        self.conn.commit()
        return stored, duplicated

    def commit(self) -> None:
        self.conn.commit()

    def documents(self, segment: str | None = None, source: str | None = None) -> Iterator[Document]:
        sql = f"SELECT {COLUMNS} FROM documents"
        where, params = [], []
        if segment:
            where.append("segment = ?")
            params.append(segment)
        if source:
            where.append("source = ?")
            params.append(source)
        if where:
            sql += " WHERE " + " AND ".join(where)
        for row in self.conn.execute(sql, params):
            yield Document.from_row(dict(row))

    def count(self, segment: str | None = None) -> int:
        if segment:
            cur = self.conn.execute("SELECT COUNT(*) FROM documents WHERE segment = ?", (segment,))
        else:
            cur = self.conn.execute("SELECT COUNT(*) FROM documents")
        return int(cur.fetchone()[0])

    def clear(self) -> None:
        self.conn.execute("DELETE FROM documents")
        self.conn.commit()
