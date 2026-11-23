"""Paquete para redactar el artículo del curso (Cambio 4).

Crea resultados/articulo/ con tablas numeradas (Excel y Word, estilo sobrio tipo APA), figuras
numeradas (PNG a 300 ppp y HTML interactivo), párrafos ya redactados con las cifras reales,
ficha metodológica, normas y fuentes (sin referencias inventadas) y un índice.
Las cifras de los textos salen de las MISMAS tablas, para que siempre coincidan.
"""

import shutil
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

from modulos.comun import CARPETA_RESULTADOS  # noqa: E402
from modulos.interpretar_local import huella_estante, huella_obstaculo  # noqa: E402

CARPETA_ARTICULO = CARPETA_RESULTADOS / "articulo"
VERSION_PROGRAMA = "Acomoda 3.0"
GRISES_ABC = {"A": "#252525", "B": "#737373", "C": "#bdbdbd", "SIN ROTACIÓN": "#f0f0f0", "VACÍO": "#ffffff"}
TRAMAS_ABC = {"A": "", "B": "//", "C": "..", "SIN ROTACIÓN": "", "VACÍO": ""}

plt.rcParams.update({"font.size": 9, "axes.titlesize": 10, "font.family": "DejaVu Sans"})


# --------------------------------------------------------------------------------------
# Tablas
# --------------------------------------------------------------------------------------

def construir_tablas(c):
    """c: contexto con los resultados de la corrida. Devuelve lista de (número, título, DataFrame, nota)."""
    u, calidad, conf = c["union"], c["calidad"], c["confiabilidad"]
    t1 = pd.DataFrame([
        ("Productos en el catálogo", f"{calidad['productos']:,}"),
        ("Productos del catálogo con ventas", f"{u['productos_con_ventas']:,}"),
        ("Líneas de venta leídas", f"{u['lineas_totales']:,}"),
        ("Líneas dentro del catálogo (usadas)", f"{u['lineas_dentro']:,}"),
        ("Líneas fuera del catálogo (descartadas)", f"{u['lineas_fuera']:,} (S/ {u['soles_fuera']:,.2f})"),
        ("Periodo", f"{u['fecha_min']:%d/%m/%Y} – {u['fecha_max']:%d/%m/%Y} ({u['dias_periodo']} días)"),
        ("Pedidos (comprobantes) en el periodo", f"{c['evidencia']['info_pedidos']['pedidos_totales']:,}"),
        ("Productos con medidas reales", f"{calidad['con_medida_real']:,} de {calidad['productos']:,}"),
        ("Índice de confiabilidad", f"{conf['indice']:.0f} %"),
    ], columns=["Dato", "Valor"])
    resumen = c["resumen"]
    abc = resumen.groupby("clase_abc").agg(productos=("producto", "size"), ventas=("ventas_soles", "sum")).reindex(
        ["A", "B", "C", "SIN ROTACIÓN"]).fillna(0).reset_index()
    abc["% de productos"] = (100 * abc["productos"] / max(abc["productos"].sum(), 1)).round(1)
    abc["% de ventas"] = (100 * abc["ventas"] / max(abc["ventas"].sum(), 1)).round(1)
    t2 = abc.rename(columns={"clase_abc": "Clase", "productos": "Productos", "ventas": "Ventas (S/)"})
    t2["Ventas (S/)"] = t2["Ventas (S/)"].round(2)
    local = c["local_base"]
    t3 = pd.DataFrame([
        ("Dimensiones del local", f"{local['largo_m']} × {local['ancho_m']} m; altura libre {local['altura_libre_m']} m"),
        ("Fuente del plano", local.get("fuente") or "-"),
        ("Modo de diseño", {"A": "A: diseño desde cero", "B": "B: reutilizar estantes", "C": "C: mixto"}[c["modo_diseno"]]),
        ("Ancho mínimo de pasillo usado", f"{c['pasillo_m']:.2f} m"),
        ("Presupuesto máximo", "sin tope" if c["presupuesto"] is None else f"S/ {c['presupuesto']:,.2f}"),
        ("Peso λ (inversión vs. recorrido)", f"{c['lambda']:.2f}"),
        ("Velocidad de caminata (supuesto)", f"{c['ajustes']['evidencia']['velocidad_caminata_m_s']} m/s"),
        ("Segundos por producto recogido (supuesto)", f"{c['ajustes']['evidencia']['segundos_por_producto']} s"),
        ("Tarifa de mano de obra (supuesto)", f"S/ {c['ajustes']['operacion']['tarifa_hora_soles']}/h"),
        ("Días de cobertura del stock exhibido", f"{c['parametros'].get('dias_cobertura')}"),
        ("Límite de peso por unidad (ergonomía)", f"{c['parametros'].get('limite_peso_kg')} kg"),
    ], columns=["Característica o supuesto", "Valor"])
    compra = c["lista_compra"]
    if len(compra):
        t4 = compra[["nombre", "cantidad", "precio_unitario", "montaje_unitario", "subtotal"]].rename(columns={
            "nombre": "Tipo de rack", "cantidad": "Cantidad", "precio_unitario": "Precio unitario (S/)*",
            "montaje_unitario": "Montaje (S/)*", "subtotal": "Subtotal (S/)"})
    else:
        t4 = pd.DataFrame([{"Tipo de rack": "(no se compran racks: se reutilizan los existentes)", "Cantidad": 0,
                            "Precio unitario (S/)*": 0, "Montaje (S/)*": 0, "Subtotal (S/)": 0}])
    escenarios = c["evidencia"]["escenarios"].set_index("Escenario").T.reset_index().rename(columns={"index": "Indicador"})
    t5 = escenarios
    p = c["evidencia"]["contraste"]
    t6 = pd.DataFrame([
        ("Hipótesis nula (H₀)", p["h0"]), ("Hipótesis alternativa (H₁)", p["h1"]),
        ("Pedidos comparados (n)", f"{p['n']:,}"), ("Prueba", p["prueba"]),
        ("Normalidad de las diferencias (Shapiro–Wilk, p)", "-" if p.get("p_normalidad") is None else f"{p['p_normalidad']:.3g}"),
        ("Estadístico", "-" if p["estadistico"] is None else f"{p['estadistico']:,.3f}"),
        ("Valor p (unilateral)", f"{p['valor_p']:.3g}"),
        (f"Tamaño del efecto ({p['nombre_efecto']})", f"{p['efecto']:.3f}"),
        ("Distancia media antes (m)", f"{p['media_antes_m']:.2f}"), ("Distancia media después (m)", f"{p['media_despues_m']:.2f}"),
        ("Reducción media (m)", f"{p['reduccion_media_m']:.2f}"), ("Reducción media (%)", f"{p['reduccion_pct']:.2f}"),
        ("IC 95 % de la reducción (%) — bootstrap", f"{p['ic95_pct'][0]:.2f} a {p['ic95_pct'][1]:.2f}"),
    ], columns=["Elemento", "Resultado"])
    t7 = c["sensibilidad"] if c.get("sensibilidad") is not None else pd.DataFrame(
        [{"Parámetro": "(no se calculó la sensibilidad)"}])
    e = c["economia"]
    t8 = pd.DataFrame([
        ("Inversión total (S/)", f"{e['inversion']:,.2f}"), ("— de la cual racks y montaje (S/)*", f"{e['inversion_racks']:,.2f}"),
        ("Ahorro mensual estimado (S/)", f"{e['ahorro_mensual']:,.2f}"), ("Ahorro anual estimado (S/)", f"{e['ahorro_anual']:,.2f}"),
        ("Período de recuperación (meses)", "no se recupera" if e["recuperacion_meses"] is None else f"{e['recuperacion_meses']:.1f}"),
        (f"VAN a {e['horizonte_meses']} meses, tasa {e['tasa_anual'] * 100:.1f} % anual (S/)", f"{e['van']:,.2f}"),
        ("TIR anual", "no existe en el horizonte" if e["tir_anual"] is None else f"{e['tir_anual'] * 100:.1f} %"),
    ], columns=["Indicador", "Valor"])
    t9 = c["reporte_normativo"]
    nota_precios = "* Valores típicos de referencia: confirmar con el proveedor."
    return [
        (1, "Descripción de los datos y calidad", t1, "Solo se usaron las ventas de productos que están en el catálogo."),
        (2, "Clasificación ABC por ventas en soles", t2, "Cortes A/B: 80 % y 95 % de las ventas acumuladas."),
        (3, "Características del local y supuestos del análisis", t3, "Los supuestos son editables en el programa."),
        (4, "Diseño de racks propuesto y lista de compra", t4, nota_precios),
        (5, "Comparación antes y después por indicador", t5,
         "Mejora estimada por simulación con pedidos reales; no medida en el local."),
        (6, "Prueba de hipótesis sobre la distancia por pedido", t6, "Datos pareados: los mismos pedidos antes y después."),
        (7, "Análisis de sensibilidad (±20 %)", t7, "Las variantes se recalculan con la propuesta rápida (heurística)."),
        (8, "Evaluación económica", t8, nota_precios + " El ahorro proviene del menor tiempo de recorrido."),
        (9, "Cumplimiento normativo", t9, "Las normas «por verificar» no están confirmadas en el texto oficial vigente."),
    ]


def tablas_excel(tablas, ruta):
    from modulos.reportes import _ajustar_hoja
    with pd.ExcelWriter(ruta, engine="openpyxl") as escritor:
        for numero, titulo, tabla, nota in tablas:
            hoja = f"Tabla {numero}"
            encabezado = pd.DataFrame([[f"Tabla {numero}"], [titulo]])
            encabezado.to_excel(escritor, sheet_name=hoja, index=False, header=False)
            tabla.to_excel(escritor, sheet_name=hoja, index=False, startrow=3)
            pd.DataFrame([[f"Nota. {nota}"]]).to_excel(escritor, sheet_name=hoja, index=False, header=False,
                                                       startrow=len(tabla) + 5)
            _ajustar_hoja(escritor.sheets[hoja])
    return ruta


def tablas_word(tablas, ruta):
    from docx import Document
    from docx.shared import Pt
    documento = Document()
    documento.styles["Normal"].font.name = "Times New Roman"
    documento.styles["Normal"].font.size = Pt(11)
    for numero, titulo, tabla, nota in tablas:
        documento.add_paragraph().add_run(f"Tabla {numero}").bold = True
        documento.add_paragraph().add_run(titulo).italic = True
        celdas = documento.add_table(rows=1, cols=len(tabla.columns))
        celdas.style = "Table Grid"
        for k, columna in enumerate(tabla.columns):
            celdas.rows[0].cells[k].text = str(columna)
        for fila in tabla.itertuples(index=False):
            nuevas = celdas.add_row().cells
            for k, valor in enumerate(fila):
                nuevas[k].text = "" if valor is None else (f"{valor:,.2f}" if isinstance(valor, float) else str(valor))
        for fila in celdas.rows:
            for celda in fila.cells:
                for parrafo in celda.paragraphs:
                    for run in parrafo.runs:
                        run.font.size = Pt(9)
        parrafo = documento.add_paragraph()
        parrafo.add_run("Nota. ").italic = True
        parrafo.add_run(nota)
        documento.add_paragraph()
    documento.save(ruta)
    return ruta


# --------------------------------------------------------------------------------------
# Figuras (PNG 300 ppp en escala de grises legible + HTML interactivo)
# --------------------------------------------------------------------------------------

def _clase_por_tramo(asignacion, productos, validas):
    datos = {}
    for i, j in asignacion.items():
        clave = (validas.at[j, "estante"], validas.at[j, "tramo"])
        dato = datos.setdefault(clave, {"rot": 0.0, "clases": {}})
        dato["rot"] += float(productos.at[i, "rotacion_diaria"])
        clase = productos.at[i, "clase_abc"]
        dato["clases"][clase] = dato["clases"].get(clase, 0) + max(float(productos.at[i, "rotacion_diaria"]), 0.001)
    return datos


def _dibujar_plano(eje, local, validas, datos, por="abc", titulo=""):
    eje.add_patch(Rectangle((0, 0), local["largo_m"], local["ancho_m"], fill=False, lw=1.8))
    for zona in local.get("zonas", []):
        eje.add_patch(Rectangle((zona["x_m"], zona["y_m"]), zona["largo_m"], zona["ancho_m"], fill=False, ls="--", lw=0.8))
        eje.text(zona["x_m"] + 0.05, zona["y_m"] + 0.05, zona["tipo"], fontsize=6)
    maximo = max([d["rot"] for d in datos.values()] + [1e-9])
    mapa = plt.get_cmap("Greys")
    primer_nivel = validas[validas["nivel"] == 1]
    for tramo in primer_nivel.itertuples():
        dato = datos.get((tramo.estante, tramo.tramo))
        if por == "abc":
            clase = max(dato["clases"], key=dato["clases"].get) if dato else "VACÍO"
            eje.add_patch(Rectangle((tramo.x0, tramo.y0), tramo.x1 - tramo.x0, tramo.y1 - tramo.y0, facecolor=GRISES_ABC[clase],
                                    hatch=TRAMAS_ABC[clase], edgecolor="#000000", lw=0.4))
        else:
            valor = (dato["rot"] / maximo) if dato else 0.0
            eje.add_patch(Rectangle((tramo.x0, tramo.y0), tramo.x1 - tramo.x0, tramo.y1 - tramo.y0, facecolor=mapa(0.1 + 0.85 * valor),
                                    edgecolor="#000000", lw=0.4))
    for estante in local.get("estantes", []):
        x0, y0, x1, y1 = huella_estante(estante)
        eje.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, lw=1.0 if estante.get("existente") else 0.6,
                                ls="-" if estante.get("existente") else (0, (2, 1))))
    for obstaculo in local.get("obstaculos", []):
        if obstaculo["tipo"] in ("rociador", "luminaria"):
            continue
        x0, y0, x1, y1 = huella_obstaculo(obstaculo)
        eje.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor="#000000"))
    eje.set_xlim(-0.3, local["largo_m"] + 0.3)
    eje.set_ylim(-0.3, local["ancho_m"] + 0.3)
    eje.set_aspect("equal")
    eje.set_xlabel("X (m)")
    eje.set_ylabel("Y (m)")
    eje.set_title(titulo)


def _leyenda_abc(eje):
    from matplotlib.patches import Patch
    eje.legend(handles=[Patch(facecolor=GRISES_ABC[k], hatch=TRAMAS_ABC[k], edgecolor="black", label=f"Clase {k}")
                        for k in ("A", "B", "C", "SIN ROTACIÓN")], loc="upper right", fontsize=6, framealpha=0.9)


def _png(figura, carpeta, nombre):
    ruta = carpeta / nombre
    figura.savefig(ruta, dpi=300, bbox_inches="tight")
    plt.close(figura)
    return ruta


def _html(figura, carpeta, nombre):
    ruta = carpeta / nombre
    figura.update_layout(font=dict(family="Arial", size=12), template="simple_white")
    figura.write_html(ruta, include_plotlyjs="directory", full_html=True)
    return ruta


def construir_figuras(c, carpeta):
    from modulos.visual_2d import plano_2d
    from modulos.visual_3d import figura_3d
    solucion, ev = c["solucion"], c["evidencia"]
    productos, validas, local = solucion["productos"], solucion["validas"], solucion["local"]
    figuras = []
    # 1. Plano antes / después
    figura, ejes = plt.subplots(1, 2, figsize=(12, 6 * float(local["ancho_m"]) / float(local["largo_m"]) + 1.2))
    _dibujar_plano(ejes[0], local, validas, _clase_por_tramo(c["antes"], productos, validas), "abc", f"Antes ({c['nombre_antes']})")
    _dibujar_plano(ejes[1], local, validas, _clase_por_tramo(solucion["asignacion"], productos, validas), "abc", "Después (propuesta)")
    _leyenda_abc(ejes[1])
    figuras.append((1, "Plano de planta antes y después (clase ABC dominante por tramo)", _png(figura, carpeta, "figura_1_plano_antes_despues.png"),
                    _html(plano_2d(local, solucion["posiciones"], solucion["ubicaciones"], "abc", parametros=c["parametros"]),
                          carpeta, "figura_1_plano_despues.html")))
    # 2. Mapa de calor
    figura, eje = plt.subplots(figsize=(8, 8 * float(local["ancho_m"]) / float(local["largo_m"]) + 0.8))
    _dibujar_plano(eje, local, validas, _clase_por_tramo(solucion["asignacion"], productos, validas), "calor",
                   "Rotación diaria por tramo (más oscuro = más rotación)")
    figuras.append((2, "Mapa de calor de la rotación en la propuesta", _png(figura, carpeta, "figura_2_mapa_calor.png"),
                    _html(plano_2d(local, solucion["posiciones"], solucion["ubicaciones"], "rotacion", parametros=c["parametros"]),
                          carpeta, "figura_2_mapa_calor.html")))
    # 3. Pareto
    tabla = c["resumen"].sort_values("ventas_soles", ascending=False)
    tabla = tabla[tabla["ventas_soles"] > 0].reset_index(drop=True)
    figura, eje = plt.subplots(figsize=(9, 4.2))
    eje.bar(range(len(tabla)), tabla["ventas_soles"], color="#7f7f7f", width=1.0)
    eje2 = eje.twinx()
    eje2.plot(range(len(tabla)), 100 * tabla["acumulado"], color="black", lw=1.4)
    for corte, estilo in ((80, "--"), (95, ":")):
        eje2.axhline(corte, ls=estilo, color="black", lw=0.8)
    eje.set_xlabel("Productos ordenados por ventas (de mayor a menor)")
    eje.set_ylabel("Ventas en el periodo (S/)")
    eje2.set_ylabel("Ventas acumuladas (%)")
    eje.set_title("Curva de Pareto y cortes ABC (80 % y 95 %)")
    grafico = go.Figure([go.Bar(y=tabla["ventas_soles"], name="Ventas (S/)", marker_color="#7f7f7f"),
                         go.Scatter(y=100 * tabla["acumulado"], name="% acumulado", yaxis="y2", line=dict(color="black"))])
    grafico.update_layout(title="Curva de Pareto y cortes ABC", xaxis_title="Productos ordenados por ventas",
                          yaxis_title="Ventas (S/)", yaxis2=dict(overlaying="y", side="right", title="% acumulado"))
    figuras.append((3, "Curva de Pareto y clasificación ABC", _png(figura, carpeta, "figura_3_pareto_abc.png"),
                    _html(grafico, carpeta, "figura_3_pareto_abc.html")))
    # 4. Réplicas aleatorias con la propuesta marcada
    replicas = ev["replicas"]
    figura, eje = plt.subplots(figsize=(8, 4))
    if len(replicas):
        eje.hist(replicas, bins=min(15, max(5, len(replicas) // 2)), color="#bdbdbd", edgecolor="black", label="Réplicas aleatorias factibles")
    eje.axvline(ev["media_propuesta"], color="black", lw=2, label=f"Propuesta: {ev['media_propuesta']:.1f} m")
    eje.axvline(float(ev["distancias_antes"].mean()), color="black", lw=1.2, ls="--",
                label=f"Antes: {float(ev['distancias_antes'].mean()):.1f} m")
    eje.set_xlabel("Distancia media por pedido (m)")
    eje.set_ylabel("Número de réplicas")
    eje.set_title(f"Distribución de {len(replicas)} distribuciones aleatorias y ubicación de la propuesta")
    eje.legend(fontsize=7)
    grafico = go.Figure([go.Histogram(x=replicas, name="Réplicas aleatorias", marker_color="#bdbdbd")])
    grafico.add_vline(x=ev["media_propuesta"], line_width=3, annotation_text="Propuesta")
    grafico.add_vline(x=float(ev["distancias_antes"].mean()), line_dash="dash", annotation_text="Antes")
    grafico.update_layout(title="Réplicas aleatorias y propuesta", xaxis_title="Distancia media por pedido (m)",
                          yaxis_title="Número de réplicas")
    figuras.append((4, "Distribución de las réplicas aleatorias con la propuesta marcada", _png(figura, carpeta, "figura_4_replicas.png"),
                    _html(grafico, carpeta, "figura_4_replicas.html")))
    # 5. Histograma de la reducción por pedido
    diferencias = ev["diferencias"]
    figura, eje = plt.subplots(figsize=(8, 4))
    eje.hist(diferencias, bins=40, color="#969696", edgecolor="black")
    eje.axvline(0, color="black", lw=1)
    eje.axvline(float(np.mean(diferencias)) if len(diferencias) else 0, color="black", lw=2, ls="--",
                label=f"Media: {float(np.mean(diferencias)) if len(diferencias) else 0:.2f} m")
    eje.set_xlabel("Reducción de la distancia por pedido (m; positivo = la propuesta recorre menos)")
    eje.set_ylabel("Número de pedidos")
    eje.set_title("Reducción de la distancia en cada pedido real")
    eje.legend(fontsize=7)
    grafico = go.Figure([go.Histogram(x=diferencias, marker_color="#969696")])
    grafico.update_layout(title="Reducción por pedido", xaxis_title="Reducción (m)", yaxis_title="Pedidos")
    figuras.append((5, "Histograma de la reducción de distancia por pedido", _png(figura, carpeta, "figura_5_reduccion_por_pedido.png"),
                    _html(grafico, carpeta, "figura_5_reduccion_por_pedido.html")))
    # 6. Sensibilidad
    sens = c.get("sensibilidad")
    figura, eje = plt.subplots(figsize=(8, 4))
    if sens is not None and "Reducción de distancia (%)" in sens:
        etiquetas = sens["Parámetro"] + " " + sens["Variación"]
        eje.barh(etiquetas, sens["Reducción de distancia (%)"], color=["#525252" if s == "sí" else "#d9d9d9"
                                                                      for s in sens["¿Se mantiene la conclusión?"]], edgecolor="black")
        eje.axvline(c["umbrales"]["reduccion_distancia_pct"], color="black", ls="--", lw=1, label="Umbral de reducción")
        eje.legend(fontsize=7)
        grafico = go.Figure([go.Bar(y=etiquetas, x=sens["Reducción de distancia (%)"], orientation="h", marker_color="#525252")])
    else:
        eje.text(0.5, 0.5, "Sensibilidad no calculada", ha="center")
        grafico = go.Figure()
    eje.set_xlabel("Reducción de la distancia media (%)")
    eje.set_title("Sensibilidad de la conclusión (oscuro = se mantiene)")
    grafico.update_layout(title="Sensibilidad (±20 %)", xaxis_title="Reducción de distancia (%)")
    figuras.append((6, "Análisis de sensibilidad", _png(figura, carpeta, "figura_6_sensibilidad.png"),
                    _html(grafico, carpeta, "figura_6_sensibilidad.html")))
    # 7. Vista 3D (captura estática con matplotlib) y HTML interactivo
    figura = plt.figure(figsize=(9, 6))
    eje = figura.add_subplot(projection="3d")
    for estante in local.get("estantes", []):
        x0, y0, x1, y1 = huella_estante(estante)
        eje.bar3d(x0, y0, 0, x1 - x0, y1 - y0, float(estante["alto_m"]), color="#4d4d4d" if estante.get("existente") else "#bdbdbd",
                  edgecolor="black", linewidth=0.3, shade=True)
    eje.set_xlim(0, local["largo_m"])
    eje.set_ylim(0, local["ancho_m"])
    eje.set_zlim(0, float(local.get("altura_libre_m") or 3))
    eje.set_box_aspect((float(local["largo_m"]), float(local["ancho_m"]), float(local.get("altura_libre_m") or 3)))
    eje.set_xlabel("X (m)")
    eje.set_ylabel("Y (m)")
    eje.set_zlabel("Altura (m)")
    eje.set_title("Vista 3D de los racks (gris claro = nuevos, oscuro = existentes)")
    figuras.append((7, "Vista 3D del diseño de racks", _png(figura, carpeta, "figura_7_vista_3d.png"),
                    _html(figura_3d(local, c["parametros"], solucion=solucion, titulo="Vista 3D de la propuesta"),
                          carpeta, "figura_7_vista_3d.html")))
    # 8. Flujo de la metodología
    pasos = ["Catálogo con\nmagnitudes", "Plano del\nlocal", "Reporte de\nventas", "Normativas", "Diseño de racks\n+ modelo único",
             "Simulación con\npedidos reales", "Prueba de\nhipótesis", "Costeo y\nveredicto"]
    figura, eje = plt.subplots(figsize=(12, 2.4))
    for k, texto in enumerate(pasos):
        eje.add_patch(FancyBboxPatch((k * 1.5, 0), 1.2, 1, boxstyle="round,pad=0.05", facecolor="white", edgecolor="black"))
        eje.text(k * 1.5 + 0.6, 0.5, texto, ha="center", va="center", fontsize=7)
        if k < len(pasos) - 1:
            eje.annotate("", xy=(k * 1.5 + 1.5, 0.5), xytext=(k * 1.5 + 1.25, 0.5), arrowprops=dict(arrowstyle="->"))
    eje.set_xlim(-0.2, len(pasos) * 1.5)
    eje.set_ylim(-0.2, 1.2)
    eje.axis("off")
    eje.set_title("Flujo de la metodología")
    grafico = go.Figure()
    for k, texto in enumerate(pasos):
        grafico.add_shape(type="rect", x0=k * 1.5, x1=k * 1.5 + 1.2, y0=0, y1=1, line=dict(color="black"))
        grafico.add_annotation(x=k * 1.5 + 0.6, y=0.5, text=texto.replace("\n", "<br>"), showarrow=False)
    grafico.update_xaxes(visible=False, range=[-0.2, len(pasos) * 1.5])
    grafico.update_yaxes(visible=False, range=[-0.2, 1.2])
    grafico.update_layout(title="Flujo de la metodología", height=260)
    figuras.append((8, "Flujo de la metodología", _png(figura, carpeta, "figura_8_metodologia.png"),
                    _html(grafico, carpeta, "figura_8_metodologia.html")))
    return figuras


# --------------------------------------------------------------------------------------
# Textos
# --------------------------------------------------------------------------------------

def textos(c):
    """Párrafos con las cifras reales (las mismas de las tablas)."""
    u, p, e, ev = c["union"], c["evidencia"]["contraste"], c["economia"], c["evidencia"]
    s = c["solucion"]
    nuevos, existentes = s.get("modulos_nuevos", 0), s.get("modulos_existentes", 0)
    recuperacion = "no se recupera con el ahorro estimado" if e["recuperacion_meses"] is None else f"se recupera en {e['recuperacion_meses']:.1f} meses"
    significativo = p["valor_p"] < c["umbrales"]["valor_p"]
    percentil = ev.get("percentil_propuesta")
    limites = "\n".join(f"- {t}" for t in c["limites"])
    return f"""# Resultados para redactar — {c['empresa']}

> Párrafos generados automáticamente con las cifras de la corrida del {datetime.now():%d/%m/%Y %H:%M}.
> Adáptelos con sus palabras. Todas las cifras coinciden con las Tablas 1 a 9.

## Planteamiento del problema

{c['diagnostico']['frase']} {c.get('problema_usuario') or ''}

## Metodología

Se usaron {u['lineas_dentro']:,} líneas de venta de productos del catálogo, del {u['fecha_min']:%d/%m/%Y} al {u['fecha_max']:%d/%m/%Y}
({u['dias_periodo']} días); se descartaron {u['lineas_fuera']:,} líneas de productos que no están en el catálogo (Tabla 1).
Los productos se clasificaron por el método ABC (Tabla 2). A partir de las medidas del local (Tabla 3), el programa generó
{s.get('candidatos', 0):,} módulos candidatos de rack mediante reglas geométricas que respetan pasillos, salidas y zonas
prohibidas, y resolvió un único modelo de programación lineal entera (asignación generalizada con decisión de instalación
z de cada módulo) con el solver CBC; el objetivo combina el costo de acceso ponderado por la rotación y el costo anualizado
de los racks con un peso λ = {c['lambda']:.2f}. La mejora se evaluó simulando {p['n']:,} pedidos reales (comprobantes) con rutas
por los pasillos (caminos mínimos sobre una cuadrícula y heurística del vecino más cercano), comparando la situación
«{c['nombre_antes']}», {ev['replicas_n']} réplicas aleatorias factibles y la propuesta optimizada. Se aplicó la prueba
{p['prueba']} (unilateral, datos pareados) con α = {c['umbrales']['valor_p']}, y un intervalo de confianza del 95 % por bootstrap
(semilla {ev['semilla']}).

## Resultados

La propuesta instala {nuevos} módulos nuevos{f' y conserva {existentes} existentes' if existentes else ''} (Tabla 4), con una
inversión total de S/ {e['inversion']:,.2f}. La distancia media por pedido pasa de {p['media_antes_m']:.2f} m a
{p['media_despues_m']:.2f} m, una reducción de {p['reduccion_media_m']:.2f} m ({p['reduccion_pct']:.2f} %; IC 95 %:
{p['ic95_pct'][0]:.2f} % a {p['ic95_pct'][1]:.2f} %) (Tablas 5 y 6). El valor p fue {p['valor_p']:.3g}
({'menor' if significativo else 'no menor'} que α), con un tamaño del efecto ({p['nombre_efecto']}) de {p['efecto']:.3f}.
{f'La propuesta recorre menos que el {100 - percentil:.0f} % de las réplicas aleatorias (Figura 4).' if percentil is not None else ''}
El ahorro estimado es S/ {e['ahorro_mensual']:,.2f} al mes y la inversión {recuperacion}; el VAN a {e['horizonte_meses']} meses
es S/ {e['van']:,.2f} (Tabla 8).

## Discusión

{c['veredicto_texto']} {p.get('aviso_n_grande') or ''} El análisis de sensibilidad (Tabla 7) muestra qué conclusiones se
mantienen al variar ±20 % los precios, la rotación, el límite de peso y λ.

## Limitaciones

{limites}

## Conclusiones

{_conclusion(significativo, p['reduccion_pct'], c['umbrales']['reduccion_distancia_pct'], e['recuperacion_meses'], c['umbrales']['recuperacion_max_meses'])}
La decisión de inversión depende de confirmar los precios con proveedores y las medidas de los productos de clase A.
"""


def _conclusion(significativo, reduccion, umbral, meses, meses_max):
    if not significativo or reduccion <= 0:
        texto = (f"La evidencia simulada NO permite afirmar que la propuesta reduzca el recorrido ({reduccion:.2f} % por pedido, "
                 "sin significancia estadística).")
    elif reduccion < umbral:
        texto = (f"La propuesta reduce el recorrido de forma estadísticamente significativa, pero la magnitud es pequeña "
                 f"({reduccion:.2f} % por pedido, por debajo del umbral práctico de {umbral:g} %).")
    else:
        texto = (f"La evidencia simulada respalda que la propuesta reduce el recorrido de picking ({reduccion:.2f} % por pedido, "
                 f"por encima del umbral de {umbral:g} %).")
    if meses is None or meses > meses_max:
        texto += " Con los precios supuestos, la inversión no se recupera en el plazo aceptable."
    return texto


def ficha_metodologica(c):
    parametros = "\n".join(f"- {k}: {v}" for k, v in c["parametros"].items())
    evidencia = c["ajustes"]["evidencia"]
    return f"""# Ficha metodológica (para replicar el análisis)

- Programa: {VERSION_PROGRAMA}
- Fecha y hora de la corrida: {datetime.now():%d/%m/%Y %H:%M}
- Responsable: {c.get('responsable') or '-'}
- Semilla aleatoria: {c['evidencia']['semilla']}
- Datos: catálogo «{c.get('archivo_catalogo') or '-'}», ventas «{c.get('archivo_ventas') or '-'}»
- Periodo: {c['union']['fecha_min']:%d/%m/%Y} – {c['union']['fecha_max']:%d/%m/%Y}
- Pedidos simulados: {c['evidencia']['info_pedidos']['pedidos_usados']:,} de {c['evidencia']['info_pedidos']['pedidos_totales']:,}
  ({'muestra aleatoria reproducible' if c['evidencia']['info_pedidos']['muestreado'] else 'todos'})
- Réplicas aleatorias: {c['evidencia']['replicas_n']}; remuestreos bootstrap: {evidencia['remuestreos_bootstrap']}
- Velocidad de caminata: {evidencia['velocidad_caminata_m_s']} m/s; segundos por producto: {evidencia['segundos_por_producto']}
- Modo: {c['solucion']['modo']}; modo de diseño: {c['modo_diseno']}; λ = {c['lambda']}
- Estado del solver: {c['solucion']['estado']}; tiempo: {c['solucion']['tiempo_s']} s
- Umbrales del veredicto: {c['umbrales']}

## Parámetros normativos y de negocio aplicados

{parametros}

## Supuestos

- Precios de racks: valores típicos de referencia (configuracion/catalogo_racks.json), confirmar con el proveedor.
- Distancias: caminos mínimos sobre una cuadrícula de {c['ajustes']['geometria']['resolucion_grilla_m']} m con los racks instalados.
- Ruta de cada pedido: heurística del vecino más cercano desde y hacia el despacho.
"""


def normas_y_fuentes(c):
    filas = []
    for norma in c["normas"]["normas"]:
        if not norma.get("aplicable"):
            continue
        filas.append(f"| {norma['numero']} | {norma['nombre']} | {norma['estado']} | "
                     f"{'sí' if norma['activa'] else 'no (desactivada por el usuario)'} | {norma.get('fuente') or '-'} |")
    return ("# Normas y fuentes\n\n| Norma | Nombre | Estado | Aplicada | Fuente oficial |\n|---|---|---|---|---|\n"
            + "\n".join(filas) +
            "\n\n**Importante:** las normas con estado «por verificar» usan valores iniciales prudentes que NO están confirmados "
            "en el texto oficial vigente. Verifíquelas antes de citarlas.\n\n"
            "**Referencias bibliográficas:** el programa no sugiere libros ni artículos para no inventar referencias. "
            "Agregue las lecturas de su curso y verifique cada cita en su fuente original.\n")


def leeme(tablas, figuras):
    destino_tabla = {1: "Método (datos)", 2: "Método o Resultados", 3: "Método (caso y supuestos)", 4: "Resultados",
                     5: "Resultados", 6: "Resultados", 7: "Discusión", 8: "Resultados o Discusión", 9: "Discusión"}
    destino_figura = {1: "Resultados", 2: "Resultados", 3: "Método o Resultados", 4: "Resultados", 5: "Resultados",
                      6: "Discusión", 7: "Resultados", 8: "Método"}
    lineas = ["# Índice del paquete del artículo", "", "| Elemento | Título | Sección sugerida | Archivo |", "|---|---|---|---|"]
    for numero, titulo, _, _ in tablas:
        lineas.append(f"| Tabla {numero} | {titulo} | {destino_tabla[numero]} | tablas_articulo.xlsx / .docx |")
    for numero, titulo, png, html in figuras:
        lineas.append(f"| Figura {numero} | {titulo} | {destino_figura[numero]} | {png.name}, {html.name} |")
    lineas += ["", "- `resultados_para_redactar.md`: párrafos con las cifras reales (introducción, método, resultados, discusión).",
               "- `ficha_metodologica.md`: datos, parámetros, semilla y fecha para replicar.",
               "- `normas_y_fuentes.md`: normas usadas y su estado.",
               "- Las figuras HTML se abren con doble clic (usan el archivo plotly.min.js de la misma carpeta)."]
    return "\n".join(lineas) + "\n"


# --------------------------------------------------------------------------------------
# Decisión en una línea y borrador del artículo en Word (en lenguaje sencillo)
# --------------------------------------------------------------------------------------

def decision(c):
    """Lo único que el gerente necesita leer: qué hacer, por qué (cifras clave) y qué falta confirmar.
    Devuelve {"color", "accion", "por_que", "cifras": [(etiqueta, valor, ayuda)], "siguientes": [...]}."""
    p, e = c["evidencia"]["contraste"], c["economia"]
    u = c["umbrales"]
    reduccion = float(p["reduccion_pct"])
    real = p["valor_p"] < u["valor_p"] and reduccion > 0  # la mejora no es casualidad
    meses = e["recuperacion_meses"]
    inversion = float(e["inversion"])
    paga = inversion <= 0 or (meses is not None and meses <= u["recuperacion_max_meses"])
    if real and reduccion >= u["reduccion_distancia_pct"] and paga:
        color, accion = "verde", "SÍ conviene: implemente la propuesta."
        por_que = (f"Los pedidos se arman recorriendo {reduccion:.0f} % menos y "
                   + ("no requiere comprar racks." if inversion <= 0 else f"la inversión se paga en {meses:.0f} meses."))
    elif real and not paga:
        color, accion = "rojo", "NO compre racks todavía. Como máximo, reordene los productos en los estantes que ya tiene."
        por_que = (f"La mejora existe ({reduccion:.1f} % menos recorrido por pedido), pero el ahorro no paga la inversión de "
                   f"S/ {inversion:,.0f} en el plazo aceptable" + (f" (tardaría {meses:.0f} meses)." if meses else " (no se paga nunca)."))
    elif real:
        color, accion = "amarillo", "Pruebe primero en pequeño: reubique solo los productos más vendidos (clase A) y mida."
        por_que = f"La mejora es real pero pequeña ({reduccion:.1f} % menos recorrido por pedido)."
    else:
        color, accion = "rojo", "NO cambie la distribución: la propuesta no demostró mejora."
        por_que = f"La diferencia de recorrido ({reduccion:.1f} %) puede ser casualidad."
    cifras = [("Recorrido por pedido", f"−{reduccion:.1f} %" if reduccion > 0 else f"{-reduccion:+.1f} %",
               f"de {p['media_antes_m']:.1f} m a {p['media_despues_m']:.1f} m por pedido"),
              ("Ahorro al mes", f"S/ {e['ahorro_mensual']:,.0f}", "por caminar menos"),
              ("Inversión", f"S/ {inversion:,.0f}", "precios referenciales: cotizar"),
              ("Se paga en", "nunca" if meses is None else f"{meses:.0f} meses", f"aceptable: hasta {u['recuperacion_max_meses']:g} meses")]
    siguientes = []
    if inversion > 0:
        siguientes.append("Pida 2 cotizaciones reales de los racks de la lista de compra y cámbielas en el costeo (Paso 8).")
    siguientes.append("Mida largo, ancho, alto y peso de los productos de clase A (plantilla prellenada del Paso 1).")
    if not c.get("ubicacion_real"):
        siguientes.append("Anote dónde está hoy cada producto (columna ubicacion_actual) para comparar contra la realidad.")
    siguientes.append("Cronometre 10 pedidos para confirmar la velocidad de caminata usada.")
    return {"color": color, "accion": accion, "por_que": por_que, "cifras": cifras, "siguientes": siguientes[:4]}


def _parrafo(documento, texto, negrita=False, cursiva=False, tamano=None):
    """Párrafo de Word; los espacios [COMPLETAR: …] quedan resaltados en amarillo."""
    import re
    from docx.enum.text import WD_COLOR_INDEX
    from docx.shared import Pt
    parrafo = documento.add_paragraph()
    for trozo in re.split(r"(\[COMPLETAR[^\]]*\])", texto):
        if not trozo:
            continue
        run = parrafo.add_run(trozo)
        run.bold, run.italic = negrita, cursiva
        if tamano:
            run.font.size = Pt(tamano)
        if trozo.startswith("[COMPLETAR"):
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
    return parrafo


def _tabla_docx(documento, tabla):
    from docx.shared import Pt
    celdas = documento.add_table(rows=1, cols=len(tabla.columns))
    celdas.style = "Table Grid"
    for k, columna in enumerate(tabla.columns):
        celdas.rows[0].cells[k].text = str(columna)
    for fila in tabla.head(25).itertuples(index=False):
        nuevas = celdas.add_row().cells
        for k, valor in enumerate(fila):
            nuevas[k].text = "" if valor is None else (f"{valor:,.2f}" if isinstance(valor, float) else str(valor))
    for fila in celdas.rows:
        for celda in fila.cells:
            for parrafo in celda.paragraphs:
                for run in parrafo.runs:
                    run.font.size = Pt(8)


def borrador_articulo(c, tablas, figuras, ruta):
    """Primera versión del artículo científico (Word) con las cifras reales y espacios [COMPLETAR] resaltados.
    Lenguaje sencillo; los términos estadísticos van entre paréntesis solo para el revisor."""
    from docx import Document
    from docx.shared import Inches, Pt
    u, p, e, ev, s = c["union"], c["evidencia"]["contraste"], c["economia"], c["evidencia"], c["solucion"]
    d = decision(c)
    real = p["valor_p"] < c["umbrales"]["valor_p"] and p["reduccion_pct"] > 0
    tabla_por_numero = {numero: (titulo, tabla, nota) for numero, titulo, tabla, nota in tablas}
    figura_por_numero = {numero: (titulo, png) for numero, titulo, png, _ in figuras}
    documento = Document()
    documento.styles["Normal"].font.name = "Times New Roman"
    documento.styles["Normal"].font.size = Pt(12)

    def tabla(numero):
        if numero in tabla_por_numero:
            titulo, datos, nota = tabla_por_numero[numero]
            _parrafo(documento, f"Tabla {numero}", negrita=True)
            _parrafo(documento, titulo, cursiva=True)
            _tabla_docx(documento, datos)
            _parrafo(documento, f"Nota. {nota} Fuente: elaboración propia con Acomoda.", tamano=9)

    def figura(numero):
        if numero in figura_por_numero and figura_por_numero[numero][1].exists():
            titulo, png = figura_por_numero[numero]
            _parrafo(documento, f"Figura {numero}", negrita=True)
            _parrafo(documento, titulo, cursiva=True)
            documento.add_picture(str(png), width=Inches(6.0))
            _parrafo(documento, "Fuente: elaboración propia con Acomoda.", tamano=9)

    aviso = documento.add_paragraph()
    aviso.add_run("BORRADOR GENERADO AUTOMÁTICAMENTE. ").bold = True
    aviso.add_run("Las cifras salen de sus datos. Lo resaltado en amarillo lo completa usted. Revise cada párrafo y "
                  "escríbalo con sus palabras antes de entregarlo. No trae referencias bibliográficas: agréguelas usted "
                  "desde fuentes reales que haya leído (no invente citas).")
    documento.add_heading(f"Rediseño de la distribución de productos para reducir el recorrido de preparación de pedidos "
                          f"en {c['empresa']}", level=0)
    _parrafo(documento, "[COMPLETAR: autores, institución y correo]")

    documento.add_heading("Resumen", level=1)
    _parrafo(documento,
             f"Este estudio busca reducir la distancia que se camina para preparar los pedidos en {c['empresa']}. "
             f"Se analizaron {u['lineas_dentro']:,} líneas de venta reales ({u['fecha_min']:%d/%m/%Y} a {u['fecha_max']:%d/%m/%Y}) "
             f"y se diseñó una nueva distribución de estantes y productos con un modelo de optimización. Al simular "
             f"{p['n']:,} pedidos reales, el recorrido medio por pedido pasó de {p['media_antes_m']:.1f} m a "
             f"{p['media_despues_m']:.1f} m ({p['reduccion_pct']:.1f} % menos)"
             + (", una diferencia que no se explica por azar." if real else ", una diferencia que podría deberse al azar.")
             + f" El ahorro estimado es de S/ {e['ahorro_mensual']:,.0f} al mes frente a una inversión de S/ {e['inversion']:,.0f}. "
             f"Conclusión práctica: {d['accion']}")
    _parrafo(documento, "Palabras clave: distribución de almacenes, ubicación de productos, clasificación ABC, "
                        "preparación de pedidos, optimización. [COMPLETAR: ajuste según la revista]")

    documento.add_heading("1. Introducción", level=1)
    _parrafo(documento, f"{c['diagnostico']['frase']} {c.get('problema_usuario') or ''}")
    _parrafo(documento, "[COMPLETAR: por qué este problema importa para la empresa y para el rubro; cite 3 a 5 estudios reales "
                        "sobre distribución de almacenes o asignación de ubicaciones (Google Académico, Scielo, Redalyc)]")
    _parrafo(documento, f"El objetivo de este trabajo es proponer una distribución de estantes y productos que reduzca el "
                        f"recorrido por pedido en {c['empresa']}, respetando las normas de seguridad aplicables, y evaluar si "
                        f"la inversión necesaria se justifica.")

    documento.add_heading("2. Metodología", level=1)
    _parrafo(documento,
             f"Datos. Se usaron las ventas registradas del {u['fecha_min']:%d/%m/%Y} al {u['fecha_max']:%d/%m/%Y} "
             f"({u['dias_periodo']} días): {u['lineas_dentro']:,} líneas de productos del catálogo; se descartaron "
             f"{u['lineas_fuera']:,} líneas de productos que no están en él (Tabla 1).")
    tabla(1)
    _parrafo(documento, "Clasificación de productos. Los productos se ordenaron según cuánto venden: la clase A reúne a los que "
                        "suman el 80 % de las ventas, la B el siguiente 15 % y la C el resto (clasificación ABC, Tabla 2).")
    tabla(2)
    _parrafo(documento,
             f"Diseño de la distribución. Con las medidas del local (Tabla 3), el programa Acomoda probó "
             f"{s.get('candidatos', 0):,} posiciones posibles para los estantes, descartó las que bloquean salidas, puertas "
             f"o pasillos, y eligió con un modelo matemático de optimización (programación lineal entera, resuelto con CBC) "
             f"dónde poner cada estante y cada producto: los que más se venden quedan más cerca de la zona de despacho, "
             f"sin pasar el peso ni el espacio permitidos.")
    tabla(3)
    _parrafo(documento,
             f"Evaluación. Se repitieron por computadora {p['n']:,} pedidos reales con la distribución «{c['nombre_antes']}» y "
             f"con la propuesta, midiendo los metros caminados por los pasillos. Para saber si la diferencia es real o "
             f"casual se usó una prueba estadística para datos pareados ({p['prueba']}, nivel de significancia "
             f"{c['umbrales']['valor_p']}). También se compararon {ev['replicas_n']} distribuciones al azar.")

    documento.add_heading("3. Resultados", level=1)
    _parrafo(documento,
             f"La propuesta usa {s.get('modulos_nuevos', 0)} estantes nuevos"
             + (f" y conserva {s.get('modulos_existentes', 0)} existentes" if s.get("modulos_existentes") else "")
             + f", con una inversión estimada de S/ {e['inversion']:,.0f} (Tabla 4; precios referenciales por confirmar).")
    tabla(4)
    figura(1)
    _parrafo(documento,
             f"El recorrido medio por pedido bajó de {p['media_antes_m']:.1f} m a {p['media_despues_m']:.1f} m, es decir "
             f"{p['reduccion_media_m']:.1f} m menos ({p['reduccion_pct']:.1f} %; entre {p['ic95_pct'][0]:.1f} % y "
             f"{p['ic95_pct'][1]:.1f} % con 95 % de confianza). "
             + ("Esta diferencia no se explica por azar" if real else "Esta diferencia podría explicarse por azar")
             + f" (valor p = {p['valor_p']:.3g}) (Tablas 5 y 6).")
    tabla(5)
    tabla(6)
    figura(4)
    _parrafo(documento,
             f"En lo económico, el ahorro estimado es de S/ {e['ahorro_mensual']:,.0f} al mes; la inversión "
             + ("no se recupera con ese ahorro" if e["recuperacion_meses"] is None
                else f"se recupera en {e['recuperacion_meses']:.0f} meses") + " (Tabla 8).")
    tabla(8)

    documento.add_heading("4. Discusión", level=1)
    _parrafo(documento, f"{d['por_que']} {c.get('veredicto_texto') or ''}")
    _parrafo(documento, "[COMPLETAR: compare su resultado con los estudios citados en la introducción: ¿la reducción es "
                        "mayor o menor que la que ellos encontraron? ¿por qué?]")
    _parrafo(documento, "Limitaciones. " + " ".join(c.get("limites") or []))

    documento.add_heading("5. Conclusiones", level=1)
    _parrafo(documento, _conclusion(real, p["reduccion_pct"], c["umbrales"]["reduccion_distancia_pct"], e["recuperacion_meses"],
                                    c["umbrales"]["recuperacion_max_meses"]))
    _parrafo(documento, f"Recomendación para la empresa: {d['accion']} Siguientes pasos: " + " ".join(d["siguientes"]))

    documento.add_heading("Referencias", level=1)
    _parrafo(documento, "[COMPLETAR: referencias en formato APA 7. Use solo fuentes que usted haya leído.]")
    documento.save(ruta)
    return ruta


def resumen_decision_md(c):
    d = decision(c)
    lineas = [f"# Decisión — {c['empresa']}", "", f"## {d['accion']}", "", d["por_que"], "",
              "| Dato | Valor | Qué significa |", "|---|---|---|"]
    lineas += [f"| {a} | **{b}** | {h} |" for a, b, h in d["cifras"]]
    lineas += ["", "## Qué hacer ahora", ""] + [f"{k}. {t}" for k, t in enumerate(d["siguientes"], 1)]
    return "\n".join(lineas) + "\n"


def generar_paquete(contexto, carpeta=None):
    """Genera todo el paquete. Devuelve un resumen con las rutas."""
    carpeta = carpeta or CARPETA_ARTICULO
    if carpeta.exists():
        shutil.rmtree(carpeta)
    figuras_dir = carpeta / "figuras"
    figuras_dir.mkdir(parents=True, exist_ok=True)
    tablas = construir_tablas(contexto)
    tablas_excel(tablas, carpeta / "tablas_articulo.xlsx")
    tablas_word(tablas, carpeta / "tablas_articulo.docx")
    figuras = construir_figuras(contexto, figuras_dir)
    (carpeta / "resultados_para_redactar.md").write_text(textos(contexto), encoding="utf-8")
    (carpeta / "ficha_metodologica.md").write_text(ficha_metodologica(contexto), encoding="utf-8")
    (carpeta / "normas_y_fuentes.md").write_text(normas_y_fuentes(contexto), encoding="utf-8")
    (carpeta / "LEEME_articulo.md").write_text(leeme(tablas, figuras), encoding="utf-8")
    borrador_articulo(contexto, tablas, figuras, carpeta / "BORRADOR_articulo.docx")
    (carpeta / "DECISION.md").write_text(resumen_decision_md(contexto), encoding="utf-8")
    return {"carpeta": carpeta, "tablas": len(tablas), "figuras": len(figuras),
            "archivos": sorted(str(r.relative_to(carpeta)) for r in carpeta.rglob("*") if r.is_file())}
