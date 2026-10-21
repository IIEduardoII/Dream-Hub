import unittest
import json
import os
import io
import shutil
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
        self.upload_dir = tempfile.mkdtemp(prefix='dreamhub_uploads_')
        self.app = create_app({
            'TESTING': True,
            'DATABASE': self.db_path,
            'UPLOAD_FOLDER': self.upload_dir
        })
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
        for ext in ('-wal', '-shm'):
            p = f"{self.db_path}{ext}"
            if os.path.exists(p):
                os.unlink(p)
        if os.path.exists(self.upload_dir):
            shutil.rmtree(self.upload_dir, ignore_errors=True)

    # --- Health, Version 1.2.0 & SQLite Pragmas ---
    def test_health_and_version_1_2(self):
        res = self.client.get('/api/health')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('app'), 'Dream Hub')
        self.assertEqual(data.get('version'), '1.2.0')

    def test_sqlite_pragmas_enforced(self):
        conn = get_db(self.db_path)
        try:
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            temp_store = conn.execute("PRAGMA temp_store").fetchone()[0]
            cache_size = conn.execute("PRAGMA cache_size").fetchone()[0]
            self.assertEqual(fk, 1)
            self.assertEqual(busy, 5000)
            self.assertEqual(temp_store, 2)
            self.assertEqual(cache_size, -8000)
        finally:
            conn.close()

    # --- Cockpit "Meu Dia" ([RF01]) & Overview ---
    def test_cockpit_today_and_overview(self):
        today_str = date.today().isoformat()
        self.client.post('/api/tasks', json={
            'title': 'Tarefa de Hoje',
            'priority': 'high',
            'due_date': today_str
        })
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
        self.client.post('/api/ideas', json={
            'title': 'Ideia para o Cockpit',
            'tags': 'cockpit,produtividade'
        })

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

    def test_frontend_serving(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Dream Hub', res.data)

        res_css = self.client.get('/css/style.css')
        self.assertEqual(res_css.status_code, 200)
        self.assertIn(b'--bg-canvas', res_css.data)

    # --- Tasks Module & Automatic Recurrence ---
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
        task_id = task['id']

        res = self.client.put(f'/api/tasks/{task_id}', json={
            'status': 'in_progress',
            'completed_pomodoros': 1,
            'pomodoro_duration_minutes': 50
        })
        self.assertEqual(res.status_code, 200)
        updated = res.get_json()
        self.assertEqual(updated['status'], 'in_progress')

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
        task_id = res.get_json()['id']

        patch_res = self.client.patch(f'/api/tasks/{task_id}/status', json={'status': 'concluida'})
        self.assertEqual(patch_res.status_code, 200)
        patch_data = patch_res.get_json()

        # Solução 1: Tarefa Mestre (Reciclagem Instantânea sem duplicação no Kanban)
        self.assertTrue(patch_data.get('streak_incremented'))
        self.assertEqual(patch_data.get('streak_count'), 1)
        self.assertEqual(patch_data['due_date'], '2026-10-21')
        self.assertEqual(patch_data['status'], 'todo')

        # Garante que existe apenas 1 card no Kanban (sem duplicação de cards)
        tasks_list = self.client.get('/api/tasks').get_json()
        self.assertEqual(len(tasks_list), 1)
        self.assertEqual(tasks_list[0]['id'], task_id)
        self.assertEqual(tasks_list[0]['streak_count'], 1)

        # Garante que o histórico silencioso foi registrado em task_completions
        comp_res = self.client.get(f'/api/tasks/{task_id}/completions')
        self.assertEqual(comp_res.status_code, 200)
        completions = comp_res.get_json()
        self.assertEqual(len(completions), 1)

    # --- Time & Pomodoro Module ---
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

    # --- Ideas & Atomic Conversion to Task ---
    def test_idea_atomic_conversion_to_task(self):
        idea_res = self.client.post('/api/ideas', json={
            'title': 'Automatizar backup no Termux',
            'content': 'Criar rotina cron para rodar backup.sh diariamente',
            'stage': 'raw',
            'tags': 'termux,sqlite'
        })
        self.assertEqual(idea_res.status_code, 201)
        idea_id = idea_res.get_json()['id']

        conv_res = self.client.post(f'/api/ideas/{idea_id}/convert', json={
            'priority': 'high',
            'category': 'Infraestrutura'
        })
        self.assertEqual(conv_res.status_code, 201)
        conv_data = conv_res.get_json()
        self.assertEqual(conv_data['idea']['converted_task_id'], conv_data['task']['id'])
        self.assertEqual(conv_data['idea']['status'], 'convertida')

    # --- v1.2 PONTO 1: Decentralized File Attachments ([RF01], [RNF01], RN01) ---
    def test_attachments_upload_list_and_orphan_cleanup(self):
        # Create a transaction to attach a receipt PDF
        txn_res = self.client.post('/api/finance/transactions', json={
            'description': 'Conta de Energia',
            'amount': 180.00,
            'type': 'despesa',
            'category': 'Moradia',
            'date': '2026-10-20'
        })
        txn_id = txn_res.get_json()['id']

        # Upload a simulated PDF file via multipart/form-data
        pdf_bytes = b'%PDF-1.4 simulated receipt content for Dream Hub v1.2'
        upload_res = self.client.post(
            '/api/uploads',
            data={
                'entity_type': 'transaction',
                'entity_id': str(txn_id),
                'file': (io.BytesIO(pdf_bytes), 'comprovante_energia.pdf', 'application/pdf')
            },
            content_type='multipart/form-data'
        )
        self.assertEqual(upload_res.status_code, 201)
        att = upload_res.get_json()
        att_id = att['id']
        self.assertEqual(att['filename'], 'comprovante_energia.pdf')
        self.assertEqual(att['file_size'], len(pdf_bytes))
        self.assertEqual(att['entity_type'], 'transaction')
        self.assertEqual(att['entity_id'], txn_id)

        # Verify physical file exists on disk in upload_dir
        physical_path = os.path.join(self.upload_dir, os.path.basename(att['storage_path']))
        self.assertTrue(os.path.exists(physical_path))

        # List attachments for this transaction
        list_res = self.client.get(f'/api/attachments/transaction/{txn_id}')
        self.assertEqual(list_res.status_code, 200)
        att_list = list_res.get_json()
        self.assertEqual(len(att_list), 1)
        self.assertEqual(att_list[0]['id'], att_id)

        # Download attachment file
        dl_res = self.client.get(f'/api/attachments/file/{att_id}')
        self.assertEqual(dl_res.status_code, 200)
        self.assertEqual(dl_res.data, pdf_bytes)
        dl_res.close()

        # Delete attachment and verify physical file is removed from disk (RN01)
        del_res = self.client.delete(f'/api/attachments/{att_id}')
        self.assertEqual(del_res.status_code, 200)
        self.assertFalse(os.path.exists(physical_path))
        self.assertEqual(len(self.client.get(f'/api/attachments/transaction/{txn_id}').get_json()), 0)

    # --- v1.2 PONTO 2: Goals & Milestones Module ([RF02], [RF03], RN02) ---
    def test_goals_crud_and_progress(self):
        # 1. Create a Monetary Goal (e.g. Save R$ 5000 for Emergency Fund)
        g1_res = self.client.post('/api/goals', json={
            'title': 'Reserva de Segurança',
            'description': 'Guardar valor para emergências',
            'category': 'financas',
            'goal_type': 'monetaria',
            'target_value': 5000.00,
            'current_value': 1000.00,
            'unit': 'R$',
            'deadline': '2026-12-31'
        })
        self.assertEqual(g1_res.status_code, 201)
        g1 = g1_res.get_json()
        self.assertEqual(g1['progress_percent'], 20.0)
        g1_id = g1['id']

        # 2. Create a Qualitative Study Goal ("Estudar até aprender" - target_value = None)
        g2_res = self.client.post('/api/goals', json={
            'title': 'Dominar Arquitetura Linux e Redes',
            'description': 'Estudar até aprender profundamente',
            'category': 'estudos',
            'goal_type': 'qualitativa',
            'unit': 'tópicos'
        })
        self.assertEqual(g2_res.status_code, 201)
        g2 = g2_res.get_json()
        self.assertEqual(g2['goal_type'], 'qualitativa')
        self.assertEqual(g2['status'], 'em_andamento')

        # 3. Increment progress via PATCH /api/goals/<id>/progress
        patch_res = self.client.patch(f'/api/goals/{g1_id}/progress', json={'delta': 1500.00})
        self.assertEqual(patch_res.status_code, 200)
        updated_g1 = patch_res.get_json()
        self.assertEqual(updated_g1['current_value'], 2500.0)
        self.assertEqual(updated_g1['progress_percent'], 50.0)

        # 4. Link a transaction to monetary goal (RN02) -> auto-increments goal
        self.client.post('/api/finance/transactions', json={
            'description': 'Aporte Reserva',
            'amount': 2500.00,
            'type': 'receita',
            'category': 'Investimento',
            'date': '2026-10-20',
            'goal_id': g1_id
        })
        goals_list = self.client.get('/api/goals').get_json()
        g1_after = next(g for g in goals_list if g['id'] == g1_id)
        self.assertEqual(g1_after['current_value'], 5000.0)
        self.assertEqual(g1_after['progress_percent'], 100.0)
        self.assertEqual(g1_after['status'], 'alcancada')

    # --- v1.2 PONTO 3: Knowledge Base / Notes Mode ([RF04]) ---
    def test_notes_knowledge_base_and_cascade_cleanup(self):
        # Create a Markdown note
        n_res = self.client.post('/api/notes', json={
            'title': 'Guia de Comandos Termux & Runit',
            'content': '# Comandos Runit\n\n- `sv up nexus-api`\n- `sv status nexus-nginx`',
            'folder': 'Servidores',
            'tags': 'termux,linux,runit',
            'is_pinned': True
        })
        self.assertEqual(n_res.status_code, 201)
        note = n_res.get_json()
        note_id = note['id']
        self.assertEqual(note['folder'], 'Servidores')
        self.assertEqual(note['is_pinned'], 1)

        # Attach a file to the note
        upload_res = self.client.post(
            '/api/uploads',
            data={
                'entity_type': 'note',
                'entity_id': str(note_id),
                'file': (io.BytesIO(b'config sample'), 'nginx.txt', 'text/plain')
            },
            content_type='multipart/form-data'
        )
        self.assertEqual(upload_res.status_code, 201)
        att_storage = upload_res.get_json()['storage_path']
        physical_path = os.path.join(self.upload_dir, os.path.basename(att_storage))
        self.assertTrue(os.path.exists(physical_path))

        # Filter notes by folder
        notes_folder = self.client.get('/api/notes?folder=Servidores').get_json()
        self.assertEqual(len(notes_folder), 1)

        # Update note
        put_res = self.client.put(f'/api/notes/{note_id}', json={
            'title': 'Guia Completo Termux & Runit',
            'is_pinned': False
        })
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.get_json()['title'], 'Guia Completo Termux & Runit')

        # Delete note -> should also delete linked attachment from disk!
        del_res = self.client.delete(f'/api/notes/{note_id}')
        self.assertEqual(del_res.status_code, 200)
        self.assertFalse(os.path.exists(physical_path))

    # --- v1.2 PONTO 4: Recurring Rules Engine & Cashflow Projection ([RF05], [RF06], [RF07], RN03) ---
    def test_recurring_rules_and_projection(self):
        # 1. Create a recurring income rule (day 5) and a future-day fixed expense rule (day 25)
        r_inc = self.client.post('/api/finance/recurring-rules', json={
            'type': 'receita',
            'description': 'Salário Fixo',
            'amount': 5000.00,
            'category': 'Salário',
            'frequency': 'mensal',
            'day_of_month': 5,
            'start_date': '2026-10-05'
        })
        self.assertEqual(r_inc.status_code, 201)

        r_exp = self.client.post('/api/finance/recurring-rules', json={
            'type': 'despesa',
            'description': 'Aluguel + Condomínio',
            'amount': 1500.00,
            'category': 'Moradia',
            'frequency': 'mensal',
            'day_of_month': 25,
            'start_date': '2026-10-25'
        })
        self.assertEqual(r_exp.status_code, 201)
        exp_rule_id = r_exp.get_json()['id']

        # 2. Immediately visible in GET /api/finance/recurring-rules even before day 25!
        rules = self.client.get('/api/finance/recurring-rules').get_json()
        self.assertEqual(len(rules), 2)

        # 3. Edit rule value and due day via PUT /api/finance/recurring-rules/<id> ([RF06], RN03)
        put_res = self.client.put(f'/api/finance/recurring-rules/{exp_rule_id}', json={
            'amount': 1600.00,
            'day_of_month': 28,
            'apply_current_month': True
        })
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.get_json()['amount'], 1600.0)
        self.assertEqual(put_res.get_json()['day_of_month'], 28)

        # 4. Check 3-month Cashflow Projection (D+30, D+60, D+90) ([RF07])
        proj_res = self.client.get('/api/finance/projection?months=3')
        self.assertEqual(proj_res.status_code, 200)
        proj = proj_res.get_json()
        self.assertEqual(len(proj['projections']), 3)
        self.assertEqual(proj['projections'][0]['projected_income_cents'], 500000)
        self.assertEqual(proj['projections'][0]['projected_expense_cents'], 160000)
        self.assertEqual(proj['projections'][0]['projected_net_cents'], 340000)

        # 5. Pause rule via PATCH /api/finance/recurring-rules/<id> ([RF06])
        patch_res = self.client.patch(f'/api/finance/recurring-rules/{exp_rule_id}', json={'is_active': False})
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.get_json()['is_active'], 0)

        # Projection after pausing expense rule should show 0 expense
        proj_after = self.client.get('/api/finance/projection?months=1').get_json()
        self.assertEqual(proj_after['projections'][0]['projected_expense_cents'], 0)

    # --- Hot Backup & Export ---
    def test_system_hot_backup_and_export(self):
        self.client.post('/api/tasks', json={'title': 'Tarefa Exportável', 'priority': 'medium'})
        backup_res = self.client.get('/api/system/backup')
        self.assertEqual(backup_res.status_code, 200)
        self.assertTrue(backup_res.data.startswith(b'SQLite format 3'))
    def test_task_archive_and_auto_archive(self):
        # Create regular task and complete it
        res = self.client.post('/api/tasks', json={'title': 'Tarefa Regular Feita', 'priority': 'low'})
        task_id = res.get_json()['id']
        self.client.patch(f'/api/tasks/{task_id}/status', json={'status': 'done'})

        # Archive manually
        arc_res = self.client.post(f'/api/tasks/{task_id}/archive')
        self.assertEqual(arc_res.status_code, 200)
        self.assertEqual(arc_res.get_json()['status'], 'archived')

        # Regular task list should not include archived
        active_tasks = self.client.get('/api/tasks').get_json()
        self.assertEqual(len([t for t in active_tasks if t['id'] == task_id]), 0)

        # Archived endpoint should list it
        archived_tasks = self.client.get('/api/tasks?status=archived').get_json()
        self.assertTrue(any(t['id'] == task_id for t in archived_tasks))

        # Unarchive
        unarc_res = self.client.post(f'/api/tasks/{task_id}/archive')
        self.assertEqual(unarc_res.status_code, 200)
        self.assertEqual(unarc_res.get_json()['status'], 'todo')

if __name__ == '__main__':
    unittest.main()
