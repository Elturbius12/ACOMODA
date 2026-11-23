"""Entiende el local: calcula la huella de cada estante, revisa choques y pasillos,
genera las posiciones (tramos de cada nivel) y mide distancias caminando por los
pasillos con una grilla (no en línea recta)."""

import heapq
import math

import numpy as np
import pandas as pd

from modulos.comun import a_numero, cargar_ajustes

# Obstáculos que impiden caminar o colocar un estante encima
OBSTACULOS_SOLIDOS = {"columna", "muro", "escalera", "tablero", "extintor"}


# --------------------------------------------------------------------------------------
# Rectángulos
# --------------------------------------------------------------------------------------

def rect(x, y, largo, ancho):
    return (float(x), float(y), float(x) + float(largo), float(y) + float(ancho))


def se_cruzan(a, b, tolerancia=0.005):
    """True si dos rectángulos (x0, y0, x1, y1) se superponen (tocarse no cuenta)."""
    return (a[0] < b[2] - tolerancia and b[0] < a[2] - tolerancia and
            a[1] < b[3] - tolerancia and b[1] < a[3] - tolerancia)


def distancia_rects(a, b):
    """Distancia mínima entre dos rectángulos (0 si se tocan o cruzan)."""
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def ampliar(r, margen):
    return (r[0] - margen, r[1] - margen, r[2] + margen, r[3] + margen)


def dentro_de(r, contenedor, tolerancia=0.01):
    return (r[0] >= contenedor[0] - tolerancia and r[1] >= contenedor[1] - tolerancia and
            r[2] <= contenedor[2] + tolerancia and r[3] <= contenedor[3] + tolerancia)


def contorno(local):
    return (0.0, 0.0, float(local.get("largo_m") or 0), float(local.get("ancho_m") or 0))


def huella_estante(estante):
    """Rectángulo que ocupa el estante en el piso, según su orientación."""
    largo, fondo = float(estante["largo_m"]), float(estante["fondo_m"])
    if int(estante.get("orientacion") or 0) in (90, 270):
        return rect(estante["x_m"], estante["y_m"], fondo, largo)
    return rect(estante["x_m"], estante["y_m"], largo, fondo)


def huella_obstaculo(obstaculo):
    return rect(obstaculo["x_m"], obstaculo["y_m"], obstaculo["largo_m"], obstaculo["ancho_m"])


def frente_estante(estante):
    """Devuelve (inicio_x, inicio_y, dirección a lo largo (dx, dy), normal hacia afuera (nx, ny))."""
    x0, y0, x1, y1 = huella_estante(estante)
    orientacion = int(estante.get("orientacion") or 0)
    if orientacion == 0:      # frente en el borde inferior, mira hacia Y menor
        return x0, y0, (1, 0), (0, -1)
    if orientacion == 180:    # frente en el borde superior, mira hacia Y mayor
        return x0, y1, (1, 0), (0, 1)
    if orientacion == 90:     # frente en el borde derecho, mira hacia X mayor
        return x1, y0, (0, 1), (1, 0)
    return x0, y0, (0, 1), (-1, 0)  # 270: frente en el borde izquierdo


def rect_frente(estante, desde, hasta, profundidad):
    """Rectángulo del pasillo frente al tramo [desde, hasta] (metros a lo largo del frente)."""
    fx, fy, (dx, dy), (nx, ny) = frente_estante(estante)
    ax, ay = fx + dx * desde, fy + dy * desde
    bx, by = fx + dx * hasta, fy + dy * hasta
    cx, cy = ax + nx * profundidad, ay + ny * profundidad
    ex, ey = bx + nx * profundidad, by + ny * profundidad
    xs, ys = [ax, bx, cx, ex], [ay, by, cy, ey]
    return (min(xs), min(ys), max(xs), max(ys))


def rect_tramo(estante, desde, hasta):
    """Huella en el piso de un tramo del estante."""
    fx, fy, (dx, dy), (nx, ny) = frente_estante(estante)
    fondo = float(estante["fondo_m"])
    ax, ay = fx + dx * desde, fy + dy * desde
    bx, by = fx + dx * hasta, fy + dy * hasta
    cx, cy = ax - nx * fondo, ay - ny * fondo
    ex, ey = bx - nx * fondo, by - ny * fondo
    xs, ys = [ax, bx, cx, ex], [ay, by, cy, ey]
    return (min(xs), min(ys), max(xs), max(ys))


def niveles_estante(estante, ajustes=None):
    """Lista de (altura_base_m, altura_libre_m) de cada nivel, de abajo hacia arriba."""
    ajustes = ajustes or cargar_ajustes()
    geometria = ajustes["geometria"]
    primer = geometria["altura_primer_nivel_m"]
    grosor = geometria["grosor_bandeja_m"]
    niveles = int(estante.get("niveles") or 1)
    texto = str(estante.get("alturas_niveles_m") or "").strip()
    alturas = [a_numero(p) for p in texto.replace(",", ".").split(";") if p.strip()] if texto else []
    alturas = [a for a in alturas if a and a > 0]
    if len(alturas) != niveles:
        util = float(estante["alto_m"]) - primer
        alturas = [max(0.05, util / niveles - grosor)] * niveles
    resultado = []
    base = primer
    for altura in alturas:
        resultado.append((round(base, 3), round(altura, 3)))
        base += altura + grosor
    return resultado


# --------------------------------------------------------------------------------------
# Parámetros normativos que afectan la geometría
# --------------------------------------------------------------------------------------

def parametros_geometria_por_defecto(local=None, modo="almacen"):
    """Valores iniciales de normas (antes de confirmar el Paso 4)."""
    from modulos.normas import estado_inicial, parametros_activos
    return parametros_activos(estado_inicial(None), modo, local)


def ancho_pasillo_requerido(local, parametros):
    anchos = [parametros.get("ancho_pasillo_min_m") or 0]
    for pasillo in local.get("pasillos", []):
        if pasillo.get("uso") != "evacuacion" and pasillo.get("ancho_min_m"):
            anchos.append(float(pasillo["ancho_min_m"]))
    if parametros.get("ancho_pasillo_accesible_m"):
        anchos.append(parametros["ancho_pasillo_accesible_m"])
    return max(anchos) if anchos else 0.9


def altura_maxima_mercaderia(local, parametros):
    """Altura máxima a la que puede llegar la mercadería (techo libre y rociadores)."""
    maximo = float(local.get("altura_libre_m") or 99)
    rociadores = [o for o in local.get("obstaculos", []) if o.get("tipo") == "rociador"]
    despeje = parametros.get("despeje_rociador_m")
    if rociadores and despeje:
        altura_rociador = min(float(o.get("alto_m") or maximo) for o in rociadores)
        maximo = min(maximo, altura_rociador - despeje)
    return maximo


# --------------------------------------------------------------------------------------
# Validaciones geométricas
# --------------------------------------------------------------------------------------

def _aviso(gravedad, tabla, id_, mensaje):
    return {"gravedad": gravedad, "tabla": tabla, "id": id_, "mensaje": mensaje}


def validar_local(local, parametros=None):
    """Revisa el local y devuelve una lista de avisos {gravedad: 'grave'|'advertencia', tabla, id, mensaje}."""
    parametros = parametros or parametros_geometria_por_defecto(local)
    avisos = []
    largo, ancho, altura = local.get("largo_m"), local.get("ancho_m"), local.get("altura_libre_m")
    if not largo or not ancho or largo <= 0 or ancho <= 0:
        avisos.append(_aviso("grave", "LOCAL", "local", "Faltan el largo o el ancho del local."))
        return avisos
    if not altura or altura <= 0:
        avisos.append(_aviso("grave", "LOCAL", "local", "Falta la altura libre útil del local."))
        altura = 99
    if largo > 200 or ancho > 200:
        avisos.append(_aviso("grave", "LOCAL", "local",
                             f"El local mide {largo} × {ancho}: parece que las medidas están en centímetros y no en metros."))
    if altura and altura > 20:
        avisos.append(_aviso("grave", "LOCAL", "local", f"Altura libre de {altura} metros: ¿está en centímetros?"))
    caja_local = contorno(local)

    # Identificadores repetidos
    for clave, tabla in (("estantes", "ESTANTES"), ("obstaculos", "OBSTACULOS"), ("zonas", "ZONAS")):
        vistos = set()
        for elemento in local.get(clave, []):
            if elemento["id"] in vistos:
                avisos.append(_aviso("grave", tabla, elemento["id"], f"El identificador {elemento['id']} está repetido."))
            vistos.add(elemento["id"])

    for obstaculo in local.get("obstaculos", []):
        if not dentro_de(huella_obstaculo(obstaculo), caja_local):
            avisos.append(_aviso("advertencia", "OBSTACULOS", obstaculo["id"],
                                 f"{obstaculo['tipo']} {obstaculo['id']} está fuera del contorno del local."))

    if not any(o.get("tipo") == "salida_emergencia" for o in local.get("obstaculos", [])):
        avisos.append(_aviso("advertencia", "OBSTACULOS", "-", "No se registró ninguna salida de emergencia."))
    if not any(z.get("tipo") in ("despacho", "caja") for z in local.get("zonas", [])):
        avisos.append(_aviso("advertencia", "ZONAS", "-",
                             "No hay zona de despacho ni de caja: las distancias se medirán desde la primera puerta."))

    estantes = local.get("estantes", [])
    huellas = {e["id"]: huella_estante(e) for e in estantes}
    requerido = ancho_pasillo_requerido(local, parametros)
    altura_max = altura_maxima_mercaderia(local, parametros)
    for estante in estantes:
        identificador = estante["id"]
        huella = huellas[identificador]
        if float(estante["largo_m"]) > 30 or float(estante["alto_m"]) > 15:
            avisos.append(_aviso("grave", "ESTANTES", identificador,
                                 f"Estante {identificador}: {estante['largo_m']} metros de largo y {estante['alto_m']} metros de alto; ¿están en centímetros?"))
        if not dentro_de(huella, caja_local):
            avisos.append(_aviso("grave", "ESTANTES", identificador, f"Estante {identificador} queda fuera del contorno del local."))
        for obstaculo in local.get("obstaculos", []):
            caja = huella_obstaculo(obstaculo)
            tipo = obstaculo["tipo"]
            if tipo in ("columna", "muro", "escalera") and se_cruzan(huella, caja):
                avisos.append(_aviso("grave", "ESTANTES", identificador,
                                     f"Estante {identificador} choca con {tipo} {obstaculo['id']}."))
            elif tipo == "salida_emergencia" and parametros.get("despeje_salida_m") is not None and \
                    se_cruzan(huella, ampliar(caja, parametros["despeje_salida_m"])):
                avisos.append(_aviso("grave", "ESTANTES", identificador,
                                     f"Estante {identificador} bloquea la salida de emergencia {obstaculo['id']} "
                                     f"(debe quedar a {parametros['despeje_salida_m']} metros o más de distancia)."))
            elif tipo == "extintor" and parametros.get("despeje_extintor_m") is not None and \
                    se_cruzan(huella, ampliar(caja, parametros["despeje_extintor_m"])):
                avisos.append(_aviso("advertencia", "ESTANTES", identificador,
                                     f"Estante {identificador} bloquea el extintor {obstaculo['id']}: se eliminan los tramos cercanos."))
            elif tipo == "tablero" and parametros.get("despeje_tablero_m") is not None and \
                    se_cruzan(huella, ampliar(caja, parametros["despeje_tablero_m"])):
                avisos.append(_aviso("advertencia", "ESTANTES", identificador,
                                     f"Estante {identificador} bloquea el tablero eléctrico {obstaculo['id']}: se eliminan los tramos cercanos."))
            elif tipo == "puerta" and se_cruzan(huella, ampliar(caja, cargar_ajustes()["geometria"]["despeje_puerta_m"])):
                avisos.append(_aviso("advertencia", "ESTANTES", identificador,
                                     f"Estante {identificador} está frente a la puerta {obstaculo['id']}: se eliminan los tramos cercanos."))
        for otro in estantes:
            if otro["id"] > identificador and se_cruzan(huella, huellas[otro["id"]]):
                avisos.append(_aviso("grave", "ESTANTES", identificador,
                                     f"Estante {identificador} choca con el estante {otro['id']}."))
        libre = espacio_libre_frente(local, estante, huellas, requerido)
        if libre + 1e-6 < requerido:
            avisos.append(_aviso("advertencia", "ESTANTES", identificador,
                                 f"Pasillo frente a {identificador} de solo {libre:.2f} metros (mínimo {requerido:.2f} metros): "
                                 "se eliminan los tramos afectados."))
        if float(estante["alto_m"]) > float(local.get("altura_libre_m") or 99):
            avisos.append(_aviso("advertencia", "ESTANTES", identificador,
                                 f"Estante {identificador} ({estante['alto_m']} metros) es más alto que la altura libre del local."))
        niveles = niveles_estante(estante)
        if niveles and niveles[-1][0] + niveles[-1][1] > altura_max + 1e-6:
            avisos.append(_aviso("advertencia", "ESTANTES", identificador,
                                 f"El nivel más alto de {identificador} supera la altura máxima permitida "
                                 f"({altura_max:.2f} metros por techo o rociadores): ese nivel no se usará."))
        if estante.get("estimado"):
            avisos.append(_aviso("advertencia", "ESTANTES", identificador,
                                 f"Estante {identificador}: niveles, alto o capacidad son supuestos. Confírmelos."))
    return avisos


def espacio_libre_frente(local, estante, huellas=None, maximo=3.0, paso=0.05):
    """Metros libres frente a TODO el estante (lo más angosto a lo largo del frente)."""
    huellas = huellas or {e["id"]: huella_estante(e) for e in local.get("estantes", [])}
    bloqueos = [h for i, h in huellas.items() if i != estante["id"]]
    bloqueos += [huella_obstaculo(o) for o in local.get("obstaculos", []) if o["tipo"] in OBSTACULOS_SOLIDOS]
    caja_local = contorno(local)
    largo = float(estante["largo_m"])
    profundidad = 0.0
    while profundidad < maximo:
        siguiente = profundidad + paso
        zona = rect_frente(estante, 0.02, largo - 0.02, siguiente)
        if not dentro_de(zona, caja_local) or any(se_cruzan(zona, b) for b in bloqueos):
            return profundidad
        profundidad = siguiente
    return maximo


def hay_errores_graves(avisos):
    return any(a["gravedad"] == "grave" for a in avisos)


# --------------------------------------------------------------------------------------
# Posiciones (tramo de un nivel de un estante)
# --------------------------------------------------------------------------------------

def generar_posiciones(local, parametros=None, ajustes=None):
    """Devuelve un DataFrame con todas las posiciones y si son válidas o no (con motivo).
    Las posiciones que invaden pasillos, salidas, extintores o tableros quedan como no válidas."""
    ajustes = ajustes or cargar_ajustes()
    parametros = parametros or parametros_geometria_por_defecto(local)
    ancho_tramo = ajustes["geometria"]["ancho_tramo_m"]
    requerido = ancho_pasillo_requerido(local, parametros)
    altura_max = altura_maxima_mercaderia(local, parametros)
    altura_min_piso = parametros.get("altura_minima_piso_m") or 0.0
    caja_local = contorno(local)
    huellas = {e["id"]: huella_estante(e) for e in local.get("estantes", [])}
    solidos = [huella_obstaculo(o) for o in local.get("obstaculos", []) if o["tipo"] in OBSTACULOS_SOLIDOS]
    despejes = []
    for obstaculo in local.get("obstaculos", []):
        margen = {"salida_emergencia": parametros.get("despeje_salida_m"),
                  "extintor": parametros.get("despeje_extintor_m"),
                  "tablero": parametros.get("despeje_tablero_m"),
                  "puerta": ajustes["geometria"]["despeje_puerta_m"]}.get(obstaculo["tipo"])
        if margen is not None:
            despejes.append((obstaculo, ampliar(huella_obstaculo(obstaculo), margen)))
    zonas_controladas = [rect(z["x_m"], z["y_m"], z["largo_m"], z["ancho_m"])
                         for z in local.get("zonas", []) if z.get("tipo") in ("controlada", "caja")]

    filas = []
    for estante in local.get("estantes", []):
        largo = float(estante["largo_m"])
        tramos = max(1, int(round(largo / ancho_tramo)))
        ancho = largo / tramos
        otros = [h for i, h in huellas.items() if i != estante["id"]]
        controlado = estante.get("zona_controlada") == "si" or any(
            se_cruzan(huellas[estante["id"]], z) for z in zonas_controladas)
        capacidad_nivel = float(estante.get("capacidad_kg_nivel") or 0)
        for numero_nivel, (base, alto_libre) in enumerate(niveles_estante(estante, ajustes), start=1):
            for numero_tramo in range(1, tramos + 1):
                desde, hasta = (numero_tramo - 1) * ancho, numero_tramo * ancho
                huella_tramo = rect_tramo(estante, desde, hasta)
                motivos = []
                if not dentro_de(huella_tramo, caja_local):
                    motivos.append("fuera del local")
                if any(se_cruzan(huella_tramo, s) for s in solidos):
                    motivos.append("choca con un obstáculo")
                if any(se_cruzan(huella_tramo, o) for o in otros):
                    motivos.append("choca con otro estante")
                for obstaculo, zona in despejes:
                    if se_cruzan(huella_tramo, zona):
                        motivos.append(f"invade el despeje de {obstaculo['tipo']} {obstaculo['id']}")
                pasillo = rect_frente(estante, desde + 0.02, hasta - 0.02, requerido)
                if not dentro_de(pasillo, caja_local) or any(se_cruzan(pasillo, b) for b in otros + solidos):
                    motivos.append(f"pasillo menor a {requerido:.2f} m")
                if base + alto_libre > altura_max + 1e-6:
                    motivos.append(f"supera la altura máxima de {altura_max:.2f} m")
                if base < altura_min_piso - 1e-6:
                    motivos.append(f"está a menos de {altura_min_piso:.2f} m del piso")
                if capacidad_nivel <= 0:
                    motivos.append("el nivel no tiene capacidad de peso registrada")
                fx, fy, (dx, dy), (nx, ny) = frente_estante(estante)
                medio = (desde + hasta) / 2
                filas.append({
                    "id_posicion": f"{estante['id']}-N{numero_nivel}-T{numero_tramo}",
                    "estante": estante["id"], "tipo_estante": estante.get("tipo", ""),
                    "nivel": numero_nivel, "tramo": numero_tramo, "tramos_estante": tramos,
                    "niveles_estante": int(estante.get("niveles") or 1),
                    "ancho_m": round(ancho, 4), "fondo_m": float(estante["fondo_m"]),
                    "alto_libre_m": alto_libre, "base_m": base, "altura_centro_m": round(base + alto_libre / 2, 3),
                    "capacidad_kg_nivel": capacidad_nivel,
                    "x0": huella_tramo[0], "y0": huella_tramo[1], "x1": huella_tramo[2], "y1": huella_tramo[3],
                    "x_acceso": round(fx + dx * medio + nx * 0.45, 3),
                    "y_acceso": round(fy + dy * medio + ny * 0.45, 3),
                    "zona_controlada": controlado, "permite_peligrosos": estante.get("permite_peligrosos") == "si",
                    "cabecera": numero_tramo in (1, tramos),
                    "valida": not motivos, "motivo_eliminacion": "; ".join(motivos),
                })
    return pd.DataFrame(filas)


# --------------------------------------------------------------------------------------
# Grilla de pasillos y distancias caminando
# --------------------------------------------------------------------------------------

class Grilla:
    """Grilla de celdas libres u ocupadas para medir recorridos a pie."""

    def __init__(self, local, resolucion=None):
        ajustes = cargar_ajustes()
        self.resolucion = resolucion or ajustes["geometria"]["resolucion_grilla_m"]
        self.columnas = max(1, int(math.ceil(float(local["largo_m"]) / self.resolucion)))
        self.filas = max(1, int(math.ceil(float(local["ancho_m"]) / self.resolucion)))
        self.ocupada = np.zeros((self.filas, self.columnas), dtype=bool)
        bloqueos = [huella_estante(e) for e in local.get("estantes", [])]
        bloqueos += [huella_obstaculo(o) for o in local.get("obstaculos", []) if o["tipo"] in OBSTACULOS_SOLIDOS]
        for x0, y0, x1, y1 in bloqueos:
            c0, c1 = int(math.floor(x0 / self.resolucion + 0.05)), int(math.ceil(x1 / self.resolucion - 0.05))
            f0, f1 = int(math.floor(y0 / self.resolucion + 0.05)), int(math.ceil(y1 / self.resolucion - 0.05))
            self.ocupada[max(f0, 0):max(f1, 0), max(c0, 0):max(c1, 0)] = True

    def celda(self, x, y):
        columna = min(max(int(x / self.resolucion), 0), self.columnas - 1)
        fila = min(max(int(y / self.resolucion), 0), self.filas - 1)
        return fila, columna

    def centro(self, fila, columna):
        return ((columna + 0.5) * self.resolucion, (fila + 0.5) * self.resolucion)

    def celda_libre_cercana(self, x, y):
        """La celda libre más cercana al punto (busca en anillos)."""
        fila, columna = self.celda(x, y)
        if not self.ocupada[fila, columna]:
            return fila, columna
        for radio in range(1, max(self.filas, self.columnas)):
            mejor = None
            for df in range(-radio, radio + 1):
                for dc in (-radio, radio) if abs(df) != radio else range(-radio, radio + 1):
                    f, c = fila + df, columna + dc
                    if 0 <= f < self.filas and 0 <= c < self.columnas and not self.ocupada[f, c]:
                        distancia = df * df + dc * dc
                        if mejor is None or distancia < mejor[0]:
                            mejor = (distancia, f, c)
            if mejor:
                return mejor[1], mejor[2]
        return fila, columna

    def dijkstra(self, x, y, bloqueada=None):
        """Distancia caminando (m) desde el punto a todas las celdas. inf = no se llega."""
        ocupada = self.ocupada if bloqueada is None else bloqueada
        distancia = np.full(ocupada.shape, np.inf)
        padre = {}
        inicio = self.celda_libre_cercana(x, y)
        distancia[inicio] = 0.0
        cola = [(0.0, inicio)]
        pasos = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
                 (-1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)), (1, -1, math.sqrt(2)), (1, 1, math.sqrt(2))]
        while cola:
            actual, (f, c) = heapq.heappop(cola)
            if actual > distancia[f, c]:
                continue
            for df, dc, costo in pasos:
                nf, nc = f + df, c + dc
                if not (0 <= nf < self.filas and 0 <= nc < self.columnas) or ocupada[nf, nc]:
                    continue
                if df and dc and (ocupada[f + df, c] or ocupada[f, c + dc]):
                    continue  # no cortar esquinas
                nuevo = actual + costo * self.resolucion
                if nuevo < distancia[nf, nc]:
                    distancia[nf, nc] = nuevo
                    padre[(nf, nc)] = (f, c)
                    heapq.heappush(cola, (nuevo, (nf, nc)))
        return distancia, padre

    def camino(self, origen, destino):
        """Lista de puntos (x, y) del recorrido más corto entre dos puntos."""
        _, padre = self.dijkstra(*origen)
        fin = self.celda_libre_cercana(*destino)
        puntos = [self.centro(*fin)]
        actual = fin
        while actual in padre:
            actual = padre[actual]
            puntos.append(self.centro(*actual))
        return list(reversed(puntos))


def punto_origen(local, modo="almacen"):
    """Punto desde donde se mide el recorrido: despacho (almacén) o caja (tienda)."""
    preferidas = ["despacho", "caja"] if modo == "almacen" else ["caja", "despacho"]
    for tipo in preferidas:
        for zona in local.get("zonas", []):
            if zona.get("tipo") == tipo:
                return (zona["x_m"] + zona["largo_m"] / 2, zona["y_m"] + zona["ancho_m"] / 2), f"zona {tipo} {zona['id']}"
    for obstaculo in local.get("obstaculos", []):
        if obstaculo.get("tipo") == "puerta":
            return (obstaculo["x_m"] + obstaculo["largo_m"] / 2, obstaculo["y_m"] + obstaculo["ancho_m"] / 2), f"puerta {obstaculo['id']}"
    return (0.5, 0.5), "origen (0,0)"


def medir_distancias(posiciones, local, modo="almacen"):
    """Agrega 'distancia_m' (caminando) desde el origen a cada posición. También 'distancia_ingreso_m'."""
    grilla = Grilla(local)
    origen, _ = punto_origen(local, modo)
    distancias, _ = grilla.dijkstra(*origen)
    ingreso = next(((z["x_m"] + z["largo_m"] / 2, z["y_m"] + z["ancho_m"] / 2)
                    for z in local.get("zonas", []) if z.get("tipo") == "ingreso"), origen)
    distancias_ingreso, _ = grilla.dijkstra(*ingreso)
    valores, valores_ingreso = [], []
    for fila in posiciones.itertuples():
        celda = grilla.celda_libre_cercana(fila.x_acceso, fila.y_acceso)
        valor = distancias[celda]
        directa = math.hypot(fila.x_acceso - origen[0], fila.y_acceso - origen[1])
        valores.append(float(valor) if np.isfinite(valor) else directa * 3)
        valor_ingreso = distancias_ingreso[celda]
        valores_ingreso.append(float(valor_ingreso) if np.isfinite(valor_ingreso) else directa * 3)
    posiciones = posiciones.copy()
    posiciones["distancia_m"] = np.round(valores, 2)
    posiciones["distancia_ingreso_m"] = np.round(valores_ingreso, 2)
    return posiciones


def rutas_evacuacion(local, ancho_minimo):
    """Revisa que desde el frente de cada estante haya una ruta de al menos `ancho_minimo`
    hasta una salida de emergencia o puerta. Devuelve la lista de estantes sin ruta."""
    salidas = [o for o in local.get("obstaculos", []) if o["tipo"] in ("salida_emergencia", "puerta")]
    if not salidas or not local.get("estantes"):
        return []
    grilla = Grilla(local)
    # Erosión: una celda solo sirve si hay espacio libre a su alrededor del ancho pedido
    radio = max(0, int(math.ceil((ancho_minimo / 2) / grilla.resolucion)) - 1)
    ocupada = grilla.ocupada.copy()
    if radio > 0:
        ampliada = ocupada.copy()
        for df in range(-radio, radio + 1):
            for dc in range(-radio, radio + 1):
                desplazada = np.zeros_like(ocupada)
                f0, f1 = max(df, 0), ocupada.shape[0] + min(df, 0)
                c0, c1 = max(dc, 0), ocupada.shape[1] + min(dc, 0)
                desplazada[f0:f1, c0:c1] = ocupada[f0 - df:f1 - df, c0 - dc:c1 - dc]
                ampliada |= desplazada
        ocupada = ampliada
    alcanzable = np.zeros_like(ocupada)
    for salida in salidas:
        centro = (salida["x_m"] + salida["largo_m"] / 2, salida["y_m"] + salida["ancho_m"] / 2)
        fila, columna = grilla.celda(*centro)
        libre = ocupada.copy()
        libre[max(fila - 4, 0):fila + 5, max(columna - 4, 0):columna + 5] = False  # la puerta misma es transitable
        distancia, _ = grilla.dijkstra(*centro, bloqueada=libre)
        alcanzable |= np.isfinite(distancia)
    sin_ruta = []
    for estante in local["estantes"]:
        fx, fy, (dx, dy), (nx, ny) = frente_estante(estante)
        medio = float(estante["largo_m"]) / 2
        x, y = fx + dx * medio + nx * (ancho_minimo / 2 + 0.1), fy + dy * medio + ny * (ancho_minimo / 2 + 0.1)
        fila, columna = grilla.celda(x, y)
        vecindad = alcanzable[max(fila - 2, 0):fila + 3, max(columna - 2, 0):columna + 3]
        if not vecindad.any():
            sin_ruta.append(estante["id"])
    return sin_ruta


def resumen_local(local, posiciones=None):
    """Tabla resumen de lo que se entendió del local."""
    estantes = local.get("estantes", [])
    obstaculos = local.get("obstaculos", [])
    area_total = float(local.get("largo_m") or 0) * float(local.get("ancho_m") or 0)
    area_estantes = sum((huella_estante(e)[2] - huella_estante(e)[0]) * (huella_estante(e)[3] - huella_estante(e)[1])
                        for e in estantes)
    area_obstaculos = sum(o["largo_m"] * o["ancho_m"] for o in obstaculos if o["tipo"] in OBSTACULOS_SOLIDOS)
    filas = [
        ("Nombre", local.get("nombre") or "(sin nombre)"),
        ("Fuente de los datos", local.get("fuente")),
        ("Largo × ancho", f"{local.get('largo_m')} m × {local.get('ancho_m')} m"),
        ("Área total", f"{area_total:,.1f} m²"),
        ("Área útil (sin obstáculos sólidos)", f"{area_total - area_obstaculos:,.1f} m²"),
        ("Área ocupada por estantes", f"{area_estantes:,.1f} m² ({(area_estantes / area_total * 100) if area_total else 0:.0f} %)"),
        ("Altura libre útil", f"{local.get('altura_libre_m')} m"),
        ("Estantes", f"{len(estantes)} módulos, {sum(int(e.get('niveles') or 0) for e in estantes)} niveles en total"),
    ]
    conteo = {}
    for obstaculo in obstaculos:
        conteo[obstaculo["tipo"]] = conteo.get(obstaculo["tipo"], 0) + 1
    for tipo, cantidad in sorted(conteo.items()):
        filas.append((f"Obstáculos: {tipo}", cantidad))
    for zona in local.get("zonas", []):
        filas.append((f"Zona {zona['tipo']}", f"{zona['id']} en ({zona['x_m']}, {zona['y_m']}), {zona['largo_m']} × {zona['ancho_m']} m"))
    for pasillo in local.get("pasillos", []):
        filas.append((f"Pasillo {pasillo['uso']}", f"mínimo {pasillo['ancho_min_m']} m"))
    for equipo in local.get("equipos", []):
        filas.append((f"Equipo {equipo['tipo']}", f"altura máxima {equipo.get('altura_max_m') or '-'} m"))
    if posiciones is not None and len(posiciones):
        validas = int(posiciones["valida"].sum())
        filas.append(("Posiciones (tramos de nivel)", f"{len(posiciones)} en total, {validas} utilizables, {len(posiciones) - validas} eliminadas"))
        volumen = (posiciones[posiciones["valida"]].eval("ancho_m * fondo_m * alto_libre_m")).sum()
        filas.append(("Volumen útil de estantería", f"{volumen:,.2f} m³"))
    return pd.DataFrame(filas, columns=["Concepto", "Valor"]).astype(str)


# --------------------------------------------------------------------------------------
# Compuerta de confirmación y estante adicional
# --------------------------------------------------------------------------------------

PREGUNTAS_CONFIRMACION_LOCAL = [
    "¿Las dimensiones del local son correctas?",
    "¿La ubicación de puertas y salidas es correcta?",
    "¿Los estantes existentes que declaré son correctos? (o no declaré ninguno)",
    "¿Aceptas las advertencias restantes?",
]


def puede_confirmar_local(casillas, avisos, responsable):
    """El botón 'Confirmo que el local está bien interpretado' solo se activa si todas las
    casillas están marcadas, no hay errores graves y hay un responsable. Devuelve (bool, motivo)."""
    if hay_errores_graves(avisos):
        return False, "Quedan errores graves: corríjalos antes de confirmar."
    if len(casillas) < len(PREGUNTAS_CONFIRMACION_LOCAL) or not all(casillas):
        return False, "Marque todas las casillas de confirmación."
    if not str(responsable or "").strip():
        return False, "Escriba el nombre del responsable en la barra lateral."
    return True, ""


def agregar_estante_libre(local, parametros=None, modelo_id=None, paso=0.2, modelo=None, nuevo_id=None):
    """Copia un estante existente y lo coloca en el lugar libre más cercano al despacho
    (sin chocar, sin invadir despejes y con pasillo suficiente). Devuelve (local_nuevo, estante) o (local, None)."""
    import copy
    parametros = parametros or parametros_geometria_por_defecto(local)
    if not local.get("estantes") and modelo is None:
        return local, None
    modelo = modelo or next((e for e in local["estantes"] if e["id"] == modelo_id), None) or max(
        local["estantes"], key=lambda e: float(e["largo_m"]) * int(e.get("niveles") or 1))
    requerido = ancho_pasillo_requerido(local, parametros)
    caja_local = contorno(local)
    bloqueos = [ampliar(huella_estante(e), 0.02) for e in local["estantes"]]
    bloqueos += [huella_obstaculo(o) for o in local.get("obstaculos", []) if o["tipo"] in OBSTACULOS_SOLIDOS]
    margenes = {"salida_emergencia": parametros.get("despeje_salida_m") or 0, "extintor": parametros.get("despeje_extintor_m") or 0,
                "tablero": parametros.get("despeje_tablero_m") or 0, "puerta": cargar_ajustes()["geometria"]["despeje_puerta_m"]}
    despejes = [ampliar(huella_obstaculo(o), margenes[o["tipo"]]) for o in local.get("obstaculos", []) if o["tipo"] in margenes]
    zonas = [rect(z["x_m"], z["y_m"], z["largo_m"], z["ancho_m"]) for z in local.get("zonas", [])]
    origen, _ = punto_origen(local)
    mejor = None
    numero = 1
    while any(e["id"] == f"N{numero}" for e in local["estantes"]):
        numero += 1
    identificador = nuevo_id or f"N{numero}"
    for orientacion in (0, 180, 90, 270):
        prueba = dict(modelo, orientacion=orientacion, id=identificador)
        ancho_x, ancho_y = (float(modelo["fondo_m"]), float(modelo["largo_m"])) if orientacion in (90, 270) else \
            (float(modelo["largo_m"]), float(modelo["fondo_m"]))
        y = 0.0
        while y + ancho_y <= caja_local[3]:
            x = 0.0
            while x + ancho_x <= caja_local[2]:
                prueba["x_m"], prueba["y_m"] = round(x, 2), round(y, 2)
                huella = huella_estante(prueba)
                pasillo = rect_frente(prueba, 0.02, float(prueba["largo_m"]) - 0.02, requerido)
                libre = (not any(se_cruzan(huella, b) for b in bloqueos + despejes + zonas) and dentro_de(pasillo, caja_local)
                         and not any(se_cruzan(pasillo, b) for b in bloqueos))
                if libre:
                    # tampoco debe tapar el pasillo de los estantes existentes
                    tapa = any(se_cruzan(huella, rect_frente(e, 0.02, float(e["largo_m"]) - 0.02, requerido))
                               for e in local["estantes"])
                    if not tapa:
                        distancia = math.hypot(huella[0] - origen[0], huella[1] - origen[1])
                        if mejor is None or distancia < mejor[0]:
                            mejor = (distancia, dict(prueba))
                x += paso
            y += paso
    if mejor is None:
        return local, None
    nuevo = copy.deepcopy(local)
    estante = mejor[1]
    estante["estimado"] = False
    nuevo["estantes"].append(estante)
    return nuevo, estante


# --------------------------------------------------------------------------------------
# Soluciones propuestas para cada aviso (botón «Corregir»)
# --------------------------------------------------------------------------------------

def proponer_solucion(local, aviso, parametros=None):
    """Devuelve una lista de propuestas [{"texto": ..., "local": local_corregido}] para resolver el aviso.
    La primera es la recomendada. Lista vacía si no hay arreglo automático."""
    import copy
    parametros = parametros or parametros_geometria_por_defecto(local)
    propuestas = []
    mensaje = aviso["mensaje"]
    tabla, identificador = aviso["tabla"], aviso["id"]

    def con(cambio, texto):
        nuevo = copy.deepcopy(local)
        cambio(nuevo)
        propuestas.append({"texto": texto, "local": nuevo})

    if tabla == "LOCAL":
        if "centímetros" in mensaje and "Altura" not in mensaje:
            con(lambda l: l.update(largo_m=round(l["largo_m"] / 100, 2), ancho_m=round(l["ancho_m"] / 100, 2)),
                f"Convertir a metros: {local['largo_m'] / 100:.2f} × {local['ancho_m'] / 100:.2f} metros.")
        elif "centímetros" in mensaje:
            con(lambda l: l.update(altura_libre_m=round(l["altura_libre_m"] / 100, 2)),
                f"Convertir la altura a metros: {local['altura_libre_m'] / 100:.2f} metros.")
        elif "altura libre" in mensaje:
            con(lambda l: l.update(altura_libre_m=3.0), "Usar una altura libre típica de 3.0 metros (luego mídala).")
        return propuestas

    if tabla != "ESTANTES":
        if "salida de emergencia" in mensaje:
            def agregar_salida(l):
                l.setdefault("obstaculos", []).append({"id": "S1", "tipo": "salida_emergencia", "x_m": round(l["largo_m"] - 0.2, 2),
                                                       "y_m": round(l["ancho_m"] / 2, 2), "largo_m": 0.2, "ancho_m": 1.2, "alto_m": 2.2})
            con(agregar_salida, "Agregar una salida de emergencia S1 en la pared derecha (al centro). Ajuste su posición real después.")
        elif "despacho" in mensaje:
            con(lambda l: l.setdefault("zonas", []).append({"id": "Z1", "tipo": "despacho", "x_m": 0.0, "y_m": 0.0,
                                                            "largo_m": 2.0, "ancho_m": 1.5}),
                "Agregar una zona de despacho de 2 × 1.5 metros en la esquina inferior izquierda (0, 0).")
        elif "fuera del contorno" in mensaje:
            def recortar(l):
                for o in l["obstaculos"]:
                    if o["id"] == identificador:
                        o["x_m"] = round(min(max(0.0, float(o["x_m"])), l["largo_m"] - float(o["largo_m"])), 2)
                        o["y_m"] = round(min(max(0.0, float(o["y_m"])), l["ancho_m"] - float(o["ancho_m"])), 2)
            con(recortar, f"Mover {identificador} al borde más cercano dentro del local.")
            con(lambda l: l.update(obstaculos=[o for o in l["obstaculos"] if o["id"] != identificador]), f"Eliminar {identificador}.")
        return propuestas

    estante = next((e for e in local.get("estantes", []) if e["id"] == identificador), None)
    if estante is None:
        return propuestas
    if "repetido" in mensaje:
        def renombrar(l):
            usados = {e["id"] for e in l["estantes"]}
            numero = 2
            while f"{identificador}_{numero}" in usados:
                numero += 1
            for e in reversed(l["estantes"]):
                if e["id"] == identificador:
                    e["id"] = f"{identificador}_{numero}"
                    break
        con(renombrar, f"Cambiar el nombre del segundo {identificador} para que no se repita.")
        return propuestas
    if "centímetros" in mensaje:
        def dividir(l):
            for e in l["estantes"]:
                if e["id"] == identificador:
                    for c in ("largo_m", "fondo_m", "alto_m"):
                        if float(e[c]) > 15:
                            e[c] = round(float(e[c]) / 100, 2)
        con(dividir, f"Convertir las medidas de {identificador} de centímetros a metros.")
        return propuestas
    if "más alto que la altura libre" in mensaje:
        def bajar(l):
            for e in l["estantes"]:
                if e["id"] == identificador:
                    e["alto_m"] = round(float(l["altura_libre_m"]) - 0.1, 2)
        con(bajar, f"Ajustar la altura de {identificador} a {float(local['altura_libre_m']) - 0.1:.2f} metros (10 cm bajo el techo).")
        return propuestas
    if "supuestos" in mensaje:
        def confirmar(l):
            for e in l["estantes"]:
                if e["id"] == identificador:
                    e["estimado"] = False
        con(confirmar, f"Aceptar los datos de {identificador} como correctos.")
        return propuestas
    if "nivel más alto" in mensaje:
        return propuestas  # solo informativo: el programa ya ignora ese nivel
    # Choques, bloqueos y pasillos angostos: reubicar el estante en el lugar libre más cercano
    sin_estante = copy.deepcopy(local)
    sin_estante["estantes"] = [e for e in sin_estante["estantes"] if e["id"] != identificador]
    movido, nuevo = agregar_estante_libre(sin_estante, parametros, modelo=dict(estante), nuevo_id=identificador)
    if nuevo is not None:
        propuestas.append({"texto": f"Mover {identificador} a un lugar libre: x = {nuevo['x_m']} metros, y = {nuevo['y_m']} metros, "
                                    f"mirando a {nuevo['orientacion']}° (sin chocar ni bloquear salidas, extintores o pasillos).",
                           "local": movido})
    else:
        corto = float(estante["largo_m"]) / 2
        if corto >= 0.6:
            movido, nuevo = agregar_estante_libre(sin_estante, parametros, modelo=dict(estante, largo_m=round(corto, 2)),
                                                  nuevo_id=identificador)
            if nuevo is not None:
                propuestas.append({"texto": f"No hay espacio para {identificador} completo: usar un módulo de {corto:.2f} metros "
                                            f"en x = {nuevo['x_m']}, y = {nuevo['y_m']} metros.", "local": movido})
    propuestas.append({"texto": f"Quitar el estante {identificador} del plano.", "local": sin_estante})
    return propuestas
