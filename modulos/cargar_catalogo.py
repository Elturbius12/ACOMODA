"""Carga el catálogo (plantilla de Acomoda o catálogo propio del usuario), lo limpia,
une códigos repetidos, clasifica categorías por palabras y arma el reporte de calidad."""

import io

import pandas as pd

from modulos.comun import (a_numero, cargar_ajustes, cargar_perfiles, nombre_columna_simple,
                           normalizar_codigo, sin_tildes, vacio)
from modulos.medidas import COLUMNAS_MEDIDA, completar_catalogo, contiene
from modulos.plantillas import COLUMNAS_CATALOGO, es_plantilla, validar_plantilla

SIN_CATEGORIA = "SIN CATEGORÍA"

SINONIMOS = {
    "codigo_barras": ["CODIGOBARRAS", "CODIGODEBARRAS", "CODIGODEBARRA", "CODBARRAS", "EAN", "EAN13", "BARCODE", "CODIGOEAN"],
    "sku": ["SKU", "CODIGOINTERNO", "CODIGO", "COD", "ITEM"],
    "producto": ["PRODUCTO", "DESCRIPCION", "NOMBRE", "NOMBREPRODUCTO", "ARTICULO", "DETALLE"],
    "categoria": ["CATEGORIA", "FAMILIA", "LINEA", "RUBRO"],
    "precio_compra": ["PRECIOCOMPRA", "COSTO", "COSTOUNITARIO", "PRECIOCOSTO", "PRECIODECOMPRA"],
    "precio_venta": ["PRECIOVENTA", "PRECIO", "PVP", "PRECIODEVENTA"],
    "stock": ["STOCK", "EXISTENCIA", "EXISTENCIAS", "SALDO", "INVENTARIO"],
    "fecha_vencimiento": ["VENCIMIENTO", "FECHAVENCIMIENTO", "FECHADEVENCIMIENTO", "CADUCIDAD"],
    "peso_kg": ["PESOKG", "PESO"],
    "largo_cm": ["LARGOCM", "LARGO"],
    "ancho_cm": ["ANCHOCM", "ANCHO", "FONDOCM"],
    "alto_cm": ["ALTOCM", "ALTO", "ALTURA"],
    "ubicacion_actual": ["UBICACION", "UBICACIONACTUAL"],
}
COLUMNAS_IGNORADAS_CON_AVISO = {"VOLUMENM2": "VOLUMEN(m²) se ignora: el volumen no se mide en m² y la columna está vacía; se usan largo, ancho y alto en cm."}


def detectar_fila_encabezado(tabla_cruda, sinonimos, filas=15):
    """Fila (0, 1, 2...) que más se parece a un encabezado conocido."""
    conocidos = {s for lista in sinonimos.values() for s in lista}
    mejor, mejor_puntaje = 0, -1
    for numero in range(min(filas, len(tabla_cruda))):
        celdas = [nombre_columna_simple(v) for v in tabla_cruda.iloc[numero].tolist() if not vacio(v)]
        puntaje = sum(1 for c in celdas if c in conocidos)
        if puntaje > mejor_puntaje:
            mejor, mejor_puntaje = numero, puntaje
    return mejor


def mapear_columnas(columnas, sinonimos):
    """Propone {campo_estandar: columna_original} comparando nombres simplificados."""
    simples = {c: nombre_columna_simple(c) for c in columnas}
    mapeo = {}
    for campo, opciones in sinonimos.items():
        for opcion in opciones:  # el orden de la lista da prioridad
            encontrada = next((c for c, s in simples.items() if s == opcion and c not in mapeo.values()), None)
            if encontrada is not None:
                mapeo[campo] = encontrada
                break
    return mapeo


def leer_tabla(contenido, nombre_archivo, sinonimos):
    """Lee un Excel o CSV cualquiera detectando la fila de encabezados. Devuelve (tabla, fila_encabezado)."""
    if nombre_archivo.lower().endswith(".csv"):
        cruda = pd.read_csv(io.BytesIO(contenido), header=None, dtype=object, sep=None, engine="python",
                            encoding_errors="replace", nrows=20)
        fila = detectar_fila_encabezado(cruda, sinonimos)
        tabla = pd.read_csv(io.BytesIO(contenido), header=fila, dtype=object, sep=None, engine="python",
                            encoding_errors="replace")
    else:
        cruda = pd.read_excel(io.BytesIO(contenido), header=None, dtype=object, nrows=20)
        fila = detectar_fila_encabezado(cruda, sinonimos)
        tabla = pd.read_excel(io.BytesIO(contenido), header=fila, dtype=object)
    tabla.columns = [str(c).strip() for c in tabla.columns]
    tabla = tabla[[c for c in tabla.columns if not c.startswith("Unnamed")]]
    return tabla, fila


def inferir_categoria(nombre, reglas):
    """Categoría por palabras del nombre (gana la palabra clave más larga encontrada)."""
    mejor, largo_mejor = None, 0
    for categoria, palabras in reglas.items():
        for palabra in palabras:
            if len(palabra) > largo_mejor and contiene(nombre, [palabra]):
                mejor, largo_mejor = categoria, len(palabra)
    return mejor


def _estandarizar(tabla, mapeo):
    estandar = pd.DataFrame(index=tabla.index)
    for col in COLUMNAS_CATALOGO:
        nombre = col["nombre"]
        origen = mapeo.get(nombre)
        estandar[nombre] = tabla[origen] if origen is not None and origen in tabla else None
    return estandar


def limpiar_catalogo(estandar, fila_inicial=2):
    """Quita filas vacías, normaliza códigos, consolida repetidos y clasifica categorías."""
    calidad = {"filas_leidas": int(len(estandar))}
    tabla = estandar.copy()
    tabla["fila_origen"] = range(fila_inicial, fila_inicial + len(tabla))
    tabla["codigo_barras"] = tabla["codigo_barras"].map(normalizar_codigo)
    tabla["sku"] = tabla["sku"].map(lambda v: "" if vacio(v) else str(v).strip())
    tabla["producto"] = tabla["producto"].map(lambda v: "" if vacio(v) else " ".join(str(v).split()))
    vacias = (tabla["producto"] == "") & (tabla["codigo_barras"] == "") & (tabla["sku"] == "")
    calidad["filas_vacias_descartadas"] = int(vacias.sum())
    tabla = tabla[~vacias].copy()
    sin_nombre = tabla["producto"] == ""
    calidad["sin_nombre"] = tabla.loc[sin_nombre, ["fila_origen", "codigo_barras", "sku"]].to_dict("records")
    tabla.loc[sin_nombre, "producto"] = "(SIN NOMBRE) " + tabla.loc[sin_nombre, "codigo_barras"]
    for columna in ("precio_compra", "precio_venta", "stock", "unidades_por_caja", "largo_caja_cm", "ancho_caja_cm",
                    "alto_caja_cm", "maximo_apilado") + tuple(COLUMNAS_MEDIDA):
        tabla[columna] = pd.to_numeric(tabla[columna].map(a_numero), errors="coerce")
    calidad["medidas_imposibles"] = []
    for columna in COLUMNAS_MEDIDA:
        malos = tabla[columna].notna() & (tabla[columna] <= 0)
        for fila in tabla[malos].itertuples():
            calidad["medidas_imposibles"].append({"fila_origen": fila.fila_origen, "producto": fila.producto,
                                                  "problema": f"{columna} = {getattr(fila, columna)} (debe ser mayor que 0)"})
        tabla.loc[malos, columna] = None
    maximo = cargar_ajustes()["estimacion"]["medida_maxima_cm"]
    for columna in ("largo_cm", "ancho_cm", "alto_cm"):
        grandes = tabla[columna].notna() & (tabla[columna] > maximo)
        for fila in tabla[grandes].itertuples():
            calidad["medidas_imposibles"].append({"fila_origen": fila.fila_origen, "producto": fila.producto,
                                                  "problema": f"{columna} = {getattr(fila, columna)} cm supera {maximo} cm"})
        tabla.loc[grandes, columna] = None

    tabla["id_producto"] = [c if c else (f"SKU:{s}" if s else f"FILA:{f}")
                            for c, s, f in zip(tabla["codigo_barras"], tabla["sku"], tabla["fila_origen"])]
    # Consolidar códigos repetidos sin perder stock
    conteo = tabla["id_producto"].value_counts()
    repetidos = conteo[conteo > 1]
    calidad["codigos_repetidos"] = [
        {"id_producto": i, "veces": int(n), "productos": " | ".join(tabla.loc[tabla["id_producto"] == i, "producto"].unique()[:3]),
         "stock_total": float(tabla.loc[tabla["id_producto"] == i, "stock"].fillna(0).sum())}
        for i, n in repetidos.items()]
    calidad["repeticiones"] = int((repetidos - 1).sum())
    if len(repetidos):
        primeros = tabla.groupby("id_producto", sort=False).first()
        primeros["stock"] = tabla.groupby("id_producto", sort=False)["stock"].apply(lambda s: s.fillna(0).sum())
        tabla = primeros.reset_index()

    # Categorías
    reglas = cargar_perfiles()["reglas_categoria_comunes"]
    tabla["categoria"] = tabla["categoria"].map(lambda v: "" if vacio(v) else sin_tildes(v))
    origen = []
    categorias = []
    for nombre, categoria in zip(tabla["producto"], tabla["categoria"]):
        if categoria:
            categorias.append(categoria)
            origen.append("dato")
        else:
            adivinada = inferir_categoria(nombre, reglas)
            categorias.append(adivinada or SIN_CATEGORIA)
            origen.append("regla" if adivinada else "sin")
    tabla["categoria"] = categorias
    tabla["origen_categoria"] = origen
    calidad["productos"] = int(len(tabla))
    calidad["categoria_dato"] = int((tabla["origen_categoria"] == "dato").sum())
    calidad["categoria_regla"] = int((tabla["origen_categoria"] == "regla").sum())
    calidad["sin_categoria"] = int((tabla["origen_categoria"] == "sin").sum())
    calidad["precio_venta_cero"] = tabla.loc[tabla["precio_venta"].fillna(0) <= 0, ["id_producto", "producto"]].to_dict("records")
    calidad["precio_compra_cero"] = int((tabla["precio_compra"].fillna(0) <= 0).sum())
    calidad["venta_menor_compra"] = tabla.loc[tabla["precio_venta"].fillna(0) < tabla["precio_compra"].fillna(0),
                                              ["id_producto", "producto", "precio_compra", "precio_venta"]].to_dict("records")
    calidad["stock_negativo"] = int((tabla["stock"].fillna(0) < 0).sum())
    return tabla.reset_index(drop=True), calidad


def agregar_atipicos(catalogo, calidad):
    """Densidades imposibles (solo en medidas reales): peso / volumen fuera de 0.01–8 g/cm³."""
    reales = catalogo[catalogo["origen_medidas"] == "real"]
    densidad = reales["peso_kg"] * 1000 / reales["volumen_unitario_cm3"]
    raros = reales[(densidad < 0.01) | (densidad > 8)]
    calidad["atipicos"] = [{"id_producto": f.id_producto, "producto": f.producto,
                            "problema": f"densidad {f.peso_kg * 1000 / f.volumen_unitario_cm3:.3f} g/cm³ poco creíble; revise peso o medidas"}
                           for f in raros.itertuples()]
    calidad["sin_medida_real"] = int((catalogo["origen_medidas"] != "real").sum())
    calidad["con_medida_real"] = int((catalogo["origen_medidas"] == "real").sum())
    return calidad


def cargar_catalogo(contenido, nombre_archivo, perfil_id="bazar"):
    """Punto de entrada. Devuelve un diccionario con:
    catalogo (DataFrame), calidad (dict), es_plantilla, validacion (si es plantilla), mapeo, avisos."""
    resultado = {"catalogo": None, "calidad": {}, "es_plantilla": False, "validacion": None, "mapeo": {}, "avisos": []}
    if nombre_archivo.lower().endswith((".xlsx", ".xlsm")) and es_plantilla(contenido):
        resultado["es_plantilla"] = True
        validacion = validar_plantilla(contenido, "catalogo")
        resultado["validacion"] = validacion
        if validacion["rechazada"]:
            return resultado
        estandar = validacion["tablas"]["DATOS"].drop(columns=["fila_excel"])
        for columna in ("fecha_vencimiento",):
            estandar[columna] = estandar[columna].astype(object)
        fila_inicial = 2
    else:
        tabla, fila_encabezado = leer_tabla(contenido, nombre_archivo, SINONIMOS)
        mapeo = mapear_columnas(tabla.columns, SINONIMOS)
        resultado["mapeo"] = mapeo
        for columna in tabla.columns:
            simple = nombre_columna_simple(columna)
            if simple in COLUMNAS_IGNORADAS_CON_AVISO:
                resultado["avisos"].append(COLUMNAS_IGNORADAS_CON_AVISO[simple])
        if "producto" not in mapeo:
            resultado["avisos"].append("No se encontró la columna con el nombre del producto. Use la plantilla de catálogo.")
            return resultado
        if "codigo_barras" not in mapeo and "sku" not in mapeo:
            resultado["avisos"].append("No se encontró columna de código de barras ni de SKU. Use la plantilla de catálogo.")
            return resultado
        for campo in ("peso_kg", "largo_cm", "ancho_cm", "alto_cm"):
            if campo in mapeo and tabla[mapeo[campo]].map(vacio).all():
                resultado["avisos"].append(f"La columna '{mapeo[campo]}' está vacía en el 100 % de los productos.")
        estandar = _estandarizar(tabla, mapeo)
        fila_inicial = fila_encabezado + 2
    catalogo, calidad = limpiar_catalogo(estandar, fila_inicial)
    catalogo = completar_catalogo(catalogo, perfil_id)
    calidad = agregar_atipicos(catalogo, calidad)
    resultado["catalogo"] = catalogo
    resultado["calidad"] = calidad
    return resultado
