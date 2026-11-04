import socket
import platform
import time
import math
import psutil
from typing import Any
from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import numpy as np
import uvicorn
import discovery
import shared_hub

app = FastAPI(title="Agente de Nodo del Clúster")

class TaskRequest(BaseModel):
    task_id: str
    complexity: int = 0  # Número hasta el cual calcular para simular carga
    task_type: str = "math"  # "math", "csv_analysis", "full_dataset_analysis"
    chunk_data: Any = []  # Puede ser lista simple o dict de columnas para dataset completo
    column_name: str = ""
    normalization_type: str = "none"

class NodeRegistration(BaseModel):
    address: str
    hostname: str = ""

class SharedAccessRequest(BaseModel):
    hostname: str
    ip: str = "127.0.0.1"
    action: str = "Acceso general"

class SharedNoteRequest(BaseModel):
    author: str
    message: str
    tag: str = "Info"
    ip: str = "127.0.0.1"

class SharedVariableRequest(BaseModel):
    key: str
    value: Any
    updated_by: str
    ip: str = "127.0.0.1"

@app.get("/metrics")
def get_metrics():
    """Devuelve qué aporta este computador y su uso actual en tiempo real."""
    vm = psutil.virtual_memory()
    cpu_freq = psutil.cpu_freq()
    
    return {
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "cpu_physical_cores": psutil.cpu_count(logical=False) or 1,
        "cpu_logical_cores": psutil.cpu_count(logical=True) or 1,
        "cpu_freq_mhz": round(cpu_freq.current, 0) if cpu_freq else 0,
        "cpu_usage_percent": psutil.cpu_percent(interval=0.2),
        "ram_total_gb": round(vm.total / (1024 ** 3), 2),
        "ram_used_gb": round(vm.used / (1024 ** 3), 2),
        "ram_available_gb": round(vm.available / (1024 ** 3), 2),
        "ram_usage_percent": vm.percent,
        "status": "ONLINE"
    }

@app.post("/execute")
def execute_task(task: TaskRequest):
    """Ejecuta una tarea enviada por el nodo maestro y mide el tiempo de cómputo."""
    start_time = time.time()
    try:
        shared_hub.record_access(socket.gethostname(), "127.0.0.1", f"Procesando {task.task_id} ({task.task_type})")
    except Exception:
        pass
    
    # 1. ANÁLISIS DEL DATASET COMPLETO (TODAS LAS COLUMNAS)
    if task.task_type == "full_dataset_analysis":
        if isinstance(task.chunk_data, dict):
            df_chunk = pd.DataFrame(task.chunk_data)
        elif isinstance(task.chunk_data, list) and task.chunk_data:
            if isinstance(task.chunk_data[0], dict):
                df_chunk = pd.DataFrame(task.chunk_data)
            else:
                df_chunk = pd.DataFrame({task.column_name or "valor": task.chunk_data})
        else:
            df_chunk = pd.DataFrame()

        num_cols = df_chunk.select_dtypes(include=[np.number]).columns.tolist()
        cat_cols = df_chunk.select_dtypes(exclude=[np.number]).columns.tolist()

        numeric_stats = {}
        for col in num_cols:
            s = df_chunk[col].dropna()
            cnt = len(s)
            if cnt > 0:
                sum_val = float(s.sum())
                sum_sq_val = float((s ** 2).sum())
                min_val = float(s.min())
                max_val = float(s.max())
                mean_val = float(s.mean())
                std_val = float(s.std(ddof=0)) if cnt > 1 else 0.0
            else:
                sum_val = sum_sq_val = min_val = max_val = mean_val = std_val = 0.0

            numeric_stats[col] = {
                "count": cnt,
                "sum": round(sum_val, 4),
                "sum_sq": round(sum_sq_val, 4),
                "min": round(min_val, 4),
                "max": round(max_val, 4),
                "mean": round(mean_val, 4),
                "std": round(std_val, 4)
            }

        # Simulación de carga computacional analítica si complexity > 0
        if task.complexity > 0 and len(num_cols) > 0:
            for col in num_cols:
                limit = min(len(df_chunk[col].dropna()), task.complexity)
                _ = sum(math.isqrt(int(abs(x) * 100)) for x in df_chunk[col].dropna().iloc[:limit])

        categorical_stats = {}
        for col in cat_cols:
            categorical_stats[col] = df_chunk[col].value_counts().head(5).to_dict()

        elapsed_time = round(time.time() - start_time, 4)
        return {
            "hostname": socket.gethostname(),
            "task_id": task.task_id,
            "task_type": "full_dataset_analysis",
            "rows_processed": len(df_chunk),
            "columns_processed": list(df_chunk.columns),
            "numeric_stats": numeric_stats,
            "categorical_stats": categorical_stats,
            "elapsed_seconds": elapsed_time
        }

    # 2. ANÁLISIS DE UNA SOLA COLUMNA
    if task.task_type == "csv_analysis" and task.chunk_data:
        nums = []
        if isinstance(task.chunk_data, list):
            for x in task.chunk_data:
                try:
                    nums.append(float(x))
                except (ValueError, TypeError):
                    continue

        count = len(nums)
        if count > 0:
            total_sum = sum(nums)
            mean = total_sum / count
            variance = sum((x - mean) ** 2 for x in nums) / count
            std_dev = math.sqrt(variance)
            min_val = min(nums)
            max_val = max(nums)
            
            if task.complexity > 0:
                limit = min(count, task.complexity)
                _ = sum(math.isqrt(int(abs(x) * 100)) for x in nums[:limit])
        else:
            total_sum = mean = std_dev = min_val = max_val = 0.0

        elapsed_time = round(time.time() - start_time, 4)
        return {
            "hostname": socket.gethostname(),
            "task_id": task.task_id,
            "task_type": "csv_analysis",
            "column": task.column_name,
            "rows_processed": count,
            "sum": round(total_sum, 4),
            "mean": round(mean, 4),
            "std": round(std_dev, 4),
            "min": round(min_val, 4),
            "max": round(max_val, 4),
            "elapsed_seconds": elapsed_time
        }

    # 3. TAREA MATEMÁTICA ITERATIVA POR DEFECTO
    resultado = sum(math.isqrt(i) for i in range(task.complexity))
    elapsed_time = round(time.time() - start_time, 4)
    return {
        "hostname": socket.gethostname(),
        "task_id": task.task_id,
        "task_type": "math",
        "elapsed_seconds": elapsed_time,
        "result_sample": resultado
    }

@app.post("/register_node")
def register_node(node: NodeRegistration):
    """Registra automáticamente un nuevo nodo trabajador en la lista compartida."""
    clean_addr = node.address.strip()
    added = discovery.add_node_to_list(clean_addr)
    return {
        "status": "SUCCESS",
        "address": clean_addr,
        "registered": added
    }

@app.post("/unregister_node")
def unregister_node(node: NodeRegistration):
    """Desvincula un nodo de la lista al apagarse."""
    clean_addr = node.address.strip()
    removed = discovery.remove_node_from_list(clean_addr)
    return {
        "status": "SUCCESS",
        "address": clean_addr,
        "removed": removed
    }

@app.get("/nodes")
def get_nodes():
    """Retorna la lista actual de nodos registrados."""
    return {"nodes": discovery.load_nodes_list()}

# --- ENDPOINTS DEL ENTORNO COMÚN Y ESPACIO COMPARTIDO ---

@app.get("/shared/active_pcs")
def get_shared_active_pcs():
    """Retorna los computadores que están accediendo activamente."""
    return {"active_pcs": shared_hub.get_active_sessions()}

@app.post("/shared/record_access")
def post_shared_access(req: SharedAccessRequest):
    """Registra la presencia o actividad de un computador."""
    shared_hub.record_access(req.hostname, req.ip, req.action)
    return {"status": "SUCCESS"}

@app.get("/shared/notes")
def get_shared_notes():
    """Retorna las notas de la pizarra compartida."""
    return {"notes": shared_hub.get_notes()}

@app.post("/shared/notes")
def post_shared_note(req: SharedNoteRequest):
    """Agrega una nota a la pizarra compartida."""
    note = shared_hub.add_note(req.author, req.ip, req.message, req.tag)
    return {"status": "SUCCESS", "note": note}

@app.get("/shared/variables")
def get_shared_variables():
    """Retorna las variables compartidas del clúster."""
    return {"variables": shared_hub.get_variables()}

@app.post("/shared/variables")
def post_shared_variable(req: SharedVariableRequest):
    """Establece o actualiza una variable compartida."""
    shared_hub.set_variable(req.key, req.value, req.updated_by, req.ip)
    return {"status": "SUCCESS"}

@app.get("/shared/files")
def get_shared_files_list():
    """Retorna la lista de archivos en el repositorio compartido."""
    return {"files": shared_hub.get_shared_files()}

if __name__ == "__main__":
    # Se ejecuta en 0.0.0.0 para que sea accesible desde otros PCs en la red
    uvicorn.run(app, host="0.0.0.0", port=8000)
