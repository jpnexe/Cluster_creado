"""
Generador y Preparador de Datos de Ventas para Procesamiento en Clúster Distribuido.

Crea los archivos de ventas simuladas con suciedad intencional (devoluciones,
montos nulos, duplicados, categorías desalineadas) y aplica un pipeline
de limpieza y preparación automatizado para dejarlos 100% listos para procesamiento
distribuido en el clúster.

Guarda los datos organizados en la carpeta del proyecto 'datos_ventas/':
  - datos_ventas/crudos/          -> Archivos mensuales con datos brutos.
  - datos_ventas/preparados/      -> Archivos mensuales limpios y estructurados.
  - datos_ventas/ventas_consolidado_preparado.csv -> Dataset total listo para el clúster.
  - datos_ventas/productos.csv    -> Catálogo de productos.
  - datos_ventas/tiendas.csv      -> Catálogo de tiendas y regiones.

Uso:
    python generar.py --tamano demo        (~60,000 filas, rápido para pruebas)
    python generar.py --tamano pequeno     (~300,000 filas)
    python generar.py --tamano mediano     (~1,200,000 filas)
"""

import argparse
import calendar
import os
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd

SEMILLA = 2025

TAMANOS = {
    "demo": {"anios": [2025], "filas_mes": 5_000},       # ~60,000 filas totales (ideal para pruebas rápidas)
    "pequeno": {"anios": [2025], "filas_mes": 25_000},   # ~300,000 filas totales
    "mediano": {"anios": [2025], "filas_mes": 100_000},  # ~1,200,000 filas totales
    "grande": {"anios": [2024, 2025], "filas_mes": 300_000},
}

# ---------------------------------------------------------------- Catálogos
CIUDADES = {
    "Bogotá": ("Andina", 30),
    "Medellín": ("Andina", 14),
    "Cali": ("Pacífica", 11),
    "Barranquilla": ("Caribe", 9),
    "Cartagena": ("Caribe", 6),
    "Bucaramanga": ("Andina", 5),
    "Pereira": ("Andina", 4),
    "Manizales": ("Andina", 3),
    "Santa Marta": ("Caribe", 3),
    "Riohacha": ("Caribe", 2),
    "Villavicencio": ("Orinoquía", 3),
    "Pasto": ("Pacífica", 2),
}

PRODUCTOS = {
    "Electrónica": [
        ("Audífonos inalámbricos", 189_000), ("Celular gama media", 1_150_000),
        ("Cargador USB-C", 59_000), ("Parlante Bluetooth", 249_000),
        ("Televisor 50 pulgadas", 2_090_000), ("Portátil 14 pulgadas", 2_850_000),
        ("Mouse inalámbrico", 69_000), ("Reloj inteligente", 459_000),
    ],
    "Hogar": [
        ("Juego de sábanas", 129_000), ("Olla a presión", 219_000),
        ("Licuadora", 279_000), ("Toallas x2", 79_000),
        ("Lámpara LED", 89_000), ("Juego de vasos x6", 49_000),
        ("Freidora de aire", 389_000), ("Almohada", 65_000),
    ],
    "Ropa": [
        ("Camiseta básica", 45_000), ("Jean clásico", 139_000),
        ("Chaqueta impermeable", 259_000), ("Medias x3", 29_000),
        ("Vestido casual", 159_000), ("Tenis urbanos", 289_000),
        ("Sudadera", 119_000), ("Gorra", 39_000),
    ],
    "Alimentos": [
        ("Café 500 g", 24_000), ("Arroz 5 kg", 21_000),
        ("Aceite 1 L", 14_500), ("Chocolate de mesa", 9_800),
        ("Panela x4", 12_000), ("Atún x3", 22_500),
        ("Leche x6", 27_000), ("Galletas surtidas", 8_900),
    ],
    "Deportes": [
        ("Balón de fútbol", 99_000), ("Mancuernas 5 kg", 149_000),
        ("Bicicleta urbana", 1_290_000), ("Tapete de yoga", 79_000),
        ("Guayos", 239_000), ("Termo deportivo", 45_000),
    ],
    "Juguetes": [
        ("Rompecabezas 1000 piezas", 69_000), ("Carro a control remoto", 189_000),
        ("Muñeca", 99_000), ("Bloques de construcción", 159_000),
        ("Juego de mesa", 119_000),
    ],
    "Libros": [
        ("Novela", 59_000), ("Libro de cocina", 89_000),
        ("Cuaderno x5", 32_000), ("Libro infantil", 39_000),
    ],
    "Belleza": [
        ("Protector solar", 54_000), ("Champú", 26_000),
        ("Perfume", 249_000), ("Crema hidratante", 47_000),
        ("Kit de maquillaje", 135_000),
    ],
}

POP_CLIENTES = 1 / np.arange(1, 200_001) ** 0.7
POP_CLIENTES /= POP_CLIENTES.sum()

METODOS_PAGO = ["Efectivo", "Tarjeta débito", "Tarjeta crédito", "Transferencia"]
PESO_PAGO = [0.34, 0.30, 0.20, 0.16]
PESO_PAGO_CARO = [0.08, 0.17, 0.62, 0.13]

TASA_DEVOLUCION = {
    "Ropa": 0.014, "Electrónica": 0.009, "Juguetes": 0.006, "Deportes": 0.006,
    "Hogar": 0.005, "Belleza": 0.003, "Libros": 0.002, "Alimentos": 0.001
}

FACTOR_MES = {
    1: 0.80, 2: 0.82, 3: 0.92, 4: 0.90, 5: 1.00, 6: 1.12,
    7: 0.98, 8: 0.95, 9: 0.93, 10: 1.00, 11: 1.25, 12: 1.60
}


def crear_catalogos(rng):
    """Crea los catálogos base de productos y tiendas."""
    filas = []
    for cat, items in PRODUCTOS.items():
        for nombre, precio in items:
            filas.append((cat, nombre, precio))
    productos = pd.DataFrame(filas, columns=["categoria", "producto", "precio_base"])
    productos.insert(0, "id_producto", [f"P{i:03d}" for i in range(1, len(productos) + 1)])

    nombres = list(CIUDADES)
    pesos = np.array([CIUDADES[c][1] for c in nombres], dtype=float)
    n_tiendas = 40
    ciudades = list(nombres)
    ciudades += list(rng.choice(nombres, size=n_tiendas - len(nombres), p=pesos / pesos.sum()))
    tiendas = pd.DataFrame({
        "tienda": [f"T{i:03d}" for i in range(1, n_tiendas + 1)],
        "ciudad": ciudades,
    })
    tiendas["region"] = tiendas["ciudad"].map(lambda c: CIUDADES[c][0])
    tiendas["metros_cuadrados"] = (rng.integers(12, 90, size=n_tiendas) * 10).astype(int)
    tiendas["anio_apertura"] = rng.integers(2005, 2024, size=n_tiendas)
    return productos, tiendas


def generar_mes(rng, anio, mes, filas_base, productos, tiendas, pop_tiendas, pop_productos):
    """Genera las ventas brutas de un mes con suciedad intencional."""
    n = int(filas_base * FACTOR_MES[mes])
    dias = calendar.monthrange(anio, mes)[1]

    fechas_dia = pd.date_range(f"{anio}-{mes:02d}-01", periods=dias, freq="D")
    peso_dia = np.where(fechas_dia.dayofweek >= 5, 1.35, 1.0)
    dia = rng.choice(dias, size=n, p=peso_dia / peso_dia.sum())
    segundos = rng.integers(8 * 3600, 21 * 3600, size=n)
    fecha = fechas_dia.values[dia] + segundos.astype("timedelta64[s]")

    t_idx = rng.choice(len(tiendas), size=n, p=pop_tiendas)
    p_idx = rng.choice(len(productos), size=n, p=pop_productos)

    categoria = productos["categoria"].to_numpy()[p_idx].astype(object)
    precio_base = productos["precio_base"].to_numpy()[p_idx]
    es_alimento = categoria == "Alimentos"

    cantidad = 1 + rng.poisson(np.where(es_alimento, 2.0, 0.35))
    precio = np.round(precio_base * rng.normal(1.0, 0.03, size=n) / 100) * 100

    prob_desc = 0.45 if mes == 11 else 0.25
    descuento = np.where(rng.random(n) < prob_desc,
                         rng.choice([0.05, 0.10, 0.15, 0.20, 0.30], size=n), 0.0)
    monto = np.round(cantidad * precio * (1 - descuento))

    cliente_num = rng.choice(len(POP_CLIENTES), size=n, p=POP_CLIENTES) + 1
    cliente = np.array(pd.Series(cliente_num).map("C{:06d}".format), dtype=object)
    cliente[rng.random(n) < 0.18] = None

    df = pd.DataFrame({
        "fecha": fecha,
        "tienda": tiendas["tienda"].to_numpy()[t_idx],
        "ciudad": tiendas["ciudad"].to_numpy()[t_idx],
        "categoria": categoria,
        "producto": productos["producto"].to_numpy()[p_idx],
        "cantidad": cantidad,
        "precio_unitario": precio.astype(np.int64),
        "descuento": descuento,
        "monto": monto,
        "metodo_pago": np.where(precio_base >= 400_000,
                                rng.choice(METODOS_PAGO, size=n, p=PESO_PAGO_CARO),
                                rng.choice(METODOS_PAGO, size=n, p=PESO_PAGO)),
        "cliente_id": cliente,
    })

    # Suciedad intencional simulada:
    # 1. Devoluciones (cantidades y montos negativos)
    dev = rng.random(n) < pd.Series(categoria).map(TASA_DEVOLUCION).to_numpy()
    df.loc[dev, "cantidad"] *= -1
    df.loc[dev, "monto"] *= -1

    # 2. Montos nulos por fallas de caja
    df.loc[rng.random(n) < 0.008, "monto"] = np.nan

    # 3. Categorías mal escritas (mayúsculas, minúsculas o espacios)
    sucia = np.flatnonzero(rng.random(n) < 0.01)
    variantes = [str.upper, str.lower, lambda s: s + " ", lambda s: " " + s]
    eleccion = rng.integers(0, len(variantes), size=len(sucia))
    df.loc[sucia, "categoria"] = [variantes[e](c) for e, c in zip(eleccion, categoria[sucia])]

    df = df.sort_values("fecha", kind="stable", ignore_index=True)
    df.insert(0, "id_venta", pd.Series(np.arange(1, n + 1)).map(f"V{anio}{mes:02d}-{{:07d}}".format))

    # 4. Filas duplicadas por doble envío del datáfono
    dup = df.iloc[np.flatnonzero(rng.random(n) < 0.003)]
    df = pd.concat([df, dup]).sort_index(kind="stable").reset_index(drop=True)
    return df


def preparar_datos_ventas(df_crudo, tiendas=None):
    """
    Pipeline de Limpieza, Estandarización y Preparación de Datos:
      1. Elimina duplicados de datáfono.
      2. Imputa montos vacíos usando cantidad * precio * (1 - descuento).
      3. Estandariza nombres de categorías (limpieza de espacios y capitalización).
      4. Añade variables analíticas: flag de devolución, montos netos y brutos.
      5. Enriquece con información regional de tiendas si está disponible.
    """
    df = df_crudo.copy()
    inicial = len(df)

    # 1. Deduplicación
    df = df.drop_duplicates(subset=["id_venta"]).copy()
    duplicados_eliminados = inicial - len(df)

    # 2. Imputación de montos vacíos
    nulos_monto = int(df["monto"].isnull().sum())
    calculado = np.round(df["cantidad"] * df["precio_unitario"] * (1 - df["descuento"]))
    df["monto"] = df["monto"].fillna(calculado)

    # 3. Estandarización de categorías
    categorias_validas = {k.lower(): k for k in PRODUCTOS.keys()}
    df["categoria"] = df["categoria"].astype(str).str.strip()
    df["categoria"] = df["categoria"].map(lambda c: categorias_validas.get(c.lower(), c.title()))

    # 4. Variables analíticas derivadas
    df["es_devolucion"] = df["cantidad"] < 0
    df["monto_bruto"] = df["monto"].abs()
    
    # 5. Enriquecimiento opcional con tiendas
    if tiendas is not None and "tienda" in df.columns:
        tiendas_sub = tiendas[["tienda", "region", "metros_cuadrados"]].drop_duplicates()
        df = df.merge(tiendas_sub, on="tienda", how="left")

    return df, duplicados_eliminados, nulos_monto


def main():
    ap = argparse.ArgumentParser(description="Genera y Prepara CSV de ventas para procesamiento en Clúster.")
    ap.add_argument("--tamano", choices=TAMANOS, default="demo", help="Tamaño del conjunto de datos (por defecto 'demo')")
    ap.add_argument("--salida", default="datos_ventas", help="Carpeta destino dentro del proyecto (por defecto 'datos_ventas')")
    ap.add_argument("--filas-mes", type=int, help="Sobrescribe las filas base por mes")
    ap.add_argument("--copiar-compartido", action="store_true", default=True, help="Copia el dataset consolidado al espacio compartido del clúster")
    args = ap.parse_args()

    # Directorio base dentro del proyecto
    script_dir = Path(__file__).resolve().parent
    salida_base = script_dir / args.salida
    dir_crudos = salida_base / "crudos"
    dir_preparados = salida_base / "preparados"

    salida_base.mkdir(parents=True, exist_ok=True)
    dir_crudos.mkdir(parents=True, exist_ok=True)
    dir_preparados.mkdir(parents=True, exist_ok=True)

    cfg = TAMANOS[args.tamano]
    filas_mes = args.filas_mes or cfg["filas_mes"]

    rng = np.random.default_rng(SEMILLA)
    productos, tiendas = crear_catalogos(rng)
    productos.to_csv(salida_base / "productos.csv", index=False, encoding="utf-8")
    tiendas.to_csv(salida_base / "tiendas.csv", index=False, encoding="utf-8")

    pop_t = rng.lognormal(0, 0.6, size=len(tiendas)); pop_t /= pop_t.sum()
    pop_p = 1 / np.arange(1, len(productos) + 1) ** 0.6
    pop_p = rng.permutation(pop_p); pop_p /= pop_p.sum()

    print("=" * 70)
    print("      GENERACIÓN Y PREPARACIÓN DE DATOS PARA EL CLÚSTER")
    print("=" * 70)
    print(f"[*] Tamaño seleccionado: '{args.tamano}'")
    print(f"[*] Carpeta destino:    {salida_base.resolve()}")
    print("-" * 70)

    inicio = time.time()
    total_filas_crudas = 0
    total_duplicados = 0
    total_nulos_corregidos = 0
    dfs_preparados_todos = []

    for anio in cfg["anios"]:
        for mes in range(1, 13):
            t0 = time.time()
            
            # 1. Generar mes con suciedad
            df_crudo = generar_mes(rng, anio, mes, filas_mes, productos, tiendas, pop_t, pop_p)
            total_filas_crudas += len(df_crudo)

            # Guardar versión cruda
            ruta_crudo = dir_crudos / f"ventas_crudas_{anio}_{mes:02d}.csv"
            df_crudo.to_csv(ruta_crudo, index=False, encoding="utf-8", date_format="%Y-%m-%d %H:%M:%S")

            # 2. Preparar y limpiar datos para procesamiento
            df_prep, dup_n, nul_n = preparar_datos_ventas(df_crudo, tiendas)
            total_duplicados += dup_n
            total_nulos_corregidos += nul_n
            dfs_preparados_todos.append(df_prep)

            # Guardar versión preparada
            ruta_prep = dir_preparados / f"ventas_preparadas_{anio}_{mes:02d}.csv"
            df_prep.to_csv(ruta_prep, index=False, encoding="utf-8", date_format="%Y-%m-%d %H:%M:%S")

            tiempo_mes = time.time() - t0
            print(f"  -> Mes {anio}-{mes:02d}: {len(df_prep):>8,} filas preparadas | "
                  f"Limpieza: {dup_n:>3} duplicados, {nul_n:>3} nulos ({tiempo_mes:.2f}s)")

    # 3. Generar Dataset Consolidado Completo
    print("-" * 70)
    print("[*] Consolidando archivo maestro preparado...")
    df_consolidado = pd.concat(dfs_preparados_todos, ignore_index=True)
    ruta_consolidado = salida_base / "ventas_consolidado_preparado.csv"
    df_consolidado.to_csv(ruta_consolidado, index=False, encoding="utf-8", date_format="%Y-%m-%d %H:%M:%S")
    tam_mb = ruta_consolidado.stat().st_size / (1024 ** 2)

    # 4. Copiar al Almacén Compartido del Clúster (si existe)
    shared_archivos_dir = script_dir / "shared_storage" / "archivos"
    if args.copiar_compartido and shared_archivos_dir.exists():
        try:
            shutil.copy2(ruta_consolidado, shared_archivos_dir / "ventas_consolidado_preparado.csv")
            print(f"[+] Archivo maestro copiado al Espacio Compartido del Clúster: 'shared_storage/archivos/'")
        except Exception as e:
            print(f"[*] Nota al copiar a compartido: {e}")

    tiempo_total = time.time() - inicio
    print("=" * 70)
    print("  ¡DATOS PREPARADOS EXITOSAMENTE PARA EL CLÚSTER!")
    print("=" * 70)
    print(f"  - Filas totales brutas:      {total_filas_crudas:,}")
    print(f"  - Duplicados eliminados:     {total_duplicados:,}")
    print(f"  - Montos nulos corregidos:   {total_nulos_corregidos:,}")
    print(f"  - Filas limpias finales:     {len(df_consolidado):,}")
    print(f"  - Archivo Consolidado:       {ruta_consolidado.name} ({tam_mb:.2f} MB)")
    print(f"  - Carpeta de preparados:     datos_ventas/preparados/ (12 archivos mensuales)")
    print(f"  - Tiempo total de ejecución: {tiempo_total:.2f} segundos")
    print("=" * 70)
    print("\n[*] Puedes cargar 'datos_ventas/ventas_consolidado_preparado.csv' en el")
    print("   Panel de Control (dashboard.py) para distribuirlo y normalizarlo en el clúster.\n")


if __name__ == "__main__":
    main()
