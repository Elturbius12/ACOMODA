"""Carga el reporte de ventas (plantilla o reporte propio del sistema de ventas).

- La primera lectura de un Excel grande se guarda en datos_procesados/ como .parquet y se
  reutiliza mientras el archivo no cambie (se compara su huella MD5).
- El asistente de columnas propone equivalencias por nombre y por contenido.
- Solo se trabaja con productos del catálogo; lo demás se descarta y se informa.
"""

import hashlib
import io
import re
import warnings

import pandas as pd
from openpyxl import load_workbook

from modulos.comun import (CARPETA_CONFIGURACION, CARPETA_PROCESADOS, cargar_json, guardar_json,
                           nombre_columna_simple, normalizar_codigo, vacio)
from modulos.cargar_catalogo import detectar_fila_encabezado

CAMPOS_VENTAS = {
    "fecha_hora": ("Fecha y hora", True),
    "comprobante": ("Comprobante (boleta/factura)", True),
    "codigo_barras": ("Código de barras", True),
    "sku": ("SKU / código interno", False),
    "producto": ("Nombre del producto", False),
    "cantidad": ("Cantidad", True),
    "precio_unitario": ("Precio por unidad", False),
    "total": ("Total de la línea", False),
    "costo": ("Costo unitario", False),
}

SINONIMOS_VENTAS = {
    "fecha_hora": ["FECHAHORA", "FECHA", "FECHAEMISION", "FECHADEVENTA", "FECHADEEMISION"],
    "comprobante": ["COMPROBANTE", "NUMEROCOMPROBANTE", "NCOMPROBANTE", "DOCUMENTO", "BOLETA", "TICKET", "NRODOC", "SERIENUMERO"],
    "codigo_barras": ["CODIGODEBARRA", "CODIGODEBARRAS", "CODIGOBARRAS", "CODIGOBARRA", "EAN", "BARCODE"],
    "sku": ["SKU", "CODIGOINTERNO", "CODIGO"],
    "producto": ["PRODUCTO", "DESCRIPCION", "NOMBRE", "ARTICULO"],
    "cantidad": ["CANTIDAD", "CANT", "UNIDADES", "QTY"],
    "precio_unitario": ["PRECIOXUNIDAD", "PRECIOUNITARIO", "PRECIODEVENTA", "PRECIO", "PU", "VALORUNITARIO"],
    "total": ["TOTAL", "IMPORTE", "IMPORTETOTAL", "SUBTOTAL", "MONTO"],
    "costo": ["COSTO", "COSTOUNITARIO", "COSTOPROMEDIO"],
}

RUTA_MAPEOS = CARPETA_CONFIGURACION / "mapeo_ventas.json"


def huella_archivo(contenido):
    return hashlib.md5(contenido).hexdigest()


def _a_texto(valor):
    if valor is None:
        return None
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(valor, float) and valor.is_integer() and abs(valor) < 1e15:
        return str(int(valor)) if abs(valor) >= 1e6 else str(valor)
    return str(valor)


def _filas_excel(contenido, avance=None):
    """Filas del Excel como texto. Usa el motor rápido «calamine» si está instalado; si no, openpyxl."""
    try:
        from python_calamine import CalamineWorkbook
        if avance:
            avance(0.05, "Leyendo el Excel con el motor rápido (calamine)…")
        libro = CalamineWorkbook.from_filelike(io.BytesIO(contenido))
        nombres = libro.sheet_names
        hoja = "DATOS" if "DATOS" in nombres and "INSTRUCCIONES" in nombres else nombres[0]
        datos = libro.get_sheet_by_name(hoja).to_python(skip_empty_area=False)
        if avance:
            avance(0.8, f"Convirtiendo {len(datos):,} filas…")
        # calamine entrega todo número como float; openpyxl da enteros para los números sin decimales
        return [[_a_texto(None if v == "" else (int(v) if isinstance(v, float) and v.is_integer() and abs(v) < 1e15 else v))
                 for v in fila] for fila in datos]
    except ImportError:
        pass
    libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    hoja = libro["DATOS"] if "DATOS" in libro.sheetnames and "INSTRUCCIONES" in libro.sheetnames else libro.worksheets[0]
    total_filas = hoja.max_row or 1
    filas = []
    for numero, fila in enumerate(hoja.iter_rows(values_only=True)):
        filas.append([_a_texto(v) for v in fila])
        if avance and numero % 5000 == 0:
            avance(min(numero / total_filas, 0.99), f"Leyendo fila {numero:,} de {total_filas:,}…")
    libro.close()
    return filas


def leer_reporte(contenido, nombre_archivo, avance=None):
    """Lee el reporte crudo (todas las columnas como texto). Usa caché .parquet.
    `avance(fraccion, texto)` se llama para mostrar la barra de progreso.
    Devuelve (tabla, desde_cache)."""
    huella = huella_archivo(contenido)
    ruta_cache = CARPETA_PROCESADOS / f"ventas_{huella}.parquet"
    if ruta_cache.exists():
        if avance:
            avance(1.0, "Leído desde datos_procesados (el archivo no cambió).")
        return pd.read_parquet(ruta_cache), True
    if nombre_archivo.lower().endswith(".csv"):
        cruda = pd.read_csv(io.BytesIO(contenido), header=None, dtype=str, sep=None, engine="python",
                            encoding_errors="replace", nrows=20)
        fila = detectar_fila_encabezado(cruda, SINONIMOS_VENTAS)
        tabla = pd.read_csv(io.BytesIO(contenido), header=fila, dtype=str, sep=None, engine="python",
                            encoding_errors="replace")
    else:
        filas = _filas_excel(contenido, avance)
        cruda = pd.DataFrame(filas[:20])
        fila = detectar_fila_encabezado(cruda, SINONIMOS_VENTAS)
        encabezados = [str(c).strip() if c is not None else f"Unnamed: {i}" for i, c in enumerate(filas[fila])]
        tabla = pd.DataFrame(filas[fila + 1:], columns=encabezados)
    tabla.columns = [str(c).strip() for c in tabla.columns]
    tabla = tabla[[c for c in tabla.columns if not c.startswith("Unnamed") and c != "None"]]
    tabla = tabla.loc[:, ~tabla.columns.duplicated()]
    tabla = tabla.dropna(how="all").reset_index(drop=True)
    tabla = tabla.astype(object).where(tabla.notna(), None)
    for columna in tabla.columns:
        tabla[columna] = tabla[columna].map(lambda v: None if v is None else str(v))
    tabla.to_parquet(ruta_cache, index=False)
    if avance:
        avance(1.0, f"Listo: {len(tabla):,} líneas. Guardado en datos_procesados para la próxima vez.")
    return tabla, False


def _firma(columnas):
    return "|".join(sorted(nombre_columna_simple(c) for c in columnas))


def mapeo_guardado(columnas):
    if not RUTA_MAPEOS.exists():
        return None
    return cargar_json(RUTA_MAPEOS).get(_firma(columnas))


def guardar_mapeo(columnas, mapeo):
    datos = cargar_json(RUTA_MAPEOS) if RUTA_MAPEOS.exists() else {}
    datos[_firma(columnas)] = mapeo
    guardar_json(datos, RUTA_MAPEOS)


def _parece_fecha(serie):
    muestra = serie.dropna().astype(str).head(200)
    if not len(muestra):
        return 0
    return muestra.str.match(r"^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}").mean()


def _parece_codigo(serie):
    muestra = serie.dropna().astype(str).head(200)
    if not len(muestra):
        return 0
    return muestra.str.fullmatch(r"\d{8,14}(\.0)?").mean()


def proponer_mapeo(tabla):
    """{campo: columna o None}. Primero el mapeo guardado; luego por nombre; luego por contenido."""
    guardado = mapeo_guardado(tabla.columns)
    if guardado and all(v is None or v in tabla.columns for v in guardado.values()):
        return guardado, "guardado"
    simples = {c: nombre_columna_simple(c) for c in tabla.columns}
    mapeo = {campo: None for campo in CAMPOS_VENTAS}
    usadas = set()
    for campo, opciones in SINONIMOS_VENTAS.items():
        for opcion in opciones:
            columna = next((c for c, s in simples.items() if s == opcion and c not in usadas), None)
            if columna:
                mapeo[campo] = columna
                usadas.add(columna)
                break
    libres = [c for c in tabla.columns if c not in usadas]
    if not mapeo["fecha_hora"]:
        candidata = max(libres, key=lambda c: _parece_fecha(tabla[c]), default=None)
        if candidata and _parece_fecha(tabla[candidata]) > 0.8:
            mapeo["fecha_hora"] = candidata
            usadas.add(candidata)
    if not mapeo["codigo_barras"]:
        candidata = max([c for c in libres if c not in usadas], key=lambda c: _parece_codigo(tabla[c]), default=None)
        if candidata and _parece_codigo(tabla[candidata]) > 0.8:
            mapeo["codigo_barras"] = candidata
    return mapeo, "propuesto"


def _numeros(serie):
    texto = serie.astype(str).str.strip().str.replace(" ", "", regex=False)
    coma_decimal = texto.str.fullmatch(r"-?\d+,\d+")
    texto = texto.where(~coma_decimal, texto.str.replace(",", ".", regex=False))
    texto = texto.str.replace(",", "", regex=False)
    return pd.to_numeric(texto, errors="coerce")


def convertir_fechas(serie, dia_primero=True):
    """Convierte textos de fecha. Acepta ISO (2026-11-05) y dd-mm-aaaa HH:MM."""
    texto = serie.astype(str).str.strip()
    iso = texto.str.match(r"^\d{4}-\d{2}-\d{2}")
    resultado = pd.Series(pd.NaT, index=serie.index, dtype="datetime64[ns]")
    if iso.any():
        resultado[iso] = pd.to_datetime(texto[iso], errors="coerce", format="ISO8601")
    resto = ~iso
    if resto.any():
        formatos = ["%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M", "%d-%m-%Y", "%d/%m/%Y", "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"]
        if not dia_primero:
            formatos = [f.replace("%d-%m", "%m-%d").replace("%d/%m", "%m/%d") for f in formatos]
        pendientes = resto.copy()
        for formato in formatos:
            if not pendientes.any():
                break
            convertidas = pd.to_datetime(texto[pendientes], format=formato, errors="coerce")
            resultado[pendientes] = convertidas
            pendientes = pendientes & resultado.isna()
        if pendientes.any():
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                resultado[pendientes] = pd.to_datetime(texto[pendientes], dayfirst=dia_primero, errors="coerce")
    return resultado


def aplicar_mapeo(tabla, mapeo, dia_primero=True):
    """Devuelve (ventas_estandar, estadisticas)."""
    ventas = pd.DataFrame(index=tabla.index)
    for campo in CAMPOS_VENTAS:
        columna = mapeo.get(campo)
        ventas[campo] = tabla[columna] if columna else None
    ventas["fecha_hora"] = convertir_fechas(ventas["fecha_hora"], dia_primero)
    ventas["codigo_barras"] = ventas["codigo_barras"].map(normalizar_codigo)
    ventas["sku"] = ventas["sku"].map(lambda v: "" if vacio(v) else str(v).strip())
    ventas["comprobante"] = ventas["comprobante"].map(lambda v: "" if vacio(v) else str(v).strip())
    for campo in ("cantidad", "precio_unitario", "total", "costo"):
        ventas[campo] = _numeros(ventas[campo]) if mapeo.get(campo) else pd.Series(float("nan"), index=ventas.index)
    falta_total = ventas["total"].isna()
    ventas.loc[falta_total, "total"] = ventas.loc[falta_total, "cantidad"] * ventas.loc[falta_total, "precio_unitario"]
    falta_precio = ventas["precio_unitario"].isna() & ventas["cantidad"].ne(0)
    ventas.loc[falta_precio, "precio_unitario"] = ventas.loc[falta_precio, "total"] / ventas.loc[falta_precio, "cantidad"]
    estadisticas = {
        "lineas_leidas": int(len(ventas)),
        "fechas_invalidas": int(ventas["fecha_hora"].isna().sum()),
        "cantidades_invalidas": int(ventas["cantidad"].isna().sum()),
        "devoluciones": int((ventas["cantidad"] < 0).sum()),
        "sin_codigo": int(((ventas["codigo_barras"] == "") & (ventas["sku"] == "")).sum()),
    }
    ventas = ventas[ventas["fecha_hora"].notna() & ventas["cantidad"].notna()].copy()
    ventas["total"] = ventas["total"].fillna(0.0)
    estadisticas["lineas_validas"] = int(len(ventas))
    return ventas.reset_index(drop=True), estadisticas


def unir_con_catalogo(ventas, catalogo):
    """Marca cada línea con su id_producto del catálogo. Las que no están se separan.
    Une por código de barras; si la línea no trae código, por SKU."""
    por_codigo = {c: i for c, i in zip(catalogo["codigo_barras"], catalogo["id_producto"]) if c}
    por_sku = {s: i for s, i in zip(catalogo["sku"], catalogo["id_producto"]) if s}
    # Vectorizado: por código de barras; si la línea no trae código, por SKU
    codigo = ventas["codigo_barras"].fillna("").astype(str)
    sku = ventas["sku"].fillna("").astype(str)
    por_cod = codigo.map(por_codigo)
    por_s = sku.map(por_sku)
    ventas = ventas.copy()
    ventas["id_producto"] = por_cod.where(codigo != "", por_s.where(sku != "", None))
    ventas["id_producto"] = ventas["id_producto"].astype(object).where(ventas["id_producto"].notna(), None)
    dentro = ventas[ventas["id_producto"].notna()].copy()
    fuera = ventas[ventas["id_producto"].isna()].copy()
    codigos_fuera = fuera["codigo_barras"].where(fuera["codigo_barras"] != "", "SKU:" + fuera["sku"])
    resumen = {
        "lineas_totales": int(len(ventas)),
        "lineas_dentro": int(len(dentro)), "soles_dentro": round(float(dentro["total"].sum()), 2),
        "lineas_fuera": int(len(fuera)), "soles_fuera": round(float(fuera["total"].sum()), 2),
        "codigos_vendidos": int(ventas["codigo_barras"].where(ventas["codigo_barras"] != "", "SKU:" + ventas["sku"]).nunique()),
        "codigos_fuera": int(codigos_fuera.nunique()),
        "productos_con_ventas": int(dentro["id_producto"].nunique()),
        "productos_sin_ventas": int(len(catalogo) - dentro["id_producto"].nunique()),
        "fecha_min": ventas["fecha_hora"].min(), "fecha_max": ventas["fecha_hora"].max(),
    }
    if len(ventas):
        resumen["dias_periodo"] = int((ventas["fecha_hora"].max().normalize() - ventas["fecha_hora"].min().normalize()).days) + 1
    else:
        resumen["dias_periodo"] = 0
    top_fuera = (fuera.groupby(codigos_fuera.rename("codigo")).agg(producto=("producto", "first"), lineas=("total", "size"),
                                                                    soles=("total", "sum"))
                 .sort_values("soles", ascending=False).head(50).reset_index())
    return dentro.reset_index(drop=True), resumen, top_fuera


def ejemplo_fecha_legible(fecha):
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
             "noviembre", "diciembre"]
    return f"{fecha.day} de {meses[fecha.month - 1]} de {fecha.year}, {fecha.strftime('%H:%M')}"


def texto_original_fecha(tabla, mapeo, indice=0):
    columna = mapeo.get("fecha_hora")
    if not columna or not len(tabla):
        return ""
    valor = tabla[columna].iloc[indice]
    return "" if valor is None else re.sub(r"\s+", " ", str(valor))
