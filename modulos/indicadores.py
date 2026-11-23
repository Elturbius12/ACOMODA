"""Indicadores antes/después, líneas base, validador independiente de restricciones duras,
lista de reubicación y evaluación económica."""

import math
from itertools import permutations

import numpy as np
import pandas as pd

from modulos.comun import cargar_ajustes
from modulos.interpretar_local import distancia_rects, huella_estante
from modulos.modelo_optimo import Capacidad

# --------------------------------------------------------------------------------------
# Líneas base "antes"
# --------------------------------------------------------------------------------------


def _llenar_en_orden(orden_productos, pares, validas, local, recorrer="fisico"):
    """Llena las posiciones en orden físico (estante, nivel, tramo) con los productos en el
    orden dado, como haría una persona sin modelo. No revisa incompatibilidades."""
    capacidad = Capacidad(validas, local)
    orden_posiciones = validas.sort_values(["estante", "nivel", "tramo"]).index.tolist()
    rango = {j: k for k, j in enumerate(orden_posiciones)}
    por_producto = {i: g.assign(rango_fisico=g["j"].map(rango)).sort_values("rango_fisico") for i, g in pares.groupby("i")}
    asignacion = {}
    cursor = 0
    for i in orden_productos:
        if i not in por_producto:
            continue
        opciones = por_producto[i]
        # primero desde donde va el llenado; si no entra, se vuelve a buscar desde el inicio
        for fila in list(opciones[opciones["rango_fisico"] >= cursor].itertuples()) + list(opciones[opciones["rango_fisico"] < cursor].itertuples()):
            if capacidad.entra(fila.cubre, fila.ancho_ocupado_m, fila.volumen_m3, fila.peso_kg):
                capacidad.ocupar(fila.cubre, fila.ancho_ocupado_m, fila.volumen_m3, fila.peso_kg, "")
                asignacion[i] = fila.j
                cursor = fila.rango_fisico
                break
    return asignacion


def linea_base_alfabetica(productos, pares, validas, local):
    orden = productos.sort_values(["categoria", "producto"]).index.tolist()
    return _llenar_en_orden(orden, pares, validas, local)


def linea_base_aleatoria(productos, pares, validas, local, semilla=None):
    semilla = cargar_ajustes()["semilla"] if semilla is None else semilla
    orden = productos.sample(frac=1, random_state=semilla).index.tolist()
    return _llenar_en_orden(orden, pares, validas, local)


def linea_base_actual(productos, pares, validas):
    """Usa la columna ubicacion_actual si el usuario la llenó: una posición exacta (E1-N2-T1) o solo el
    código del estante o zona (E1): en ese caso se toma la primera posición posible de ese estante."""
    if "ubicacion_actual" not in productos:
        return None
    posicion_por_id = {p: j for j, p in validas["id_posicion"].items()}
    claves = set(zip(pares["i"], pares["j"]))
    por_estante = {}
    for i, j in zip(pares["i"], pares["j"]):
        por_estante.setdefault((i, str(validas.at[j, "estante"]).upper()), []).append(j)
    asignacion = {}
    for i, valor in productos["ubicacion_actual"].items():
        if isinstance(valor, str) and valor.strip():
            codigo = valor.strip().upper()
            j = posicion_por_id.get(codigo)
            if j is None and (i, codigo) in por_estante:
                j = min(por_estante[(i, codigo)], key=lambda k: (validas.at[k, "nivel"], validas.at[k, "tramo"]))
            if j is not None and (i, j) in claves:
                asignacion[i] = j
    return asignacion if len(asignacion) >= max(5, 0.2 * len(productos)) else None


# --------------------------------------------------------------------------------------
# Indicadores
# --------------------------------------------------------------------------------------

def evaluar(asignacion, productos, validas, local, pares, estadisticas, modo="almacen", ajustes=None,
            parametros=None, incompatibilidades=None):
    """KPI de una asignación (sirve para el antes y el después)."""
    ajustes = ajustes or cargar_ajustes()
    operacion = ajustes["operacion"]
    indice = pares.set_index(["i", "j"])
    rotacion = productos["m_rotacion"].to_numpy()
    filas = [(i, j) for i, j in asignacion.items()]
    distancia = np.array([validas.at[j, "distancia_m"] for _, j in filas]) if filas else np.array([])
    costo = np.array([validas.at[j, "costo_acceso"] for _, j in filas]) if filas else np.array([])
    exposicion = np.array([validas.at[j, "factor_exposicion"] for _, j in filas]) if filas else np.array([])
    rot = np.array([rotacion[i] for i, _ in filas]) if filas else np.array([])
    margen = np.array([productos.at[i, "margen_diario"] for i, _ in filas]) if filas else np.array([])
    distancia_ponderada = float((rot * distancia * 2).sum())
    distancia_media = float((rot * distancia).sum() / rot.sum()) if rot.sum() > 0 else 0.0
    lineas = estadisticas.get("lineas_por_pedido", 1.0)
    pedidos_dia = estadisticas.get("pedidos_por_dia", 0.0)
    tiempo_pedido = lineas * (2 * distancia_media / operacion["velocidad_caminata_m_s"] + operacion["segundos_por_linea"])
    horas_mes = pedidos_dia * tiempo_pedido * operacion["dias_operacion_mes"] / 3600
    volumen_ocupado = float(sum(indice.at[(i, j), "volumen_m3"] for i, j in filas))
    volumen_total = float((validas["ancho_m"] * validas["fondo_m"] * validas["alto_libre_m"]).sum())
    area_local = float(local["largo_m"]) * float(local["ancho_m"])
    area_estantes = sum((h[2] - h[0]) * (h[3] - h[1]) for h in map(huella_estante, local.get("estantes", [])))
    validacion = validar_solucion(asignacion, productos, validas, local, pares, parametros, incompatibilidades, ajustes)
    return {
        "productos_ubicados": len(filas),
        "productos_sin_ubicar": int(len(productos) - len(filas)),
        "distancia_ponderada_m_dia": round(distancia_ponderada, 1),
        "distancia_media_por_linea_m": round(distancia_media, 2),
        "costo_acceso_ponderado": round(float((rot * costo).sum()), 2),
        "exposicion_margen_soles_dia": round(float((margen * exposicion).sum()), 2),
        "tiempo_por_pedido_s": round(tiempo_pedido, 1),
        "horas_picking_mes": round(horas_mes, 1),
        "costo_picking_mes_soles": round(horas_mes * operacion["tarifa_hora_soles"], 2),
        "aprovechamiento_volumen_pct": round(100 * volumen_ocupado / volumen_total, 1) if volumen_total else 0.0,
        "aprovechamiento_area_pct": round(100 * area_estantes / area_local, 1) if area_local else 0.0,
        "incumplimientos_duros": len(validacion["duros"]),
        "incumplimientos_blandos": len(validacion["blandos"]),
    }


NOMBRES_KPI = {
    "productos_ubicados": "Productos ubicados",
    "productos_sin_ubicar": "Productos sin ubicar",
    "distancia_ponderada_m_dia": "Distancia de picking ponderada (m/día)",
    "distancia_media_por_linea_m": "Distancia media por línea (m, ida)",
    "costo_acceso_ponderado": "Costo de acceso ponderado (objetivo almacén)",
    "exposicion_margen_soles_dia": "Margen × exposición (objetivo tienda)",
    "tiempo_por_pedido_s": "Tiempo estimado por pedido (s)",
    "horas_picking_mes": "Horas de picking al mes",
    "costo_picking_mes_soles": "Costo de picking al mes (S/)",
    "aprovechamiento_volumen_pct": "Aprovechamiento del volumen (%)",
    "aprovechamiento_area_pct": "Aprovechamiento del área (%)",
    "incumplimientos_duros": "Incumplimientos de restricciones duras",
    "incumplimientos_blandos": "Incumplimientos de reglas blandas",
}


def tabla_antes_despues(kpis):
    """kpis = {'Antes (alfabético)': {...}, 'Después (modelo)': {...}} -> DataFrame legible."""
    filas = []
    for clave, nombre in NOMBRES_KPI.items():
        fila = {"Indicador": nombre}
        for escenario, valores in kpis.items():
            fila[escenario] = valores.get(clave)
        filas.append(fila)
    return pd.DataFrame(filas)


# --------------------------------------------------------------------------------------
# Validador independiente (no usa los cálculos del modelo)
# --------------------------------------------------------------------------------------

def _ancho_minimo(largo, ancho, alto, girar, apilado, cantidad, ancho_pos, fondo_pos, alto_pos, holgura):
    """Recalcula por fuerza bruta el menor ancho (cm) que ocupa la cantidad. None si no entra."""
    if girar:
        orientaciones = set(permutations((largo, ancho, alto)))
    else:
        orientaciones = {(largo, ancho, alto), (ancho, largo, alto)}
    mejor = None
    for frente, fondo, altura in orientaciones:
        if altura + holgura > alto_pos or fondo > fondo_pos:
            continue
        capas = max(1, min(apilado, int((alto_pos - holgura) // altura)))
        por_frente = max(1, int(fondo_pos // fondo) * capas)
        ocupado = math.ceil(cantidad / por_frente) * frente
        if ocupado <= ancho_pos + 1e-6 and (mejor is None or ocupado < mejor):
            mejor = ocupado
    return mejor


def validar_solucion(asignacion, productos, validas, local, pares, parametros=None, incompatibilidades=None, ajustes=None):
    """Revisa una asignación contra TODAS las restricciones duras, de forma independiente.
    Devuelve {'duros': [textos], 'blandos': [textos]}."""
    ajustes = ajustes or cargar_ajustes()
    holgura = ajustes["geometria"]["holgura_altura_cm"]
    parametros = parametros or {}
    duros, blandos = [], []
    cubre = pares.set_index(["i", "j"])["cubre"].to_dict()
    uso_ancho, uso_peso_nivel, uso_piso, estantes_categoria = {}, {}, {}, {}
    equipos = {e.get("tipo") for e in local.get("equipos", [])}
    limite = parametros.get("limite_peso_kg")
    vistos = set()
    for i, j in asignacion.items():
        producto = productos.loc[i]
        nombre = producto["producto"][:40]
        if i in vistos:
            duros.append(f"{nombre}: asignado más de una vez")
        vistos.add(i)
        tramos = cubre.get((i, j), (j,))
        if any(not validas.at[t, "valida"] for t in tramos):
            duros.append(f"{nombre}: usa una posición eliminada ({validas.at[j, 'id_posicion']})")
        posicion = validas.loc[j]
        ancho_total = sum(validas.at[t, "ancho_m"] for t in tramos) * 100
        if len({(validas.at[t, "estante"], validas.at[t, "nivel"]) for t in tramos}) > 1:
            duros.append(f"{nombre}: ocupa tramos de niveles distintos")
        cantidad = int(producto["m_cantidad"])
        minimo = _ancho_minimo(producto["m_largo"], producto["m_ancho"], producto["m_alto"],
                               producto.get("se_puede_girar") == "si", int(producto["m_apilado"]), cantidad,
                               ancho_total, posicion["fondo_m"] * 100, posicion["alto_libre_m"] * 100, holgura)
        if minimo is None:
            duros.append(f"{nombre}: el stock mínimo de {cantidad} u. no entra en {posicion['id_posicion']} (alto, fondo o ancho)")
            minimo = ancho_total
        for t in tramos:
            uso_ancho[t] = uso_ancho.get(t, 0) + minimo / len(tramos)
        peso = cantidad * float(producto["m_peso"])
        clave_nivel = (posicion["estante"], posicion["nivel"])
        uso_peso_nivel[clave_nivel] = uso_peso_nivel.get(clave_nivel, 0) + peso
        uso_piso[posicion["estante"]] = uso_piso.get(posicion["estante"], 0) + peso
        if limite is not None and float(producto["m_peso"]) > limite:
            if not (equipos & {"transpaleta", "apilador", "montacargas"} and posicion["base_m"] <= 0.3):
                duros.append(f"{nombre}: pesa {producto['m_peso']:.1f} kg y supera el límite ergonómico de {limite} kg")
        if parametros.get("valor_alto_controlado") and producto.get("valor_alto") == "si" and not posicion["zona_controlada"]:
            duros.append(f"{nombre}: alto valor fuera de zona controlada ({posicion['id_posicion']})")
        if producto.get("peligroso") == "si" and not posicion["permite_peligrosos"]:
            duros.append(f"{nombre}: peligroso en estante no habilitado ({posicion['id_posicion']})")
        temperatura = producto.get("temperatura_requerida") or "ambiente"
        if temperatura == "refrigerado" and posicion["tipo_estante"] != "refrigerador":
            duros.append(f"{nombre}: requiere frío y está en {posicion['tipo_estante']}")
        estantes_categoria.setdefault(str(producto["categoria"]).upper(), set()).add(posicion["estante"])
        # reglas blandas
        umbral = parametros.get("umbral_pesado_kg")
        if umbral is not None and float(producto["m_peso"]) >= umbral and posicion["base_m"] > 1.2:
            blandos.append(f"{nombre}: pesado ({producto['m_peso']:.1f} kg) a {posicion['base_m']:.2f} m de altura")
        altura_ninos = parametros.get("ninos_altura_max_m")
        if altura_ninos is not None and bool(producto.get("para_ninos")) and posicion["base_m"] > altura_ninos:
            blandos.append(f"{nombre}: producto infantil a {posicion['base_m']:.2f} m")
    for t, usado in uso_ancho.items():
        if usado > validas.at[t, "ancho_m"] * 100 + 0.5:
            duros.append(f"Posición {validas.at[t, 'id_posicion']}: ancho ocupado {usado:.0f} cm > {validas.at[t, 'ancho_m'] * 100:.0f} cm")
    capacidad = validas.groupby(["estante", "nivel"])["capacidad_kg_nivel"].first().to_dict()
    for clave, usado in uso_peso_nivel.items():
        if usado > capacidad[clave] + 1e-6:
            duros.append(f"Estante {clave[0]} nivel {clave[1]}: {usado:.1f} kg > {capacidad[clave]:.0f} kg")
    capacidad_piso = local.get("capacidad_piso_kg_m2")
    if capacidad_piso:
        for estante in local.get("estantes", []):
            h = huella_estante(estante)
            maximo = capacidad_piso * (h[2] - h[0]) * (h[3] - h[1])
            if uso_piso.get(estante["id"], 0) > maximo + 1e-6:
                duros.append(f"Estante {estante['id']}: {uso_piso[estante['id']]:.0f} kg superan la carga del piso ({maximo:.0f} kg)")
    if incompatibilidades:
        huellas = {e["id"]: huella_estante(e) for e in local.get("estantes", [])}
        for a, b, minima, motivo in incompatibilidades:
            for e1 in estantes_categoria.get(a, ()):
                for e2 in estantes_categoria.get(b, ()):
                    distancia = distancia_rects(huellas[e1], huellas[e2])
                    if distancia < minima:
                        duros.append(f"{a} en {e1} y {b} en {e2} a {distancia:.2f} m (mínimo {minima} m: {motivo})")
    # frágil debajo de pesado en el mismo tramo
    if parametros.get("fragil_no_debajo") and parametros.get("umbral_pesado_kg") is not None:
        por_columna = {}
        for i, j in asignacion.items():
            posicion = validas.loc[j]
            por_columna.setdefault((posicion["estante"], posicion["tramo"]), []).append((posicion["nivel"], i))
        for (estante, tramo), lista in por_columna.items():
            for nivel_f, i_f in lista:
                if productos.at[i_f, "fragil"] != "si":
                    continue
                if any(n > nivel_f and productos.at[k, "m_peso"] >= parametros["umbral_pesado_kg"] for n, k in lista):
                    blandos.append(f"{productos.at[i_f, 'producto'][:40]}: frágil debajo de un pesado en {estante}, tramo {tramo}")
    return {"duros": duros, "blandos": blandos}


# --------------------------------------------------------------------------------------
# Reubicación y evaluación económica
# --------------------------------------------------------------------------------------

def lista_reubicacion(antes, despues, productos, validas, modo="almacen", ajustes=None):
    """Movimientos ordenados por beneficio diario: lo que más rinde se mueve primero."""
    ajustes = ajustes or cargar_ajustes()
    minutos = ajustes["operacion"]["minutos_reubicar_producto"]
    filas = []
    for i, j in despues.items():
        anterior = antes.get(i)
        if anterior == j:
            continue
        producto = productos.loc[i]
        if modo == "tienda":
            ganancia = producto["margen_diario"] * (validas.at[j, "factor_exposicion"] -
                                                    (validas.at[anterior, "factor_exposicion"] if anterior is not None else 0))
        else:
            costo_antes = validas.at[anterior, "costo_acceso"] if anterior is not None else validas["costo_acceso"].max()
            ganancia = producto["m_rotacion"] * (costo_antes - validas.at[j, "costo_acceso"])
        filas.append({"producto": producto["producto"], "id_producto": producto["id_producto"], "clase_abc": producto["clase_abc"],
                      "desde": validas.at[anterior, "id_posicion"] if anterior is not None else "(sin ubicación)",
                      "hacia": validas.at[j, "id_posicion"], "beneficio_relativo_dia": round(float(ganancia), 4)})
    tabla = pd.DataFrame(filas, columns=["producto", "id_producto", "clase_abc", "desde", "hacia", "beneficio_relativo_dia"])
    if not len(tabla):
        return tabla
    tabla = tabla.sort_values("beneficio_relativo_dia", ascending=False).reset_index(drop=True)
    tabla.insert(0, "orden", range(1, len(tabla) + 1))
    tabla["minutos_acumulados"] = (tabla["orden"] * minutos).astype(int)
    total = tabla["beneficio_relativo_dia"].clip(lower=0).sum()
    tabla["beneficio_acumulado_pct"] = (100 * tabla["beneficio_relativo_dia"].clip(lower=0).cumsum() / total).round(1) if total else 0.0
    tabla["tanda"] = np.where(tabla["beneficio_acumulado_pct"] <= 80, "1: primero (80 % del beneficio)", "2: después")
    return tabla


def evaluacion_economica(kpi_antes, kpi_despues, movimientos, ajustes=None, tasa_anual=None, horizonte=None):
    """Costo de reubicar frente al ahorro mensual de picking: recuperación y VAN simple."""
    ajustes = ajustes or cargar_ajustes()
    operacion = ajustes["operacion"]
    tasa_anual = operacion["tasa_anual"] if tasa_anual is None else tasa_anual
    horizonte = operacion["horizonte_meses"] if horizonte is None else horizonte
    horas_reubicar = movimientos * operacion["minutos_reubicar_producto"] / 60
    costo = horas_reubicar * operacion["tarifa_hora_soles"]
    ahorro = kpi_antes["costo_picking_mes_soles"] - kpi_despues["costo_picking_mes_soles"]
    horas_ahorradas = kpi_antes["horas_picking_mes"] - kpi_despues["horas_picking_mes"]
    tasa_mensual = (1 + tasa_anual) ** (1 / 12) - 1
    van = -costo + sum(ahorro / (1 + tasa_mensual) ** t for t in range(1, horizonte + 1))
    return {"movimientos": int(movimientos), "horas_reubicacion": round(horas_reubicar, 1), "costo_reubicacion": round(costo, 2),
            "horas_ahorradas_mes": round(horas_ahorradas, 1), "ahorro_mensual": round(ahorro, 2),
            "recuperacion_meses": round(costo / ahorro, 1) if ahorro > 0 else None,
            "tasa_anual": tasa_anual, "horizonte_meses": horizonte, "van": round(van, 2)}


# --------------------------------------------------------------------------------------
# Escenarios y sensibilidad
# --------------------------------------------------------------------------------------

def kpi_con_costos_base(solucion, solucion_base, estadisticas, local, modo, parametros=None, incompatibilidades=None):
    """KPI de un escenario medido con los costos de acceso del escenario base (para comparar parejo)."""
    validas = solucion["validas"].copy()
    base = solucion_base["validas"].set_index("id_posicion")
    for columna in ("costo_acceso", "factor_exposicion", "distancia_m"):
        validas[columna] = validas["id_posicion"].map(base[columna]).fillna(validas[columna])
    return evaluar(solucion["asignacion"], solucion["productos"], validas, local, solucion["pares"], estadisticas, modo,
                   parametros=parametros, incompatibilidades=incompatibilidades)


def sensibilidad(ejecutar, solucion_base, estadisticas, local, modo, pesos_base, variacion=0.2, avance=None,
                 parametros=None, incompatibilidades=None):
    """Re-optimiza variando ±20 % cada peso del objetivo (uno a la vez).
    `ejecutar(pesos)` debe devolver una solución de modelo_optimo.optimizar."""
    claves = ["peso_distancia", "peso_ergonomia", "peso_reglas_blandas"]
    filas = []
    base_ids = {solucion_base["productos"].at[i, "id_producto"]: solucion_base["validas"].at[j, "id_posicion"]
                for i, j in solucion_base["asignacion"].items()}
    total = len(claves) * 2
    paso = 0
    for clave in claves:
        for signo in (-1, 1):
            pesos = dict(pesos_base)
            pesos[clave] = round(pesos_base[clave] * (1 + signo * variacion), 4)
            if avance:
                avance(paso / total, f"{clave} {'-' if signo < 0 else '+'}{int(variacion * 100)} %…")
            solucion = ejecutar(pesos)
            kpi = kpi_con_costos_base(solucion, solucion_base, estadisticas, local, modo, parametros, incompatibilidades)
            ids = {solucion["productos"].at[i, "id_producto"]: solucion["validas"].at[j, "id_posicion"]
                   for i, j in solucion["asignacion"].items()}
            cambian = sum(1 for k, v in ids.items() if base_ids.get(k) != v)
            filas.append({"Peso variado": clave, "Variación": f"{'-' if signo < 0 else '+'}{int(variacion * 100)} %",
                          "Valor usado": pesos[clave], "Productos ubicados": kpi["productos_ubicados"],
                          "Distancia ponderada (m/día)": kpi["distancia_ponderada_m_dia"],
                          "Costo de acceso (pesos base)": kpi["costo_acceso_ponderado"],
                          "Productos que cambian de lugar": cambian,
                          "% que cambia": round(100 * cambian / max(len(base_ids), 1), 1)})
            paso += 1
    if avance:
        avance(1.0, "Listo.")
    return pd.DataFrame(filas)
