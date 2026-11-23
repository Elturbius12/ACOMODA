"""Convierte las normativas incluidas (carpeta normativas/) en parámetros y restricciones
del modelo, y arma el semáforo cumple / no cumple / por verificar."""

import copy
from datetime import datetime

from modulos.comun import cargar_normativas, cargar_perfiles

CUMPLE, NO_CUMPLE, POR_VERIFICAR, NO_APLICA = "cumple", "no cumple", "por verificar", "no aplica"


def estado_inicial(perfil_id="bazar"):
    """Copia editable de las normas y reglas, marcando cuáles aplican al rubro."""
    datos = copy.deepcopy(cargar_normativas())
    perfiles = cargar_perfiles()["perfiles"]
    extra = perfiles.get(perfil_id, {}).get("normas_extra", []) if perfil_id else []
    for norma in datos["normas"]:
        rubros = norma.get("rubros")
        norma["aplicable"] = rubros is None or (perfil_id in rubros) or (norma["id"] in extra)
        for parametro in norma["parametros"].values():
            parametro["valor_original"] = parametro["valor"]
        norma["activa_original"] = norma["activa"]
    for regla in datos["reglas_negocio"]:
        for parametro in regla["parametros"].values():
            parametro["valor_original"] = parametro["valor"]
        regla["activa_original"] = regla["activa"]
    perfil = perfiles.get(perfil_id, {})
    datos["incompatibilidades"] = datos["incompatibilidades"] + perfil.get("incompatibilidades_extra", [])
    datos["perfil"] = perfil_id
    datos["cambios"] = []
    return datos


def buscar_norma(estado, id_norma):
    return next((n for n in estado["normas"] if n["id"] == id_norma), None)


def buscar_regla(estado, id_regla):
    return next((r for r in estado["reglas_negocio"] if r["id"] == id_regla), None)


def norma_vigente(estado, id_norma):
    norma = buscar_norma(estado, id_norma)
    return norma is not None and norma["activa"] and norma["aplicable"]


def valor(estado, id_norma, clave):
    norma = buscar_norma(estado, id_norma)
    if norma is None or not norma_vigente(estado, id_norma):
        return None
    return norma["parametros"][clave]["valor"]


def valor_regla(estado, id_regla, clave, por_defecto=None):
    regla = buscar_regla(estado, id_regla)
    if regla is None or not regla["activa"]:
        return por_defecto
    return regla["parametros"].get(clave, {}).get("valor", por_defecto)


def regla_activa(estado, id_regla):
    regla = buscar_regla(estado, id_regla)
    return bool(regla and regla["activa"])


def parametros_activos(estado, modo="almacen", local=None):
    """Diccionario con los valores que usa el modelo. None = la norma no se aplica."""
    estado = estado or estado_inicial("bazar")
    alturas_piso = [v for v in (valor(estado, "farmacia", "altura_minima_piso_m"),
                                valor(estado, "alimentos", "altura_minima_piso_m")) if v is not None]
    return {
        "limite_peso_kg": valor(estado, "ergonomia", "limite_peso_kg"),
        "despeje_tablero_m": valor(estado, "sst", "despeje_tablero_m"),
        "ancho_pasillo_min_m": valor(estado, "sst", "ancho_pasillo_min_m"),
        "despeje_salida_m": valor(estado, "incendios", "despeje_salida_m"),
        "ancho_evacuacion_m": valor(estado, "incendios", "ancho_evacuacion_m"),
        "despeje_rociador_m": valor(estado, "incendios", "despeje_rociador_m"),
        "despeje_extintor_m": valor(estado, "extintores", "despeje_extintor_m"),
        "distancia_max_extintor_m": valor(estado, "extintores", "distancia_max_extintor_m"),
        "ancho_pasillo_accesible_m": valor(estado, "accesibilidad", "ancho_pasillo_accesible_m") if modo == "tienda" else None,
        "altura_minima_piso_m": max(alturas_piso) if alturas_piso else None,
        "separacion_limpieza_m": valor(estado, "alimentos", "separacion_limpieza_m"),
        "exigir_precio": norma_vigente(estado, "consumidor"),
        "frio_obligatorio": norma_vigente(estado, "farmacia"),
        # Reglas de negocio
        "umbral_pesado_kg": valor_regla(estado, "pesados_abajo", "umbral_kg"),
        "fragil_no_debajo": regla_activa(estado, "fragil_no_debajo"),
        "incompatibles": regla_activa(estado, "incompatibles"),
        "fefo": regla_activa(estado, "fefo"),
        "ninos_altura_max_m": valor_regla(estado, "ninos_bajos", "altura_max_m"),
        "valor_alto_controlado": regla_activa(estado, "valor_alto_controlado"),
        "dias_cobertura": valor_regla(estado, "stock_minimo", "dias_cobertura", 0) if regla_activa(estado, "stock_minimo") else 0,
    }


def incompatibilidades_activas(estado):
    """Lista de (categoria_a, categoria_b, distancia_min_m, motivo) que el modelo debe respetar."""
    pares = {}
    if regla_activa(estado, "incompatibles"):
        for fila in estado["incompatibilidades"]:
            if not fila.get("categoria_a") or not fila.get("categoria_b"):
                continue
            clave = tuple(sorted((str(fila["categoria_a"]).upper(), str(fila["categoria_b"]).upper())))
            pares[clave] = (max(float(fila.get("distancia_min_m") or 0), pares.get(clave, (0, ""))[0]),
                            fila.get("motivo", "regla de negocio"))
    separacion = valor(estado, "alimentos", "separacion_limpieza_m")
    if separacion:
        for comida in ("ALIMENTOS", "BEBIDAS"):
            clave = tuple(sorted(("LIMPIEZA", comida)))
            anterior = pares.get(clave, (0, ""))[0]
            pares[clave] = (max(anterior, separacion), "DIGESA: alimentos separados de limpieza")
    return [(a, b, d, motivo) for (a, b), (d, motivo) in pares.items() if d > 0]


def cambiar_parametro(estado, id_norma, clave, nuevo_valor, responsable=""):
    norma = buscar_norma(estado, id_norma)
    anterior = norma["parametros"][clave]["valor"]
    if anterior == nuevo_valor:
        return
    norma["parametros"][clave]["valor"] = nuevo_valor
    estado["cambios"].append({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "norma": f"{norma['numero']}",
                              "cambio": f"{clave}: {anterior} → {nuevo_valor}",
                              "original": norma["parametros"][clave]["valor_original"], "responsable": responsable})


def cambiar_activa(estado, id_norma, activa, responsable=""):
    norma = buscar_norma(estado, id_norma) or buscar_regla(estado, id_norma)
    if norma["activa"] == activa:
        return
    norma["activa"] = activa
    nombre = norma.get("numero", norma.get("nombre"))
    estado["cambios"].append({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "norma": nombre,
                              "cambio": "ACTIVADA" if activa else "DESACTIVADA (no aplicable según el usuario)",
                              "original": "activa" if norma["activa_original"] else "inactiva", "responsable": responsable})


def cambiar_parametro_regla(estado, id_regla, clave, nuevo_valor, responsable=""):
    regla = buscar_regla(estado, id_regla)
    anterior = regla["parametros"][clave]["valor"]
    if anterior == nuevo_valor:
        return
    regla["parametros"][clave]["valor"] = nuevo_valor
    estado["cambios"].append({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "norma": regla["nombre"],
                              "cambio": f"{clave}: {anterior} → {nuevo_valor}",
                              "original": regla["parametros"][clave]["valor_original"], "responsable": responsable})


def texto_regla(norma):
    """Frase de la regla con los valores actuales: 'Peso por unidad ≤ 25 kg'."""
    texto = norma.get("regla_modelo") or norma.get("descripcion", "")
    for clave, parametro in norma.get("parametros", {}).items():
        texto = texto.replace("{" + clave + "}", str(parametro["valor"]))
    return texto


def resumen(estado):
    aplicables = [n for n in estado["normas"] if n["aplicable"] and n["activa"]]
    return {"consideradas": len(aplicables),
            "obligatorias": sum(1 for n in aplicables if n["tipo"] == "obligatoria"),
            "por_verificar": sum(1 for n in aplicables if n["estado"] != "verificada")}


# --------------------------------------------------------------------------------------
# Semáforo sobre el local confirmado
# --------------------------------------------------------------------------------------

def semaforo_local(estado, local, avisos, posiciones, catalogo=None, modo="almacen"):
    """Una fila por norma: resultado (cumple / no cumple / por verificar / no aplica) y detalle."""
    from modulos.interpretar_local import (distancia_rects, huella_estante, huella_obstaculo,
                                           rutas_evacuacion)
    parametros = parametros_activos(estado, modo, local)
    filas = []
    obstaculos = local.get("obstaculos", [])
    salidas = [o for o in obstaculos if o["tipo"] == "salida_emergencia"]
    extintores = [o for o in obstaculos if o["tipo"] == "extintor"]
    equipos = {e.get("tipo") for e in local.get("equipos", [])}

    def agregar(norma, resultado, detalle):
        filas.append({"id": norma["id"], "norma": norma["numero"], "nombre": norma["nombre"],
                      "verificacion": norma["estado"], "resultado": resultado, "detalle": detalle})

    for norma in estado["normas"]:
        if not norma["aplicable"]:
            agregar(norma, NO_APLICA, "No corresponde al rubro elegido.")
            continue
        if not norma["activa"]:
            agregar(norma, NO_APLICA, "Desactivada por el usuario (registrado en el acta).")
            continue
        identificador = norma["id"]
        if identificador == "ergonomia":
            limite = parametros["limite_peso_kg"]
            pesados = []
            if catalogo is not None and "peso_kg" in catalogo:
                pesados = catalogo[catalogo["peso_kg"].fillna(0) > limite]["producto"].tolist()
            con_equipo = bool(equipos & {"transpaleta", "apilador", "montacargas"})
            if pesados and not con_equipo:
                agregar(norma, NO_CUMPLE, f"{len(pesados)} productos pesan más de {limite} kg por unidad y el local no tiene "
                                          f"equipo de carga: no se podrán ubicar (ej.: {', '.join(pesados[:3])}).")
            elif pesados:
                agregar(norma, CUMPLE, f"{len(pesados)} productos pesan más de {limite} kg: solo irán al nivel del piso con equipo.")
            else:
                agregar(norma, CUMPLE, f"Ningún producto supera {limite} kg por unidad; el modelo aplica el límite.")
        elif identificador == "sst":
            problemas = [a["mensaje"] for a in avisos if "tablero" in a["mensaje"] or "Pasillo" in a["mensaje"]]
            agregar(norma, NO_CUMPLE if problemas else CUMPLE,
                    "; ".join(problemas) if problemas else
                    f"Tableros con {parametros['despeje_tablero_m']} m libres y pasillos ≥ {parametros['ancho_pasillo_min_m']} m.")
        elif identificador == "incendios":
            problemas = [a["mensaje"] for a in avisos if "salida de emergencia" in a["mensaje"] and a["gravedad"] == "grave"]
            if not salidas:
                problemas.append("No hay salida de emergencia registrada.")
            sin_ruta = rutas_evacuacion(local, parametros["ancho_evacuacion_m"]) if salidas else []
            if sin_ruta:
                problemas.append(f"Sin ruta de evacuación de {parametros['ancho_evacuacion_m']} m desde: {', '.join(sin_ruta)}.")
            eliminadas = 0
            if posiciones is not None and len(posiciones):
                eliminadas = int(posiciones["motivo_eliminacion"].str.contains("altura máxima").sum())
            detalle = "; ".join(problemas) if problemas else "Salidas despejadas y rutas de evacuación con el ancho mínimo."
            if eliminadas:
                detalle += f" {eliminadas} posiciones eliminadas por altura (techo o rociadores)."
            agregar(norma, NO_CUMPLE if problemas else CUMPLE, detalle)
        elif identificador == "itse":
            agregar(norma, POR_VERIFICAR, "Requiere inspección municipal. Revise salidas, extintores, señalización, "
                                          "tableros y pasillos con el resultado de este semáforo.")
        elif identificador == "senalizacion":
            if not salidas:
                agregar(norma, NO_CUMPLE, "No hay salida de emergencia registrada para señalizar.")
            else:
                agregar(norma, POR_VERIFICAR, f"{len(salidas)} salida(s) y {len(extintores)} extintor(es) deben tener su señal; revisar en campo.")
        elif identificador == "extintores":
            problemas = [a["mensaje"] for a in avisos if "extintor" in a["mensaje"]]
            if not extintores:
                problemas.append("No hay extintores registrados.")
            else:
                maximo = parametros["distancia_max_extintor_m"]
                lejanos = [e["id"] for e in local.get("estantes", [])
                           if min(distancia_rects(huella_estante(e), huella_obstaculo(x)) for x in extintores) > maximo]
                if lejanos:
                    problemas.append(f"Estantes a más de {maximo} m de un extintor: {', '.join(lejanos)}.")
            agregar(norma, NO_CUMPLE if problemas else CUMPLE,
                    "; ".join(problemas) if problemas else f"{len(extintores)} extintor(es) accesibles.")
        elif identificador == "accesibilidad":
            if modo != "tienda":
                agregar(norma, NO_APLICA, "Solo se evalúa en modo tienda (pasillos de clientes).")
            else:
                problemas = [a["mensaje"] for a in avisos if "Pasillo" in a["mensaje"]]
                agregar(norma, NO_CUMPLE if problemas else CUMPLE,
                        "; ".join(problemas) if problemas else f"Pasillos ≥ {parametros['ancho_pasillo_accesible_m']} m.")
        elif identificador == "consumidor":
            sin_precio = []
            if catalogo is not None and "precio_venta" in catalogo:
                sin_precio = catalogo[catalogo["precio_venta"].fillna(0) <= 0]["producto"].tolist()
            agregar(norma, NO_CUMPLE if sin_precio else CUMPLE,
                    f"{len(sin_precio)} productos sin precio de venta: no se pueden exhibir con precio (ej.: {', '.join(sin_precio[:3])})."
                    if sin_precio else "Todos los productos tienen precio de venta registrado.")
        elif identificador in ("farmacia", "alimentos"):
            eliminadas = 0
            if posiciones is not None and len(posiciones):
                eliminadas = int(posiciones["motivo_eliminacion"].str.contains("del piso").sum())
            texto = texto_regla(norma) + (f" {eliminadas} posiciones eliminadas por estar muy cerca del piso." if eliminadas else "")
            agregar(norma, CUMPLE, texto + " Se aplica en el modelo.")
        else:
            agregar(norma, POR_VERIFICAR, "Sin chequeo automático.")
    return filas


# --------------------------------------------------------------------------------------
# Reporte normativo final (Paso 7): la propuesta frente a cada norma
# --------------------------------------------------------------------------------------

def reporte_final(estado, semaforo, validacion, ubicaciones, catalogo=None):
    """Una fila por norma con el resultado de la PROPUESTA y las excepciones autorizadas."""
    duros = validacion.get("duros", [])
    filas = []
    ubicados = ubicaciones[ubicaciones["ubicado"]] if ubicaciones is not None else None
    for fila in semaforo:
        resultado, detalle = fila["resultado"], fila["detalle"]
        identificador = fila["id"]
        if resultado != NO_APLICA:
            if identificador == "ergonomia":
                fallas = [d for d in duros if "límite ergonómico" in d]
                resultado = NO_CUMPLE if fallas else CUMPLE
                detalle = "; ".join(fallas[:5]) if fallas else "Ningún producto ubicado supera el límite por unidad manipulada."
            elif identificador in ("sst", "incendios", "extintores", "accesibilidad"):
                fallas = [d for d in duros if "posición eliminada" in d]
                if fallas:
                    resultado, detalle = NO_CUMPLE, "; ".join(fallas[:5])
                elif resultado == CUMPLE:
                    detalle = "La propuesta solo usa posiciones que respetan pasillos y despejes. " + detalle
                else:
                    detalle = "La propuesta no usa las posiciones afectadas, pero el LOCAL debe corregirse: " + detalle
            elif identificador == "alimentos":
                fallas = [d for d in duros if "DIGESA" in d or "mínimo" in d]
                resultado = NO_CUMPLE if fallas else CUMPLE
                detalle = "; ".join(fallas[:5]) if fallas else "Alimentos y bebidas separados de limpieza y fuera del piso."
            elif identificador == "farmacia":
                resultado = CUMPLE if not duros else resultado
            elif identificador == "consumidor" and ubicados is not None and catalogo is not None:
                sin_precio = catalogo[catalogo["precio_venta"].fillna(0) <= 0]["id_producto"]
                exhibidos = ubicados[ubicados["id_producto"].isin(sin_precio)]
                resultado = NO_CUMPLE if len(exhibidos) else CUMPLE
                detalle = (f"{len(exhibidos)} productos ubicados no tienen precio de venta registrado." if len(exhibidos)
                           else "Todos los productos ubicados tienen precio de venta para exhibir.")
        filas.append({"Norma": fila["norma"], "Nombre": fila["nombre"], "Verificación del texto": fila["verificacion"],
                      "Resultado de la propuesta": resultado, "Detalle": detalle})
    return filas
