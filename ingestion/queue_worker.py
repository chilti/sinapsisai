import os
import sys
import time
import subprocess
from filelock import FileLock, Timeout

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from ingestion.task_queue import pop_next_task, mark_task_completed, mark_task_failed

LOCK_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'worker.lock')
PYTHON_BIN = sys.executable
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

def run_command(cmd, task_id):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [Task {task_id}] Ejecutando: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        error_msg = f"Error code {result.returncode}\nSTDOUT: {result.stdout[-500:]}\nSTDERR: {result.stderr[-500:]}"
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [Task {task_id}] Falló con error:\n{error_msg}")
        raise Exception(error_msg)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [Task {task_id}] Comando completado exitosamente.")

def process_queue():
    while True:
        task = pop_next_task()
        if not task:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Cola vacía. Terminando el worker.")
            break
            
        task_id = task['id']
        task_type = task['type']
        
        try:
            print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Iniciando procesamiento de Task {task_id} ({task_type})")
            
            if task_type == 'academic_pipeline':
                academic = task['academic']
                institution = task['institution']
                
                # 1. sync_works.py
                run_command([PYTHON_BIN, "ingestion/sync_works.py", "--sync-academics", "--name", academic], task_id)
                
                # 2. sync_analytics_pipeline.py
                if institution:
                    run_command([PYTHON_BIN, "ingestion/sync_analytics_pipeline.py", "--academic", academic, "--institution", institution], task_id)
                else:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [Task {task_id}] ADVERTENCIA: No hay institución asociada, el pipeline analítico podría fallar.")
                    run_command([PYTHON_BIN, "ingestion/sync_analytics_pipeline.py", "--academic", academic], task_id)
                    
                # 3. compute_scholar_metrics_ch.py
                if institution:
                    run_command([PYTHON_BIN, "ingestion/compute_scholar_metrics_ch.py", "--academic", academic, "--institution", institution], task_id)
                else:
                    run_command([PYTHON_BIN, "ingestion/compute_scholar_metrics_ch.py", "--academic", academic], task_id)
                    
            elif task_type == 'institution_pipeline':
                institution = task['institution']
                run_command([PYTHON_BIN, "ingestion/compute_scholar_metrics_ch.py", "--institution", institution], task_id)

            elif task_type == 'institution_maps_pipeline':
                # Pipeline completo de reconstrucción de mapas espaciales
                institution = task['institution']
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [Task {task_id}] Reconstruyendo mapas para {institution}...")
                run_command(["bash", "spatial_metrics/run_maps_pipeline.sh"], task_id)
                
            else:
                raise Exception(f"Tipo de tarea desconocido: {task_type}")
                
            mark_task_completed(task_id)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Task {task_id} completada exitosamente.")
            
        except Exception as e:
            mark_task_failed(task_id, str(e))
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Task {task_id} marcada como fallida.")

if __name__ == '__main__':
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    lock = FileLock(LOCK_FILE, timeout=0)
    
    try:
        with lock:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Worker iniciado y lock adquirido.")
            process_queue()
    except Timeout:
        # Ya hay un worker corriendo. Termina silenciosamente.
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Otro worker ya está en ejecución. Saliendo silenciosamente.")
        sys.exit(0)
