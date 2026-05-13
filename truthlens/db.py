"""
SQLite storage for processed posts and generated reports.
"""

import sqlite3
import json
from datetime import datetime, timezone

import config


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            author TEXT,
            content TEXT NOT NULL,
            url TEXT,
            score INTEGER DEFAULT 0,
            fetched_at TEXT NOT NULL,
            processed INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id TEXT NOT NULL REFERENCES posts(id),
            claims_json TEXT,
            verdicts_json TEXT,
            autopsy_md TEXT,
            autopsy_html TEXT,
            overall_verdict TEXT,
            confidence TEXT,
            created_at TEXT DEFAULT 0,
            published INTEGER DEFAULT 0
        );
                       
        CREATE INDEX IF NOT EXISTS idx_posts_processed ON posts(processed);
        CREATE INDEX IF NOT EXISTS idx_reports_published ON reports(published);
    """)
    conn.close()


def post_exists(post_id: str) -> bool:
    conn = _connect()
    row = conn.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone()
    conn.close()
    return row is not None


def save_post(
    post_id: str,
    platform: str,
    author: str,
    content: str,
    url: str,
    score: int
) -> None:
    conn = _connect()
    conn.execute("""
        INSERT OR IGNORE INTO posts (id, platform, author, content, url, score, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (post_id, platform, author, content, url, score,
        datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def mark_processed(post_id: str) -> None:
    conn = _connect()
    conn.execute("UPDATE posts SET processed = 1 WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()


def get_unprocessed_posts() -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM posts WHERE processed = 0 ORDER BY score DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_report(
    post_id: str,
    claims: list[str],
    verdicts: list[dict],
    autopsy_md: str,
    autopsy_html: str,
    overall_verdict: str,
    confidence: str
) -> int:
    conn = _connect()
    cur = conn.execute(
        """INSERT INTO reports
           (post_id, claims_json, verdicts_json, autopsy_md, autopsy_html,
            overall_verdict, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            post_id,
            json.dumps(claims),
            json.dumps(verdicts),
            autopsy_md,
            autopsy_html,
            overall_verdict,
            confidence,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    report_id = cur.lastrowid
    conn.commit()
    conn.close()
    return report_id


def get_unpublished_reports() -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM reports WHERE published = 0 ORDER BY created_at"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_published(report_id: int) -> None:
    conn = _connect()
    conn.execute("UPDATE reports SET published = 1 WHERE id = ?", (report_id,))
    conn.commit()
    conn.close()
    