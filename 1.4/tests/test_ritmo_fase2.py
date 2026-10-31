import unittest
import json
import os
import shutil
import tempfile
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app import create_app

class RitmoFase2TestCase(unittest.TestCase):
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

    def test_calendar_and_workout_statuses(self):
        # 1. Cadastra exercício e rotina
        ex_res = self.client.post('/api/exercises', json={
            'name': 'Supino Reto',
            'muscle_group': 'chest'
        })
        self.assertEqual(ex_res.status_code, 201)
        ex_id = ex_res.get_json()['id']

        r_res = self.client.post('/api/routines', json={
            'name': 'Peito e Tríceps',
            'target_muscle_groups': 'chest,triceps',
            'exercises': [
                {'exercise_id': ex_id, 'sets': 3, 'reps': 10, 'rest': 90}
            ]
        })
        self.assertEqual(r_res.status_code, 201)
        r_id = r_res.get_json()['id']

        # 2. Agendar treino como 'pendente' (RF02)
        today_str = datetime.now().strftime('%Y-%m-%d')
        pending_res = self.client.post('/api/workouts', json={
            'routine_id': r_id,
            'status': 'pendente'
        })
        self.assertEqual(pending_res.status_code, 201)
        self.assertTrue(pending_res.get_json().get('scheduled'))

        # 3. Consultar calendário do mês
        curr_month = today_str[:7]
        cal_res = self.client.get(f'/api/calendar/month?month={curr_month}')
        self.assertEqual(cal_res.status_code, 200)
        cal_data = cal_res.get_json()
        self.assertIn(today_str, cal_data['scheduled_dates'])

        # 4. Iniciar treino como 'em_andamento'
        start_res = self.client.post('/api/workouts', json={
            'routine_id': r_id,
            'status': 'em_andamento'
        })
        self.assertEqual(start_res.status_code, 201)
        w_active = start_res.get_json()
        self.assertIsNone(w_active['finished_at'])

        # 5. Finalizar treino ativo
        fin_res = self.client.put(f"/api/workouts/{w_active['id']}", json={'action': 'finish'})
        self.assertEqual(fin_res.status_code, 200)

        # 6. Registrar treino direto como 'concluido'
        done_res = self.client.post('/api/workouts', json={
            'routine_id': r_id,
            'status': 'concluido'
        })
        self.assertEqual(done_res.status_code, 201)
        w_done = done_res.get_json()
        self.assertIsNotNone(w_done['finished_at'])

        # 7. Checar detalhes do dia
        day_res = self.client.get(f'/api/calendar/day/{today_str}')
        self.assertEqual(day_res.status_code, 200)
        day_data = day_res.get_json()
        self.assertIn('state', day_data)

    def test_evolution_photos_endpoints(self):
        # Listagem inicial vazia
        res = self.client.get('/api/metrics/photos')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), [])

        # Upload de foto com payload json (mock base64)
        post_res = self.client.post('/api/metrics/photos', json={
            'photo_date': datetime.now().strftime('%Y-%m-%d'),
            'angle': 'frontal',
            'notes': 'Shape inicial',
            'file_content': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
        })
        self.assertEqual(post_res.status_code, 201)
        photo_id = post_res.get_json()['id']

        # Listagem deve conter a foto
        res = self.client.get('/api/metrics/photos')
        self.assertEqual(len(res.get_json()), 1)

        # Exclusão
        del_res = self.client.delete(f'/api/metrics/photos/{photo_id}')
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(len(self.client.get('/api/metrics/photos').get_json()), 0)

    def test_task_stop_status_and_task_history_with_date_filter(self):
        # 1. Create a recurring task
        t_res = self.client.post('/api/tasks', json={
            'title': 'Estudar Engenharia Reversa',
            'recurrence': 'diaria',
            'due_date': '2026-10-30'
        })
        self.assertEqual(t_res.status_code, 201)
        task_id = t_res.get_json()['id']

        # 2. Change status to 'Stop' (stopped)
        stop_res = self.client.patch(f'/api/tasks/{task_id}/status', json={'status': 'Stop'})
        self.assertEqual(stop_res.status_code, 200)
        self.assertEqual(stop_res.get_json()['status'], 'stopped')

        # 3. Complete recurring task -> records in task_history and advances due_date
        done_res = self.client.patch(f'/api/tasks/{task_id}/status', json={'status': 'done'})
        self.assertEqual(done_res.status_code, 200)
        done_data = done_res.get_json()
        self.assertTrue(done_data.get('cycle_completed'))

        # 4. Manually add another historical record on a specific date for filter test
        hist_post = self.client.post(f'/api/tasks/{task_id}/history', json={
            'execution_date': '2026-10-15T14:30:00',
            'notes': 'Sessão extra de revisão'
        })
        self.assertEqual(hist_post.status_code, 201)

        # 5. Fetch all task_history records
        hist_res = self.client.get(f'/api/tasks/{task_id}/history')
        self.assertEqual(hist_res.status_code, 200)
        all_hist = hist_res.get_json()
        self.assertEqual(len(all_hist), 2)

        # 6. Filter task_history by date '2026-10-15'
        filt_res = self.client.get(f'/api/tasks/{task_id}/history?date=2026-10-15')
        self.assertEqual(filt_res.status_code, 200)
        filt_hist = filt_res.get_json()
        self.assertEqual(len(filt_hist), 1)
        self.assertEqual(filt_hist[0]['notes'], 'Sessão extra de revisão')

    def test_adhoc_workout_sets_and_comments_do_not_alter_routine(self):
        # 1. Create exercise and routine with 3 planned sets
        ex_res = self.client.post('/api/exercises', json={
            'name': 'Agachamento Hack',
            'muscle_group': 'quadriceps'
        })
        ex_id = ex_res.get_json()['id']

        r_res = self.client.post('/api/routines', json={
            'name': 'Treino de Pernas A',
            'target_muscle_groups': 'quadriceps',
            'items': [
                {'exercise_id': ex_id, 'sets': 3, 'reps': 12, 'rest': 120}
            ]
        })
        self.assertEqual(r_res.status_code, 201)
        routine_id = r_res.get_json()['id']

        # 2. Start active workout session
        w_res = self.client.post('/api/workouts', json={
            'routine_id': routine_id,
            'status': 'em_andamento'
        })
        self.assertEqual(w_res.status_code, 201)
        workout = w_res.get_json()
        item_id = workout['items'][0]['id']
        self.assertEqual(len(workout['items'][0]['sets']), 3)

        # 3. Add ad-hoc set (+ Série) in active workout
        adhoc_res = self.client.post(f'/api/workout_items/{item_id}/sets', json={
            'reps': 10,
            'load': 80.0
        })
        self.assertEqual(adhoc_res.status_code, 201)
        updated_w = adhoc_res.get_json()['workout']
        self.assertEqual(len(updated_w['items'][0]['sets']), 4)

        # 4. Save comment on exercise in active workout
        note_res = self.client.patch(f'/api/workout_items/{item_id}', json={
            'notes': 'Ótima amplitude na última série'
        })
        self.assertEqual(note_res.status_code, 200)
        self.assertEqual(note_res.get_json()['notes'], 'Ótima amplitude na última série')

        # 5. CRITICAL BUSINESS RULE: Routine planning table (routine_items) MUST remain at 3 sets
        routine_check = self.client.get(f'/api/routines/{routine_id}').get_json()
        self.assertEqual(routine_check['items'][0]['sets'], 3)

    def test_calendar_schedule_direct_status_change(self):
        ex_res = self.client.post('/api/exercises', json={
            'name': 'Remada Curvada',
            'muscle_group': 'costas'
        })
        ex_id = ex_res.get_json()['id']

        r_res = self.client.post('/api/routines', json={
            'name': 'Costas e Bíceps',
            'items': [{'exercise_id': ex_id, 'sets': 3, 'reps': 10, 'rest': 90}]
        })
        r_id = r_res.get_json()['id']

        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        sched_res = self.client.post('/api/calendar/schedule', json={
            'routine_id': r_id,
            'scheduled_at': tomorrow_str
        })
        self.assertEqual(sched_res.status_code, 201)
        sched_id = sched_res.get_json()['id']

        # Directly mark scheduled workout as 'stopped' without starting session
        st_stop = self.client.patch(f'/api/calendar/schedule/{sched_id}/status', json={'status': 'stopped'})
        self.assertEqual(st_stop.status_code, 200)
        self.assertEqual(st_stop.get_json()['status'], 'stopped')

        cal_stop = self.client.get(f"/api/calendar/month?month={tomorrow_str[:7]}").get_json()
        self.assertIn(tomorrow_str, cal_stop['stopped_dates'])

        # Directly change scheduled workout to 'concluido'
        st_done = self.client.patch(f'/api/calendar/schedule/{sched_id}/status', json={'status': 'concluido'})
        self.assertEqual(st_done.status_code, 200)
        self.assertEqual(st_done.get_json()['status'], 'concluido')

        cal_done = self.client.get(f"/api/calendar/month?month={tomorrow_str[:7]}").get_json()
        self.assertIn(tomorrow_str, cal_done['trained_dates'])

if __name__ == '__main__':
    unittest.main()
