import os
from datetime import datetime, date
from flask import Flask, request, jsonify, g, send_from_directory
try:
    from backend.database import get_db_connection, init_db, dict_from_row
except ImportError:
    from database import get_db_connection, init_db, dict_from_row

def create_app(test_config=None):
    app = Flask(__name__)

    db_path = os.environ.get('NEXUS_DB', os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'nexus.db')))
    if test_config and 'DATABASE' in test_config:
        db_path = test_config['DATABASE']

    app.config['DATABASE'] = db_path

    # Initialize DB schema
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

    # CORS Headers for API if accessed from other origins in Tailnet
    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
        return response

    # ------------------- Health & Overview -------------------
    @app.route('/api/health', methods=['GET'])
    def health():
        return jsonify({'status': 'ok', 'app': 'Dream Hub', 'version': '1.0.0'})

    @app.route('/api/overview', methods=['GET'])
    def overview():
        conn = get_db()
        today = date.today().isoformat()
        current_month = datetime.now().strftime('%Y-%m')

        # Tasks counts
        pending_tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE status != 'done' AND status != 'archived'").fetchone()[0]
        urgent_tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE priority = 'urgent' AND status != 'done'").fetchone()[0]
        
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
            SELECT type, COALESCE(SUM(amount_cents), 0)
            FROM transactions
            WHERE date LIKE ?
            GROUP BY type
        """, (f"{current_month}%",)).fetchall()
        income_cents = 0
        expense_cents = 0
        for r in fin_rows:
            if r['type'] == 'income':
                income_cents = r[1]
            elif r['type'] == 'expense':
                expense_cents = r[1]
        
        # Ideas count
        active_ideas = conn.execute("SELECT COUNT(*) FROM ideas WHERE stage != 'archived'").fetchone()[0]

        return jsonify({
            'pending_tasks': pending_tasks,
            'urgent_tasks': urgent_tasks,
            'today_focus_minutes': today_focus_min,
            'today_pomodoro_sessions': today_sessions,
            'month_income_cents': income_cents,
            'month_expense_cents': expense_cents,
            'month_balance_cents': income_cents - expense_cents,
            'active_ideas': active_ideas
        })

    # ------------------- Tasks Module -------------------
    @app.route('/api/tasks', methods=['GET', 'POST'])
    def handle_tasks():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            title = (data.get('title') or '').strip()
            if not title:
                return jsonify({'error': 'Título é obrigatório'}), 400

            description = data.get('description', '').strip()
            status = data.get('status', 'todo')
            priority = data.get('priority', 'medium')
            due_date = data.get('due_date') or None
            category = data.get('category', 'Geral')
            estimated = int(data.get('estimated_pomodoros') or 1)
            pomodoro_duration = int(data.get('pomodoro_duration_minutes') or 25)
            now = datetime.now().isoformat()

            cur = conn.execute("""
                INSERT INTO tasks (title, description, status, priority, due_date, category, estimated_pomodoros, completed_pomodoros, pomodoro_duration_minutes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """, (title, description, status, priority, due_date, category, estimated, pomodoro_duration, now, now))
            conn.commit()
            new_id = cur.lastrowid
            task = conn.execute("SELECT * FROM tasks WHERE id = ?", (new_id,)).fetchone()
            return jsonify(dict_from_row(task)), 201

        # GET
        status = request.args.get('status')
        priority = request.args.get('priority')
        category = request.args.get('category')

        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, due_date ASC, id DESC"
        rows = conn.execute(query, params).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/tasks/<int:task_id>', methods=['GET', 'PUT', 'DELETE'])
    def task_detail(task_id):
        conn = get_db()
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            return jsonify({'error': 'Tarefa não encontrada'}), 404

        if request.method == 'GET':
            return jsonify(dict_from_row(task))

        if request.method == 'DELETE':
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            return jsonify({'success': True, 'deleted_id': task_id})

        # PUT
        data = request.get_json() or {}
        now = datetime.now().isoformat()
        current = dict_from_row(task)

        title = data.get('title', current['title'])
        description = data.get('description', current['description'])
        status = data.get('status', current['status'])
        priority = data.get('priority', current['priority'])
        due_date = data.get('due_date', current['due_date'])
        category = data.get('category', current['category'])
        estimated = data.get('estimated_pomodoros', current['estimated_pomodoros'])
        completed = data.get('completed_pomodoros', current['completed_pomodoros'])
        pomodoro_duration = data.get('pomodoro_duration_minutes', current.get('pomodoro_duration_minutes', 25))

        conn.execute("""
            UPDATE tasks
            SET title = ?, description = ?, status = ?, priority = ?, due_date = ?, category = ?, 
                estimated_pomodoros = ?, completed_pomodoros = ?, pomodoro_duration_minutes = ?, updated_at = ?
            WHERE id = ?
        """, (title, description, status, priority, due_date, category, estimated, completed, pomodoro_duration, now, task_id))
        conn.commit()
        updated = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return jsonify(dict_from_row(updated))

    # ------------------- Time / Pomodoro Module -------------------
    @app.route('/api/time/sessions', methods=['GET', 'POST'])
    def time_sessions():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            task_id = data.get('task_id')
            session_type = data.get('session_type', 'focus')
            duration_minutes = int(data.get('duration_minutes', 25))
            started_at = data.get('started_at', datetime.now().isoformat())
            ended_at = data.get('ended_at', datetime.now().isoformat())
            completed = int(data.get('completed', 1))
            notes = data.get('notes', '')

            cur = conn.execute("""
                INSERT INTO time_sessions (task_id, session_type, duration_minutes, started_at, ended_at, completed, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (task_id, session_type, duration_minutes, started_at, ended_at, completed, notes))
            conn.commit()

            # Increment task's pomodoro count if completed focus
            if task_id and completed == 1 and session_type == 'focus':
                conn.execute("""
                    UPDATE tasks 
                    SET completed_pomodoros = completed_pomodoros + 1, updated_at = ?
                    WHERE id = ?
                """, (datetime.now().isoformat(), task_id))
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

    # ------------------- Finance Module -------------------
    @app.route('/api/finance/transactions', methods=['GET', 'POST'])
    def transactions():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            description = (data.get('description') or '').strip()
            if not description:
                return jsonify({'error': 'Descrição é obrigatória'}), 400

            # Support amount_cents or amount in currency decimal
            if 'amount_cents' in data:
                amount_cents = int(data['amount_cents'])
            else:
                amount_val = float(data.get('amount', 0))
                amount_cents = int(round(amount_val * 100))

            if amount_cents <= 0:
                return jsonify({'error': 'Valor deve ser positivo'}), 400

            txn_type = data.get('type', 'expense')
            category = data.get('category', 'Outros')
            account = data.get('account', 'Carteira')
            txn_date = data.get('date', date.today().isoformat())
            is_settled = int(data.get('is_settled', 1))
            now = datetime.now().isoformat()

            cur = conn.execute("""
                INSERT INTO transactions (description, amount_cents, type, category, account, date, is_settled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (description, amount_cents, txn_type, category, account, txn_date, is_settled, now))
            conn.commit()

            new_id = cur.lastrowid
            txn = conn.execute("SELECT * FROM transactions WHERE id = ?", (new_id,)).fetchone()
            return jsonify(dict_from_row(txn)), 201

        # GET
        month = request.args.get('month') # YYYY-MM
        txn_type = request.args.get('type')
        category = request.args.get('category')

        query = "SELECT * FROM transactions WHERE 1=1"
        params = []
        if month:
            query += " AND date LIKE ?"
            params.append(f"{month}%")
        if txn_type:
            query += " AND type = ?"
            params.append(txn_type)
        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY date DESC, id DESC"
        rows = conn.execute(query, params).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/finance/transactions/<int:txn_id>', methods=['DELETE'])
    def delete_transaction(txn_id):
        conn = get_db()
        conn.execute("DELETE FROM transactions WHERE id = ?", (txn_id,))
        conn.commit()
        return jsonify({'success': True, 'deleted_id': txn_id})

    @app.route('/api/finance/summary', methods=['GET'])
    def finance_summary():
        conn = get_db()
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))

        rows = conn.execute("""
            SELECT type, category, COALESCE(SUM(amount_cents), 0) as total
            FROM transactions
            WHERE date LIKE ?
            GROUP BY type, category
        """, (f"{month}%",)).fetchall()

        total_income = 0
        total_expense = 0
        categories_breakdown = {}

        for r in rows:
            t = r['type']
            cat = r['category']
            tot = r['total']
            if t == 'income':
                total_income += tot
            else:
                total_expense += tot
                categories_breakdown[cat] = categories_breakdown.get(cat, 0) + tot

        return jsonify({
            'month': month,
            'total_income_cents': total_income,
            'total_expense_cents': total_expense,
            'net_balance_cents': total_income - total_expense,
            'categories_breakdown': categories_breakdown
        })

    # ------------------- Ideas Module -------------------
    @app.route('/api/ideas', methods=['GET', 'POST'])
    def handle_ideas():
        conn = get_db()
        if request.method == 'POST':
            data = request.get_json() or {}
            title = (data.get('title') or '').strip()
            if not title:
                return jsonify({'error': 'Título da ideia é obrigatório'}), 400

            content = data.get('content', '').strip()
            stage = data.get('stage', 'raw')
            tags = data.get('tags', '').strip()
            now = datetime.now().isoformat()

            cur = conn.execute("""
                INSERT INTO ideas (title, content, stage, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (title, content, stage, tags, now, now))
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
            query += " AND stage = ?"
            params.append(stage)
        if tag:
            query += " AND tags LIKE ?"
            params.append(f"%{tag}%")
        if q:
            query += " AND (title LIKE ? OR content LIKE ?)"
            params.extend([f"%{q}%", f"%{q}%"])

        query += " ORDER BY updated_at DESC, id DESC"
        rows = conn.execute(query, params).fetchall()
        return jsonify([dict_from_row(r) for r in rows])

    @app.route('/api/ideas/<int:idea_id>', methods=['GET', 'PUT', 'DELETE'])
    def idea_detail(idea_id):
        conn = get_db()
        idea = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        if not idea:
            return jsonify({'error': 'Ideia não encontrada'}), 404

        if request.method == 'GET':
            return jsonify(dict_from_row(idea))

        if request.method == 'DELETE':
            conn.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
            conn.commit()
            return jsonify({'success': True, 'deleted_id': idea_id})

        # PUT
        data = request.get_json() or {}
        now = datetime.now().isoformat()
        current = dict_from_row(idea)

        title = data.get('title', current['title'])
        content = data.get('content', current['content'])
        stage = data.get('stage', current['stage'])
        tags = data.get('tags', current['tags'])

        conn.execute("""
            UPDATE ideas
            SET title = ?, content = ?, stage = ?, tags = ?, updated_at = ?
            WHERE id = ?
        """, (title, content, stage, tags, now, idea_id))
        conn.commit()
        updated = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        return jsonify(dict_from_row(updated))

    # ------------------- Frontend Static Fallback -------------------
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_frontend(path):
        if path.startswith('api/'):
            return jsonify({'error': 'Not found'}), 404
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
