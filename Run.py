"""
====================================================================
Script de Ejecución Principal (Run.py) - Clúster Distribuido en Python
====================================================================
Este script permite iniciar fácilmente los diferentes componentes
del proyecto según el rol de la máquina en el clúster:

  1) Maestro Completo (Agente Local + Panel Streamlit) [Recomendado]
  2) Solo Panel de Control (Dashboard Streamlit)
  3) Solo Agente de Nodo (FastAPI Worker para PC 1, PC 2, PC 3...)

Soporta argumentos por línea de comandos:
  python Run.py --all         # Ejecuta Agente + Dashboard
  python Run.py --agent       # Ejecuta solo el Agente
  python Run.py --dashboard   # Ejecuta solo el Panel de Control
====================================================================
"""

import argparse
import os
import signal
import socket
import subprocess
import sys
import time

REQUIRED_PACKAGES = ["fastapi", "uvicorn", "psutil", "streamlit", "requests", "pandas"]
PROCESSES = []


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
                    # Preferencia a direcciones no APIPA (169.254.x.x)
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

    # Ordenar poniendo las IPs normales antes de APIPA
    ips.sort(key=lambda x: (x[2], x[0]))
    return ips


def show_network_info():
    """Muestra información de red útil para conectar otros nodos."""
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
        print("    - No se detectaron IPs adicionales a 127.0.0.1")
    print("-" * 68)


def terminate_all_processes():
    """Finaliza todos los subprocesos de forma limpia."""
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
    """Inicia el panel de control dashboard.py (Streamlit en puerto 8501)."""
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.py")
    if not os.path.exists(script_path):
        print(f"[!] Error: No se encontró el archivo '{script_path}'")
        sys.exit(1)

    print("[*] Iniciando Panel de Control (Streamlit en http://localhost:8501)...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", script_path],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    PROCESSES.append((proc, "Panel de Control (dashboard.py)"))
    return proc


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


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(description="Lanzador del Clúster Distribuido en Python")
    parser.add_argument(
        "--mode",
        choices=["all", "agent", "dashboard"],
        default=None,
        help="Modo de ejecución: 'all' (Agente + Dashboard), 'agent' (solo agente), 'dashboard' (solo panel)"
    )
    parser.add_argument("--all", action="store_true", help="Iniciar Maestro Completo (Agente + Dashboard)")
    parser.add_argument("--agent", action="store_true", help="Iniciar solo el Agente de Nodo")
    parser.add_argument("--dashboard", action="store_true", help="Iniciar solo el Panel de Control")

    args = parser.parse_args()

    print_banner()
    check_and_install_dependencies()
    show_network_info()

    # Determinar modo
    mode = args.mode
    if args.all:
        mode = "all"
    elif args.agent:
        mode = "agent"
    elif args.dashboard:
        mode = "dashboard"

    if mode is None:
        if sys.stdin.isatty():
            print("Selecciona el modo de inicio para este computador:")
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
        start_agent()
        time.sleep(1.5)  # Breve pausa para que el agente levante en puerto 8000
        start_dashboard()
        wait_for_processes()
    elif mode == "agent":
        start_agent()
        wait_for_processes()
    elif mode == "dashboard":
        start_dashboard()
        wait_for_processes()


if __name__ == "__main__":
    main()

