import os
import io
import csv
import calendar
import sqlite3
import tempfile
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, g, send_from_directory, send_file, Response

try:
    from backend.database import get_db_connection, init_db, dict_from_row
except ImportError:
    from database import get_db_connection, init_db, dict_from_row

APP_VERSION = '1.1.0'

# ------------------- Normalization Helpers (PT/EN Dual Support) -------------------

def normalize_task_status(val: str) -> str:
    if not val:
        return 'todo'
    v = val.strip().lower()
    mapping = {
        'todo': 'todo',
        'pendente': 'todo',
        'a_fazer': 'todo',
        'in_progress': 'in_progress',
        'em_progresso': 'in_progress',
        'em_execucao': 'in_progress',
        'done': 'done',
        'concluida': 'done',
        'concluído': 'done',
        'concluido': 'done',
        'archived': 'archived',
        'arquivada': 'archived',
        'arquivado': 'archived',
    }
    return mapping.get(v, 'todo')

def normalize_task_priority(val: str) -> str:
    if not val:
        return 'medium'
    v = val.strip().lower()
    mapping = {
        'low': 'low',
        'baixa': 'low',
        'medium': 'medium',
        'media': 'medium',
        'média': 'medium',
        'high': 'high',
        'alta': 'high',
        'urgent': 'urgent',
        'urgente': 'urgent',
    }
    return mapping.get(v, 'medium')

def normalize_recurrence(val: str) -> str:
    if not val:
        return 'nenhuma'
    v = val.strip().lower()
    mapping = {
        'none': 'nenhuma',
        'nenhuma': 'nenhuma',
        'daily': 'diaria',
        'diaria': 'diaria',
        'diária': 'diaria',
        'weekly': 'semanal',
        'semanal': 'semanal',
        'monthly': 'mensal',
        'mensal': 'mensal',
        'yearly': 'anual',
        'anual': 'anual',
    }
    return mapping.get(v, 'nenhuma')

def normalize_txn_type(val: str) -> str:
    if not val:
        return 'expense'
    v = val.strip().lower()
    if v in ('income', 'receita', 'deposito', 'depósito', 'entrada'):
        return 'income'
    return 'expense'

def normalize_idea_stage_and_status(stage_val: str = None, status_val: str = None):
    raw_in = (status_val or stage_val or 'raw').strip().lower()
    if raw_in in ('convertida', 'converted'):
        return 'in_action', 'convertida'
    if raw_in in ('evaluating', 'em_analise', 'em_análise'):
        return 'evaluating', 'em_analise'
    if raw_in in ('in_action', 'em_execucao', 'em_execução'):
        return 'in_action', 'em_analise'
    if raw_in in ('archived', 'arquivada', 'arquivado'):
        return 'archived', 'arquivada'
    return 'raw', 'bruta'

def compute_next_due_date(current_due_str: str, recurrence: str) -> str:
    try:
        if current_due_str:
            base = date.fromisoformat(current_due_str[:10])
        else:
            base = date.today()
    except ValueError:
        base = date.today()

    rec = normalize_recurrence(recurrence)
    if rec == 'diaria':
        return (base + timedelta(days=1)).isoformat()
    elif rec == 'semanal':
        return (base + timedelta(days=7)).isoformat()
    elif rec == 'mensal':
        year = base.year + (base.month // 12)
        month = (base.month % 12) + 1
        max_day = calendar.monthrange(year, month)[1]
        return date(year, month, min(base.day, max_day)).isoformat()
    elif rec == 'anual':
        year = base.year + 1
        max_day = calendar.monthrange(year, base.month)[1]
        return date(year, base.month, min(base.day, max_day)).isoformat()
    return base.isoformat()

def resolve_category_id(conn: sqlite3.Connection, category_name: str, category_id=None):
    if category_id is not None:
        return int(category_id)
    if not category_name:
        category_name = 'Geral'
    row = conn.execute("SELECT id FROM categories WHERE name = ?", (category_name,)).fetchone()
    if row:
        return row['id']
    cur = conn.execute(
        "INSERT INTO categories (name, created_at) VALUES (?, ?)",
        (category_name, datetime.now().isoformat())
    )
    return cur.lastrowid

def ensure_recurring_transactions_for_month(conn: sqlite3.Connection, target_month: str):
    """
    Idempotently materializes recurring monthly/yearly transactions for target_month (YYYY-MM)
    so the user never has to re-enter fixed expenses or recurring deposits manually.
    """
    if not target_month or len(target_month) != 7 or '-' not in target_month:
        return
    try:
        t_year, t_month = map(int, target_month.split('-'))
    except ValueError:
        return

    # Find root recurring templates created in earlier months
    roots = conn.execute("""
        SELECT * FROM transactions
        WHERE is_recurring = 1
          AND (parent_recurring_id IS NULL OR parent_recurring_id = 0)
          AND substr(date, 1, 7) < ?
    """, (target_month,)).fetchall()

    if not roots:
        return

    now = datetime.now().isoformat()
    inserted = False
    for root in roots:
        rec = normalize_recurrence(root['recurrence'] or 'mensal')
        if rec == 'nenhuma':
            rec = 'mensal'

        orig_date_str = root['date'] or ''
        try:
            orig_day = int(orig_date_str.split('-')[2][:2])
            orig_month = int(orig_date_str.split('-')[1])
        except (IndexError, ValueError):
            orig_day = 1
            orig_month = t_month

        if rec == 'anual' and orig_month != t_month:
            continue

        # Check if already materialized for this target_month
        existing = conn.execute("""
            SELECT id FROM transactions
            WHERE parent_recurring_id = ? AND date LIKE ?
        """, (root['id'], f"{target_month}%")).fetchone()
        if existing:
            continue

        max_day = calendar.monthrange(t_year, t_month)[1]
        day = min(max(1, orig_day), max_day)
        new_date = f"{target_month}-{day:02d}"

        conn.execute("""
            INSERT INTO transactions (
                description, amount_cents, amount, type, category, category_id, task_id,
                account, date, transaction_date, is_settled, is_recurring, recurrence,
                parent_recurring_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """, (
            root['description'],
            root['amount_cents'],
            root['amount'] or round(root['amount_cents'] / 100.0, 2),
            root['type'],
            root['category'],
            root['category_id'],
            root['task_id'],
            root['account'],
            new_date,
            new_date,
            root['is_settled'],
            rec,
            root['id'],
            now
        ))
        inserted = True

    if inserted:
        conn.commit()


def create_app(test_config=None):
    app = Flask(__name__)

    db_path = os.environ.get('NEXUS_DB', os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'nexus.db')))
    if test_config and 'DATABASE' in test_config:
        db_path = test_config['DATABASE']

    app.config['DATABASE'] = db_path

    # Initialize DB schema & migrations
    init_db(db_path)

    def get_db():
        if 'db' not in g:
            g.db = get_db_connection(app.config['DATABASE'])
        return g.db

    @app.teardown_appcontext
    def close_db(exception):
        db = g.pop('db', None)
        if db is not None:
            db.close()

    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,PATCH,DELETE,OPTIONS'
        return response

    # ------------------- Health, Cockpit ("Meu Dia") & Overview -------------------
    @app.route('/api/health', methods=['GET'])
    def health():
        return jsonify({'status': 'ok', 'app': 'Dream Hub', 'version': APP_VERSION})

    def _build_cockpit_data(conn: sqlite3.Connection):
        today = date.today().isoformat()
        current_month = datetime.now().strftime('%Y-%m')

        # Materialize recurring transactions for current month if needed
        ensure_recurring_transactions_for_month(conn, current_month)

        pending_tasks = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status != 'done' AND status != 'archived'"
        ).fetchone()[0]
        urgent_tasks = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE priority = 'urgent' AND status != 'done' AND status != 'archived'"
        ).fetchone()[0]

        # Tasks due today or overdue or urgent
        due_today_rows = conn.execute("""
            SELECT * FROM tasks
            WHERE status != 'done' AND status != 'archived'
              AND (due_date <= ? OR priority IN ('urgent', 'high'))
            ORDER BY CASE WHEN due_date = ? THEN 0 WHEN due_date < ? THEN 1 ELSE 2 END,
                     CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
                     id DESC
            LIMIT 8
        """, (today, today, today)).fetchall()
        tasks_due_today = [dict_from_row(r) for r in due_today_rows]

        exact_due_today_count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status != 'done' AND status != 'archived' AND due_date = ?",
            (today,)
        ).fetchone()[0]

        # Focus minutes today
        focus_row = conn.execute("""
            SELECT COALESCE(SUM(duration_minutes), 0), COUNT(*)
            FROM time_sessions
            WHERE session_type = 'focus' AND completed = 1 AND started_at LIKE ?
        """, (f"{today}%",)).fetchone()
        today_focus_min = focus_row[0]
        today_sessions = focus_row[1]

        # Financial balance this month
        fin_rows = conn.execute("""
            SELECT type, is_recurring, COALESCE(SUM(amount_cents), 0) as total
            FROM transactions
            WHERE date LIKE ?
            GROUP BY type, is_recurring
        """, (f"{current_month}%",)).fetchall()

        income_cents = 0
        expense_cents = 0
        recurring_income_cents = 0
        recurring_expense_cents = 0
        for r in fin_rows:
            tot = r['total']
            is_rec = int(r['is_recurring'] or 0) == 1
            if r['type'] == 'income':
                income_cents += tot
                if is_rec:
                    recurring_income_cents += tot
            elif r['type'] == 'expense':
                expense_cents += tot
                if is_rec:
                    recurring_expense_cents += tot

        active_ideas = conn.execute(
            "SELECT COUNT(*) FROM ideas WHERE stage != 'archived' AND status != 'arquivada'"
        ).fetchone()[0]

        recent_ideas_rows = conn.execute("""
            SELECT * FROM ideas
            WHERE stage != 'archived' AND status != 'convertida'
            ORDER BY updated_at DESC, id DESC LIMIT 4
        """).fetchall()

        return {
            'today': today,
            'current_month': current_month,
            'pending_tasks': pending_tasks,
            'urgent_tasks': urgent_tasks,
            'tasks_due_today_count': exact_due_today_count or len(tasks_due_today),
            'tasks_due_today': tasks_due_today,
            'today_focus_minutes': today_focus_min,
            'today_pomodoro_sessions': today_sessions,
            'month_income_cents': income_cents,
            'month_expense_cents': expense_cents,
            'month_balance_cents': income_cents - expense_cents,
            'recurring_income_cents': recurring_income_cents,
            'recurring_expense_cents': recurring_expense_cents,
            'active_ideas': active_ideas,
            'recent_ideas': [dict_from_row(r) for r in recent_ideas_rows]
        }

    @app.route('/api/cockpit/today', methods=['GET'])
    def cockpit_today():
        conn = get_db()
        data = _build_cockpit_data(conn)
        return jsonify({
            'status': 'success',
            'data': data,
            **data
        })

    @app.route('/api/overview', methods=['GET'])
    def overview():
        conn = get_db()
        data = _build_cockpit_data(conn)
        return jsonify(data)

    # ------------------- Categories Module -------------------
    @app.route('/api/categories', methods=['GET', 'POST'])
    def handle_categories():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            name = (data.get('name') or '').strip()
            if not name:
                return jsonify({'status': 'error', 'error': 'Nome da categoria é obrigatório'}), 400
            color = data.get('color', '#2563EB')
            icon = data.get('icon', 'folder')
            now = datetime.now().isoformat()
            conn.execute(
                "INSERT OR IGNORE INTO categories (name, color, icon, created_at) VALUES (?, ?, ?, ?)",
                (name, color, icon, now)
            )
            conn.commit()
            cat = conn.execute("SELECT * FROM categories WHERE name = ?", (name,)).fetchone()
            return jsonify(dict_from_row(cat)), 201

        rows = conn.execute("SELECT * FROM categories ORDER BY name ASC").fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    # ------------------- Tasks Module -------------------
    def _create_recurring_clone_if_needed(conn: sqlite3.Connection, task_dict: dict, prev_status: str, new_status: str):
        rec = normalize_recurrence(task_dict.get('recurrence', 'nenhuma'))
        if prev_status != 'done' and new_status == 'done' and rec != 'nenhuma':
            next_due = compute_next_due_date(task_dict.get('due_date'), rec)
            now = datetime.now().isoformat()
            cur = conn.execute("""
                INSERT INTO tasks (
                    title, description, status, priority, due_date, category, category_id,
                    recurrence, estimated_pomodoros, completed_pomodoros,
                    pomodoro_duration_minutes, created_at, updated_at
                )
                VALUES (?, ?, 'todo', ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """, (
                task_dict['title'],
                task_dict.get('description', ''),
                task_dict['priority'],
                next_due,
                task_dict.get('category', 'Geral'),
                task_dict.get('category_id'),
                rec,
                task_dict.get('estimated_pomodoros', 1),
                task_dict.get('pomodoro_duration_minutes', 25),
                now,
                now
            ))
            new_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
            return dict_from_row(new_row)
        return None

    @app.route('/api/tasks', methods=['GET', 'POST'])
    def handle_tasks():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            title = (data.get('title') or '').strip()
            if not title:
                return jsonify({'status': 'error', 'error': 'Título é obrigatório'}), 400

            description = (data.get('description') or '').strip()
            status = normalize_task_status(data.get('status', 'todo'))
            priority = normalize_task_priority(data.get('priority', 'medium'))
            due_date = data.get('due_date') or None
            category = (data.get('category') or 'Geral').strip()
            category_id = resolve_category_id(conn, category, data.get('category_id'))
            recurrence = normalize_recurrence(data.get('recurrence', 'nenhuma'))
            estimated = int(data.get('estimated_pomodoros') or 1)
            pomodoro_duration = int(data.get('pomodoro_duration_minutes') or 25)
            now = datetime.now().isoformat()
            completed_at = now if status == 'done' else None

            cur = conn.execute("""
                INSERT INTO tasks (
                    title, description, status, priority, due_date, category, category_id,
                    recurrence, estimated_pomodoros, completed_pomodoros,
                    pomodoro_duration_minutes, created_at, updated_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """, (
                title, description, status, priority, due_date, category, category_id,
                recurrence, estimated, pomodoro_duration, now, now, completed_at
            ))
            conn.commit()
            new_id = cur.lastrowid
            task = conn.execute("SELECT * FROM tasks WHERE id = ?", (new_id,)).fetchone()
            return jsonify(dict_from_row(task)), 201

        # GET
        status = request.args.get('status')
        priority = request.args.get('priority')
        category = request.args.get('category')
        due_date = request.args.get('due_date')

        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(normalize_task_status(status))
        if priority:
            query += " AND priority = ?"
            params.append(normalize_task_priority(priority))
        if category:
            query += " AND category = ?"
            params.append(category)
        if due_date:
            query += " AND due_date = ?"
            params.append(due_date)

        query += " ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, CASE WHEN due_date IS NULL THEN 1 ELSE 0 END, due_date ASC, id DESC"
        rows = conn.execute(query, params).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/tasks/<int:task_id>', methods=['GET', 'PUT', 'DELETE'])
    def task_detail(task_id):
        conn = get_db()
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            return jsonify({'status': 'error', 'error': 'Tarefa não encontrada'}), 404

        if request.method == 'GET':
            return jsonify(dict_from_row(task))

        if request.method == 'DELETE':
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            return jsonify({'status': 'success', 'success': True, 'deleted_id': task_id})

        # PUT
        data = request.get_json() or {}
        now = datetime.now().isoformat()
        current = dict_from_row(task)
        prev_status = current['status']

        title = data.get('title', current['title'])
        description = data.get('description', current['description'])
        status = normalize_task_status(data['status']) if 'status' in data else current['status']
        priority = normalize_task_priority(data['priority']) if 'priority' in data else current['priority']
        due_date = data.get('due_date', current['due_date'])
        category = data.get('category', current['category'])
        category_id = resolve_category_id(conn, category, data.get('category_id', current.get('category_id')))
        recurrence = normalize_recurrence(data['recurrence']) if 'recurrence' in data else normalize_recurrence(current.get('recurrence', 'nenhuma'))
        estimated = data.get('estimated_pomodoros', current['estimated_pomodoros'])
        completed = data.get('completed_pomodoros', current['completed_pomodoros'])
        pomodoro_duration = data.get('pomodoro_duration_minutes', current.get('pomodoro_duration_minutes', 25))
        completed_at = now if (status == 'done' and prev_status != 'done') else (None if status != 'done' else current.get('completed_at'))

        conn.execute("""
            UPDATE tasks
            SET title = ?, description = ?, status = ?, priority = ?, due_date = ?, category = ?,
                category_id = ?, recurrence = ?, estimated_pomodoros = ?, completed_pomodoros = ?,
                pomodoro_duration_minutes = ?, updated_at = ?, completed_at = ?
            WHERE id = ?
        """, (
            title, description, status, priority, due_date, category,
            category_id, recurrence, estimated, completed,
            pomodoro_duration, now, completed_at, task_id
        ))

        updated_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        updated_dict = dict_from_row(updated_row)

        next_task = _create_recurring_clone_if_needed(conn, updated_dict, prev_status, status)
        conn.commit()

        if next_task:
            updated_dict['next_recurring_task'] = next_task
        return jsonify(updated_dict)

    @app.route('/api/tasks/<int:task_id>/status', methods=['PATCH', 'POST'])
    def patch_task_status(task_id):
        conn = get_db()
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            return jsonify({'status': 'error', 'error': 'Tarefa não encontrada'}), 404

        current = dict_from_row(task)
        prev_status = current['status']
        data = request.get_json(silent=True) or {}

        if 'status' in data:
            new_status = normalize_task_status(data['status'])
        else:
            new_status = 'done' if prev_status != 'done' else 'todo'

        now = datetime.now().isoformat()
        completed_at = now if new_status == 'done' else None

        conn.execute("""
            UPDATE tasks
            SET status = ?, updated_at = ?, completed_at = ?
            WHERE id = ?
        """, (new_status, now, completed_at, task_id))

        updated_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        updated_dict = dict_from_row(updated_row)

        next_task = _create_recurring_clone_if_needed(conn, updated_dict, prev_status, new_status)
        conn.commit()

        if next_task:
            updated_dict['next_recurring_task'] = next_task
        return jsonify(updated_dict)

    # ------------------- Time / Pomodoro Module -------------------
    @app.route('/api/time/sessions', methods=['GET', 'POST'])
    def time_sessions():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            task_id = data.get('task_id')
            raw_type = data.get('session_type') or data.get('type') or 'focus'
            session_type = 'focus' if raw_type in ('focus', 'pomodoro') else raw_type
            spec_type = 'pomodoro' if session_type == 'focus' else session_type
            duration_minutes = int(data.get('duration_minutes', 25))
            now_iso = datetime.now().isoformat()
            started_at = data.get('started_at', now_iso)
            ended_at = data.get('ended_at', now_iso)
            completed = int(data.get('completed', 1))
            notes = data.get('notes', '')

            cur = conn.execute("""
                INSERT INTO time_sessions (task_id, session_type, type, duration_minutes, started_at, ended_at, completed, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (task_id, session_type, spec_type, duration_minutes, started_at, ended_at, completed, notes, now_iso))

            # RN03: Increment task's pomodoro count only if focus session completed
            if task_id and completed == 1 and session_type == 'focus':
                conn.execute("""
                    UPDATE tasks
                    SET completed_pomodoros = completed_pomodoros + 1, updated_at = ?
                    WHERE id = ?
                """, (now_iso, task_id))

            conn.commit()
            new_id = cur.lastrowid
            session = conn.execute("SELECT * FROM time_sessions WHERE id = ?", (new_id,)).fetchone()
            return jsonify(dict_from_row(session)), 201

        # GET
        limit = int(request.args.get('limit', 50))
        rows = conn.execute("""
            SELECT s.*, t.title as task_title
            FROM time_sessions s
            LEFT JOIN tasks t ON s.task_id = t.id
            ORDER BY s.id DESC LIMIT ?
        """, (limit,)).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/time/stats', methods=['GET'])
    def time_stats():
        conn = get_db()
        today = date.today().isoformat()

        row_today = conn.execute("""
            SELECT COALESCE(SUM(duration_minutes), 0), COUNT(*)
            FROM time_sessions
            WHERE session_type = 'focus' AND completed = 1 AND started_at LIKE ?
        """, (f"{today}%",)).fetchone()

        row_total = conn.execute("""
            SELECT COALESCE(SUM(duration_minutes), 0), COUNT(*)
            FROM time_sessions
            WHERE session_type = 'focus' AND completed = 1
        """).fetchone()

        return jsonify({
            'today_focus_minutes': row_today[0],
            'today_completed_sessions': row_today[1],
            'total_focus_minutes': row_total[0],
            'completed_sessions': row_total[1]
        })

    # ------------------- Finance Module & Recurring Transactions -------------------
    @app.route('/api/finance/transactions', methods=['GET', 'POST'])
    def transactions():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            description = (data.get('description') or '').strip()
            if not description:
                return jsonify({'status': 'error', 'error': 'Descrição é obrigatória'}), 400

            if 'amount_cents' in data and data['amount_cents'] is not None:
                amount_cents = int(data['amount_cents'])
            else:
                amount_val = float(data.get('amount', 0))
                amount_cents = int(round(amount_val * 100))

            if amount_cents <= 0:
                return jsonify({'status': 'error', 'error': 'Valor deve ser positivo'}), 400

            amount_decimal = round(amount_cents / 100.0, 2)
            txn_type = normalize_txn_type(data.get('type', 'expense'))
            category = (data.get('category') or 'Outros').strip()
            category_id = resolve_category_id(conn, category, data.get('category_id'))
            task_id = int(data['task_id']) if data.get('task_id') else None
            account = (data.get('account') or 'Carteira').strip()
            txn_date = data.get('date') or data.get('transaction_date') or date.today().isoformat()
            is_settled = int(data.get('is_settled', 1))

            is_recurring_flag = 1 if data.get('is_recurring') in (True, 1, '1', 'true') else 0
            recurrence = normalize_recurrence(data.get('recurrence', 'mensal' if is_recurring_flag else 'nenhuma'))
            if recurrence != 'nenhuma':
                is_recurring_flag = 1

            now = datetime.now().isoformat()

            cur = conn.execute("""
                INSERT INTO transactions (
                    description, amount_cents, amount, type, category, category_id, task_id,
                    account, date, transaction_date, is_settled, is_recurring, recurrence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                description, amount_cents, amount_decimal, txn_type, category, category_id, task_id,
                account, txn_date, txn_date, is_settled, is_recurring_flag, recurrence, now
            ))
            conn.commit()

            new_id = cur.lastrowid
            txn = conn.execute("SELECT * FROM transactions WHERE id = ?", (new_id,)).fetchone()
            return jsonify(dict_from_row(txn)), 201

        # GET
        month = request.args.get('month') # YYYY-MM
        if month:
            ensure_recurring_transactions_for_month(conn, month)

        txn_type = request.args.get('type')
        category = request.args.get('category')
        recurring_only = request.args.get('is_recurring')

        query = """
            SELECT tr.*, t.title as task_title
            FROM transactions tr
            LEFT JOIN tasks t ON tr.task_id = t.id
            WHERE 1=1
        """
        params = []
        if month:
            query += " AND tr.date LIKE ?"
            params.append(f"{month}%")
        if txn_type:
            query += " AND tr.type = ?"
            params.append(normalize_txn_type(txn_type))
        if category:
            query += " AND tr.category = ?"
            params.append(category)
        if recurring_only in ('1', 'true'):
            query += " AND tr.is_recurring = 1"

        query += " ORDER BY tr.date DESC, tr.id DESC"
        rows = conn.execute(query, params).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/finance/transactions/<int:txn_id>', methods=['DELETE', 'PATCH'])
    def modify_transaction(txn_id):
        conn = get_db()
        txn = conn.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,)).fetchone()
        if not txn:
            return jsonify({'status': 'error', 'error': 'Transação não encontrada'}), 404

        if request.method == 'PATCH':
            data = request.get_json(silent=True) or {}
            is_rec = 1 if data.get('is_recurring') in (True, 1, '1', 'true') else 0
            rec = normalize_recurrence(data.get('recurrence', 'mensal' if is_rec else 'nenhuma'))
            conn.execute(
                "UPDATE transactions SET is_recurring = ?, recurrence = ? WHERE id = ?",
                (is_rec, rec, txn_id)
            )
            # If turning off recurrence on a child, also turn off on the parent template
            if is_rec == 0 and txn['parent_recurring_id']:
                conn.execute(
                    "UPDATE transactions SET is_recurring = 0, recurrence = 'nenhuma' WHERE id = ?",
                    (txn['parent_recurring_id'],)
                )
            conn.commit()
            updated = conn.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,)).fetchone()
            return jsonify(dict_from_row(updated))

        # DELETE
        # If deleting a recurring child or template, also stop future auto-generation if requested
        if txn['is_recurring'] == 1 and txn['parent_recurring_id']:
            conn.execute(
                "UPDATE transactions SET is_recurring = 0, recurrence = 'nenhuma' WHERE id = ?",
                (txn['parent_recurring_id'],)
            )
        conn.execute("DELETE FROM transactions WHERE id = ?", (txn_id,))
        conn.commit()
        return jsonify({'status': 'success', 'success': True, 'deleted_id': txn_id})

    @app.route('/api/finance/summary', methods=['GET'])
    def finance_summary():
        conn = get_db()
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        ensure_recurring_transactions_for_month(conn, month)

        rows = conn.execute("""
            SELECT type, category, is_recurring, COALESCE(SUM(amount_cents), 0) as total
            FROM transactions
            WHERE date LIKE ?
            GROUP BY type, category, is_recurring
        """, (f"{month}%",)).fetchall()

        total_income = 0
        total_expense = 0
        recurring_income = 0
        recurring_expense = 0
        categories_breakdown = {}

        for r in rows:
            t = r['type']
            cat = r['category']
            tot = r['total']
            is_rec = int(r['is_recurring'] or 0) == 1
            if t == 'income':
                total_income += tot
                if is_rec:
                    recurring_income += tot
            else:
                total_expense += tot
                if is_rec:
                    recurring_expense += tot
                categories_breakdown[cat] = categories_breakdown.get(cat, 0) + tot

        recurring_rows = conn.execute("""
            SELECT * FROM transactions
            WHERE date LIKE ? AND is_recurring = 1
            ORDER BY type ASC, amount_cents DESC
        """, (f"{month}%",)).fetchall()

        return jsonify({
            'month': month,
            'total_income_cents': total_income,
            'total_expense_cents': total_expense,
            'net_balance_cents': total_income - total_expense,
            'recurring_income_cents': recurring_income,
            'recurring_expense_cents': recurring_expense,
            'recurring_transactions': [dict_from_row(r) for r in recurring_rows],
            'categories_breakdown': categories_breakdown
        })

    # ------------------- Ideas Module & Atomic Conversion -------------------
    @app.route('/api/ideas', methods=['GET', 'POST'])
    def handle_ideas():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            title = (data.get('title') or '').strip()
            if not title:
                return jsonify({'status': 'error', 'error': 'Título da ideia é obrigatório'}), 400

            content = (data.get('content') or '').strip()
            stage, status = normalize_idea_stage_and_status(data.get('stage'), data.get('status'))
            tags = (data.get('tags') or '').strip()
            now = datetime.now().isoformat()

            cur = conn.execute("""
                INSERT INTO ideas (title, content, stage, status, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (title, content, stage, status, tags, now, now))
            conn.commit()
            new_id = cur.lastrowid
            idea = conn.execute("SELECT * FROM ideas WHERE id = ?", (new_id,)).fetchone()
            return jsonify(dict_from_row(idea)), 201

        # GET
        stage = request.args.get('stage')
        tag = request.args.get('tag')
        q = request.args.get('q')

        query = "SELECT * FROM ideas WHERE 1=1"
        params = []
        if stage:
            if stage in ('convertida', 'converted'):
                query += " AND status = 'convertida'"
            else:
                norm_stage, _ = normalize_idea_stage_and_status(stage, None)
                query += " AND stage = ?"
                params.append(norm_stage)
        if tag:
            query += " AND tags LIKE ?"
            params.append(f"%{tag}%")
        if q:
            query += " AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)"
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

        query += " ORDER BY updated_at DESC, id DESC"
        rows = conn.execute(query, params).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/ideas/<int:idea_id>', methods=['GET', 'PUT', 'DELETE'])
    def idea_detail(idea_id):
        conn = get_db()
        idea = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        if not idea:
            return jsonify({'status': 'error', 'error': 'Ideia não encontrada'}), 404

        if request.method == 'GET':
            return jsonify(dict_from_row(idea))

        if request.method == 'DELETE':
            conn.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
            conn.commit()
            return jsonify({'status': 'success', 'success': True, 'deleted_id': idea_id})

        # PUT
        data = request.get_json() or {}
        now = datetime.now().isoformat()
        current = dict_from_row(idea)

        title = data.get('title', current['title'])
        content = data.get('content', current['content'])
        if 'stage' in data or 'status' in data:
            stage, status = normalize_idea_stage_and_status(data.get('stage'), data.get('status'))
        else:
            stage, status = current['stage'], current.get('status', 'bruta')
        tags = data.get('tags', current['tags'])

        conn.execute("""
            UPDATE ideas
            SET title = ?, content = ?, stage = ?, status = ?, tags = ?, updated_at = ?
            WHERE id = ?
        """, (title, content, stage, status, tags, now, idea_id))
        conn.commit()
        updated = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        return jsonify(dict_from_row(updated))

    @app.route('/api/ideas/<int:idea_id>/convert', methods=['POST'])
    def convert_idea_to_task(idea_id):
        """
        RN02 & [RF12]: Atomic conversion of an Idea into a Task using BEGIN IMMEDIATE.
        """
        conn = get_db()
        idea = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        if not idea:
            return jsonify({'status': 'error', 'error': 'Ideia não encontrada'}), 404

        data = request.get_json(silent=True) or {}
        priority = normalize_task_priority(data.get('priority', 'medium'))
        category = (data.get('category') or 'Geral').strip()
        due_date = data.get('due_date') or date.today().isoformat()
        estimated = int(data.get('estimated_pomodoros') or 1)
        pomodoro_duration = int(data.get('pomodoro_duration_minutes') or 25)
        now = datetime.now().isoformat()

        try:
            conn.execute("BEGIN IMMEDIATE")
            category_id = resolve_category_id(conn, category)
            cur = conn.execute("""
                INSERT INTO tasks (
                    title, description, status, priority, due_date, category, category_id,
                    recurrence, estimated_pomodoros, completed_pomodoros,
                    pomodoro_duration_minutes, created_at, updated_at
                )
                VALUES (?, ?, 'todo', ?, ?, ?, ?, 'nenhuma', ?, 0, ?, ?, ?)
            """, (
                idea['title'],
                idea['content'] or '',
                priority,
                due_date,
                category,
                category_id,
                estimated,
                pomodoro_duration,
                now,
                now
            ))
            new_task_id = cur.lastrowid

            conn.execute("""
                UPDATE ideas
                SET stage = 'in_action', status = 'convertida', converted_task_id = ?, updated_at = ?
                WHERE id = ?
            """, (new_task_id, now, idea_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            return jsonify({'status': 'error', 'error': f'Falha na conversão atômica: {str(e)}'}), 500

        created_task = dict_from_row(conn.execute("SELECT * FROM tasks WHERE id = ?", (new_task_id,)).fetchone())
        updated_idea = dict_from_row(conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone())

        return jsonify({
            'status': 'success',
            'task': created_task,
            'idea': updated_idea
        }), 201

    # ------------------- System Backup ([RF14]) & Export ([RF15]) -------------------
    @app.route('/api/system/backup', methods=['GET'])
    def system_backup():
        conn = get_db()
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.db')
        os.close(tmp_fd)
        try:
            dst_conn = sqlite3.connect(tmp_path)
            with dst_conn:
                conn.backup(dst_conn)
            dst_conn.close()

            with open(tmp_path, 'rb') as f:
                buf = io.BytesIO(f.read())
            buf.seek(0)
            stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            return send_file(
                buf,
                mimetype='application/x-sqlite3',
                as_attachment=True,
                download_name=f'dreamhub_backup_{stamp}.db'
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @app.route('/api/system/export', methods=['GET'])
    def system_export():
        conn = get_db()
        module = (request.args.get('module') or 'all').lower()
        fmt = (request.args.get('format') or 'json').lower()
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        tasks_list = [dict_from_row(r) for r in conn.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()]
        txns_list = [dict_from_row(r) for r in conn.execute("SELECT * FROM transactions ORDER BY date DESC, id DESC").fetchall()]
        ideas_list = [dict_from_row(r) for r in conn.execute("SELECT * FROM ideas ORDER BY id DESC").fetchall()]

        if fmt == 'csv':
            output = io.StringIO()
            output.write('\ufeff')  # UTF-8 BOM for Excel/Sheets compatibility
            writer = csv.writer(output)

            if module == 'tasks':
                writer.writerow(['ID', 'Título', 'Status', 'Prioridade', 'Prazo', 'Categoria', 'Recorrência', 'Pomodoros Concluídos', 'Pomodoros Estimados', 'Criado Em'])
                for t in tasks_list:
                    writer.writerow([t['id'], t['title'], t['status'], t['priority'], t['due_date'] or '', t['category'], t.get('recurrence', 'nenhuma'), t['completed_pomodoros'], t['estimated_pomodoros'], t['created_at']])
                filename = f'dreamhub_tarefas_{stamp}.csv'
            elif module == 'ideas':
                writer.writerow(['ID', 'Título', 'Estágio', 'Status', 'Tags', 'Tarefa Vinculada', 'Conteúdo', 'Criado Em'])
                for i in ideas_list:
                    writer.writerow([i['id'], i['title'], i['stage'], i.get('status', ''), i['tags'], i.get('converted_task_id') or '', i['content'], i['created_at']])
                filename = f'dreamhub_ideias_{stamp}.csv'
            else:
                writer.writerow(['ID', 'Data', 'Tipo', 'Descrição', 'Valor (R$)', 'Categoria', 'Conta', 'Recorrente', 'Frequência', 'Tarefa ID'])
                for tr in txns_list:
                    val_brl = f"{(tr['amount_cents'] or 0) / 100.0:.2f}"
                    writer.writerow([tr['id'], tr['date'], tr['type'], tr['description'], val_brl, tr['category'], tr['account'], 'Sim' if tr.get('is_recurring') else 'Não', tr.get('recurrence', 'nenhuma'), tr.get('task_id') or ''])
                filename = f'dreamhub_financas_{stamp}.csv'

            return Response(
                output.getvalue(),
                mimetype='text/csv; charset=utf-8',
                headers={'Content-Disposition': f'attachment; filename="{filename}"'}
            )

        # Default JSON export
        result = {'exported_at': datetime.now().isoformat(), 'version': APP_VERSION}
        if module in ('tasks', 'all'):
            result['tasks'] = tasks_list
        if module in ('finance', 'transactions', 'all'):
            result['transactions'] = txns_list
        if module in ('ideas', 'all'):
            result['ideas'] = ideas_list

        return jsonify(result)

    # ------------------- Frontend Static Fallback -------------------
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_frontend(path):
        if path.startswith('api/'):
            return jsonify({'status': 'error', 'error': 'Not found'}), 404
        frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
        target = os.path.join(frontend_dir, path)
        if path and os.path.exists(target) and not os.path.isdir(target):
            return send_from_directory(frontend_dir, path)
        return send_from_directory(frontend_dir, 'index.html')

    return app

# WSGI application entrypoint for Gunicorn
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8001))
    app.run(host='127.0.0.1', port=port, debug=False)
