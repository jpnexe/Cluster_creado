"""
====================================================================
Script de Ejecución Principal (Run.py) - Clúster Distribuido en Python
====================================================================
Características:
  - Detección automática de Clústeres activos en la red local (UDP).
  - Pregunta al usuario si desea unirse automáticamente al clúster detectado.
  - Registro dinámico y desvinculación limpia de nodos.
  - Soporte de roles manuales:
      python Run.py --all         # Inicia Maestro Completo (Agente + Dashboard)
      python Run.py --agent       # Inicia solo Agente Trabajador
      python Run.py --dashboard   # Inicia solo Panel de Control
====================================================================
"""

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
import requests
import discovery

REQUIRED_PACKAGES = ["fastapi", "uvicorn", "psutil", "streamlit", "requests", "pandas", "numpy"]
PROCESSES = []
DISCOVERY_SERVER = None
REGISTERED_MASTER_IP = None


def print_banner():
    print(r"""
====================================================================
        CLÚSTER DISTRIBUIDO EN PYTHON - PANEL DE CONTROL
====================================================================
    """)


def check_and_install_dependencies():
    """Verifica e instala dependencias requeridas si falta alguna."""
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"[*] Faltan dependencias necesarias: {', '.join(missing)}")
        print("[*] Instalando dependencias con pip...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print("[+] Dependencias instaladas exitosamente.\n")
        except subprocess.CalledProcessError as e:
            print(f"[!] Error instalando dependencias: {e}")
            sys.exit(1)


def get_local_network_ips():
    """Detecta las direcciones IP locales para facilitar la configuración."""
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
            hostname = socket.gethostname()
            host_ip = socket.gethostbyname(hostname)
            if not host_ip.startswith("127."):
                ips.append(("Host", host_ip, False))
        except Exception:
            pass

    ips.sort(key=lambda x: (x[2], x[0]))
    return ips


def show_network_info():
    """Muestra información de red útil."""
    hostname = socket.gethostname()
    print(f"[*] Nombre de este equipo (Hostname): {hostname}")
    ips = get_local_network_ips()
    if ips:
        print("[*] Direcciones IP detectadas en este computador:")
        for iface, ip, is_apipa in ips:
            tag = " (Enlace local/APIPA)" if is_apipa else ""
            print(f"    - {iface}: {ip}{tag}")
            if not is_apipa:
                print(f"      -> URL del Agente para otros PCs: http://{ip}:8000")
    else:
        print("    - No se detectaron IPs de red adicionales a 127.0.0.1")
    print("-" * 68)


def terminate_all_processes():
    """Finaliza todos los subprocesos y desvincula el nodo de forma limpia."""
    global DISCOVERY_SERVER, REGISTERED_MASTER_IP

    # Si estamos conectados a un maestro, desvincularse
    if REGISTERED_MASTER_IP:
        try:
            my_ip = discovery.get_primary_ip()
            print(f"\n[*] Desvinculando este nodo del Maestro ({REGISTERED_MASTER_IP})...")
            requests.post(
                f"http://{REGISTERED_MASTER_IP}:8000/unregister_node",
                json={"address": f"{my_ip}:8000", "hostname": socket.gethostname()},
                timeout=1.5
            )
        except Exception:
            pass
        REGISTERED_MASTER_IP = None

    if DISCOVERY_SERVER:
        try:
            DISCOVERY_SERVER.stop()
        except Exception:
            pass
        DISCOVERY_SERVER = None

    if not PROCESSES:
        return

    print("\n[*] Cerrando servicios del clúster...")
    for proc, name in PROCESSES:
        if proc.poll() is None:
            print(f"[*] Deteniendo {name} (PID: {proc.pid})...")
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
    PROCESSES.clear()
    print("[+] Todos los servicios se han detenido correctamente.")


def signal_handler(sig, frame):
    terminate_all_processes()
    sys.exit(0)


def start_agent():
    """Inicia el microservicio agent.py (FastAPI en puerto 8000)."""
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent.py")
    if not os.path.exists(script_path):
        print(f"[!] Error: No se encontró el archivo '{script_path}'")
        sys.exit(1)

    print("[*] Iniciando Agente de Recursos (FastAPI en http://0.0.0.0:8000)...")
    proc = subprocess.Popen(
        [sys.executable, script_path],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    PROCESSES.append((proc, "Agente (agent.py)"))
    return proc


def start_dashboard():
    """Inicia el panel de control dashboard.py (Streamlit en puerto 8501 para toda la red)."""
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.py")
    if not os.path.exists(script_path):
        print(f"[!] Error: No se encontró el archivo '{script_path}'")
        sys.exit(1)

    primary_ip = discovery.get_primary_ip()
    print(f"[*] Iniciando Panel de Control (Streamlit):")
    print(f"    - Acceso local:       http://localhost:8501")
    print(f"    - Acceso desde otros PCs: http://{primary_ip}:8501")

    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", script_path, "--server.address=0.0.0.0", "--server.port=8501"],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    PROCESSES.append((proc, "Panel de Control (dashboard.py)"))
    return proc


def start_discovery_server():
    """Inicia el servidor UDP para que otros equipos encuentren a este Maestro."""
    global DISCOVERY_SERVER
    if DISCOVERY_SERVER is None:
        try:
            DISCOVERY_SERVER = discovery.MasterDiscoveryServer(
                master_ip=discovery.get_primary_ip(),
                hostname=socket.gethostname(),
                dashboard_port=8501,
                agent_port=8000
            )
            DISCOVERY_SERVER.start()
            print("[+] Servicio de auto-descubrimiento en red activado (UDP puerto 8555).")
        except Exception as e:
            print(f"[*] Nota sobre auto-descubrimiento: {e}")


def wait_for_processes():
    """Monitorea los procesos y espera hasta Ctrl+C o cierre de proceso."""
    print("\n[+] Servicios en ejecución. Presiona Ctrl+C en cualquier momento para detener.\n")
    try:
        while True:
            for proc, name in PROCESSES:
                ret = proc.poll()
                if ret is not None:
                    print(f"[!] El servicio '{name}' finalizó con código {ret}.")
                    terminate_all_processes()
                    return
            time.sleep(1)
    except KeyboardInterrupt:
        terminate_all_processes()


def connect_as_worker_to_master(master_ip, master_hostname):
    """Inicia el agente y lo registra automáticamente en el Maestro."""
    global REGISTERED_MASTER_IP
    print(f"\n[*] Conectando este equipo al clúster de '{master_hostname}' ({master_ip})...")
    start_agent()
    time.sleep(1.5)  # Esperar que el agente local esté listo

    my_ip = discovery.get_primary_ip()
    my_address = f"{my_ip}:8000"
    REGISTERED_MASTER_IP = master_ip

    print(f"[*] Registrando dirección `{my_address}` en el Maestro...")
    try:
        resp = requests.post(
            f"http://{master_ip}:8000/register_node",
            json={"address": my_address, "hostname": socket.gethostname()},
            timeout=3.0
        )
        if resp.status_code == 200:
            print(f"\n====================================================================")
            print(f"  ✅ ¡CONEXIÓN EXITOSA AL CLÚSTER!")
            print(f"  - Maestro:            {master_hostname} ({master_ip})")
            print(f"  - Este Nodo:          {socket.gethostname()} ({my_address})")
            print(f"  - Estado en el panel: ONLINE (recursos aportados y listos)")
            print(f"====================================================================")
        else:
            print(f"[*] Aviso: El agente maestro respondió código {resp.status_code}, pero tu agente está activo.")
    except Exception as e:
        print(f"[!] No se pudo registrar automáticamente en el endpoint del Maestro: {e}")
        print(f"    (Puedes agregar manualmente `{my_address}` en el panel web del Maestro).")

    wait_for_processes()


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(description="Lanzador del Clúster Distribuido en Python")
    parser.add_argument(
        "--mode",
        choices=["all", "agent", "dashboard"],
        default=None,
        help="Modo de ejecución: 'all' (Maestro Completo), 'agent' (solo agente), 'dashboard' (solo panel)"
    )
    parser.add_argument("--all", action="store_true", help="Iniciar Maestro Completo (Agente + Dashboard)")
    parser.add_argument("--agent", action="store_true", help="Iniciar solo el Agente de Nodo")
    parser.add_argument("--dashboard", action="store_true", help="Iniciar solo el Panel de Control")

    args = parser.parse_args()

    print_banner()
    check_and_install_dependencies()
    show_network_info()

    # Si se pasó un argumento explícito por CLI, ejecutar directamente
    if args.all:
        mode = "all"
    elif args.agent:
        mode = "agent"
    elif args.dashboard:
        mode = "dashboard"
    elif args.mode:
        mode = args.mode
    else:
        # --- DETECCIÓN AUTOMÁTICA DE CLÚSTER EXISTENTE ---
        print("[*] Buscando si ya existe un Clúster activo en la red local...")
        discovered = discovery.discover_cluster(timeout=1.2)

        if discovered:
            m_host = discovered.get("hostname", "Desconocido")
            m_ip = discovered.get("master_ip", discovered.get("detected_ip"))
            d_port = discovered.get("dashboard_port", 8501)

            print(r"""
====================================================================
  ✨ ¡SE HA DETECTADO UN CLÚSTER ACTIVO EN LA RED LOCAL!
--------------------------------------------------------------------
  - Nodo Maestro:  {host}
  - Dirección IP:  {ip}
  - Panel Web:     http://{ip}:{port}
====================================================================
            """.format(host=m_host, ip=m_ip, port=d_port))

            try:
                ans = input("¿Deseas conectar este computador a ese clúster como Nodo de Trabajo? [S/n] (Por defecto S): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nOperación cancelada.")
                return

            if ans in ("", "s", "si", "y", "yes"):
                connect_as_worker_to_master(m_ip, m_host)
                return
            else:
                print("\n[*] Omitiendo conexión al clúster detectado.")

        else:
            print("[*] No se detectó ningún clúster activo en la red local.")

        # Menú interactivo estándar
        if sys.stdin.isatty():
            print("\nSelecciona el rol para este computador:")
            print("  [1] Maestro Completo (Agente Local + Panel de Control Streamlit) [Recomendado]")
            print("  [2] Solo Panel de Control (Dashboard Streamlit)")
            print("  [3] Solo Agente (Microservicio FastAPI para computadores trabajadores)")
            print("  [4] Salir")
            try:
                choice = input("\nIngresa una opción [1-4] (Por defecto 1): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nOperación cancelada.")
                return

            if choice == "2":
                mode = "dashboard"
            elif choice == "3":
                mode = "agent"
            elif choice == "4":
                print("Saliendo...")
                return
            else:
                mode = "all"
        else:
            mode = "all"

    print(f"\n[*] Modo seleccionado: {mode.upper()}\n")

    if mode == "all":
        # Al iniciar como Maestro, activar descubrimiento UDP para que otros equipos lo encuentren
        start_discovery_server()
        start_agent()
        time.sleep(1.5)
        start_dashboard()
        wait_for_processes()
    elif mode == "agent":
        start_agent()
        wait_for_processes()
    elif mode == "dashboard":
        start_discovery_server()
        start_dashboard()
        wait_for_processes()


if __name__ == "__main__":
    main()
