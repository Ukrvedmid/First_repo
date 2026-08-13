import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path('/data/agent.db')


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS seen_jobs (
            fingerprint TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            first_seen_at TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS job_summaries (
            cache_key TEXT PRIMARY KEY,
            summary_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    conn.commit()
    return conn


def has_seen(fingerprint: str) -> bool:
    with connect() as conn:
        row = conn.execute('SELECT 1 FROM seen_jobs WHERE fingerprint = ?', (fingerprint,)).fetchone()
        return row is not None


def mark_seen(fingerprint: str, source: str, title: str, url: str, first_seen_at: str):
    with connect() as conn:
        conn.execute('''
            INSERT OR IGNORE INTO seen_jobs
            (fingerprint, source, title, url, first_seen_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (fingerprint, source, title, url, first_seen_at))
        conn.commit()


def get_cached_summary(cache_key: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            'SELECT summary_json FROM job_summaries WHERE cache_key = ?',
            (cache_key,),
        ).fetchone()
    if row is None:
        return None
    try:
        value = json.loads(row[0])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def save_cached_summary(cache_key: str, summary: dict) -> None:
    payload = json.dumps(summary, ensure_ascii=False, sort_keys=True)
    created_at = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        conn.execute('''
            INSERT INTO job_summaries (cache_key, summary_json, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                summary_json = excluded.summary_json,
                created_at = excluded.created_at
        ''', (cache_key, payload, created_at))
        conn.commit()
