import os
import io
import csv
import json
import re
import uuid
import calendar
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, g, send_from_directory, send_file, Response

try:
    from backend.database import get_db_connection, init_db, dict_from_row
except ImportError:
    from database import get_db_connection, init_db, dict_from_row

APP_VERSION = '1.4.0'
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
        'not_done': 'not_done',
        'nao_concluida': 'not_done',
        'nao_concluido': 'not_done',
        'não_concluído': 'not_done',
        'não_concluida': 'not_done',
        'cancelada': 'not_done',
        'cancelado': 'not_done',
        'stop': 'stopped',
        'stopped': 'stopped',
        'parada': 'stopped',
        'parado': 'stopped',
        'interrompida': 'stopped',
        'interrompido': 'stopped',
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

def validate_and_normalize_note_content(note_type_raw, content_raw):
    note_type = (str(note_type_raw or 'text')).strip().lower()
    if note_type not in ('text', 'checklist'):
        raise ValueError("note_type inválido. Use 'text' ou 'checklist'.")

    if note_type == 'checklist':
        if content_raw is None or content_raw == '':
            return 'checklist', '[]'
        if isinstance(content_raw, list):
            parsed = content_raw
        elif isinstance(content_raw, str):
            try:
                parsed = json.loads(content_raw)
            except Exception:
                raise ValueError('O campo content deve ser um JSON array válido quando note_type for checklist.')
        else:
            raise ValueError('O campo content deve ser um JSON array válido quando note_type for checklist.')

        if not isinstance(parsed, list):
            raise ValueError('O campo content deve ser um array JSON de objetos [{text, done}] quando note_type for checklist.')

        normalized_items = []
        for item in parsed:
            if isinstance(item, dict):
                text_val = str(item.get('text', '')).strip()
                if text_val:
                    normalized_items.append({
                        'text': text_val,
                        'done': bool(item.get('done', False))
                    })
            elif isinstance(item, str) and item.strip():
                normalized_items.append({
                    'text': item.strip(),
                    'done': False
                })
        return 'checklist', json.dumps(normalized_items, ensure_ascii=False)

    # note_type == 'text'
    if isinstance(content_raw, (list, dict)):
        return 'text', json.dumps(content_raw, ensure_ascii=False)
    return 'text', str(content_raw or '')

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


def _parse_days_of_week(days_str: str) -> set:
    if not days_str:
        return set()
    res = set()
    for part in str(days_str).split(','):
        part = part.strip()
        if part.isdigit():
            d = int(part)
            if 0 <= d <= 6:
                res.add(d)
    return res

def _date_to_js_weekday(d_obj: date) -> int:
    # Python weekday(): 0=Mon..6=Sun -> JS/Cron convention: 0=Sun, 1=Mon..6=Sat
    return (d_obj.weekday() + 1) % 7

def _is_routine_suspended_on_date(conn: sqlite3.Connection, routine_id: int, target_date_str: str) -> dict:
    """
    Checks if routine_id has an active temporary suspension covering target_date_str (YYYY-MM-DD).
    Also auto-deactivates expired suspensions where end_date < today (RN02).
    """
    today_str = date.today().isoformat()
    conn.execute("""
        UPDATE daily_routine_suspensions
        SET is_active = 0
        WHERE is_active = 1 AND end_date IS NOT NULL AND end_date != '' AND end_date < ?
    """, (today_str,))

    try:
        d_obj = date.fromisoformat(target_date_str[:10])
    except ValueError:
        return None
    js_wday = _date_to_js_weekday(d_obj)

    susp_rows = conn.execute("""
        SELECT * FROM daily_routine_suspensions
        WHERE routine_id = ? AND is_active = 1
        ORDER BY id DESC
    """, (routine_id,)).fetchall()

    for s in susp_rows:
        s_type = s['suspension_type']
        s_start = (s['start_date'] or '')[:10]
        s_end = (s['end_date'] or '')[:10]
        if s_start and target_date_str < s_start:
            continue
        if s_end and target_date_str > s_end:
            continue
        if s_type == 'date_range':
            if s_start and s_end and s_start <= target_date_str <= s_end:
                return dict_from_row(s)
            elif s_start and not s_end and target_date_str >= s_start:
                return dict_from_row(s)
        elif s_type == 'days_of_week':
            allowed_days = _parse_days_of_week(s['days_of_week'])
            if js_wday in allowed_days:
                return dict_from_row(s)
    return None

def ensure_daily_routines_initialized_for_today(conn: sqlite3.Connection, target_date_str: str = None) -> list:
    """
    [RF02 / Decisão 01 / RN01 / RN02]:
    Transitions scheduled daily_routines for today's weekday into 'em_andamento' at 00:00,
    respecting manual cancellations ('cancelada') and active temporary suspensions.
    Generates immediate push notification payload and records notified_at.
    """
    today_str = (target_date_str or date.today().isoformat())[:10]
    try:
        today_obj = date.fromisoformat(today_str)
    except ValueError:
        today_obj = date.today()
        today_str = today_obj.isoformat()

    js_wday = _date_to_js_weekday(today_obj)
    now_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    notifications = []

    # Auto-expire past suspensions first (RN02)
    conn.execute("""
        UPDATE daily_routine_suspensions
        SET is_active = 0
        WHERE is_active = 1 AND end_date IS NOT NULL AND end_date != '' AND end_date < ?
    """, (today_str,))

    routines = conn.execute("SELECT * FROM daily_routines ORDER BY scheduled_time ASC, id ASC").fetchall()
    changed = False

    for r in routines:
        r_id = r['id']
        r_status = r['status']
        # RN01: Manual cancellation strictly blocks automatic start and notifications
        if r_status == 'cancelada':
            continue

        days_set = _parse_days_of_week(r['days_of_week'])
        is_scheduled_weekday = (js_wday in days_set)
        if not is_scheduled_weekday:
            continue

        active_susp = _is_routine_suspended_on_date(conn, r_id, today_str)
        existing_log = conn.execute("""
            SELECT * FROM daily_routine_logs
            WHERE routine_id = ? AND execution_date = ?
        """, (r_id, today_str)).fetchone()

        if active_susp:
            if not existing_log:
                conn.execute("""
                    INSERT INTO daily_routine_logs (routine_id, execution_date, status, started_at)
                    VALUES (?, ?, 'suspensa', ?)
                """, (r_id, today_str, now_iso))
                if r['active_date'] != today_str:
                    conn.execute("""
                        UPDATE daily_routines
                        SET status = 'agendada', active_date = ?, updated_at = ?
                        WHERE id = ?
                    """, (today_str, now_iso, r_id))
                changed = True
            elif existing_log['status'] not in ('suspensa', 'concluida'):
                conn.execute("""
                    UPDATE daily_routine_logs SET status = 'suspensa' WHERE id = ?
                """, (existing_log['id'],))
                changed = True
            continue

        # Normal active day for this routine
        if not existing_log:
            conn.execute("""
                UPDATE daily_routines
                SET status = 'em_andamento',
                    active_date = ?,
                    elapsed_seconds = 0,
                    updated_at = ?
                WHERE id = ?
            """, (today_str, now_iso, r_id))
            conn.execute("""
                UPDATE daily_routine_tasks
                SET is_done = 0, completed_pomodoros = 0, elapsed_seconds = 0, completed_at = NULL
                WHERE routine_id = ?
            """, (r_id,))
            conn.execute("""
                INSERT INTO daily_routine_logs (
                    routine_id, execution_date, status, started_at,
                    total_focus_seconds, pomodoros_completed, notified_at
                )
                VALUES (?, ?, 'em_andamento', ?, 0, 0, ?)
            """, (r_id, today_str, now_iso, now_iso))
            notifications.append({
                'routine_id': r_id,
                'title': f"Rotina iniciada: {r['title']}",
                'body': f"Sua rotina '{r['title']}' entrou em andamento automaticamente ({today_str}).",
                'notified_at': now_iso,
                'execution_date': today_str
            })
            changed = True
        else:
            # If log was 'suspensa' or 'agendada' because suspension was deleted/expired today, transition to em_andamento
            if existing_log['status'] in ('agendada', 'suspensa') and not active_susp:
                notif_ts = existing_log['notified_at'] or now_iso
                conn.execute("""
                    UPDATE daily_routine_logs
                    SET status = 'em_andamento', notified_at = ?
                    WHERE id = ?
                """, (notif_ts, existing_log['id']))
                conn.execute("""
                    UPDATE daily_routines
                    SET status = 'em_andamento', active_date = ?, updated_at = ?
                    WHERE id = ?
                """, (today_str, now_iso, r_id))
                if not existing_log['notified_at']:
                    notifications.append({
                        'routine_id': r_id,
                        'title': f"Rotina iniciada: {r['title']}",
                        'body': f"Sua rotina '{r['title']}' entrou em andamento automaticamente ({today_str}).",
                        'notified_at': notif_ts,
                        'execution_date': today_str
                    })
                changed = True

    if changed:
        conn.commit()
    return notifications


def _format_minutes_label(total_min) -> str:
    total_min = int(total_min or 0)
    h, m = divmod(total_min, 60)
    if h and m:
        return f"{h}h {m}min"
    if h:
        return f"{h}h"
    return f"{m}min"


def _parse_routine_tasks_payload(tasks_in):
    """Parse routine tasks using hours/minutes duration (v1.4.1). Returns (list, error)."""
    parsed = []
    for t_item in tasks_in or []:
        if isinstance(t_item, str):
            t_item = {'title': t_item}
        if not isinstance(t_item, dict):
            continue
        title = (t_item.get('title') or '').strip()
        if not title:
            continue
        try:
            if t_item.get('duration_minutes') is not None and str(t_item.get('duration_minutes')).strip() != '':
                dur = int(t_item.get('duration_minutes'))
            elif t_item.get('duration_hours') is not None or t_item.get('duration_mins') is not None:
                dur = int(t_item.get('duration_hours') or 0) * 60 + int(t_item.get('duration_mins') or 0)
            else:
                dur = 30
        except (TypeError, ValueError):
            return None, f'Duração inválida na tarefa "{title}"'
        if dur < 1:
            return None, f'A tarefa "{title}" precisa ter duração mínima de 1 minuto'
        parsed.append({
            'title': title,
            'linked_task_id': int(t_item['linked_task_id']) if t_item.get('linked_task_id') else None,
            'duration_minutes': min(dur, 24 * 60),
            'is_done': 1 if (t_item.get('is_done') or t_item.get('done')) else 0,
            'elapsed_seconds': max(0, int(t_item.get('elapsed_seconds') or 0)),
        })
    return parsed, None


def _recalc_routine_total_planned(conn: sqlite3.Connection, r_id: int) -> int:
    total = conn.execute(
        "SELECT COALESCE(SUM(duration_minutes), 0) FROM daily_routine_tasks WHERE routine_id = ?", (r_id,)
    ).fetchone()[0]
    conn.execute("UPDATE daily_routines SET total_planned_minutes = ? WHERE id = ?", (int(total), r_id))
    return int(total)


def _enrich_daily_routine(conn: sqlite3.Connection, r_row, target_date_str: str = None) -> dict:
    if r_row is None:
        return None
    d = dict_from_row(r_row)
    r_id = d['id']
    today_str = (target_date_str or date.today().isoformat())[:10]

    tasks_raw = [dict_from_row(t) for t in conn.execute("""
        SELECT * FROM daily_routine_tasks
        WHERE routine_id = ?
        ORDER BY position ASC, id ASC
    """, (r_id,)).fetchall()]
    tasks = []
    for t in tasks_raw:
        t['done'] = bool(int(t.get('is_done') or 0) == 1)
        t['duration_minutes'] = int(t.get('duration_minutes') or 30)
        t['elapsed_seconds'] = int(t.get('elapsed_seconds') or 0)
        t['duration_label'] = _format_minutes_label(t['duration_minutes'])
        t['estimated_minutes'] = t['duration_minutes']
        for k in ('estimated_pomodoros', 'completed_pomodoros'):
            t.pop(k, None)
        tasks.append(t)

    total_tasks = len(tasks)
    done_tasks = sum(1 for t in tasks if int(t.get('is_done') or 0) == 1)
    progress_pct = round((done_tasks / total_tasks) * 100.0, 1) if total_tasks > 0 else (100.0 if d['status'] == 'concluida' else 0.0)
    total_planned = sum(t['duration_minutes'] for t in tasks)
    done_planned = sum(t['duration_minutes'] for t in tasks if t['done'])

    suspensions = []
    for s in conn.execute("""
        SELECT * FROM daily_routine_suspensions
        WHERE routine_id = ? AND is_active = 1
        ORDER BY id DESC
    """, (r_id,)).fetchall():
        sd = dict_from_row(s)
        sd['reason'] = sd.get('note') or ''
        suspensions.append(sd)

    active_susp_today = _is_routine_suspended_on_date(conn, r_id, today_str)

    log_row = conn.execute("""
        SELECT * FROM daily_routine_logs
        WHERE routine_id = ? AND execution_date = ?
    """, (r_id, today_str)).fetchone()
    log_dict = dict_from_row(log_row) if log_row else None

    interruptions = [dict_from_row(i) for i in conn.execute("""
        SELECT * FROM daily_routine_interruptions
        WHERE routine_id = ? AND execution_date = ?
        ORDER BY id DESC
    """, (r_id, today_str)).fetchall()]

    comments = [dict_from_row(c) for c in conn.execute("""
        SELECT * FROM daily_routine_comments
        WHERE routine_id = ? AND execution_date = ?
        ORDER BY created_at DESC, id DESC
    """, (r_id, today_str)).fetchall()]

    effective_status = d['status']
    if d['status'] != 'cancelada' and active_susp_today is not None:
        effective_status = 'suspensa'
    elif log_dict and log_dict.get('status') in ('suspensa', 'concluida', 'interrompida', 'em_andamento') and d['status'] != 'cancelada':
        effective_status = log_dict['status']

    d['routine_id'] = r_id
    d['routine_status'] = d['status']
    d['status'] = effective_status
    d['notified_at'] = log_dict.get('notified_at') if log_dict else None
    d['total_planned_minutes'] = total_planned
    d['total_planned_label'] = _format_minutes_label(total_planned)
    d['done_planned_minutes'] = done_planned
    for k in ('pomodoro_focus_min', 'pomodoro_short_break_min', 'pomodoro_long_break_min', 'pomodoro_cycles'):
        d.pop(k, None)
    d['tasks'] = tasks
    d['total_tasks'] = total_tasks
    d['done_tasks'] = done_tasks
    d['progress_percent'] = progress_pct
    d['suspensions'] = suspensions
    d['is_suspended_today'] = active_susp_today is not None
    d['active_suspension_today'] = active_susp_today
    d['today_log'] = log_dict
    d['today_interruptions'] = interruptions
    d['interruptions'] = interruptions
    d['today_comments'] = comments
    d['comments'] = comments
    d['is_cancelled'] = (d['routine_status'] == 'cancelada')
    d['can_start'] = (d['routine_status'] != 'cancelada')
    d['can_schedule_suspension'] = (d['routine_status'] != 'cancelada')
    return d


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

    # Lightweight background daemon thread for 00:00 daily turnover (RF02 / Decisão 01)
    if not test_config and os.environ.get('DISABLE_ROUTINE_DAEMON') != '1':
        def _daily_turnover_worker(database_file):
            last_checked_date = None
            while True:
                try:
                    cur_date = date.today().isoformat()
                    if cur_date != last_checked_date:
                        bg_conn = get_db_connection(database_file)
                        try:
                            ensure_daily_routines_initialized_for_today(bg_conn, cur_date)
                        finally:
                            bg_conn.close()
                        last_checked_date = cur_date
                except Exception:
                    pass
                time.sleep(30)

        t = threading.Thread(target=_daily_turnover_worker, args=(db_path,), daemon=True)
        t.start()

    def get_db():
        if 'db' not in g:
            g.db = get_db_connection(app.config['DATABASE'])
        return g.db

    @app.teardown_appcontext
    def close_db(exception):
        db = g.pop('db', None)
        if db is not None:
            db.close()

    @app.before_request
    def handle_preflight():
        if request.method == 'OPTIONS':
            res = Response()
            res.headers['Access-Control-Allow-Origin'] = '*'
            res.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-Requested-With'
            res.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,PATCH,DELETE,OPTIONS'
            return res

    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-Requested-With'
        response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,PATCH,DELETE,OPTIONS'
        return response

    @app.route('/api/<path:subpath>', methods=['OPTIONS'])
    def handle_options(subpath):
        return ('', 204)

    # ------------------- Health, Cockpit ("Meu Dia") & Overview -------------------
    @app.route('/api/health', methods=['GET'])
    def health():
        return jsonify({'status': 'ok', 'app': 'Dream Hub', 'version': APP_VERSION})

    def _build_cockpit_data(conn: sqlite3.Connection):
        today = date.today().isoformat()
        current_month = datetime.now().strftime('%Y-%m')

        ensure_recurring_transactions_for_month(conn, current_month)
        push_notifications = ensure_daily_routines_initialized_for_today(conn, today)

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
            "SELECT COUNT(*) FROM ideas WHERE stage != 'archived' AND status NOT IN ('arquivada', 'convertida') AND stage != 'in_action'"
        ).fetchone()[0]

        recent_ideas_rows = conn.execute("""
            SELECT * FROM ideas
            WHERE stage != 'archived' AND status NOT IN ('arquivada', 'convertida') AND stage != 'in_action' AND converted_task_id IS NULL
            ORDER BY updated_at DESC, id DESC LIMIT 4
        """).fetchall()

        all_goals_rows = conn.execute("""
            SELECT * FROM goals
            ORDER BY CASE WHEN status = 'em_andamento' THEN 0 ELSE 1 END, id DESC
        """).fetchall()
        all_goals_enriched = [enrich_goal(r) for r in all_goals_rows]
        active_goals_enriched = [g for g in all_goals_enriched if g['status'] == 'em_andamento']
        active_goals_count = len(active_goals_enriched)

        # RN04 / RF12: Featured Goal selection logic
        featured_goal_setting = conn.execute(
            "SELECT value FROM user_settings WHERE key = 'featured_goal_id'"
        ).fetchone()
        featured_goal_id_str = (featured_goal_setting['value'] if featured_goal_setting else '').strip()
        featured_goal = None
        candidate_pool = active_goals_enriched if active_goals_enriched else all_goals_enriched
        if len(candidate_pool) == 1:
            featured_goal = candidate_pool[0]
        elif len(candidate_pool) >= 2:
            if featured_goal_id_str.isdigit():
                fg_id = int(featured_goal_id_str)
                featured_goal = next((g for g in all_goals_enriched if g['id'] == fg_id), None)
            if not featured_goal:
                featured_goal = candidate_pool[0]

        available_goals = [
            {
                'id': g['id'],
                'title': g['title'],
                'category': g['category'],
                'status': g['status'],
                'progress_percent': g['progress_percent']
            }
            for g in all_goals_enriched
        ]

        # RF11: Routine of the day summary for Dashboard widget
        all_daily_routines = [
            _enrich_daily_routine(conn, r, today)
            for r in conn.execute("SELECT * FROM daily_routines ORDER BY CASE status WHEN 'em_andamento' THEN 0 WHEN 'interrompida' THEN 1 WHEN 'agendada' THEN 2 WHEN 'concluida' THEN 3 ELSE 4 END, scheduled_time ASC, id DESC").fetchall()
        ]
        routine_today = next((r for r in all_daily_routines if r['status'] in ('em_andamento', 'interrompida', 'concluida') and r.get('active_date') == today), None)
        if not routine_today and all_daily_routines:
            routine_today = next((r for r in all_daily_routines if r['status'] != 'cancelada'), all_daily_routines[0])

        notes_count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]

        finance_summary = {
            'month': current_month,
            'income_cents': income_cents,
            'expense_cents': expense_cents,
            'balance_cents': income_cents - expense_cents,
            'recurring_income_cents': recurring_income_cents,
            'recurring_expense_cents': recurring_expense_cents
        }

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
            'finance': finance_summary,
            'routine_today': routine_today,
            'daily_routines_today': all_daily_routines,
            'featured_goal': featured_goal,
            'available_goals': available_goals,
            'push_notifications': push_notifications,
            'active_ideas': active_ideas,
            'recent_ideas': [dict_from_row(r) for r in recent_ideas_rows],
            'active_goals_count': active_goals_count,
            'active_goals': active_goals_enriched[:4],
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

            try:
                note_type, content = validate_and_normalize_note_content(
                    data.get('note_type', 'text'),
                    data.get('content', '')
                )
            except ValueError as ve:
                return jsonify({'status': 'error', 'error': str(ve)}), 400

            folder = (data.get('folder') or 'Geral').strip() or 'Geral'
            tags = (data.get('tags') or '').strip()
            is_pinned = 1 if data.get('is_pinned') in (True, 1, '1', 'true') else 0
            now = datetime.now().isoformat()

            cur = conn.execute("""
                INSERT INTO notes (title, content, note_type, folder, tags, is_pinned, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, content, note_type, folder, tags, is_pinned, now, now))
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
        raw_note_type = data.get('note_type', current.get('note_type', 'text'))
        raw_content = data.get('content', current['content'])
        try:
            note_type, content = validate_and_normalize_note_content(raw_note_type, raw_content)
        except ValueError as ve:
            return jsonify({'status': 'error', 'error': str(ve)}), 400

        folder = (data.get('folder', current['folder']) or 'Geral').strip()
        tags = data.get('tags', current['tags'])
        if 'is_pinned' in data:
            is_pinned = 1 if data.get('is_pinned') in (True, 1, '1', 'true') else 0
        else:
            is_pinned = current['is_pinned']
        now = datetime.now().isoformat()

        conn.execute("""
            UPDATE notes
            SET title = ?, content = ?, note_type = ?, folder = ?, tags = ?, is_pinned = ?, updated_at = ?
            WHERE id = ?
        """, (title, content, note_type, folder, tags, is_pinned, now, note_id))
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
    def _process_task_completion_or_recurrence(conn: sqlite3.Connection, task_dict: dict, prev_status: str, new_status: str):
        """
        Solução 1: Conceito de 'Tarefa Mestre' (Recorrência Sem Poluição e Gamificação com Streaks).
        Em vez de clonar o card no banco de dados a cada ciclo:
        1) Registra histórico de realização na tabela `task_completions`.
        2) Incrementa streak_count (Ofensiva 🔥).
        3) Atualiza a própria tarefa mestre: avança a due_date para o próximo ciclo,
           reseta completed_pomodoros para 0 e mantém o card em 'todo' para o próximo ciclo.
        """
        rec = normalize_recurrence(task_dict.get('recurrence', 'nenhuma'))
        task_id = task_dict['id']
        now = datetime.now().isoformat()

        if prev_status != 'done' and new_status == 'done':
            # 1) Registra no histórico de execuções (task_history e task_completions)
            pom_done = int(task_dict.get('completed_pomodoros') or 0)
            note_str = f"{pom_done} pomodoro(s)" if pom_done > 0 else "Execução concluída"
            conn.execute("""
                INSERT INTO task_completions (task_id, completed_at, pomodoros_completed)
                VALUES (?, ?, ?)
            """, (task_id, now, pom_done))
            conn.execute("""
                INSERT INTO task_history (task_id, execution_date, notes)
                VALUES (?, ?, ?)
            """, (task_id, now, note_str))

            # 2) Incrementa meta se houver vínculo
            if task_dict.get('goal_id'):
                increment_goal_progress(conn, task_dict['goal_id'], 1.0)

            # 3) Se for recorrente: recicla a tarefa mestre com nova data e streak sem clonar
            if rec != 'nenhuma':
                next_due = compute_next_due_date(task_dict.get('due_date'), rec)
                new_streak = (task_dict.get('streak_count') or 0) + 1

                conn.execute("""
                    UPDATE tasks
                    SET status = 'todo',
                        due_date = ?,
                        streak_count = ?,
                        completed_pomodoros = 0,
                        completed_at = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (next_due, new_streak, now, now, task_id))

                updated_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
                res = dict_from_row(updated_row)
                res['cycle_completed'] = True
                res['streak_incremented'] = True
                res['next_due_date'] = next_due
                res['streak_count'] = new_streak
                return res

        return None

    @app.route('/api/tasks', methods=['GET', 'POST'])
    def handle_tasks():
        conn = get_db()

        # Solução 2: Regra de Arquivamento Automático (24 Horas)
        # Tarefas regulares não-recorrentes concluídas há mais de 24 horas são arquivadas
        try:
            conn.execute("""
                UPDATE tasks
                SET status = 'archived', updated_at = datetime('now')
                WHERE status = 'done'
                  AND recurrence = 'nenhuma'
                  AND completed_at IS NOT NULL
                  AND completed_at < datetime('now', '-24 hours')
            """)
            conn.commit()
        except Exception:
            pass

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
            streak_count = int(data.get('streak_count') or 0)
            estimated = int(data.get('estimated_pomodoros') or 1)
            pomodoro_duration = int(data.get('pomodoro_duration_minutes') or 25)
            now = datetime.now().isoformat()
            completed_at = now if status == 'done' else None

            cur = conn.execute("""
                INSERT INTO tasks (
                    title, description, status, priority, due_date, category, category_id, goal_id,
                    recurrence, streak_count, estimated_pomodoros, completed_pomodoros,
                    pomodoro_duration_minutes, created_at, updated_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """, (
                title, description, status, priority, due_date, category, category_id, goal_id,
                recurrence, streak_count, estimated, pomodoro_duration, now, now, completed_at
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
        q = request.args.get('q')
        include_archived = request.args.get('include_archived') in ('1', 'true')

        query = """
            SELECT t.*,
                   (SELECT COUNT(*) FROM attachments a WHERE a.entity_type = 'task' AND a.entity_id = t.id) as attachments_count,
                   (SELECT COUNT(*) FROM task_history th WHERE th.task_id = t.id) as completions_count
            FROM tasks t
            WHERE 1=1
        """
        params = []
        if status:
            query += " AND t.status = ?"
            params.append(normalize_task_status(status))
        elif not include_archived:
            query += " AND t.status != 'archived'"

        if priority:
            query += " AND t.priority = ?"
            params.append(normalize_task_priority(priority))
        if category:
            query += " AND t.category = ?"
            params.append(category)
        if due_date:
            query += " AND t.due_date = ?"
            params.append(due_date)
        if q:
            query += " AND (t.title LIKE ? OR t.description LIKE ? OR t.category LIKE ?)"
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

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
            hist = conn.execute(
                "SELECT id, task_id, execution_date, notes, execution_date AS completed_at FROM task_history WHERE task_id = ? ORDER BY execution_date DESC, id DESC",
                (task_id,)
            ).fetchall()
            d['completions'] = [dict_from_row(c) for c in hist]
            d['history'] = [dict_from_row(c) for c in hist]
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
        streak_count = int(data.get('streak_count', current.get('streak_count', 0)))
        estimated = data.get('estimated_pomodoros', current['estimated_pomodoros'])
        completed = data.get('completed_pomodoros', current['completed_pomodoros'])
        pomodoro_duration = data.get('pomodoro_duration_minutes', current.get('pomodoro_duration_minutes', 25))
        completed_at = now if (status == 'done' and prev_status != 'done') else (None if status != 'done' else current.get('completed_at'))

        conn.execute("""
            UPDATE tasks
            SET title = ?, description = ?, status = ?, priority = ?, due_date = ?, category = ?,
                category_id = ?, goal_id = ?, recurrence = ?, streak_count = ?, estimated_pomodoros = ?, completed_pomodoros = ?,
                pomodoro_duration_minutes = ?, updated_at = ?, completed_at = ?
            WHERE id = ?
        """, (
            title, description, status, priority, due_date, category,
            category_id, goal_id, recurrence, streak_count, estimated, completed,
            pomodoro_duration, now, completed_at, task_id
        ))

        # Check for Master Card recurrence or standard completion
        master_cycle = _process_task_completion_or_recurrence(conn, current, prev_status, status)
        conn.commit()

        if master_cycle:
            return jsonify(master_cycle)

        updated_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return jsonify(dict_from_row(updated_row))

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

        master_cycle = _process_task_completion_or_recurrence(conn, current, prev_status, new_status)
        conn.commit()

        if master_cycle:
            return jsonify(master_cycle)

        updated_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return jsonify(dict_from_row(updated_row))

    @app.route('/api/tasks/<int:task_id>/history', methods=['GET', 'POST'])
    @app.route('/api/tasks/<int:task_id>/completions', methods=['GET'])
    def task_completions(task_id):
        conn = get_db()
        task = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            return jsonify({'status': 'error', 'error': 'Tarefa não encontrada'}), 404

        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
            exec_date = (data.get('execution_date') or datetime.now().isoformat()).strip()
            notes = (data.get('notes') or '').strip()
            cur = conn.execute("""
                INSERT INTO task_history (task_id, execution_date, notes)
                VALUES (?, ?, ?)
            """, (task_id, exec_date, notes))
            conn.execute("""
                INSERT INTO task_completions (task_id, completed_at, pomodoros_completed)
                VALUES (?, ?, 0)
            """, (task_id, exec_date))
            conn.commit()
            row = conn.execute("""
                SELECT id, task_id, execution_date, notes, execution_date AS completed_at
                FROM task_history WHERE id = ?
            """, (cur.lastrowid,)).fetchone()
            return jsonify(dict_from_row(row)), 201

        date_filter = (request.args.get('date') or request.args.get('q') or '').strip()
        if date_filter:
            rows = conn.execute("""
                SELECT id, task_id, execution_date, notes, execution_date AS completed_at
                FROM task_history
                WHERE task_id = ? AND (execution_date LIKE ? OR notes LIKE ?)
                ORDER BY execution_date DESC, id DESC
            """, (task_id, f"%{date_filter}%", f"%{date_filter}%")).fetchall()
        else:
            rows = conn.execute("""
                SELECT id, task_id, execution_date, notes, execution_date AS completed_at
                FROM task_history
                WHERE task_id = ?
                ORDER BY execution_date DESC, id DESC
            """, (task_id,)).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/tasks/<int:task_id>/archive', methods=['POST'])
    def archive_task(task_id):
        conn = get_db()
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            return jsonify({'status': 'error', 'error': 'Tarefa não encontrada'}), 404
        current_status = task['status']
        new_status = 'todo' if current_status == 'archived' else 'archived'
        now = datetime.now().isoformat()
        conn.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (new_status, now, task_id))
        conn.commit()
        updated = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return jsonify(dict_from_row(updated))

    @app.route('/api/tasks/archive_all_done', methods=['POST'])
    def archive_all_done():
        conn = get_db()
        now = datetime.now().isoformat()
        cur = conn.execute("""
            UPDATE tasks
            SET status = 'archived', updated_at = ?
            WHERE status = 'done' AND recurrence = 'nenhuma'
        """, (now,))
        conn.commit()
        return jsonify({'status': 'success', 'archived_count': cur.rowcount})

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

            # Also include one-off transactions already scheduled in that future month
            scheduled_txns = conn.execute("""
                SELECT * FROM transactions
                WHERE date LIKE ? AND is_recurring = 0 AND recurring_rule_id IS NULL
                ORDER BY date ASC
            """, (f"{m_str}%",)).fetchall()
            for st in scheduled_txns:
                amt_c = int(st['amount_cents'] or round(float(st['amount'] or 0) * 100))
                t_type = 'receita' if st['type'] == 'income' else 'despesa'
                if t_type == 'receita':
                    proj_inc += amt_c
                else:
                    proj_exp += amt_c
                try:
                    d_m = int((st['date'] or '2026-01-01').split('-')[2][:2])
                except (IndexError, ValueError):
                    d_m = 1
                items.append({
                    'transaction_id': st['id'],
                    'description': f"{st['description']} (Agendado)",
                    'type': t_type,
                    'day_of_month': d_m,
                    'frequency': 'única',
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
            if 'is_recurring' in data or 'recurrence' in data:
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
            if 'category' in data and data.get('category'):
                new_cat = str(data['category']).strip()
                new_cat_id = resolve_category_id(conn, new_cat)
                conn.execute(
                    "UPDATE transactions SET category = ?, category_id = ? WHERE id = ?",
                    (new_cat, new_cat_id, txn_id)
                )
            if 'description' in data and data.get('description'):
                new_desc = str(data['description']).strip()
                conn.execute(
                    "UPDATE transactions SET description = ? WHERE id = ?",
                    (new_desc, txn_id)
                )
            if 'amount_cents' in data or 'amount' in data:
                if 'amount_cents' in data and data.get('amount_cents') is not None:
                    new_cents = int(data['amount_cents'])
                else:
                    new_cents = int(round(abs(parse_monetary_float(data.get('amount'))) * 100))
                if new_cents > 0:
                    conn.execute(
                        "UPDATE transactions SET amount_cents = ?, amount = ? WHERE id = ?",
                        (new_cents, round(new_cents / 100.0, 2), txn_id)
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

    @app.route('/api/finance/clear', methods=['POST', 'DELETE'])
    @app.route('/api/finance/transactions/clear', methods=['POST', 'DELETE'])
    @app.route('/api/finances/clear', methods=['POST', 'DELETE'])
    def clear_finance_data():
        conn = get_db()
        data = request.get_json(silent=True) or {}
        scope = (data.get('scope') or request.args.get('scope') or 'all').strip().lower()
        month = (data.get('month') or request.args.get('month') or '').strip()
        include_rules = data.get('include_rules', False) or request.args.get('include_rules') in ('1', 'true', 'True')

        deleted_txns = 0
        deleted_rules = 0

        if scope == 'month' and month:
            txns = conn.execute("SELECT id FROM transactions WHERE date LIKE ?", (f"{month}%",)).fetchall()
            for t in txns:
                delete_entity_attachments(conn, app.config['UPLOAD_FOLDER'], 'transaction', t['id'])
            cur = conn.execute("DELETE FROM transactions WHERE date LIKE ?", (f"{month}%",))
            deleted_txns = cur.rowcount
        else:
            txns = conn.execute("SELECT id FROM transactions").fetchall()
            for t in txns:
                delete_entity_attachments(conn, app.config['UPLOAD_FOLDER'], 'transaction', t['id'])
            cur = conn.execute("DELETE FROM transactions")
            deleted_txns = cur.rowcount

        if include_rules:
            cur_r = conn.execute("DELETE FROM recurring_rules")
            deleted_rules = cur_r.rowcount

        conn.commit()
        return jsonify({
            'status': 'success',
            'success': True,
            'scope': scope,
            'deleted_transactions': deleted_txns,
            'deleted_rules': deleted_rules
        }), 200

    # ------------------- FASE 3: Conciliação Financeira Híbrida (Custo Zero) -------------------

    def parse_monetary_float(val_str) -> float:
        if isinstance(val_str, (int, float)):
            return float(val_str)
        s = re.sub(r'[R$\s"\']', '', str(val_str or ''))
        if not s:
            return 0.0
        if ',' in s and '.' in s:
            if s.rfind(',') > s.rfind('.'):
                s = s.replace('.', '').replace(',', '.')
            else:
                s = s.replace(',', '')
        elif ',' in s:
            s = s.replace(',', '.')
        elif s.count('.') > 1:
            s = s.replace('.', '')
        try:
            return float(s)
        except ValueError:
            return 0.0

    def clean_transaction_description(raw_desc: str) -> str:
        s = (raw_desc or '').strip()
        if not s:
            return 'Transação'

        # 1. Remove CPF/CNPJ block and trailing bank routing info (e.g., "- 17.895.646/0001-87 - ADYEN ... Agência: 1 Conta: ...")
        s = re.sub(
            r'\s*-\s*(?:[0-9•*]{2,3}\.[0-9•*]{3}\.[0-9•*]{3}[/-][0-9•*]{2,4}(?:-[0-9•*]{2})?|\b\d{11,14}\b).*$',
            '',
            s,
            flags=re.IGNORECASE
        )

        # 2. Remove standalone CPF/CNPJ patterns anywhere in string
        s = re.sub(r'\b[0-9•*]{2,3}\.[0-9•*]{3}\.[0-9•*]{3}[/-][0-9•*]{2,4}(?:-[0-9•*]{2})?\b', '', s)
        s = re.sub(r'(?:•|\*){2,3}\.[0-9•*]{3}\.[0-9•*]{3}-[0-9•*]{2}', '', s)
        s = re.sub(r'\b(?:cpf|cnpj)\s*:?\s*[0-9•*./-]+', '', s, flags=re.IGNORECASE)

        # 3. Remove Agência, Conta, and COMPE bank codes like (0260)
        s = re.sub(r'\s*-?\s*\b(?:ag[êe]ncia|ag)\s*:?\s*[0-9a-zA-Z.-]+.*$', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\s*-?\s*\b(?:conta|cc)\s*:?\s*[0-9a-zA-Z.-]+.*$', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\(\d{3,4}\)', '', s)

        # 4. Strip verbose bank prefixes
        prefixes = [
            r'^transfer[êe]ncia\s+enviada\s+pelo\s+pix\s*-\s*',
            r'^transfer[êe]ncia\s+recebida\s+pelo\s+pix\s*-\s*',
            r'^transfer[êe]ncia\s+recebida\s*-\s*',
            r'^transfer[êe]ncia\s+enviada\s*-\s*',
            r'^pagamento\s+de\s+boleto\s+efetuado\s*-\s*',
            r'^pagamento\s+de\s+fatura\s*-\s*',
            r'^compra\s+no\s+d[ée]bito\s*(?:via\s+nubank\s*)?-\s*',
            r'^compra\s+no\s+cr[ée]dito\s*-\s*',
            r'^pix\s+enviado\s*-\s*',
            r'^pix\s+recebido\s*-\s*',
        ]
        for pat in prefixes:
            s = re.sub(pat, '', s, flags=re.IGNORECASE)

        # 5. Strip MEI 8-digit root CNPJ prefix before name (e.g. "52.331.137 IRINEIA KLABUNDE")
        s = re.sub(r'^\d{2}\.\d{3}\.\d{3}\s+', '', s)

        # 6. Clean truncated single-letter suffix after dash (e.g. "- UNIVEL L" -> "- UNIVEL") and corporate suffixes
        s = re.sub(r'\s+-\s+([A-Z0-9]+)\s+[A-Z]$', r' - \1', s)
        s = re.sub(r'\b(?:LTDA\.?|S\.?A\.?|S/A|EIRELI)\b\.?', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\s*-\s*$', '', s)
        s = re.sub(r'\s{2,}', ' ', s).strip(' -.,')

        return s or (raw_desc or 'Transação').strip()

    def categorize_transaction_by_keyword(text: str, txn_type: str = 'expense') -> str:
        cleaned_text = clean_transaction_description(text)
        t = (cleaned_text or '').lower()

        # 1. Educação
        if any(k in t for k in ['faculdade', 'universidade', 'univel', 'uniao educacional', 'união educacional',
                                'udemy', 'alura', 'livraria', 'livro', 'escola', 'colegio', 'colégio',
                                'estudo', 'mensalidade escolar', 'pos-graduacao', 'pós-graduação', 'idiomas']) or re.search(r'\b(?:curso|cursos)\b', t):
            return 'Educação'

        # 2. Saúde (verificar antes para termos como drogaria/drogasil/academia)
        if any(k in t for k in ['droga', 'farmacia', 'farmácia', 'drogaria', 'drogasil', 'pague menos',
                                'hospital', 'medico', 'médico', 'consulta', 'laboratorio', 'laboratório', 'exame', 'dentista',
                                'odonto', 'otica', 'ótica', 'clinica', 'clínica', 'panvel', 'ultrafarma', 'nissei',
                                'academia', 'smartfit', 'smart fit', 'psicologo', 'psicólogo', 'terapia', 'fisioterapia', 'unimed']) or re.search(r'\braia\b', t):
            return 'Saúde'

        # 3. Lazer
        if any(k in t for k in ['netflix', 'spotify', 'amazon prime', 'prime video', 'disney', 'cinema', 'cinemark',
                                'steam', 'playstation', 'xbox', 'nintendo', 'riot', 'google brasil pagamentos',
                                'google play', 'apple.com/bill', 'ebanx', 'ingresso', 'jogos',
                                'twitch', 'hbo', 'youtube', 'crunchyroll', 'lazer', 'parque', 'boliche', 'viagem', 'hotel', 'airbnb']) or re.search(r'\b(?:game|games|show)\b', t):
            return 'Lazer'

        # 4. Salário / Receita de Trabalho
        if any(k in t for k in ['salario', 'salário', 'folha de pagamento', 'rendimento', 'pro-labore',
                                'adiantamento salarial', 'remuneracao', 'remuneração', 'ted recebida', 'pix recebido']):
            return 'Salário'
        if txn_type == 'income' and 'novo sabor restaurante' in t:
            return 'Salário'

        # 5. Alimentação
        if any(k in t for k in ['ifood', 'ubereats', 'rappi', 'aiqfome', 'restaurante', 'burger', 'burgz', 'dogz',
                                'hamburgueria', 'mcdonald', 'burger king', 'lanche', 'padaria', 'panificadora', 'confeitaria',
                                'mercado', 'supermercado', 'muffato', 'festval', 'condor', 'irani', 'grupo irani',
                                'carrefour', 'pao de acucar', 'assai', 'atacadao', 'acougue', 'açougue', 'hortifruti',
                                'pizzaria', 'pizza', 'planeta pizza', 'cafe', 'café', 'starbucks', 'habib',
                                'churrascaria', 'sorvete', 'doceria', 'acai', 'açaí', 'pastel', 'marmita', 'refeicao', 'refeição']) or re.search(r'\b(?:bar|adega|food|grill|bistro|bistrô|sushi)\b', t):
            return 'Alimentação'

        # 6. Transporte
        if any(k in t for k in ['uber', '99app', '99*', '99pop', '99taxis', '99 tecnologia', '99pay',
                                'gasolina', 'combustivel', 'combustível', 'etanol', 'diesel', 'shell', 'ipiranga',
                                'br distribuidora', 'petrobras', 'estapar', 'pedagio', 'pedágio', 'sem parar', 'veloe',
                                'metro', 'metrô', 'onibus', 'ônibus', 'valesim', 'transporte', 'coletivo', 'passagem',
                                'auto posto', 'estacionamento', 'pareamento', 'oficina', 'mecanica', 'mecânica']) or re.search(r'\b(?:posto|99)\b', t):
            return 'Transporte'

        # 7. Moradia (usa boundaries para palavras curtas: gas, luz, agua, tim, oi)
        if any(k in t for k in ['aluguel', 'condominio', 'condomínio', 'enel', 'copel', 'sanepar', 'sabesp',
                                'comgas', 'comgás', 'ultragaz', 'liquigas', 'copasa', 'cpfl', 'internet', 'fibra',
                                'claro', 'vivo', 'iptu']) or re.search(r'\b(?:luz|energia|agua|água|gas|gás|tim|oi)\b', t):
            return 'Moradia'

        return 'Outros'

    def parse_bank_notification(text: str):
        cleaned = (text or '').strip()
        lower = cleaned.lower()

        # 1. Type: income vs expense
        is_income = any(w in lower for w in [
            'recebeu', 'recebida', 'recebido', 'depósito', 'deposito', 
            'reembolso', 'estorno', 'creditada', 'creditado', 'crédito recebido',
            'você recebeu'
        ])
        txn_type = 'income' if is_income else 'expense'

        # 2. Extract Value (R$)
        amount_cents = 0
        val_match = re.search(r'R\$\s*([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2}|[0-9]+(?:[.,][0-9]{2})?)', cleaned, re.IGNORECASE)
        if not val_match:
            val_match = re.search(r'(?:valor|total|de)\s+([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2}|[0-9]+(?:[.,][0-9]{2})?)', cleaned, re.IGNORECASE)

        if val_match:
            amt_float = parse_monetary_float(val_match.group(1))
            amount_cents = int(round(abs(amt_float) * 100))

        # 3. Extract Recipient / Description
        description = ''
        patterns = [
            r'(?:enviad[ao]\s+para|transferiu\s+para|pago\s+a|para)\s+([^,\.\n]+?)(?:\s+no\s+valor|\s+via|\.|$)',
            r'(?:aprovada\s+(?:no\s+cartão\s+)?em|compra\s+em|pagamento\s+em)\s+([^,\.\n]+?)(?:\s+no\s+valor|\s+de\s+R\$|\.|$)',
            r'(?:recebid[ao]\s+de|transferência\s+de\s+R\$.+?de)\s+([^,\.\n]+?)(?:\s+no\s+valor|\s+via|\.|$)',
            r'(?:de\s+R\$.+?\s+em\s+)([^,\.\n]+?)(?:\.|$)'
        ]
        for pat in patterns:
            m = re.search(pat, cleaned, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                candidate = re.sub(r'^(?:o\s+|a\s+|o\s+banco\s+)', '', candidate, flags=re.IGNORECASE).strip()
                if candidate and len(candidate) > 2:
                    description = candidate
                    break

        if not description:
            clean_desc = re.sub(r'R\$\s*[0-9\.,]+', '', cleaned)
            clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
            description = clean_desc[:80] if clean_desc else 'Notificação Bancária'

        description = clean_transaction_description(description)

        return {
            'amount_cents': amount_cents,
            'type': txn_type,
            'description': description
        }

    def parse_ofx_content(content: str):
        txns = []
        blocks = re.findall(r'<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|$)', content, re.DOTALL | re.IGNORECASE)
        for b in blocks:
            trntype_m = re.search(r'<TRNTYPE>([^\r\n<]+)', b, re.IGNORECASE)
            dtposted_m = re.search(r'<DTPOSTED>([0-9]{8})', b, re.IGNORECASE)
            trnamt_m = re.search(r'<TRNAMT>([^\r\n<]+)', b, re.IGNORECASE)
            fitid_m = re.search(r'<FITID>([^\r\n<]+)', b, re.IGNORECASE)
            memo_m = re.search(r'<MEMO>([^\r\n<]+)', b, re.IGNORECASE)
            name_m = re.search(r'<NAME>([^\r\n<]+)', b, re.IGNORECASE)

            if not trnamt_m:
                continue

            amt_float = parse_monetary_float(trnamt_m.group(1).strip())
            if amt_float == 0.0:
                continue

            txn_type = 'expense' if amt_float < 0 else 'income'
            if trntype_m:
                tt = trntype_m.group(1).strip().upper()
                if tt in ('CREDIT', 'DEP', 'DIRECTDEP'):
                    txn_type = 'income'
                elif tt in ('DEBIT', 'PAYMENT', 'CHECK', 'POS', 'ATM'):
                    txn_type = 'expense'

            amount_cents = int(round(abs(amt_float) * 100))
            txn_date = date.today().isoformat()
            if dtposted_m:
                ds = dtposted_m.group(1).strip()
                txn_date = f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}"

            fitid = fitid_m.group(1).strip() if fitid_m else None
            memo = memo_m.group(1).strip() if memo_m else ''
            name = name_m.group(1).strip() if name_m else ''
            raw_desc = (memo or name or 'Transação OFX').strip()
            desc = clean_transaction_description(raw_desc)

            txns.append({
                'date': txn_date,
                'amount_cents': amount_cents,
                'amount': round(amount_cents / 100.0, 2),
                'type': txn_type,
                'description': desc,
                'fitid': fitid
            })
        return txns

    def parse_csv_content(content: str):
        txns = []
        lines = content.strip().splitlines()
        if not lines:
            return txns
        first_line = lines[0]
        delim = ';' if ';' in first_line else ','
        reader = csv.DictReader(io.StringIO(content), delimiter=delim)
        for row in reader:
            norm = {k.strip().lower(): (v.strip() if v else '') for k, v in row.items() if k}
            date_val = None
            for dk in ['data', 'date', 'data lançamento', 'data lancamento']:
                if dk in norm and norm[dk]:
                    raw_d = norm[dk]
                    m_br = re.match(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})', raw_d)
                    if m_br:
                        date_val = f"{m_br.group(3)}-{int(m_br.group(2)):02d}-{int(m_br.group(1)):02d}"
                        break
                    m_iso = re.match(r'(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})', raw_d)
                    if m_iso:
                        date_val = f"{m_iso.group(1)}-{int(m_iso.group(2)):02d}-{int(m_iso.group(3)):02d}"
                        break
            if not date_val:
                date_val = date.today().isoformat()

            amt_float = 0.0
            for ak in ['valor', 'amount', 'valor (r$)', 'valor(r$)', 'valor líquido (r$)', 'valor liquido (r$)']:
                if ak in norm and norm[ak]:
                    amt_float = parse_monetary_float(norm[ak])
                    if amt_float != 0.0:
                        break

            desc_val = ''
            for rk in ['descrição', 'descricao', 'description', 'título', 'titulo', 'histórico', 'historico', 'estabelecimento', 'nome']:
                if rk in norm and norm[rk]:
                    desc_val = norm[rk]
                    break
            if not desc_val:
                desc_val = 'Transação CSV'
            desc_val = clean_transaction_description(desc_val)

            fitid_val = None
            for fk in ['identificador', 'id', 'fitid', 'external_id', 'codigo', 'código']:
                if fk in norm and norm[fk]:
                    fitid_val = norm[fk].strip()
                    break

            txn_type = 'expense' if amt_float < 0 else 'income'
            for tk in ['tipo', 'type']:
                if tk in norm and norm[tk]:
                    tv = norm[tk].lower()
                    if any(x in tv for x in ['receita', 'crédito', 'credito', 'entrada']):
                        txn_type = 'income'
                    elif any(x in tv for x in ['despesa', 'débito', 'debito', 'saída']):
                        txn_type = 'expense'

            amount_cents = int(round(abs(amt_float) * 100))
            if amount_cents <= 0:
                continue

            txns.append({
                'date': date_val,
                'amount_cents': amount_cents,
                'amount': round(amount_cents / 100.0, 2),
                'type': txn_type,
                'description': desc_val,
                'fitid': fitid_val
            })
        return txns

    @app.route('/api/finances/webhook/notification', methods=['POST'])
    @app.route('/api/finance/webhook/notification', methods=['POST'])
    def finance_notification_webhook():
        conn = get_db()
        data = request.get_json(silent=True) or {}
        bank = (data.get('banco') or data.get('bank') or 'Nubank').strip()
        text = (data.get('texto') or data.get('text') or data.get('message') or data.get('body') or '').strip()

        if not text:
            return jsonify({'status': 'error', 'error': 'Texto da notificação é obrigatório'}), 400

        parsed = parse_bank_notification(text)
        amount_cents = parsed['amount_cents']
        if amount_cents <= 0:
            return jsonify({'status': 'error', 'error': 'Não foi possível extrair um valor financeiro válido da notificação'}), 422

        amount_decimal = round(amount_cents / 100.0, 2)
        txn_type = parsed['type']
        description = parsed['description']
        category = categorize_transaction_by_keyword(description, txn_type)
        category_id = resolve_category_id(conn, category)

        ts_val = data.get('timestamp') or data.get('time')
        if ts_val:
            try:
                if isinstance(ts_val, (int, float)) or (isinstance(ts_val, str) and ts_val.isdigit()):
                    ts_num = float(ts_val)
                    if ts_num > 1e11:
                        ts_num /= 1000.0
                    txn_date = datetime.fromtimestamp(ts_num).strftime('%Y-%m-%d')
                else:
                    txn_date = str(ts_val)[:10]
            except Exception:
                txn_date = date.today().isoformat()
        else:
            txn_date = date.today().isoformat()

        now = datetime.now().isoformat()
        cur = conn.execute("""
            INSERT INTO transactions (
                description, amount_cents, amount, type, category, category_id,
                account, date, transaction_date, is_settled, is_recurring, recurrence,
                source, external_id, reconciled, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, 'nenhuma', 'webhook', NULL, 0, ?)
        """, (
            description, amount_cents, amount_decimal, txn_type, category, category_id,
            bank, txn_date, txn_date, now
        ))
        conn.commit()
        new_id = cur.lastrowid
        txn = conn.execute("SELECT * FROM transactions WHERE id = ?", (new_id,)).fetchone()
        return jsonify({
            'status': 'success',
            'success': True,
            'transaction': dict_from_row(txn)
        }), 201

    @app.route('/api/finances/import', methods=['POST'])
    @app.route('/api/finance/import', methods=['POST'])
    def finance_import_statement():
        conn = get_db()
        account_name = (request.form.get('account') or request.args.get('account') or 'Nubank').strip()

        content = ''
        filename = ''
        if 'file' in request.files:
            uploaded_file = request.files['file']
            filename = uploaded_file.filename or ''
            try:
                content = uploaded_file.read().decode('utf-8', errors='replace')
            except Exception as e:
                return jsonify({'status': 'error', 'error': f'Falha ao ler arquivo: {str(e)}'}), 400
        else:
            json_data = request.get_json(silent=True) or {}
            content = json_data.get('content') or request.get_data(as_text=True)
            filename = json_data.get('filename') or ''
            if json_data.get('account'):
                account_name = json_data['account'].strip()

        if not content:
            return jsonify({'status': 'error', 'error': 'Nenhum conteúdo OFX ou CSV enviado para importação'}), 400

        is_ofx = '<OFX>' in content.upper() or '<STMTTRN>' in content.upper() or filename.lower().endswith('.ofx')
        if is_ofx:
            parsed_txns = parse_ofx_content(content)
        else:
            parsed_txns = parse_csv_content(content)

        if not parsed_txns:
            return jsonify({'status': 'error', 'error': 'Nenhuma transação válida identificada no extrato'}), 422

        imported_count = 0
        reconciled_duplicates = 0
        imported_list = []

        for t in parsed_txns:
            # 3.3 Deduplication: exact external_id match OR 24h tolerance (+/- 1 day) with same type and amount_cents
            try:
                t_date_obj = datetime.strptime(t['date'][:10], '%Y-%m-%d').date()
            except ValueError:
                t_date_obj = date.today()
            d_minus = (t_date_obj - timedelta(days=1)).isoformat()
            d_cur = t_date_obj.isoformat()
            d_plus = (t_date_obj + timedelta(days=1)).isoformat()

            existing = None
            if t.get('fitid'):
                existing = conn.execute("""
                    SELECT id, description, source, external_id, reconciled FROM transactions
                    WHERE external_id = ? LIMIT 1
                """, (t['fitid'],)).fetchone()

            if not existing:
                existing = conn.execute("""
                    SELECT id, description, source, external_id, reconciled FROM transactions
                    WHERE type = ? AND amount_cents = ? AND date IN (?, ?, ?)
                    ORDER BY CASE WHEN source = 'webhook' THEN 0 ELSE 1 END, id ASC
                    LIMIT 1
                """, (t['type'], t['amount_cents'], d_minus, d_cur, d_plus)).fetchone()

            if existing:
                reconciled_duplicates += 1
                if t.get('fitid') and not existing['external_id']:
                    conn.execute("UPDATE transactions SET external_id = ?, reconciled = 1 WHERE id = ?", (t['fitid'], existing['id']))
                else:
                    conn.execute("UPDATE transactions SET reconciled = 1 WHERE id = ?", (existing['id'],))
            else:
                cat = categorize_transaction_by_keyword(t['description'], t['type'])
                cat_id = resolve_category_id(conn, cat)
                now = datetime.now().isoformat()
                cur = conn.execute("""
                    INSERT INTO transactions (
                        description, amount_cents, amount, type, category, category_id,
                        account, date, transaction_date, is_settled, is_recurring, recurrence,
                        source, external_id, reconciled, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, 'nenhuma', ?, ?, 0, ?)
                """, (
                    t['description'], t['amount_cents'], t['amount'], t['type'], cat, cat_id,
                    account_name, d_cur, d_cur, 'ofx' if is_ofx else 'csv', t.get('fitid'), now
                ))
                imported_count += 1
                new_id = cur.lastrowid
                imported_list.append(new_id)

        conn.commit()
        return jsonify({
            'status': 'success',
            'success': True,
            'format': 'ofx' if is_ofx else 'csv',
            'total_processed': len(parsed_txns),
            'imported': imported_count,
            'reconciled_duplicates': reconciled_duplicates,
            'account': account_name
        }), 200

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

            try:
                note_type, content = validate_and_normalize_note_content(
                    data.get('note_type', 'text'),
                    data.get('content', '')
                )
            except ValueError as ve:
                return jsonify({'status': 'error', 'error': str(ve)}), 400

            if note_type == 'text':
                content = content.strip()
            stage, status = normalize_idea_stage_and_status(data.get('stage'), data.get('status'))
            tags = (data.get('tags') or '').strip()
            now = datetime.now().isoformat()

            cur = conn.execute("""
                INSERT INTO ideas (title, content, note_type, stage, status, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, content, note_type, stage, status, tags, now, now))
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
        raw_note_type = data.get('note_type', current.get('note_type', 'text'))
        raw_content = data.get('content', current['content'])
        try:
            note_type, content = validate_and_normalize_note_content(raw_note_type, raw_content)
        except ValueError as ve:
            return jsonify({'status': 'error', 'error': str(ve)}), 400

        if note_type == 'text' and isinstance(content, str):
            content = content.strip()

        if 'stage' in data or 'status' in data:
            stage, status = normalize_idea_stage_and_status(data.get('stage'), data.get('status'))
        else:
            stage, status = current['stage'], current.get('status', 'bruta')
        tags = data.get('tags', current['tags'])

        conn.execute("""
            UPDATE ideas
            SET title = ?, content = ?, note_type = ?, stage = ?, status = ?, tags = ?, updated_at = ?
            WHERE id = ?
        """, (title, content, note_type, stage, status, tags, now, idea_id))
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

        idea_dict = dict_from_row(idea)
        task_desc = idea_dict.get('content') or ''
        if idea_dict.get('note_type') == 'checklist' and task_desc:
            try:
                items = json.loads(task_desc)
                if isinstance(items, list):
                    task_desc = '\n'.join([f"[{'x' if it.get('done') else ' '}] {it.get('text', '')}" for it in items if isinstance(it, dict)])
            except Exception:
                pass

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
                task_desc,
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
        month = (request.args.get('month') or '').strip()
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        tasks_list = [dict_from_row(r) for r in conn.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()]
        
        # Finance query with optional month filtering (for precise audit matching screen state)
        if month and month.lower() != 'all':
            txns_query = """
                SELECT tr.*, t.title as task_title, g.title as goal_title
                FROM transactions tr
                LEFT JOIN tasks t ON tr.task_id = t.id
                LEFT JOIN goals g ON tr.goal_id = g.id
                WHERE tr.date LIKE ?
                ORDER BY tr.date DESC, tr.id DESC
            """
            txns_list = [dict_from_row(r) for r in conn.execute(txns_query, (f"{month}%",)).fetchall()]
        else:
            txns_query = """
                SELECT tr.*, t.title as task_title, g.title as goal_title
                FROM transactions tr
                LEFT JOIN tasks t ON tr.task_id = t.id
                LEFT JOIN goals g ON tr.goal_id = g.id
                ORDER BY tr.date DESC, tr.id DESC
            """
            txns_list = [dict_from_row(r) for r in conn.execute(txns_query).fetchall()]

        ideas_list = [dict_from_row(r) for r in conn.execute("SELECT * FROM ideas ORDER BY id DESC").fetchall()]
        goals_list = [enrich_goal(r) for r in conn.execute("SELECT * FROM goals ORDER BY id DESC").fetchall()]
        notes_list = [dict_from_row(r) for r in conn.execute("SELECT * FROM notes ORDER BY id DESC").fetchall()]

        if fmt == 'csv':
            output = io.StringIO()
            output.write('\ufeff')
            writer = csv.writer(output, delimiter=';')

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
                writer.writerow([
                    'ID', 'Data', 'Tipo', 'Descrição', 'Valor Original (R$)',
                    'Valor Líquido (R$)', 'Categoria', 'Conta', 'Origem',
                    'Conciliado', 'ID Externo (FITID)', 'Recorrente', 'Frequência',
                    'Tarefa Vinculada', 'Meta Vinculada'
                ])
                total_income = 0
                total_expense = 0

                for tr in txns_list:
                    cents = tr['amount_cents'] or 0
                    val_float = cents / 100.0
                    val_orig_brl = f"{val_float:.2f}".replace('.', ',')

                    if tr['type'] == 'income':
                        total_income += cents
                        val_net_brl = f"{val_float:.2f}".replace('.', ',')
                        tipo_label = 'Receita'
                    else:
                        total_expense += cents
                        val_net_brl = f"{-val_float:.2f}".replace('.', ',')
                        tipo_label = 'Despesa'

                    src = tr.get('source') or 'manual'
                    if src == 'webhook':
                        origem_label = 'Notificação (Webhook)'
                    elif src == 'ofx':
                        origem_label = 'Extrato OFX'
                    elif src == 'csv':
                        origem_label = 'Extrato CSV'
                    else:
                        origem_label = 'Manual'

                    writer.writerow([
                        tr['id'],
                        tr['date'],
                        tipo_label,
                        tr['description'],
                        val_orig_brl,
                        val_net_brl,
                        tr['category'] or 'Outros',
                        tr['account'] or 'Conta Corrente',
                        origem_label,
                        'Sim' if tr.get('reconciled') else 'Não',
                        tr.get('external_id') or '',
                        'Sim' if tr.get('is_recurring') else 'Não',
                        tr.get('recurrence') or 'nenhuma',
                        tr.get('task_title') or '',
                        tr.get('goal_title') or ''
                    ])

                # Linhas de conferência e auditoria de totais
                net_cents = total_income - total_expense
                tot_inc_brl = f"{(total_income / 100.0):.2f}".replace('.', ',')
                tot_exp_brl = f"{(total_expense / 100.0):.2f}".replace('.', ',')
                net_brl = f"{(net_cents / 100.0):.2f}".replace('.', ',')
                period_label = f"Mês {month}" if (month and month.lower() != 'all') else "Todo o Histórico"

                writer.writerow([])
                writer.writerow(['---', '---', '---', 'RESUMO DE AUDITORIA', '---', '---', '---', '---', '---', '---', '---', '---', '---', '---', '---'])
                writer.writerow(['', '', 'TOTAL RECEITAS (+)', '', '', tot_inc_brl, '', '', '', '', '', '', '', '', ''])
                writer.writerow(['', '', 'TOTAL DESPESAS (-)', '', '', f"-{tot_exp_brl}", '', '', '', '', '', '', '', '', ''])
                writer.writerow(['', '', 'SALDO LÍQUIDO', '', '', net_brl, '', '', '', '', '', '', '', '', ''])
                writer.writerow(['', '', 'PERÍODO', period_label, '', f"{len(txns_list)} lançamentos", '', '', '', '', '', '', '', '', ''])

                if month and month.lower() != 'all':
                    filename = f'dreamhub_financas_{month}_{stamp}.csv'
                else:
                    filename = f'dreamhub_financas_completo_{stamp}.csv'

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

    # ------------------- RITMO MODULE API ENDPOINTS -------------------
    @app.route('/api/exercises', methods=['GET', 'POST'])
    def handle_exercises():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            name = (data.get('name') or '').strip()
            if not name:
                return jsonify({'status': 'error', 'error': 'Nome do exercício é obrigatório'}), 400
            muscle = (data.get('muscle_group') or data.get('muscle') or 'outro').strip().lower()
            equipment = (data.get('equipment') or '').strip()
            notes = (data.get('notes') or '').strip()
            now = datetime.now().isoformat()
            try:
                cur = conn.execute("""
                    INSERT INTO exercises (name, muscle_group, equipment, notes, custom, created_at)
                    VALUES (?, ?, ?, ?, 1, ?)
                """, (name, muscle, equipment, notes, now))
                conn.commit()
                row = conn.execute("SELECT * FROM exercises WHERE id = ?", (cur.lastrowid,)).fetchone()
                return jsonify(dict_from_row(row)), 201
            except sqlite3.IntegrityError:
                return jsonify({'status': 'error', 'error': 'Exercício já cadastrado com este nome'}), 400

        muscle = request.args.get('muscle', '').strip().lower()
        if muscle:
            rows = conn.execute("SELECT * FROM exercises WHERE muscle_group = ? ORDER BY name ASC", (muscle,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM exercises ORDER BY muscle_group ASC, name ASC").fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/exercises/<int:ex_id>', methods=['GET', 'PUT', 'DELETE'])
    def exercise_detail(ex_id):
        conn = get_db()
        ex = conn.execute("SELECT * FROM exercises WHERE id = ?", (ex_id,)).fetchone()
        if not ex:
            return jsonify({'status': 'error', 'error': 'Exercício não encontrado'}), 404

        if request.method == 'GET':
            return jsonify(dict_from_row(ex))

        if request.method == 'DELETE':
            if not ex['custom']:
                return jsonify({'status': 'error', 'error': 'Exercícios padrão do catálogo não podem ser removidos'}), 400
            in_use = conn.execute("SELECT COUNT(*) FROM routine_items WHERE exercise_id = ?", (ex_id,)).fetchone()[0]
            if in_use > 0:
                return jsonify({'status': 'error', 'error': 'Remova o exercício de todas as rotinas antes de excluir'}), 400
            conn.execute("UPDATE workout_items SET exercise_id = NULL WHERE exercise_id = ?", (ex_id,))
            conn.execute("DELETE FROM exercises WHERE id = ?", (ex_id,))
            conn.commit()
            return jsonify({'status': 'success', 'success': True, 'deleted_id': ex_id})

        data = request.get_json() or {}
        name = (data.get('name') or ex['name']).strip()
        muscle = (data.get('muscle_group') or data.get('muscle') or ex['muscle_group']).strip().lower()
        equipment = (data.get('equipment') if 'equipment' in data else ex['equipment']) or ''
        notes = (data.get('notes') if 'notes' in data else ex['notes']) or ''
        conn.execute("""
            UPDATE exercises SET name = ?, muscle_group = ?, equipment = ?, notes = ? WHERE id = ?
        """, (name, muscle, equipment, notes, ex_id))
        conn.commit()
        updated = conn.execute("SELECT * FROM exercises WHERE id = ?", (ex_id,)).fetchone()
        return jsonify(dict_from_row(updated))

    def _build_routine_dict(conn, r_row):
        d = dict_from_row(r_row)
        items_rows = conn.execute("""
            SELECT ri.*, e.name as exercise_name, e.muscle_group as exercise_muscle
            FROM routine_items ri
            LEFT JOIN exercises e ON e.id = ri.exercise_id
            WHERE ri.routine_id = ?
            ORDER BY ri.position ASC, ri.id ASC
        """, (r_row['id'],)).fetchall()
        d['items'] = [{
            'id': i['id'],
            'exercise_id': i['exercise_id'],
            'name': i['exercise_name'] or 'Exercício',
            'muscle_group': i['exercise_muscle'] or 'outro',
            'sets': i['sets'],
            'reps': i['reps'],
            'rest': i['rest'],
            'target_reps': i['target_reps'] or f"{i['reps']}"
        } for i in items_rows]
        return d

    @app.route('/api/routines', methods=['GET', 'POST'])
    def handle_routines():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            name = (data.get('name') or '').strip()
            if not name:
                return jsonify({'status': 'error', 'error': 'Nome da rotina é obrigatório'}), 400
            target_muscles = (data.get('target_muscle_groups') or '').strip()
            day_of_week = data.get('day_of_week')
            items = data.get('items') or []
            now = datetime.now().isoformat()

            cur = conn.execute("""
                INSERT INTO routines (name, target_muscle_groups, day_of_week, created_at)
                VALUES (?, ?, ?, ?)
            """, (name, target_muscles, day_of_week, now))
            r_id = cur.lastrowid

            for pos, it in enumerate(items):
                ex_id = int(it.get('exercise_id'))
                sets = int(it.get('sets') or 3)
                reps = int(it.get('reps') or 10)
                rest = int(it.get('rest') or 90)
                target_reps = str(it.get('target_reps') or f"{reps}")
                conn.execute("""
                    INSERT INTO routine_items (routine_id, exercise_id, position, sets, reps, rest, target_reps)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (r_id, ex_id, pos, sets, reps, rest, target_reps))

            conn.commit()
            new_r = conn.execute("SELECT * FROM routines WHERE id = ?", (r_id,)).fetchone()
            return jsonify(_build_routine_dict(conn, new_r)), 201

        rows = conn.execute("SELECT * FROM routines ORDER BY id ASC").fetchall()
        return jsonify([_build_routine_dict(conn, r) for r in rows])

    @app.route('/api/routines/<int:r_id>', methods=['GET', 'PUT', 'DELETE'])
    def routine_detail(r_id):
        conn = get_db()
        r = conn.execute("SELECT * FROM routines WHERE id = ?", (r_id,)).fetchone()
        if not r:
            return jsonify({'status': 'error', 'error': 'Rotina não encontrada'}), 404

        if request.method == 'GET':
            return jsonify(_build_routine_dict(conn, r))

        if request.method == 'DELETE':
            conn.execute("DELETE FROM routines WHERE id = ?", (r_id,))
            conn.commit()
            return jsonify({'status': 'success', 'success': True, 'deleted_id': r_id})

        data = request.get_json() or {}
        name = (data.get('name') or r['name']).strip()
        target_muscles = data.get('target_muscle_groups', r['target_muscle_groups'])
        day_of_week = data.get('day_of_week', r['day_of_week'])

        conn.execute("""
            UPDATE routines SET name = ?, target_muscle_groups = ?, day_of_week = ? WHERE id = ?
        """, (name, target_muscles, day_of_week, r_id))

        if 'items' in data:
            conn.execute("DELETE FROM routine_items WHERE routine_id = ?", (r_id,))
            for pos, it in enumerate(data['items']):
                ex_id = int(it.get('exercise_id'))
                sets = int(it.get('sets') or 3)
                reps = int(it.get('reps') or 10)
                rest = int(it.get('rest') or 90)
                target_reps = str(it.get('target_reps') or f"{reps}")
                conn.execute("""
                    INSERT INTO routine_items (routine_id, exercise_id, position, sets, reps, rest, target_reps)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (r_id, ex_id, pos, sets, reps, rest, target_reps))

        conn.commit()
        updated = conn.execute("SELECT * FROM routines WHERE id = ?", (r_id,)).fetchone()
        return jsonify(_build_routine_dict(conn, updated))

    def _build_workout_dict(conn, w_row):
        d = dict_from_row(w_row)
        items = conn.execute("""
            SELECT * FROM workout_items WHERE workout_id = ? ORDER BY position ASC, id ASC
        """, (w_row['id'],)).fetchall()
        items_list = []
        for it in items:
            it_dict = dict_from_row(it)
            sets = conn.execute("""
                SELECT * FROM workout_sets WHERE item_id = ? ORDER BY position ASC, id ASC
            """, (it['id'],)).fetchall()
            it_dict['sets'] = [{
                'id': s['id'],
                'position': s['position'],
                'reps': s['reps'],
                'load': float(s['load'] or 0),
                'done': bool(s['done']),
                'rpe': float(s['rpe']) if s['rpe'] is not None else None
            } for s in sets]
            items_list.append(it_dict)
        d['items'] = items_list
        return d

    @app.route('/api/workouts', methods=['GET', 'POST'])
    def handle_workouts():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            r_id = data.get('routine_id')
            if not r_id:
                return jsonify({'status': 'error', 'error': 'Rotina é obrigatória para iniciar o treino'}), 400

            r = conn.execute("SELECT * FROM routines WHERE id = ?", (r_id,)).fetchone()
            if not r:
                return jsonify({'status': 'error', 'error': 'Rotina não encontrada'}), 404

            status_opt = data.get('status', 'em_andamento')
            now_dt = datetime.now()
            now_iso = now_dt.isoformat()
            today_str = (data.get('session_date') or now_dt.strftime('%Y-%m-%d'))[:10]

            if status_opt == 'pendente':
                cur_sc = conn.execute("""
                    INSERT INTO schedules (routine_id, routine_name, scheduled_at)
                    VALUES (?, ?, ?)
                """, (r['id'], r['name'], today_str))
                conn.commit()
                sc_row = conn.execute("SELECT * FROM schedules WHERE id = ?", (cur_sc.lastrowid,)).fetchone()
                return jsonify({'status': 'scheduled', 'scheduled': True, 'schedule': dict_from_row(sc_row)}), 201

            if status_opt not in ('concluido', 'stop'):
                # em_andamento requires no active workout
                active_w = conn.execute("SELECT id FROM workouts WHERE finished_at IS NULL").fetchone()
                if active_w:
                    return jsonify({'status': 'error', 'error': 'Já existe um treino em andamento. Finalize ou descarte-o.'}), 400

            if status_opt in ('stop', 'stopped'):
                status_opt = 'stopped'
            finished_at_val = now_iso if status_opt in ('concluido', 'stopped') else None
            w_status = 'stopped' if status_opt == 'stopped' else 'concluido'
            cur = conn.execute("""
                INSERT INTO workouts (routine_id, routine_name, started_at, finished_at, session_date, notes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (r['id'], r['name'], now_iso, finished_at_val, today_str, data.get('notes', ''), w_status))
            w_id = cur.lastrowid

            r_items = conn.execute("""
                SELECT ri.*, e.name as ex_name
                FROM routine_items ri
                LEFT JOIN exercises e ON e.id = ri.exercise_id
                WHERE ri.routine_id = ?
                ORDER BY ri.position ASC
            """, (r['id'],)).fetchall()

            for pos, ri in enumerate(r_items):
                ex_name = ri['ex_name'] or 'Exercício'
                cur_it = conn.execute("""
                    INSERT INTO workout_items (workout_id, exercise_id, name, position, rest, notes)
                    VALUES (?, ?, ?, ?, ?, '')
                """, (w_id, ri['exercise_id'], ex_name, pos, ri['rest'] or 90))
                it_id = cur_it.lastrowid

                # Ergonomic auto-fill from previous session
                last_load = 0.0
                last_reps = ri['reps'] or 10
                if ri['exercise_id']:
                    prev_set = conn.execute("""
                        SELECT ws.load, ws.reps
                        FROM workout_sets ws
                        JOIN workout_items wi ON wi.id = ws.item_id
                        JOIN workouts w ON w.id = wi.workout_id
                        WHERE wi.exercise_id = ? AND w.finished_at IS NOT NULL AND ws.done = 1
                        ORDER BY w.started_at DESC, ws.position DESC
                        LIMIT 1
                    """, (ri['exercise_id'],)).fetchone()
                    if prev_set:
                        last_load = float(prev_set['load'] or 0.0)
                        last_reps = int(prev_set['reps'] or last_reps)

                num_sets = max(1, ri['sets'] or 3)
                done_val = 1 if status_opt == 'concluido' else 0
                for s_pos in range(num_sets):
                    conn.execute("""
                        INSERT INTO workout_sets (item_id, position, reps, load, done)
                        VALUES (?, ?, ?, ?, ?)
                    """, (it_id, s_pos, last_reps, last_load, done_val))

            conn.commit()
            new_w = conn.execute("SELECT * FROM workouts WHERE id = ?", (w_id,)).fetchone()
            return jsonify(_build_workout_dict(conn, new_w)), 201

        # GET workouts list
        month = request.args.get('month', '')
        if month:
            rows = conn.execute("""
                SELECT * FROM workouts
                WHERE finished_at IS NOT NULL AND session_date LIKE ?
                ORDER BY started_at DESC
            """, (f"{month}%",)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM workouts
                WHERE finished_at IS NOT NULL
                ORDER BY started_at DESC
                LIMIT 50
            """).fetchall()
        return jsonify([_build_workout_dict(conn, w) for w in rows])

    @app.route('/api/workouts/active', methods=['GET'])
    def active_workout():
        conn = get_db()
        w = conn.execute("""
            SELECT * FROM workouts WHERE finished_at IS NULL ORDER BY id DESC LIMIT 1
        """).fetchone()
        if not w:
            return jsonify(None)
        return jsonify(_build_workout_dict(conn, w))

    @app.route('/api/workouts/<int:w_id>', methods=['GET', 'PUT', 'DELETE'])
    def workout_detail(w_id):
        conn = get_db()
        w = conn.execute("SELECT * FROM workouts WHERE id = ?", (w_id,)).fetchone()
        if not w:
            return jsonify({'status': 'error', 'error': 'Treino não encontrado'}), 404

        if request.method == 'GET':
            return jsonify(_build_workout_dict(conn, w))

        if request.method == 'DELETE':
            conn.execute("DELETE FROM workouts WHERE id = ?", (w_id,))
            conn.commit()
            return jsonify({'status': 'success', 'success': True, 'deleted_id': w_id})

        # PUT: Update sets/notes or Finish workout
        data = request.get_json() or {}
        notes_val = data.get('notes', w['notes'] or '')
        finish = data.get('finish', False)

        conn.execute("UPDATE workouts SET notes = ? WHERE id = ?", (notes_val, w_id))

        items_data = data.get('items', [])
        for it in items_data:
            it_id = it.get('id')
            if not it_id:
                continue
            conn.execute("UPDATE workout_items SET notes = ? WHERE id = ? AND workout_id = ?",
                         (it.get('notes', ''), it_id, w_id))
            for s in it.get('sets', []):
                s_id = s.get('id')
                if not s_id:
                    continue
                reps = int(s.get('reps') or 0)
                load = float(s.get('load') or 0.0)
                done = 1 if s.get('done') else 0
                rpe = float(s['rpe']) if s.get('rpe') is not None and str(s.get('rpe')).strip() else None
                conn.execute("""
                    UPDATE workout_sets
                    SET reps = ?, load = ?, done = ?, rpe = ?
                    WHERE id = ? AND item_id = ?
                """, (reps, load, done, rpe, s_id, it_id))

        if finish or data.get('stop') or data.get('action') == 'finish' or data.get('action') == 'stop':
            now_finish = datetime.now().isoformat()
            w_status = 'stopped' if (data.get('stop') or data.get('action') == 'stop') else 'concluido'
            conn.execute("UPDATE workouts SET finished_at = ?, status = ? WHERE id = ?", (now_finish, w_status, w_id))
        elif data.get('status') in ('concluido', 'stop', 'stopped') and w['finished_at']:
            w_status = 'stopped' if data.get('status') in ('stop', 'stopped') else 'concluido'
            conn.execute("UPDATE workouts SET status = ? WHERE id = ?", (w_status, w_id))

        conn.commit()
        updated_w = conn.execute("SELECT * FROM workouts WHERE id = ?", (w_id,)).fetchone()
        return jsonify(_build_workout_dict(conn, updated_w))

    @app.route('/api/workout_items/<int:item_id>/sets', methods=['POST'])
    def add_adhoc_workout_set(item_id):
        """
        Adiciona uma série dinâmica (ad-hoc) APENAS na tabela workout_sets da sessão ativa.
        REGRA DE NEGÓCIO CRÍTICA: NUNCA altera a tabela routine_items (planeamento da rotina).
        """
        conn = get_db()
        item = conn.execute("SELECT * FROM workout_items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            return jsonify({'status': 'error', 'error': 'Exercício da sessão não encontrado'}), 404

        data = request.get_json(silent=True) or {}
        last_set = conn.execute("""
            SELECT position, reps, load FROM workout_sets
            WHERE item_id = ?
            ORDER BY position DESC, id DESC
            LIMIT 1
        """, (item_id,)).fetchone()

        next_pos = (last_set['position'] + 1) if last_set and last_set['position'] is not None else 0
        default_reps = int(data['reps']) if 'reps' in data and data['reps'] is not None else (int(last_set['reps'] or 10) if last_set else 10)
        default_load = float(data['load']) if 'load' in data and data['load'] is not None else (float(last_set['load'] or 0.0) if last_set else 0.0)
        done_val = 1 if data.get('done') else 0

        cur = conn.execute("""
            INSERT INTO workout_sets (item_id, position, reps, load, done)
            VALUES (?, ?, ?, ?, ?)
        """, (item_id, next_pos, default_reps, default_load, done_val))
        conn.commit()

        new_set = conn.execute("SELECT * FROM workout_sets WHERE id = ?", (cur.lastrowid,)).fetchone()
        w_row = conn.execute("SELECT * FROM workouts WHERE id = ?", (item['workout_id'],)).fetchone()
        return jsonify({
            'status': 'success',
            'set': {
                'id': new_set['id'],
                'item_id': new_set['item_id'],
                'position': new_set['position'],
                'reps': new_set['reps'],
                'load': float(new_set['load'] or 0.0),
                'done': bool(new_set['done'])
            },
            'workout': _build_workout_dict(conn, w_row) if w_row else None
        }), 201

    @app.route('/api/workout_items/<int:item_id>', methods=['PATCH', 'PUT'])
    def update_workout_item_notes(item_id):
        """
        Salva o comentário (notes) do exercício na tabela de histórico da sessão (workout_items).
        """
        conn = get_db()
        item = conn.execute("SELECT * FROM workout_items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            return jsonify({'status': 'error', 'error': 'Exercício da sessão não encontrado'}), 404

        data = request.get_json(silent=True) or {}
        notes_val = (data.get('notes') if 'notes' in data else item['notes']) or ''
        conn.execute("UPDATE workout_items SET notes = ? WHERE id = ?", (notes_val, item_id))
        conn.commit()

        updated_item = conn.execute("SELECT * FROM workout_items WHERE id = ?", (item_id,)).fetchone()
        return jsonify(dict_from_row(updated_item))

    # Weight and Body Metrics
    @app.route('/api/metrics/weight', methods=['GET', 'POST'])
    def handle_weight_metrics():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            try:
                w = float(data.get('weight'))
                if not (20 <= w <= 500):
                    raise ValueError()
            except (ValueError, TypeError):
                return jsonify({'status': 'error', 'error': 'Informe um peso válido entre 20 e 500 kg'}), 400

            rec_date = (data.get('recorded_at') or date.today().isoformat())[:10]
            notes = (data.get('notes') or '').strip()
            now = datetime.now().isoformat()

            conn.execute("""
                INSERT INTO body_metrics (weight, notes, recorded_at, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(recorded_at) DO UPDATE SET weight = excluded.weight, notes = excluded.notes
            """, (w, notes, rec_date, now))
            conn.commit()

            row = conn.execute("SELECT * FROM body_metrics WHERE recorded_at = ?", (rec_date,)).fetchone()
            return jsonify(dict_from_row(row)), 201

        # GET metrics with deltas
        rows = conn.execute("SELECT * FROM body_metrics ORDER BY recorded_at ASC").fetchall()
        result = []
        prev_w = None
        for r in rows:
            w_val = float(r['weight'])
            delta = round(w_val - prev_w, 2) if prev_w is not None else 0.0
            result.append({
                'id': r['id'],
                'weight': w_val,
                'delta': delta,
                'notes': r['notes'] or '',
                'recorded_at': r['recorded_at']
            })
            prev_w = w_val
        return jsonify(list(reversed(result)))

    @app.route('/api/metrics/weight/<int:m_id>', methods=['DELETE'])
    def delete_weight_metric(m_id):
        conn = get_db()
        conn.execute("DELETE FROM body_metrics WHERE id = ?", (m_id,))
        conn.commit()
        return jsonify({'status': 'success', 'success': True, 'deleted_id': m_id})

    # Evolution Photos (Ritmo - Peso & Evolução)
    @app.route('/api/metrics/photos', methods=['GET', 'POST'])
    def handle_evolution_photos():
        conn = get_db()
        if request.method == 'POST':
            file_storage = request.files.get('file')
            angle = 'frontal'
            taken_at = date.today().isoformat()
            metric_id = None
            physical_path = None
            unique_name = None

            if file_storage and file_storage.filename:
                angle = (request.form.get('angle') or 'frontal').strip()
                taken_at = (request.form.get('taken_at') or date.today().isoformat())[:10]
                metric_id = request.form.get('metric_id')
                if metric_id:
                    try:
                        metric_id = int(metric_id)
                    except ValueError:
                        metric_id = None

                orig_name = secure_filename(file_storage.filename) or 'foto.jpg'
                mime = (file_storage.mimetype or '').lower()
                if mime and not mime.startswith('image/') and mime != 'application/octet-stream':
                    return jsonify({'status': 'error', 'error': 'Arquivo enviado não é uma imagem'}), 400
                mime_ext = {'image/webp': '.webp', 'image/jpeg': '.jpg', 'image/png': '.png',
                            'image/heic': '.heic', 'image/heif': '.heif', 'image/gif': '.gif'}
                ext = os.path.splitext(orig_name)[1].lower()[:16]
                if ext not in ('.webp', '.jpg', '.jpeg', '.png', '.heic', '.heif', '.gif'):
                    ext = mime_ext.get(mime, '.jpg')
                unique_name = f"evo_{uuid.uuid4().hex}{ext}"
                physical_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
                file_storage.save(physical_path)
            elif request.is_json:
                data = request.get_json() or {}
                file_b64 = data.get('file_content') or ''
                if not file_b64:
                    return jsonify({'status': 'error', 'error': 'Nenhuma foto enviada'}), 400
                if ',' in file_b64:
                    file_b64 = file_b64.split(',', 1)[1]
                import base64
                raw_bytes = base64.b64decode(file_b64)
                angle = (data.get('angle') or 'frontal').strip()
                taken_at = (data.get('photo_date') or data.get('taken_at') or date.today().isoformat())[:10]
                metric_id = int(data['metric_id']) if data.get('metric_id') else None
                unique_name = f"evo_{uuid.uuid4().hex}.jpg"
                physical_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
                with open(physical_path, 'wb') as f:
                    f.write(raw_bytes)
            else:
                return jsonify({'status': 'error', 'error': 'Nenhuma foto enviada'}), 400

            file_size = os.path.getsize(physical_path)
            if file_size > MAX_UPLOAD_BYTES:
                if os.path.exists(physical_path):
                    os.remove(physical_path)
                return jsonify({'status': 'error', 'error': 'Foto excede o limite de 15 MB'}), 413

            storage_rel = f"uploads/{unique_name}"
            now = datetime.now().isoformat()
            cur = conn.execute("""
                INSERT INTO evolution_photos (metric_id, photo_path, angle, taken_at, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (metric_id, storage_rel, angle, taken_at, now))
            conn.commit()

            row = conn.execute("SELECT * FROM evolution_photos WHERE id = ?", (cur.lastrowid,)).fetchone()
            return jsonify(dict_from_row(row)), 201

        rows = conn.execute("SELECT * FROM evolution_photos ORDER BY taken_at DESC, id DESC").fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/metrics/photos/<int:p_id>', methods=['DELETE'])
    def delete_evolution_photo(p_id):
        conn = get_db()
        row = conn.execute("SELECT photo_path FROM evolution_photos WHERE id = ?", (p_id,)).fetchone()
        if row and row['photo_path']:
            fname = os.path.basename(row['photo_path'])
            phys = os.path.join(app.config['UPLOAD_FOLDER'], fname)
            if os.path.exists(phys):
                try:
                    os.remove(phys)
                except OSError:
                    pass
        conn.execute("DELETE FROM evolution_photos WHERE id = ?", (p_id,))
        conn.commit()
        return jsonify({'status': 'success', 'success': True, 'deleted_id': p_id})

    # History of Exercises
    @app.route('/api/history/<int:ex_id>', methods=['GET'])
    def exercise_history(ex_id):
        conn = get_db()
        rows = conn.execute("""
            SELECT w.started_at, wi.name, ws.reps, ws.load
            FROM workout_items wi
            JOIN workouts w ON w.id = wi.workout_id
            JOIN workout_sets ws ON ws.item_id = wi.id
            WHERE wi.exercise_id = ? AND w.finished_at IS NOT NULL AND ws.done = 1
            ORDER BY w.started_at DESC, ws.position ASC
        """, (ex_id,)).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    # ------------------- CALENDAR / MATRIZ TEMPORAL (RITMO RF04) -------------------
    @app.route('/api/calendar/month', methods=['GET'])
    def calendar_month():
        conn = get_db()
        month = request.args.get('month') or datetime.now().strftime('%Y-%m')

        w_rows = conn.execute("""
            SELECT session_date, MAX(CASE WHEN COALESCE(status, 'concluido') = 'concluido' THEN 1 ELSE 0 END) AS any_done
            FROM workouts
            WHERE finished_at IS NOT NULL AND session_date LIKE ?
            GROUP BY session_date
        """, (f"{month}%",)).fetchall()
        trained_dates_set = {r['session_date'] for r in w_rows if r['session_date'] and r['any_done']}
        stopped_dates_set = {r['session_date'] for r in w_rows if r['session_date'] and not r['any_done']}

        # Also check schedules directly marked as concluido / stopped / pendente
        sched_rows = conn.execute("""
            SELECT date(scheduled_at) as s_date, COALESCE(status, 'pendente') as s_status, workout_id
            FROM schedules
            WHERE scheduled_at LIKE ?
        """, (f"{month}%",)).fetchall()

        scheduled_dates_set = set()
        for sr in sched_rows:
            sd = sr['s_date']
            if not sd:
                continue
            st = (sr['s_status'] or 'pendente').lower()
            if st == 'concluido':
                trained_dates_set.add(sd)
            elif st in ('stop', 'stopped', 'interrompido'):
                if sd not in trained_dates_set:
                    stopped_dates_set.add(sd)
            elif not sr['workout_id']:
                scheduled_dates_set.add(sd)

        return jsonify({
            'month': month,
            'trained_dates': sorted(trained_dates_set),
            'stopped_dates': sorted(stopped_dates_set),
            'scheduled_dates': sorted(scheduled_dates_set)
        })

    @app.route('/api/calendar/day/<string:date_str>', methods=['GET'])
    def calendar_day_state(date_str):
        conn = get_db()
        d_str = date_str[:10]
        today_str = date.today().isoformat()
        is_past = d_str < today_str
        is_today = d_str == today_str
        is_future = d_str > today_str

        w_rows = conn.execute("""
            SELECT * FROM workouts
            WHERE session_date = ? OR date(started_at) = ?
            ORDER BY id DESC
        """, (d_str, d_str)).fetchall()
        workouts = [_build_workout_dict(conn, w) for w in w_rows]

        finished = next((w for w in workouts if w.get('finished_at') and (w.get('status') or 'concluido') == 'concluido'), None)
        stopped = next((w for w in workouts if w.get('finished_at') and w.get('status') in ('stop', 'stopped')), None)
        active = next((w for w in workouts if not w.get('finished_at')), None)

        s_rows = conn.execute("""
            SELECT * FROM schedules
            WHERE scheduled_at = ? OR date(scheduled_at) = ?
            ORDER BY id DESC
        """, (d_str, d_str)).fetchall()
        schedules = [dict_from_row(s) for s in s_rows]

        if is_past:
            day_state = 'past_trained' if finished else ('past_stopped' if stopped else 'past_rest')
            can_schedule = False
        elif is_today:
            if finished:
                day_state = 'today_trained'
                can_schedule = False
            elif active:
                day_state = 'today_ready'
                can_schedule = False
            elif stopped:
                day_state = 'past_stopped'
                can_schedule = False
            elif schedules:
                day_state = 'today_ready'
                can_schedule = False
            else:
                day_state = 'today_idle'
                can_schedule = True
        else:
            if finished:
                day_state = 'today_trained'
                can_schedule = True
            elif stopped:
                day_state = 'past_stopped'
                can_schedule = True
            elif schedules:
                day_state = 'future_scheduled'
                can_schedule = True
            else:
                day_state = 'future_empty'
                can_schedule = True

        return jsonify({
            'date': d_str,
            'state': day_state,
            'is_past': is_past,
            'is_today': is_today,
            'is_future': is_future,
            'can_schedule': can_schedule,
            'workout': finished or stopped or active,
            'workouts': workouts,
            'schedules': schedules
        })

    @app.route('/api/calendar/schedule', methods=['POST'])
    def create_calendar_schedule():
        conn = get_db()
        data = request.get_json() or {}
        r_id = data.get('routine_id')
        sched_at = (data.get('scheduled_at') or date.today().isoformat())[:10]
        if not r_id:
            return jsonify({'status': 'error', 'error': 'Rotina é obrigatória'}), 400
        r = conn.execute("SELECT * FROM routines WHERE id = ?", (r_id,)).fetchone()
        if not r:
            return jsonify({'status': 'error', 'error': 'Rotina não encontrada'}), 404

        cur = conn.execute("""
            INSERT INTO schedules (routine_id, routine_name, scheduled_at, status)
            VALUES (?, ?, ?, 'pendente')
        """, (r['id'], r['name'], sched_at))
        conn.commit()
        s_row = conn.execute("SELECT * FROM schedules WHERE id = ?", (cur.lastrowid,)).fetchone()
        return jsonify(dict_from_row(s_row)), 201

    @app.route('/api/calendar/schedule/<int:s_id>/status', methods=['PATCH', 'PUT', 'POST'])
    @app.route('/api/calendar/schedule/<int:s_id>', methods=['PATCH', 'PUT', 'DELETE'])
    def handle_calendar_schedule_item(s_id):
        conn = get_db()
        if request.method == 'DELETE':
            conn.execute("DELETE FROM schedules WHERE id = ?", (s_id,))
            conn.commit()
            return jsonify({'status': 'success', 'success': True, 'deleted_id': s_id})

        s_row = conn.execute("SELECT * FROM schedules WHERE id = ?", (s_id,)).fetchone()
        if not s_row:
            return jsonify({'status': 'error', 'error': 'Agendamento não encontrado'}), 404

        data = request.get_json(silent=True) or {}
        raw_status = (data.get('status') or 'concluido').strip().lower()
        if raw_status in ('stop', 'stopped', 'interrompido'):
            norm_status = 'stopped'
        elif raw_status in ('concluido', 'done', 'completed'):
            norm_status = 'concluido'
        else:
            norm_status = 'pendente'

        sched_date = (s_row['scheduled_at'] or date.today().isoformat())[:10]
        now_iso = datetime.now().isoformat()
        w_id = s_row['workout_id']

        if norm_status in ('concluido', 'stopped'):
            if w_id:
                conn.execute("""
                    UPDATE workouts SET status = ?, finished_at = COALESCE(finished_at, ?) WHERE id = ?
                """, (norm_status, now_iso, w_id))
            else:
                cur_w = conn.execute("""
                    INSERT INTO workouts (routine_id, routine_name, started_at, finished_at, session_date, notes, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (s_row['routine_id'], s_row['routine_name'], f"{sched_date}T12:00:00", now_iso, sched_date, 'Atualizado direto pelo Calendário', norm_status))
                w_id = cur_w.lastrowid

                r_items = conn.execute("""
                    SELECT ri.*, e.name as ex_name
                    FROM routine_items ri
                    LEFT JOIN exercises e ON e.id = ri.exercise_id
                    WHERE ri.routine_id = ?
                    ORDER BY ri.position ASC
                """, (s_row['routine_id'],)).fetchall()
                for pos, ri in enumerate(r_items):
                    ex_name = ri['ex_name'] or 'Exercício'
                    cur_it = conn.execute("""
                        INSERT INTO workout_items (workout_id, exercise_id, name, position, rest, notes)
                        VALUES (?, ?, ?, ?, ?, '')
                    """, (w_id, ri['exercise_id'], ex_name, pos, ri['rest'] or 90))
                    it_id = cur_it.lastrowid
                    num_sets = max(1, ri['sets'] or 3)
                    done_val = 1 if norm_status == 'concluido' else 0
                    for s_pos in range(num_sets):
                        conn.execute("""
                            INSERT INTO workout_sets (item_id, position, reps, load, done)
                            VALUES (?, ?, ?, 0, ?)
                        """, (it_id, s_pos, ri['reps'] or 10, done_val))

        conn.execute("""
            UPDATE schedules SET status = ?, workout_id = ? WHERE id = ?
        """, (norm_status, w_id, s_id))
        conn.commit()

        updated_s = conn.execute("SELECT * FROM schedules WHERE id = ?", (s_id,)).fetchone()
        return jsonify(dict_from_row(updated_s))

    # ------------------- SLEEP MODULE & SETTINGS API ENDPOINTS (v1.4.0) -------------------
    VALID_SLEEP_COMPLIANCE = ('no_horario', 'nao_conseguiu_dormir', 'dormiu_menos', 'dormiu_mais')

    def _get_sleep_settings(conn: sqlite3.Connection) -> dict:
        rows = conn.execute(
            "SELECT key, value FROM user_settings WHERE key IN ('planned_bedtime', 'planned_wake_time')"
        ).fetchall()
        kv = {r['key']: r['value'] for r in rows}
        return {
            'planned_bedtime': kv.get('planned_bedtime') or '23:00',
            'planned_wake_time': kv.get('planned_wake_time') or '06:30'
        }

    @app.route('/api/settings/sleep', methods=['GET', 'PUT', 'POST'])
    def handle_sleep_settings():
        conn = get_db()
        if request.method in ('PUT', 'POST'):
            data = request.get_json(silent=True) or {}
            p_bed = (data.get('planned_bedtime') or '23:00').strip()
            p_wake = (data.get('planned_wake_time') or '06:30').strip()
            now_iso = datetime.now().isoformat()
            conn.execute("""
                INSERT INTO user_settings (key, value, updated_at) VALUES ('planned_bedtime', ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """, (p_bed, now_iso))
            conn.execute("""
                INSERT INTO user_settings (key, value, updated_at) VALUES ('planned_wake_time', ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """, (p_wake, now_iso))
            conn.commit()
        return jsonify(_get_sleep_settings(conn))

    @app.route('/api/settings/featured-goal', methods=['GET', 'PUT', 'POST'])
    def handle_featured_goal_setting():
        conn = get_db()
        if request.method in ('PUT', 'POST'):
            data = request.get_json(silent=True) or {}
            fg_id = str(data.get('featured_goal_id') or data.get('goal_id') or '').strip()
            now_iso = datetime.now().isoformat()
            conn.execute("""
                INSERT INTO user_settings (key, value, updated_at) VALUES ('featured_goal_id', ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """, (fg_id, now_iso))
            conn.commit()
            goal_obj = None
            if fg_id.isdigit():
                g_row = conn.execute("SELECT * FROM goals WHERE id = ?", (int(fg_id),)).fetchone()
                if g_row:
                    goal_obj = enrich_goal(g_row)
            return jsonify({'status': 'success', 'featured_goal_id': fg_id, 'featured_goal': goal_obj})

        row = conn.execute("SELECT value FROM user_settings WHERE key = 'featured_goal_id'").fetchone()
        val = (row['value'] if row else '').strip()
        return jsonify({'featured_goal_id': val})

    @app.route('/api/sleep/logs', methods=['GET', 'POST'])
    def handle_sleep_logs():
        conn = get_db()
        sleep_cfg = _get_sleep_settings(conn)
        if request.method == 'POST':
            data = request.get_json() or {}
            sleep_date = (data.get('sleep_date') or date.today().isoformat())[:10]
            bedtime = (data.get('bedtime') or sleep_cfg['planned_bedtime']).strip()
            wake_time = (data.get('wake_time') or sleep_cfg['planned_wake_time']).strip()
            planned_bed = (data.get('planned_bedtime') or sleep_cfg['planned_bedtime']).strip()
            planned_wake = (data.get('planned_wake_time') or sleep_cfg['planned_wake_time']).strip()
            compliance = (data.get('compliance_status') or 'no_horario').strip().lower()
            if compliance not in VALID_SLEEP_COMPLIANCE:
                compliance = 'no_horario'
            quality = max(1, min(5, int(data.get('quality_rating') or 4)))
            notes = (data.get('notes') or '').strip()
            now = datetime.now().isoformat()

            if not bedtime or not wake_time:
                return jsonify({'status': 'error', 'error': 'Horário de dormir e acordar são obrigatórios'}), 400

            try:
                t1 = datetime.strptime(bedtime[:5], '%H:%M')
                t2 = datetime.strptime(wake_time[:5], '%H:%M')
                if t2 <= t1:
                    t2 += timedelta(days=1)
                duration_minutes = int((t2 - t1).total_seconds() / 60)
            except Exception:
                duration_minutes = int(data.get('duration_minutes') or 480)

            conn.execute("""
                INSERT INTO sleep_logs (
                    sleep_date, bedtime, wake_time, duration_minutes, quality_rating,
                    planned_bedtime, planned_wake_time, compliance_status, notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sleep_date) DO UPDATE SET
                    bedtime = excluded.bedtime,
                    wake_time = excluded.wake_time,
                    duration_minutes = excluded.duration_minutes,
                    quality_rating = excluded.quality_rating,
                    planned_bedtime = excluded.planned_bedtime,
                    planned_wake_time = excluded.planned_wake_time,
                    compliance_status = excluded.compliance_status,
                    notes = excluded.notes
            """, (
                sleep_date, bedtime, wake_time, duration_minutes, quality,
                planned_bed, planned_wake, compliance, notes, now
            ))
            conn.commit()

            row = conn.execute("SELECT * FROM sleep_logs WHERE sleep_date = ?", (sleep_date,)).fetchone()
            return jsonify(dict_from_row(row)), 201

        limit_days = int(request.args.get('days') or 30)
        rows = conn.execute("""
            SELECT * FROM sleep_logs
            ORDER BY sleep_date DESC
            LIMIT ?
        """, (limit_days,)).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/sleep/summary', methods=['GET'])
    def sleep_summary():
        conn = get_db()
        today = date.today()
        seven_days_ago = (today - timedelta(days=7)).isoformat()
        rows = conn.execute("""
            SELECT AVG(duration_minutes) as avg_duration,
                   AVG(quality_rating) as avg_quality,
                   COUNT(*) as total_records
            FROM sleep_logs
            WHERE sleep_date >= ?
        """, (seven_days_ago,)).fetchone()
        comp_rows = conn.execute("""
            SELECT COALESCE(compliance_status, 'no_horario') as status, COUNT(*) as cnt
            FROM sleep_logs
            WHERE sleep_date >= ?
            GROUP BY COALESCE(compliance_status, 'no_horario')
        """, (seven_days_ago,)).fetchall()
        compliance_counts = {r['status']: r['cnt'] for r in comp_rows}
        cfg = _get_sleep_settings(conn)
        return jsonify({
            'avg_duration_minutes': round(rows['avg_duration'] or 0, 1),
            'avg_quality_rating': round(rows['avg_quality'] or 0, 1),
            'total_logged_week': rows['total_records'] or 0,
            'compliance_counts': compliance_counts,
            **cfg
        })

    @app.route('/api/sleep/logs/<int:log_id>', methods=['DELETE'])
    def delete_sleep_log(log_id):
        conn = get_db()
        conn.execute("DELETE FROM sleep_logs WHERE id = ?", (log_id,))
        conn.commit()
        return jsonify({'status': 'success', 'success': True, 'deleted_id': log_id})

    # ------------------- MODO ROTINAS DIÁRIAS API (v1.4.0: RF01-RF10, RN01-RN03) -------------------
    @app.route('/api/daily-routines', methods=['GET', 'POST'])
    def handle_daily_routines():
        conn = get_db()
        today_str = (request.args.get('date') or date.today().isoformat())[:10]
        ensure_daily_routines_initialized_for_today(conn, today_str)

        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
            title = (data.get('title') or '').strip()
            if not title:
                return jsonify({'status': 'error', 'error': 'Título da rotina é obrigatório'}), 400

            description = (data.get('description') or '').strip()
            scheduled_time = (data.get('scheduled_time') or '07:00').strip()
            raw_days = data.get('days_of_week', '0,1,2,3,4,5,6')
            if isinstance(raw_days, list):
                days_of_week = ','.join(str(int(x)) for x in raw_days if str(x).strip().isdigit())
            else:
                days_of_week = str(raw_days or '0,1,2,3,4,5,6').strip()
            if not days_of_week:
                days_of_week = '0,1,2,3,4,5,6'

            focus_min = max(1, min(180, int(data.get('pomodoro_focus_min') or 25)))
            short_min = max(1, min(60, int(data.get('pomodoro_short_break_min') or 5)))
            long_min = max(1, min(90, int(data.get('pomodoro_long_break_min') or 15)))
            cycles = max(1, min(20, int(data.get('pomodoro_cycles') or 4)))
            now_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            initial_status = (data.get('status') or 'agendada').strip().lower()
            if initial_status not in ('agendada', 'em_andamento', 'interrompida', 'concluida', 'cancelada'):
                initial_status = 'agendada'

            cur = conn.execute("""
                INSERT INTO daily_routines (
                    title, description, scheduled_time, days_of_week, status,
                    pomodoro_focus_min, pomodoro_short_break_min, pomodoro_long_break_min,
                    pomodoro_cycles, elapsed_seconds, active_date, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """, (
                title, description, scheduled_time, days_of_week, initial_status,
                focus_min, short_min, long_min, cycles, today_str, now_iso, now_iso
            ))
            r_id = cur.lastrowid

            tasks_in = data.get('tasks') or []
            parsed_tasks, err = _parse_routine_tasks_payload(tasks_in)
            if err:
                conn.rollback()
                return jsonify({'status': 'error', 'error': err}), 400
            for idx, t in enumerate(parsed_tasks):
                conn.execute("""
                    INSERT INTO daily_routine_tasks (
                        routine_id, linked_task_id, title, position, estimated_pomodoros,
                        completed_pomodoros, is_done, duration_minutes, elapsed_seconds
                    )
                    VALUES (?, ?, ?, ?, 1, 0, 0, ?, 0)
                """, (r_id, t['linked_task_id'], t['title'], idx, t['duration_minutes']))
            _recalc_routine_total_planned(conn, r_id)

            conn.commit()
            # Trigger today's initialization if scheduled for today
            ensure_daily_routines_initialized_for_today(conn, today_str)
            row = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
            return jsonify(_enrich_daily_routine(conn, row, today_str)), 201

        rows = conn.execute("""
            SELECT * FROM daily_routines
            ORDER BY CASE status
                WHEN 'em_andamento' THEN 0
                WHEN 'interrompida' THEN 1
                WHEN 'agendada' THEN 2
                WHEN 'concluida' THEN 3
                ELSE 4
            END, scheduled_time ASC, id DESC
        """).fetchall()
        return jsonify([_enrich_daily_routine(conn, r, today_str) for r in rows])

    @app.route('/api/daily-routines/today', methods=['GET'])
    def daily_routines_today():
        conn = get_db()
        today_str = (request.args.get('date') or date.today().isoformat())[:10]
        notifications = ensure_daily_routines_initialized_for_today(conn, today_str)
        rows = conn.execute("""
            SELECT * FROM daily_routines
            ORDER BY CASE status
                WHEN 'em_andamento' THEN 0
                WHEN 'interrompida' THEN 1
                WHEN 'agendada' THEN 2
                WHEN 'concluida' THEN 3
                ELSE 4
            END, scheduled_time ASC, id DESC
        """).fetchall()
        enriched = [_enrich_daily_routine(conn, r, today_str) for r in rows]
        sleep_today = conn.execute("SELECT * FROM sleep_logs WHERE sleep_date = ?", (today_str,)).fetchone()
        sleep_cfg = _get_sleep_settings(conn)
        return jsonify({
            'date': today_str,
            'routines': enriched,
            'active_routine': next((r for r in enriched if r['status'] in ('em_andamento', 'interrompida', 'concluida')), enriched[0] if enriched else None),
            'push_notifications': notifications,
            'sleep_today': dict_from_row(sleep_today) if sleep_today else None,
            'sleep_settings': sleep_cfg
        })

    @app.route('/api/daily-routines/<int:r_id>', methods=['GET', 'PUT', 'DELETE'])
    def daily_routine_detail(r_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        if not row:
            return jsonify({'status': 'error', 'error': 'Rotina diária não encontrada'}), 404

        today_str = date.today().isoformat()
        if request.method == 'GET':
            return jsonify(_enrich_daily_routine(conn, row, today_str))

        if request.method == 'DELETE':
            conn.execute("DELETE FROM daily_routines WHERE id = ?", (r_id,))
            conn.commit()
            return jsonify({'status': 'success', 'success': True, 'deleted_id': r_id})

        # PUT: Edit routine (allowed even when status == 'cancelada' per RN01)
        data = request.get_json(silent=True) or {}
        title = (data.get('title') if 'title' in data else row['title']).strip()
        if not title:
            return jsonify({'status': 'error', 'error': 'Título da rotina é obrigatório'}), 400
        description = (data.get('description') if 'description' in data else (row['description'] or '')).strip()
        scheduled_time = (data.get('scheduled_time') if 'scheduled_time' in data else (row['scheduled_time'] or '07:00')).strip()

        if 'days_of_week' in data:
            raw_days = data['days_of_week']
            if isinstance(raw_days, list):
                days_of_week = ','.join(str(int(x)) for x in raw_days if str(x).strip().isdigit())
            else:
                days_of_week = str(raw_days or '0,1,2,3,4,5,6').strip()
        else:
            days_of_week = row['days_of_week']

        focus_min = max(1, min(180, int(data.get('pomodoro_focus_min', row['pomodoro_focus_min']) or 25)))
        short_min = max(1, min(60, int(data.get('pomodoro_short_break_min', row['pomodoro_short_break_min']) or 5)))
        long_min = max(1, min(90, int(data.get('pomodoro_long_break_min', row['pomodoro_long_break_min']) or 15)))
        cycles = max(1, min(20, int(data.get('pomodoro_cycles', row['pomodoro_cycles']) or 4)))
        now_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        conn.execute("""
            UPDATE daily_routines
            SET title = ?, description = ?, scheduled_time = ?, days_of_week = ?,
                pomodoro_focus_min = ?, pomodoro_short_break_min = ?,
                pomodoro_long_break_min = ?, pomodoro_cycles = ?, updated_at = ?
            WHERE id = ?
        """, (
            title, description, scheduled_time, days_of_week,
            focus_min, short_min, long_min, cycles, now_iso, r_id
        ))

        if 'tasks' in data and isinstance(data['tasks'], list):
            parsed_tasks, err = _parse_routine_tasks_payload(data['tasks'])
            if err:
                conn.rollback()
                return jsonify({'status': 'error', 'error': err}), 400
            conn.execute("DELETE FROM daily_routine_tasks WHERE routine_id = ?", (r_id,))
            for idx, t in enumerate(parsed_tasks):
                conn.execute("""
                    INSERT INTO daily_routine_tasks (
                        routine_id, linked_task_id, title, position,
                        estimated_pomodoros, completed_pomodoros, is_done, duration_minutes, elapsed_seconds
                    )
                    VALUES (?, ?, ?, ?, 1, 0, ?, ?, ?)
                """, (r_id, t['linked_task_id'], t['title'], idx, t['is_done'], t['duration_minutes'], t['elapsed_seconds']))
        _recalc_routine_total_planned(conn, r_id)

        conn.commit()
        updated = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        return jsonify(_enrich_daily_routine(conn, updated, today_str))

    @app.route('/api/daily-routines/<int:r_id>/start', methods=['POST'])
    def start_daily_routine(r_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        if not row:
            return jsonify({'status': 'error', 'error': 'Rotina diária não encontrada'}), 404

        # RN01: Cancelled routine cannot be started
        if row['status'] == 'cancelada':
            return jsonify({
                'status': 'error',
                'error': 'Rotina cancelada não pode ser iniciada. Reative-a primeiro.'
            }), 400

        today_str = date.today().isoformat()
        now_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        conn.execute("""
            UPDATE daily_routines
            SET status = 'em_andamento', active_date = ?, updated_at = ?
            WHERE id = ?
        """, (today_str, now_iso, r_id))

        log_row = conn.execute("""
            SELECT * FROM daily_routine_logs WHERE routine_id = ? AND execution_date = ?
        """, (r_id, today_str)).fetchone()
        if not log_row:
            conn.execute("""
                INSERT INTO daily_routine_logs (routine_id, execution_date, status, started_at, notified_at)
                VALUES (?, ?, 'em_andamento', ?, ?)
            """, (r_id, today_str, now_iso, now_iso))
        else:
            conn.execute("""
                UPDATE daily_routine_logs SET status = 'em_andamento' WHERE id = ?
            """, (log_row['id'],))

        conn.commit()
        updated = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        return jsonify(_enrich_daily_routine(conn, updated, today_str))

    @app.route('/api/daily-routines/<int:r_id>/interrupt', methods=['POST'])
    def interrupt_daily_routine(r_id):
        """
        [RF03 / RN03 / Decisão 02 / US02]:
        Interrupts an active routine, freezes elapsed_seconds, and strictly requires a non-empty reason.
        Records exact timestamp down to the minute/second in daily_routine_interruptions.
        """
        conn = get_db()
        row = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        if not row:
            return jsonify({'status': 'error', 'error': 'Rotina diária não encontrada'}), 404

        if row['status'] == 'cancelada':
            return jsonify({'status': 'error', 'error': 'Rotina cancelada não pode ser interrompida.'}), 400

        data = request.get_json(silent=True) or {}
        reason = (data.get('reason') or '').strip()
        if not reason:
            return jsonify({
                'status': 'error',
                'error': 'O motivo da interrupção é obrigatório.'
            }), 400

        elapsed_sec = int(data.get('elapsed_seconds') if data.get('elapsed_seconds') is not None else (row['elapsed_seconds'] or 0))
        today_str = (data.get('execution_date') or row['active_date'] or date.today().isoformat())[:10]
        now_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        log_row = conn.execute("""
            SELECT * FROM daily_routine_logs WHERE routine_id = ? AND execution_date = ?
        """, (r_id, today_str)).fetchone()
        if not log_row:
            cur_log = conn.execute("""
                INSERT INTO daily_routine_logs (routine_id, execution_date, status, started_at, total_focus_seconds)
                VALUES (?, ?, 'interrompida', ?, ?)
            """, (r_id, today_str, now_iso, elapsed_sec))
            log_id = cur_log.lastrowid
        else:
            log_id = log_row['id']
            conn.execute("""
                UPDATE daily_routine_logs
                SET status = 'interrompida', total_focus_seconds = ?
                WHERE id = ?
            """, (elapsed_sec, log_id))

        conn.execute("""
            UPDATE daily_routines
            SET status = 'interrompida', elapsed_seconds = ?, active_date = ?, updated_at = ?
            WHERE id = ?
        """, (elapsed_sec, today_str, now_iso, r_id))

        conn.execute("""
            INSERT INTO daily_routine_interruptions (
                routine_id, log_id, execution_date, interrupted_at, elapsed_seconds_at_pause, reason
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (r_id, log_id, today_str, now_iso, elapsed_sec, reason))

        conn.commit()
        updated = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        payload = _enrich_daily_routine(conn, updated, today_str)
        payload['reason'] = reason
        return jsonify(payload)

    @app.route('/api/daily-routines/<int:r_id>/resume', methods=['POST'])
    def resume_daily_routine(r_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        if not row:
            return jsonify({'status': 'error', 'error': 'Rotina diária não encontrada'}), 404
        if row['status'] == 'cancelada':
            return jsonify({'status': 'error', 'error': 'Rotina cancelada não pode ser retomada. Reative-a primeiro.'}), 400

        today_str = (row['active_date'] or date.today().isoformat())[:10]
        now_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        conn.execute("""
            UPDATE daily_routines
            SET status = 'em_andamento', active_date = ?, updated_at = ?
            WHERE id = ?
        """, (today_str, now_iso, r_id))

        conn.execute("""
            UPDATE daily_routine_logs
            SET status = 'em_andamento'
            WHERE routine_id = ? AND execution_date = ?
        """, (r_id, today_str))

        last_int = conn.execute("""
            SELECT id FROM daily_routine_interruptions
            WHERE routine_id = ? AND execution_date = ? AND resumed_at IS NULL
            ORDER BY id DESC LIMIT 1
        """, (r_id, today_str)).fetchone()
        if last_int:
            conn.execute("""
                UPDATE daily_routine_interruptions SET resumed_at = ? WHERE id = ?
            """, (now_iso, last_int['id']))

        conn.commit()
        updated = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        return jsonify(_enrich_daily_routine(conn, updated, today_str))

    @app.route('/api/daily-routines/<int:r_id>/complete', methods=['POST'])
    def complete_daily_routine(r_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        if not row:
            return jsonify({'status': 'error', 'error': 'Rotina diária não encontrada'}), 404
        if row['status'] == 'cancelada':
            return jsonify({'status': 'error', 'error': 'Rotina cancelada não pode ser concluída.'}), 400

        data = request.get_json(silent=True) or {}
        raw_sec = data.get('elapsed_seconds') if data.get('elapsed_seconds') is not None else data.get('total_focus_seconds')
        elapsed_sec = int(raw_sec if raw_sec is not None else (row['elapsed_seconds'] or 0))
        pomodoros_done = int(data.get('pomodoros_completed') or 0)
        today_str = (row['active_date'] or date.today().isoformat())[:10]
        now_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        conn.execute("""
            UPDATE daily_routines
            SET status = 'concluida', elapsed_seconds = ?, active_date = ?, updated_at = ?
            WHERE id = ?
        """, (elapsed_sec, today_str, now_iso, r_id))

        log_row = conn.execute("""
            SELECT * FROM daily_routine_logs WHERE routine_id = ? AND execution_date = ?
        """, (r_id, today_str)).fetchone()
        if not log_row:
            conn.execute("""
                INSERT INTO daily_routine_logs (
                    routine_id, execution_date, status, started_at, finished_at, total_focus_seconds, pomodoros_completed
                )
                VALUES (?, ?, 'concluida', ?, ?, ?, ?)
            """, (r_id, today_str, now_iso, now_iso, elapsed_sec, pomodoros_done))
        else:
            conn.execute("""
                UPDATE daily_routine_logs
                SET status = 'concluida', finished_at = ?,
                    total_focus_seconds = MAX(total_focus_seconds, ?),
                    pomodoros_completed = MAX(pomodoros_completed, ?)
                WHERE id = ?
            """, (now_iso, elapsed_sec, pomodoros_done, log_row['id']))

        conn.commit()
        updated = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        return jsonify(_enrich_daily_routine(conn, updated, today_str))

    @app.route('/api/daily-routines/<int:r_id>/cancel', methods=['POST'])
    def cancel_daily_routine(r_id):
        """
        [RF05 / RN01 / Decisão 04]:
        Immediate Manual Cancellation -> status = 'cancelada'.
        Blocks starting and scheduling until reactivated.
        """
        conn = get_db()
        row = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        if not row:
            return jsonify({'status': 'error', 'error': 'Rotina diária não encontrada'}), 404

        today_str = date.today().isoformat()
        now_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        conn.execute("""
            UPDATE daily_routines SET status = 'cancelada', updated_at = ? WHERE id = ?
        """, (now_iso, r_id))
        conn.execute("""
            UPDATE daily_routine_logs SET status = 'cancelada', finished_at = ?
            WHERE routine_id = ? AND execution_date = ? AND status != 'concluida'
        """, (now_iso, r_id, today_str))
        conn.commit()
        updated = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        return jsonify(_enrich_daily_routine(conn, updated, today_str))

    @app.route('/api/daily-routines/<int:r_id>/reactivate', methods=['POST'])
    def reactivate_daily_routine(r_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        if not row:
            return jsonify({'status': 'error', 'error': 'Rotina diária não encontrada'}), 404

        today_str = date.today().isoformat()
        now_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        conn.execute("""
            UPDATE daily_routines SET status = 'agendada', updated_at = ? WHERE id = ?
        """, (now_iso, r_id))
        conn.execute("""
            DELETE FROM daily_routine_logs
            WHERE routine_id = ? AND execution_date = ? AND status = 'cancelada'
        """, (r_id, today_str))
        conn.commit()

        ensure_daily_routines_initialized_for_today(conn, today_str)
        updated = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        payload = _enrich_daily_routine(conn, updated, today_str)
        payload['status'] = 'ativa'
        return jsonify(payload)

    @app.route('/api/daily-routines/<int:r_id>/suspensions', methods=['GET', 'POST'])
    def handle_routine_suspensions(r_id):
        """
        [RF06 / RN01 / RN02 / US01 / Decisão 04]:
        Schedules a temporary suspension (by date_range or days_of_week).
        Blocked if routine is manually cancelled (status == 'cancelada').
        """
        conn = get_db()
        row = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        if not row:
            return jsonify({'status': 'error', 'error': 'Rotina diária não encontrada'}), 404

        if request.method == 'GET':
            s_rows = conn.execute("""
                SELECT * FROM daily_routine_suspensions
                WHERE routine_id = ?
                ORDER BY is_active DESC, id DESC
            """, (r_id,)).fetchall()
            out = []
            for s in s_rows:
                sd = dict_from_row(s)
                sd['reason'] = sd.get('note') or ''
                out.append(sd)
            return jsonify(out)

        # RN01: Manual cancellation blocks scheduling suspensions
        if row['status'] == 'cancelada':
            return jsonify({
                'status': 'error',
                'error': 'Rotina cancelada não permite novos agendamentos. Reative-a primeiro.'
            }), 400

        data = request.get_json(silent=True) or {}
        s_type = (data.get('suspension_type') or 'date_range').strip().lower()
        if s_type not in ('date_range', 'days_of_week'):
            return jsonify({'status': 'error', 'error': 'suspension_type inválido'}), 400

        start_date = (data.get('start_date') or date.today().isoformat())[:10]
        end_date = (data.get('end_date') or '')[:10] or None
        raw_days = data.get('days_of_week') or ''
        if isinstance(raw_days, list):
            days_of_week = ','.join(str(int(x)) for x in raw_days if str(x).strip().isdigit())
        else:
            days_of_week = str(raw_days).strip()

        if s_type == 'date_range' and (not start_date or not end_date):
            return jsonify({'status': 'error', 'error': 'Informe data inicial e data final para o intervalo.'}), 400
        if s_type == 'days_of_week' and not days_of_week:
            return jsonify({'status': 'error', 'error': 'Selecione ao menos um dia da semana para suspender.'}), 400

        note = (data.get('note') or data.get('reason') or '').strip()
        now_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cur = conn.execute("""
            INSERT INTO daily_routine_suspensions (
                routine_id, suspension_type, start_date, end_date, days_of_week, note, is_active, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """, (r_id, s_type, start_date, end_date, days_of_week, note, now_iso))

        today_str = date.today().isoformat()
        if _is_routine_suspended_on_date(conn, r_id, today_str):
            conn.execute("""
                UPDATE daily_routines SET status = 'agendada', updated_at = ? WHERE id = ? AND status = 'em_andamento'
            """, (now_iso, r_id))
            conn.execute("""
                INSERT INTO daily_routine_logs (routine_id, execution_date, status, started_at)
                VALUES (?, ?, 'suspensa', ?)
                ON CONFLICT(routine_id, execution_date) DO UPDATE SET status = 'suspensa'
            """, (r_id, today_str, now_iso))

        conn.commit()
        s_row = conn.execute("SELECT * FROM daily_routine_suspensions WHERE id = ?", (cur.lastrowid,)).fetchone()
        s_dict = dict_from_row(s_row)
        s_dict['reason'] = s_dict.get('note') or ''
        return jsonify(s_dict), 201

    @app.route('/api/daily-routines/suspensions/<int:susp_id>', methods=['DELETE'])
    def delete_routine_suspension(susp_id):
        conn = get_db()
        s_row = conn.execute("SELECT * FROM daily_routine_suspensions WHERE id = ?", (susp_id,)).fetchone()
        if not s_row:
            return jsonify({'status': 'error', 'error': 'Suspensão não encontrada'}), 404
        r_id = s_row['routine_id']
        conn.execute("DELETE FROM daily_routine_suspensions WHERE id = ?", (susp_id,))
        conn.commit()
        ensure_daily_routines_initialized_for_today(conn, date.today().isoformat())
        return jsonify({'status': 'success', 'success': True, 'deleted_id': susp_id, 'routine_id': r_id})

    @app.route('/api/daily-routines/<int:r_id>/comments', methods=['GET', 'POST'])
    def handle_routine_comments(r_id):
        """
        [RF04]: Chronological comments with exact timestamp at any stage of routine lifecycle.
        """
        conn = get_db()
        row = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        if not row:
            return jsonify({'status': 'error', 'error': 'Rotina diária não encontrada'}), 404

        if request.method == 'GET':
            c_rows = conn.execute("""
                SELECT * FROM daily_routine_comments
                WHERE routine_id = ?
                ORDER BY created_at DESC, id DESC
            """, (r_id,)).fetchall()
            return jsonify([dict_from_row(c) for c in c_rows])

        data = request.get_json(silent=True) or {}
        comment_text = (data.get('comment_text') or data.get('text') or '').strip()
        if not comment_text:
            return jsonify({'status': 'error', 'error': 'O texto do comentário é obrigatório'}), 400

        exec_date = (data.get('execution_date') or row['active_date'] or date.today().isoformat())[:10]
        now_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        log_row = conn.execute("""
            SELECT id FROM daily_routine_logs WHERE routine_id = ? AND execution_date = ?
        """, (r_id, exec_date)).fetchone()
        log_id = log_row['id'] if log_row else None

        cur = conn.execute("""
            INSERT INTO daily_routine_comments (routine_id, log_id, execution_date, comment_text, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (r_id, log_id, exec_date, comment_text, now_iso))
        conn.commit()

        c_row = conn.execute("SELECT * FROM daily_routine_comments WHERE id = ?", (cur.lastrowid,)).fetchone()
        return jsonify(dict_from_row(c_row)), 201

    @app.route('/api/daily-routines/<int:r_id>/tasks/<int:t_id>', methods=['PATCH', 'PUT'])
    def update_daily_routine_task(r_id, t_id):
        conn = get_db()
        t_row = conn.execute("""
            SELECT * FROM daily_routine_tasks WHERE id = ? AND routine_id = ?
        """, (t_id, r_id)).fetchone()
        if not t_row:
            return jsonify({'status': 'error', 'error': 'Tarefa da rotina não encontrada'}), 404

        data = request.get_json(silent=True) or {}
        now_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if 'is_done' in data:
            is_done = 1 if data['is_done'] in (True, 1, '1', 'true') else 0
        elif 'done' in data:
            is_done = 1 if data['done'] in (True, 1, '1', 'true') else 0
        else:
            is_done = 0 if int(t_row['is_done'] or 0) == 1 else 1

        task_elapsed = int(t_row['elapsed_seconds'] or 0) if 'elapsed_seconds' in t_row.keys() else 0
        if data.get('task_elapsed_seconds') is not None:
            task_elapsed = max(0, int(data['task_elapsed_seconds']))

        comp_at = now_iso if is_done == 1 else None
        conn.execute("""
            UPDATE daily_routine_tasks
            SET is_done = ?, elapsed_seconds = ?, completed_at = ?
            WHERE id = ? AND routine_id = ?
        """, (is_done, task_elapsed, comp_at, t_id, r_id))

        if 'elapsed_seconds' in data and data['elapsed_seconds'] is not None:
            el_sec = int(data['elapsed_seconds'])
            conn.execute("UPDATE daily_routines SET elapsed_seconds = ?, updated_at = ? WHERE id = ?", (el_sec, now_iso, r_id))
            conn.execute("""
                UPDATE daily_routine_logs SET total_focus_seconds = MAX(total_focus_seconds, ?)
                WHERE routine_id = ? AND execution_date = ?
            """, (el_sec, r_id, date.today().isoformat()))

        conn.commit()
        r_row = conn.execute("SELECT * FROM daily_routines WHERE id = ?", (r_id,)).fetchone()
        return jsonify(_enrich_daily_routine(conn, r_row, date.today().isoformat()))

    @app.route('/api/daily-routines/calendar', methods=['GET'])
    def daily_routines_calendar():
        """
        [RF09]: Monthly / Weekly calendar matrix of planned routines, completed/interrupted logs,
        and scheduled temporary suspensions.
        """
        conn = get_db()
        month_str = (request.args.get('month') or datetime.now().strftime('%Y-%m'))[:7]
        try:
            year, month = map(int, month_str.split('-'))
        except ValueError:
            today_d = date.today()
            year, month = today_d.year, today_d.month
            month_str = f"{year:04d}-{month:02d}"

        ensure_daily_routines_initialized_for_today(conn, date.today().isoformat())

        routines = [dict_from_row(r) for r in conn.execute("SELECT * FROM daily_routines ORDER BY scheduled_time ASC").fetchall()]
        logs = [dict_from_row(l) for l in conn.execute("""
            SELECT l.*, dr.title as routine_title
            FROM daily_routine_logs l
            JOIN daily_routines dr ON dr.id = l.routine_id
            WHERE l.execution_date LIKE ?
        """, (f"{month_str}%",)).fetchall()]
        suspensions = []
        for s in conn.execute("""
            SELECT s.*, dr.title as routine_title
            FROM daily_routine_suspensions s
            JOIN daily_routines dr ON dr.id = s.routine_id
            WHERE s.is_active = 1
        """).fetchall():
            sd = dict_from_row(s)
            sd['reason'] = sd.get('note') or ''
            suspensions.append(sd)

        sleep_rows = conn.execute("""
            SELECT * FROM sleep_logs WHERE sleep_date LIKE ?
        """, (f"{month_str}%",)).fetchall()
        sleep_by_date = {r['sleep_date']: dict_from_row(r) for r in sleep_rows}

        logs_by_day = {}
        for lg in logs:
            logs_by_day.setdefault(lg['execution_date'], []).append(lg)

        days_in_month = calendar.monthrange(year, month)[1]
        days_matrix = []
        for day_num in range(1, days_in_month + 1):
            d_obj = date(year, month, day_num)
            d_str = d_obj.isoformat()
            js_wday = _date_to_js_weekday(d_obj)
            day_logs = logs_by_day.get(d_str, [])
            logged_r_ids = {lg['routine_id'] for lg in day_logs}

            items = []
            for lg in day_logs:
                items.append({
                    'routine_id': lg['routine_id'],
                    'title': lg['routine_title'],
                    'status': lg['status'],
                    'state': lg['status'],
                    'total_focus_seconds': lg['total_focus_seconds']
                })

            for r in routines:
                if r['id'] in logged_r_ids:
                    continue
                if r['status'] == 'cancelada':
                    continue
                if js_wday in _parse_days_of_week(r['days_of_week']):
                    susp = _is_routine_suspended_on_date(conn, r['id'], d_str)
                    st_val = 'suspensa' if susp else 'planejada'
                    items.append({
                        'routine_id': r['id'],
                        'title': r['title'],
                        'status': 'suspensa' if susp else 'agendada',
                        'state': st_val,
                        'suspension': susp
                    })

            days_matrix.append({
                'date': d_str,
                'day': day_num,
                'weekday': js_wday,
                'sleep': sleep_by_date.get(d_str),
                'items': items
            })

        completed_days_set = set()
        in_progress_days_set = set()
        interrupted_days_set = set()
        suspended_days_set = set()
        total_runs = 0

        for d in days_matrix:
            d_date = d['date']
            for it in d.get('items', []):
                st = it.get('state') or it.get('status')
                if st == 'concluida':
                    completed_days_set.add(d_date)
                    total_runs += 1
                elif st == 'em_andamento':
                    in_progress_days_set.add(d_date)
                    total_runs += 1
                elif st == 'interrompida':
                    interrupted_days_set.add(d_date)
                    total_runs += 1
                elif st == 'suspensa':
                    suspended_days_set.add(d_date)

        return jsonify({
            'month': month_str,
            'days': days_matrix,
            'suspensions': suspensions,
            'routines': routines,
            'summary': {
                'total_runs': total_runs,
                'completed_days': len(completed_days_set),
                'interrupted_suspended_days': len(interrupted_days_set | suspended_days_set),
                'completed_dates': sorted(completed_days_set),
                'in_progress_dates': sorted(in_progress_days_set),
                'interrupted_dates': sorted(interrupted_days_set),
                'suspended_dates': sorted(suspended_days_set)
            }
        })

    @app.route('/api/daily-routines/day/<string:date_str>', methods=['GET'])
    def daily_routines_day_details(date_str):
        conn = get_db()
        d_str = date_str[:10]
        today_str = date.today().isoformat()
        is_past = d_str < today_str
        is_today = d_str == today_str
        is_future = d_str > today_str

        if is_today:
            ensure_daily_routines_initialized_for_today(conn, d_str)

        log_rows = conn.execute("""
            SELECT l.*, dr.title as routine_title, dr.scheduled_time, dr.total_planned_minutes
            FROM daily_routine_logs l
            JOIN daily_routines dr ON dr.id = l.routine_id
            WHERE l.execution_date = ?
            ORDER BY dr.scheduled_time ASC, l.id ASC
        """, (d_str,)).fetchall()

        logs = []
        for lr in log_rows:
            ld = dict_from_row(lr)
            ld['tasks'] = [dict_from_row(t) for t in conn.execute("""
                SELECT * FROM daily_routine_tasks WHERE routine_id = ? ORDER BY position ASC, id ASC
            """, (ld['routine_id'],)).fetchall()]
            ld['interruptions'] = [dict_from_row(i) for i in conn.execute("""
                SELECT * FROM daily_routine_interruptions WHERE routine_id = ? AND execution_date = ? ORDER BY id ASC
            """, (ld['routine_id'], d_str)).fetchall()]
            ld['comments'] = [dict_from_row(c) for c in conn.execute("""
                SELECT * FROM daily_routine_comments WHERE routine_id = ? AND execution_date = ? ORDER BY id ASC
            """, (ld['routine_id'], d_str)).fetchall()]
            logs.append(ld)

        try:
            d_obj = datetime.strptime(d_str, '%Y-%m-%d').date()
            js_wday = _date_to_js_weekday(d_obj)
        except Exception:
            js_wday = 0

        logged_routine_ids = {l['routine_id'] for l in logs}
        configured = []
        for r in conn.execute("SELECT * FROM daily_routines WHERE status != 'cancelada' ORDER BY scheduled_time ASC").fetchall():
            rd = dict_from_row(r)
            if rd['id'] in logged_routine_ids:
                continue
            if js_wday in _parse_days_of_week(rd.get('days_of_week') or ''):
                susp = _is_routine_suspended_on_date(conn, rd['id'], d_str)
                rd['is_suspended'] = bool(susp)
                rd['suspension'] = susp
                configured.append(rd)

        sleep_row = conn.execute("SELECT * FROM sleep_logs WHERE sleep_date = ?", (d_str,)).fetchone()
        sleep_log = dict_from_row(sleep_row) if sleep_row else None

        suspensions = [dict_from_row(s) for s in conn.execute("""
            SELECT s.*, dr.title as routine_title
            FROM daily_routine_suspensions s
            JOIN daily_routines dr ON dr.id = s.routine_id
            WHERE s.is_active = 1
              AND (
                (s.suspension_type = 'date_range' AND s.start_date <= ? AND s.end_date >= ?)
                OR
                (s.suspension_type = 'days_of_week')
              )
        """, (d_str, d_str)).fetchall()]

        return jsonify({
            'date': d_str,
            'is_past': is_past,
            'is_today': is_today,
            'is_future': is_future,
            'logs': logs,
            'configured_routines': configured,
            'sleep': sleep_log,
            'suspensions': suspensions
        })

    @app.route('/api/daily-routines/history', methods=['GET'])
    def daily_routines_history():
        """
        [RF10 / US02]: Retrospective audit of executions, interruptions with exact timestamps and reasons,
        chronological comments, total focus time, and daily correlation with sleep_logs.
        """
        conn = get_db()
        end_date = (request.args.get('end_date') or date.today().isoformat())[:10]
        start_date = (request.args.get('start_date') or (date.today() - timedelta(days=30)).isoformat())[:10]
        routine_id = request.args.get('routine_id')

        q_logs = """
            SELECT l.*, dr.title as routine_title, dr.scheduled_time, dr.total_planned_minutes,
                   (SELECT COUNT(*) FROM daily_routine_tasks tt WHERE tt.routine_id = l.routine_id) as total_tasks
            FROM daily_routine_logs l
            JOIN daily_routines dr ON dr.id = l.routine_id
            WHERE l.execution_date >= ? AND l.execution_date <= ?
        """
        params = [start_date, end_date]
        if routine_id and str(routine_id).isdigit():
            q_logs += " AND l.routine_id = ?"
            params.append(int(routine_id))
        q_logs += " ORDER BY l.execution_date DESC, l.id DESC"
        logs = [dict_from_row(r) for r in conn.execute(q_logs, params).fetchall()]

        int_rows = conn.execute("""
            SELECT i.*, dr.title as routine_title
            FROM daily_routine_interruptions i
            JOIN daily_routines dr ON dr.id = i.routine_id
            WHERE i.execution_date >= ? AND i.execution_date <= ?
            ORDER BY i.interrupted_at DESC, i.id DESC
        """, (start_date, end_date)).fetchall()
        interruptions = [dict_from_row(r) for r in int_rows]

        comm_rows = conn.execute("""
            SELECT c.*, dr.title as routine_title
            FROM daily_routine_comments c
            JOIN daily_routines dr ON dr.id = c.routine_id
            WHERE c.execution_date >= ? AND c.execution_date <= ?
            ORDER BY c.created_at DESC, c.id DESC
        """, (start_date, end_date)).fetchall()
        comments = [dict_from_row(r) for r in comm_rows]

        sleep_rows = conn.execute("""
            SELECT * FROM sleep_logs
            WHERE sleep_date >= ? AND sleep_date <= ?
            ORDER BY sleep_date DESC
        """, (start_date, end_date)).fetchall()
        sleep_by_date = {r['sleep_date']: dict_from_row(r) for r in sleep_rows}

        ints_by_key = {}
        for i in interruptions:
            ints_by_key.setdefault((i['routine_id'], i['execution_date']), []).append(i)

        comms_by_key = {}
        for c in comments:
            comms_by_key.setdefault((c['routine_id'], c['execution_date']), []).append(c)

        total_focus_sec = 0
        completed_count = 0
        interrupted_count = 0
        suspended_count = 0
        for lg in logs:
            key = (lg['routine_id'], lg['execution_date'])
            lg['log_date'] = lg['execution_date']
            lg['interruptions'] = ints_by_key.get(key, [])
            lg['comments'] = comms_by_key.get(key, [])
            lg['sleep_log'] = sleep_by_date.get(lg['execution_date'])
            lg['sleep'] = lg['sleep_log']
            total_focus_sec += int(lg.get('total_focus_seconds') or 0)
            if lg['status'] == 'concluida':
                completed_count += 1
            elif lg['status'] == 'suspensa':
                suspended_count += 1
            elif lg['status'] == 'interrompida' or lg['interruptions']:
                interrupted_count += 1

        denom = max(1, len(logs) - suspended_count)
        completion_rate = round((completed_count / denom) * 100.0, 1) if len(logs) > 0 else 0.0

        return jsonify({
            'start_date': start_date,
            'end_date': end_date,
            'summary': {
                'total_logs': len(logs),
                'completed_count': completed_count,
                'completed': completed_count,
                'interrupted_count': interrupted_count,
                'interrupted': interrupted_count,
                'suspended_count': suspended_count,
                'suspended': suspended_count,
                'completion_rate': completion_rate,
                'total_focus_seconds': total_focus_sec,
                'total_focus_minutes': round(total_focus_sec / 60.0, 1),
                'total_interruptions': len(interruptions),
                'total_comments': len(comments)
            },
            'logs': logs,
            'items': logs,
            'interruptions': interruptions,
            'comments': comments,
            'sleep_logs': list(sleep_by_date.values())
        })

    # ------------------- RITMO EXERCISE EVOLUTION API (v1.4.0: RF13, RF14, RN05, US03) -------------------
    @app.route('/api/ritmo/performed-exercises', methods=['GET'])
    def ritmo_performed_exercises():
        conn = get_db()
        rows = conn.execute("""
            SELECT e.id, e.name, e.muscle_group, e.equipment,
                   COUNT(DISTINCT w.id) as sessions_count,
                   MAX(ws.load) as best_load_kg,
                   MAX(ws.load) as all_time_max_load
            FROM exercises e
            JOIN workout_items wi ON wi.exercise_id = e.id
            JOIN workouts w ON w.id = wi.workout_id
                AND w.finished_at IS NOT NULL
                AND COALESCE(w.status, 'concluido') NOT IN ('cancelado', 'descartado')
            JOIN workout_sets ws ON ws.item_id = wi.id AND ws.done = 1
            GROUP BY e.id
            HAVING COUNT(DISTINCT w.id) > 0
            ORDER BY sessions_count DESC, e.name ASC
        """).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/ritmo/exercise-evolution', methods=['GET'])
    def ritmo_exercise_evolution():
        """
        [RF13 / RF14 / RN05 / RNF01 / US03 / Decisão 03]:
        Returns time series for an exercise across strictly finished workouts and completed sets (done = 1).
        Supports Mode 1: Max Load (kg), Mode 2: Total Volume (kg * reps), and Total Reps.
        """
        conn = get_db()
        ex_id_raw = request.args.get('exercise_id')
        period = (request.args.get('period') or 'all').strip().lower()

        if not ex_id_raw or not str(ex_id_raw).isdigit():
            return jsonify({'status': 'error', 'error': 'exercise_id é obrigatório'}), 400
        ex_id = int(ex_id_raw)

        ex_row = conn.execute("SELECT * FROM exercises WHERE id = ?", (ex_id,)).fetchone()
        if not ex_row:
            return jsonify({'status': 'error', 'error': 'Exercício não encontrado'}), 404

        today_d = date.today()
        period_days_map = {'1m': 30, '3m': 90, '6m': 180, '1y': 365, '1a': 365}
        min_date_str = None
        if period in period_days_map:
            min_date_str = (today_d - timedelta(days=period_days_map[period])).isoformat()

        # RN05: Filter strictly finished workouts and done = 1 sets
        query = """
            SELECT w.id as workout_id,
                   COALESCE(w.session_date, substr(w.started_at, 1, 10)) as session_date,
                   w.routine_name,
                   w.started_at,
                   ws.position,
                   ws.reps,
                   ws.load,
                   ws.rpe
            FROM workout_items wi
            JOIN workouts w ON w.id = wi.workout_id
            JOIN workout_sets ws ON ws.item_id = wi.id
            WHERE wi.exercise_id = ?
              AND w.finished_at IS NOT NULL
              AND COALESCE(w.status, 'concluido') NOT IN ('cancelado', 'descartado')
              AND ws.done = 1
        """
        params = [ex_id]
        if min_date_str:
            query += " AND COALESCE(w.session_date, substr(w.started_at, 1, 10)) >= ?"
            params.append(min_date_str)
        query += " ORDER BY session_date ASC, w.id ASC, ws.position ASC, ws.id ASC"

        rows = conn.execute(query, params).fetchall()

        sessions_map = {}
        sessions_order = []
        for r in rows:
            w_id = r['workout_id']
            if w_id not in sessions_map:
                sessions_map[w_id] = {
                    'workout_id': w_id,
                    'session_date': r['session_date'],
                    'date': r['session_date'],
                    'routine_name': r['routine_name'],
                    'max_load_kg': 0.0,
                    'max_load': 0.0,
                    'total_volume_kg': 0.0,
                    'total_volume': 0.0,
                    'total_reps': 0,
                    'sets_count': 0,
                    'sets_detail': []
                }
                sessions_order.append(w_id)

            s_entry = sessions_map[w_id]
            load_val = float(r['load'] or 0.0)
            reps_val = int(r['reps'] or 0)
            vol_val = round(load_val * reps_val, 2)

            if load_val > s_entry['max_load_kg']:
                s_entry['max_load_kg'] = round(load_val, 2)
                s_entry['max_load'] = round(load_val, 2)
            s_entry['total_volume_kg'] = round(s_entry['total_volume_kg'] + vol_val, 2)
            s_entry['total_volume'] = s_entry['total_volume_kg']
            s_entry['total_reps'] += reps_val
            s_entry['sets_count'] += 1
            s_entry['sets_detail'].append({
                'set': s_entry['sets_count'],
                'load': round(load_val, 2),
                'reps': reps_val,
                'rpe': float(r['rpe']) if r['rpe'] is not None else None
            })

        series = [sessions_map[wid] for wid in sessions_order]
        pr_load = max((pt['max_load_kg'] for pt in series), default=0.0)
        pr_volume = max((pt['total_volume_kg'] for pt in series), default=0.0)
        pr_reps = max((pt['total_reps'] for pt in series), default=0)

        return jsonify({
            'exercise': dict_from_row(ex_row),
            'period': period,
            'total_sessions': len(series),
            'summary': {
                'pr_max_load': pr_load,
                'pr_max_volume': pr_volume,
                'pr_max_reps': pr_reps,
                'sessions_count': len(series)
            },
            'records': {
                'max_load_kg': pr_load,
                'max_volume_kg': pr_volume,
                'max_reps': pr_reps
            },
            'series': series,
            'points': series
        })

    @app.route('/uploads/<path:filename>')
    def serve_uploaded_file(filename):
        import mimetypes
        mimetypes.add_type('image/webp', '.webp')
        mimetypes.add_type('image/heic', '.heic')
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    # ------------------- Frontend Static Fallback -------------------
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_frontend(path):
        if path.startswith('api/'):
            return jsonify({'status': 'error', 'error': 'Not found'}), 404
        frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
        target = os.path.join(frontend_dir, path)
        if path and os.path.exists(target) and not os.path.isdir(target):
            if path == 'manifest.webmanifest':
                resp = send_from_directory(frontend_dir, path, mimetype='application/manifest+json')
                resp.headers['Cache-Control'] = 'no-cache'
                return resp
            if path == 'sw.js':
                resp = send_from_directory(frontend_dir, path, mimetype='application/javascript')
                resp.headers['Service-Worker-Allowed'] = '/'
                resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                return resp
            return send_from_directory(frontend_dir, path)
        return send_from_directory(frontend_dir, 'index.html')

    return app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8001))
    app.run(host='127.0.0.1', port=port, debug=False)
