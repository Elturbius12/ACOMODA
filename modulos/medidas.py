"""Estimador de medidas por reglas (lee el nombre del producto) e índice de confiabilidad.

Todo valor estimado queda marcado: origen_medidas = 'estimado' (o 'mixto' si faltaba
solo una parte) y origen_atributos = 'estimado'. Nunca se presenta como dato real.
"""

import re

import pandas as pd

from modulos.comun import cargar_ajustes, cargar_perfiles, sin_tildes, vacio

NUMERO = r"(\d+(?:[.,]\d+)?)"
PATRON_ML = re.compile(NUMERO + r"\s*(ML|CC)\b")
PATRON_LITRO = re.compile(NUMERO + r"\s*(L|LT|LTS|LITRO|LITROS)\b")
PATRON_GRAMO = re.compile(NUMERO + r"\s*(G|GR|GRS|GRAMOS)\b")
PATRON_KILO = re.compile(NUMERO + r"\s*(KG|KGS|KILO|KILOS)\b")
PATRON_PAQUETE = re.compile(r"\bX\s*(\d{1,3})\b")
PATRON_PIEZAS = re.compile(r"(\d{1,3})\s*(PCS|PZS|PZAS|PIEZAS|UNID|UNDS?|UNIDADES)\b")
PATRON_CM = re.compile(NUMERO + r"\s*CM\b")
PATRON_DIMENSIONES = re.compile(NUMERO + r"\s*X\s*" + NUMERO + r"\s*X\s*" + NUMERO + r"\s*CM\b")
PALABRAS_CAPACIDAD = ("BALANZA", "CAPACIDAD", "SOPORTA", "HASTA", "CARGA MAX")
# Recipientes: los ml indican su capacidad, no un contenido líquido
RECIPIENTES = ("VASO", "JARRA", "BALDE", "TAPER", "TUPPER", "TERMO", "TOMATODO", "MANTEQUILLERA", "OLLA", "DISPENSADOR",
               "ESCURRIDOR", "BOTELLA VACIA", "CONTENEDOR", "RECIPIENTE", "TAZA", "COPA", "BOWL", "FUENTE", "TINA", "LONCHERA",
               "BIDON", "CANASTA", "CESTO", "PORTA")

COLUMNAS_MEDIDA = ["largo_cm", "ancho_cm", "alto_cm", "peso_kg"]
COLUMNAS_ATRIBUTO = ["apilable", "maximo_apilado", "se_puede_girar", "fragil", "perecible", "peligroso",
                     "valor_alto", "temperatura_requerida"]


def _numero(texto):
    return float(texto.replace(",", "."))


def leer_contenido(nombre):
    """Busca en el nombre el contenido (ml o g), el número de unidades del paquete y un tamaño en cm."""
    texto = sin_tildes(nombre)
    resultado = {"ml": None, "gramos": None, "paquete": 1, "cm": None, "dimensiones": None}
    if (m := PATRON_DIMENSIONES.search(texto)):
        resultado["dimensiones"] = tuple(_numero(m.group(i)) for i in (1, 2, 3))
    if (m := PATRON_ML.search(texto)):
        resultado["ml"] = _numero(m.group(1))
    elif (m := PATRON_LITRO.search(texto)):
        resultado["ml"] = _numero(m.group(1)) * 1000
    if (m := PATRON_GRAMO.search(texto)):
        resultado["gramos"] = _numero(m.group(1))
    elif (m := PATRON_KILO.search(texto)) and not any(p in texto for p in PALABRAS_CAPACIDAD):
        kilos = _numero(m.group(1))
        if kilos <= 50:
            resultado["gramos"] = kilos * 1000
    if (m := PATRON_PAQUETE.search(texto)):
        resultado["paquete"] = max(1, int(m.group(1)))
    elif (m := PATRON_PIEZAS.search(texto)):
        resultado["paquete"] = max(1, int(m.group(1)))
    if (m := PATRON_CM.search(texto)):
        centimetros = _numero(m.group(1))
        if 3 <= centimetros <= 150:
            resultado["cm"] = centimetros
    return resultado


def _acotar(valor, minimo, maximo):
    return max(minimo, min(maximo, valor))


def estimar_medidas(nombre, categoria, perfil):
    """Devuelve (largo, ancho, alto, peso, método) estimados para UNA unidad."""
    contenido = leer_contenido(nombre)
    tipicas = perfil["medidas_tipicas"]
    largo, ancho, alto, peso = tipicas.get(str(categoria).upper(), tipicas["_defecto"])
    paquete = contenido["paquete"]
    # "10G X20" = 20 sobres de 10 g; pero en "100G X100" los 100 g ya son el total (si no, serían 10 kg)
    cantidad_base = contenido["ml"] or contenido["gramos"] or 0
    multiplica = paquete if (paquete <= 12 or cantidad_base * paquete <= 3000) else 1
    es_recipiente = contiene(nombre, RECIPIENTES)
    if contenido["dimensiones"]:
        largo, ancho, alto = contenido["dimensiones"]
        metodo = f"dimensiones escritas en el nombre ({largo:g}×{ancho:g}×{alto:g} cm), peso típico"
    elif contenido["ml"] and es_recipiente:
        volumen = contenido["ml"] * 1.3
        alto = _acotar(1.3 * volumen ** (1 / 3), 4, 45)
        base = (volumen / alto) ** 0.5
        largo, ancho = base, base
        if paquete > 1:  # recipientes iguales se encajan uno dentro de otro
            alto = alto * (1 + 0.08 * (min(paquete, 50) - 1))
        peso = contenido["ml"] / 1000 * 0.2 * min(paquete, 50) + 0.05
        metodo = f"recipiente de {contenido['ml']:g} ml" + (f" × {paquete}" if paquete > 1 else "")
    elif contenido["ml"]:
        mililitros = contenido["ml"] * multiplica
        volumen = mililitros * 1.25
        alto = _acotar(2.2 * (contenido["ml"] * 1.25) ** (1 / 3), 6, 45)
        base = (volumen / alto) ** 0.5
        largo = ancho = base
        if multiplica > 1:  # pack de botellas: se agrupan a lo largo
            largo, ancho = base * 1.5, base / 1.5
        peso = mililitros / 1000 * 1.03 + 0.03
        metodo = f"por contenido: {contenido['ml']:g} ml" + (f" × {multiplica}" if multiplica > 1 else "")
    elif contenido["gramos"]:
        gramos = contenido["gramos"] * multiplica
        volumen = gramos / 0.45
        alto = _acotar(1.2 * volumen ** (1 / 3), 1, 35)
        area = volumen / alto
        largo = (area * 1.6) ** 0.5
        ancho = area / largo
        peso = gramos / 1000 + 0.015
        metodo = f"por contenido: {contenido['gramos']:g} g" + (f" × {multiplica}" if multiplica > 1 else "")
    else:
        metodo = f"medida típica de la categoría {categoria or 'por defecto'}"
        if contenido["cm"]:
            nuevo_largo = min(contenido["cm"], 100)
            peso = peso * _acotar(nuevo_largo / max(largo, 1), 0.3, 3) ** 0.5
            largo = nuevo_largo
            metodo += f", largo de {nuevo_largo:g} cm según el nombre"
        if paquete > 1:
            factor = min(1 + 0.1 * (paquete - 1), 3)
            ancho, peso = ancho * factor, peso * factor
            metodo += f", paquete de {paquete}"
    redondear = lambda v: round(max(0.5, round(v * 2) / 2), 1)
    return redondear(largo), redondear(ancho), redondear(alto), round(max(peso, 0.01), 3), metodo


def contiene(texto, palabras):
    texto = sin_tildes(texto)
    return any(re.search(r"\b" + re.escape(sin_tildes(p)) + r"(S|ES)?\b", texto) for p in palabras)


def completar_catalogo(catalogo, perfil_id="bazar", ajustes=None):
    """Completa medidas y atributos faltantes con estimaciones marcadas."""
    ajustes = ajustes or cargar_ajustes()
    datos_perfiles = cargar_perfiles()
    perfil = datos_perfiles["perfiles"].get(perfil_id) or datos_perfiles["perfiles"]["bazar"]
    palabras = datos_perfiles["palabras_atributos"]
    umbral_valor = ajustes["inventario"]["umbral_valor_alto_soles"]
    maximo_apilado = ajustes["estimacion"]["maximo_apilado"]
    tabla = catalogo.copy()
    for columna in COLUMNAS_MEDIDA + COLUMNAS_ATRIBUTO:
        if columna not in tabla:
            tabla[columna] = None
    origen_medidas, metodos, origen_atributos, atributos_estimados, para_ninos = [], [], [], [], []
    for indice, fila in tabla.iterrows():
        presentes = [not vacio(fila[c]) and float(fila[c]) > 0 for c in COLUMNAS_MEDIDA]
        if all(presentes):
            origen_medidas.append("real")
            metodos.append("medido por el usuario")
        else:
            largo, ancho, alto, peso, metodo = estimar_medidas(fila["producto"], fila["categoria"], perfil)
            for columna, estimado, presente in zip(COLUMNAS_MEDIDA, (largo, ancho, alto, peso), presentes):
                if not presente:
                    tabla.at[indice, columna] = estimado
            origen_medidas.append("mixto" if any(presentes) else "estimado")
            metodos.append(metodo)
        nombre = fila["producto"]
        es_liquido = bool(leer_contenido(nombre)["ml"])
        estimados = []
        sugeridos = {
            "fragil": "si" if contiene(nombre, palabras["fragil"]) else "no",
            "peligroso": "si" if contiene(nombre, palabras["peligroso"]) else "no",
            "perecible": "si" if (contiene(nombre, palabras["perecible"]) or not vacio(fila.get("fecha_vencimiento"))
                                  or str(fila["categoria"]).upper() in ("ALIMENTOS", "BEBIDAS")) else "no",
            "temperatura_requerida": "ambiente",
            "valor_alto": "si" if (fila.get("precio_venta") or 0) >= umbral_valor else "no",
        }
        sugeridos["se_puede_girar"] = "no" if (es_liquido or sugeridos["fragil"] == "si" or
                                               contiene(nombre, palabras["no_girar"])) else "si"
        sugeridos["apilable"] = "no" if (sugeridos["fragil"] == "si" or es_liquido) else "si"
        sugeridos["maximo_apilado"] = maximo_apilado if sugeridos["apilable"] == "si" else 1
        for columna, valor in sugeridos.items():
            if vacio(fila.get(columna)):
                tabla.at[indice, columna] = valor
                estimados.append(columna)
        if tabla.at[indice, "apilable"] == "no":
            tabla.at[indice, "maximo_apilado"] = 1
        origen_atributos.append("estimado" if estimados else "real")
        atributos_estimados.append(", ".join(estimados))
        para_ninos.append(contiene(nombre, palabras["ninos"]))
    tabla["origen_medidas"] = origen_medidas
    tabla["metodo_medidas"] = metodos
    tabla["origen_atributos"] = origen_atributos
    tabla["atributos_estimados"] = atributos_estimados
    tabla["para_ninos"] = para_ninos
    for columna in COLUMNAS_MEDIDA:
        tabla[columna] = pd.to_numeric(tabla[columna], errors="coerce")
    tabla["maximo_apilado"] = pd.to_numeric(tabla["maximo_apilado"], errors="coerce").fillna(1).astype(int)
    tabla["volumen_unitario_cm3"] = tabla["largo_cm"] * tabla["ancho_cm"] * tabla["alto_cm"]
    return tabla


def indice_confiabilidad(catalogo, resumen_ventas=None, factor_local=1.0):
    """% de las ventas en soles cuyos productos tienen medidas reales, multiplicado por la
    precisión de la fuente del local (1.0 Excel o DXF, 0.8 imagen, 0.5 ejemplo)."""
    if catalogo is None or len(catalogo) == 0:
        return {"indice": 0.0, "medidas_reales": 0.0, "factor_local": factor_local, "base": "sin catálogo"}
    reales = catalogo["origen_medidas"].eq("real") if "origen_medidas" in catalogo else pd.Series(False, index=catalogo.index)
    if resumen_ventas is not None and len(resumen_ventas) and resumen_ventas["ventas_soles"].sum() > 0:
        tabla = catalogo[["id_producto"]].assign(real=reales.values).merge(
            resumen_ventas[["id_producto", "ventas_soles"]], on="id_producto", how="left").fillna({"ventas_soles": 0})
        porcentaje = tabla.loc[tabla["real"], "ventas_soles"].sum() / tabla["ventas_soles"].sum()
        base = "ventas en soles"
    else:
        porcentaje = float(reales.mean())
        base = "cantidad de productos (aún no hay ventas)"
    return {"indice": round(100 * porcentaje * factor_local, 1), "medidas_reales": round(100 * porcentaje, 1),
            "factor_local": factor_local, "base": base}
