"""Mide cada operación de la tabla de metas de rendimiento con el caso real y FALLA (código 1) si alguna
supera su meta. Escribe el resultado en resultados/rendimiento.md.

Uso:  python pruebas/medir_rendimiento.py          (todo, ~3 minutos)
      python pruebas/medir_rendimiento.py rapido   (sin la optimización completa)
"""

import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import pandas as pd  # noqa: E402

from modulos import cargar_ventas as cv  # noqa: E402
from modulos.analisis_ventas import pares_comprobante, resumen_por_producto  # noqa: E402
from modulos.cargar_catalogo import cargar_catalogo  # noqa: E402
from modulos.cargar_local import local_de_ejemplo  # noqa: E402
from modulos.comun import CARPETA_ENTRADA, CARPETA_RESULTADOS, cargar_ajustes  # noqa: E402
from modulos.costeo import calcular, tabla_inicial  # noqa: E402
from modulos.modelo_optimo import optimizar_diseno  # noqa: E402
from modulos.normas import estado_inicial, incompatibilidades_activas, parametros_activos  # noqa: E402
from modulos.visual_3d import figura_3d  # noqa: E402

CATALOGO = CARPETA_ENTRADA / "lista_de_productos_limpio.xlsx"
VENTAS = next(iter(sorted(CARPETA_ENTRADA.glob("reporte_ventas_producto_*.xlsx"))), None)


def medir(funcion):
    inicio = time.perf_counter()
    resultado = funcion()
    return time.perf_counter() - inicio, resultado


def main():
    rapido = "rapido" in sys.argv
    filas = []

    def anotar(operacion, segundos, meta, nota=""):
        filas.append({"Operación": operacion, "Tiempo (s)": round(segundos, 3), "Meta (s)": meta,
                      "Cumple": "sí" if segundos <= meta else "NO", "Nota": nota})
        print(f"{operacion:<45} {segundos:8.3f} s   meta {meta:>6} s   {'OK' if segundos <= meta else 'NO CUMPLE'}  {nota}", flush=True)

    # 1. Abrir la app y cambiar de paso
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=120)
    segundos, _ = medir(app.run)
    anotar("Abrir la app (primera vez, incluye importar)", segundos, 10.0,
           "en Streamlit las librerías se importan una sola vez al iniciar el servidor")
    segundos, _ = medir(app.run)
    anotar("Abrir la app y cambiar de paso (recarga)", segundos, 1.0)

    # 2. Ventas desde caché parquet y primera lectura del Excel de 16 MB
    contenido = VENTAS.read_bytes()
    cv.leer_reporte(contenido, VENTAS.name)  # deja la caché lista
    segundos, (tabla, desde_cache) = medir(lambda: cv.leer_reporte(contenido, VENTAS.name))
    anotar("Cargar ventas desde caché (parquet)", segundos, 3.0, f"{len(tabla):,} líneas; caché = {desde_cache}")
    original = cv.CARPETA_PROCESADOS
    with tempfile.TemporaryDirectory() as temporal:
        cv.CARPETA_PROCESADOS = Path(temporal)
        segundos, (tabla_excel, _) = medir(lambda: cv.leer_reporte(contenido, VENTAS.name))
        cv.CARPETA_PROCESADOS = original
    motor = "calamine" if _hay_calamine() else "openpyxl"
    anotar("Primera lectura del Excel de 16 MB", segundos, 60.0, f"motor {motor}; {len(tabla_excel):,} líneas")

    # Datos del caso real
    catalogo = cargar_catalogo(CATALOGO.read_bytes(), CATALOGO.name, "bazar")["catalogo"]
    mapeo, _ = cv.proponer_mapeo(tabla)
    ventas, _ = cv.aplicar_mapeo(tabla, mapeo, True)
    dentro, union, _ = cv.unir_con_catalogo(ventas, catalogo)
    resumen = resumen_por_producto(dentro, catalogo)
    local = local_de_ejemplo()
    estado = estado_inicial("bazar")
    parametros = parametros_activos(estado, "almacen", local)
    argumentos = dict(catalogo=catalogo, resumen=resumen, local=local, parametros=parametros,
                      incompatibilidades=incompatibilidades_activas(estado), pares_venta=pares_comprobante(dentro, 30),
                      modo="almacen")

    # 3. Propuesta rápida y optimización completa
    segundos, solucion = medir(lambda: optimizar_diseno(**argumentos, rapido=True))
    anotar("Propuesta rápida (heurística)", segundos, 5.0,
           f"{union['productos_con_ventas']} productos con ventas; {solucion['modulos_nuevos']} módulos; "
           f"{len(solucion['asignacion'])}/{len(solucion['productos'])} ubicados")
    if not rapido:
        limite = cargar_ajustes()["solver"]["tiempo_limite_s"]
        segundos, completa = medir(lambda: optimizar_diseno(**argumentos, rapido=False, tiempo_limite=limite))
        anotar("Optimización completa", segundos, float(limite), f"tiempo límite configurado {limite} s; estado: {completa['estado']}")
        solucion = completa

    # 4. Vista 3D
    segundos, figura = medir(lambda: figura_3d(solucion["local"], parametros, solucion=solucion, titulo="3D"))
    triangulos = sum(len(t.i) for t in figura.data if getattr(t, "type", "") == "mesh3d" and t.i is not None)
    anotar("Generar la vista 3D", segundos, 3.0, f"≈ {triangulos // 12:,} cajas en {len(figura.data)} mallas (agrupadas por color)")
    anotar("Mover, rotar o filtrar el 3D", 0.0 if triangulos <= 60000 else 99.0, 1.0,
           f"medido de forma INDIRECTA: {triangulos:,} triángulos (meta ≤ 60 000 para que el navegador rote sin bloqueos); "
           "la rotación ocurre en el navegador y no se puede cronometrar desde Python")

    # 5. Costeo
    tabla_costeo = tabla_inicial(solucion["lista_compra"], 100)
    segundos, _ = medir(lambda: calcular(tabla_costeo, 150.0, 0.12, 24))
    anotar("Editar el costeo (recalcular)", segundos, 0.3)

    tabla_resultado = pd.DataFrame(filas)
    ruta = CARPETA_RESULTADOS / "rendimiento.md"
    ruta.write_text("# Rendimiento medido\n\n" + tabla_resultado.to_markdown(index=False) + "\n", encoding="utf-8") \
        if _hay_tabulate() else ruta.write_text("# Rendimiento medido\n\n" + tabla_resultado.to_string(index=False) + "\n",
                                                encoding="utf-8")
    fallas = tabla_resultado[tabla_resultado["Cumple"] == "NO"]
    print(f"\nResultado guardado en {ruta}.")
    if len(fallas):
        print(f"NO se cumplen {len(fallas)} metas: " + "; ".join(fallas["Operación"]))
        sys.exit(1)
    print("Se cumplen todas las metas.")


def _hay_calamine():
    try:
        import python_calamine  # noqa: F401
        return True
    except ImportError:
        return False


def _hay_tabulate():
    try:
        import tabulate  # noqa: F401
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    main()
