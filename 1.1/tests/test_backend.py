import unittest
import json
import os
import tempfile
import sqlite3
import sys
from datetime import date, timedelta

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app import create_app
from backend.database import get_db, init_db

class NexusBackendTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.app = create_app({'TESTING': True, 'DATABASE': self.db_path})
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
        wal_path = f"{self.db_path}-wal"
        shm_path = f"{self.db_path}-shm"
        if os.path.exists(wal_path):
            os.unlink(wal_path)
        if os.path.exists(shm_path):
            os.unlink(shm_path)

    # --- Health, Version 1.1.0 & SQLite Pragmas ---
    def test_health_and_version_1_1(self):
        res = self.client.get('/api/health')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('app'), 'Dream Hub')
        self.assertEqual(data.get('version'), '1.1.0')

    def test_sqlite_pragmas_enforced(self):
        conn = get_db(self.db_path)
        try:
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            temp_store = conn.execute("PRAGMA temp_store").fetchone()[0]
            cache_size = conn.execute("PRAGMA cache_size").fetchone()[0]
            self.assertEqual(fk, 1)
            self.assertEqual(busy, 5000)
            self.assertEqual(temp_store, 2) # 2 = MEMORY
            self.assertEqual(cache_size, -8000)
        finally:
            conn.close()

    # --- Cockpit "Meu Dia" ([RF01]) & Overview ---
    def test_cockpit_today_and_overview(self):
        today_str = date.today().isoformat()
        # Create a task due today
        self.client.post('/api/tasks', json={
            'title': 'Tarefa de Hoje',
            'priority': 'high',
            'due_date': today_str
        })
        # Create a recurring income and an expense
        self.client.post('/api/finance/transactions', json={
            'description': 'Depósito Mensal Fixo',
            'amount': 3000.00,
            'type': 'receita',
            'category': 'Salário',
            'date': today_str,
            'is_recurring': True,
            'recurrence': 'mensal'
        })
        self.client.post('/api/finance/transactions', json={
            'description': 'Café Expresso',
            'amount': 15.50,
            'type': 'despesa',
            'category': 'Alimentação',
            'date': today_str
        })
        # Create an idea
        self.client.post('/api/ideas', json={
            'title': 'Ideia para o Cockpit',
            'tags': 'cockpit,produtividade'
        })

        # Test /api/cockpit/today
        res = self.client.get('/api/cockpit/today')
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload.get('status'), 'success')
        data = payload.get('data', payload)
        self.assertEqual(len(data['tasks_due_today']), 1)
        self.assertEqual(data['tasks_due_today'][0]['title'], 'Tarefa de Hoje')
        self.assertEqual(data['month_income_cents'], 300000)
        self.assertEqual(data['month_expense_cents'], 1550)
        self.assertEqual(data['month_balance_cents'], 298450)
        self.assertEqual(data['active_ideas'], 1)

        # Test backward-compatible /api/overview
        res_ov = self.client.get('/api/overview')
        self.assertEqual(res_ov.status_code, 200)
        ov = res_ov.get_json()
        self.assertEqual(ov['pending_tasks'], 1)
        self.assertEqual(ov['tasks_due_today_count'], 1)
        self.assertEqual(ov['month_balance_cents'], 298450)

    def test_frontend_serving(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Dream Hub', res.data)

        res_css = self.client.get('/css/style.css')
        self.assertEqual(res_css.status_code, 200)
        self.assertIn(b'--bg-canvas', res_css.data)

    # --- Tasks Module & Automatic Recurrence ([RF06], [RF07], RN04) ---
    def test_tasks_crud(self):
        payload = {
            'title': 'Comprar suporte articulado',
            'description': 'Suporte para o celular servidor',
            'priority': 'high',
            'category': 'Infraestrutura',
            'due_date': '2026-10-25',
            'estimated_pomodoros': 2,
            'pomodoro_duration_minutes': 45,
            'recurrence': 'nenhuma'
        }
        res = self.client.post('/api/tasks', json=payload)
        self.assertEqual(res.status_code, 201)
        task = res.get_json()
        self.assertEqual(task['title'], payload['title'])
        self.assertEqual(task['status'], 'todo')
        self.assertEqual(task['priority'], 'high')
        self.assertEqual(task['pomodoro_duration_minutes'], 45)
        task_id = task['id']

        # Get Tasks
        res = self.client.get('/api/tasks')
        self.assertEqual(res.status_code, 200)
        tasks = res.get_json()
        self.assertEqual(len(tasks), 1)

        # Update Task Status & Pomodoros & Custom Duration
        res = self.client.put(f'/api/tasks/{task_id}', json={
            'status': 'in_progress',
            'completed_pomodoros': 1,
            'pomodoro_duration_minutes': 50
        })
        self.assertEqual(res.status_code, 200)
        updated = res.get_json()
        self.assertEqual(updated['status'], 'in_progress')
        self.assertEqual(updated['completed_pomodoros'], 1)
        self.assertEqual(updated['pomodoro_duration_minutes'], 50)

        # Delete Task
        res = self.client.delete(f'/api/tasks/{task_id}')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(self.client.get('/api/tasks').get_json()), 0)

    def test_task_automatic_recurrence_on_completion(self):
        base_date = '2026-10-20'
        res = self.client.post('/api/tasks', json={
            'title': 'Backup Diário de Estudo',
            'priority': 'alta',
            'due_date': base_date,
            'recurrence': 'diaria',
            'pomodoro_duration_minutes': 30
        })
        self.assertEqual(res.status_code, 201)
        task = res.get_json()
        task_id = task['id']
        self.assertEqual(task['recurrence'], 'diaria')

        # Complete via PATCH /api/tasks/<id>/status
        patch_res = self.client.patch(f'/api/tasks/{task_id}/status', json={'status': 'concluida'})
        self.assertEqual(patch_res.status_code, 200)
        patch_data = patch_res.get_json()
        self.assertEqual(patch_data['status'], 'done')
        self.assertIsNotNone(patch_data.get('completed_at'))
        self.assertIsNotNone(patch_data.get('next_recurring_task'))
        self.assertEqual(patch_data['next_recurring_task']['due_date'], '2026-10-21')
        self.assertEqual(patch_data['next_recurring_task']['status'], 'todo')
        self.assertEqual(patch_data['next_recurring_task']['recurrence'], 'diaria')

        # Verify total tasks in DB is now 2 (1 done, 1 todo for D+1)
        all_tasks = self.client.get('/api/tasks').get_json()
        self.assertEqual(len(all_tasks), 2)

    # --- Time & Pomodoro Module ([RF03], [RF05], RN03) ---
    def test_time_sessions(self):
        t_res = self.client.post('/api/tasks', json={'title': 'Estudar Rust', 'estimated_pomodoros': 4})
        task_id = t_res.get_json()['id']

        session_data = {
            'task_id': task_id,
            'session_type': 'focus',
            'duration_minutes': 25,
            'started_at': '2026-10-18T10:00:00',
            'ended_at': '2026-10-18T10:25:00',
            'completed': 1,
            'notes': 'Primeiro bloco de leitura'
        }
        res = self.client.post('/api/time/sessions', json=session_data)
        self.assertEqual(res.status_code, 201)

        task_check = self.client.get(f'/api/tasks/{task_id}').get_json()
        self.assertEqual(task_check['completed_pomodoros'], 1)

    # --- Finance Module & Recurring Transactions/Deposits ([RF08], [RF09], [RF10]) ---
    def test_finance_and_recurring_transactions(self):
        # 1. Create a recurring monthly deposit (income) and recurring monthly expense in 2026-10
        res_inc = self.client.post('/api/finance/transactions', json={
            'description': 'Salário Recorrente',
            'amount_cents': 500000,
            'type': 'income',
            'category': 'Salário',
            'account': 'Conta Corrente',
            'date': '2026-10-05',
            'is_recurring': 1,
            'recurrence': 'mensal'
        })
        self.assertEqual(res_inc.status_code, 201)
        inc_txn = res_inc.get_json()
        self.assertEqual(inc_txn['is_recurring'], 1)
        self.assertEqual(inc_txn['recurrence'], 'mensal')

        res_exp = self.client.post('/api/finance/transactions', json={
            'description': 'Internet Fibra Fixa',
            'amount_cents': 12000,
            'type': 'expense',
            'category': 'Moradia',
            'account': 'Conta Corrente',
            'date': '2026-10-10',
            'is_recurring': 1,
            'recurrence': 'mensal'
        })
        self.assertEqual(res_exp.status_code, 201)

        # 2. Check 2026-10 summary
        sum_oct = self.client.get('/api/finance/summary?month=2026-10').get_json()
        self.assertEqual(sum_oct['total_income_cents'], 500000)
        self.assertEqual(sum_oct['total_expense_cents'], 12000)
        self.assertEqual(sum_oct['net_balance_cents'], 488000)
        self.assertEqual(sum_oct['recurring_income_cents'], 500000)
        self.assertEqual(sum_oct['recurring_expense_cents'], 12000)

        # 3. Query next month (2026-11) -> recurring transactions should auto-materialize once!
        txns_nov = self.client.get('/api/finance/transactions?month=2026-11').get_json()
        self.assertEqual(len(txns_nov), 2)
        sum_nov = self.client.get('/api/finance/summary?month=2026-11').get_json()
        self.assertEqual(sum_nov['total_income_cents'], 500000)
        self.assertEqual(sum_nov['total_expense_cents'], 12000)
        self.assertEqual(sum_nov['net_balance_cents'], 488000)

        # Query 2026-11 again -> idempotent (still 2 transactions, no duplicates)
        txns_nov_again = self.client.get('/api/finance/transactions?month=2026-11').get_json()
        self.assertEqual(len(txns_nov_again), 2)

    # --- Ideas & Atomic Conversion to Task ([RF11], [RF12], RN02) ---
    def test_idea_atomic_conversion_to_task(self):
        idea_res = self.client.post('/api/ideas', json={
            'title': 'Automatizar backup no Termux',
            'content': 'Criar rotina cron para rodar backup.sh diariamente',
            'stage': 'raw',
            'tags': 'termux,sqlite'
        })
        self.assertEqual(idea_res.status_code, 201)
        idea_id = idea_res.get_json()['id']

        # Convert idea to task atomically
        conv_res = self.client.post(f'/api/ideas/{idea_id}/convert', json={
            'priority': 'high',
            'category': 'Infraestrutura'
        })
        self.assertEqual(conv_res.status_code, 201)
        conv_data = conv_res.get_json()
        self.assertIn('task', conv_data)
        self.assertIn('idea', conv_data)

        created_task = conv_data['task']
        updated_idea = conv_data['idea']

        self.assertEqual(created_task['title'], 'Automatizar backup no Termux')
        self.assertEqual(created_task['description'], 'Criar rotina cron para rodar backup.sh diariamente')
        self.assertEqual(updated_idea['converted_task_id'], created_task['id'])
        self.assertEqual(updated_idea['status'], 'convertida')
        self.assertEqual(updated_idea['stage'], 'in_action')

    # --- Hot Backup ([RF14]) & Data Export CSV/JSON ([RF15]) ---
    def test_system_hot_backup_and_export(self):
        self.client.post('/api/tasks', json={'title': 'Tarefa Exportável', 'priority': 'medium'})
        self.client.post('/api/finance/transactions', json={
            'description': 'Livro Técnico',
            'amount_cents': 8900,
            'type': 'expense',
            'category': 'Educação',
            'date': '2026-10-19'
        })

        # 1. Hot SQLite backup
        backup_res = self.client.get('/api/system/backup')
        self.assertEqual(backup_res.status_code, 200)
        self.assertTrue(backup_res.data.startswith(b'SQLite format 3'))

        # 2. Export CSV
        csv_res = self.client.get('/api/system/export?module=finance&format=csv')
        self.assertEqual(csv_res.status_code, 200)
        self.assertIn('Livro Técnico', csv_res.data.decode('utf-8-sig'))

        # 3. Export JSON
        json_res = self.client.get('/api/system/export?module=tasks&format=json')
        self.assertEqual(json_res.status_code, 200)
        exported_tasks = json_res.get_json()
        self.assertEqual(len(exported_tasks['tasks']), 1)
        self.assertEqual(exported_tasks['tasks'][0]['title'], 'Tarefa Exportável')

if __name__ == '__main__':
    unittest.main()
