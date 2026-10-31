"""
Automated Tests for Dream Hub v1.4.0:
- Modo Rotinas Diárias (RF01-RF10, RN01-RN03, RNF03, RNF04, US01, US02, Decisões 01/02/04)
- Redesign do Dashboard Central (RF11, RF12, RN04)
- Evolução por Exercício no Módulo Ritmo (RF13, RF14, RN05, RNF01, US03, Decisão 03)
"""
import os
import shutil
import tempfile
import unittest
from datetime import date, timedelta

from backend.app import app
from backend.database import get_db, init_db


class DreamHubV14TestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(prefix='dreamhub_v14_test_', suffix='.db')
        os.close(self.db_fd)
        self.upload_dir = tempfile.mkdtemp(prefix='dreamhub_v14_uploads_')
        app.config['TESTING'] = True
        app.config['DATABASE'] = self.db_path
        app.config['UPLOAD_FOLDER'] = self.upload_dir
        init_db(self.db_path)
        self.client = app.test_client()

    def tearDown(self):
        for suffix in ['', '-wal', '-shm']:
            p = self.db_path + suffix
            if os.path.exists(p):
                os.unlink(p)
        if os.path.exists(self.upload_dir):
            shutil.rmtree(self.upload_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. ISOLATION BETWEEN RITMO `routines` AND DAILY ROUTINES `daily_routines`
    # -------------------------------------------------------------------------
    def test_zero_table_collision_between_ritmo_and_daily_routines(self):
        # Create a Ritmo workout routine
        r_ritmo = self.client.post('/api/routines', json={
            'name': 'Treino A - Peito e Tríceps',
            'target_muscle_groups': 'peito,triceps',
            'items': [{'exercise_id': 1, 'sets': 3, 'reps': 10, 'rest': 90}]
        })
        self.assertEqual(r_ritmo.status_code, 201)

        # Create a Daily Routine (Modo Rotinas Diárias)
        r_daily = self.client.post('/api/daily-routines', json={
            'title': 'Rotina Matinal de Estudos',
            'description': 'Leitura técnica + prática de Linux',
            'scheduled_time': '07:30',
            'days_of_week': '0,1,2,3,4,5,6',
            'pomodoro_target': 2,
            'pomodoro_duration_minutes': 25,
            'tasks': [
                {'title': 'Revisar flashcards', 'estimated_minutes': 15},
                {'title': 'Resolver laboratório prático', 'estimated_minutes': 35}
            ]
        })
        self.assertEqual(r_daily.status_code, 201)

        # Verify Ritmo routines only contain the workout routine
        ritmo_list = self.client.get('/api/routines').get_json()
        self.assertEqual(len(ritmo_list), 1)
        self.assertEqual(ritmo_list[0]['name'], 'Treino A - Peito e Tríceps')

        # Verify Daily Routines only contain the daily habit routine
        daily_list = self.client.get('/api/daily-routines').get_json()
        self.assertEqual(len(daily_list), 1)
        self.assertEqual(daily_list[0]['title'], 'Rotina Matinal de Estudos')
        self.assertEqual(len(daily_list[0]['tasks']), 2)

    # -------------------------------------------------------------------------
    # 2. AUTOMATIC 00:00 TRANSITION TO `em_andamento` & PUSH NOTIFICATION (RF01, Decisão 01)
    # -------------------------------------------------------------------------
    def test_automatic_daily_turnover_and_push_notification(self):
        create_res = self.client.post('/api/daily-routines', json={
            'title': 'Rotina Diária Automática',
            'scheduled_time': '08:00',
            'days_of_week': '0,1,2,3,4,5,6',
            'tasks': [{'title': 'Planejar o dia', 'estimated_minutes': 10}]
        })
        self.assertEqual(create_res.status_code, 201)
        routine_id = create_res.get_json()['id']

        # Querying /api/daily-routines/today triggers ensure_daily_routines_initialized_for_today
        today_res = self.client.get('/api/daily-routines/today')
        self.assertEqual(today_res.status_code, 200)
        today_data = today_res.get_json()

        routines_today = today_data.get('routines', [])
        self.assertEqual(len(routines_today), 1)
        self.assertEqual(routines_today[0]['routine_id'], routine_id)
        self.assertEqual(routines_today[0]['status'], 'em_andamento')
        self.assertIsNotNone(routines_today[0].get('notified_at'))

    # -------------------------------------------------------------------------
    # 3. INTERRUPT REQUIRES MANDATORY REASON (HTTP 400 IF EMPTY), RESUME & COMMENTS (RF03, RF04, RN03, Decisão 02)
    # -------------------------------------------------------------------------
    def test_interrupt_mandatory_reason_resume_and_chronological_comments(self):
        r = self.client.post('/api/daily-routines', json={
            'title': 'Rotina de Engenharia',
            'days_of_week': '0,1,2,3,4,5,6',
            'tasks': [{'title': 'Codificar módulo', 'estimated_minutes': 45}]
        }).get_json()
        rid = r['id']

        # Attempt to interrupt without reason -> MUST fail with HTTP 400
        bad_intr = self.client.post(f'/api/daily-routines/{rid}/interrupt', json={'reason': '   '})
        self.assertEqual(bad_intr.status_code, 400)

        # Valid interrupt with reason -> HTTP 200 and status becomes 'interrompida'
        ok_intr = self.client.post(f'/api/daily-routines/{rid}/interrupt', json={
            'reason': 'Chamada urgente da equipe de infraestrutura',
            'elapsed_seconds': 600
        })
        self.assertEqual(ok_intr.status_code, 200)
        intr_payload = ok_intr.get_json()
        self.assertEqual(intr_payload['status'], 'interrompida')
        self.assertEqual(intr_payload['reason'], 'Chamada urgente da equipe de infraestrutura')

        # Resume on the same day -> status returns to 'em_andamento' and resumed_at is populated
        res_resume = self.client.post(f'/api/daily-routines/{rid}/resume', json={})
        self.assertEqual(res_resume.status_code, 200)
        self.assertEqual(res_resume.get_json()['status'], 'em_andamento')

        # Add chronological comment (RF04)
        comm_res = self.client.post(f'/api/daily-routines/{rid}/comments', json={
            'comment_text': 'Retomei o foco após resolver o incidente.'
        })
        self.assertEqual(comm_res.status_code, 201)

        # Complete routine
        comp_res = self.client.post(f'/api/daily-routines/{rid}/complete', json={'elapsed_seconds': 1800})
        self.assertEqual(comp_res.status_code, 200)
        self.assertEqual(comp_res.get_json()['status'], 'concluida')

        # Verify in history (RF10)
        hist = self.client.get('/api/daily-routines/history').get_json()
        self.assertGreaterEqual(len(hist['items']), 1)
        first_log = hist['items'][0]
        self.assertEqual(first_log['status'], 'concluida')
        self.assertEqual(len(first_log['interruptions']), 1)
        self.assertIsNotNone(first_log['interruptions'][0]['resumed_at'])
        self.assertEqual(len(first_log['comments']), 1)

    # -------------------------------------------------------------------------
    # 4. MANUAL CANCELLATION (RN01) vs SCHEDULED TEMPORARY SUSPENSION (RN02, US01)
    # -------------------------------------------------------------------------
    def test_manual_cancellation_vs_scheduled_temporary_suspension(self):
        r = self.client.post('/api/daily-routines', json={
            'title': 'Rotina Noturna de Leitura',
            'days_of_week': '0,1,2,3,4,5,6',
            'tasks': [{'title': 'Ler 20 páginas', 'estimated_minutes': 25}]
        }).get_json()
        rid = r['id']

        # 1) Schedule Temporary Suspension for today..tomorrow (RN02, US01)
        today_str = date.today().isoformat()
        tomorrow_str = (date.today() + timedelta(days=1)).isoformat()
        susp_res = self.client.post(f'/api/daily-routines/{rid}/suspensions', json={
            'suspension_type': 'date_range',
            'start_date': today_str,
            'end_date': tomorrow_str,
            'reason': 'Viagem curta'
        })
        self.assertEqual(susp_res.status_code, 201)

        # Check today status -> must be 'suspensa'
        today_view = self.client.get('/api/daily-routines/today').get_json()
        routine_today = [x for x in today_view['routines'] if x['routine_id'] == rid][0]
        self.assertEqual(routine_today['status'], 'suspensa')

        # Check calendar view -> today and tomorrow are 'suspensa', day after tomorrow is 'planejada' (automatic return RN02!)
        day_after_str = (date.today() + timedelta(days=2)).isoformat()
        month_prefix = today_str[:7]
        cal_data = self.client.get(f'/api/daily-routines/calendar?month={month_prefix}&view=month').get_json()
        day_map = {d['date']: d['items'] for d in cal_data['days']}
        if day_after_str[:7] == month_prefix:
            items_after = [i for i in day_map[day_after_str] if i['routine_id'] == rid]
            self.assertEqual(items_after[0]['state'], 'planejada')

        # 2) Manual Immediate Cancellation (RN01)
        cancel_res = self.client.post(f'/api/daily-routines/{rid}/cancel', json={})
        self.assertEqual(cancel_res.status_code, 200)
        self.assertEqual(cancel_res.get_json()['status'], 'cancelada')

        # RN01: While 'cancelada', attempting to start or schedule suspension MUST return HTTP 400
        blocked_start = self.client.post(f'/api/daily-routines/{rid}/start', json={})
        self.assertEqual(blocked_start.status_code, 400)

        blocked_susp = self.client.post(f'/api/daily-routines/{rid}/suspensions', json={
            'suspension_type': 'date_range',
            'start_date': today_str,
            'end_date': tomorrow_str
        })
        self.assertEqual(blocked_susp.status_code, 400)

        # Reactivate -> returns to 'ativa' and 'em_andamento'
        react_res = self.client.post(f'/api/daily-routines/{rid}/reactivate', json={})
        self.assertEqual(react_res.status_code, 200)
        self.assertEqual(react_res.get_json()['status'], 'ativa')

    # -------------------------------------------------------------------------
    # 5. SLEEP MONITORING WITH 4 COMPLIANCE STATES (RF07)
    # -------------------------------------------------------------------------
    def test_sleep_monitoring_settings_and_four_compliance_states(self):
        # Update sleep settings
        put_set = self.client.put('/api/settings/sleep', json={
            'planned_bedtime': '22:30',
            'planned_wake_time': '06:30'
        })
        self.assertEqual(put_set.status_code, 200)
        self.assertEqual(put_set.get_json()['planned_bedtime'], '22:30')

        # Log all 4 compliance states
        states = ['no_horario', 'dormiu_menos', 'dormiu_mais', 'nao_conseguiu_dormir']
        for idx, st in enumerate(states):
            d_str = (date.today() - timedelta(days=idx)).isoformat()
            res = self.client.post('/api/sleep/logs', json={
                'sleep_date': d_str,
                'bedtime': '23:00',
                'wake_time': '06:30',
                'compliance_status': st,
                'quality_rating': 4
            })
            self.assertEqual(res.status_code, 201)
            self.assertEqual(res.get_json()['compliance_status'], st)

        sum_res = self.client.get('/api/sleep/summary').get_json()
        counts = sum_res.get('compliance_counts', {})
        for st in states:
            self.assertEqual(counts.get(st), 1)

    # -------------------------------------------------------------------------
    # 6. DASHBOARD REDESIGN: 3 PRIORITY WIDGETS & FEATURED GOAL SELECTOR (RF11, RF12, RN04)
    # -------------------------------------------------------------------------
    def test_dashboard_three_priority_widgets_and_featured_goal_selector(self):
        # Create two active goals
        g1 = self.client.post('/api/goals', json={
            'title': 'Reserva de Emergência',
            'category': 'financas',
            'goal_type': 'monetaria',
            'current_value': 2500,
            'target_value': 5000,
            'unit': 'R$'
        }).get_json()
        g2 = self.client.post('/api/goals', json={
            'title': 'Certificação Linux LPIC-1',
            'category': 'estudos',
            'goal_type': 'quantitativa',
            'current_value': 30,
            'target_value': 60,
            'unit': 'aulas'
        }).get_json()

        # Select g2 as featured goal via PUT /api/settings/featured-goal (RN04)
        sel_res = self.client.put('/api/settings/featured-goal', json={'featured_goal_id': g2['id']})
        self.assertEqual(sel_res.status_code, 200)

        cockpit = self.client.get('/api/cockpit/today').get_json()['data']
        self.assertIn('finance', cockpit)
        self.assertIn('routine_today', cockpit)
        self.assertIn('featured_goal', cockpit)
        self.assertIn('available_goals', cockpit)
        self.assertEqual(len(cockpit['available_goals']), 2)
        self.assertEqual(cockpit['featured_goal']['id'], g2['id'])
        self.assertEqual(cockpit['featured_goal']['title'], 'Certificação Linux LPIC-1')

    # -------------------------------------------------------------------------
    # 7. RITMO EXERCISE EVOLUTION: MAX(load) vs SUM(load * reps) & RN05 FILTER
    # -------------------------------------------------------------------------
    def test_ritmo_exercise_evolution_max_load_volume_and_rn05_finished_only(self):
        # Create routine with exercise_id = 1 (Supino Reto)
        r = self.client.post('/api/routines', json={
            'name': 'Treino Força Peito',
            'target_muscle_groups': 'peito',
            'items': [{'exercise_id': 1, 'sets': 2, 'reps': 10, 'rest': 90}]
        }).get_json()

        # Start Workout #1 and finish it with done sets: 60kg x 10 and 70kg x 8
        w1 = self.client.post('/api/workouts', json={'routine_id': r['id']}).get_json()
        active1 = self.client.get('/api/workouts/active').get_json()
        it1 = active1['items'][0]
        sets1 = it1['sets']
        self.client.put(f"/api/workouts/{w1['id']}", json={
            'finish': True,
            'items': [{
                'id': it1['id'],
                'notes': '',
                'sets': [
                    {'id': sets1[0]['id'], 'load': 60.0, 'reps': 10, 'done': True},
                    {'id': sets1[1]['id'], 'load': 70.0, 'reps': 8, 'done': True}
                ]
            }]
        })

        # Start Workout #2 (unfinished!) with 120kg x 10 -> RN05: MUST NOT pollute evolution chart
        w2 = self.client.post('/api/workouts', json={'routine_id': r['id']}).get_json()
        active2 = self.client.get('/api/workouts/active').get_json()
        it2 = active2['items'][0]
        sets2 = it2['sets']
        self.client.put(f"/api/workouts/{w2['id']}", json={
            'finish': False,
            'items': [{
                'id': it2['id'],
                'notes': '',
                'sets': [
                    {'id': sets2[0]['id'], 'load': 120.0, 'reps': 10, 'done': True},
                    {'id': sets2[1]['id'], 'load': 120.0, 'reps': 10, 'done': False}
                ]
            }]
        })
        # Notice we do NOT finish workout #2

        # Verify performed-exercises lists Exercise #1 with PR = 70.0kg (ignoring unfinished 120kg)
        perf_list = self.client.get('/api/ritmo/performed-exercises').get_json()
        self.assertEqual(len(perf_list), 1)
        self.assertEqual(perf_list[0]['id'], 1)
        self.assertEqual(perf_list[0]['all_time_max_load'], 70.0)

        # Verify exercise-evolution calculation:
        # max_load = 70.0 kg
        # total_volume = (60 * 10) + (70 * 8) = 600 + 560 = 1160.0 kg
        # total_reps = 10 + 8 = 18
        evo = self.client.get('/api/ritmo/exercise-evolution?exercise_id=1&period=all').get_json()
        self.assertEqual(len(evo['points']), 1)
        pt = evo['points'][0]
        self.assertEqual(pt['max_load'], 70.0)
        self.assertEqual(pt['total_volume'], 1160.0)
        self.assertEqual(pt['total_reps'], 18)

    # -------------------------------------------------------------------------
    # 8. DAILY ROUTINES CALENDAR MATRIX & DAY DETAILS (IDENTICAL TO RITMO)
    # -------------------------------------------------------------------------
    def test_daily_routines_calendar_matrix_and_day_details_identical_to_ritmo(self):
        today_str = date.today().isoformat()
        month_str = today_str[:7]

        # Create a routine and start/complete it for today
        r = self.client.post('/api/daily-routines', json={
            'title': 'Rotina Foco Calendário',
            'scheduled_time': '08:00',
            'days_of_week': '0,1,2,3,4,5,6',
            'tasks': [{'title': 'Passo 1', 'position': 0}]
        }).get_json()

        # Complete the routine for today
        self.client.post(f"/api/daily-routines/{r['id']}/complete", json={'total_focus_seconds': 1800})

        # Add comment
        self.client.post(f"/api/daily-routines/{r['id']}/comments", json={'comment_text': 'Execução excelente'})

        # Verify /api/daily-routines/calendar returns month summary matching Ritmo structure
        cal_res = self.client.get(f'/api/daily-routines/calendar?month={month_str}').get_json()
        self.assertIn('month', cal_res)
        self.assertIn('days', cal_res)
        self.assertIn('summary', cal_res)
        self.assertGreaterEqual(cal_res['summary']['total_runs'], 1)
        self.assertIn(today_str, cal_res['summary']['completed_dates'])
        self.assertGreaterEqual(cal_res['summary']['completed_days'], 1)

        # Verify /api/daily-routines/day/<today_str> returns rich details for modal
        day_res = self.client.get(f'/api/daily-routines/day/{today_str}').get_json()
        self.assertEqual(day_res['date'], today_str)
        self.assertTrue(day_res['is_today'])
        self.assertGreaterEqual(len(day_res['logs']), 1)
        log = day_res['logs'][0]
        self.assertEqual(log['routine_title'], 'Rotina Foco Calendário')
        self.assertEqual(log['status'], 'concluida')
        self.assertEqual(log['total_focus_seconds'], 1800)
        self.assertEqual(len(log['comments']), 1)
        self.assertEqual(log['comments'][0]['comment_text'], 'Execução excelente')

    # -------------------------------------------------------------------------
    # 9. V1.4.1 SURGICAL ADJUSTMENTS: TASK HOURS & MINUTES AND SLEEP CLEANUP
    # -------------------------------------------------------------------------
    def test_daily_routine_task_duration_hours_and_minutes_and_total_planned(self):
        # 1. Create routine with hours and minutes per task
        res = self.client.post('/api/daily-routines', json={
            'title': 'Rotina de Engenharia de Software',
            'description': 'Estudo aprofundado e arquitetura',
            'scheduled_time': '09:00',
            'days_of_week': '0,1,2,3,4,5,6',
            'tasks': [
                {'title': 'Arquitetura de Sistemas', 'duration_hours': 1, 'duration_mins': 30},
                {'title': 'Code Review & Refatoração', 'duration_minutes': 45}
            ]
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        r_id = data['id']

        # Verify total planned minutes = 90 + 45 = 135 (2h 15min)
        self.assertEqual(data['total_planned_minutes'], 135)
        self.assertEqual(data['total_planned_label'], '2h 15min')
        self.assertEqual(len(data['tasks']), 2)
        self.assertEqual(data['tasks'][0]['duration_minutes'], 90)
        self.assertEqual(data['tasks'][0]['duration_label'], '1h 30min')
        self.assertEqual(data['tasks'][1]['duration_minutes'], 45)
        self.assertEqual(data['tasks'][1]['duration_label'], '45min')

        # 2. Toggle task completion with elapsed seconds
        t_id = data['tasks'][0]['id']
        t_toggle = self.client.patch(f'/api/daily-routines/{r_id}/tasks/{t_id}', json={
            'done': True,
            'task_elapsed_seconds': 5400
        })
        self.assertEqual(t_toggle.status_code, 200)
        t_data = t_toggle.get_json()
        matching_task = [t for t in t_data['tasks'] if t['id'] == t_id][0]
        self.assertTrue(matching_task['done'])
        self.assertEqual(matching_task['elapsed_seconds'], 5400)

        # 3. Check /api/daily-routines/today includes duration labels and planned totals
        today_res = self.client.get('/api/daily-routines/today').get_json()
        routines_list = today_res.get('routines', [])
        matching = [r for r in routines_list if r.get('routine_id') == r_id or r.get('id') == r_id]
        self.assertTrue(len(matching) > 0)
        m_r = matching[0]
        self.assertEqual(m_r['total_planned_minutes'], 135)
        self.assertEqual(m_r['total_planned_label'], '2h 15min')

        # 4. Check /api/daily-routines/history returns total_planned_minutes
        self.client.post(f'/api/daily-routines/{r_id}/complete', json={'total_focus_seconds': 5400})
        hist = self.client.get('/api/daily-routines/history').get_json()
        hist_items = [h for h in hist['items'] if h['routine_id'] == r_id]
        self.assertTrue(len(hist_items) > 0)
        self.assertEqual(hist_items[0]['total_planned_minutes'], 135)

    def test_sleep_dropdown_cleanup_and_html_integrity(self):
        # Verify index.html does not contain the standalone dropdown item for sleep
        with open('frontend/index.html', 'r', encoding='utf-8') as f:
            html = f.read()

        self.assertNotIn("App.navigateTo('sleep')\">Sono</button>", html)
        self.assertNotIn('<section id="view-sleep"', html)
        # Verify Foco / Pomodoro and integrated Sono subview are preserved
        self.assertIn("App.navigateTo('time')\">Foco / Pomodoro</button>", html)
        self.assertIn('id="routines-subview-sono"', html)


if __name__ == '__main__':
    unittest.main()

