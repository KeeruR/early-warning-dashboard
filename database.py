"""
SQLite storage layer.

A small local database is enough for a proof of concept. It stores the
synthetic student records, the calculated priority scores, advisors'
review decisions and an audit log, so data now survives an app restart
(in the Report 2 prototype, reviewed status was lost when a session ended).
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username        TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'advisor',
    password_hash   TEXT NOT NULL,
    salt            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS students (
    student_id                      TEXT PRIMARY KEY,
    advisor_username                TEXT NOT NULL REFERENCES users(username),
    course                          TEXT NOT NULL,
    year_level                      INTEGER NOT NULL,
    demographic_group               TEXT NOT NULL,
    registration_days_before_start  INTEGER NOT NULL,
    canvas_logins_per_week          INTEGER NOT NULL,
    days_since_last_login           INTEGER NOT NULL,
    submitted_early_assessment      INTEGER NOT NULL,
    early_assessment_days_late      INTEGER NOT NULL,
    forum_posts_count               INTEGER NOT NULL,
    loaded_at                       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS priority_scores (
    student_id      TEXT PRIMARY KEY REFERENCES students(student_id) ON DELETE CASCADE,
    score           INTEGER NOT NULL,
    band            TEXT NOT NULL,
    reasons_json    TEXT NOT NULL,
    rule_version    TEXT NOT NULL,
    scored_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id        TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    advisor_username  TEXT NOT NULL REFERENCES users(username),
    next_step         TEXT NOT NULL,
    reviewed_at       TEXT NOT NULL,
    is_active         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS audit_log (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at   TEXT NOT NULL,
    username    TEXT,
    action      TEXT NOT NULL,
    detail      TEXT
);

CREATE INDEX IF NOT EXISTS idx_students_advisor ON students(advisor_username);
CREATE INDEX IF NOT EXISTS idx_reviews_student ON reviews(student_id, is_active);
"""


def resolve_path(db_path=None) -> Path:
    """Explicit path, else the EWD_DB_PATH environment variable (used by the
    tests so they never touch the demo database), else data/early_warning.db."""
    path = Path(db_path or os.environ.get("EWD_DB_PATH") or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connect(db_path=None):
    """Open a connection, commit on success, roll back on any error."""
    conn = sqlite3.connect(resolve_path(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_schema(db_path=None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
