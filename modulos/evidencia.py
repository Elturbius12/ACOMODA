"""Evidencia de que la propuesta resuelve el problema (Cambio 3).

Todo lo de aquí es ANÁLISIS ESTADÍSTICO sobre los resultados; no es otro modelo de optimización:

  - Pedidos reales: cada COMPROBANTE del reporte, reducido a sus productos del catálogo.
  - Distancias reales por los pasillos: una sola matriz de caminos mínimos entre los puntos de
    acceso (scipy.sparse.csgraph sobre la cuadrícula del local), reutilizada en todo el análisis.
  - Ruta de cada pedido: vecino más cercano desde y hacia el despacho.
  - Escenarios: situación actual (o simulada), réplicas aleatorias factibles y propuesta.
  - Contraste de hipótesis pareado (t de Student o Wilcoxon), tamaño del efecto, IC 95 % por bootstrap.
  - Veredicto con umbrales editables y límites de la evidencia.
"""

import math

import numpy as np
import pandas as pd
from scipy import stats
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

from modulos.comun import cargar_ajustes
from modulos.interpretar_local import Grilla, punto_origen
from modulos.modelo_optimo import Capacidad

VERDE, AMARILLO, ROJO = "verde", "amarillo", "rojo"


# --------------------------------------------------------------------------------------
# Pedidos reales
# --------------------------------------------------------------------------------------

def pedidos_reales(ventas, maximo=None, semilla=None, ajustes=None):
    """Lista de pedidos (cada uno, lista de id_producto sin repetir) y un resumen.
    Si hay más de `maximo` pedidos se toma una muestra aleatoria reproducible."""
    ajustes = ajustes or cargar_ajustes()
    maximo = maximo or ajustes["evidencia"]["muestra_pedidos"]
    semilla = ajustes["semilla"] if semilla is None else semilla
    lineas = ventas[ventas["cantidad"] > 0] if "cantidad" in ventas else ventas
    unicos = lineas[["comprobante", "id_producto"]].dropna().drop_duplicates()
    por_pedido = unicos.groupby("comprobante", sort=True)["id_producto"].agg(list)
    total = len(por_pedido)
    muestreado = total > maximo
    if muestreado:
        por_pedido = por_pedido.sample(maximo, random_state=semilla).sort_index()
    tamanos = por_pedido.str.len()
    return list(por_pedido.values), {"pedidos_totales": int(total), "pedidos_usados": int(len(por_pedido)),
                                     "muestreado": bool(muestreado), "semilla": int(semilla),
                                     "productos_por_pedido": round(float(tamanos.mean()), 2) if len(tamanos) else 0.0,
                                     "pedidos_de_una_linea": int((tamanos == 1).sum())}


# --------------------------------------------------------------------------------------
# Matriz de distancias por los pasillos (se calcula una sola vez)
# --------------------------------------------------------------------------------------

class MatrizDistancias:
    """Caminos mínimos (m) entre los puntos de acceso de las posiciones y el despacho."""

    def __init__(self, local, validas, modo="almacen", resolucion=None):
        self.grilla = grilla = Grilla(local, resolucion)
        filas, columnas = grilla.filas, grilla.columnas
        libre = ~grilla.ocupada
        numero = -np.ones((filas, columnas), dtype=int)
        numero[libre] = np.arange(int(libre.sum()))
        origenes, destinos, pesos = [], [], []
        for df, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            f0, f1 = max(0, -df), filas - max(0, df)
            c0, c1 = max(0, -dc), columnas - max(0, dc)
            a = libre[f0:f1, c0:c1] & libre[f0 + df:f1 + df, c0 + dc:c1 + dc]
            if df and dc:  # diagonal: no cortar esquinas
                a &= libre[f0 + df:f1 + df, c0:c1] & libre[f0:f1, c0 + dc:c1 + dc]
            origenes.append(numero[f0:f1, c0:c1][a])
            destinos.append(numero[f0 + df:f1 + df, c0 + dc:c1 + dc][a])
            pesos.append(np.full(int(a.sum()), grilla.resolucion * (math.sqrt(2) if df and dc else 1.0)))
        o, d, w = np.concatenate(origenes), np.concatenate(destinos), np.concatenate(pesos)
        n = int(libre.sum())
        self.grafo = coo_matrix((np.concatenate([w, w]), (np.concatenate([o, d]), np.concatenate([d, o]))), shape=(n, n)).tocsr()
        origen, _ = punto_origen(local, modo)
        puntos = [origen] + list(zip(validas["x_acceso"], validas["y_acceso"]))
        nodos = []
        cache = {}
        for x, y in puntos:
            celda = grilla.celda(x, y)
            if celda not in cache:
                cache[celda] = numero[grilla.celda_libre_cercana(x, y)]
            nodos.append(cache[celda])
        nodos = np.array(nodos)
        self.unicos, inversa = np.unique(nodos, return_inverse=True)
        self.matriz = dijkstra(self.grafo, directed=False, indices=self.unicos)[:, self.unicos]
        # Si algún punto quedara aislado, se usa la línea recta × 3 (y se cuenta)
        aislados = ~np.isfinite(self.matriz)
        self.pares_aislados = int(aislados.sum())
        if self.pares_aislados:
            self.matriz[aislados] = np.nanmax(np.where(np.isfinite(self.matriz), self.matriz, 0)) * 3
        self.deposito = int(inversa[0])
        self.punto_de_posicion = inversa[1:]  # posición j (orden de validas) -> índice en la matriz

    def ruta(self, nodos):
        """Largo (m) de la ruta del vecino más cercano: despacho → productos → despacho."""
        pendientes = list(dict.fromkeys(nodos))
        if not pendientes:
            return 0.0
        actual, total = self.deposito, 0.0
        matriz = self.matriz
        while pendientes:
            fila = matriz[actual, pendientes]
            k = int(np.argmin(fila))
            total += float(fila[k])
            actual = pendientes.pop(k)
        return total + float(matriz[actual, self.deposito])


def simular(asignacion, pedidos, productos, validas, matriz, comparables=None):
    """Distancia (m) y número de productos de cada pedido con una asignación dada.
    Solo cuentan los productos de `comparables` (ubicados en todos los escenarios que se comparan)."""
    indice = {pid: i for i, pid in productos["id_producto"].items()}
    posicion_validas = {j: k for k, j in enumerate(validas.index)}
    nodo_producto = {}
    for i, j in asignacion.items():
        if comparables is None or i in comparables:
            nodo_producto[i] = int(matriz.punto_de_posicion[posicion_validas[j]])
    distancias = np.zeros(len(pedidos))
    cantidad = np.zeros(len(pedidos), dtype=int)
    for k, pedido in enumerate(pedidos):
        nodos = [nodo_producto[indice[p]] for p in pedido if p in indice and indice[p] in nodo_producto]
        cantidad[k] = len(nodos)
        distancias[k] = matriz.ruta(nodos)
    return distancias, cantidad


def tiempos(distancias, cantidad, ajustes=None):
    evidencia = (ajustes or cargar_ajustes())["evidencia"]
    return distancias / evidencia["velocidad_caminata_m_s"] + cantidad * evidencia["segundos_por_producto"]


# --------------------------------------------------------------------------------------
# Réplicas aleatorias factibles
# --------------------------------------------------------------------------------------

def asignacion_aleatoria(productos, pares, validas, local, semilla, por_producto=None):
    """Distribución factible al azar: orden de productos al azar y, para cada uno, una posición al azar
    entre las que tienen espacio (respeta capacidad, peso y reglas duras de los pares posibles)."""
    rng = np.random.default_rng(semilla)
    capacidad = Capacidad(validas, local)
    por_producto = por_producto or {i: g for i, g in pares.groupby("i")}
    asignacion = {}
    for i in rng.permutation(np.array(list(por_producto))):
        opciones = por_producto[i]
        for k in rng.permutation(len(opciones)):
            fila = opciones.iloc[k]
            if capacidad.entra(fila.cubre, fila.ancho_ocupado_m, fila.volumen_m3, fila.peso_kg):
                capacidad.ocupar(fila.cubre, fila.ancho_ocupado_m, fila.volumen_m3, fila.peso_kg, "")
                asignacion[int(i)] = int(fila.j)
                break
    return asignacion


# --------------------------------------------------------------------------------------
# Contraste de hipótesis
# --------------------------------------------------------------------------------------

def contraste(antes, despues, semilla=None, ajustes=None, alfa=0.05):
    """H0: la propuesta no reduce la distancia media por pedido; H1: la reduce (prueba unilateral, pareada)."""
    ajustes = ajustes or cargar_ajustes()
    semilla = ajustes["semilla"] if semilla is None else semilla
    evidencia = ajustes["evidencia"]
    antes, despues = np.asarray(antes, float), np.asarray(despues, float)
    d = antes - despues
    n = len(d)
    resultado = {"n": n, "h0": "La propuesta NO reduce la distancia media por pedido (μ_antes − μ_después ≤ 0).",
                 "h1": "La propuesta SÍ reduce la distancia media por pedido (μ_antes − μ_después > 0).",
                 "media_antes_m": round(float(antes.mean()), 2) if n else 0.0,
                 "media_despues_m": round(float(despues.mean()), 2) if n else 0.0,
                 "reduccion_media_m": round(float(d.mean()), 2) if n else 0.0,
                 "reduccion_pct": round(float(100 * d.mean() / antes.mean()), 2) if n and antes.mean() > 0 else 0.0}
    if n < 3 or np.allclose(d, 0):
        resultado.update({"prueba": "no aplicable", "estadistico": None, "valor_p": 1.0, "efecto": 0.0, "nombre_efecto": "-",
                          "ic95_pct": (0.0, 0.0), "ic95_m": (0.0, 0.0), "p_normalidad": None,
                          "explicacion": "No hay diferencias entre antes y después: no se puede rechazar H0."})
        return resultado
    rng = np.random.default_rng(semilla)
    muestra = d if n <= evidencia["muestra_shapiro"] else rng.choice(d, evidencia["muestra_shapiro"], replace=False)
    p_normal = float(stats.shapiro(muestra).pvalue) if np.ptp(muestra) > 0 else 0.0
    if p_normal >= 0.05:
        prueba = stats.ttest_rel(antes, despues, alternative="greater")
        nombre, estadistico, valor_p = "t de Student pareada", float(prueba.statistic), float(prueba.pvalue)
        efecto, nombre_efecto = float(d.mean() / d.std(ddof=1)) if d.std(ddof=1) > 0 else 0.0, "d de Cohen (dz)"
    else:
        prueba = stats.wilcoxon(antes, despues, alternative="greater", zero_method="wilcox")
        nombre, estadistico, valor_p = "Wilcoxon de rangos con signo", float(prueba.statistic), float(prueba.pvalue)
        no_cero = int((d != 0).sum())
        z = float(stats.norm.isf(min(max(valor_p, 1e-300), 1 - 1e-16)))
        efecto, nombre_efecto = z / math.sqrt(max(no_cero, 1)), "r = Z / √n"
    # Intervalo de confianza del 95 % por bootstrap reproducible (por bloques para cuidar la memoria)
    remuestreos = evidencia["remuestreos_bootstrap"]
    medias_d, medias_pct = [], []
    for inicio in range(0, remuestreos, 200):
        k = min(200, remuestreos - inicio)
        indices = rng.integers(0, n, size=(k, n))
        md = d[indices].mean(axis=1)
        medias_d.append(md)
        medias_pct.append(100 * md / antes[indices].mean(axis=1))
    medias_d, medias_pct = np.concatenate(medias_d), np.concatenate(medias_pct)
    ic_m = tuple(round(float(v), 2) for v in np.percentile(medias_d, [2.5, 97.5]))
    ic_pct = tuple(round(float(v), 2) for v in np.percentile(medias_pct, [2.5, 97.5]))
    explicacion = (f"Se compararon {n:,} pedidos reales con la misma muestra antes y después (datos pareados). "
                   f"La prueba de Shapiro–Wilk sobre las diferencias dio p = {p_normal:.3g}: "
                   + ("las diferencias se pueden tratar como normales y se usó la t de Student pareada. " if p_normal >= 0.05 else
                      "las diferencias NO son normales y se usó la prueba de Wilcoxon de rangos con signo (no paramétrica). ")
                   + f"Valor p = {valor_p:.3g} {'<' if valor_p < alfa else '≥'} {alfa}: "
                   + ("se rechaza H0; la reducción es estadísticamente significativa. " if valor_p < alfa else
                      "no se puede rechazar H0. ")
                   + f"Tamaño del efecto ({nombre_efecto}) = {efecto:.2f}. La reducción media es {d.mean():.2f} m por pedido "
                   f"({resultado['reduccion_pct']:.1f} %), con IC 95 % de {ic_pct[0]:.1f} % a {ic_pct[1]:.1f} %.")
    aviso_n = ""
    if n > 1000:
        aviso_n = ("Con una muestra tan grande, casi cualquier diferencia sale significativa: mire sobre todo el tamaño "
                   "del efecto y la magnitud práctica (metros y segundos por pedido).")
    resultado.update({"prueba": nombre, "estadistico": round(estadistico, 4), "valor_p": valor_p, "efecto": round(efecto, 3),
                      "nombre_efecto": nombre_efecto, "ic95_m": ic_m, "ic95_pct": ic_pct, "p_normalidad": p_normal,
                      "explicacion": explicacion, "aviso_n_grande": aviso_n, "alfa": alfa})
    return resultado


# --------------------------------------------------------------------------------------
# Análisis completo
# --------------------------------------------------------------------------------------

def indicadores_escenario(nombre, distancias, cantidad, kpi, pedidos_mes, ajustes=None):
    t = tiempos(distancias, cantidad, ajustes)
    return {"Escenario": nombre, "Distancia media por pedido (m)": round(float(distancias.mean()), 2),
            "Tiempo medio por pedido (s)": round(float(t.mean()), 1),
            "Distancia total mensual (km)": round(float(distancias.mean()) * pedidos_mes / 1000, 2),
            "Aprovechamiento del volumen (%)": kpi.get("aprovechamiento_volumen_pct") if kpi else None,
            "Incumplimientos duros": kpi.get("incumplimientos_duros") if kpi else None,
            "Incumplimientos blandos": kpi.get("incumplimientos_blandos") if kpi else None}


def analizar(solucion, antes, ventas, pedidos_mes, kpis=None, nombre_antes="Antes", ajustes=None, replicas=None,
             muestra=None, semilla=None, avance=None):
    """Simulación completa con pedidos reales. Devuelve un diccionario con escenarios, réplicas y contraste."""
    ajustes = ajustes or cargar_ajustes()
    semilla = ajustes["semilla"] if semilla is None else semilla
    replicas = ajustes["evidencia"]["replicas_aleatorias"] if replicas is None else replicas
    avance = avance or (lambda f, t: None)
    kpis = kpis or {}
    productos, validas, pares, local = solucion["productos"], solucion["validas"], solucion["pares"], solucion["local"]
    avance(0.05, "Armando los pedidos reales…")
    pedidos, info = pedidos_reales(ventas, muestra, semilla, ajustes)
    avance(0.15, "Calculando la matriz de distancias por los pasillos (una sola vez)…")
    matriz = MatrizDistancias(local, validas, solucion["modo"])
    despues = solucion["asignacion"]
    comparables = set(despues) & set(antes)
    avance(0.3, "Simulando el antes y el después…")
    d_antes, n_antes = simular(antes, pedidos, productos, validas, matriz, comparables)
    d_despues, n_despues = simular(despues, pedidos, productos, validas, matriz, comparables)
    heuristica = solucion.get("asignacion_heuristica") or {}
    d_heur, n_heur = simular(heuristica, pedidos, productos, validas, matriz, comparables & set(heuristica))
    validos = n_despues > 0  # pedidos con al menos un producto comparable
    escenarios = [indicadores_escenario(nombre_antes, d_antes[validos], n_antes[validos], kpis.get(nombre_antes), pedidos_mes, ajustes)]
    por_producto = {i: g for i, g in pares.groupby("i")}
    medias_replicas = []
    for r in range(replicas):
        avance(0.35 + 0.5 * r / max(replicas, 1), f"Réplica aleatoria {r + 1} de {replicas}…")
        asignacion = asignacion_aleatoria(productos, pares, validas, local, semilla + 1 + r, por_producto)
        d_r, _ = simular(asignacion, pedidos, productos, validas, matriz, comparables)
        medias_replicas.append(float(d_r[validos].mean()) if validos.any() else 0.0)
    medias_replicas = np.array(medias_replicas)
    if replicas:
        escenarios.append({"Escenario": f"Réplicas aleatorias (promedio de {replicas})",
                           "Distancia media por pedido (m)": round(float(medias_replicas.mean()), 2),
                           "Tiempo medio por pedido (s)": round(float(medias_replicas.mean() / ajustes["evidencia"]["velocidad_caminata_m_s"]
                                                                       + n_despues[validos].mean() * ajustes["evidencia"]["segundos_por_producto"]), 1),
                           "Distancia total mensual (km)": round(float(medias_replicas.mean()) * pedidos_mes / 1000, 2),
                           "Aprovechamiento del volumen (%)": None, "Incumplimientos duros": 0, "Incumplimientos blandos": None})
    if heuristica:
        escenarios.append(indicadores_escenario("Heurística de respaldo", d_heur[validos], n_heur[validos], None, pedidos_mes, ajustes))
    escenarios.append(indicadores_escenario("Propuesta optimizada", d_despues[validos], n_despues[validos],
                                            kpis.get("Después (modelo)"), pedidos_mes, ajustes))
    avance(0.9, "Contraste de hipótesis y bootstrap…")
    prueba = contraste(d_antes[validos], d_despues[validos], semilla, ajustes)
    media_propuesta = float(d_despues[validos].mean()) if validos.any() else 0.0
    percentil = float(100 * (medias_replicas < media_propuesta).mean()) if replicas else None
    t_antes = tiempos(d_antes[validos], n_antes[validos], ajustes)
    t_despues = tiempos(d_despues[validos], n_despues[validos], ajustes)
    avance(1.0, "Listo.")
    return {"info_pedidos": info, "escenarios": pd.DataFrame(escenarios), "contraste": prueba,
            "replicas": medias_replicas, "percentil_propuesta": percentil, "media_propuesta": media_propuesta,
            "diferencias": d_antes[validos] - d_despues[validos], "distancias_antes": d_antes[validos],
            "distancias_despues": d_despues[validos], "tiempo_medio_antes_s": float(t_antes.mean()) if len(t_antes) else 0.0,
            "tiempo_medio_despues_s": float(t_despues.mean()) if len(t_despues) else 0.0, "pedidos_mes": pedidos_mes,
            "pedidos_sin_productos_comparables": int((~validos).sum()), "productos_comparables": len(comparables),
            "pares_aislados": matriz.pares_aislados, "nombre_antes": nombre_antes, "semilla": semilla, "replicas_n": replicas}


def ahorro_mensual_soles(analisis, ajustes=None):
    """Ahorro de mano de obra al mes por el menor tiempo de recorrido (tarifa editable)."""
    ajustes = ajustes or cargar_ajustes()
    segundos = analisis["tiempo_medio_antes_s"] - analisis["tiempo_medio_despues_s"]
    horas = segundos * analisis["pedidos_mes"] / 3600
    return round(horas * ajustes["operacion"]["tarifa_hora_soles"], 2), round(horas, 1)


# --------------------------------------------------------------------------------------
# Planteamiento del problema
# --------------------------------------------------------------------------------------

def diagnostico(analisis, solucion, antes, kpi_antes, semaforo=None, empresa="la empresa", ubicacion_real=False):
    """Cifras de la situación actual y una frase del problema con esos números."""
    validas, productos = solucion["validas"], solucion["productos"]
    clase_a = [i for i in antes if productos.at[i, "clase_abc"] == "A"]
    desfavorables = None
    if ubicacion_real and clase_a:
        mediana = validas["costo_acceso"].median()
        desfavorables = round(100 * sum(validas.at[antes[i], "costo_acceso"] > mediana for i in clase_a) / len(clase_a), 1)
    no_cumple = sum(1 for f in (semaforo or []) if f.get("resultado") == "no cumple")
    faltante = solucion.get("faltante") or {}
    datos = {"distancia_media_m": round(float(analisis["distancias_antes"].mean()), 2) if len(analisis["distancias_antes"]) else 0.0,
             "tiempo_medio_s": round(analisis["tiempo_medio_antes_s"], 1),
             "pct_clase_a_desfavorable": desfavorables,
             "aprovechamiento_volumen_pct": kpi_antes.get("aprovechamiento_volumen_pct") if kpi_antes else None,
             "incumplimientos_normativos": no_cumple,
             "productos_sin_espacio": int(faltante.get("productos_fuera") or 0),
             "pedidos_mes": round(analisis["pedidos_mes"])}
    frase = (f"En {empresa}, cada pedido obliga hoy a recorrer en promedio {datos['distancia_media_m']:.1f} m "
             f"({datos['tiempo_medio_s']:.0f} s por pedido) y se atienden unos {datos['pedidos_mes']:,} pedidos al mes")
    if desfavorables is not None:
        frase += f"; el {desfavorables:.0f} % de los productos de clase A está en posiciones de acceso desfavorable"
    if datos["aprovechamiento_volumen_pct"] is not None:
        frase += f"; se aprovecha el {datos['aprovechamiento_volumen_pct']:.0f} % del volumen de estantería"
    if no_cumple:
        frase += f"; y hay {no_cumple} incumplimiento(s) normativo(s) detectado(s)"
    frase += "."
    if not ubicacion_real:
        frase += (" (La situación «actual» es SIMULADA: el catálogo no trae la columna ubicacion_actual; "
                  "la evidencia es más débil que con la ubicación real.)")
    datos["frase"] = frase
    return datos


# --------------------------------------------------------------------------------------
# Validación técnica
# --------------------------------------------------------------------------------------

def validacion_tecnica(validacion, resumen_union, total_excel, lineas_excel, reproducible):
    """Tres comprobaciones: restricciones duras, totales de ventas y reproducibilidad."""
    suma = round(resumen_union["soles_dentro"] + resumen_union["soles_fuera"], 2)
    lineas = resumen_union["lineas_dentro"] + resumen_union["lineas_fuera"]
    return pd.DataFrame([
        {"Comprobación": "Validador independiente de restricciones duras", "Resultado": "pasa" if not validacion["duros"] else "falla",
         "Detalle": f"{len(validacion['duros'])} violaciones duras; {len(validacion['blandos'])} reglas blandas no cumplidas"},
        {"Comprobación": "Los totales de ventas cuadran con el Excel original",
         "Resultado": "pasa" if abs(suma - total_excel) < 0.05 and lineas == lineas_excel else "falla",
         "Detalle": f"Dentro + fuera del catálogo = S/ {suma:,.2f} y {lineas:,} líneas; Excel = S/ {total_excel:,.2f} y {lineas_excel:,} líneas"},
        {"Comprobación": "Reproducibilidad (misma semilla, mismo resultado)", "Resultado": "pasa" if reproducible else "falla",
         "Detalle": "Se repitió la simulación con la misma semilla y se obtuvieron las mismas cifras." if reproducible else
                    "Dos corridas con la misma semilla dieron cifras distintas."},
    ])


def es_reproducible(solucion, antes, ventas, pedidos_mes, ajustes=None):
    """Repite una simulación pequeña dos veces con la misma semilla y compara."""
    resultados = [analizar(solucion, antes, ventas, pedidos_mes, ajustes=ajustes, replicas=2, muestra=300) for _ in range(2)]
    a, b = resultados
    return (np.allclose(a["diferencias"], b["diferencias"]) and np.allclose(a["replicas"], b["replicas"]) and
            a["contraste"]["valor_p"] == b["contraste"]["valor_p"])


# --------------------------------------------------------------------------------------
# Veredicto y límites
# --------------------------------------------------------------------------------------

def _estado(cumple, casi):
    return VERDE if cumple else (AMARILLO if casi else ROJO)


def veredicto(datos, umbrales):
    """datos: reduccion_pct, valor_p, duros, ubicados, total_productos, no_cumple, por_verificar, confiabilidad,
    recuperacion_meses. Devuelve (tabla de criterios, texto del veredicto, estado global)."""
    criterios = []
    reduccion = datos["reduccion_pct"]
    meta = umbrales["reduccion_distancia_pct"]
    criterios.append({"Criterio": f"Reducción de la distancia media ≥ {meta:g} %", "Valor": f"{reduccion:.1f} %",
                      "Estado": _estado(reduccion >= meta, reduccion >= meta / 2)})
    alfa = umbrales["valor_p"]
    p = datos["valor_p"]
    criterios.append({"Criterio": f"Significancia estadística (p < {alfa:g})", "Valor": f"p = {p:.3g}",
                      "Estado": _estado(p < alfa, p < 2 * alfa)})
    criterios.append({"Criterio": "Cero violaciones de restricciones duras", "Valor": str(datos["duros"]),
                      "Estado": VERDE if datos["duros"] == 0 else ROJO})
    fraccion = datos["ubicados"] / max(datos["total_productos"], 1)
    criterios.append({"Criterio": "Factibilidad: todos los productos tienen lugar", "Valor": f"{datos['ubicados']} de {datos['total_productos']}",
                      "Estado": _estado(fraccion >= 0.999, fraccion >= 0.95)})
    criterios.append({"Criterio": "Cumplimiento normativo", "Valor": f"{datos['no_cumple']} no cumple; {datos['por_verificar']} por verificar",
                      "Estado": ROJO if datos["no_cumple"] else (AMARILLO if datos["por_verificar"] else VERDE)})
    confiabilidad = datos["confiabilidad"]
    minimo = umbrales["confiabilidad_pct"]
    criterios.append({"Criterio": f"Índice de confiabilidad ≥ {minimo:g} %", "Valor": f"{confiabilidad:.0f} %",
                      "Estado": _estado(confiabilidad >= minimo, confiabilidad >= minimo - 20)})
    meses = datos["recuperacion_meses"]
    maximo = umbrales["recuperacion_max_meses"]
    criterios.append({"Criterio": f"Período de recuperación ≤ {maximo:g} meses",
                      "Valor": "no se recupera" if meses is None else f"{meses:.1f} meses",
                      "Estado": ROJO if meses is None else _estado(meses <= maximo, meses <= 2 * maximo)})
    tabla = pd.DataFrame(criterios)
    rojos = tabla[tabla["Estado"] == ROJO]["Criterio"].tolist()
    amarillos = tabla[tabla["Estado"] == AMARILLO]["Criterio"].tolist()
    if rojos:
        estado = ROJO
        texto = ("NO DEMOSTRADO con los datos actuales. Fallan: " + "; ".join(rojos) + ". " + _que_falta(rojos))
    elif amarillos:
        estado = AMARILLO
        texto = ("PARCIALMENTE: la propuesta mejora la situación, pero hay criterios en el límite: " + "; ".join(amarillos)
                 + ". " + _que_falta(amarillos))
    else:
        estado = VERDE
        texto = ("SÍ, con la evidencia disponible: la propuesta reduce el recorrido de forma significativa, es factible, "
                 "cumple las restricciones y se recupera en un plazo aceptable (mejora ESTIMADA por simulación).")
    return tabla, texto, estado


def _que_falta(criterios):
    consejos = []
    texto = " ".join(criterios)
    if "confiabilidad" in texto:
        consejos.append("mida los productos de clase A (plantilla prellenada del Paso 1) para subir la confiabilidad")
    if "normativo" in texto:
        consejos.append("confirme las normas «por verificar» en el texto oficial y corrija los incumplimientos")
    if "recuperación" in texto:
        consejos.append("revise precios con proveedores o reutilice estantes (modo C)")
    if "Factibilidad" in texto:
        consejos.append("amplíe el presupuesto o libere zonas (vea las alternativas del Paso 5)")
    if "Reducción" in texto or "Significancia" in texto:
        consejos.append("registre la ubicación actual real (columna ubicacion_actual) para medir el antes con datos reales")
    return ("Qué hacer: " + "; ".join(consejos) + ".") if consejos else ""


def limites_evidencia(confiabilidad, resumen_union, ubicacion_real, normas_por_verificar, info_pedidos, calidad=None):
    """Recuadro siempre visible: lo que la evidencia NO demuestra."""
    lineas = [
        "Las mejoras son ESTIMADAS POR SIMULACIÓN con pedidos reales de la empresa; no fueron medidas en el local.",
        f"Índice de confiabilidad de las medidas: {confiabilidad['indice']:.0f} % "
        f"({confiabilidad['medidas_reales']:.0f} % de las ventas en soles tiene medidas reales; el resto es estimado).",
        f"Ventas fuera del catálogo (descartadas): {resumen_union['lineas_fuera']:,} líneas por S/ {resumen_union['soles_fuera']:,.2f}.",
        "Los precios de los racks son VALORES TÍPICOS DE REFERENCIA (confirmar con el proveedor); el tiempo de caminata "
        "y los segundos por producto son supuestos editables.",
        f"Normas «por verificar» (no confirmadas en el texto oficial): {normas_por_verificar}.",
    ]
    if not ubicacion_real:
        lineas.append("La situación «antes» es simulada (no se registró la ubicación actual de los productos).")
    if info_pedidos.get("muestreado"):
        lineas.append(f"Se usó una muestra aleatoria reproducible de {info_pedidos['pedidos_usados']:,} de "
                      f"{info_pedidos['pedidos_totales']:,} pedidos (semilla {info_pedidos['semilla']}).")
    return lineas


# --------------------------------------------------------------------------------------
# Sensibilidad de las conclusiones
# --------------------------------------------------------------------------------------

def sensibilidad_conclusiones(rediseñar, base, umbrales, economia_base, variacion=0.2, avance=None):
    """`rediseñar(cambio)` debe devolver {'reduccion_pct', 'inversion', 'recuperacion_meses'} para un cambio
    {'rotacion': f} / {'limite_peso': f} / {'lambda': f}. Los precios solo cambian la parte económica."""
    filas = []
    pruebas = [("Precios de racks", "precios"), ("Rotación de productos", "rotacion"), ("Límite de peso", "limite_peso"),
               ("λ (inversión vs. recorrido)", "lambda")]
    total = len(pruebas) * 2
    paso = 0
    for nombre, clave in pruebas:
        for signo in (-1, 1):
            factor = 1 + signo * variacion
            if avance:
                avance(paso / total, f"{nombre} {signo * variacion:+.0%}…")
            paso += 1
            if clave == "precios":
                inversion = economia_base["inversion"] * (1 + signo * variacion * economia_base.get("fraccion_racks", 1.0))
                ahorro = economia_base["ahorro_mensual"]
                resultado = {"reduccion_pct": base["reduccion_pct"], "inversion": inversion,
                             "recuperacion_meses": round(inversion / ahorro, 1) if ahorro > 0 else None}
            else:
                resultado = rediseñar({clave: factor})
            meses = resultado["recuperacion_meses"]
            se_mantiene = (resultado["reduccion_pct"] >= umbrales["reduccion_distancia_pct"] and meses is not None
                           and meses <= umbrales["recuperacion_max_meses"])
            filas.append({"Parámetro": nombre, "Variación": f"{signo * variacion:+.0%}",
                          "Reducción de distancia (%)": round(resultado["reduccion_pct"], 1),
                          "Inversión (S/)": round(resultado["inversion"], 2),
                          "Recuperación (meses)": meses, "¿Se mantiene la conclusión?": "sí" if se_mantiene else "no"})
    if avance:
        avance(1.0, "Listo.")
    return pd.DataFrame(filas)
