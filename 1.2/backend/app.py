import os
import io
import csv
import uuid
import calendar
import sqlite3
import tempfile
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, g, send_from_directory, send_file, Response

try:
    from backend.database import get_db_connection, init_db, dict_from_row
except ImportError:
    from database import get_db_connection, init_db, dict_from_row

APP_VERSION = '1.2.0'
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB strict limit ([RNF01])

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

def normalize_rule_type(val: str) -> str:
    if not val:
        return 'despesa'
    v = val.strip().lower()
    if v in ('income', 'receita', 'deposito', 'depósito', 'entrada'):
        return 'receita'
    return 'despesa'

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

def enrich_goal(row) -> dict:
    if row is None:
        return None
    d = dict(row)
    g_type = d.get('goal_type', 'quantitativa')
    target = float(d['target_value']) if d.get('target_value') is not None else None
    current = float(d.get('current_value') or 0.0)
    if d.get('status') == 'alcancada':
        pct = 100.0
    elif g_type in ('monetaria', 'quantitativa') and target and target > 0:
        pct = round(min(100.0, max(0.0, (current / target) * 100.0)), 1)
    else:
        pct = round(min(95.0, current * 10.0), 1) if current > 0 else 0.0
    d['progress_percent'] = pct
    return d

def increment_goal_progress(conn: sqlite3.Connection, goal_id: int, delta: float):
    if not goal_id or delta == 0:
        return
    goal = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    if not goal:
        return
    current = float(goal['current_value'] or 0.0) + float(delta)
    target = float(goal['target_value']) if goal['target_value'] is not None else None
    status = goal['status']
    completed_at = goal['completed_at']
    if target is not None and target > 0 and current >= target:
        status = 'alcancada'
        completed_at = completed_at or datetime.now().isoformat()
    conn.execute("""
        UPDATE goals
        SET current_value = ?, status = ?, completed_at = ?
        WHERE id = ?
    """, (round(current, 2), status, completed_at, goal_id))

def delete_entity_attachments(conn: sqlite3.Connection, upload_dir: str, entity_type: str, entity_id: int):
    rows = conn.execute(
        "SELECT id, storage_path FROM attachments WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id)
    ).fetchall()
    for r in rows:
        fname = os.path.basename(r['storage_path'])
        p = os.path.join(upload_dir, fname)
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
    conn.execute(
        "DELETE FROM attachments WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id)
    )

def ensure_recurring_transactions_for_month(conn: sqlite3.Connection, target_month: str):
    """
    Materializes active recurring_rules (and legacy root recurring transactions) for target_month (YYYY-MM).
    """
    if not target_month or len(target_month) != 7 or '-' not in target_month:
        return
    try:
        t_year, t_month = map(int, target_month.split('-'))
    except ValueError:
        return

    now = datetime.now().isoformat()
    inserted = False

    # 1. Materialize from recurring_rules (v1.2 Engine)
    active_rules = conn.execute("""
        SELECT * FROM recurring_rules
        WHERE is_active = 1
          AND substr(start_date, 1, 7) <= ?
          AND (end_date IS NULL OR end_date = '' OR substr(end_date, 1, 7) >= ?)
    """, (target_month, target_month)).fetchall()

    for rule in active_rules:
        freq = rule['frequency'] or 'mensal'
        if freq == 'anual':
            try:
                s_month = int((rule['start_date'] or '2026-01-01').split('-')[1])
            except (IndexError, ValueError):
                s_month = t_month
            if s_month != t_month:
                continue

        existing = conn.execute("""
            SELECT id FROM transactions
            WHERE recurring_rule_id = ? AND date LIKE ?
        """, (rule['id'], f"{target_month}%")).fetchone()
        if existing:
            continue

        max_day = calendar.monthrange(t_year, t_month)[1]
        day = min(max(1, int(rule['day_of_month'] or 1)), max_day)
        new_date = f"{target_month}-{day:02d}"
        txn_type = 'income' if rule['type'] == 'receita' else 'expense'
        amt_val = float(rule['amount'] or 0.0)
        amt_cents = int(rule['amount_cents'] or round(amt_val * 100))

        conn.execute("""
            INSERT INTO transactions (
                description, amount_cents, amount, type, category, category_id,
                recurring_rule_id, account, date, transaction_date,
                is_settled, is_recurring, recurrence, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
        """, (
            rule['description'],
            amt_cents,
            amt_val,
            txn_type,
            rule['category'] or 'Outros',
            rule['category_id'],
            rule['id'],
            rule['account'] or 'Conta Corrente',
            new_date,
            new_date,
            freq,
            now
        ))
        conn.execute("UPDATE recurring_rules SET last_generated_date = ? WHERE id = ?", (new_date, rule['id']))
        inserted = True

    # 2. Fallback for any unlinked root recurring transactions
    roots = conn.execute("""
        SELECT * FROM transactions
        WHERE is_recurring = 1
          AND recurring_rule_id IS NULL
          AND (parent_recurring_id IS NULL OR parent_recurring_id = 0)
          AND substr(date, 1, 7) < ?
    """, (target_month,)).fetchall()

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
    app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_BYTES

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    db_path = os.environ.get('NEXUS_DB', os.path.join(project_root, 'nexus.db'))
    upload_dir = os.environ.get('NEXUS_UPLOAD_DIR', os.path.join(project_root, 'uploads'))

    if test_config:
        if 'DATABASE' in test_config:
            db_path = test_config['DATABASE']
        if 'UPLOAD_FOLDER' in test_config:
            upload_dir = test_config['UPLOAD_FOLDER']

    os.makedirs(upload_dir, exist_ok=True)
    app.config['DATABASE'] = db_path
    app.config['UPLOAD_FOLDER'] = upload_dir

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

        ensure_recurring_transactions_for_month(conn, current_month)

        pending_tasks = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status != 'done' AND status != 'archived'"
        ).fetchone()[0]
        urgent_tasks = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE priority = 'urgent' AND status != 'done' AND status != 'archived'"
        ).fetchone()[0]

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

        focus_row = conn.execute("""
            SELECT COALESCE(SUM(duration_minutes), 0), COUNT(*)
            FROM time_sessions
            WHERE session_type = 'focus' AND completed = 1 AND started_at LIKE ?
        """, (f"{today}%",)).fetchone()
        today_focus_min = focus_row[0]
        today_sessions = focus_row[1]

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

        active_goals_rows = conn.execute("""
            SELECT * FROM goals
            WHERE status = 'em_andamento'
            ORDER BY id DESC LIMIT 4
        """).fetchall()
        active_goals_count = conn.execute(
            "SELECT COUNT(*) FROM goals WHERE status = 'em_andamento'"
        ).fetchone()[0]

        notes_count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]

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
            'recent_ideas': [dict_from_row(r) for r in recent_ideas_rows],
            'active_goals_count': active_goals_count,
            'active_goals': [enrich_goal(r) for r in active_goals_rows],
            'notes_count': notes_count
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

    # ------------------- PONTO 1: Decentralized Attachments ([RF01], [RNF01], RN01) -------------------
    @app.route('/api/uploads', methods=['POST'])
    def upload_attachment():
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'error': 'Nenhum arquivo enviado'}), 400
        file_storage = request.files['file']
        if not file_storage or not file_storage.filename:
            return jsonify({'status': 'error', 'error': 'Nome de arquivo inválido'}), 400

        entity_type = (request.form.get('entity_type') or 'note').strip().lower()
        if entity_type not in ('task', 'note', 'idea', 'transaction'):
            return jsonify({'status': 'error', 'error': 'entity_type inválido'}), 400

        try:
            entity_id = int(request.form.get('entity_id') or 0)
        except ValueError:
            return jsonify({'status': 'error', 'error': 'entity_id inválido'}), 400
        if entity_id <= 0:
            return jsonify({'status': 'error', 'error': 'entity_id é obrigatório'}), 400

        orig_name = secure_filename(file_storage.filename) or 'anexo.bin'
        ext = os.path.splitext(orig_name)[1].lower()[:16]
        unique_name = f"{uuid.uuid4().hex}{ext}"
        physical_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)

        file_storage.save(physical_path)
        file_size = os.path.getsize(physical_path)
        if file_size > MAX_UPLOAD_BYTES:
            os.remove(physical_path)
            return jsonify({'status': 'error', 'error': 'Arquivo excede o limite de 15 MB'}), 413

        mime_type = file_storage.mimetype or 'application/octet-stream'
        storage_rel = f"uploads/{unique_name}"
        now = datetime.now().isoformat()

        conn = get_db()
        cur = conn.execute("""
            INSERT INTO attachments (filename, storage_path, file_size, mime_type, entity_type, entity_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (orig_name, storage_rel, file_size, mime_type, entity_type, entity_id, now))
        conn.commit()

        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (cur.lastrowid,)).fetchone()
        return jsonify(dict_from_row(row)), 201

    @app.route('/api/attachments/<string:entity_type>/<int:entity_id>', methods=['GET'])
    def list_attachments(entity_type, entity_id):
        conn = get_db()
        rows = conn.execute("""
            SELECT * FROM attachments
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY id DESC
        """, (entity_type.lower(), entity_id)).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/attachments/file/<int:attachment_id>', methods=['GET'])
    def download_attachment_file(attachment_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
        if not row:
            return jsonify({'status': 'error', 'error': 'Anexo não encontrado'}), 404
        fname = os.path.basename(row['storage_path'])
        return send_from_directory(
            app.config['UPLOAD_FOLDER'],
            fname,
            download_name=row['filename'],
            as_attachment=request.args.get('download') == '1'
        )

    @app.route('/api/attachments/<int:attachment_id>', methods=['DELETE'])
    def delete_attachment(attachment_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
        if not row:
            return jsonify({'status': 'error', 'error': 'Anexo não encontrado'}), 404

        fname = os.path.basename(row['storage_path'])
        physical_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
        if os.path.exists(physical_path):
            try:
                os.remove(physical_path)
            except OSError:
                pass

        conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
        conn.commit()
        return jsonify({'status': 'success', 'success': True, 'deleted_id': attachment_id})

    # ------------------- PONTO 2: Goals & Milestones Module ([RF02], [RF03], RN02) -------------------
    @app.route('/api/goals', methods=['GET', 'POST'])
    def handle_goals():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            title = (data.get('title') or '').strip()
            if not title:
                return jsonify({'status': 'error', 'error': 'Título da meta é obrigatório'}), 400

            description = (data.get('description') or '').strip()
            category = (data.get('category') or 'pessoal').strip().lower()
            if category not in ('financas', 'estudos', 'atividades', 'pessoal'):
                category = 'pessoal'

            goal_type = (data.get('goal_type') or 'quantitativa').strip().lower()
            if goal_type not in ('monetaria', 'quantitativa', 'qualitativa'):
                goal_type = 'quantitativa'

            target_raw = data.get('target_value')
            target_value = float(target_raw) if (target_raw is not None and str(target_raw).strip() != '') else None
            current_value = float(data.get('current_value') or 0.0)
            unit = (data.get('unit') or ('R$' if goal_type == 'monetaria' else 'unidades')).strip()
            deadline = data.get('deadline') or None
            status = (data.get('status') or 'em_andamento').strip().lower()
            if status not in ('em_andamento', 'alcancada', 'pausada'):
                status = 'em_andamento'

            now = datetime.now().isoformat()
            completed_at = now if status == 'alcancada' else None

            cur = conn.execute("""
                INSERT INTO goals (
                    title, description, category, goal_type, target_value,
                    current_value, unit, deadline, status, created_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title, description, category, goal_type, target_value,
                current_value, unit, deadline, status, now, completed_at
            ))
            conn.commit()
            row = conn.execute("SELECT * FROM goals WHERE id = ?", (cur.lastrowid,)).fetchone()
            return jsonify(enrich_goal(row)), 201

        # GET
        status = request.args.get('status')
        category = request.args.get('category')
        query = "SELECT * FROM goals WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY CASE status WHEN 'em_andamento' THEN 0 WHEN 'pausada' THEN 1 ELSE 2 END, id DESC"
        rows = conn.execute(query, params).fetchall()
        return jsonify([enrich_goal(r) for r in rows])

    @app.route('/api/goals/<int:goal_id>', methods=['GET', 'PUT', 'DELETE'])
    def goal_detail(goal_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if not row:
            return jsonify({'status': 'error', 'error': 'Meta não encontrada'}), 404

        if request.method == 'GET':
            return jsonify(enrich_goal(row))

        if request.method == 'DELETE':
            conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
            conn.commit()
            return jsonify({'status': 'success', 'success': True, 'deleted_id': goal_id})

        # PUT
        data = request.get_json() or {}
        current = dict(row)
        title = data.get('title', current['title'])
        description = data.get('description', current['description'])
        category = data.get('category', current['category'])
        goal_type = data.get('goal_type', current['goal_type'])
        target_value = data.get('target_value', current['target_value'])
        if target_value == '':
            target_value = None
        elif target_value is not None:
            target_value = float(target_value)
        current_value = float(data.get('current_value', current['current_value'] or 0.0))
        unit = data.get('unit', current['unit'])
        deadline = data.get('deadline', current['deadline'])
        status = data.get('status', current['status'])
        completed_at = datetime.now().isoformat() if status == 'alcancada' and not current.get('completed_at') else current.get('completed_at')

        conn.execute("""
            UPDATE goals
            SET title = ?, description = ?, category = ?, goal_type = ?, target_value = ?,
                current_value = ?, unit = ?, deadline = ?, status = ?, completed_at = ?
            WHERE id = ?
        """, (title, description, category, goal_type, target_value, current_value, unit, deadline, status, completed_at, goal_id))
        conn.commit()
        updated = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        return jsonify(enrich_goal(updated))

    @app.route('/api/goals/<int:goal_id>/progress', methods=['PATCH', 'POST'])
    def update_goal_progress(goal_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if not row:
            return jsonify({'status': 'error', 'error': 'Meta não encontrada'}), 404

        data = request.get_json(silent=True) or {}
        current = float(row['current_value'] or 0.0)
        if 'current_value' in data and data['current_value'] is not None:
            new_val = float(data['current_value'])
        else:
            delta = float(data.get('delta', 1.0))
            new_val = max(0.0, current + delta)

        target = float(row['target_value']) if row['target_value'] is not None else None
        status = data.get('status', row['status'])
        completed_at = row['completed_at']

        if target is not None and target > 0 and new_val >= target and 'status' not in data:
            status = 'alcancada'
            completed_at = completed_at or datetime.now().isoformat()
        elif status == 'alcancada' and not completed_at:
            completed_at = datetime.now().isoformat()

        conn.execute("""
            UPDATE goals
            SET current_value = ?, status = ?, completed_at = ?
            WHERE id = ?
        """, (round(new_val, 2), status, completed_at, goal_id))
        conn.commit()
        updated = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        return jsonify(enrich_goal(updated))

    # ------------------- PONTO 3: Notes / Knowledge Base Module ([RF04]) -------------------
    @app.route('/api/notes', methods=['GET', 'POST'])
    def handle_notes():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            title = (data.get('title') or '').strip()
            if not title:
                return jsonify({'status': 'error', 'error': 'Título da anotação é obrigatório'}), 400

            content = data.get('content') or ''
            folder = (data.get('folder') or 'Geral').strip() or 'Geral'
            tags = (data.get('tags') or '').strip()
            is_pinned = 1 if data.get('is_pinned') in (True, 1, '1', 'true') else 0
            now = datetime.now().isoformat()

            cur = conn.execute("""
                INSERT INTO notes (title, content, folder, tags, is_pinned, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (title, content, folder, tags, is_pinned, now, now))
            conn.commit()
            note = conn.execute("SELECT * FROM notes WHERE id = ?", (cur.lastrowid,)).fetchone()
            res_dict = dict_from_row(note)
            res_dict['attachments'] = []
            return jsonify(res_dict), 201

        # GET
        folder = request.args.get('folder')
        tag = request.args.get('tag')
        q = request.args.get('q')

        query = """
            SELECT n.*,
                   (SELECT COUNT(*) FROM attachments a WHERE a.entity_type = 'note' AND a.entity_id = n.id) as attachments_count
            FROM notes n
            WHERE 1=1
        """
        params = []
        if folder and folder != 'all':
            query += " AND n.folder = ?"
            params.append(folder)
        if tag:
            query += " AND n.tags LIKE ?"
            params.append(f"%{tag}%")
        if q:
            query += " AND (n.title LIKE ? OR n.content LIKE ? OR n.tags LIKE ? OR n.folder LIKE ?)"
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"])

        query += " ORDER BY n.is_pinned DESC, n.updated_at DESC, n.id DESC"
        rows = conn.execute(query, params).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/notes/<int:note_id>', methods=['GET', 'PUT', 'DELETE'])
    def note_detail(note_id):
        conn = get_db()
        note = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not note:
            return jsonify({'status': 'error', 'error': 'Anotação não encontrada'}), 404

        if request.method == 'GET':
            d = dict_from_row(note)
            atts = conn.execute(
                "SELECT * FROM attachments WHERE entity_type = 'note' AND entity_id = ? ORDER BY id DESC",
                (note_id,)
            ).fetchall()
            d['attachments'] = [dict_from_row(a) for a in atts]
            return jsonify(d)

        if request.method == 'DELETE':
            delete_entity_attachments(conn, app.config['UPLOAD_FOLDER'], 'note', note_id)
            conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            conn.commit()
            return jsonify({'status': 'success', 'success': True, 'deleted_id': note_id})

        # PUT
        data = request.get_json() or {}
        current = dict_from_row(note)
        title = data.get('title', current['title'])
        content = data.get('content', current['content'])
        folder = (data.get('folder', current['folder']) or 'Geral').strip()
        tags = data.get('tags', current['tags'])
        if 'is_pinned' in data:
            is_pinned = 1 if data.get('is_pinned') in (True, 1, '1', 'true') else 0
        else:
            is_pinned = current['is_pinned']
        now = datetime.now().isoformat()

        conn.execute("""
            UPDATE notes
            SET title = ?, content = ?, folder = ?, tags = ?, is_pinned = ?, updated_at = ?
            WHERE id = ?
        """, (title, content, folder, tags, is_pinned, now, note_id))
        conn.commit()
        updated = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return jsonify(dict_from_row(updated))

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
                    title, description, status, priority, due_date, category, category_id, goal_id,
                    recurrence, estimated_pomodoros, completed_pomodoros,
                    pomodoro_duration_minutes, created_at, updated_at
                )
                VALUES (?, ?, 'todo', ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """, (
                task_dict['title'],
                task_dict.get('description', ''),
                task_dict['priority'],
                next_due,
                task_dict.get('category', 'Geral'),
                task_dict.get('category_id'),
                task_dict.get('goal_id'),
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
            goal_id = int(data['goal_id']) if data.get('goal_id') else None
            recurrence = normalize_recurrence(data.get('recurrence', 'nenhuma'))
            estimated = int(data.get('estimated_pomodoros') or 1)
            pomodoro_duration = int(data.get('pomodoro_duration_minutes') or 25)
            now = datetime.now().isoformat()
            completed_at = now if status == 'done' else None

            cur = conn.execute("""
                INSERT INTO tasks (
                    title, description, status, priority, due_date, category, category_id, goal_id,
                    recurrence, estimated_pomodoros, completed_pomodoros,
                    pomodoro_duration_minutes, created_at, updated_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """, (
                title, description, status, priority, due_date, category, category_id, goal_id,
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

        query = """
            SELECT t.*,
                   (SELECT COUNT(*) FROM attachments a WHERE a.entity_type = 'task' AND a.entity_id = t.id) as attachments_count
            FROM tasks t
            WHERE 1=1
        """
        params = []
        if status:
            query += " AND t.status = ?"
            params.append(normalize_task_status(status))
        if priority:
            query += " AND t.priority = ?"
            params.append(normalize_task_priority(priority))
        if category:
            query += " AND t.category = ?"
            params.append(category)
        if due_date:
            query += " AND t.due_date = ?"
            params.append(due_date)

        query += " ORDER BY CASE t.priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, CASE WHEN t.due_date IS NULL THEN 1 ELSE 0 END, t.due_date ASC, t.id DESC"
        rows = conn.execute(query, params).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/tasks/<int:task_id>', methods=['GET', 'PUT', 'DELETE'])
    def task_detail(task_id):
        conn = get_db()
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            return jsonify({'status': 'error', 'error': 'Tarefa não encontrada'}), 404

        if request.method == 'GET':
            d = dict_from_row(task)
            atts = conn.execute(
                "SELECT * FROM attachments WHERE entity_type = 'task' AND entity_id = ? ORDER BY id DESC",
                (task_id,)
            ).fetchall()
            d['attachments'] = [dict_from_row(a) for a in atts]
            return jsonify(d)

        if request.method == 'DELETE':
            delete_entity_attachments(conn, app.config['UPLOAD_FOLDER'], 'task', task_id)
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
        goal_id = int(data['goal_id']) if data.get('goal_id') else (None if 'goal_id' in data else current.get('goal_id'))
        recurrence = normalize_recurrence(data['recurrence']) if 'recurrence' in data else normalize_recurrence(current.get('recurrence', 'nenhuma'))
        estimated = data.get('estimated_pomodoros', current['estimated_pomodoros'])
        completed = data.get('completed_pomodoros', current['completed_pomodoros'])
        pomodoro_duration = data.get('pomodoro_duration_minutes', current.get('pomodoro_duration_minutes', 25))
        completed_at = now if (status == 'done' and prev_status != 'done') else (None if status != 'done' else current.get('completed_at'))

        conn.execute("""
            UPDATE tasks
            SET title = ?, description = ?, status = ?, priority = ?, due_date = ?, category = ?,
                category_id = ?, goal_id = ?, recurrence = ?, estimated_pomodoros = ?, completed_pomodoros = ?,
                pomodoro_duration_minutes = ?, updated_at = ?, completed_at = ?
            WHERE id = ?
        """, (
            title, description, status, priority, due_date, category,
            category_id, goal_id, recurrence, estimated, completed,
            pomodoro_duration, now, completed_at, task_id
        ))

        if prev_status != 'done' and status == 'done' and goal_id:
            increment_goal_progress(conn, goal_id, 1.0)

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

        if prev_status != 'done' and new_status == 'done' and current.get('goal_id'):
            increment_goal_progress(conn, current['goal_id'], 1.0)

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

            if task_id and completed == 1 and session_type == 'focus':
                conn.execute("""
                    UPDATE tasks
                    SET completed_pomodoros = completed_pomodoros + 1, updated_at = ?
                    WHERE id = ?
                """, (now_iso, task_id))
                t_row = conn.execute("SELECT goal_id FROM tasks WHERE id = ?", (task_id,)).fetchone()
                if t_row and t_row['goal_id']:
                    increment_goal_progress(conn, t_row['goal_id'], 1.0)

            conn.commit()
            new_id = cur.lastrowid
            session = conn.execute("SELECT * FROM time_sessions WHERE id = ?", (new_id,)).fetchone()
            return jsonify(dict_from_row(session)), 201

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

    # ------------------- PONTO 4: Finance Recurring Rules & Projection ([RF05], [RF06], [RF07], RN03) -------------------
    @app.route('/api/finance/recurring-rules', methods=['GET', 'POST'])
    def handle_recurring_rules():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            description = (data.get('description') or '').strip()
            if not description:
                return jsonify({'status': 'error', 'error': 'Descrição da regra recorrente é obrigatória'}), 400

            rule_type = normalize_rule_type(data.get('type', 'despesa'))
            if 'amount_cents' in data and data['amount_cents'] is not None:
                amount_cents = int(data['amount_cents'])
                amount_val = round(amount_cents / 100.0, 2)
            else:
                amount_val = round(float(data.get('amount', 0)), 2)
                amount_cents = int(round(amount_val * 100))

            if amount_cents <= 0:
                return jsonify({'status': 'error', 'error': 'Valor deve ser positivo'}), 400

            category = (data.get('category') or ('Salário' if rule_type == 'receita' else 'Moradia')).strip()
            category_id = resolve_category_id(conn, category, data.get('category_id'))
            account = (data.get('account') or 'Conta Corrente').strip()
            freq = normalize_recurrence(data.get('frequency') or data.get('recurrence') or 'mensal')
            if freq not in ('semanal', 'mensal', 'anual'):
                freq = 'mensal'

            start_date = data.get('start_date') or date.today().isoformat()
            end_date = data.get('end_date') or None
            try:
                default_day = int(start_date.split('-')[2][:2])
            except (IndexError, ValueError):
                default_day = date.today().day
            day_of_month = min(31, max(1, int(data.get('day_of_month') or default_day)))
            is_active = 1 if data.get('is_active', True) in (True, 1, '1', 'true') else 0
            now = datetime.now().isoformat()

            cur = conn.execute("""
                INSERT INTO recurring_rules (
                    type, description, amount, amount_cents, category, category_id,
                    account, frequency, day_of_month, start_date, end_date,
                    is_active, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rule_type, description, amount_val, amount_cents, category, category_id,
                account, freq, day_of_month, start_date, end_date, is_active, now
            ))
            rule_id = cur.lastrowid
            conn.commit()

            # Materialize for start_date month if active
            if is_active and len(start_date) >= 7:
                ensure_recurring_transactions_for_month(conn, start_date[:7])

            row = conn.execute("SELECT * FROM recurring_rules WHERE id = ?", (rule_id,)).fetchone()
            return jsonify(dict_from_row(row)), 201

        # GET
        rows = conn.execute("""
            SELECT * FROM recurring_rules
            ORDER BY is_active DESC, day_of_month ASC, id DESC
        """).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/finance/recurring-rules/<int:rule_id>', methods=['PUT', 'PATCH', 'DELETE'])
    def recurring_rule_detail(rule_id):
        conn = get_db()
        rule = conn.execute("SELECT * FROM recurring_rules WHERE id = ?", (rule_id,)).fetchone()
        if not rule:
            return jsonify({'status': 'error', 'error': 'Regra recorrente não encontrada'}), 404

        if request.method == 'DELETE':
            # Unlink past transactions without deleting history ([RF06])
            conn.execute("UPDATE transactions SET recurring_rule_id = NULL, is_recurring = 0 WHERE recurring_rule_id = ?", (rule_id,))
            conn.execute("DELETE FROM recurring_rules WHERE id = ?", (rule_id,))
            conn.commit()
            return jsonify({'status': 'success', 'success': True, 'deleted_id': rule_id})

        data = request.get_json(silent=True) or {}
        current = dict_from_row(rule)

        if request.method == 'PATCH':
            if 'is_active' in data:
                is_active = 1 if data['is_active'] in (True, 1, '1', 'true') else 0
            else:
                is_active = 0 if current['is_active'] == 1 else 1
            conn.execute("UPDATE recurring_rules SET is_active = ? WHERE id = ?", (is_active, rule_id))
            conn.commit()
            updated = conn.execute("SELECT * FROM recurring_rules WHERE id = ?", (rule_id,)).fetchone()
            return jsonify(dict_from_row(updated))

        # PUT ([RF06], RN03)
        description = (data.get('description', current['description']) or '').strip()
        rule_type = normalize_rule_type(data['type']) if 'type' in data else current['type']
        if 'amount_cents' in data and data['amount_cents'] is not None:
            amount_cents = int(data['amount_cents'])
            amount_val = round(amount_cents / 100.0, 2)
        elif 'amount' in data and data['amount'] is not None:
            amount_val = round(float(data['amount']), 2)
            amount_cents = int(round(amount_val * 100))
        else:
            amount_val = float(current['amount'])
            amount_cents = int(current['amount_cents'])

        category = data.get('category', current.get('category', 'Outros'))
        category_id = resolve_category_id(conn, category, data.get('category_id', current.get('category_id')))
        account = data.get('account', current.get('account', 'Conta Corrente'))
        freq = normalize_recurrence(data.get('frequency', current['frequency']))
        if freq not in ('semanal', 'mensal', 'anual'):
            freq = 'mensal'
        day_of_month = min(31, max(1, int(data.get('day_of_month', current['day_of_month'] or 1))))
        start_date = data.get('start_date', current['start_date'])
        end_date = data.get('end_date', current['end_date'])
        is_active = 1 if data.get('is_active', current['is_active']) in (True, 1, '1', 'true') else 0

        conn.execute("""
            UPDATE recurring_rules
            SET type = ?, description = ?, amount = ?, amount_cents = ?,
                category = ?, category_id = ?, account = ?, frequency = ?,
                day_of_month = ?, start_date = ?, end_date = ?, is_active = ?
            WHERE id = ?
        """, (
            rule_type, description, amount_val, amount_cents,
            category, category_id, account, freq,
            day_of_month, start_date, end_date, is_active, rule_id
        ))

        # RN03: Optionally update current month's materialized transaction if requested
        if data.get('apply_current_month'):
            cur_month = datetime.now().strftime('%Y-%m')
            t_year, t_month = map(int, cur_month.split('-'))
            max_d = calendar.monthrange(t_year, t_month)[1]
            new_d = f"{cur_month}-{min(day_of_month, max_d):02d}"
            txn_type = 'income' if rule_type == 'receita' else 'expense'
            conn.execute("""
                UPDATE transactions
                SET description = ?, amount_cents = ?, amount = ?, type = ?,
                    category = ?, category_id = ?, date = ?, transaction_date = ?
                WHERE recurring_rule_id = ? AND date LIKE ?
            """, (
                description, amount_cents, amount_val, txn_type,
                category, category_id, new_d, new_d, rule_id, f"{cur_month}%"
            ))

        conn.commit()
        updated = conn.execute("SELECT * FROM recurring_rules WHERE id = ?", (rule_id,)).fetchone()
        return jsonify(dict_from_row(updated))

    @app.route('/api/finance/projection', methods=['GET'])
    def finance_projection():
        """
        [RF07]: Simulates future cashflow for the next 1, 2, and 3 months (D+30, D+60, D+90)
        based on active recurring_rules.
        """
        conn = get_db()
        months_count = min(12, max(1, int(request.args.get('months', 3))))
        base_month_str = request.args.get('start_month') or datetime.now().strftime('%Y-%m')
        try:
            b_year, b_month = map(int, base_month_str.split('-'))
        except ValueError:
            now_d = date.today()
            b_year, b_month = now_d.year, now_d.month

        # Current month actual balance
        ensure_recurring_transactions_for_month(conn, f"{b_year:04d}-{b_month:02d}")
        cur_rows = conn.execute("""
            SELECT type, COALESCE(SUM(amount_cents), 0) as total
            FROM transactions
            WHERE date LIKE ?
            GROUP BY type
        """, (f"{b_year:04d}-{b_month:02d}%",)).fetchall()
        cur_inc = sum(r['total'] for r in cur_rows if r['type'] == 'income')
        cur_exp = sum(r['total'] for r in cur_rows if r['type'] == 'expense')
        current_balance_cents = cur_inc - cur_exp

        active_rules = conn.execute("SELECT * FROM recurring_rules WHERE is_active = 1 ORDER BY day_of_month ASC").fetchall()

        projections = []
        cumulative_cents = current_balance_cents

        for offset in range(1, months_count + 1):
            total_m = (b_year * 12 + (b_month - 1)) + offset
            p_year = total_m // 12
            p_month = (total_m % 12) + 1
            m_str = f"{p_year:04d}-{p_month:02d}"

            proj_inc = 0
            proj_exp = 0
            items = []

            for r in active_rules:
                if r['end_date'] and r['end_date'][:7] < m_str:
                    continue
                freq = r['frequency'] or 'mensal'
                amt_c = int(r['amount_cents'] or round(float(r['amount'] or 0) * 100))
                if freq == 'semanal':
                    amt_c = amt_c * 4
                elif freq == 'anual':
                    try:
                        s_m = int((r['start_date'] or '2026-01-01').split('-')[1])
                    except (IndexError, ValueError):
                        s_m = p_month
                    if s_m != p_month:
                        continue

                if r['type'] == 'receita':
                    proj_inc += amt_c
                else:
                    proj_exp += amt_c

                items.append({
                    'rule_id': r['id'],
                    'description': r['description'],
                    'type': r['type'],
                    'day_of_month': r['day_of_month'],
                    'frequency': freq,
                    'amount_cents': amt_c
                })

            net_c = proj_inc - proj_exp
            cumulative_cents += net_c
            projections.append({
                'horizon_label': f"D+{offset * 30}",
                'month': m_str,
                'projected_income_cents': proj_inc,
                'projected_expense_cents': proj_exp,
                'projected_net_cents': net_c,
                'cumulative_free_balance_cents': cumulative_cents,
                'items': items
            })

        return jsonify({
            'base_month': f"{b_year:04d}-{b_month:02d}",
            'current_balance_cents': current_balance_cents,
            'projections': projections
        })

    # ------------------- Finance Transactions Module -------------------
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
            goal_id = int(data['goal_id']) if data.get('goal_id') else None
            account = (data.get('account') or 'Carteira').strip()
            txn_date = data.get('date') or data.get('transaction_date') or date.today().isoformat()
            is_settled = int(data.get('is_settled', 1))

            is_recurring_flag = 1 if data.get('is_recurring') in (True, 1, '1', 'true') else 0
            recurrence = normalize_recurrence(data.get('recurrence', 'mensal' if is_recurring_flag else 'nenhuma'))
            if recurrence != 'nenhuma':
                is_recurring_flag = 1

            now = datetime.now().isoformat()
            recurring_rule_id = data.get('recurring_rule_id')

            # If user creates a recurring transaction directly, also register it in recurring_rules
            if is_recurring_flag == 1 and not recurring_rule_id:
                r_type = 'receita' if txn_type == 'income' else 'despesa'
                freq = recurrence if recurrence in ('semanal', 'mensal', 'anual') else 'mensal'
                try:
                    day_m = min(31, max(1, int(txn_date.split('-')[2][:2])))
                except (IndexError, ValueError):
                    day_m = 1
                rule_cur = conn.execute("""
                    INSERT INTO recurring_rules (
                        type, description, amount, amount_cents, category, category_id,
                        account, frequency, day_of_month, start_date, is_active,
                        last_generated_date, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """, (
                    r_type, description, amount_decimal, amount_cents, category, category_id,
                    account, freq, day_m, txn_date, txn_date, now
                ))
                recurring_rule_id = rule_cur.lastrowid

            cur = conn.execute("""
                INSERT INTO transactions (
                    description, amount_cents, amount, type, category, category_id,
                    task_id, goal_id, recurring_rule_id, account, date, transaction_date,
                    is_settled, is_recurring, recurrence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                description, amount_cents, amount_decimal, txn_type, category, category_id,
                task_id, goal_id, recurring_rule_id, account, txn_date, txn_date,
                is_settled, is_recurring_flag, recurrence, now
            ))

            # RN02: If transaction is linked to a goal, increment goal progress
            if goal_id:
                increment_goal_progress(conn, goal_id, amount_decimal)

            conn.commit()
            new_id = cur.lastrowid
            txn = conn.execute("SELECT * FROM transactions WHERE id = ?", (new_id,)).fetchone()
            return jsonify(dict_from_row(txn)), 201

        # GET
        month = request.args.get('month')
        if month:
            ensure_recurring_transactions_for_month(conn, month)

        txn_type = request.args.get('type')
        category = request.args.get('category')
        recurring_only = request.args.get('is_recurring')

        query = """
            SELECT tr.*, t.title as task_title, g.title as goal_title,
                   (SELECT COUNT(*) FROM attachments a WHERE a.entity_type = 'transaction' AND a.entity_id = tr.id) as attachments_count
            FROM transactions tr
            LEFT JOIN tasks t ON tr.task_id = t.id
            LEFT JOIN goals g ON tr.goal_id = g.id
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
            if is_rec == 0 and txn['parent_recurring_id']:
                conn.execute(
                    "UPDATE transactions SET is_recurring = 0, recurrence = 'nenhuma' WHERE id = ?",
                    (txn['parent_recurring_id'],)
                )
            if is_rec == 0 and txn['recurring_rule_id']:
                conn.execute(
                    "UPDATE recurring_rules SET is_active = 0 WHERE id = ?",
                    (txn['recurring_rule_id'],)
                )
            conn.commit()
            updated = conn.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,)).fetchone()
            return jsonify(dict_from_row(updated))

        # DELETE
        delete_entity_attachments(conn, app.config['UPLOAD_FOLDER'], 'transaction', txn_id)
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

        rules_rows = conn.execute("""
            SELECT * FROM recurring_rules
            ORDER BY is_active DESC, day_of_month ASC
        """).fetchall()

        return jsonify({
            'month': month,
            'total_income_cents': total_income,
            'total_expense_cents': total_expense,
            'net_balance_cents': total_income - total_expense,
            'recurring_income_cents': recurring_income,
            'recurring_expense_cents': recurring_expense,
            'recurring_transactions': [dict_from_row(r) for r in recurring_rows],
            'recurring_rules': [dict_from_row(r) for r in rules_rows],
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

        stage = request.args.get('stage')
        tag = request.args.get('tag')
        q = request.args.get('q')

        query = """
            SELECT i.*,
                   (SELECT COUNT(*) FROM attachments a WHERE a.entity_type = 'idea' AND a.entity_id = i.id) as attachments_count
            FROM ideas i
            WHERE 1=1
        """
        params = []
        if stage:
            if stage in ('convertida', 'converted'):
                query += " AND i.status = 'convertida'"
            else:
                norm_stage, _ = normalize_idea_stage_and_status(stage, None)
                query += " AND i.stage = ?"
                params.append(norm_stage)
        if tag:
            query += " AND i.tags LIKE ?"
            params.append(f"%{tag}%")
        if q:
            query += " AND (i.title LIKE ? OR i.content LIKE ? OR i.tags LIKE ?)"
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

        query += " ORDER BY i.updated_at DESC, i.id DESC"
        rows = conn.execute(query, params).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/ideas/<int:idea_id>', methods=['GET', 'PUT', 'DELETE'])
    def idea_detail(idea_id):
        conn = get_db()
        idea = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        if not idea:
            return jsonify({'status': 'error', 'error': 'Ideia não encontrada'}), 404

        if request.method == 'GET':
            d = dict_from_row(idea)
            atts = conn.execute(
                "SELECT * FROM attachments WHERE entity_type = 'idea' AND entity_id = ? ORDER BY id DESC",
                (idea_id,)
            ).fetchall()
            d['attachments'] = [dict_from_row(a) for a in atts]
            return jsonify(d)

        if request.method == 'DELETE':
            delete_entity_attachments(conn, app.config['UPLOAD_FOLDER'], 'idea', idea_id)
            conn.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
            conn.commit()
            return jsonify({'status': 'success', 'success': True, 'deleted_id': idea_id})

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
        goals_list = [enrich_goal(r) for r in conn.execute("SELECT * FROM goals ORDER BY id DESC").fetchall()]
        notes_list = [dict_from_row(r) for r in conn.execute("SELECT * FROM notes ORDER BY id DESC").fetchall()]

        if fmt == 'csv':
            output = io.StringIO()
            output.write('\ufeff')
            writer = csv.writer(output)

            if module == 'tasks':
                writer.writerow(['ID', 'Título', 'Status', 'Prioridade', 'Prazo', 'Categoria', 'Recorrência', 'Pomodoros Concluídos', 'Pomodoros Estimados', 'Criado Em'])
                for t in tasks_list:
                    writer.writerow([t['id'], t['title'], t['status'], t['priority'], t['due_date'] or '', t['category'], t.get('recurrence', 'nenhuma'), t['completed_pomodoros'], t['estimated_pomodoros'], t['created_at']])
                filename = f'dreamhub_tarefas_{stamp}.csv'
            elif module == 'notes':
                writer.writerow(['ID', 'Título', 'Pasta', 'Tags', 'Fixada', 'Conteúdo', 'Atualizado Em'])
                for n in notes_list:
                    writer.writerow([n['id'], n['title'], n['folder'], n['tags'], 'Sim' if n['is_pinned'] else 'Não', n['content'], n['updated_at']])
                filename = f'dreamhub_anotacoes_{stamp}.csv'
            elif module == 'goals':
                writer.writerow(['ID', 'Título', 'Categoria', 'Tipo', 'Atual', 'Alvo', 'Unidade', 'Progresso %', 'Status', 'Prazo'])
                for g_item in goals_list:
                    writer.writerow([g_item['id'], g_item['title'], g_item['category'], g_item['goal_type'], g_item['current_value'], g_item['target_value'] or '', g_item['unit'], g_item['progress_percent'], g_item['status'], g_item['deadline'] or ''])
                filename = f'dreamhub_metas_{stamp}.csv'
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

        result = {'exported_at': datetime.now().isoformat(), 'version': APP_VERSION}
        if module in ('tasks', 'all'):
            result['tasks'] = tasks_list
        if module in ('finance', 'transactions', 'all'):
            result['transactions'] = txns_list
        if module in ('ideas', 'all'):
            result['ideas'] = ideas_list
        if module in ('goals', 'all'):
            result['goals'] = goals_list
        if module in ('notes', 'all'):
            result['notes'] = notes_list

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

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8001))
    app.run(host='127.0.0.1', port=port, debug=False)
