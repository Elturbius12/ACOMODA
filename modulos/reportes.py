"""Entregables: Excel de la propuesta, figuras y tablas para el informe del curso,
esqueleto del informe en Markdown y acta de confirmaciones."""

import io
import zipfile
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from openpyxl.styles import Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

from modulos.comun import CARPETA_RESULTADOS, leer_acta  # noqa: E402
from modulos.interpretar_local import huella_estante, huella_obstaculo  # noqa: E402
from modulos.visual_2d import COLORES_ABC, COLORES_OBSTACULO  # noqa: E402

CARPETA_FIGURAS = CARPETA_RESULTADOS / "figuras_informe"
COLORES_RESULTADO = {"cumple": "C6EFCE", "no cumple": "FFC7CE", "por verificar": "FFEB9C", "no aplica": "EDEDED"}


def _ajustar_hoja(hoja):
    for columna in hoja.columns:
        largo = max((len(str(c.value)) if c.value is not None else 0) for c in columna[:200])
        hoja.column_dimensions[get_column_letter(columna[0].column)].width = min(max(10, largo + 2), 70)
    for celda in hoja[1]:
        celda.font = Font(bold=True)
        celda.fill = PatternFill("solid", fgColor="DDEBF7")
    hoja.freeze_panes = "A2"


def excel_propuesta(hojas, ruta=None):
    """hojas = {nombre: DataFrame}. Guarda propuesta_distribucion.xlsx y devuelve los bytes."""
    salida = io.BytesIO()
    with pd.ExcelWriter(salida, engine="openpyxl") as escritor:
        for nombre, tabla in hojas.items():
            tabla = tabla if isinstance(tabla, pd.DataFrame) else pd.DataFrame(tabla)
            tabla.to_excel(escritor, sheet_name=nombre[:31], index=False)
            hoja = escritor.sheets[nombre[:31]]
            _ajustar_hoja(hoja)
            if "Resultado de la propuesta" in tabla.columns:
                posicion = list(tabla.columns).index("Resultado de la propuesta") + 1
                for fila in range(2, len(tabla) + 2):
                    celda = hoja.cell(row=fila, column=posicion)
                    celda.fill = PatternFill("solid", fgColor=COLORES_RESULTADO.get(str(celda.value), "FFFFFF"))
    contenido = salida.getvalue()
    ruta = ruta or CARPETA_RESULTADOS / "propuesta_distribucion.xlsx"
    ruta.write_bytes(contenido)
    return contenido


def tabla_resumen(datos):
    """datos: diccionario de pares concepto → valor."""
    return pd.DataFrame([{"Concepto": k, "Valor": v} for k, v in datos.items()])


def tabla_supuestos(catalogo, local, ajustes, parametros):
    filas = [
        ("Medidas de productos", f"{(catalogo['origen_medidas'] != 'real').sum()} de {len(catalogo)} productos con medidas ESTIMADAS por reglas (nombre y categoría)."),
        ("Atributos (frágil, apilable, etc.)", f"{(catalogo['origen_atributos'] != 'real').sum()} productos con atributos estimados por palabras clave."),
        ("Categorías", f"{(catalogo['origen_categoria'] == 'regla').sum()} categorías asignadas por palabras del nombre; "
                       f"{(catalogo['origen_categoria'] == 'sin').sum()} quedaron SIN CATEGORÍA."),
        ("Fuente del local", f"{local.get('fuente')}{' (EJEMPLO, NO ES REAL)' if local.get('es_ejemplo') else ''}"),
        ("Estantes con datos supuestos", f"{sum(1 for e in local.get('estantes', []) if e.get('estimado'))}"),
        ("Ancho de tramo", f"{ajustes['geometria']['ancho_tramo_m']} m"),
        ("Holgura de altura", f"{ajustes['geometria']['holgura_altura_cm']} cm"),
        ("Días de cobertura (stock mínimo)", f"{parametros.get('dias_cobertura')}"),
        ("Límite ergonómico", f"{parametros.get('limite_peso_kg')} kg"),
        ("Velocidad de caminata", f"{ajustes['operacion']['velocidad_caminata_m_s']} m/s"),
        ("Tiempo por línea de pedido", f"{ajustes['operacion']['segundos_por_linea']} s"),
        ("Tarifa por hora", f"S/ {ajustes['operacion']['tarifa_hora_soles']}"),
        ("Distancias", "Se miden caminando por los pasillos (grilla de "
                       f"{ajustes['geometria']['resolucion_grilla_m']} m), ida y vuelta desde el despacho o la caja."),
        ("Línea base 'antes'", "Si no se registró la ubicación actual, se simula con orden alfabético por categoría y con orden aleatorio (semilla fija)."),
        ("Normas por verificar", "Los valores marcados 'por verificar' son iniciales prudentes; deben confirmarse en el texto oficial vigente."),
    ]
    return pd.DataFrame(filas, columns=["Supuesto", "Detalle"])


def tabla_calidad(calidad, resumen_union=None):
    filas = [(k, v if not isinstance(v, list) else len(v)) for k, v in calidad.items()]
    if resumen_union:
        filas += [(f"ventas: {k}", str(v)) for k, v in resumen_union.items()]
    return pd.DataFrame(filas, columns=["Indicador de calidad", "Valor"]).astype(str)


def tabla_acta(sesion=None):
    acta = leer_acta(sesion)
    filas = [{"fecha": e["fecha"], "paso": e["paso"], "responsable": e["responsable"], "confirmado": e["confirmado"],
              "detalle": "; ".join(f"{k}: {v}" for k, v in (e.get("detalle") or {}).items())} for e in acta]
    return pd.DataFrame(filas, columns=["fecha", "paso", "responsable", "confirmado", "detalle"])


def acta_markdown(cambios_normas=(), sesion=None):
    acta = leer_acta(sesion)
    lineas = ["# Acta de levantamiento y confirmaciones", "",
              f"Generada por Acomoda el {datetime.now():%d/%m/%Y %H:%M}.", "",
              "| Fecha | Paso | Responsable | Confirmado | Detalle |", "|---|---|---|---|---|"]
    for entrada in acta:
        detalle = "; ".join(f"{k}: {v}" for k, v in (entrada.get("detalle") or {}).items()).replace("|", "/")
        lineas.append(f"| {entrada['fecha']} | {entrada['paso']} | {entrada['responsable']} | {'Sí' if entrada['confirmado'] else 'No'} | {detalle} |")
    if cambios_normas:
        lineas += ["", "## Excepciones y cambios a normas autorizados por el usuario", "",
                   "| Fecha | Norma | Cambio | Valor original | Responsable |", "|---|---|---|---|---|"]
        for cambio in cambios_normas:
            lineas.append(f"| {cambio['fecha']} | {cambio['norma']} | {cambio['cambio']} | {cambio['original']} | {cambio['responsable']} |")
    texto = "\n".join(lineas) + "\n"
    (CARPETA_RESULTADOS / "acta_confirmaciones.md").write_text(texto, encoding="utf-8")
    return texto


# --------------------------------------------------------------------------------------
# Figuras para el informe (PNG de alta resolución)
# --------------------------------------------------------------------------------------

def _guardar(figura, nombre):
    CARPETA_FIGURAS.mkdir(parents=True, exist_ok=True)
    ruta = CARPETA_FIGURAS / nombre
    figura.savefig(ruta, dpi=220, bbox_inches="tight")
    plt.close(figura)
    return ruta


def figura_plano(local, posiciones=None, ubicaciones=None, color_por="abc", titulo="Plano de planta"):
    figura, eje = plt.subplots(figsize=(10, 10 * float(local["ancho_m"]) / float(local["largo_m"]) + 1))
    eje.add_patch(Rectangle((0, 0), local["largo_m"], local["ancho_m"], fill=False, lw=2.5))
    for zona in local.get("zonas", []):
        eje.add_patch(Rectangle((zona["x_m"], zona["y_m"]), zona["largo_m"], zona["ancho_m"], color="#bfe3ea", alpha=0.6))
        eje.text(zona["x_m"] + 0.1, zona["y_m"] + 0.1, zona["tipo"], fontsize=7, color="#205060")
    datos = {}
    if ubicaciones is not None:
        for fila in ubicaciones[ubicaciones["ubicado"]].itertuples():
            dato = datos.setdefault((fila.estante, fila.tramo), {"rot": 0.0, "clases": {}})
            dato["rot"] += fila.rotacion_diaria
            dato["clases"][fila.clase_abc] = dato["clases"].get(fila.clase_abc, 0) + max(fila.rotacion_diaria, 0.001)
    maximo = max([d["rot"] for d in datos.values()] + [1e-9])
    mapa = plt.get_cmap("YlOrRd")
    for estante in local.get("estantes", []):
        x0, y0, x1, y1 = huella_estante(estante)
        if posiciones is not None and datos:
            for tramo in posiciones[(posiciones["estante"] == estante["id"]) & (posiciones["nivel"] == 1)].itertuples():
                dato = datos.get((estante["id"], tramo.tramo))
                if color_por == "abc":
                    color = COLORES_ABC[max(dato["clases"], key=dato["clases"].get)] if dato else COLORES_ABC["VACÍO"]
                else:
                    color = mapa(dato["rot"] / maximo) if dato else COLORES_ABC["VACÍO"]
                eje.add_patch(Rectangle((tramo.x0, tramo.y0), tramo.x1 - tramo.x0, tramo.y1 - tramo.y0, color=color, ec="#555555", lw=0.5))
        else:
            eje.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, color="#6baed6", ec="#1f3b5a"))
        eje.text((x0 + x1) / 2, (y0 + y1) / 2, estante["id"], ha="center", va="center", fontsize=6)
    for obstaculo in local.get("obstaculos", []):
        if obstaculo["tipo"] in ("rociador", "luminaria"):
            continue
        x0, y0, x1, y1 = huella_obstaculo(obstaculo)
        eje.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, color=COLORES_OBSTACULO.get(obstaculo["tipo"], "#444444")))
        eje.text(x1 + 0.05, y1 + 0.05, obstaculo["id"], fontsize=6)
    if color_por == "abc" and datos:
        from matplotlib.patches import Patch
        eje.legend(handles=[Patch(color=c, label=f"Clase {k}") for k, c in COLORES_ABC.items()], loc="upper right", fontsize=7)
    eje.set_xlim(-0.3, local["largo_m"] + 0.3)
    eje.set_ylim(-0.3, local["ancho_m"] + 0.3)
    eje.set_aspect("equal")
    eje.set_xlabel("X (m)")
    eje.set_ylabel("Y (m)")
    eje.set_title(titulo + (" — EJEMPLO, NO ES REAL" if local.get("es_ejemplo") else ""))
    return figura


def figuras_informe(local, solucion, resumen, ventas_mes, kpis, sensibilidad_tabla=None):
    """Genera los PNG para el informe y devuelve la lista de rutas."""
    rutas = [_guardar(figura_plano(local, solucion["posiciones"], solucion["ubicaciones"], "abc",
                                   "Propuesta: tramos por clase ABC dominante"), "01_plano_abc.png"),
             _guardar(figura_plano(local, solucion["posiciones"], solucion["ubicaciones"], "rotacion",
                                   "Mapa de calor de rotación por tramo"), "02_mapa_calor_rotacion.png")]
    # Pareto ABC
    tabla = resumen.sort_values("ventas_soles", ascending=False).reset_index(drop=True)
    figura, eje = plt.subplots(figsize=(9, 4.5))
    con_ventas = tabla[tabla["ventas_soles"] > 0]
    colores = [COLORES_ABC.get(c, "#999999") for c in con_ventas["clase_abc"]]
    eje.bar(range(len(con_ventas)), con_ventas["ventas_soles"], color=colores, width=1.0)
    eje2 = eje.twinx()
    eje2.plot(range(len(con_ventas)), 100 * con_ventas["acumulado"], color="#222222", lw=1.5)
    eje2.axhline(80, ls="--", color="#d1495b", lw=1)
    eje2.axhline(95, ls="--", color="#edae49", lw=1)
    eje.set_xlabel("Productos ordenados por ventas")
    eje.set_ylabel("Ventas (S/)")
    eje2.set_ylabel("% acumulado")
    eje.set_title("Curva ABC por ventas en soles")
    rutas.append(_guardar(figura, "03_pareto_abc.png"))
    if ventas_mes is not None and len(ventas_mes):
        figura, eje = plt.subplots(figsize=(9, 4))
        eje.bar(ventas_mes["mes"], ventas_mes["ventas_soles"], color="#4c78a8")
        eje.set_title("Ventas por mes (productos del catálogo)")
        eje.set_ylabel("S/")
        eje.tick_params(axis="x", rotation=45)
        rutas.append(_guardar(figura, "04_ventas_por_mes.png"))
    if kpis:
        nombres = list(kpis)
        figura, ejes = plt.subplots(1, 3, figsize=(12, 4))
        for eje, (clave, titulo) in zip(ejes, [("distancia_ponderada_m_dia", "Distancia ponderada (m/día)"),
                                                ("tiempo_por_pedido_s", "Tiempo por pedido (s)"),
                                                ("costo_picking_mes_soles", "Costo de picking (S/ mes)")]):
            valores = [kpis[n][clave] for n in nombres]
            eje.bar(range(len(nombres)), valores, color=["#9e9e9e", "#bdbdbd", "#2a9d8f"][:len(nombres)])
            eje.set_xticks(range(len(nombres)))
            eje.set_xticklabels(nombres, rotation=20, fontsize=8)
            eje.set_title(titulo, fontsize=10)
        figura.suptitle("Antes y después")
        rutas.append(_guardar(figura, "05_antes_despues.png"))
    if sensibilidad_tabla is not None and len(sensibilidad_tabla):
        figura, eje = plt.subplots(figsize=(9, 4))
        etiquetas = sensibilidad_tabla["Peso variado"] + " " + sensibilidad_tabla["Variación"]
        eje.barh(etiquetas, sensibilidad_tabla["% que cambia"], color="#e76f51")
        eje.set_xlabel("% de productos que cambian de lugar")
        eje.set_title("Sensibilidad de la propuesta (±20 % en los pesos)")
        rutas.append(_guardar(figura, "06_sensibilidad.png"))
    return rutas


def tablas_informe(tablas):
    """Guarda las tablas del informe en un Excel aparte."""
    CARPETA_FIGURAS.mkdir(parents=True, exist_ok=True)
    ruta = CARPETA_FIGURAS / "tablas_informe.xlsx"
    with pd.ExcelWriter(ruta, engine="openpyxl") as escritor:
        for nombre, tabla in tablas.items():
            pd.DataFrame(tabla).to_excel(escritor, sheet_name=nombre[:31], index=False)
            _ajustar_hoja(escritor.sheets[nombre[:31]])
    return ruta


def informe_markdown(datos):
    """Esqueleto del informe del curso con los números del caso ya colocados."""
    d = datos
    texto = f"""# Distribución óptima de productos en estantes: caso {d.get('caso', 'tienda')}

*Curso: Modelos Cuantitativos y de Optimización — Administración de Empresas.*
*Borrador generado por Acomoda el {datetime.now():%d/%m/%Y}. Complete las secciones marcadas con [ ].*

## 1. Problema

[Describa la empresa, el local y el problema: tiempos de búsqueda y recorrido, desorden, productos que no se encuentran.]

- Productos del catálogo: **{d.get('productos')}**; con ventas en el periodo: **{d.get('con_ventas')}**.
- Periodo de ventas analizado: **{d.get('periodo')}** ({d.get('dias')} días).
- Local: **{d.get('local')}**.

## 2. Marco teórico

[Asignación generalizada (GAP), clasificación ABC (Pareto), *slotting* o asignación de ubicaciones en almacenes,
ergonomía en la manipulación manual de cargas (RM 375-2008-TR), merchandising por altura de exhibición.]

## 3. Metodología

1. Levantamiento de datos con plantillas: catálogo con medidas, plano del local y reporte de ventas.
2. Validación con compuertas: cada entrada se confirma antes de continuar (ver acta).
3. Análisis descriptivo de ventas: rotación diaria, ABC por soles (A hasta {d.get('corte_a')} acumulado, B hasta {d.get('corte_b')}, C el resto), estacionalidad.
4. Modelo de programación lineal entera (PuLP + CBC) y heurística de respaldo.
5. Comparación contra la línea base y evaluación económica.

## 4. Modelo

**Conjuntos:** productos *i* ({d.get('productos')}); posiciones *j* = tramo de un nivel de un estante ({d.get('posiciones_validas')} utilizables).

**Variables:** x[i,j] ∈ {{0,1}} (el producto *i* va en *j*); y[i] (no ubicado, con penalización alta);
u[c,e] (la categoría *c* usa el estante *e*); s[p,e] (par vendido junto en el mismo estante).

**Objetivo ({d.get('modo')}):** {d.get('objetivo_texto')}

**Restricciones duras:** una posición por producto; ancho, volumen y peso por nivel; altura libre; límite ergonómico
de {d.get('limite_peso')} kg; incompatibilidades por distancia; alto valor y peligrosos solo en posiciones habilitadas;
posiciones que invaden pasillos, salidas, extintores o tableros eliminadas antes de optimizar; stock mínimo de
{d.get('dias_cobertura')} días de venta.

**Tamaño:** {d.get('variables')} variables binarias, {d.get('restricciones')} restricciones. Estado: {d.get('estado')};
brecha {d.get('brecha')}; tiempo {d.get('tiempo')} s.

## 5. Caso

[Describa la tienda, su rubro y cómo se tomaron las medidas.] Índice de confiabilidad: **{d.get('confiabilidad')} %**.

## 6. Resultados

{d.get('tabla_kpi_md', '')}

Figuras: `01_plano_abc.png`, `02_mapa_calor_rotacion.png`, `03_pareto_abc.png`, `04_ventas_por_mes.png`,
`05_antes_despues.png`, `06_sensibilidad.png` y la vista interactiva `visual_3d.html`.

## 7. Evaluación económica

- Movimientos de reubicación: **{d.get('movimientos')}** ({d.get('horas_reubicacion')} h) → costo **S/ {d.get('costo_reubicacion')}**.
- Ahorro mensual estimado: **S/ {d.get('ahorro_mensual')}** ({d.get('horas_ahorradas')} h/mes).
- Período de recuperación: **{d.get('recuperacion')} meses**; VAN a {d.get('horizonte')} meses con tasa {d.get('tasa')}: **S/ {d.get('van')}**.

## 8. Conclusiones

[ ]

## 9. Limitaciones

{d.get('limitaciones_md', '')}
"""
    ruta = CARPETA_RESULTADOS / "informe_esqueleto.md"
    ruta.write_text(texto, encoding="utf-8")
    return texto


def tabla_markdown(tabla):
    columnas = list(tabla.columns)
    lineas = ["| " + " | ".join(map(str, columnas)) + " |", "|" + "---|" * len(columnas)]
    for fila in tabla.itertuples(index=False):
        lineas.append("| " + " | ".join("" if v is None else str(v) for v in fila) + " |")
    return "\n".join(lineas)


def zip_entregables(rutas):
    """Empaqueta archivos en un .zip (en memoria) para descargar."""
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as archivo:
        for ruta in rutas:
            if ruta.exists():
                archivo.write(ruta, arcname=ruta.relative_to(CARPETA_RESULTADOS))
    return salida.getvalue()
