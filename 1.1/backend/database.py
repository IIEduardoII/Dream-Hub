import sqlite3
import os
from datetime import datetime

PRAGMAS_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA temp_store = MEMORY;
PRAGMA cache_size = -8000;
PRAGMA busy_timeout = 5000;
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#2563EB',
    icon TEXT DEFAULT 'folder',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo', 'in_progress', 'done', 'archived')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high', 'urgent')),
    due_date TEXT,
    category TEXT DEFAULT 'Geral',
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    recurrence TEXT NOT NULL DEFAULT 'nenhuma',
    estimated_pomodoros INTEGER DEFAULT 1,
    completed_pomodoros INTEGER DEFAULT 0,
    pomodoro_duration_minutes INTEGER DEFAULT 25,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_due_status ON tasks(due_date, status);

CREATE TABLE IF NOT EXISTS time_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    session_type TEXT NOT NULL DEFAULT 'focus' CHECK(session_type IN ('focus', 'short_break', 'long_break')),
    type TEXT DEFAULT 'pomodoro',
    duration_minutes INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    completed INTEGER NOT NULL DEFAULT 1,
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_time_sessions_started ON time_sessions(started_at);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    amount REAL DEFAULT 0.0,
    type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
    category TEXT NOT NULL,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    account TEXT NOT NULL DEFAULT 'Carteira',
    date TEXT NOT NULL,
    transaction_date TEXT,
    is_settled INTEGER NOT NULL DEFAULT 1,
    is_recurring INTEGER NOT NULL DEFAULT 0,
    recurrence TEXT NOT NULL DEFAULT 'nenhuma',
    parent_recurring_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);

CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    stage TEXT NOT NULL DEFAULT 'raw' CHECK(stage IN ('raw', 'evaluating', 'in_action', 'archived')),
    status TEXT NOT NULL DEFAULT 'bruta',
    converted_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    tags TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ideas_stage ON ideas(stage);
"""

DEFAULT_CATEGORIES = [
    ('Geral', '#38bdf8', 'folder'),
    ('Trabalho', '#2563eb', 'briefcase'),
    ('Estudo', '#a78bfa', 'book'),
    ('Infraestrutura', '#06b6d4', 'server'),
    ('Saúde', '#10b981', 'heart'),
    ('Alimentação', '#f59e0b', 'utensils'),
    ('Moradia', '#ef4444', 'home'),
    ('Transporte', '#ec4899', 'car'),
    ('Salário', '#34d399', 'wallet'),
    ('Investimento', '#8b5cf6', 'trending-up'),
    ('Lazer', '#fbbf24', 'smile'),
    ('Educação', '#6366f1', 'graduation-cap'),
    ('Outros', '#64748b', 'tag'),
]

def get_db_connection(db_path: str):
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA cache_size = -8000;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn

get_db = get_db_connection

def _ensure_column(conn: sqlite3.Connection, table: str, col_name: str, col_def: str):
    cursor = conn.execute(f"PRAGMA table_info({table})")
    existing = [row['name'] for row in cursor.fetchall()]
    if col_name not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")

def init_db(db_path: str):
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = get_db_connection(db_path)
    try:
        conn.executescript(PRAGMAS_SQL)
        conn.executescript(SCHEMA_SQL)

        # Idempotent Expand-and-Contract migrations for existing v1.0 databases
        _ensure_column(conn, 'tasks', 'pomodoro_duration_minutes', 'INTEGER DEFAULT 25')
        _ensure_column(conn, 'tasks', 'category_id', 'INTEGER REFERENCES categories(id) ON DELETE SET NULL')
        _ensure_column(conn, 'tasks', 'recurrence', "TEXT NOT NULL DEFAULT 'nenhuma'")
        _ensure_column(conn, 'tasks', 'completed_at', 'TEXT')

        _ensure_column(conn, 'time_sessions', 'type', "TEXT DEFAULT 'pomodoro'")
        _ensure_column(conn, 'time_sessions', 'created_at', 'TEXT')

        _ensure_column(conn, 'transactions', 'amount', 'REAL DEFAULT 0.0')
        _ensure_column(conn, 'transactions', 'category_id', 'INTEGER REFERENCES categories(id) ON DELETE SET NULL')
        _ensure_column(conn, 'transactions', 'task_id', 'INTEGER REFERENCES tasks(id) ON DELETE SET NULL')
        _ensure_column(conn, 'transactions', 'transaction_date', 'TEXT')
        _ensure_column(conn, 'transactions', 'is_recurring', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(conn, 'transactions', 'recurrence', "TEXT NOT NULL DEFAULT 'nenhuma'")
        _ensure_column(conn, 'transactions', 'parent_recurring_id', 'INTEGER')

        _ensure_column(conn, 'ideas', 'status', "TEXT NOT NULL DEFAULT 'bruta'")
        _ensure_column(conn, 'ideas', 'converted_task_id', 'INTEGER REFERENCES tasks(id) ON DELETE SET NULL')

        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_status ON tasks(due_date, status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_recurring ON transactions(is_recurring);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ideas_status ON ideas(status);")

        now = datetime.now().isoformat()
        for name, color, icon in DEFAULT_CATEGORIES:
            conn.execute(
                "INSERT OR IGNORE INTO categories (name, color, icon, created_at) VALUES (?, ?, ?, ?)",
                (name, color, icon, now)
            )

        conn.commit()
    finally:
        conn.close()

def dict_from_row(row):
    if row is None:
        return None
    return dict(row)
