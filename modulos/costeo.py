"""Costeo editable y exportación a gerencia (Cambio 2).

La tabla de costeo se recalcula al instante (sin volver a optimizar): total de inversión, ahorro
anual, período de recuperación, VAN (tasa editable) y TIR. Los precios de los racks son
SUPUESTOS (valores típicos, confirmar con el proveedor) y así se rotulan en todos los archivos.
"""

import io
from datetime import datetime

import pandas as pd

from modulos.comun import CARPETA_RESULTADOS, cargar_ajustes, cargar_json, guardar_json

RUTA_COSTEO = CARPETA_RESULTADOS / "costeo.json"
COLUMNAS = ["concepto", "cantidad", "unidad", "precio_unitario", "supuesto"]


def tabla_inicial(lista_compra, movimientos, ajustes=None):
    """Filas iniciales: racks propuestos, mano de obra de reubicación, etiquetado, señalización y capacitación."""
    ajustes = ajustes or cargar_ajustes()
    operacion, costeo = ajustes["operacion"], ajustes["costeo"]
    filas = []
    modulos = 0
    for fila in (lista_compra.to_dict("records") if lista_compra is not None and len(lista_compra) else []):
        filas.append({"concepto": f"Rack: {fila['nombre']}", "cantidad": float(fila["cantidad"]), "unidad": "módulo",
                      "precio_unitario": float(fila["precio_unitario"]), "supuesto": "sí (valor típico, confirmar con el proveedor)"})
        filas.append({"concepto": f"Montaje: {fila['nombre']}", "cantidad": float(fila["cantidad"]), "unidad": "módulo",
                      "precio_unitario": float(fila["montaje_unitario"]), "supuesto": "sí (valor típico, confirmar con el proveedor)"})
        modulos += int(fila["cantidad"])
    horas = round(movimientos * operacion["minutos_reubicar_producto"] / 60, 1)
    filas += [
        {"concepto": "Mano de obra de reubicación", "cantidad": horas, "unidad": "hora",
         "precio_unitario": operacion["tarifa_hora_soles"], "supuesto": "sí (tarifa y minutos por producto editables)"},
        {"concepto": "Etiquetado de posiciones", "cantidad": float(max(modulos, 1)), "unidad": "módulo",
         "precio_unitario": costeo["etiquetado_por_modulo_soles"], "supuesto": "sí"},
        {"concepto": "Señalización (pasillos y salidas)", "cantidad": 1.0, "unidad": "global",
         "precio_unitario": costeo["senalizacion_soles"], "supuesto": "sí"},
        {"concepto": "Capacitación del personal", "cantidad": float(costeo["capacitacion_horas"] * costeo["personas_capacitadas"]),
         "unidad": "hora-persona", "precio_unitario": operacion["tarifa_hora_soles"], "supuesto": "sí"},
    ]
    return pd.DataFrame(filas, columns=COLUMNAS)


def con_subtotales(tabla):
    tabla = tabla.copy()
    tabla["cantidad"] = pd.to_numeric(tabla["cantidad"], errors="coerce").fillna(0.0)
    tabla["precio_unitario"] = pd.to_numeric(tabla["precio_unitario"], errors="coerce").fillna(0.0)
    tabla["subtotal"] = (tabla["cantidad"] * tabla["precio_unitario"]).round(2)
    return tabla


def van(flujo_inicial, ahorro_mensual, tasa_anual, meses):
    tasa = (1 + tasa_anual) ** (1 / 12) - 1
    return -flujo_inicial + sum(ahorro_mensual / (1 + tasa) ** t for t in range(1, int(meses) + 1))


def tir_anual(inversion, ahorro_mensual, meses):
    """TIR anual equivalente (bisección sobre la tasa mensual). None si no existe."""
    if inversion <= 0 or ahorro_mensual <= 0 or ahorro_mensual * meses <= inversion:
        return None

    def valor(tasa):
        return -inversion + sum(ahorro_mensual / (1 + tasa) ** t for t in range(1, int(meses) + 1))
    bajo, alto = 0.0, 10.0
    for _ in range(80):
        medio = (bajo + alto) / 2
        if valor(medio) > 0:
            bajo = medio
        else:
            alto = medio
    return (1 + bajo) ** 12 - 1


def calcular(tabla, ahorro_mensual, tasa_anual, horizonte_meses):
    """Resultado económico de una tabla de costeo (rápido: no vuelve a optimizar)."""
    tabla = con_subtotales(tabla)
    inversion = float(tabla["subtotal"].sum())
    racks = float(tabla[tabla["concepto"].str.startswith(("Rack:", "Montaje:"))]["subtotal"].sum())
    tir = tir_anual(inversion, ahorro_mensual, horizonte_meses)
    return {"inversion": round(inversion, 2), "inversion_racks": round(racks, 2),
            "fraccion_racks": round(racks / inversion, 4) if inversion else 0.0,
            "ahorro_mensual": round(ahorro_mensual, 2), "ahorro_anual": round(ahorro_mensual * 12, 2),
            "recuperacion_meses": round(inversion / ahorro_mensual, 1) if ahorro_mensual > 0 else None,
            "van": round(van(inversion, ahorro_mensual, tasa_anual, horizonte_meses), 2),
            "tir_anual": None if tir is None else round(tir, 4), "tasa_anual": tasa_anual, "horizonte_meses": int(horizonte_meses)}


def guardar_escenarios(escenarios, ruta=None):
    """Guarda {nombre: {"tabla": DataFrame, ...}} para reabrir y seguir editando."""
    datos = {nombre: dict(valores, tabla=valores["tabla"].to_dict("records")) for nombre, valores in escenarios.items()}
    guardar_json({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "escenarios": datos}, ruta or RUTA_COSTEO)
    return ruta or RUTA_COSTEO


def cargar_escenarios(ruta=None):
    ruta = ruta or RUTA_COSTEO
    if not ruta.exists():
        return None
    datos = cargar_json(ruta)
    return {nombre: dict(valores, tabla=pd.DataFrame(valores["tabla"], columns=COLUMNAS))
            for nombre, valores in datos.get("escenarios", {}).items()}


# --------------------------------------------------------------------------------------
# Informe gerencial (1 a 2 páginas)
# --------------------------------------------------------------------------------------

def _soles(valor):
    return "—" if valor is None else f"S/ {valor:,.2f}"


def textos_informe(datos):
    """Secciones del informe gerencial con las cifras editadas por el usuario."""
    e = datos["economia"]
    tir = "no existe en el horizonte" if e["tir_anual"] is None else f"{e['tir_anual'] * 100:.1f} % anual"
    recuperacion = "no se recupera con el ahorro estimado" if e["recuperacion_meses"] is None else f"{e['recuperacion_meses']:.1f} meses"
    return [
        ("Problema", datos["problema"]),
        ("Solución propuesta", datos["solucion"]),
        ("Inversión", f"{_soles(e['inversion'])} (racks y montaje: {_soles(e['inversion_racks'])}). Los precios de racks son "
                      "valores típicos de referencia: confirmar con el proveedor."),
        ("Ahorro anual estimado", f"{_soles(e['ahorro_anual'])} ({_soles(e['ahorro_mensual'])} al mes), por menor tiempo de "
                                  "recorrido, estimado por simulación con pedidos reales."),
        ("Recuperación, VAN y TIR", f"Período de recuperación: {recuperacion}. VAN a {e['horizonte_meses']} meses con tasa "
                                    f"{e['tasa_anual'] * 100:.1f} % anual: {_soles(e['van'])}. TIR: {tir}."),
        ("Riesgos", datos["riesgos"]),
        ("Cumplimiento normativo", datos["normativo"]),
        ("Supuestos", datos["supuestos"]),
        ("Recomendación", datos["recomendacion"]),
    ]


def informe_excel(datos, tablas, ruta=None):
    from modulos.reportes import _ajustar_hoja
    ruta = ruta or CARPETA_RESULTADOS / "informe_gerencial.xlsx"
    with pd.ExcelWriter(ruta, engine="openpyxl") as escritor:
        resumen = pd.DataFrame(textos_informe(datos), columns=["Sección", "Contenido"])
        resumen.to_excel(escritor, sheet_name="informe", index=False)
        _ajustar_hoja(escritor.sheets["informe"])
        for nombre, tabla in tablas.items():
            hoja = nombre[:31]
            tabla.to_excel(escritor, sheet_name=hoja, index=False)
            _ajustar_hoja(escritor.sheets[hoja])
    return ruta


def informe_word(datos, tablas, figura_png=None, ruta=None):
    from docx import Document
    from docx.shared import Cm, Pt
    ruta = ruta or CARPETA_RESULTADOS / "informe_gerencial.docx"
    documento = Document()
    for seccion in documento.sections:
        seccion.top_margin = seccion.bottom_margin = Cm(1.6)
        seccion.left_margin = seccion.right_margin = Cm(1.8)
    estilo = documento.styles["Normal"]
    estilo.font.name = "Calibri"
    estilo.font.size = Pt(10)
    documento.add_heading(datos.get("titulo", "Informe gerencial — redistribución del local"), level=1)
    documento.add_paragraph(f"{datos.get('empresa', '')} · {datetime.now():%d/%m/%Y} · Responsable: {datos.get('responsable', '')}")
    for titulo, texto in textos_informe(datos):
        parrafo = documento.add_paragraph()
        parrafo.add_run(f"{titulo}. ").bold = True
        parrafo.add_run(texto)
        parrafo.paragraph_format.space_after = Pt(3)
    if figura_png is not None:
        documento.add_picture(str(figura_png), width=Cm(11))
    for nombre, tabla in tablas.items():
        documento.add_paragraph().add_run(nombre).bold = True
        tabla = tabla.head(12)
        celdas = documento.add_table(rows=1, cols=len(tabla.columns))
        celdas.style = "Light Grid"
        for k, columna in enumerate(tabla.columns):
            celdas.rows[0].cells[k].text = str(columna)
        for fila in tabla.itertuples(index=False):
            nuevas = celdas.add_row().cells
            for k, valor in enumerate(fila):
                nuevas[k].text = f"{valor:,.2f}" if isinstance(valor, float) else str(valor)
        for fila in celdas.rows:
            for celda in fila.cells:
                for p in celda.paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(8)
    documento.add_paragraph("Nota: los precios marcados como supuestos son valores típicos de referencia; la mejora es "
                            "estimada por simulación, no medida en el local.").runs[0].italic = True
    documento.save(ruta)
    return ruta


def a_bytes(ruta):
    return io.BytesIO(open(ruta, "rb").read()).getvalue()
