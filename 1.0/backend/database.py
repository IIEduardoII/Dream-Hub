import sqlite3
import os
from datetime import datetime

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo', 'in_progress', 'done', 'archived')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high', 'urgent')),
    due_date TEXT,
    category TEXT DEFAULT 'Geral',
    estimated_pomodoros INTEGER DEFAULT 1,
    completed_pomodoros INTEGER DEFAULT 0,
    pomodoro_duration_minutes INTEGER DEFAULT 25,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);

CREATE TABLE IF NOT EXISTS time_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    session_type TEXT NOT NULL DEFAULT 'focus' CHECK(session_type IN ('focus', 'short_break', 'long_break')),
    duration_minutes INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    completed INTEGER NOT NULL DEFAULT 1,
    notes TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_time_sessions_started ON time_sessions(started_at);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
    category TEXT NOT NULL,
    account TEXT NOT NULL DEFAULT 'Carteira',
    date TEXT NOT NULL,
    is_settled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);

CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    stage TEXT NOT NULL DEFAULT 'raw' CHECK(stage IN ('raw', 'evaluating', 'in_action', 'archived')),
    tags TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ideas_stage ON ideas(stage);
"""

def get_db_connection(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

get_db = get_db_connection

def init_db(db_path: str):
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = get_db_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        # Migração idempotente para bases existentes
        cursor = conn.execute("PRAGMA table_info(tasks)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'pomodoro_duration_minutes' not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN pomodoro_duration_minutes INTEGER DEFAULT 25")
        conn.commit()
    finally:
        conn.close()

def dict_from_row(row):
    if row is None:
        return None
    return dict(row)
