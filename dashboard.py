import socket
import time
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import requests
import streamlit as st
import discovery

st.set_page_config(
    page_title="Cluster Control Panel",
    page_icon="🖥️",
    layout="wide"
)

# Iniciar servidor de descubrimiento UDP en el Maestro si aún no está corriendo
if "discovery_server" not in st.session_state:
    try:
        disc = discovery.MasterDiscoveryServer(
            master_ip=discovery.get_primary_ip(),
            hostname=socket.gethostname(),
            dashboard_port=8501,
            agent_port=8000
        )
        disc.start()
        st.session_state["discovery_server"] = disc
    except Exception:
        pass

def get_local_ips():
    """Detecta las IPs locales para facilitar la configuración en la red."""
    ips = []
    try:
        import psutil
        for iface_name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    is_apipa = addr.address.startswith("169.254.")
                    ips.append((iface_name, addr.address, is_apipa))
    except Exception:
        pass
    if not ips:
        try:
            h = socket.gethostname()
            ip = socket.gethostbyname(h)
            if not ip.startswith("127."):
                ips.append(("Host", ip, False))
        except Exception:
            pass
    ips.sort(key=lambda x: (x[2], x[0]))
    return ips

# --- CONFIGURACIÓN DE NODOS EN LA BARRA LATERAL ---
st.sidebar.title("Configuración del Clúster")

# Cargar nodos guardados y registrados automáticamente
saved_nodes = discovery.load_nodes_list()
if not saved_nodes:
    saved_nodes = ["127.0.0.1:8000"]
    discovery.save_nodes_list(saved_nodes)

default_ips_str = "\n".join(saved_nodes)

nodes_input = st.sidebar.text_area(
    "IPs de los Nodos (una por línea):",
    value=default_ips_str,
    height=120,
    help="Puedes agregar o quitar IPs manualmente. Los nodos que ejecuten Run.py se agregarán aquí automáticamente."
)

auto_refresh = st.sidebar.checkbox("Actualización automática (cada 2 seg)", value=False)

node_addresses = [ip.strip() for ip in nodes_input.split("\n") if ip.strip()]

# Sincronizar cambios manuales del cuadro de texto con nodes.json
if set(node_addresses) != set(saved_nodes):
    discovery.save_nodes_list(node_addresses)

st.sidebar.markdown("---")
st.sidebar.info("💡 **Descubrimiento Activo:** Nuevos PCs que ejecuten `Run.py` detectarán este clúster y se registrarán de forma automática.")

def fetch_node_metrics(address):
    """Consulta el endpoint /metrics de un computador del clúster."""
    clean_addr = address.replace("http://", "").replace("https://", "")
    try:
        t0 = time.time()
        response = requests.get(f"http://{clean_addr}/metrics", timeout=1.8)
        lat = round((time.time() - t0) * 1000, 1)
        if response.status_code == 200:
            data = response.json()
            data["address"] = clean_addr
            data["latency_ms"] = lat
            return data
    except Exception:
        pass
    return {
        "hostname": "Desconectado",
        "address": clean_addr,
        "os": "-",
        "cpu_physical_cores": 0,
        "cpu_logical_cores": 0,
        "cpu_freq_mhz": 0,
        "cpu_usage_percent": 0.0,
        "ram_total_gb": 0.0,
        "ram_used_gb": 0.0,
        "ram_available_gb": 0.0,
        "ram_usage_percent": 0.0,
        "status": "OFFLINE",
        "latency_ms": 0.0
    }

def send_task_to_node(address, task_id, complexity):
    """Envía una subtarea a un nodo específico."""
    clean_addr = address.replace("http://", "").replace("https://", "")
    try:
        payload = {"task_id": task_id, "complexity": complexity}
        res = requests.post(f"http://{clean_addr}/execute", json=payload, timeout=30)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        return {"hostname": clean_addr, "task_id": task_id, "error": str(e)}

# --- RECOLECCIÓN DE DATOS EN PARALELO ---
with ThreadPoolExecutor(max_workers=15) as executor:
    nodes_data = list(executor.map(fetch_node_metrics, node_addresses))

online_nodes = [n for n in nodes_data if n["status"] == "ONLINE"]

# Botón en sidebar para limpiar desconectados
if st.sidebar.button("🗑️ Eliminar Nodos Desconectados"):
    active_addrs = [n["address"] for n in online_nodes]
    if "127.0.0.1:8000" not in active_addrs:
        active_addrs.append("127.0.0.1:8000")
    discovery.save_nodes_list(active_addrs)
    st.rerun()

# --- PESTAÑAS PRINCIPALES ---
tab_monitor, tab_guide = st.tabs([
    "📊 Panel de Control y Monitoreo", 
    "🚀 Guía de Conexión de Nuevos PCs"
])

# =========================================================================
# PESTAÑA 1: PANEL DE CONTROL Y MONITOREO
# =========================================================================
with tab_monitor:
    st.title("Panel de Control del Clúster en Python")
    st.markdown("Monitoreo de recursos aportados por cada computador y ejecución de tareas distribuidas en tiempo real.")

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
    col2.metric("Hilos CPU Totales", f"{total_logical_cpus} ({total_physical_cpus} físicos)")
    col3.metric("RAM Total del Clúster", f"{total_ram} GB", f"{available_ram} GB libres")
    col4.metric("Carga Promedio CPU", f"{avg_cpu_load}%")

    st.divider()

    # --- APORTE INDIVIDUAL POR COMPUTADOR ---
    st.subheader("2. Aporte Individual por Computador (Nodos)")
    cols = st.columns(len(nodes_data) if len(nodes_data) > 0 else 1)

    for idx, node in enumerate(nodes_data):
        with cols[idx % len(cols)]:
            if node["status"] == "ONLINE":
                st.success(f"🟢 **{node['hostname']}**")
                st.caption(f"Dirección: `{node['address']}` | Latencia: {node.get('latency_ms', 0)} ms")
                st.caption(f"Sistema: {node['os']}")
                
                cpu_share = round((node["cpu_logical_cores"] / total_logical_cpus) * 100, 1) if total_logical_cpus else 0
                ram_share = round((node["ram_total_gb"] / total_ram) * 100, 1) if total_ram else 0
                
                st.write(f"**Aporte CPU:** {node['cpu_logical_cores']} hilos ({cpu_share}%)")
                cpu_val = min(max(int(node["cpu_usage_percent"]), 0), 100)
                st.progress(cpu_val, text=f"Uso CPU: {node['cpu_usage_percent']}%")
                
                st.write(f"**Aporte RAM:** {node['ram_total_gb']} GB ({ram_share}%)")
                ram_val = min(max(int(node["ram_usage_percent"]), 0), 100)
                st.progress(ram_val, text=f"Uso RAM: {node['ram_used_gb']} / {node['ram_total_gb']} GB ({node['ram_usage_percent']}%)")
            else:
                st.error(f"🔴 **Nodo Offline**")
                st.caption(f"Dirección: `{node['address']}`")
                st.write("No se detecta respuesta del agente en este puerto.")
                st.caption("Verifica que el agente esté corriendo o elimina el nodo de la barra lateral.")

    st.divider()

    # --- TABLA COMPARATIVA DE APORTES ---
    if online_nodes:
        st.subheader("3. Resumen de Distribución de Recursos")
        df = pd.DataFrame(online_nodes)[[
            "hostname", "address", "os", "cpu_physical_cores", 
            "cpu_logical_cores", "cpu_usage_percent", "ram_total_gb", "ram_available_gb", "latency_ms"
        ]]
        df.columns = [
            "Nombre del PC", "Dirección IP", "Sistema Operativo", "Núcleos Físicos",
            "Hilos Lógicos", "Uso CPU (%)", "RAM Total (GB)", "RAM Libre (GB)", "Latencia (ms)"
        ]
        st.dataframe(df, use_container_width=True)
        st.divider()

    # --- LANZADOR DE TAREAS DISTRIBUIDAS ---
    st.subheader("4. Prueba de Procesamiento Distribuido")
    st.write("Envía un cálculo matemático intensivo repartido equitativamente entre todos los computadores activos.")

    complexity_per_node = st.slider(
        "Complejidad de la tarea por nodo (iteraciones matemáticas):", 
        min_value=1_000_000, 
        max_value=25_000_000, 
        value=5_000_000, 
        step=1_000_000
    )

    if st.button("🚀 Repartir y Ejecutar Tarea en el Clúster"):
        if not online_nodes:
            st.warning("No hay nodos activos para procesar la tarea.")
        else:
            with st.spinner(f"Distribuyendo trabajo entre {len(online_nodes)} computadores simultáneamente..."):
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
            
            st.success(f"¡Trabajo completado exitosamente por el clúster en {total_cluster_time} segundos!")
            st.json(results)

# =========================================================================
# PESTAÑA 2: GUÍA VISUAL PASO A PASO PARA CONECTAR OTROS PCS
# =========================================================================
with tab_guide:
    st.title("Guía Visual: Cómo Conectar Nuevos Computadores al Clúster")
    st.markdown("""
    ¡Ahora es más fácil que nunca! El sistema cuenta con **detección y autoconexión automática** por red local.
    """)

    # Información de red de este equipo
    st.subheader("📌 Información de este Computador (Maestro)")
    local_ips = get_local_ips()
    c_m1, c_m2 = st.columns(2)
    with c_m1:
        st.info(f"**Nombre del Host:** `{socket.gethostname()}`")
    with c_m2:
        if local_ips:
            ip_str = " | ".join([f"{iface}: `{ip}`" for iface, ip, is_a in local_ips if not is_a])
            st.info(f"**IPs Locales:** {ip_str if ip_str else '127.0.0.1'}")
        else:
            st.info("**IP Local:** `127.0.0.1`")

    st.markdown("---")

    # Pasos estructurados con autoconexión
    st.markdown("### ⚡ Conexión Automática con `Run.py` (Recomendada)")
    st.success("""
    **En el nuevo computador:**
    1. Asegúrate de estar conectado a la misma red Wi-Fi o red LAN.
    2. Ejecuta simplemente: `python Run.py`
    3. `Run.py` detectará este computador Maestro automáticamente y te preguntará:
       `¿Deseas conectar este equipo al clúster? [S/n]`
    4. Pulsa **Enter** o escribe **S** y ¡listo! El nuevo computador se registrará de inmediato en este panel sin necesidad de escribir IPs a mano.
    """)

    col_p1, col_p2 = st.columns(2)

    with col_p1:
        with st.container(border=True):
            st.markdown("### 📁 Archivos Necesarios en el Otro PC")
            st.markdown("""
            Solo necesitas copiar estos archivos al nuevo equipo:
            * `Run.py`
            * `agent.py`
            * `discovery.py`
            * `requirements.txt`
            """)

    with col_p2:
        with st.container(border=True):
            st.markdown("### 🛡️ Firewall (Puerto 8000)")
            st.markdown("""
            Si Windows solicita permisos de red, marca **Redes privadas** y presiona **Permitir acceso**.
            O ejecuta en PowerShell como Administrador:
            """)
            st.code('New-NetFirewallRule -DisplayName "Cluster Agent 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow', language="powershell")

    st.markdown("---")

    # Probador de Conexión en Vivo
    st.subheader("🧪 Probador Manual de Conexión en Vivo")
    st.markdown("Si deseas verificar manualmente la conectividad hacia un computador específico:")

    col_test1, col_test2 = st.columns([3, 1])
    with col_test1:
        test_address = st.text_input(
            "Dirección IP y puerto del nuevo nodo a probar:",
            placeholder="Ejemplo: 192.168.101.45:8000",
            key="test_node_ip"
        )
    with col_test2:
        st.write("")
        st.write("")
        btn_test = st.button("🔍 Probar Conexión", use_container_width=True)

    if btn_test:
        if not test_address.strip():
            st.warning("Por favor ingresa una dirección IP válida (ej. `192.168.101.45:8000`).")
        else:
            clean_test = test_address.strip().replace("http://", "").replace("https://", "")
            if ":" not in clean_test:
                clean_test = f"{clean_test}:8000"
            
            with st.spinner(f"Contactando a `http://{clean_test}/metrics`..."):
                try:
                    start_t = time.time()
                    resp = requests.get(f"http://{clean_test}/metrics", timeout=2.5)
                    lat_ms = round((time.time() - start_t) * 1000, 1)

                    if resp.status_code == 200:
                        m_data = resp.json()
                        st.success(f"¡Conexión Exitosa con el nodo! (Latencia: {lat_ms} ms)")
                        st.json({
                            "Estado": "ONLINE",
                            "Equipo (Hostname)": m_data.get("hostname"),
                            "Sistema Operativo": m_data.get("os"),
                            "Núcleos Lógicos de CPU": m_data.get("cpu_logical_cores"),
                            "Frecuencia CPU (MHz)": m_data.get("cpu_freq_mhz"),
                            "Memoria RAM Total": f"{m_data.get('ram_total_gb')} GB",
                            "Memoria RAM Libre": f"{m_data.get('ram_available_gb')} GB"
                        })
                        # Añadir automáticamente si no está
                        if discovery.add_node_to_list(clean_test):
                            st.info(f"✅ Se añadió `{clean_test}` a la lista de nodos del clúster.")
                    else:
                        st.error(f"El nodo respondió pero devolvió código HTTP {resp.status_code}.")
                except requests.exceptions.ConnectTimeout:
                    st.error(f"❌ Tiempo de espera agotado al conectar a `{clean_test}`. Es probable que el Firewall de Windows esté bloqueando el puerto 8000 en el otro PC o que no estén en la misma red.")
                except requests.exceptions.ConnectionError:
                    st.error(f"❌ Conexión rechazada en `{clean_test}`. Verifica que ejecutaste el agente en ese equipo.")
                except Exception as e:
                    st.error(f"❌ Error al conectar: {str(e)}")

if auto_refresh:
    time.sleep(2)
    st.rerun()
