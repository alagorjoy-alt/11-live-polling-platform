"""SQLite access layer: schema, connections and a transaction helper."""
import sqlite3
from contextlib import contextmanager

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS polls (
    id          TEXT PRIMARY KEY,
    question    TEXT NOT NULL,
    admin_token TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    closes_at   TEXT,
    is_closed   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS options (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_id  TEXT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    label    TEXT NOT NULL,
    position INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS votes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_id    TEXT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    option_id  INTEGER NOT NULL REFERENCES options(id) ON DELETE CASCADE,
    voter_id   TEXT NOT NULL,
    ip_hash    TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (poll_id, voter_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_votes_poll_ip
    ON votes(poll_id, ip_hash) WHERE ip_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_votes_option ON votes(option_id);
CREATE INDEX IF NOT EXISTS ix_options_poll ON options(poll_id);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.database_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db():
    """Open a connection, commit on success, roll back on error, always close."""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    conn = get_conn()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
