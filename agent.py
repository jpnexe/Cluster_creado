import socket
import platform
import time
import math
import psutil
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import discovery

app = FastAPI(title="Agente de Nodo del Clúster")

class TaskRequest(BaseModel):
    task_id: str
    complexity: int  # Número hasta el cual calcular para simular carga

class NodeRegistration(BaseModel):
    address: str
    hostname: str = ""

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
    
    # Simulación de carga intensiva de CPU (cálculo matemático)
    resultado = sum(math.isqrt(i) for i in range(task.complexity))
    
    elapsed_time = round(time.time() - start_time, 4)
    return {
        "hostname": socket.gethostname(),
        "task_id": task.task_id,
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

if __name__ == "__main__":
    # Se ejecuta en 0.0.0.0 para que sea accesible desde otros PCs en la red
    uvicorn.run(app, host="0.0.0.0", port=8000)
