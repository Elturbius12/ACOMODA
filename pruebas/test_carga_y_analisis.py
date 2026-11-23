"""Fases 2 y 3: carga del caso real, unión por código de barras, ABC y estimador."""

import pandas as pd
import pytest
from openpyxl import load_workbook

from conftest import CATALOGO_REAL, VENTAS_REAL
from modulos.analisis_ventas import SIN_ROTACION, clasificar_abc, pares_comprobante, resumen_por_producto
from modulos.cargar_catalogo import cargar_catalogo, inferir_categoria
from modulos.cargar_ventas import aplicar_mapeo, convertir_fechas, leer_reporte, proponer_mapeo, unir_con_catalogo
from modulos.comun import cargar_perfiles, normalizar_codigo
from modulos.medidas import estimar_medidas, indice_confiabilidad, leer_contenido

hay_caso_real = pytest.mark.skipif(CATALOGO_REAL is None or not CATALOGO_REAL.exists() or VENTAS_REAL is None,
                                   reason="Faltan los Excel del caso real en datos_entrada/")


@pytest.fixture(scope="module")
def caso_real():
    catalogo = cargar_catalogo(CATALOGO_REAL.read_bytes(), CATALOGO_REAL.name)
    tabla, _ = leer_reporte(VENTAS_REAL.read_bytes(), VENTAS_REAL.name)
    mapeo, _ = proponer_mapeo(tabla)
    ventas, estadisticas = aplicar_mapeo(tabla, mapeo)
    dentro, union, top = unir_con_catalogo(ventas, catalogo["catalogo"])
    return {"catalogo": catalogo, "tabla": tabla, "mapeo": mapeo, "ventas": ventas, "estadisticas": estadisticas,
            "dentro": dentro, "union": union}


@hay_caso_real
def test_catalogo_real_limpieza(caso_real):
    calidad = caso_real["catalogo"]["calidad"]
    assert calidad["filas_leidas"] - calidad["filas_vacias_descartadas"] == 994
    assert calidad["repeticiones"] == 21
    assert calidad["productos"] == 973
    assert 380 <= calidad["categoria_dato"] <= 390
    assert calidad["con_medida_real"] == 0  # VOLUMEN y PESO vienen vacíos
    assert any("VOLUMEN" in a for a in caso_real["catalogo"]["avisos"])
    catalogo = caso_real["catalogo"]["catalogo"]
    assert (catalogo["origen_medidas"] == "estimado").all()


@hay_caso_real
def test_columnas_de_ventas_detectadas(caso_real):
    mapeo = caso_real["mapeo"]
    assert mapeo["fecha_hora"] == "FECHA/HORA" and mapeo["comprobante"] == "COMPROBANTE"
    assert mapeo["cantidad"] == "CANTIDAD" and mapeo["total"] == "TOTAL" and mapeo["precio_unitario"] == "PRECIO X UNIDAD"


@hay_caso_real
def test_union_por_codigo_y_totales_cuadran(caso_real):
    union = caso_real["union"]
    assert union["productos_con_ventas"] == 740
    assert union["codigos_vendidos"] == 2784
    assert union["productos_sin_ventas"] == 973 - 740
    assert union["lineas_dentro"] + union["lineas_fuera"] == union["lineas_totales"]
    # Suma independiente de la columna TOTAL leyendo el Excel original con openpyxl
    libro = load_workbook(VENTAS_REAL, read_only=True)
    hoja = libro.worksheets[0]
    filas = hoja.iter_rows(values_only=True)
    next(filas)
    encabezados = list(next(filas))
    i_total, i_fecha, i_cantidad = encabezados.index("TOTAL"), encabezados.index("FECHA/HORA"), encabezados.index("CANTIDAD")
    suma = 0.0
    for fila in filas:
        if fila[i_fecha] and fila[i_cantidad] not in (None, "") and fila[i_total] not in (None, ""):
            try:
                suma += float(fila[i_total])
            except (TypeError, ValueError):
                pass
    libro.close()
    assert abs((union["soles_dentro"] + union["soles_fuera"]) - suma) < 1.0


@hay_caso_real
def test_fechas_dia_primero(caso_real):
    fechas = caso_real["ventas"]["fecha_hora"]
    assert fechas.min() >= pd.Timestamp("2026-01-01") and fechas.max() <= pd.Timestamp("2026-11-07")


@hay_caso_real
def test_abc_real(caso_real):
    resumen = resumen_por_producto(caso_real["dentro"], caso_real["catalogo"]["catalogo"])
    assert len(resumen) == 973
    assert (resumen["clase_abc"] == SIN_ROTACION).sum() == 233
    participacion_a = resumen.loc[resumen["clase_abc"] == "A", "participacion"].sum()
    assert 0.79 <= participacion_a <= 0.83


def test_abc_pequeno():
    tabla = pd.DataFrame({"id_producto": list("abcde"), "ventas_soles": [500, 300, 120, 80, 0], "unidades": [5, 3, 2, 1, 0]})
    clases = clasificar_abc(tabla, 0.8, 0.95).set_index("id_producto")["clase_abc"]
    # a (50 %) y b (80 %) son A; c (92 %) es B; d (100 %) es C; e no vendió
    assert clases.to_dict() == {"a": "A", "b": "A", "c": "B", "d": "C", "e": SIN_ROTACION}


def test_normalizar_codigo():
    assert normalizar_codigo(" 7750000000017.0 ") == "7750000000017"
    assert normalizar_codigo('"7750000000017"') == "7750000000017"
    assert normalizar_codigo("7.750000000017E+12") == "7750000000017"
    assert normalizar_codigo(None) == ""


def test_union_solo_productos_del_catalogo():
    catalogo = pd.DataFrame({"id_producto": ["111", "SKU:Z9"], "codigo_barras": ["111", ""], "sku": ["A1", "Z9"]})
    ventas = pd.DataFrame({"fecha_hora": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]), "comprobante": ["B1", "B1", "B2"],
                           "codigo_barras": ["111", "999", ""], "sku": ["", "", "Z9"], "producto": ["x", "y", "z"],
                           "cantidad": [1, 2, 3], "precio_unitario": [1, 1, 1], "total": [1.0, 2.0, 3.0], "costo": [None] * 3})
    dentro, union, _ = unir_con_catalogo(ventas, catalogo)
    assert set(dentro["id_producto"]) == {"111", "SKU:Z9"}
    assert union["lineas_fuera"] == 1 and union["soles_fuera"] == 2.0


def test_convertir_fechas():
    serie = pd.Series(["05-11-2026 10:35", "2026-11-05 10:35:00"])
    resultado = convertir_fechas(serie, dia_primero=True)
    assert (resultado == pd.Timestamp("2026-11-05 10:35")).all()


def test_estimador_lee_el_nombre():
    perfil = cargar_perfiles()["perfiles"]["bazar"]
    assert leer_contenido("GASEOSA 625ML")["ml"] == 625
    assert leer_contenido("GALLETA 36G")["gramos"] == 36
    assert leer_contenido("ATUN 425GR")["gramos"] == 425
    assert leer_contenido("CREMA 10G X20")["paquete"] == 20
    assert leer_contenido("SET DE BROCHAS 7 PCS")["paquete"] == 7
    assert leer_contenido("BALANZA 180KG")["gramos"] is None  # capacidad, no peso
    largo, ancho, alto, peso, metodo = estimar_medidas("GASEOSA 625ML", "BEBIDAS", perfil)
    assert 0.6 < peso < 0.75 and alto > largo and "625" in metodo


def test_categoria_por_palabras():
    reglas = cargar_perfiles()["reglas_categoria_comunes"]
    assert inferir_categoria("DETERGENTE ACE 900G", reglas) == "LIMPIEZA"
    assert inferir_categoria("PELOTA DE AGUA CON LUZ LED", reglas) == "JUGUETERIA"
    assert inferir_categoria("XYZ 123", reglas) is None


def test_indice_confiabilidad_por_soles():
    catalogo = pd.DataFrame({"id_producto": ["a", "b"], "origen_medidas": ["real", "estimado"]})
    resumen = pd.DataFrame({"id_producto": ["a", "b"], "ventas_soles": [750.0, 250.0]})
    assert indice_confiabilidad(catalogo, resumen)["indice"] == 75.0
    assert indice_confiabilidad(catalogo, resumen, factor_local=0.8)["indice"] == 60.0


def test_pares_comprobante():
    ventas = pd.DataFrame({"comprobante": ["1", "1", "2", "2", "3"], "id_producto": ["a", "b", "a", "b", "c"]})
    pares = pares_comprobante(ventas, 5)
    assert pares.iloc[0].to_dict() == {"id_a": "a", "id_b": "b", "veces": 2}
