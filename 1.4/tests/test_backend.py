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

    # --- Health, Version 1.4.0 & SQLite Pragmas ---
    def test_health_and_version_1_3(self):
        res = self.client.get('/api/health')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('app'), 'Dream Hub')
        self.assertEqual(data.get('version'), '1.4.0')

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
        # 1. Test creation and deletion of a draft/idea
        draft_res = self.client.post('/api/ideas', json={
            'title': 'Rascunho descartável',
            'content': 'Apenas uma nota para testar exclusão de rascunhos',
            'stage': 'raw',
            'tags': 'rascunho,teste'
        })
        self.assertEqual(draft_res.status_code, 201)
        draft_id = draft_res.get_json()['id']

        del_res = self.client.delete(f'/api/ideas/{draft_id}')
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.get_json()['status'], 'success')
        self.assertEqual(self.client.get(f'/api/ideas/{draft_id}').status_code, 404)

        # 2. Create an idea to convert
        idea_res = self.client.post('/api/ideas', json={
            'title': 'Automatizar backup no Termux',
            'content': 'Criar rotina cron para rodar backup.sh diariamente',
            'stage': 'raw',
            'tags': 'termux,sqlite'
        })
        self.assertEqual(idea_res.status_code, 201)
        idea_id = idea_res.get_json()['id']

        # Verify it is counted in cockpit before conversion
        cockpit_before = self.client.get('/api/cockpit/today').get_json()
        self.assertGreaterEqual(cockpit_before.get('active_ideas', 0), 1)

        conv_res = self.client.post(f'/api/ideas/{idea_id}/convert', json={
            'priority': 'high',
            'category': 'Infraestrutura'
        })
        self.assertEqual(conv_res.status_code, 201)
        conv_data = conv_res.get_json()
        self.assertEqual(conv_data['idea']['converted_task_id'], conv_data['task']['id'])
        self.assertEqual(conv_data['idea']['status'], 'convertida')
        self.assertEqual(conv_data['idea']['stage'], 'in_action')

        # Verify it disappeared from Cockpit active ideas and recent ideas
        cockpit_after = self.client.get('/api/cockpit/today').get_json()
        self.assertEqual(cockpit_after.get('active_ideas', 0), 0)
        self.assertNotIn(idea_id, [i['id'] for i in cockpit_after.get('recent_ideas', [])])

        # Verify frontend exports deleteIdea and deleteCurrentModalIdea, and modal has delete button
        with open('frontend/js/app.js', 'r', encoding='utf-8') as f:
            app_js = f.read()
            self.assertIn('deleteIdea,', app_js)
            self.assertIn('deleteCurrentModalIdea,', app_js)
            self.assertIn('deleteCurrentModalIdea()', app_js)
            self.assertIn("!isIdeaConverted(i) && i.stage !== 'archived'", app_js)

        with open('frontend/index.html', 'r', encoding='utf-8') as f:
            html = f.read()
            self.assertIn('id="btn-delete-modal-idea"', html)

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

    def test_cors_preflight_and_headers(self):
        options_res = self.client.open('/api/tasks', method='OPTIONS')
        self.assertEqual(options_res.status_code, 200)
        self.assertEqual(options_res.headers.get('Access-Control-Allow-Origin'), '*')
        self.assertIn('Content-Type', options_res.headers.get('Access-Control-Allow-Headers', ''))
        self.assertIn('X-Requested-With', options_res.headers.get('Access-Control-Allow-Headers', ''))

        get_res = self.client.get('/api/health')
        self.assertEqual(get_res.headers.get('Access-Control-Allow-Origin'), '*')

    def test_task_not_done_status(self):
        # Create task
        res = self.client.post('/api/tasks', json={'title': 'Tarefa de Teste'})
        self.assertEqual(res.status_code, 201)
        t_id = res.get_json()['id']

        # Update status to not_done
        patch_res = self.client.patch(f'/api/tasks/{t_id}/status', json={'status': 'not_done'})
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.get_json()['status'], 'not_done')

    def test_ritmo_module(self):
        # 1. Exercises Catalog check
        ex_res = self.client.get('/api/exercises')
        self.assertEqual(ex_res.status_code, 200)
        exercises = ex_res.get_json()
        self.assertGreater(len(exercises), 0)
        first_ex = exercises[0]

        # 2. Create Custom Exercise
        new_ex = self.client.post('/api/exercises', json={
            'name': 'Barra Paralela Custom',
            'muscle_group': 'triceps',
            'equipment': 'Paralelas'
        })
        self.assertEqual(new_ex.status_code, 201)
        custom_id = new_ex.get_json()['id']

        # 3. Create Routine
        r_res = self.client.post('/api/routines', json={
            'name': 'Treino Peito & Tríceps',
            'target_muscle_groups': 'peito,triceps',
            'items': [
                {'exercise_id': first_ex['id'], 'sets': 3, 'reps': 10, 'rest': 90},
                {'exercise_id': custom_id, 'sets': 3, 'reps': 8, 'rest': 60}
            ]
        })
        self.assertEqual(r_res.status_code, 201)
        routine = r_res.get_json()
        r_id = routine['id']
        self.assertEqual(len(routine['items']), 2)

        # 4. Start Workout
        w_res = self.client.post('/api/workouts', json={'routine_id': r_id})
        self.assertEqual(w_res.status_code, 201)
        w_data = w_res.get_json()
        w_id = w_data['id']
        self.assertIsNone(w_data['finished_at'])

        # 5. Check Active Workout
        act_res = self.client.get('/api/workouts/active')
        self.assertEqual(act_res.status_code, 200)
        self.assertEqual(act_res.get_json()['id'], w_id)

        # 6. Complete sets and Finish Workout
        for item in w_data['items']:
            for s in item['sets']:
                s['done'] = True
                s['reps'] = 10
                s['load'] = 50.0

        w_data['finish'] = True
        fin_res = self.client.put(f'/api/workouts/{w_id}', json=w_data)
        self.assertEqual(fin_res.status_code, 200)
        self.assertIsNotNone(fin_res.get_json()['finished_at'])

        # 7. Body Metrics Weight
        m_res = self.client.post('/api/metrics/weight', json={
            'weight': 78.5,
            'notes': 'Pesagem em jejum'
        })
        self.assertEqual(m_res.status_code, 201)
        get_m = self.client.get('/api/metrics/weight')
        self.assertEqual(get_m.status_code, 200)
        self.assertGreater(len(get_m.get_json()), 0)

    def test_sleep_module(self):
        # 1. Log Sleep
        s_res = self.client.post('/api/sleep/logs', json={
            'sleep_date': '2026-10-24',
            'bedtime': '23:00',
            'wake_time': '07:00',
            'quality_rating': 4,
            'notes': 'Noite tranquila'
        })
        self.assertEqual(s_res.status_code, 201)
        self.assertEqual(s_res.get_json()['duration_minutes'], 480)

        # 2. Get Sleep Summary
        sum_res = self.client.get('/api/sleep/summary')
        self.assertEqual(sum_res.status_code, 200)
        self.assertIn('avg_duration_minutes', sum_res.get_json())

    def test_routine_editing_and_stopped_workout(self):
        # 1. Create Exercise and Routine
        ex_res = self.client.post('/api/exercises', json={
            'name': 'Supino Reto Test',
            'muscle_group': 'peito'
        })
        ex_id = ex_res.get_json()['id']

        r_res = self.client.post('/api/routines', json={
            'name': 'Peito A',
            'target_muscle_groups': 'peito',
            'items': [{'exercise_id': ex_id, 'sets': 3, 'reps': 10, 'rest': 60}]
        })
        self.assertEqual(r_res.status_code, 201)
        r_id = r_res.get_json()['id']

        # 2. Edit Routine via PUT
        put_res = self.client.put(f'/api/routines/{r_id}', json={
            'name': 'Peito e Tríceps A+',
            'target_muscle_groups': 'peito,triceps',
            'items': [{'exercise_id': ex_id, 'sets': 4, 'reps': 12, 'rest': 90}]
        })
        self.assertEqual(put_res.status_code, 200)
        updated_r = put_res.get_json()
        self.assertEqual(updated_r['name'], 'Peito e Tríceps A+')
        self.assertEqual(updated_r['target_muscle_groups'], 'peito,triceps')
        self.assertEqual(len(updated_r['items']), 1)
        self.assertEqual(updated_r['items'][0]['sets'], 4)

        # 3. Start Workout and Stop it (Interromper)
        w_res = self.client.post('/api/workouts', json={'routine_id': r_id})
        self.assertEqual(w_res.status_code, 201)
        w_id = w_res.get_json()['id']

        # Interromper (Stop)
        stop_res = self.client.put(f'/api/workouts/{w_id}', json={'stop': True})
        self.assertEqual(stop_res.status_code, 200)
        stopped_w = stop_res.get_json()
        self.assertEqual(stopped_w['status'], 'stopped')
        self.assertIsNotNone(stopped_w['finished_at'])

        # Active workout should now be None
        act_res = self.client.get('/api/workouts/active')
        self.assertEqual(act_res.status_code, 200)
        self.assertIsNone(act_res.get_json())

        # Stopped workout counts in history and calendar
        session_date = stopped_w['session_date']
        day_res = self.client.get(f'/api/calendar/day/{session_date}')
        self.assertEqual(day_res.status_code, 200)
        self.assertEqual(day_res.get_json()['state'], 'past_stopped')

    def test_task_stop_status(self):
        t_res = self.client.post('/api/tasks', json={'title': 'Tarefa com Stop', 'status': 'todo'})
        self.assertEqual(t_res.status_code, 201)
        t_id = t_res.get_json()['id']

        # Move to in_progress
        p1 = self.client.patch(f'/api/tasks/{t_id}/status', json={'status': 'in_progress'})
        self.assertEqual(p1.status_code, 200)
        self.assertEqual(p1.get_json()['status'], 'in_progress')

        # Move to stopped
        p2 = self.client.patch(f'/api/tasks/{t_id}/status', json={'status': 'stopped'})
        self.assertEqual(p2.status_code, 200)
        self.assertEqual(p2.get_json()['status'], 'stopped')

        # Resume to in_progress
        p3 = self.client.patch(f'/api/tasks/{t_id}/status', json={'status': 'in_progress'})
        self.assertEqual(p3.status_code, 200)
        self.assertEqual(p3.get_json()['status'], 'in_progress')

        # Finish to done
        p4 = self.client.patch(f'/api/tasks/{t_id}/status', json={'status': 'done'})
        self.assertEqual(p4.status_code, 200)
        self.assertEqual(p4.get_json()['status'], 'done')

    # --- FASE 3: Conciliação Financeira Híbrida (Webhook, OFX/CSV & Deduplicação) ---
    def test_finance_notification_webhook(self):
        # 1. Expense Pix notification
        res1 = self.client.post('/api/finances/webhook/notification', json={
            'banco': 'Nubank',
            'texto': 'Transferência de R$ 50,00 enviada para João Silva',
            'timestamp': 1700000000
        })
        self.assertEqual(res1.status_code, 201)
        data1 = res1.get_json()['transaction']
        self.assertEqual(data1['amount_cents'], 5000)
        self.assertEqual(data1['type'], 'expense')
        self.assertEqual(data1['source'], 'webhook')
        self.assertEqual(data1['account'], 'Nubank')
        self.assertIn('João Silva', data1['description'])

        # 2. Income Pix notification
        res2 = self.client.post('/api/finances/webhook/notification', json={
            'banco': 'Nubank',
            'texto': 'Você recebeu uma transferência Pix de R$ 120,50 de Maria Souza',
            'timestamp': 1700000000000  # ms format
        })
        self.assertEqual(res2.status_code, 201)
        data2 = res2.get_json()['transaction']
        self.assertEqual(data2['amount_cents'], 12050)
        self.assertEqual(data2['type'], 'income')
        self.assertEqual(data2['source'], 'webhook')

        # 3. Market expense with automatic keyword categorization
        res3 = self.client.post('/api/finances/webhook/notification', json={
            'banco': 'Inter',
            'texto': 'Compra no cartão de R$ 85,90 aprovada em Supermercado Carrefour'
        })
        self.assertEqual(res3.status_code, 201)
        data3 = res3.get_json()['transaction']
        self.assertEqual(data3['amount_cents'], 8590)
        self.assertEqual(data3['type'], 'expense')
        self.assertEqual(data3['category'], 'Alimentação')

    def test_ofx_import_and_deduplication(self):
        today_str = date.today().isoformat()
        yesterday_str = (date.today() - timedelta(days=1)).isoformat()
        ofx_date_str = yesterday_str.replace('-', '') + '120000'

        # 1. Pre-register real-time notification transaction (R$ 50,00)
        hook_res = self.client.post('/api/finances/webhook/notification', json={
            'banco': 'Nubank',
            'texto': 'Transferência Pix de R$ 50,00 enviada para Padaria Central'
        })
        self.assertEqual(hook_res.status_code, 201)
        hook_tx = hook_res.get_json()['transaction']
        self.assertEqual(hook_tx['reconciled'], 0)
        self.assertIsNone(hook_tx['external_id'])

        # 2. Prepare OFX containing the same R$ 50,00 expense + a new R$ 35,00 expense
        ofx_content = f"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEVERSION:102
NEWFILEVERSION:102
<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<BANKTRANLIST>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>{ofx_date_str}
<TRNAMT>-50.00
<FITID>FITID-NUBANK-1001
<MEMO>PADARIA CENTRAL LTDA
</STMTTRN>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>{ofx_date_str}
<TRNAMT>-35.00
<FITID>FITID-NUBANK-1002
<MEMO>FARMACIA DROGASIL
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>"""

        # 3. Post to /api/finances/import
        data = {
            'account': 'Nubank',
            'file': (io.BytesIO(ofx_content.encode('utf-8')), 'extrato_nubank.ofx')
        }
        imp_res = self.client.post('/api/finances/import', data=data, content_type='multipart/form-data')
        self.assertEqual(imp_res.status_code, 200)
        imp_data = imp_res.get_json()
        self.assertEqual(imp_data['total_processed'], 2)
        self.assertEqual(imp_data['imported'], 1)  # Only Drograsil is new
        self.assertEqual(imp_data['reconciled_duplicates'], 1)  # Padaria was reconciled

        # 4. Verify existing webhook transaction was reconciled and assigned FITID
        conn = get_db(self.db_path)
        try:
            tx50 = conn.execute("SELECT * FROM transactions WHERE amount_cents = 5000").fetchone()
            self.assertIsNotNone(tx50)
            self.assertEqual(tx50['reconciled'], 1)
            self.assertEqual(tx50['external_id'], 'FITID-NUBANK-1001')

            # Ensure total count for R$ 50,00 is 1 (no double spend)
            count50 = conn.execute("SELECT COUNT(*) FROM transactions WHERE amount_cents = 5000").fetchone()[0]
            self.assertEqual(count50, 1)

            # Ensure Drogasil was imported as well
            tx35 = conn.execute("SELECT * FROM transactions WHERE amount_cents = 3500").fetchone()
            self.assertIsNotNone(tx35)
            self.assertEqual(tx35['category'], 'Saúde')
            self.assertEqual(tx35['external_id'], 'FITID-NUBANK-1002')
        finally:
            conn.close()

    def test_csv_import(self):
        csv_content = """Data;Descricao;Valor
2026-10-25;Uber *Corrida Centro;-24,50
2026-10-25;Salario Mensal Tech;4500,00
"""
        data = {
            'account': 'Itaú',
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'extrato_itau.csv')
        }
        res = self.client.post('/api/finances/import', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        resp = res.get_json()
        self.assertEqual(resp['imported'], 2)

        conn = get_db(self.db_path)
        try:
            uber = conn.execute("SELECT * FROM transactions WHERE description LIKE '%Uber%'").fetchone()
            self.assertIsNotNone(uber)
            self.assertEqual(uber['type'], 'expense')
            self.assertEqual(uber['amount_cents'], 2450)
            self.assertEqual(uber['category'], 'Transporte')

            salario = conn.execute("SELECT * FROM transactions WHERE description LIKE '%Salario%'").fetchone()
            self.assertIsNotNone(salario)
            self.assertEqual(salario['type'], 'income')
            self.assertEqual(salario['amount_cents'], 450000)
            self.assertEqual(salario['category'], 'Salário')
        finally:
            conn.close()

    def test_finance_csv_export_calculations_and_format(self):
        # 1. Setup transactions across different months
        self.client.post('/api/finance/transactions', json={
            'description': 'Salário Consultoria',
            'amount_cents': 300000,
            'type': 'income',
            'category': 'Salário',
            'date': '2026-10-05'
        })
        self.client.post('/api/finance/transactions', json={
            'description': 'Aluguel Apartamento',
            'amount_cents': 50000,
            'type': 'expense',
            'category': 'Moradia',
            'date': '2026-10-10'
        })
        self.client.post('/api/finance/transactions', json={
            'description': 'Gasto Mês Passado',
            'amount_cents': 20000,
            'type': 'expense',
            'category': 'Outros',
            'date': '2026-09-15'
        })

        # 2. Export filtered for 2026-10
        res = self.client.get('/api/system/export?module=finance&format=csv&month=2026-10')
        self.assertEqual(res.status_code, 200)
        self.assertIn('attachment; filename="dreamhub_financas_2026-10_', res.headers.get('Content-Disposition', ''))
        content = res.get_data(as_text=True)

        # Check pt-BR semicolon delimiter & BOM
        self.assertTrue(content.startswith('\ufeff'))
        self.assertIn(';Valor Original (R$);Valor Líquido (R$);', content)

        # Calculations check: income is positive, expense has negative sign
        self.assertIn('Receita;Salário Consultoria;3000,00;3000,00;', content)
        self.assertIn('Despesa;Aluguel Apartamento;500,00;-500,00;', content)

        # September transaction should NOT be in October export
        self.assertNotIn('Gasto Mês Passado', content)

        # Audit totals check in October export: 3000 - 500 = 2500
        self.assertIn('TOTAL RECEITAS (+);;;3000,00', content)
        self.assertIn('TOTAL DESPESAS (-);;;-500,00', content)
        self.assertIn('SALDO LÍQUIDO;;;2500,00', content)
        self.assertIn('2 lançamentos', content)

        # 3. Export all history
        res_all = self.client.get('/api/system/export?module=finance&format=csv')
        self.assertEqual(res_all.status_code, 200)
        content_all = res_all.get_data(as_text=True)

        # All 3 transactions included: 3000 - 500 - 200 = 2300
        self.assertIn('Gasto Mês Passado', content_all)
        self.assertIn('SALDO LÍQUIDO;;;2300,00', content_all)
        self.assertIn('3 lançamentos', content_all)

    def test_clear_finance_data(self):
        # 1. Insert records
        self.client.post('/api/finance/transactions', json={
            'description': 'Outubro 1',
            'amount_cents': 1000,
            'type': 'expense',
            'date': '2026-10-01'
        })
        self.client.post('/api/finance/transactions', json={
            'description': 'Outubro 2',
            'amount_cents': 2000,
            'type': 'expense',
            'date': '2026-10-15'
        })
        self.client.post('/api/finance/transactions', json={
            'description': 'Setembro 1',
            'amount_cents': 3000,
            'type': 'expense',
            'date': '2026-09-20'
        })
        self.client.post('/api/finance/recurring-rules', json={
            'description': 'Internet Fibra',
            'amount': 120.0,
            'type': 'despesa',
            'day_of_month': 10,
            'frequency': 'mensal'
        })

        # 2. Test clear only October (2 manual transactions + 1 auto-generated by the recurring rule = 3)
        res_m = self.client.post('/api/finance/clear', json={
            'scope': 'month',
            'month': '2026-10'
        })
        self.assertEqual(res_m.status_code, 200)
        data_m = res_m.get_json()
        self.assertEqual(data_m['deleted_transactions'], 3)
        self.assertEqual(data_m['deleted_rules'], 0)

        conn = get_db(self.db_path)
        try:
            oct_cnt = conn.execute("SELECT COUNT(*) FROM transactions WHERE date LIKE '2026-10%'").fetchone()[0]
            self.assertEqual(oct_cnt, 0)
            sep_cnt = conn.execute("SELECT COUNT(*) FROM transactions WHERE date LIKE '2026-09%'").fetchone()[0]
            self.assertEqual(sep_cnt, 1)
        finally:
            conn.close()

        # 3. Test clear all with recurring rules
        res_all = self.client.post('/api/finance/clear', json={
            'scope': 'all',
            'include_rules': True
        })
        self.assertEqual(res_all.status_code, 200)
        data_all = res_all.get_json()
        self.assertEqual(data_all['deleted_transactions'], 1)
        self.assertEqual(data_all['deleted_rules'], 1)

        conn = get_db(self.db_path)
        try:
            total_txns = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            total_rules = conn.execute("SELECT COUNT(*) FROM recurring_rules").fetchone()[0]
            self.assertEqual(total_txns, 0)
            self.assertEqual(total_rules, 0)
        finally:
            conn.close()

    def test_nubank_csv_dot_decimal_and_clean_redundancy_and_categories(self):
        nubank_csv = """Data,Valor,Identificador,Descrição
24/10/2026,-10.94,id-uber-1,Transferência enviada pelo Pix - UBER DO BRASIL TECNOLOGIA LTDA. - 17.895.646/0001-87 - ADYEN DO BRASIL IP LTDA. Agência: 1 Conta: 100000056-0
02/10/2026,-574.99,id-univel-1,Pagamento de boleto efetuado - UNIAO EDUCACIONAL DE CASCAVEL - UNIVEL L
04/10/2026,-25.00,id-google-1,Transferência enviada pelo Pix - GOOGLE BRASIL PAGAMENTOS LTDA. - 13.382.906/0001-60 - EBANX IP LTDA. (0383) Agência: 1 Conta: 1001238142-7
07/10/2026,-20.99,id-burgz-1,Transferência enviada pelo Pix - BURGZ - 41.600.371/0001-91 - PAGSEGURO INTERNET IP S.A. (0290) Agência: 1 Conta: 26538762-1
22/10/2026,-8.50,id-irineia-1,Transferência enviada pelo Pix - 52.331.137 IRINEIA KLABUNDE - 52.331.137/0001-22 - NU PAGAMENTOS - IP (0260) Agência: 1 Conta: 20414152-6
23/10/2026,-8.00,id-renato-1,Transferência enviada pelo Pix - RENATO KOSLINSKI - •••.234.259-•• - BCO DO BRASIL S.A. (0001) Agência: 1460 Conta: 17729-6
"""
        data = {
            'account': 'Nubank',
            'file': (io.BytesIO(nubank_csv.encode('utf-8')), 'nubank_outubro.csv')
        }
        res = self.client.post('/api/finances/import', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)

        conn = get_db(self.db_path)
        try:
            # 1. Check 10.94 was NOT multiplied to 1094.00 (must be 1094 cents, not 109400)
            uber = conn.execute("SELECT * FROM transactions WHERE external_id = 'id-uber-1'").fetchone()
            self.assertIsNotNone(uber)
            self.assertEqual(uber['amount_cents'], 1094)
            self.assertEqual(uber['amount'], 10.94)
            self.assertEqual(uber['category'], 'Transporte')
            # Must NOT contain CNPJ, Agência, Conta, or redundant prefix
            self.assertNotIn('17.895.646', uber['description'])
            self.assertNotIn('Agência', uber['description'])
            self.assertNotIn('Conta:', uber['description'])
            self.assertNotIn('Transferência enviada pelo Pix', uber['description'])

            # 2. Check UNIVEL is categorized as Educação and 574.99 is 57499 cents
            univel = conn.execute("SELECT * FROM transactions WHERE external_id = 'id-univel-1'").fetchone()
            self.assertIsNotNone(univel)
            self.assertEqual(univel['amount_cents'], 57499)
            self.assertEqual(univel['category'], 'Educação')

            # 3. Check Google Pagamentos is categorized as Lazer
            google = conn.execute("SELECT * FROM transactions WHERE external_id = 'id-google-1'").fetchone()
            self.assertIsNotNone(google)
            self.assertEqual(google['amount_cents'], 2500)
            self.assertEqual(google['category'], 'Lazer')

            # 4. Check BURGZ is Alimentação (NOT Moradia due to PAGSEGURO INTERNET)
            burgz = conn.execute("SELECT * FROM transactions WHERE external_id = 'id-burgz-1'").fetchone()
            self.assertIsNotNone(burgz)
            self.assertEqual(burgz['amount_cents'], 2099)
            self.assertEqual(burgz['category'], 'Alimentação')

            # 5. Check MEI prefix 52.331.137 and CPF •••.234.259-•• are stripped
            irineia = conn.execute("SELECT * FROM transactions WHERE external_id = 'id-irineia-1'").fetchone()
            self.assertEqual(irineia['description'], 'IRINEIA KLABUNDE')
            renato = conn.execute("SELECT * FROM transactions WHERE external_id = 'id-renato-1'").fetchone()
            self.assertEqual(renato['description'], 'RENATO KOSLINSKI')
        finally:
            conn.close()

        # 6. Check PATCH category update works
        patch_res = self.client.patch(f"/api/finance/transactions/{renato['id']}", json={'category': 'Saúde'})
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.get_json()['category'], 'Saúde')

    def test_ideas_checklist_mode_and_validation(self):
        # 1. Default note_type is 'text'
        res_text = self.client.post('/api/ideas', json={
            'title': 'Ideia em Texto Livre',
            'content': 'Linha 1\nLinha 2'
        })
        self.assertEqual(res_text.status_code, 201)
        data_text = res_text.get_json()
        self.assertEqual(data_text.get('note_type'), 'text')
        self.assertEqual(data_text.get('content'), 'Linha 1\nLinha 2')

        # 2. Create idea with note_type='checklist' and JSON string payload
        checklist_items = [
            {"text": "Comprar leite", "done": False},
            {"text": "Pagar conta", "done": True}
        ]
        res_chk = self.client.post('/api/ideas', json={
            'title': 'Lista de Compras e Contas',
            'note_type': 'checklist',
            'content': json.dumps(checklist_items, ensure_ascii=False)
        })
        self.assertEqual(res_chk.status_code, 201)
        data_chk = res_chk.get_json()
        self.assertEqual(data_chk.get('note_type'), 'checklist')
        parsed_content = json.loads(data_chk.get('content'))
        self.assertEqual(len(parsed_content), 2)
        self.assertEqual(parsed_content[0], {"text": "Comprar leite", "done": False})
        self.assertEqual(parsed_content[1], {"text": "Pagar conta", "done": True})

        # 3. Update idea (PUT) toggling done state and accepting list or JSON string
        checklist_items[0]['done'] = True
        checklist_items.append({"text": "Estudar SQLite WAL", "done": False})
        idea_id = data_chk['id']
        res_put = self.client.put(f'/api/ideas/{idea_id}', json={
            'note_type': 'checklist',
            'content': json.dumps(checklist_items, ensure_ascii=False)
        })
        self.assertEqual(res_put.status_code, 200)
        updated_chk = res_put.get_json()
        self.assertEqual(updated_chk.get('note_type'), 'checklist')
        parsed_updated = json.loads(updated_chk.get('content'))
        self.assertEqual(len(parsed_updated), 3)
        self.assertTrue(parsed_updated[0]['done'])
        self.assertFalse(parsed_updated[2]['done'])

        # 4. Reject invalid JSON when note_type == 'checklist'
        res_invalid = self.client.post('/api/ideas', json={
            'title': 'Checklist Inválido',
            'note_type': 'checklist',
            'content': 'isto nao e um json array valido {'
        })
        self.assertEqual(res_invalid.status_code, 400)

if __name__ == '__main__':
    unittest.main()


