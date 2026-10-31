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
    status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo', 'in_progress', 'done', 'not_done', 'stopped', 'archived')),
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

CREATE TABLE IF NOT EXISTS task_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    execution_date TEXT NOT NULL,
    notes TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_task_history_task_id ON task_history(task_id);
CREATE INDEX IF NOT EXISTS idx_task_history_execution_date ON task_history(execution_date);

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
    source TEXT NOT NULL DEFAULT 'manual',
    external_id TEXT,
    reconciled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);

CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    note_type TEXT NOT NULL DEFAULT 'text',
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
    note_type TEXT NOT NULL DEFAULT 'text',
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

-- ==================== RITMO MODULE TABLES ====================
CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    muscle_group TEXT NOT NULL,
    equipment TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    custom INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_exercises_muscle ON exercises(muscle_group);

CREATE TABLE IF NOT EXISTS routines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    name TEXT NOT NULL,
    target_muscle_groups TEXT DEFAULT '',
    day_of_week INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS routine_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_id INTEGER NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
    exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
    position INTEGER DEFAULT 0,
    sets INTEGER DEFAULT 3,
    reps INTEGER DEFAULT 10,
    rest INTEGER DEFAULT 90,
    target_reps TEXT DEFAULT '8-12'
);

CREATE INDEX IF NOT EXISTS idx_routine_items_routine ON routine_items(routine_id);
CREATE INDEX IF NOT EXISTS idx_routine_items_exercise ON routine_items(exercise_id);

CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    routine_id INTEGER REFERENCES routines(id) ON DELETE SET NULL,
    routine_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    notes TEXT DEFAULT '',
    session_date TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_workouts_started ON workouts(started_at);
CREATE INDEX IF NOT EXISTS idx_workouts_session_date ON workouts(session_date);

CREATE TABLE IF NOT EXISTS workout_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
    exercise_id INTEGER REFERENCES exercises(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    position INTEGER DEFAULT 0,
    rest INTEGER DEFAULT 90,
    notes TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_workout_items_workout ON workout_items(workout_id);
CREATE INDEX IF NOT EXISTS idx_workout_items_exercise ON workout_items(exercise_id);

CREATE TABLE IF NOT EXISTS workout_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES workout_items(id) ON DELETE CASCADE,
    position INTEGER DEFAULT 0,
    reps INTEGER DEFAULT 0,
    load REAL DEFAULT 0,
    done INTEGER DEFAULT 0,
    rpe REAL,
    completed_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_workout_sets_item ON workout_sets(item_id);

CREATE TABLE IF NOT EXISTS body_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    weight REAL NOT NULL,
    notes TEXT DEFAULT '',
    recorded_at TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_body_metrics_date ON body_metrics(recorded_at);

CREATE TABLE IF NOT EXISTS evolution_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    metric_id INTEGER REFERENCES body_metrics(id) ON DELETE SET NULL,
    photo_path TEXT NOT NULL,
    angle TEXT DEFAULT 'frontal',
    taken_at TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_evolution_photos_taken ON evolution_photos(taken_at);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    routine_id INTEGER NOT NULL,
    routine_name TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    status TEXT DEFAULT 'pendente',
    workout_id INTEGER REFERENCES workouts(id) ON DELETE SET NULL,
    notified_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_schedules_scheduled ON schedules(scheduled_at);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL UNIQUE,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    user_agent TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ==================== SLEEP MODULE TABLE ====================
CREATE TABLE IF NOT EXISTS sleep_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    sleep_date TEXT NOT NULL UNIQUE,
    bedtime TEXT NOT NULL,
    wake_time TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    quality_rating INTEGER DEFAULT 3 CHECK(quality_rating BETWEEN 1 AND 5),
    planned_bedtime TEXT DEFAULT '23:00',
    planned_wake_time TEXT DEFAULT '06:30',
    compliance_status TEXT DEFAULT 'no_horario',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sleep_logs_date ON sleep_logs(sleep_date);

-- ==================== MODO ROTINAS DIÁRIAS & USER SETTINGS (v1.4.0) ====================
CREATE TABLE IF NOT EXISTS daily_routines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    scheduled_time TEXT DEFAULT '07:00',
    days_of_week TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6',
    status TEXT NOT NULL DEFAULT 'agendada'
        CHECK(status IN ('agendada', 'em_andamento', 'interrompida', 'concluida', 'cancelada')),
    pomodoro_focus_min INTEGER NOT NULL DEFAULT 25,
    pomodoro_short_break_min INTEGER NOT NULL DEFAULT 5,
    pomodoro_long_break_min INTEGER NOT NULL DEFAULT 15,
    pomodoro_cycles INTEGER NOT NULL DEFAULT 4,
    elapsed_seconds INTEGER NOT NULL DEFAULT 0,
    active_date TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_daily_routines_status ON daily_routines(status);

CREATE TABLE IF NOT EXISTS daily_routine_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_id INTEGER NOT NULL REFERENCES daily_routines(id) ON DELETE CASCADE,
    linked_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    estimated_pomodoros INTEGER NOT NULL DEFAULT 1,
    completed_pomodoros INTEGER NOT NULL DEFAULT 0,
    is_done INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_daily_routine_tasks_routine ON daily_routine_tasks(routine_id);

CREATE TABLE IF NOT EXISTS daily_routine_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_id INTEGER NOT NULL REFERENCES daily_routines(id) ON DELETE CASCADE,
    execution_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'em_andamento'
        CHECK(status IN ('agendada', 'em_andamento', 'interrompida', 'concluida', 'cancelada', 'suspensa')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    total_focus_seconds INTEGER NOT NULL DEFAULT 0,
    pomodoros_completed INTEGER NOT NULL DEFAULT 0,
    notified_at TEXT,
    UNIQUE(routine_id, execution_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_routine_logs_date ON daily_routine_logs(execution_date);
CREATE INDEX IF NOT EXISTS idx_daily_routine_logs_routine ON daily_routine_logs(routine_id);

CREATE TABLE IF NOT EXISTS daily_routine_interruptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_id INTEGER NOT NULL REFERENCES daily_routines(id) ON DELETE CASCADE,
    log_id INTEGER REFERENCES daily_routine_logs(id) ON DELETE CASCADE,
    execution_date TEXT NOT NULL,
    interrupted_at TEXT NOT NULL,
    resumed_at TEXT,
    elapsed_seconds_at_pause INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_daily_routine_int_routine ON daily_routine_interruptions(routine_id, execution_date);

CREATE TABLE IF NOT EXISTS daily_routine_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_id INTEGER NOT NULL REFERENCES daily_routines(id) ON DELETE CASCADE,
    log_id INTEGER REFERENCES daily_routine_logs(id) ON DELETE SET NULL,
    execution_date TEXT NOT NULL,
    comment_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_daily_routine_comm_routine ON daily_routine_comments(routine_id, execution_date);

CREATE TABLE IF NOT EXISTS daily_routine_suspensions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_id INTEGER NOT NULL REFERENCES daily_routines(id) ON DELETE CASCADE,
    suspension_type TEXT NOT NULL CHECK(suspension_type IN ('date_range', 'days_of_week')),
    start_date TEXT,
    end_date TEXT,
    days_of_week TEXT,
    note TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_daily_routine_susp_routine ON daily_routine_suspensions(routine_id, is_active);

CREATE TABLE IF NOT EXISTS user_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

RITMO_MUSCLE_GROUPS = [
    'peito', 'costas', 'quadriceps', 'posterior',
    'ombros', 'biceps', 'triceps', 'abdomen', 'panturrilha', 'outro'
]

RITMO_CATALOG = {
    'peito': ['Supino reto com barra', 'Supino inclinado com halteres', 'Crucifixo na máquina', 'Crossover na polia'],
    'costas': ['Puxada frontal na polia', 'Remada curvada com barra', 'Remada baixa no cabo', 'Barra fixa'],
    'quadriceps': ['Agachamento livre', 'Leg press 45°', 'Cadeira extensora', 'Agachamento búlgaro'],
    'posterior': ['Mesa flexora', 'Stiff com halteres', 'Cadeira flexora', 'Elevação pélvica'],
    'ombros': ['Desenvolvimento com halteres', 'Elevação lateral na polia', 'Crucifixo inverso', 'Elevação frontal'],
    'biceps': ['Rosca direta com barra', 'Rosca alternada com halteres', 'Rosca martelo', 'Rosca Scott'],
    'triceps': ['Tríceps na polia corda', 'Tríceps testa com halteres', 'Tríceps francês', 'Mergulho no banco'],
    'abdomen': ['Abdominal supra no solo', 'Prancha isométrica', 'Abdominal infra na barra', 'Abdominal na polia'],
    'panturrilha': ['Elevação de panturrilha em pé', 'Panturrilha no leg press', 'Panturrilha sentado'],
    'outro': ['Bicicleta ergométrica', 'Esteira / Caminhada', 'Alongamento geral']
}

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

        # Idempotent Expand-and-Contract migrations for existing v1.0, v1.1 & v1.2 databases
        # If tasks table exists without 'not_done' in its CHECK constraint, migrate it safely
        tasks_sql_row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone()
        if tasks_sql_row and 'stopped' not in tasks_sql_row[0]:
            conn.execute("PRAGMA foreign_keys = OFF;")
            conn.execute("PRAGMA legacy_alter_table = ON;")
            conn.execute("ALTER TABLE tasks RENAME TO tasks_old;")
            conn.execute("""
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo', 'in_progress', 'done', 'not_done', 'stopped', 'archived')),
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
            """)
            old_cols = [c[1] for c in conn.execute("PRAGMA table_info(tasks_old)").fetchall()]
            new_cols = [c[1] for c in conn.execute("PRAGMA table_info(tasks)").fetchall()]
            common_cols = [c for c in old_cols if c in new_cols]
            cols_csv = ", ".join(common_cols)
            conn.execute(f"INSERT INTO tasks ({cols_csv}) SELECT {cols_csv} FROM tasks_old;")
            conn.execute("DROP TABLE tasks_old;")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_status ON tasks(due_date, status);")
            conn.execute("PRAGMA legacy_alter_table = OFF;")
            conn.execute("PRAGMA foreign_keys = ON;")
        # Auto-heal dangling foreign key references to 'tasks_old' if a previous ALTER TABLE occurred
        old_fk_rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE '%tasks_old%'").fetchall()
        if old_fk_rows:
            conn.execute("PRAGMA foreign_keys = OFF;")
            conn.execute("PRAGMA legacy_alter_table = ON;")
            table_defs = {
                'task_completions': (
                    """CREATE TABLE task_completions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                        completed_at TEXT NOT NULL,
                        pomodoros_completed INTEGER DEFAULT 0
                    );""",
                    ["CREATE INDEX IF NOT EXISTS idx_task_completions_task_id ON task_completions(task_id);",
                     "CREATE INDEX IF NOT EXISTS idx_task_completions_completed_at ON task_completions(completed_at);"]
                ),
                'time_sessions': (
                    """CREATE TABLE time_sessions (
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
                    );""",
                    ["CREATE INDEX IF NOT EXISTS idx_time_sessions_started ON time_sessions(started_at);"]
                ),
                'transactions': (
                    """CREATE TABLE transactions (
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
                    );""",
                    ["CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);",
                     "CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);"]
                ),
                'ideas': (
                    """CREATE TABLE ideas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        content TEXT DEFAULT '',
                        stage TEXT NOT NULL DEFAULT 'raw' CHECK(stage IN ('raw', 'evaluating', 'in_action', 'archived')),
                        status TEXT NOT NULL DEFAULT 'bruta',
                        converted_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                        tags TEXT DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );""",
                    ["CREATE INDEX IF NOT EXISTS idx_ideas_stage ON ideas(stage);"]
                )
            }
            for (t_name,) in old_fk_rows:
                if t_name in table_defs:
                    create_sql, indexes = table_defs[t_name]
                    cols_info = conn.execute(f"PRAGMA table_info({t_name})").fetchall()
                    col_names = [c[1] for c in cols_info]
                    temp_name = f"_tmp_heal_{t_name}"
                    conn.execute(f"ALTER TABLE {t_name} RENAME TO {temp_name};")
                    conn.execute(create_sql)
                    new_cols_info = conn.execute(f"PRAGMA table_info({t_name})").fetchall()
                    new_col_names = [c[1] for c in new_cols_info]
                    common_cols = [c for c in col_names if c in new_col_names]
                    common_csv = ", ".join(common_cols)
                    conn.execute(f"INSERT INTO {t_name} ({common_csv}) SELECT {common_csv} FROM {temp_name};")
                    conn.execute(f"DROP TABLE {temp_name};")
                    for idx_sql in indexes:
                        conn.execute(idx_sql)
            conn.execute("PRAGMA legacy_alter_table = OFF;")
            conn.execute("PRAGMA foreign_keys = ON;")

        _ensure_column(conn, 'workouts', 'status', "TEXT DEFAULT 'concluido'")
        _ensure_column(conn, 'schedules', 'status', "TEXT DEFAULT 'pendente'")
        _ensure_column(conn, 'tasks', 'pomodoro_duration_minutes', 'INTEGER DEFAULT 25')
        _ensure_column(conn, 'sleep_logs', 'planned_bedtime', "TEXT DEFAULT '23:00'")
        _ensure_column(conn, 'sleep_logs', 'planned_wake_time', "TEXT DEFAULT '06:30'")
        _ensure_column(conn, 'sleep_logs', 'compliance_status', "TEXT DEFAULT 'no_horario'")
        # v1.4.1: Rotinas por Horas/Minutos (substitui Pomodoro dentro de Rotinas)
        _ensure_column(conn, 'daily_routine_tasks', 'duration_minutes', 'INTEGER NOT NULL DEFAULT 30')
        _ensure_column(conn, 'daily_routine_tasks', 'elapsed_seconds', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(conn, 'daily_routines', 'total_planned_minutes', 'INTEGER NOT NULL DEFAULT 0')
        conn.execute("""
            UPDATE daily_routines SET total_planned_minutes = (
                SELECT COALESCE(SUM(duration_minutes), 0) FROM daily_routine_tasks t WHERE t.routine_id = daily_routines.id
            ) WHERE total_planned_minutes = 0
        """)

        conn.execute("INSERT OR IGNORE INTO user_settings (key, value) VALUES ('planned_bedtime', '23:00')")
        conn.execute("INSERT OR IGNORE INTO user_settings (key, value) VALUES ('planned_wake_time', '06:30')")
        conn.execute("INSERT OR IGNORE INTO user_settings (key, value) VALUES ('featured_goal_id', '')")

        # Backfill task_history from task_completions if task_history is empty
        th_count = conn.execute("SELECT COUNT(*) FROM task_history").fetchone()[0]
        if th_count == 0:
            tc_rows = conn.execute("SELECT task_id, completed_at, pomodoros_completed FROM task_completions ORDER BY id ASC").fetchall()
            for r in tc_rows:
                note_str = f"{r['pomodoros_completed']} pomodoro(s)" if r['pomodoros_completed'] else ""
                conn.execute(
                    "INSERT INTO task_history (task_id, execution_date, notes) VALUES (?, ?, ?)",
                    (r['task_id'], r['completed_at'], note_str)
                )
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
        _ensure_column(conn, 'transactions', 'source', "TEXT NOT NULL DEFAULT 'manual'")
        _ensure_column(conn, 'transactions', 'external_id', 'TEXT')
        _ensure_column(conn, 'transactions', 'reconciled', 'INTEGER NOT NULL DEFAULT 0')

        _ensure_column(conn, 'ideas', 'status', "TEXT NOT NULL DEFAULT 'bruta'")
        _ensure_column(conn, 'ideas', 'converted_task_id', 'INTEGER REFERENCES tasks(id) ON DELETE SET NULL')
        _ensure_column(conn, 'ideas', 'note_type', "TEXT NOT NULL DEFAULT 'text'")
        _ensure_column(conn, 'notes', 'note_type', "TEXT NOT NULL DEFAULT 'text'")

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

        # Populate standard anatomical exercises catalog if empty
        ex_count = conn.execute("SELECT COUNT(*) FROM exercises").fetchone()[0]
        if ex_count == 0:
            for group, names in RITMO_CATALOG.items():
                for name in names:
                    conn.execute(
                        "INSERT OR IGNORE INTO exercises (name, muscle_group, custom, created_at) VALUES (?, ?, 0, ?)",
                        (name, group, now)
                    )

        conn.commit()
    finally:
        conn.close()

def dict_from_row(row):
    if row is None:
        return None
    return dict(row)
