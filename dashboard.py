import os
import socket
import time
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np
import requests
import streamlit as st
import discovery

st.set_page_config(
    page_title="Cluster Control Panel & Data Analytics",
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

auto_refresh = st.sidebar.checkbox("Actualización automática de métricas (cada 2 seg)", value=False)

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

def send_task_to_node(address, task_id, complexity, task_type="math", chunk_data=None, column_name=""):
    """Envía una subtarea de cálculo o análisis a un nodo específico."""
    clean_addr = address.replace("http://", "").replace("https://", "")
    try:
        payload = {
            "task_id": task_id,
            "complexity": complexity,
            "task_type": task_type,
            "chunk_data": chunk_data or [],
            "column_name": column_name
        }
        res = requests.post(f"http://{clean_addr}/execute", json=payload, timeout=40)
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
tab_monitor, tab_csv, tab_guide = st.tabs([
    "📊 Panel de Control y Monitoreo", 
    "📁 Análisis de Datos y Carga CSV",
    "🚀 Guía de Conexión de Nuevos PCs"
])

# =========================================================================
# PESTAÑA 1: PANEL DE CONTROL Y MONITOREO DEL HARDWARE
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
        df_nodes = pd.DataFrame(online_nodes)[[
            "hostname", "address", "os", "cpu_physical_cores", 
            "cpu_logical_cores", "cpu_usage_percent", "ram_total_gb", "ram_available_gb", "latency_ms"
        ]]
        df_nodes.columns = [
            "Nombre del PC", "Dirección IP", "Sistema Operativo", "Núcleos Físicos",
            "Hilos Lógicos", "Uso CPU (%)", "RAM Total (GB)", "RAM Libre (GB)", "Latencia (ms)"
        ]
        st.dataframe(df_nodes, use_container_width=True)
        st.divider()

    # --- LANZADOR DE TAREAS MATEMÁTICAS ---
    st.subheader("4. Prueba de Procesamiento Sintético")
    st.write("Envía un cálculo matemático intensivo repartido equitativamente entre todos los computadores activos.")

    complexity_per_node = st.slider(
        "Complejidad de la tarea por nodo (iteraciones matemáticas):", 
        min_value=1_000_000, 
        max_value=25_000_000, 
        value=5_000_000, 
        step=1_000_000
    )

    if st.button("🚀 Repartir y Ejecutar Cálculo Matemático"):
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
# PESTAÑA 2: CARGA, ANÁLISIS ESTADÍSTICO Y PROCESAMIENTO DE CSVs
# =========================================================================
with tab_csv:
    st.title("📁 Carga, Análisis Estadístico y Procesamiento Distribuido de CSVs")
    st.markdown("""
    Sube **uno o varios archivos CSV** para explorar sus estadísticas descriptivas, consolidar lotes de datos y 
    **repartir su procesamiento analítico entre los nodos activos de tu clúster**.
    """)

    # --- SECCIÓN DE CARGA / GENERACIÓN DE DATOS ---
    c_upload1, c_upload2 = st.columns([3, 2])

    with c_upload1:
        uploaded_files = st.file_uploader(
            "Selecciona o arrastra uno o varios archivos CSV:", 
            type=["csv"],
            accept_multiple_files=True,
            help="Puedes seleccionar múltiples archivos CSV simultáneamente (coma o punto y coma)."
        )

    with c_upload2:
        st.write("**¿Deseas probar con datos de ejemplo?**")
        st.caption("Carga lotes generados para pruebas de estrés:")
        col_g1, col_g2, col_g3 = st.columns(3)
        with col_g1:
            if st.button("📦 Lote de 3 CSVs", use_container_width=True):
                np.random.seed(42)
                demo_files = {}
                nodos = ["Nodo-Alpha", "Nodo-Beta", "Nodo-Gamma"]
                for i, nodo in enumerate(nodos, 1):
                    n_rows = 5_000
                    demo_files[f"metricas_{nodo.lower()}_mes{i}.csv"] = pd.DataFrame({
                        "id_registro": range(1, n_rows + 1),
                        "servidor": nodo,
                        "cpu_uso_pct": np.random.uniform(10.0, 95.0, n_rows).round(2),
                        "memoria_ram_mb": np.random.randint(2048, 16384, n_rows),
                        "peticiones_segundo": np.random.poisson(120 + i * 20, n_rows),
                        "tiempo_respuesta_ms": np.random.normal(38.0 + i * 5, 10.0, n_rows).round(2),
                        "temperatura_c": np.random.uniform(40.0, 80.0, n_rows).round(1),
                        "estado": np.random.choice(["OK", "WARNING", "CRITICAL"], n_rows, p=[0.88, 0.10, 0.02])
                    })
                st.session_state["loaded_csv_files"] = demo_files
                st.rerun()

        with col_g2:
            test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archivos_prueba_csv")
            if os.path.exists(test_dir):
                csv_files_found = [f for f in os.listdir(test_dir) if f.endswith(".csv")]
                if st.button(f"📂 Cargar {len(csv_files_found)} CSVs", use_container_width=True):
                    with st.spinner(f"Cargando {len(csv_files_found)} archivos CSV en paralelo..."):
                        def _read_csv_file(fname):
                            return fname, pd.read_csv(os.path.join(test_dir, fname))
                        with ThreadPoolExecutor(max_workers=16) as executor:
                            loaded_dict = dict(executor.map(_read_csv_file, csv_files_found))
                        st.session_state["loaded_csv_files"] = loaded_dict
                    st.rerun()

        with col_g3:
            if "loaded_csv_files" in st.session_state or "active_df" in st.session_state:
                if st.button("🗑️ Limpiar Todo", use_container_width=True):
                    if "loaded_csv_files" in st.session_state:
                        del st.session_state["loaded_csv_files"]
                    if "active_df" in st.session_state:
                        del st.session_state["active_df"]
                    if "dataset_name" in st.session_state:
                        del st.session_state["dataset_name"]
                    st.rerun()

    # Procesar archivos subidos por el usuario
    if uploaded_files:
        parsed_files = {}
        for uf in uploaded_files:
            try:
                content = uf.getvalue()
                sample = content[:4096].decode("utf-8", errors="ignore")
                sep = ";" if sample.count(";") > sample.count(",") else ","
                df_item = pd.read_csv(io.BytesIO(content), sep=sep)
                parsed_files[uf.name] = df_item
            except Exception as e:
                st.error(f"Error al leer '{uf.name}': {e}")
        
        if parsed_files:
            st.session_state["loaded_csv_files"] = parsed_files

    # Si hay archivos cargados en el estado
    if "loaded_csv_files" in st.session_state and st.session_state["loaded_csv_files"]:
        files_dict = st.session_state["loaded_csv_files"]
        num_files = len(files_dict)

        # Si hay más de 1 archivo, mostrar resumen del lote y selector de modo
        if num_files > 1:
            st.markdown("---")
            st.subheader(f"📑 Lote de Archivos Cargados ({num_files} archivos)")
            
            summary_list = []
            for fname, f_df in files_dict.items():
                summary_list.append({
                    "Nombre de Archivo": fname,
                    "Total Filas": len(f_df),
                    "Total Columnas": len(f_df.columns),
                    "Memoria": f"{round(f_df.memory_usage(deep=True).sum() / (1024 ** 2), 2)} MB",
                    "Columnas Numéricas": len(f_df.select_dtypes(include=[np.number]).columns)
                })
            st.dataframe(pd.DataFrame(summary_list), use_container_width=True)

            c_mode1, c_mode2 = st.columns([2, 3])
            with c_mode1:
                analysis_mode = st.radio(
                    "Opciones de Análisis:",
                    ["🔗 Unir todos los archivos (Dataset Consolidado)", "📄 Analizar un archivo específico"],
                    horizontal=False
                )

            with c_mode2:
                if analysis_mode == "📄 Analizar un archivo específico":
                    selected_file = st.selectbox("Selecciona qué archivo deseas inspeccionar:", list(files_dict.keys()))
                    df = files_dict[selected_file]
                    dataset_name = selected_file
                else:
                    # Unir todos agregando columna de archivo de origen
                    combined_dfs = []
                    for fname, f_df in files_dict.items():
                        combined_dfs.append(f_df.assign(archivo_origen=fname))
                    df = pd.concat(combined_dfs, ignore_index=True)
                    dataset_name = f"Consolidado ({num_files} archivos unidos - {len(df):,} filas)"
                    st.success(f"✅ Se han concatenado **{num_files} archivos** en un único dataset de **{len(df):,} filas**.")
        else:
            first_fname = list(files_dict.keys())[0]
            df = files_dict[first_fname]
            dataset_name = first_fname

        st.session_state["active_df"] = df
        st.session_state["dataset_name"] = dataset_name

    # Si hay un DataFrame activo para analizar
    if "active_df" in st.session_state:
        df = st.session_state["active_df"]
        dataset_name = st.session_state.get("dataset_name", "Archivo CSV")

        st.markdown("---")
        st.subheader(f"📊 Estadísticas del Dataset: `{dataset_name}`")

        # 1. TARJETAS DE MÉTRICAS RÁPIDAS
        n_rows, n_cols = df.shape
        mem_mb = round(df.memory_usage(deep=True).sum() / (1024 ** 2), 2)
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        categorical_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()
        null_count = df.isnull().sum().sum()
        null_pct = round((null_count / (n_rows * n_cols)) * 100, 2) if (n_rows * n_cols) > 0 else 0

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Filas", f"{n_rows:,}")
        m2.metric("Total Columnas", f"{n_cols}")
        m3.metric("Tamaño en Memoria", f"{mem_mb} MB")
        m4.metric("Variables Numéricas", f"{len(numeric_cols)}")
        m5.metric("Valores Nulos", f"{null_count} ({null_pct}%)")

        st.markdown("---")

        # 2. VISTA PREVIA Y ESTRUCTURA DE COLUMNAS
        tab_sub_preview, tab_sub_stats, tab_sub_charts, tab_sub_cluster = st.tabs([
            "🔍 Vista Previa de Datos",
            "📈 Estadísticas Descriptivas",
            "📉 Visualizaciones Interactivas",
            "🚀 Procesar CSV con el Clúster"
        ])

        with tab_sub_preview:
            st.markdown("#### Vista Previa del Conjunto de Datos")
            c_sl, _ = st.columns([2, 4])
            with c_sl:
                preview_rows = st.slider("Número de filas a visualizar:", 5, min(100, n_rows), 10)
            
            st.dataframe(df.head(preview_rows), use_container_width=True)

            with st.expander("ℹ️ Información Detallada de Columnas y Tipos de Datos"):
                col_info = []
                for c in df.columns:
                    col_info.append({
                        "Columna": c,
                        "Tipo de Dato": str(df[c].dtype),
                        "No Nulos": int(df[c].notnull().sum()),
                        "Valores Únicos": int(df[c].nunique()),
                        "Ejemplo": str(df[c].dropna().iloc[0]) if len(df[c].dropna()) > 0 else "-"
                    })
                st.dataframe(pd.DataFrame(col_info), use_container_width=True)

        with tab_sub_stats:
            st.markdown("#### Resumen Estadístico Detallado")
            if numeric_cols:
                st.markdown("**Variables Numéricas (`describe`):**")
                desc_df = df[numeric_cols].describe().T
                desc_df["mediana"] = df[numeric_cols].median()
                desc_df["rango"] = desc_df["max"] - desc_df["min"]
                # Formatear números para lectura limpia
                desc_df = desc_df[["count", "mean", "std", "min", "25%", "mediana", "75%", "max", "rango"]]
                desc_df.columns = ["Conteo", "Media (Promedio)", "Desv. Estándar", "Mínimo", "Q1 (25%)", "Mediana (50%)", "Q3 (75%)", "Máximo", "Rango Total"]
                st.dataframe(desc_df.round(3), use_container_width=True)
            else:
                st.info("No se detectaron columnas numéricas en este archivo.")

            if categorical_cols:
                st.markdown("**Variables Categóricas / Texto:**")
                cat_desc = df[categorical_cols].describe().T
                st.dataframe(cat_desc, use_container_width=True)

        with tab_sub_charts:
            st.markdown("#### Gráficos Dinámicos de Análisis")
            
            chart_col1, chart_col2 = st.columns(2)

            with chart_col1:
                if numeric_cols:
                    st.markdown("##### 📊 Distribución de Variable Numérica")
                    selected_num_col = st.selectbox("Selecciona una columna para graficar:", numeric_cols, key="num_chart_sel")
                    
                    # Generar conteo por intervalos para gráfico estético
                    try:
                        hist_values, bin_edges = np.histogram(df[selected_num_col].dropna(), bins=25)
                        bin_labels = [f"{round(bin_edges[i], 1)} - {round(bin_edges[i+1], 1)}" for i in range(len(hist_values))]
                        chart_df = pd.DataFrame({"Frecuencia": hist_values}, index=bin_labels)
                        st.bar_chart(chart_df)
                    except Exception:
                        st.line_chart(df[selected_num_col].head(300))

            with chart_col2:
                if categorical_cols:
                    st.markdown("##### 🍩 Frecuencia de Categorías")
                    selected_cat_col = st.selectbox("Selecciona una columna categórica:", categorical_cols, key="cat_chart_sel")
                    top_vals = df[selected_cat_col].value_counts().head(10)
                    st.bar_chart(top_vals)
                elif len(numeric_cols) >= 2:
                    st.markdown("##### 📈 Comparación entre dos variables")
                    col_x = st.selectbox("Eje X:", numeric_cols, index=0, key="scatter_x")
                    col_y = st.selectbox("Eje Y:", numeric_cols, index=min(1, len(numeric_cols)-1), key="scatter_y")
                    st.scatter_chart(df[[col_x, col_y]].dropna().head(500), x=col_x, y=col_y)

        with tab_sub_cluster:
            st.markdown("#### ⚡ Procesamiento Analítico Distribuido en el Clúster")
            st.markdown("""
            Esta función divide el conjunto de datos en **fragmentos equitativos** y los envía a los 
            computadores activos en el clúster para calcular estadísticas globales y realizar **operaciones de normalización matemática**.
            """)

            if not numeric_cols:
                st.warning("Se requiere al menos una columna numérica para realizar análisis distribuido.")
            elif not online_nodes:
                st.error("❌ No hay nodos activos en el clúster. Inicia al menos un agente (`Run.py`) para procesar.")
            else:
                scope_mode = st.radio(
                    "Alcance del Procesamiento en el Clúster:",
                    ["🌐 Analizar el Dataset Completo (Todas las Columnas + Normalización)", "🎯 Analizar una Sola Columna"],
                    horizontal=True
                )

                if scope_mode == "🌐 Analizar el Dataset Completo (Todas las Columnas + Normalización)":
                    c_cfg1, c_cfg2, c_cfg3 = st.columns(3)
                    with c_cfg1:
                        norm_choice = st.selectbox(
                            "Operación de Normalización Matemática a aplicar:",
                            [
                                "Min-Max Scaling [0 a 1]",
                                "Z-Score / Estandarización (Media=0, Desv=1)",
                                "Ambas Técnicas (Min-Max y Z-Score)",
                                "Solo Estadísticas Globales (Sin Normalizar)"
                            ]
                        )
                    with c_cfg2:
                        num_batches = st.select_slider(
                            "División en Lotes / Etapas (monitoreo en vivo):",
                            options=[len(online_nodes), 5, 10, 20, 40, 60, 100],
                            value=min(20, max(len(online_nodes), 10)),
                            help="Divide el dataset en múltiples lotes que se reparten concurrentemente para observar la telemetría en tiempo real."
                        )
                    with c_cfg3:
                        visual_delay_ms = st.slider(
                            "Velocidad de Demostración Visual (retardo por lote en ms):",
                            min_value=0,
                            max_value=300,
                            value=60,
                            step=10,
                            help="Ralentiza la animación entre lotes para que puedas apreciar en vivo cómo cada nodo procesa su parte. (0 = máxima velocidad real)."
                        )

                    c_int1, c_int2 = st.columns([3, 1])
                    with c_int1:
                        st.info(f"💡 Se repartirán **{n_rows:,} filas** y **{n_cols} columnas** en **{num_batches} lotes** entre **{len(online_nodes)} computadores activos**.")
                    with c_int2:
                        workload_intensity = st.selectbox(
                            "Intensidad de carga por nodo:",
                            options=["Baja (Estadísticas puras)", "Media (Simulación analítica)", "Alta (Cálculo intensivo)"],
                            index=1
                        )
                        complexity_map = {
                            "Baja (Estadísticas puras)": 0,
                            "Media (Simulación analítica)": 500,
                            "Alta (Cálculo intensivo)": 2000
                        }

                    if st.button("🚀 Iniciar Análisis Completo y Normalización en el Clúster", use_container_width=True):
                        st.markdown("#### 📡 Monitor de Ejecución del Clúster en Tiempo Real")
                        
                        prog_bar = st.progress(0, text="Iniciando conexión con los nodos del clúster...")
                        kpi_box = st.empty()
                        nodes_box = st.empty()
                        log_box = st.empty()
                        
                        total_rows = len(df)
                        chunk_size = int(np.ceil(total_rows / num_batches))
                        df_chunks = [df.iloc[i * chunk_size:(i + 1) * chunk_size] for i in range(num_batches)]
                        df_chunks = [c for c in df_chunks if len(c) > 0]
                        actual_batches = len(df_chunks)
                        
                        node_tracker = {
                            node["address"]: {
                                "hostname": node["hostname"],
                                "batches_done": 0,
                                "rows_done": 0,
                                "last_time": 0.0
                            }
                            for node in online_nodes
                        }
                        
                        live_logs = []
                        valid_res = []
                        t_start = time.time()
                        
                        with ThreadPoolExecutor(max_workers=min(actual_batches, len(online_nodes) * 4)) as executor:
                            future_to_info = {}
                            for i, chunk_df in enumerate(df_chunks):
                                target_node = online_nodes[i % len(online_nodes)]
                                fut = executor.submit(
                                    send_task_to_node,
                                    target_node["address"],
                                    f"Lote-{i+1}",
                                    complexity_map[workload_intensity],
                                    "full_dataset_analysis",
                                    chunk_df.to_dict(orient="list"),
                                    ""
                                )
                                future_to_info[fut] = (i + 1, target_node["address"], len(chunk_df))
                            
                            completed_count = 0
                            accumulated_rows = 0
                            
                            for fut in as_completed(future_to_info):
                                batch_num, node_addr, batch_rows = future_to_info[fut]
                                res = fut.result()
                                completed_count += 1
                                
                                if "error" not in res:
                                    valid_res.append(res)
                                    h_name = res.get("hostname", node_addr)
                                    elapsed = res.get("elapsed_seconds", 0.0)
                                    accumulated_rows += batch_rows
                                    
                                    if node_addr in node_tracker:
                                        node_tracker[node_addr]["batches_done"] += 1
                                        node_tracker[node_addr]["rows_done"] += batch_rows
                                        node_tracker[node_addr]["last_time"] = elapsed
                                        node_tracker[node_addr]["hostname"] = h_name
                                        
                                    live_logs.append(f"🟢 **[Lote {batch_num}/{actual_batches}]** `{h_name}` ({node_addr}) procesó {batch_rows:,} filas en {elapsed}s.")
                                else:
                                    live_logs.append(f"🔴 **[Lote {batch_num}/{actual_batches}]** Error en `{node_addr}`: {res.get('error')}")
                                
                                pct = completed_count / actual_batches
                                prog_bar.progress(pct, text=f"Progreso del Clúster: {completed_count}/{actual_batches} lotes ({int(pct * 100)}%) | {accumulated_rows:,} filas procesadas")
                                
                                cur_elapsed = time.time() - t_start
                                rate = int(accumulated_rows / cur_elapsed) if cur_elapsed > 0 else 0
                                with kpi_box.container():
                                    k1, k2, k3, k4 = st.columns(4)
                                    k1.metric("Lotes Completados", f"{completed_count} / {actual_batches}")
                                    k2.metric("Filas Procesadas", f"{accumulated_rows:,} / {total_rows:,}")
                                    k3.metric("Velocidad de Cómputo", f"{rate:,} filas/s")
                                    k4.metric("Tiempo Transcurrido", f"{round(cur_elapsed, 1)} s")
                                
                                with nodes_box.container():
                                    n_cols_ui = st.columns(len(node_tracker))
                                    for idx_n, (n_addr, n_info) in enumerate(node_tracker.items()):
                                        with n_cols_ui[idx_n]:
                                            with st.container(border=True):
                                                st.markdown(f"💻 **{n_info['hostname']}**")
                                                st.caption(f"Dirección: `{n_addr}`")
                                                st.write(f"📦 Lotes: **{n_info['batches_done']}** | 📑 Filas: **{n_info['rows_done']:,}**")
                                                st.caption(f"Último tiempo: {n_info['last_time']} s")
                                
                                with log_box.container():
                                    with st.expander("📜 Registro de Actividad y Telemetría en Streaming", expanded=True):
                                        for log_entry in live_logs[-6:]:
                                            st.markdown(log_entry)
                                
                                if visual_delay_ms > 0:
                                    time.sleep(visual_delay_ms / 1000.0)
                        
                        total_dist_time = round(time.time() - t_start, 4)
                        prog_bar.progress(1.0, text=f"✅ ¡Trabajo Completado al 100% por el clúster en {total_dist_time} segundos!")

                        if valid_res:
                            st.success(f"🎉 ¡Análisis completo y normalización ejecutados por el clúster en **{total_dist_time} segundos**!")

                            # 1. Consolidación de estadísticas globales de todas las columnas
                            st.markdown("##### 📊 Estadísticas Globales Consolidadas de Todas las Columnas")
                            global_stats_rows = []
                            global_min_max = {}
                            global_mean_std = {}

                            for col in numeric_cols:
                                g_count = 0
                                g_sum = 0.0
                                g_sum_sq = 0.0
                                g_min = float("inf")
                                g_max = float("-inf")

                                for r in valid_res:
                                    n_stat = r.get("numeric_stats", {}).get(col, {})
                                    if n_stat:
                                        cnt = n_stat.get("count", 0)
                                        g_count += cnt
                                        g_sum += n_stat.get("sum", 0.0)
                                        g_sum_sq += n_stat.get("sum_sq", 0.0)
                                        g_min = min(g_min, n_stat.get("min", float("inf")))
                                        g_max = max(g_max, n_stat.get("max", float("-inf")))

                                if g_count > 0:
                                    g_mean = g_sum / g_count
                                    g_var = max(0.0, (g_sum_sq / g_count) - (g_mean ** 2))
                                    g_std = np.sqrt(g_var)
                                else:
                                    g_mean = g_var = g_std = g_min = g_max = 0.0

                                global_min_max[col] = (g_min, g_max)
                                global_mean_std[col] = (g_mean, g_std)

                                global_stats_rows.append({
                                    "Columna": col,
                                    "Total Registros": g_count,
                                    "Suma Global": round(g_sum, 2),
                                    "Media Global": round(g_mean, 4),
                                    "Desv. Estándar Global": round(g_std, 4),
                                    "Mínimo Global": round(g_min, 4),
                                    "Máximo Global": round(g_max, 4),
                                    "Rango (Max - Min)": round(g_max - g_min, 4)
                                })

                            st.dataframe(pd.DataFrame(global_stats_rows), use_container_width=True)

                            # 2. Rendimiento acumulado por nodo
                            st.markdown("##### ⏱️ Rendimiento Acumulado por Nodo del Clúster")
                            node_perf = []
                            for n_addr, n_info in node_tracker.items():
                                node_perf.append({
                                    "Computador (Nodo)": n_info["hostname"],
                                    "Dirección": n_addr,
                                    "Lotes Procesados": n_info["batches_done"],
                                    "Filas Procesadas": n_info["rows_done"]
                                })
                            df_node_perf = pd.DataFrame(node_perf)
                            c_p1, c_p2 = st.columns(2)
                            with c_p1:
                                st.caption("Lotes procesados por equipo:")
                                st.bar_chart(df_node_perf.set_index("Computador (Nodo)")["Lotes Procesados"])
                            with c_p2:
                                st.caption("Filas procesadas por equipo:")
                                st.bar_chart(df_node_perf.set_index("Computador (Nodo)")["Filas Procesadas"])

                            # 3. Aplicar Normalizaciones según la selección
                            if norm_choice != "Solo Estadísticas Globales (Sin Normalizar)":
                                st.markdown("---")
                                st.markdown("##### 📐 Resultados de la Normalización Matemática")

                                df_normalized = df.copy()

                                if "Min-Max" in norm_choice or "Ambas" in norm_choice:
                                    for col in numeric_cols:
                                        c_min, c_max = global_min_max[col]
                                        rng = c_max - c_min
                                        col_target = f"{col}_minmax" if "Ambas" in norm_choice else col
                                        df_normalized[col_target] = ((df[col] - c_min) / rng).round(5) if rng > 0 else 0.0

                                if "Z-Score" in norm_choice or "Ambas" in norm_choice:
                                    for col in numeric_cols:
                                        c_mean, c_std = global_mean_std[col]
                                        col_target = f"{col}_zscore" if "Ambas" in norm_choice else col
                                        df_normalized[col_target] = ((df[col] - c_mean) / c_std).round(5) if c_std > 0 else 0.0

                                st.dataframe(df_normalized.head(15), use_container_width=True)

                                # Comparativa visual antes y después de normalizar
                                st.markdown("###### 🔍 Comparativa Visual: Original vs. Normalizado")
                                col_inspect = st.selectbox("Selecciona la columna a comparar:", numeric_cols, key="norm_compare_sel")
                                
                                c_cmp1, c_cmp2 = st.columns(2)
                                with c_cmp1:
                                    st.caption(f"Distribución Original: `{col_inspect}` (Min: {global_min_max[col_inspect][0]}, Max: {global_min_max[col_inspect][1]})")
                                    h_orig, b_orig = np.histogram(df[col_inspect].dropna(), bins=20)
                                    lbl_orig = [f"{round(b_orig[i],1)}-{round(b_orig[i+1],1)}" for i in range(len(h_orig))]
                                    st.bar_chart(pd.DataFrame({"Frecuencia": h_orig}, index=lbl_orig))

                                with c_cmp2:
                                    norm_col_name = f"{col_inspect}_minmax" if "Ambas" in norm_choice else col_inspect
                                    st.caption(f"Distribución Normalizada: `{norm_col_name}`")
                                    h_norm, b_norm = np.histogram(df_normalized[norm_col_name].dropna(), bins=20)
                                    lbl_norm = [f"{round(b_norm[i],2)}-{round(b_norm[i+1],2)}" for i in range(len(h_norm))]
                                    st.bar_chart(pd.DataFrame({"Frecuencia": h_norm}, index=lbl_norm))

                                # Botón de descarga del dataset normalizado
                                csv_buffer = io.StringIO()
                                df_normalized.to_csv(csv_buffer, index=False)
                                st.download_button(
                                    label="💾 Descargar Dataset Normalizado Completo (CSV)",
                                    data=csv_buffer.getvalue(),
                                    file_name=f"dataset_normalizado_{dataset_name.replace(' ', '_')}.csv",
                                    mime="text/csv",
                                    use_container_width=True
                                )
                        else:
                            st.error("Ocurrió un error al procesar el dataset completo en los nodos.")
                            st.json(cluster_results)

                else:
                    # Modo columna única con monitoreo en streaming
                    c_dist1, c_dist2, c_dist3 = st.columns(3)
                    with c_dist1:
                        target_col = st.selectbox(
                            "Columna numérica a analizar en el clúster:",
                            numeric_cols,
                            key="cluster_target_col"
                        )
                    with c_dist2:
                        num_batches_col = st.select_slider(
                            "Número de Lotes / Etapas:",
                            options=[len(online_nodes), 5, 10, 20, 40],
                            value=min(10, max(len(online_nodes), 5)),
                            key="single_col_batches"
                        )
                    with c_dist3:
                        visual_delay_col = st.slider(
                            "Retardo Visual (ms):",
                            min_value=0,
                            max_value=300,
                            value=60,
                            step=10,
                            key="single_col_delay"
                        )

                    c_cint1, c_cint2 = st.columns([3, 1])
                    with c_cint1:
                        st.info(f"💡 Se repartirán **{n_rows:,} filas** de la columna `{target_col}` en **{num_batches_col} lotes** entre **{len(online_nodes)} nodos activos**.")
                    with c_cint2:
                        workload_intensity = st.selectbox(
                            "Intensidad de cálculo:",
                            options=["Baja (Estadísticas puras)", "Media (Simulación analítica)", "Alta (Cálculo intensivo)"],
                            index=1,
                            key="single_col_intensity"
                        )
                        complexity_map = {
                            "Baja (Estadísticas puras)": 0,
                            "Media (Simulación analítica)": 500,
                            "Alta (Cálculo intensivo)": 2000
                        }

                    if st.button("🚀 Iniciar Procesamiento Distribuido de la Columna", use_container_width=True):
                        col_values = df[target_col].dropna().tolist()
                        total_items = len(col_values)
                        chunk_size = int(np.ceil(total_items / num_batches_col))
                        chunks = [col_values[i * chunk_size:(i + 1) * chunk_size] for i in range(num_batches_col)]
                        chunks = [c for c in chunks if len(c) > 0]
                        actual_batches_col = len(chunks)

                        st.markdown("#### 📡 Monitor de Ejecución en Tiempo Real")
                        prog_bar = st.progress(0, text="Iniciando procesamiento de columna...")
                        kpi_box = st.empty()
                        nodes_box = st.empty()
                        log_box = st.empty()

                        node_tracker = {
                            node["address"]: {
                                "hostname": node["hostname"],
                                "batches_done": 0,
                                "rows_done": 0,
                                "last_time": 0.0
                            }
                            for node in online_nodes
                        }

                        live_logs = []
                        valid_res = []
                        t_start = time.time()

                        with ThreadPoolExecutor(max_workers=min(actual_batches_col, len(online_nodes) * 4)) as executor:
                            future_to_info = {}
                            for i, chunk_data in enumerate(chunks):
                                target_node = online_nodes[i % len(online_nodes)]
                                fut = executor.submit(
                                    send_task_to_node,
                                    target_node["address"],
                                    f"Chunk-Col-{i+1}",
                                    complexity_map[workload_intensity],
                                    "csv_analysis",
                                    chunk_data,
                                    target_col
                                )
                                future_to_info[fut] = (i + 1, target_node["address"], len(chunk_data))

                            completed_count = 0
                            accumulated_rows = 0

                            for fut in as_completed(future_to_info):
                                batch_num, node_addr, batch_rows = future_to_info[fut]
                                res = fut.result()
                                completed_count += 1

                                if "error" not in res:
                                    valid_res.append(res)
                                    h_name = res.get("hostname", node_addr)
                                    elapsed = res.get("elapsed_seconds", 0.0)
                                    accumulated_rows += batch_rows

                                    if node_addr in node_tracker:
                                        node_tracker[node_addr]["batches_done"] += 1
                                        node_tracker[node_addr]["rows_done"] += batch_rows
                                        node_tracker[node_addr]["last_time"] = elapsed
                                        node_tracker[node_addr]["hostname"] = h_name

                                    live_logs.append(f"🟢 **[Lote {batch_num}/{actual_batches_col}]** `{h_name}` ({node_addr}) procesó {batch_rows:,} filas en {elapsed}s.")
                                else:
                                    live_logs.append(f"🔴 **[Lote {batch_num}/{actual_batches_col}]** Error en `{node_addr}`: {res.get('error')}")

                                pct = completed_count / actual_batches_col
                                prog_bar.progress(pct, text=f"Progreso del Clúster: {completed_count}/{actual_batches_col} lotes ({int(pct * 100)}%) | {accumulated_rows:,} filas procesadas")

                                cur_elapsed = time.time() - t_start
                                rate = int(accumulated_rows / cur_elapsed) if cur_elapsed > 0 else 0
                                with kpi_box.container():
                                    k1, k2, k3, k4 = st.columns(4)
                                    k1.metric("Lotes Completados", f"{completed_count} / {actual_batches_col}")
                                    k2.metric("Filas Procesadas", f"{accumulated_rows:,} / {total_items:,}")
                                    k3.metric("Velocidad de Cómputo", f"{rate:,} filas/s")
                                    k4.metric("Tiempo Transcurrido", f"{round(cur_elapsed, 1)} s")

                                with nodes_box.container():
                                    n_cols_ui = st.columns(len(node_tracker))
                                    for idx_n, (n_addr, n_info) in enumerate(node_tracker.items()):
                                        with n_cols_ui[idx_n]:
                                            with st.container(border=True):
                                                st.markdown(f"💻 **{n_info['hostname']}**")
                                                st.caption(f"Dirección: `{n_addr}`")
                                                st.write(f"📦 Lotes: **{n_info['batches_done']}** | 📑 Filas: **{n_info['rows_done']:,}**")

                                with log_box.container():
                                    with st.expander("📜 Registro de Actividad en Streaming", expanded=True):
                                        for log_entry in live_logs[-6:]:
                                            st.markdown(log_entry)

                                if visual_delay_col > 0:
                                    time.sleep(visual_delay_col / 1000.0)

                        total_dist_time = round(time.time() - t_start, 4)
                        prog_bar.progress(1.0, text=f"✅ ¡Trabajo completado en {total_dist_time} segundos!")

                        if valid_res:
                            st.success(f"🎉 ¡Procesamiento completado por el clúster en **{total_dist_time} segundos**!")
                            st.markdown("##### 🏆 Resultados Consolidados por Computador (Nodo)")
                            res_table = []
                            total_sum_acc = 0.0
                            total_rows_acc = 0

                            for r in valid_res:
                                res_table.append({
                                    "Computador (Nodo)": r.get("hostname", "Desconocido"),
                                    "Subtarea": r.get("task_id"),
                                    "Filas Procesadas": r.get("rows_processed", 0),
                                    "Media Local": r.get("mean", 0.0),
                                    "Mínimo": r.get("min", 0.0),
                                    "Máximo": r.get("max", 0.0),
                                    "Tiempo Nodo (s)": r.get("elapsed_seconds", 0.0)
                                })
                                total_sum_acc += r.get("sum", 0.0)
                                total_rows_acc += r.get("rows_processed", 0)

                            res_df = pd.DataFrame(res_table)
                            st.dataframe(res_df, use_container_width=True)

                            global_mean = round(total_sum_acc / total_rows_acc, 4) if total_rows_acc > 0 else 0
                            gc1, gc2, gc3, gc4 = st.columns(4)
                            gc1.metric("Total Filas Consolidadas", f"{total_rows_acc:,}")
                            gc2.metric("Suma Total Global", f"{total_sum_acc:,.2f}")
                            gc3.metric("Media Global Calculada", f"{global_mean}")
                            gc4.metric("Tiempo Total del Clúster", f"{total_dist_time} s")

                            st.markdown("##### ⏱️ Comparativa de Rendimiento y Carga por Nodo")
                            gr_col1, gr_col2 = st.columns(2)
                            with gr_col1:
                                st.caption("Tiempo de cómputo por cada equipo (menor es más rápido):")
                                st.bar_chart(res_df.set_index("Computador (Nodo)")["Tiempo Nodo (s)"])
                            with gr_col2:
                                st.caption("Filas repartidas por equipo:")
                                st.bar_chart(res_df.set_index("Computador (Nodo)")["Filas Procesadas"])
                        else:
                            st.error("Ocurrió un problema al procesar los fragmentos en los nodos.")
                            st.json(cluster_results)

    else:
        st.info("👆 Por favor sube un archivo CSV arriba o haz clic en **'🎲 Cargar CSV de Prueba'** para comenzar el análisis.")

# =========================================================================
# PESTAÑA 3: GUÍA VISUAL PASO A PASO PARA CONECTAR OTROS PCS
# =========================================================================
with tab_guide:
    st.title("Guía Visual: Cómo Conectar Nuevos Computadores al Clúster")
    st.markdown("""
    El sistema cuenta con **detección y autoconexión automática** por red local (Zero-Configuration).
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
