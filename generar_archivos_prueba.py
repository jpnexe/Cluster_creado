"""
Script para generar archivos CSV de prueba para pruebas de estrés y procesamiento en clúster.
Por defecto genera hasta 700 archivos (175,000 filas).
"""

import os
import numpy as np
import pandas as pd

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archivos_prueba_csv")
TOTAL_FILES = 700
ROWS_PER_FILE = 250

def generate_test_files(total_files=TOTAL_FILES):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"[*] Verificando y generando archivos CSV en '{OUTPUT_DIR}'...")

    np.random.seed(42)
    servidores = ["Srv-Web", "Srv-Database", "Srv-Cache", "Srv-Worker", "Srv-Gateway", "Srv-Auth", "Srv-Storage"]
    estados = ["OK", "WARNING", "CRITICAL"]

    created_count = 0
    for i in range(1, total_files + 1):
        filename = f"lote_datos_{i:03d}.csv"
        filepath = os.path.join(OUTPUT_DIR, filename)

        if not os.path.exists(filepath):
            df = pd.DataFrame({
                "id_muestra": range(1, ROWS_PER_FILE + 1),
                "lote_id": i,
                "servidor": np.random.choice(servidores, ROWS_PER_FILE),
                "cpu_uso_pct": np.random.uniform(5.0, 98.0, ROWS_PER_FILE).round(2),
                "memoria_ram_mb": np.random.randint(1024, 32768, ROWS_PER_FILE),
                "peticiones_segundo": np.random.poisson(140 + (i % 25) * 4, ROWS_PER_FILE),
                "tiempo_respuesta_ms": np.random.normal(32.0 + (i % 12) * 2, 7.5, ROWS_PER_FILE).round(2),
                "temperatura_c": np.random.uniform(36.0, 84.0, ROWS_PER_FILE).round(1),
                "estado": np.random.choice(estados, ROWS_PER_FILE, p=[0.87, 0.10, 0.03])
            })
            df.to_csv(filepath, index=False)
            created_count += 1

    total_existing = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".csv")])
    print(f"[+] Total de archivos CSV disponibles: {total_existing}")
    print(f"[+] Nuevos archivos creados en esta ejecución: {created_count}")

if __name__ == "__main__":
    generate_test_files()
