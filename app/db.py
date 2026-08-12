import sqlite3
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
