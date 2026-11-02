# Guía de Implementación: Clúster Distribuido en Python con Panel de Control Visual

Este documento detalla los pasos para construir un clúster con **3 o más computadores** utilizando Python. Implementaremos una arquitectura donde podrás visualizar en un **Control Panel** en tiempo real qué recursos aporta cada nodo (núcleos de CPU, memoria RAM, estado de conexión) y repartir cargas de trabajo entre ellos.

---

## 1. Arquitectura del Sistema

Para tener un control total de la interfaz visual y a la vez poder ejecutar tareas distribuidas sin complicaciones, dividiremos los computadores en dos roles:

1. **Nodo Maestro (PC 1 - Control Panel & Orquestador):**
   * Recolecta las métricas de todos los computadores.
   * Muestra el Panel de Control web interactivo (**Streamlit**).
   * Envía tareas a los nodos trabajadores.
2. **Nodos Trabajadores / Agentes (PC 1, PC 2, PC 3...):**
   * Ejecutan un microservicio ligero (**FastAPI** + **psutil**) que reporta el hardware que aportan al clúster y ejecuta las tareas que el Nodo Maestro les asigne.
   * *Nota:* El PC 1 también puede correr el script de agente para aportar sus propios recursos al clúster.

---

## 2. Requisitos Previos y Configuración de Red

Antes de escribir código, asegúrate de cumplir estos pasos en **todos los computadores**:

### 2.1. Red Local o VPN
* **Misma Red LAN:** Conecta todos los computadores al mismo router (preferiblemente por cable Ethernet para menor latencia).
* **Redes Distintas (Opcional):** Si los computadores están en distintas casas o redes, instala **Tailscale** en cada uno y conéctalos a la misma cuenta; esto creará una IP privada virtual para cada equipo sin necesidad de abrir puertos en el router.

### 2.2. Identificar las Direcciones IP
En cada computador, averigua su dirección IP local:
* **Windows:** Abre `cmd` y ejecuta `ipconfig` (busca *Dirección IPv4*, ej. `192.168.1.101`).
* **Linux / macOS:** Abre la terminal y ejecuta `ip a` o `ifconfig`.

Anótalas siguiendo este esquema de referencia:
* **PC 1 (Maestro + Nodo 1):** `192.168.1.101`
* **PC 2 (Nodo 2):** `192.168.1.102`
* **PC 3 (Nodo 3):** `192.168.1.103`

### 2.3. Entorno de Python y Firewall
1. Instala **Python 3.10+** en todos los equipos (procura que sea la misma versión en todos).
2. Crea una carpeta para el proyecto y un entorno virtual en cada PC:
   ```bash
   mkdir cluster_python
   cd cluster_python
   python -m venv venv
   ```
3. Activa el entorno virtual:
   * **Windows:** `venv\Scripts\activate`
   * **Linux/Mac:** `source venv/bin/activate`
4. Instala las dependencias necesarias:
   ```bash
   pip install fastapi uvicorn psutil streamlit requests pandas
   ```
5. **Firewall:** Permite el tráfico en el puerto `8000` (para los agentes) y `8501` (para el panel visual) en el Firewall de Windows o `ufw` en Linux (`sudo ufw allow 8000/tcp`).

---

## 3. Paso 1: Crear el Agente en cada Computador (`agent.py`)

Este archivo debe guardarse y ejecutarse en **todos los computadores que aportarán recursos al clúster** (PC 1, PC 2, PC 3, etc.). Se encarga de leer los recursos físicos del equipo y recibir órdenes de procesamiento.

Crea el archivo `agent.py` con el siguiente código:

```python
import socket
import platform
import time
import math
import psutil
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Agente de Nodo del Clúster")

class TaskRequest(BaseModel):
    task_id: str
    complexity: int  # Número hasta el cual calcular para simular carga

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

if __name__ == "__main__":
    # Se ejecuta en 0.0.0.0 para que sea accesible desde otros PCs en la red
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Cómo iniciar el agente en cada computador:
Abre la terminal en cada PC y ejecuta:
```bash
python agent.py
```
Para verificar que funciona, puedes abrir el navegador en cualquier PC y entrar a `http://<IP_DEL_PC>:8000/metrics`.

---

## 4. Paso 2: Crear el Panel de Control en el PC Principal (`dashboard.py`)

Este archivo solo necesitas crearlo en el **Computador Principal (Maestro)**. Es la interfaz gráfica que suma el poder de todos los computadores, muestra qué aporta cada uno y permite repartir tareas.

Crea el archivo `dashboard.py` con el siguiente código:

```python
import time
from concurrent.futures import ThreadPoolExecutor
import requests
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Cluster Control Panel",
    layout="wide"
)

# --- CONFIGURACIÓN DE NODOS ---
# En la barra lateral podrás agregar o quitar las IPs de tus computadores
st.sidebar.title("Configuración del Clúster")
default_ips = "127.0.0.1:8000\n192.168.1.102:8000\n192.168.1.103:8000"
nodes_input = st.sidebar.text_area(
    "IPs de los Nodos (una por línea):",
    value=default_ips,
    height=120
)
auto_refresh = st.sidebar.checkbox("Actualización automática (cada 2 seg)", value=False)

node_addresses = [ip.strip() for ip in nodes_input.split("\n") if ip.strip()]

def fetch_node_metrics(address):
    """Consulta el endpoint /metrics de un computador del clúster."""
    try:
        response = requests.get(f"http://{address}/metrics", timeout=1.5)
        if response.status_code == 200:
            data = response.json()
            data["address"] = address
            return data
    except Exception:
        pass
    return {
        "hostname": "Desconectado",
        "address": address,
        "os": "-",
        "cpu_physical_cores": 0,
        "cpu_logical_cores": 0,
        "cpu_freq_mhz": 0,
        "cpu_usage_percent": 0.0,
        "ram_total_gb": 0.0,
        "ram_used_gb": 0.0,
        "ram_available_gb": 0.0,
        "ram_usage_percent": 0.0,
        "status": "OFFLINE"
    }

def send_task_to_node(address, task_id, complexity):
    """Envía una subtarea a un nodo específico."""
    try:
        payload = {"task_id": task_id, "complexity": complexity}
        res = requests.post(f"http://{address}/execute", json=payload, timeout=30)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        return {"hostname": address, "task_id": task_id, "error": str(e)}

# --- RECOLECCIÓN DE DATOS EN PARALELO ---
with ThreadPoolExecutor(max_workers=10) as executor:
    nodes_data = list(executor.map(fetch_node_metrics, node_addresses))

online_nodes = [n for n in nodes_data if n["status"] == "ONLINE"]

# --- ENCABEZADO Y PODER TOTAL DEL CLÚSTER ---
st.title("Panel de Control del Clúster en Python")
st.markdown("Monitoreo de recursos aportados por cada computador y ejecución de tareas distribuidas.")

total_logical_cpus = sum(n["cpu_logical_cores"] for n in online_nodes)
total_physical_cpus = sum(n["cpu_physical_cores"] for n in online_nodes)
total_ram = round(sum(n["ram_total_gb"] for n in online_nodes), 2)
available_ram = round(sum(n["ram_available_gb"] for n in online_nodes), 2)
avg_cpu_load = round(
    sum(n["cpu_usage_percent"] for n in online_nodes) / len(online_nodes), 1
) if online_nodes else 0.0

st.subheader("1. Poder Total Combinado del Clúster")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Nodos Activos", f"{len(online_nodes)} / {len(node_addresses)}")
col2.metric("Hilos CPU Totales (Núcleos)", f"{total_logical_cpus} ({total_physical_cpus} físicos)")
col3.metric("RAM Total del Clúster", f"{total_ram} GB", f"{available_ram} GB libres")
col4.metric("Carga Promedio de CPU", f"{avg_cpu_load}%")

st.divider()

# --- APORTE INDIVIDUAL POR COMPUTADOR ---
st.subheader("2. Aporte Individual por Computador (Nodos)")

cols = st.columns(len(nodes_data) if len(nodes_data) > 0 else 1)

for idx, node in enumerate(nodes_data):
    with cols[idx % len(cols)]:
        if node["status"] == "ONLINE":
            st.success(f"**{node['hostname']}** ({node['address']})")
            st.caption(f"Sistema: {node['os']}")
            
            # Qué aporta este PC al total del clúster
            cpu_share = round((node["cpu_logical_cores"] / total_logical_cpus) * 100, 1) if total_logical_cpus else 0
            ram_share = round((node["ram_total_gb"] / total_ram) * 100, 1) if total_ram else 0
            
            st.write(f"**Aporte de CPU:** {node['cpu_logical_cores']} hilos ({cpu_share}% del clúster)")
            st.progress(int(node["cpu_usage_percent"]), text=f"Uso CPU: {node['cpu_usage_percent']}%")
            
            st.write(f"**Aporte de RAM:** {node['ram_total_gb']} GB ({ram_share}% del clúster)")
            st.progress(int(node["ram_usage_percent"]), text=f"Uso RAM: {node['ram_used_gb']} / {node['ram_total_gb']} GB ({node['ram_usage_percent']}%)")
        else:
            st.error(f"**Nodo Offline** ({node['address']})")
            st.write("No se detecta respuesta del agente `agent.py` en esta dirección.")

st.divider()

# --- TABLA COMPARATIVA DE APORTES ---
if online_nodes:
    st.subheader("3. Resumen de Distribución de Recursos")
    df = pd.DataFrame(online_nodes)[[
        "hostname", "address", "os", "cpu_physical_cores", 
        "cpu_logical_cores", "cpu_usage_percent", "ram_total_gb", "ram_available_gb"
    ]]
    df.columns = [
        "Nombre del PC", "Dirección IP", "Sistema Operativo", "Núcleos Físicos",
        "Hilos Lógicos", "Uso CPU (%)", "RAM Total (GB)", "RAM Libre (GB)"
    ]
    st.dataframe(df, use_container_width=True)

st.divider()

# --- LANZADOR DE TAREAS DISTRIBUIDAS ---
st.subheader("4. Prueba de Procesamiento Distribuido")
st.write("Envía un cálculo matemático pesado repartido equitativamente entre todos los computadores activos.")

complexity_per_node = st.slider(
    "Complejidad de la tarea por nodo (iteraciones):", 
    min_value=1_000_000, 
    max_value=25_000_000, 
    value=5_000_000, 
    step=1_000_000
)

if st.button("Repartir y Ejecutar Tarea en el Clúster"):
    if not online_nodes:
        st.warning("No hay nodos activos para procesar la tarea.")
    else:
        with st.spinner(f"Distribuyendo trabajo entre {len(online_nodes)} computadores..."):
            start_cluster = time.time()
            with ThreadPoolExecutor(max_workers=len(online_nodes)) as executor:
                futures = [
                    executor.submit(
                        send_task_to_node, 
                        node["address"], 
                        f"Subtarea-{i+1}", 
                        complexity_per_node
                    )
                    for i, node in enumerate(online_nodes)
                ]
                results = [f.result() for f in futures]
            total_cluster_time = round(time.time() - start_cluster, 4)
        
        st.success(f"¡Trabajo completado por el clúster en {total_cluster_time} segundos!")
        st.json(results)

if auto_refresh:
    time.sleep(2)
    st.rerun()
```

### Cómo iniciar el Panel de Control:
En la terminal del Computador Principal (PC 1), ejecuta:
```bash
streamlit run dashboard.py
```
Se abrirá automáticamente una pestaña en tu navegador en `http://localhost:8501`. En la barra lateral izquierda podrás escribir las IPs de tus 3 o más computadores y ver de inmediato cómo se suman sus recursos.

---

## 5. Escalado Profesional con Ray (Opcional)

Si más adelante necesitas ejecutar modelos de Inteligencia Artificial, procesar millones de filas de datos o compartir memoria entre los computadores de forma automática sin programar los endpoints manualmente, puedes unir esta misma red usando **Ray**:

1. Instala Ray con soporte de panel en todos los PCs:
   ```bash
   pip install "ray[default]"
   ```
2. En el **Computador Principal (PC 1)**, inicia el nodo cabeza:
   ```bash
   ray start --head --port=6379 --dashboard-host=0.0.0.0
   ```
3. En los **Computadores 2 y 3**, únelos al principal:
   ```bash
   ray start --address='192.168.1.101:6379'
   ```
4. Abre `http://localhost:8265` en tu navegador para ver el panel nativo de Ray junto con el panel personalizado que creaste en Streamlit.