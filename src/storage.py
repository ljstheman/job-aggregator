"""SQLite 저장 계층."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.models import JobPosting

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    career_level TEXT,
    employment_type TEXT,
    description TEXT,
    tags TEXT,
    posted_at TEXT,
    deadline TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    raw_json TEXT,
    UNIQUE(source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_postings_url ON postings(url);
CREATE INDEX IF NOT EXISTS idx_postings_last_seen ON postings(last_seen_at);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def upsert_posting(conn: sqlite3.Connection, posting: JobPosting) -> bool:
    """공고를 저장/갱신한다. 새로 추가된 경우 True를 반환한다."""
    ts = now_iso()
    cur = conn.execute(
        "SELECT id FROM postings WHERE source = ? AND external_id = ?",
        (posting.source, posting.external_id),
    )
    row = cur.fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO postings (
                source, external_id, url, title, company, location, career_level,
                employment_type, description, tags, posted_at, deadline,
                first_seen_at, last_seen_at, fetched_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                posting.source, posting.external_id, posting.url, posting.title,
                posting.company, posting.location, posting.career_level,
                posting.employment_type, posting.description, posting.tags_json(),
                posting.posted_at, posting.deadline, ts, ts, ts, posting.raw_json,
            ),
        )
        conn.commit()
        return True

    conn.execute(
        """
        UPDATE postings
        SET url = ?, title = ?, company = ?, location = ?, career_level = ?,
            employment_type = ?, description = ?, tags = ?, posted_at = ?,
            deadline = ?, last_seen_at = ?, fetched_at = ?, raw_json = ?
        WHERE source = ? AND external_id = ?
        """,
        (
            posting.url, posting.title, posting.company, posting.location,
            posting.career_level, posting.employment_type, posting.description,
            posting.tags_json(), posting.posted_at, posting.deadline, ts, ts,
            posting.raw_json, posting.source, posting.external_id,
        ),
    )
    conn.commit()
    return False


def _row_to_posting(row: sqlite3.Row) -> JobPosting:
    return JobPosting(
        source=row["source"],
        external_id=row["external_id"],
        url=row["url"],
        title=row["title"],
        company=row["company"],
        location=row["location"] or "",
        career_level=row["career_level"] or "",
        employment_type=row["employment_type"] or "",
        description=row["description"] or "",
        tags=json.loads(row["tags"]) if row["tags"] else [],
        posted_at=row["posted_at"],
        deadline=row["deadline"],
        fetched_at=row["fetched_at"],
        raw_json=row["raw_json"] or "",
    )


def query_postings(conn: sqlite3.Connection) -> list[JobPosting]:
    cur = conn.execute("SELECT * FROM postings ORDER BY last_seen_at DESC")
    return [_row_to_posting(row) for row in cur.fetchall()]


def count_postings(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT COUNT(*) AS c FROM postings")
    return cur.fetchone()["c"]
