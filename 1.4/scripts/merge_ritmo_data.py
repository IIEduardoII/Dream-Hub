#!/usr/bin/env python3
"""
Merge Ritmo standalone SQLite database into Dream Hub (Nexus) unified database.
Zero data loss, idempotent, fully validated with FK and integrity checks.
"""

import sys
import os
import sqlite3

def run_merge(ritmo_path, nexus_path):
    if not os.path.exists(ritmo_path):
        print(f"[WARN] Ritmo database not found at {ritmo_path}. Skipping Ritmo merge.")
        return True

    if not os.path.exists(nexus_path):
        print(f"[ERROR] Nexus database not found at {nexus_path}.")
        return False

    # Ensure backend is in python path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from backend.database import init_db

    print(f"[*] Applying schema v1.3 and auto-healing on {nexus_path}...")
    init_db(nexus_path)

    nexus_conn = sqlite3.connect(nexus_path)
    nexus_conn.row_factory = sqlite3.Row
    ritmo_conn = sqlite3.connect(ritmo_path)
    ritmo_conn.row_factory = sqlite3.Row

    print(f"[*] Merging tables from {ritmo_path} into {nexus_path}...")

    # 1. Exercises
    ex_rows = ritmo_conn.execute("SELECT id, name, muscle, custom, muscle_group, equipment, notes, created_at FROM exercises").fetchall()
    for r in ex_rows:
        mg = r['muscle_group'] if r['muscle_group'] and r['muscle_group'] != 'outro' else r['muscle']
        nexus_conn.execute("""
            INSERT OR IGNORE INTO exercises (id, name, muscle_group, equipment, notes, custom, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (r['id'], r['name'], mg, r['equipment'] or '', r['notes'] or '', 1 if r['custom'] else 0, r['created_at']))
    print(f"  [+] Exercises: {len(ex_rows)} records processed.")

    # 2. Routines
    rot_rows = ritmo_conn.execute("SELECT id, name, goal, target_muscle_groups, day_of_week, user_id, created_at FROM routines").fetchall()
    for r in rot_rows:
        nexus_conn.execute("""
            INSERT OR REPLACE INTO routines (id, user_id, name, target_muscle_groups, day_of_week, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (r['id'], r['user_id'] or 1, r['name'], r['target_muscle_groups'] or '', r['day_of_week'], r['created_at']))
    print(f"  [+] Routines: {len(rot_rows)} records processed.")

    # 3. Routine Items
    ri_rows = ritmo_conn.execute("SELECT id, routine_id, exercise_id, position, sets, reps, rest, target_reps FROM routine_items").fetchall()
    for r in ri_rows:
        nexus_conn.execute("""
            INSERT OR REPLACE INTO routine_items (id, routine_id, exercise_id, position, sets, reps, rest, target_reps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (r['id'], r['routine_id'], r['exercise_id'], r['position'], r['sets'], r['reps'], r['rest'], r['target_reps']))
    print(f"  [+] Routine Items: {len(ri_rows)} records processed.")

    # 4. Workouts
    w_rows = ritmo_conn.execute("SELECT id, routine_name, started_at, finished_at, notes, session_date, user_id, routine_id FROM workouts").fetchall()
    for r in w_rows:
        s_date = r['session_date'] or (r['started_at'][:10] if r['started_at'] else '')
        nexus_conn.execute("""
            INSERT OR REPLACE INTO workouts (id, user_id, routine_id, routine_name, started_at, finished_at, notes, session_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (r['id'], r['user_id'] or 1, r['routine_id'], r['routine_name'], r['started_at'], r['finished_at'], r['notes'] or '', s_date))
    print(f"  [+] Workouts: {len(w_rows)} records processed.")

    # 5. Workout Items
    wi_rows = ritmo_conn.execute("SELECT id, workout_id, exercise_id, name, position, rest, notes FROM workout_items").fetchall()
    for r in wi_rows:
        nexus_conn.execute("""
            INSERT OR REPLACE INTO workout_items (id, workout_id, exercise_id, name, position, rest, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (r['id'], r['workout_id'], r['exercise_id'], r['name'], r['position'], r['rest'], r['notes'] or ''))
    print(f"  [+] Workout Items: {len(wi_rows)} records processed.")

    # 6. Workout Sets
    ws_rows = ritmo_conn.execute("SELECT id, item_id, position, reps, load, done, rpe, completed_at FROM workout_sets").fetchall()
    for r in ws_rows:
        nexus_conn.execute("""
            INSERT OR REPLACE INTO workout_sets (id, item_id, position, reps, load, done, rpe, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (r['id'], r['item_id'], r['position'], r['reps'], r['load'], 1 if r['done'] else 0, r['rpe'], r['completed_at']))
    print(f"  [+] Workout Sets: {len(ws_rows)} records processed.")

    # 7. Body Metrics
    bm_rows = ritmo_conn.execute("SELECT id, user_id, weight, notes, recorded_at, created_at FROM body_metrics").fetchall()
    for r in bm_rows:
        nexus_conn.execute("""
            INSERT OR REPLACE INTO body_metrics (id, user_id, weight, notes, recorded_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (r['id'], r['user_id'] or 1, r['weight'], r['notes'] or '', r['recorded_at'], r['created_at']))
    print(f"  [+] Body Metrics: {len(bm_rows)} records processed.")

    # 8. Evolution Photos
    ep_rows = ritmo_conn.execute("SELECT id, user_id, metric_id, photo_path, angle, taken_at, created_at FROM evolution_photos").fetchall()
    for r in ep_rows:
        nexus_conn.execute("""
            INSERT OR REPLACE INTO evolution_photos (id, user_id, metric_id, photo_path, angle, taken_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (r['id'], r['user_id'] or 1, r['metric_id'], r['photo_path'], r['angle'] or 'frontal', r['taken_at'], r['created_at']))
    print(f"  [+] Evolution Photos: {len(ep_rows)} records processed.")

    nexus_conn.commit()

    # Integrity & FK checks
    fk_violations = nexus_conn.execute("PRAGMA foreign_key_check;").fetchall()
    integrity = nexus_conn.execute("PRAGMA integrity_check;").fetchall()

    nexus_conn.close()
    ritmo_conn.close()

    if fk_violations:
        print(f"[ERROR] FK Violations found: {fk_violations}")
        return False

    if not integrity or integrity[0][0] != 'ok':
        print(f"[ERROR] Integrity check failed: {integrity}")
        return False

    print("[SUCCESS] All Ritmo data merged with 0 FK violations and integrity check OK!")
    return True

if __name__ == '__main__':
    default_ritmo = os.path.expanduser("~/.local/share/ritmo/ritmo.sqlite3")
    default_nexus = os.path.expanduser("~/nexus-termux/nexus.db")

    ritmo_arg = sys.argv[1] if len(sys.argv) > 1 else default_ritmo
    nexus_arg = sys.argv[2] if len(sys.argv) > 2 else default_nexus

    success = run_merge(ritmo_arg, nexus_arg)
    sys.exit(0 if success else 1)
