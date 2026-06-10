import sqlite3
import os
import subprocess
import datetime
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'task_queue.db')
WORKER_SCRIPT = os.path.join(os.path.dirname(__file__), 'queue_worker.py')

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tabla de colas
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_type TEXT NOT NULL,
        academic TEXT,
        institution TEXT,
        orcid TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Tabla de contadores institucionales
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS institution_counters (
        institution TEXT PRIMARY KEY,
        count INTEGER NOT NULL DEFAULT 0
    )
    ''')
    
    conn.commit()
    conn.close()

def push_academic_pipeline(academic_name: str, institution_name: str, orcid: str):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Encolar tarea académica
    cursor.execute('''
        INSERT INTO queue (task_type, academic, institution, orcid)
        VALUES ('academic_pipeline', ?, ?, ?)
    ''', (academic_name, institution_name, orcid))
    
    # 2. Incrementar contador institucional
    if institution_name:
        cursor.execute('''
            INSERT INTO institution_counters (institution, count)
            VALUES (?, 1)
            ON CONFLICT(institution) DO UPDATE SET count = count + 1
        ''', (institution_name,))
        
        cursor.execute('SELECT count FROM institution_counters WHERE institution = ?', (institution_name,))
        row = cursor.fetchone()
        count = row[0] if row else 0

        # Umbral 1 cada 3 → recalcular métricas bibliométricas
        if count % 3 == 0:
            cursor.execute('''
                INSERT INTO queue (task_type, institution)
                VALUES ('institution_pipeline', ?)
            ''', (institution_name,))
            print(f"[TaskQueue] Múltiplo de 3 ({count}) para {institution_name}. Métricas institucionales encoladas.")

        # Umbral 2 en 10 → recalcular mapas UMAP completos y resetear contador
        if count >= 10:
            cursor.execute('''
                INSERT INTO queue (task_type, institution)
                VALUES ('institution_maps_pipeline', ?)
            ''', (institution_name,))
            cursor.execute('''
                UPDATE institution_counters SET count = 0 WHERE institution = ?
            ''', (institution_name,))
            print(f"[TaskQueue] Umbral de 10 alcanzado para {institution_name}. Pipeline de mapas UMAP encolado y contador reiniciado.")
            
    conn.commit()
    conn.close()
    print(f"[TaskQueue] Tarea encolada para {academic_name} (ORCID: {orcid}).")

def trigger_worker_in_background():
    """Lanza el worker en segundo plano (fire and forget). Si ya está corriendo, el worker lo ignorará usando filelock."""
    python_bin = sys.executable
    print(f"[TaskQueue] Lanzando queue_worker.py en segundo plano...")
    subprocess.Popen([python_bin, WORKER_SCRIPT], 
                     stdout=subprocess.DEVNULL, 
                     stderr=subprocess.DEVNULL, 
                     start_new_session=True)

def pop_next_task():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    conn.execute('BEGIN EXCLUSIVE')
    
    try:
        # Priorizamos academic_pipeline antes que institution_pipeline
        cursor.execute('''
            SELECT id, task_type, academic, institution, orcid 
            FROM queue 
            WHERE status = 'pending' 
            ORDER BY 
              CASE WHEN task_type = 'academic_pipeline' THEN 1 ELSE 2 END,
              created_at ASC 
            LIMIT 1
        ''')
        task = cursor.fetchone()
        if task:
            cursor.execute("UPDATE queue SET status = 'processing', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task[0],))
            conn.commit()
            return {
                'id': task[0],
                'type': task[1],
                'academic': task[2],
                'institution': task[3],
                'orcid': task[4]
            }
        else:
            conn.commit()
            return None
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def mark_task_completed(task_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE queue SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

def mark_task_failed(task_id: int, error_msg: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE queue SET status = 'failed', updated_at = CURRENT_TIMESTAMP, orcid = ? WHERE id = ?", (f"ERROR: {error_msg}", task_id))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    # test
    init_db()
    # push_academic_pipeline("Jose Luis Jimenez", "Universidad Nacional Autónoma de México", "0000-0000-0000-0000")
    # trigger_worker_in_background()
