"""
Módulo de Entorno Común y Espacio Compartido del Clúster (Shared Hub).
Permite que todos los computadores compartan:
  1. Presencia en tiempo real (Quién está accediendo y qué está haciendo).
  2. Pizarra de mensajes y notas compartidas.
  3. Memoria / Variables clave-valor compartidas.
  4. Repositorio de archivos compartidos (Data Lake local).
  5. Registro de auditoría de accesos.
"""

import json
import os
import socket
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(BASE_DIR, "shared_storage")
FILES_DIR = os.path.join(SHARED_DIR, "archivos")

os.makedirs(FILES_DIR, exist_ok=True)

SESSIONS_FILE = os.path.join(SHARED_DIR, "active_sessions.json")
LOGS_FILE = os.path.join(SHARED_DIR, "access_log.json")
NOTES_FILE = os.path.join(SHARED_DIR, "notes.json")
VARS_FILE = os.path.join(SHARED_DIR, "variables.json")
METADATA_FILE = os.path.join(SHARED_DIR, "files_metadata.json")


def _read_json(filepath, default_val):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default_val


def _write_json(filepath, data):
    try:
        temp_path = f"{filepath}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        if os.path.exists(filepath):
            os.remove(filepath)
        os.rename(temp_path, filepath)
    except Exception as e:
        print(f"[!] Error guardando {filepath}: {e}")


def record_access(hostname, ip, action="Acceso al entorno común", client_type="PC / Nodo"):
    """
    Registra que un computador está accediendo o realizando una acción en este momento.
    Actualiza la sesión activa y guarda el evento en el log histórico.
    """
    now_ts = time.time()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_ip = ip.replace("http://", "").replace("https://", "").split(":")[0]
    session_key = f"{hostname}_{clean_ip}"

    # 1. Actualizar presencia activa
    sessions = _read_json(SESSIONS_FILE, {})
    sessions[session_key] = {
        "hostname": hostname,
        "ip": clean_ip,
        "action": action,
        "client_type": client_type,
        "last_seen": now_ts,
        "last_seen_str": now_str
    }
    _write_json(SESSIONS_FILE, sessions)

    # 2. Registrar en log histórico
    logs = _read_json(LOGS_FILE, [])
    logs.append({
        "timestamp": now_str,
        "hostname": hostname,
        "ip": clean_ip,
        "action": action,
        "client_type": client_type
    })
    # Mantener últimos 150 eventos
    if len(logs) > 150:
        logs = logs[-150:]
    _write_json(LOGS_FILE, logs)


def get_active_sessions(timeout_seconds=30):
    """
    Retorna la lista de computadores que están accediendo en este momento
    (vistos en los últimos timeout_seconds).
    """
    now_ts = time.time()
    sessions = _read_json(SESSIONS_FILE, {})
    active = []
    
    for key, data in sessions.items():
        diff = now_ts - data.get("last_seen", 0)
        if diff <= timeout_seconds:
            data["seconds_ago"] = int(diff)
            active.append(data)

    active.sort(key=lambda x: x["seconds_ago"])
    return active


def get_recent_access_logs(limit=25):
    """Retorna los registros de acceso más recientes."""
    logs = _read_json(LOGS_FILE, [])
    return list(reversed(logs[-limit:]))


# --- GESTIÓN DE NOTAS / PIZARRA COMPARTIDA ---

def get_notes():
    """Retorna las notas compartidas entre los computadores."""
    return _read_json(NOTES_FILE, [])


def add_note(author, ip, message, tag="Info"):
    """Publica un nuevo mensaje o nota en la pizarra compartida."""
    notes = get_notes()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_note = {
        "id": int(time.time() * 1000),
        "timestamp": now_str,
        "author": author,
        "ip": ip,
        "message": message,
        "tag": tag
    }
    notes.insert(0, new_note)  # Más reciente primero
    if len(notes) > 100:
        notes = notes[:100]
    _write_json(NOTES_FILE, notes)
    record_access(author, ip, f"Publicó nota [{tag}]: {message[:35]}...")
    return new_note


def delete_note(note_id):
    """Elimina una nota por ID."""
    notes = get_notes()
    notes = [n for n in notes if n.get("id") != note_id]
    _write_json(NOTES_FILE, notes)


# --- GESTIÓN DE VARIABLES / ESTADO COMPARTIDO (KEY-VALUE) ---

def get_variables():
    """Retorna el diccionario de variables compartidas."""
    return _read_json(VARS_FILE, {})


def set_variable(key, value, updated_by, ip):
    """Define o actualiza una variable compartida."""
    vars_dict = get_variables()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    vars_dict[key] = {
        "value": value,
        "updated_by": updated_by,
        "ip": ip,
        "timestamp": now_str
    }
    _write_json(VARS_FILE, vars_dict)
    record_access(updated_by, ip, f"Actualizó variable compartida '{key}'")


def delete_variable(key):
    """Elimina una variable compartida."""
    vars_dict = get_variables()
    if key in vars_dict:
        del vars_dict[key]
        _write_json(VARS_FILE, vars_dict)


# --- GESTIÓN DE ARCHIVOS COMPARTIDOS ---

def get_shared_files():
    """Retorna la lista de archivos disponibles en el almacén compartido."""
    meta = _read_json(METADATA_FILE, {})
    files = []
    if os.path.exists(FILES_DIR):
        for fname in os.listdir(FILES_DIR):
            fpath = os.path.join(FILES_DIR, fname)
            if os.path.isfile(fpath):
                size_kb = round(os.path.getsize(fpath) / 1024, 2)
                f_meta = meta.get(fname, {})
                files.append({
                    "filename": fname,
                    "size_kb": size_kb,
                    "uploaded_by": f_meta.get("uploaded_by", "Desconocido"),
                    "ip": f_meta.get("ip", "-"),
                    "timestamp": f_meta.get("timestamp", datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M:%S")),
                    "path": fpath
                })
    files.sort(key=lambda x: x["timestamp"], reverse=True)
    return files


def save_shared_file(filename, file_bytes, uploaded_by, ip):
    """Guarda un archivo en el repositorio compartido."""
    fpath = os.path.join(FILES_DIR, filename)
    with open(fpath, "wb") as f:
        f.write(file_bytes)
    
    meta = _read_json(METADATA_FILE, {})
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta[filename] = {
        "uploaded_by": uploaded_by,
        "ip": ip,
        "timestamp": now_str
    }
    _write_json(METADATA_FILE, meta)
    record_access(uploaded_by, ip, f"Subió archivo compartido '{filename}' ({round(len(file_bytes)/1024, 1)} KB)")

