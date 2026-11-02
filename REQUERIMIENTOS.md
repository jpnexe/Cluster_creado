# Requerimientos e Instrucciones de Conexión del Clúster

Este documento especifica todos los requerimientos de hardware, software, red y configuración necesarios para poner en funcionamiento el clúster distribuido en Python con panel de control visual.

---

## 1. Requerimientos de Hardware

| Componente | Requerimiento Mínimo (Por PC) | Recomendado (Por PC) |
| :--- | :--- | :--- |
| **Computadores** | Mínimo 2 (1 Maestro + 1 Trabajador) | 3 o más computadores |
| **Procesador (CPU)** | 2 núcleos físicos / 4 hilos (x86_64 o ARM64) | 4+ núcleos físicos |
| **Memoria RAM** | 4 GB | 8 GB o más |
| **Almacenamiento** | 500 MB de espacio libre | 1 GB de espacio libre |
| **Conexión de Red** | Wi-Fi 2.4 GHz | Cable Ethernet Gigabit o Wi-Fi 5/6 GHz |

> [!NOTE]
> No es necesario que todos los computadores tengan la misma potencia ni el mismo sistema operativo. El clúster soporta entornos heterogéneos (por ejemplo, mezclar PCs con Windows 11, laptops con Windows 10 y servidores con Linux).

---

## 2. Requerimientos de Software

* **Sistema Operativo Soportado:**
  * Windows 10 / 11 (64-bit)
  * Linux (Ubuntu 20.04+, Debian 11+, Fedora 36+, Arch Linux)
  * macOS (12 Monterey o superior)
* **Python:** Versión **3.10 o superior** (3.10, 3.11, 3.12, 3.13, 3.14).
* **Gestor de Paquetes:** `pip` actualizado.

---

## 3. Dependencias de Python (`requirements.txt`)

El clúster utiliza las siguientes librerías de Python:

| Paquete | Versión Recomendada | Propósito en el Clúster |
| :--- | :--- | :--- |
| **`fastapi`** | `>=0.100.0` | Expone los endpoints `/metrics` y `/execute` en los nodos trabajadores. |
| **`uvicorn`** | `>=0.22.0` | Servidor web ASGI ligero y de alto rendimiento que corre FastAPI. |
| **`psutil`** | `>=5.9.0` | Lee en tiempo real el consumo y capacidad de CPU, núcleos y memoria RAM. |
| **`streamlit`** | `>=1.28.0` | Genera el Panel de Control interactivo en el PC Maestro. |
| **`requests`** | `>=2.28.0` | Permite al Maestro recolectar métricas y despachar tareas a los nodos. |
| **`pandas`** | `>=2.0.0` | Estructura las métricas del clúster en tablas comparativas. |

### Instalación de dependencias:
```bash
pip install -r requirements.txt
```
*(Nota: El script `Run.py` verifica e instala automáticamente estas dependencias si no las tienes instaladas).*

---

## 4. Requerimientos de Red y Puertos

Todos los computadores deben poder comunicarse a través de TCP/IP en la red:

### 4.1. Puertos Utilizados
* **Puerto `8000` (TCP):** Utilizado por el Agente (`agent.py`) en **todos los computadores** para responder métricas, registro dinámico y recibir tareas.
* **Puerto `8501` (TCP):** Utilizado por el Panel de Control Streamlit (`dashboard.py`), únicamente en el **Computador Maestro**.
* **Puerto `8555` (UDP):** Utilizado para el **Auto-descubrimiento en red local**, permitiendo que los nuevos equipos detecten al Maestro automáticamente sin necesidad de escribir IPs a mano.

### 4.2. Topología de Red
* **Opción A (Red Local LAN / Wi-Fi):** Todos los computadores deben estar conectados al mismo enrutador/módem. Asegúrate de que el router no tenga activado el aislamiento de clientes (*AP Isolation*).
* **Opción B (Redes Distintas / VPN):** Si los equipos están en distintas ubicaciones físicas o casas, instala **[Tailscale](https://tailscale.com/)** en todos los equipos y vincúlalos a la misma cuenta. Esto creará una red privada virtual directa (ej. `100.x.x.x`).

---

## 5. Configuración del Firewall

Para permitir que el PC Maestro se comunique con el microservicio del puerto 8000 en los nodos trabajadores:

### En Windows (PowerShell como Administrador):
```powershell
New-NetFirewallRule -DisplayName "Cluster Node Agent" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```
*(O simplemente haz clic en "Permitir acceso en redes privadas" cuando Windows Defender te lo pregunte).*

### En Linux (UFW):
```bash
sudo ufw allow 8000/tcp
```

---

## 6. Procedimiento para Conectar Nuevos PCs al Clúster

### Método 1: Conexión Automática (Recomendada - Cero Configuración de IPs)
1. Inicia el PC Maestro ejecutando `python Run.py` (o `python Run.py --all`).
2. En cualquier otro PC de la misma red, abre la terminal y ejecuta simplemente:
   ```bash
   python Run.py
   ```
3. `Run.py` emitirá un escaneo rápido por UDP y detectará al Maestro:
   ```text
   ====================================================================
     ✨ ¡SE HA DETECTADO UN CLÚSTER ACTIVO EN LA RED LOCAL!
     - Nodo Maestro:  DESKTOP-COFQL6K (192.168.101.13)
     - Panel Web:     http://192.168.101.13:8501
   ====================================================================
   ¿Deseas conectar este computador a ese clúster como Nodo de Trabajo? [S/n]:
   ```
4. Presiona **Enter** (o escribe `S`). El equipo iniciará su agente, se registrará automáticamente en el Maestro y aparecerá en el Dashboard al instante.

---

### Método 2: Conexión Manual (o para redes con aislamiento de broadcast)
#### En los PCs Secundarios (Nodos Trabajadores):
1. Copia la carpeta del proyecto a ese equipo (`Run.py`, `agent.py`, `discovery.py` y `requirements.txt`).
2. Abre la terminal y ejecuta:
   ```bash
   python Run.py --agent
   ```
3. El script mostrará en pantalla la dirección IP del equipo (por ejemplo: `192.168.101.45`).

#### En el PC Maestro (Panel de Control):
1. Inicia el Maestro con `python Run.py --all`.
2. En la barra lateral izquierda, agrega la IP del nuevo equipo con el puerto `:8000`:
   ```text
   127.0.0.1:8000
   192.168.101.45:8000
   ```
3. El nuevo nodo cambiará a estado **ONLINE** sumando sus recursos.

---

## 7. Solución de Problemas Frecuentes

| Síntoma | Causa Probable | Solución |
| :--- | :--- | :--- |
| **El nodo aparece en rojo como OFFLINE** | El agente no está ejecutándose en ese equipo. | Ejecuta `python Run.py --agent` en el equipo secundario. |
| **Tiempo de espera agotado (Timeout)** | El Firewall de Windows está bloqueando el puerto 8000. | Ejecuta el comando de firewall en PowerShell del paso 5. |
| **Conexión rechazada (Connection Refused)** | La IP o el puerto son incorrectos. | Verifica la IP con `ipconfig` o revisa la salida de `Run.py --agent`. |
| **No se encuentran los equipos en Wi-Fi** | El router tiene "Aislamiento de AP" activado. | Desactiva el aislamiento de clientes en el router o utiliza Tailscale. |

