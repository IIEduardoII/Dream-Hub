import unittest
import json
import os
import tempfile
import sys

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

    # --- Health & Overview ---
    def test_health(self):
        res = self.client.get('/api/health')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('app'), 'Dream Hub')

    def test_overview(self):
        res = self.client.get('/api/overview')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('pending_tasks', data)
        self.assertIn('today_focus_minutes', data)
        self.assertIn('month_balance_cents', data)
        self.assertIn('active_ideas', data)

    def test_frontend_serving(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Dream Hub', res.data)

        res_css = self.client.get('/css/style.css')
        self.assertEqual(res_css.status_code, 200)
        self.assertIn(b'--bg-canvas', res_css.data)

    # --- Tasks Module ---
    def test_tasks_crud(self):
        # 1. Create Task
        payload = {
            'title': 'Comprar suporte articulado',
            'description': 'Suporte para o celular servidor',
            'priority': 'high',
            'category': 'Infraestrutura',
            'due_date': '2026-10-25',
            'estimated_pomodoros': 2,
            'pomodoro_duration_minutes': 45
        }
        res = self.client.post('/api/tasks', json=payload)
        self.assertEqual(res.status_code, 201)
        task = res.get_json()
        self.assertEqual(task['title'], payload['title'])
        self.assertEqual(task['status'], 'todo')
        self.assertEqual(task['priority'], 'high')
        self.assertEqual(task['pomodoro_duration_minutes'], 45)
        task_id = task['id']

        # 2. Get Tasks
        res = self.client.get('/api/tasks')
        self.assertEqual(res.status_code, 200)
        tasks = res.get_json()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]['id'], task_id)
        self.assertEqual(tasks[0]['pomodoro_duration_minutes'], 45)

        # 3. Update Task Status & Pomodoros & Custom Duration
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

        # 4. Filter by status
        res = self.client.get('/api/tasks?status=in_progress')
        self.assertEqual(len(res.get_json()), 1)
        res = self.client.get('/api/tasks?status=done')
        self.assertEqual(len(res.get_json()), 0)

        # 5. Delete Task
        res = self.client.delete(f'/api/tasks/{task_id}')
        self.assertEqual(res.status_code, 200)
        res = self.client.get('/api/tasks')
        self.assertEqual(len(res.get_json()), 0)

    # --- Time & Pomodoro Module ---
    def test_time_sessions(self):
        # Create a task to link
        t_res = self.client.post('/api/tasks', json={'title': 'Estudar Rust', 'estimated_pomodoros': 4})
        task_id = t_res.get_json()['id']

        # Log a completed focus session
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
        session = res.get_json()
        self.assertEqual(session['duration_minutes'], 25)

        # Task completed_pomodoros should be incremented
        task_check = self.client.get(f'/api/tasks/{task_id}').get_json()
        self.assertEqual(task_check['completed_pomodoros'], 1)

        # Check time stats
        stats_res = self.client.get('/api/time/stats')
        self.assertEqual(stats_res.status_code, 200)
        stats = stats_res.get_json()
        self.assertGreaterEqual(stats['total_focus_minutes'], 25)
        self.assertGreaterEqual(stats['completed_sessions'], 1)

    # --- Finance Module ---
    def test_finance_module(self):
        # 1. Add Income
        inc_data = {
            'description': 'Salário Mensal',
            'amount_cents': 500000, # R$ 5.000,00
            'type': 'income',
            'category': 'Salário',
            'account': 'Banco',
            'date': '2026-10-05',
            'is_settled': 1
        }
        res = self.client.post('/api/finance/transactions', json=inc_data)
        self.assertEqual(res.status_code, 201)
        t_income = res.get_json()

        # 2. Add Expense
        exp_data = {
            'description': 'Supermercado',
            'amount_cents': 35000, # R$ 350,00
            'type': 'expense',
            'category': 'Alimentação',
            'account': 'Cartão de Crédito',
            'date': '2026-10-10',
            'is_settled': 1
        }
        res = self.client.post('/api/finance/transactions', json=exp_data)
        self.assertEqual(res.status_code, 201)

        # 3. Summary check
        res = self.client.get('/api/finance/summary?month=2026-10')
        self.assertEqual(res.status_code, 200)
        summary = res.get_json()
        self.assertEqual(summary['total_income_cents'], 500000)
        self.assertEqual(summary['total_expense_cents'], 35000)
        self.assertEqual(summary['net_balance_cents'], 465000)

        # 4. List transactions
        res = self.client.get('/api/finance/transactions')
        self.assertEqual(len(res.get_json()), 2)

    # --- Ideas Module ---
    def test_ideas_crud(self):
        # 1. Create Idea
        idea_payload = {
            'title': 'Automação de Backup via Telegram',
            'content': 'Criar bot no Telegram para notificar quando o backup terminar no Drive.',
            'stage': 'evaluating',
            'tags': 'termux,backup,python'
        }
        res = self.client.post('/api/ideas', json=idea_payload)
        self.assertEqual(res.status_code, 201)
        idea = res.get_json()
        self.assertEqual(idea['stage'], 'evaluating')
        idea_id = idea['id']

        # 2. Filter & Search
        res = self.client.get('/api/ideas?stage=evaluating')
        self.assertEqual(len(res.get_json()), 1)

        res = self.client.get('/api/ideas?q=Telegram')
        self.assertEqual(len(res.get_json()), 1)

        # 3. Update Idea
        res = self.client.put(f'/api/ideas/{idea_id}', json={'stage': 'in_action'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['stage'], 'in_action')

        # 4. Delete
        res = self.client.delete(f'/api/ideas/{idea_id}')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(self.client.get('/api/ideas').get_json()), 0)

if __name__ == '__main__':
    unittest.main()
