"""
Módulo de Descubrimiento Automático y Registro de Nodos en Red Local (UDP)
"""

import json
import os
import socket
import threading
import time

DISCOVERY_PORT = 8555
NODES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nodes.json")


def get_primary_ip():
    """Detecta la IP local enrutable principal de este equipo."""
    try:
        # Crea un socket temporal a una IP pública (no envía tráfico real)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def load_nodes_list():
    """Carga la lista de nodos guardados en nodes.json."""
    if os.path.exists(NODES_FILE):
        try:
            with open(NODES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [n.strip() for n in data if isinstance(n, str) and n.strip()]
        except Exception:
            pass
    return ["127.0.0.1:8000"]


def save_nodes_list(nodes):
    """Guarda la lista de nodos en nodes.json sin duplicados preservando el orden."""
    seen = set()
    cleaned = []
    for n in nodes:
        clean = n.strip()
        if clean and clean not in seen:
            seen.add(clean)
            cleaned.append(clean)
    try:
        with open(NODES_FILE, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=2)
    except Exception as e:
        print(f"[!] Error guardando {NODES_FILE}: {e}")


def add_node_to_list(address):
    """Añade una dirección de nodo si no existe."""
    nodes = load_nodes_list()
    clean_addr = address.strip()
    if clean_addr not in nodes:
        nodes.append(clean_addr)
        save_nodes_list(nodes)
        return True
    return False


def remove_node_from_list(address):
    """Elimina una dirección de nodo de la lista."""
    nodes = load_nodes_list()
    clean_addr = address.strip()
    if clean_addr in nodes:
        nodes.remove(clean_addr)
        save_nodes_list(nodes)
        return True
    return False


class MasterDiscoveryServer:
    """
    Servidor UDP que responde a peticiones de búsqueda en la red local
    e identifica a este equipo como Nodo Maestro del Clúster.
    """
    def __init__(self, master_ip=None, hostname=None, dashboard_port=8501, agent_port=8000):
        self.master_ip = master_ip or get_primary_ip()
        self.hostname = hostname or socket.gethostname()
        self.dashboard_port = dashboard_port
        self.agent_port = agent_port
        self.running = False
        self.sock = None
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()

    def _run_server(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("", DISCOVERY_PORT))
            self.sock.settimeout(1.0)
        except Exception as e:
            print(f"[*] Advertencia: No se pudo enlazar el puerto de descubrimiento UDP {DISCOVERY_PORT}: {e}")
            self.running = False
            return

        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
                try:
                    msg = json.loads(data.decode("utf-8"))
                except Exception:
                    continue

                if msg.get("action") == "DISCOVER_CLUSTER":
                    reply = {
                        "status": "CLUSTER_MASTER",
                        "hostname": self.hostname,
                        "master_ip": self.master_ip,
                        "dashboard_port": self.dashboard_port,
                        "agent_port": self.agent_port
                    }
                    self.sock.sendto(json.dumps(reply).encode("utf-8"), addr)
            except socket.timeout:
                continue
            except Exception:
                if self.running:
                    time.sleep(0.5)

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass


def discover_cluster(timeout=1.2):
    """
    Envía un paquete UDP Broadcast para buscar si hay un Maestro activo en la red.
    Retorna un diccionario con los datos del Maestro o None si no se encuentra.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)

    my_ip = get_primary_ip()
    msg = json.dumps({"action": "DISCOVER_CLUSTER", "sender_ip": my_ip}).encode("utf-8")

    try:
        # Enviar broadcast a la red local
        sock.sendto(msg, ("<broadcast>", DISCOVERY_PORT))
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                data, addr = sock.recvfrom(1024)
                resp = json.loads(data.decode("utf-8"))
                if resp.get("status") == "CLUSTER_MASTER":
                    # Evitar considerarse a sí mismo si ya corre en este host
                    resp_ip = resp.get("master_ip") or addr[0]
                    resp["detected_ip"] = resp_ip
                    return resp
            except socket.timeout:
                break
    except Exception:
        pass
    finally:
        sock.close()

    return None

