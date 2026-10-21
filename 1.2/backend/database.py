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

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    category TEXT CHECK(category IN ('financas', 'estudos', 'atividades', 'pessoal')) NOT NULL DEFAULT 'pessoal',
    goal_type TEXT CHECK(goal_type IN ('monetaria', 'quantitativa', 'qualitativa')) NOT NULL DEFAULT 'quantitativa',
    target_value REAL,
    current_value REAL DEFAULT 0.00,
    unit TEXT DEFAULT 'R$',
    deadline TEXT,
    status TEXT CHECK(status IN ('em_andamento', 'alcancada', 'pausada')) DEFAULT 'em_andamento',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo', 'in_progress', 'done', 'archived')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high', 'urgent')),
    due_date TEXT,
    category TEXT DEFAULT 'Geral',
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    goal_id INTEGER REFERENCES goals(id) ON DELETE SET NULL,
    recurrence TEXT NOT NULL DEFAULT 'nenhuma',
    streak_count INTEGER DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS task_completions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    completed_at TEXT NOT NULL,
    pomodoros_completed INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_task_completions_task_id ON task_completions(task_id);
CREATE INDEX IF NOT EXISTS idx_task_completions_completed_at ON task_completions(completed_at);

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

CREATE TABLE IF NOT EXISTS recurring_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT CHECK(type IN ('receita', 'despesa')) NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    amount_cents INTEGER NOT NULL DEFAULT 0,
    category TEXT DEFAULT 'Outros',
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    account TEXT DEFAULT 'Conta Corrente',
    frequency TEXT CHECK(frequency IN ('semanal', 'mensal', 'anual')) DEFAULT 'mensal',
    day_of_month INTEGER CHECK(day_of_month BETWEEN 1 AND 31) DEFAULT 1,
    start_date TEXT NOT NULL,
    end_date TEXT,
    is_active INTEGER DEFAULT 1,
    last_generated_date TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_recurring_active ON recurring_rules(is_active);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    amount REAL DEFAULT 0.0,
    type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
    category TEXT NOT NULL,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    goal_id INTEGER REFERENCES goals(id) ON DELETE SET NULL,
    recurring_rule_id INTEGER REFERENCES recurring_rules(id) ON DELETE SET NULL,
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

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    folder TEXT DEFAULT 'Geral',
    tags TEXT DEFAULT '',
    is_pinned INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notes_folder ON notes(folder);
CREATE INDEX IF NOT EXISTS idx_notes_pinned ON notes(is_pinned);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    mime_type TEXT NOT NULL,
    entity_type TEXT CHECK(entity_type IN ('task', 'note', 'idea', 'transaction')) NOT NULL,
    entity_id INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_attachments_entity ON attachments(entity_type, entity_id);
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

        # Idempotent Expand-and-Contract migrations for existing v1.0 & v1.1 databases
        _ensure_column(conn, 'tasks', 'pomodoro_duration_minutes', 'INTEGER DEFAULT 25')
        _ensure_column(conn, 'tasks', 'category_id', 'INTEGER REFERENCES categories(id) ON DELETE SET NULL')
        _ensure_column(conn, 'tasks', 'goal_id', 'INTEGER REFERENCES goals(id) ON DELETE SET NULL')
        _ensure_column(conn, 'tasks', 'recurrence', "TEXT NOT NULL DEFAULT 'nenhuma'")
        _ensure_column(conn, 'tasks', 'completed_at', 'TEXT')

        _ensure_column(conn, 'time_sessions', 'type', "TEXT DEFAULT 'pomodoro'")
        _ensure_column(conn, 'time_sessions', 'created_at', 'TEXT')

        _ensure_column(conn, 'transactions', 'amount', 'REAL DEFAULT 0.0')
        _ensure_column(conn, 'transactions', 'category_id', 'INTEGER REFERENCES categories(id) ON DELETE SET NULL')
        _ensure_column(conn, 'transactions', 'task_id', 'INTEGER REFERENCES tasks(id) ON DELETE SET NULL')
        _ensure_column(conn, 'transactions', 'goal_id', 'INTEGER REFERENCES goals(id) ON DELETE SET NULL')
        _ensure_column(conn, 'transactions', 'recurring_rule_id', 'INTEGER REFERENCES recurring_rules(id) ON DELETE SET NULL')
        _ensure_column(conn, 'transactions', 'transaction_date', 'TEXT')
        _ensure_column(conn, 'transactions', 'is_recurring', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(conn, 'transactions', 'recurrence', "TEXT NOT NULL DEFAULT 'nenhuma'")
        _ensure_column(conn, 'transactions', 'parent_recurring_id', 'INTEGER')

        _ensure_column(conn, 'ideas', 'status', "TEXT NOT NULL DEFAULT 'bruta'")
        _ensure_column(conn, 'ideas', 'converted_task_id', 'INTEGER REFERENCES tasks(id) ON DELETE SET NULL')

        _ensure_column(conn, 'recurring_rules', 'amount_cents', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(conn, 'recurring_rules', 'category', "TEXT DEFAULT 'Outros'")
        _ensure_column(conn, 'recurring_rules', 'account', "TEXT DEFAULT 'Conta Corrente'")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_status ON tasks(due_date, status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_recurring ON transactions(is_recurring);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ideas_status ON ideas(status);")

        now = datetime.now().isoformat()
        for name, color, icon in DEFAULT_CATEGORIES:
            conn.execute(
                "INSERT OR IGNORE INTO categories (name, color, icon, created_at) VALUES (?, ?, ?, ?)",
                (name, color, icon, now)
            )

        _ensure_column(conn, 'tasks', 'streak_count', 'INTEGER DEFAULT 0')

        # Migrate any legacy v1.1 root recurring transactions into recurring_rules
        legacy_rec = conn.execute("""
            SELECT * FROM transactions
            WHERE is_recurring = 1
              AND recurring_rule_id IS NULL
              AND (parent_recurring_id IS NULL OR parent_recurring_id = 0)
        """).fetchall()
        for row in legacy_rec:
            r_type = 'receita' if row['type'] == 'income' else 'despesa'
            amt_cents = int(row['amount_cents'] or 0)
            amt_val = round(amt_cents / 100.0, 2)
            freq = row['recurrence'] if row['recurrence'] in ('semanal', 'mensal', 'anual') else 'mensal'
            try:
                day_m = min(31, max(1, int((row['date'] or '2026-01-01').split('-')[2][:2])))
            except (IndexError, ValueError):
                day_m = 1
            cur = conn.execute("""
                INSERT INTO recurring_rules (
                    type, description, amount, amount_cents, category, category_id,
                    account, frequency, day_of_month, start_date, is_active,
                    last_generated_date, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (
                r_type, row['description'], amt_val, amt_cents, row['category'],
                row['category_id'], row['account'], freq, day_m, row['date'],
                row['date'], now
            ))
            conn.execute(
                "UPDATE transactions SET recurring_rule_id = ? WHERE id = ?",
                (cur.lastrowid, row['id'])
            )

        # Consolidate legacy duplicate recurring task cards into Master Cards with streaks and completion logs
        all_rec_tasks = conn.execute("""
            SELECT id, title, recurrence, status, due_date, completed_pomodoros, completed_at
            FROM tasks
            WHERE recurrence != 'nenhuma'
            ORDER BY LOWER(TRIM(title)), id ASC
        """).fetchall()

        from collections import defaultdict
        grouped_tasks = defaultdict(list)
        for t in all_rec_tasks:
            t_key = (t['title'].strip().lower(), t['recurrence'])
            grouped_tasks[t_key].append(t)

        for t_key, instances in grouped_tasks.items():
            if len(instances) > 1:
                # Active master card preference: non-done with max id, or latest id
                active_cards = [i for i in instances if i['status'] in ('todo', 'in_progress')]
                master = active_cards[-1] if active_cards else instances[-1]
                streak = 0
                for inst in instances:
                    if inst['id'] != master['id']:
                        if inst['status'] == 'done':
                            c_date = inst['completed_at'] or inst['due_date'] or now
                            conn.execute("""
                                INSERT INTO task_completions (task_id, completed_at, pomodoros_completed)
                                VALUES (?, ?, ?)
                            """, (master['id'], c_date, inst['completed_pomodoros'] or 0))
                            streak += 1
                        # Re-point associated records to master task
                        conn.execute("UPDATE time_sessions SET task_id = ? WHERE task_id = ?", (master['id'], inst['id']))
                        conn.execute("UPDATE attachments SET entity_id = ? WHERE entity_type = 'task' AND entity_id = ?", (master['id'], inst['id']))
                        conn.execute("UPDATE transactions SET task_id = ? WHERE task_id = ?", (master['id'], inst['id']))
                        conn.execute("DELETE FROM tasks WHERE id = ?", (inst['id'],))

                if streak > 0:
                    conn.execute("""
                        UPDATE tasks
                        SET streak_count = COALESCE(streak_count, 0) + ?
                        WHERE id = ?
                    """, (streak, master['id']))

        conn.commit()
    finally:
        conn.close()

def dict_from_row(row):
    if row is None:
        return None
    return dict(row)
