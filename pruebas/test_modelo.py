"""Fases 5 y 6: normas → restricciones, modelo, heurística, validador e indicadores."""

import copy

import pytest

from conftest import CATALOGO_REAL, VENTAS_REAL, catalogo_sintetico, local_un_estante, resumen_sintetico
from modulos.comun import cargar_ajustes
from modulos.indicadores import (evaluacion_economica, evaluar, linea_base_alfabetica, lista_reubicacion,
                                 validar_solucion)
from modulos.interpretar_local import generar_posiciones, medir_distancias
from modulos.modelo_optimo import optimizar, valor_objetivo
from modulos.normas import (cambiar_activa, cambiar_parametro, estado_inicial, incompatibilidades_activas,
                            parametros_activos, reporte_final, semaforo_local)

PESOS_SIN_BLANDAS = dict(cargar_ajustes()["objetivo"], peso_reglas_blandas=0.0, peso_agrupar_categoria=0.0,
                         peso_pares_comprobante=0.0)


def _resolver(catalogo, rotaciones, local, parametros, incompat=(), modo="almacen", pesos=None):
    posiciones = medir_distancias(generar_posiciones(local, parametros), local, modo)
    return optimizar(catalogo, resumen_sintetico(catalogo, rotaciones), posiciones, local, parametros, list(incompat),
                     None, modo, "bazar", pesos or PESOS_SIN_BLANDAS, tiempo_limite=30)


def _parametros(**cambios):
    parametros = parametros_activos(estado_inicial("bazar"), "almacen")
    parametros.update(dias_cobertura=0)
    parametros.update(cambios)
    return parametros


def test_modelo_pequeno_coincide_con_calculo_a_mano():
    """10 productos, 12 posiciones (1 estante × 3 niveles × 4 tramos). Cada producto (55 cm de frente)
    llena un tramo de 60 cm, así que el óptimo se calcula a mano: el producto de mayor rotación va a la
    posición de menor costo, el segundo a la segunda, etc. (desigualdad de reordenamiento)."""
    catalogo = catalogo_sintetico([{"largo_cm": 55, "ancho_cm": 30, "alto_cm": 20, "peso_kg": 1.0} for _ in range(10)])
    rotaciones = [9.0, 1.0, 7.0, 3.0, 10.0, 2.0, 5.0, 4.0, 8.0, 6.0]
    local = local_un_estante(niveles=3)
    solucion = _resolver(catalogo, rotaciones, local, _parametros())
    validas = solucion["validas"]
    assert len(validas) == 12
    costos = sorted(validas["costo_acceso"])
    esperado = sum(r * c for r, c in zip(sorted(rotaciones, reverse=True), costos[:10]))
    assert solucion["estado"].startswith("Óptimo")
    assert len(solucion["asignacion"]) == 10
    assert solucion["objetivo"] == pytest.approx(esperado, rel=1e-6)
    assert valor_objetivo(solucion["asignacion"], solucion["pares"]) == pytest.approx(esperado, rel=1e-6)
    # el de mayor rotación ocupa la posición más barata
    i_max = rotaciones.index(max(rotaciones))
    assert validas.at[solucion["asignacion"][i_max], "costo_acceso"] == pytest.approx(costos[0])
    assert not validar_solucion(solucion["asignacion"], solucion["productos"], validas, local, solucion["pares"],
                                _parametros())["duros"]


def test_si_no_cabe_todo_lo_explica():
    catalogo = catalogo_sintetico([{"largo_cm": 55, "ancho_cm": 30, "alto_cm": 20, "peso_kg": 1.0} for _ in range(14)])
    solucion = _resolver(catalogo, [1.0] * 14, local_un_estante(niveles=3), _parametros())
    assert len(solucion["asignacion"]) == 12
    faltante = solucion["faltante"]
    assert faltante["productos_fuera"] == 2 and faltante["volumen_faltante_m3"] > 0 and faltante["modulos_sugeridos"] >= 1
    assert "No cabe todo" in faltante["texto"]


def test_limite_de_peso_25_a_15_cambia_el_resultado():
    catalogo = catalogo_sintetico([{"largo_cm": 30, "ancho_cm": 30, "alto_cm": 30, "peso_kg": 20.0},
                                   {"largo_cm": 20, "ancho_cm": 20, "alto_cm": 20, "peso_kg": 1.0}])
    local = local_un_estante(niveles=3)
    estado = estado_inicial("bazar")
    parametros_25 = dict(parametros_activos(estado, "almacen"), dias_cobertura=0)
    con_25 = _resolver(catalogo, [2.0, 1.0], local, parametros_25)
    cambiar_parametro(estado, "ergonomia", "limite_peso_kg", 15, "prueba")
    parametros_15 = dict(parametros_activos(estado, "almacen"), dias_cobertura=0)
    con_15 = _resolver(catalogo, [2.0, 1.0], local, parametros_15)
    assert 0 in con_25["asignacion"] and 0 not in con_15["asignacion"]
    fila = con_15["ubicaciones"].iloc[0]
    assert not fila["ubicado"] and "límite ergonómico de 15" in fila["motivo"]
    assert estado["cambios"] and "25 → 15" in estado["cambios"][0]["cambio"]


def test_incompatibilidad_separa_categorias():
    filas = [{"categoria": "LIMPIEZA", "largo_cm": 10, "ancho_cm": 10, "alto_cm": 20, "peso_kg": 0.5},
             {"categoria": "BEBIDAS", "largo_cm": 10, "ancho_cm": 10, "alto_cm": 20, "peso_kg": 0.5}]
    catalogo = catalogo_sintetico(filas)
    local = local_un_estante(niveles=2)
    segundo = copy.deepcopy(local["estantes"][0])
    segundo.update(id="E2", y_m=1.4, orientacion=180)
    local["estantes"].append(segundo)  # E2 a 1.1 m de E1 (pasillo entre ambos)
    estado = estado_inicial("bazar")
    incompat = incompatibilidades_activas(estado)
    assert any({a, b} == {"LIMPIEZA", "BEBIDAS"} for a, b, _, _ in incompat)
    parametros = dict(parametros_activos(estado, "almacen"), dias_cobertura=0, ancho_pasillo_min_m=0.9)
    solucion = _resolver(catalogo, [5.0, 5.0], local, parametros, incompat)
    assert len(solucion["asignacion"]) == 2
    estantes = {solucion["validas"].at[j, "estante"] for j in solucion["asignacion"].values()}
    assert len(estantes) == 2  # no pueden compartir estante
    assert not validar_solucion(solucion["asignacion"], solucion["productos"], solucion["validas"], local, solucion["pares"],
                                parametros, incompat)["duros"]


def test_alto_valor_solo_en_zona_controlada():
    catalogo = catalogo_sintetico([{"valor_alto": "si", "largo_cm": 10, "ancho_cm": 10, "alto_cm": 10, "peso_kg": 0.2}])
    local = local_un_estante()
    solucion = _resolver(catalogo, [1.0], local, _parametros())
    assert not solucion["asignacion"]
    assert "zona controlada" in solucion["ubicaciones"].iloc[0]["motivo"]
    local["estantes"][0]["zona_controlada"] = "si"
    assert _resolver(catalogo, [1.0], local, _parametros())["asignacion"]


def test_validador_detecta_violaciones():
    catalogo = catalogo_sintetico([{"largo_cm": 55, "ancho_cm": 30, "alto_cm": 20, "peso_kg": 1.0} for _ in range(3)])
    local = local_un_estante()
    solucion = _resolver(catalogo, [3.0, 2.0, 1.0], local, _parametros())
    forzada = {0: 0, 1: 0, 2: 1}  # dos productos de 55 cm en el mismo tramo de 60 cm
    duros = validar_solucion(forzada, solucion["productos"], solucion["validas"], local, solucion["pares"], _parametros())["duros"]
    assert any("ancho ocupado" in d for d in duros)


def test_normas_desactivada_y_semaforo(ejemplo):
    estado = estado_inicial("bazar")
    cambiar_activa(estado, "extintores", False, "prueba")
    parametros = parametros_activos(estado, "almacen", ejemplo)
    assert parametros["despeje_extintor_m"] is None
    filas = {f["id"]: f for f in semaforo_local(estado, ejemplo, [], generar_posiciones(ejemplo, parametros))}
    assert filas["extintores"]["resultado"] == "no aplica" and "Desactivada" in filas["extintores"]["detalle"]
    assert filas["farmacia"]["resultado"] == "no aplica"  # no corresponde al rubro bazar
    assert filas["itse"]["resultado"] == "por verificar"
    assert estado["cambios"][0]["cambio"].startswith("DESACTIVADA")


def test_solo_ergonomia_esta_verificada():
    estado = estado_inicial("bazar")
    verificadas = [n["id"] for n in estado["normas"] if n["estado"] == "verificada"]
    assert verificadas == ["ergonomia"]
    ergonomia = estado["normas"][0]
    assert ergonomia["parametros"]["limite_peso_kg"]["valor"] == 25
    assert ergonomia["parametros"]["limite_peso_kg"]["opciones"] == [15, 25, 40]


@pytest.mark.skipif(not CATALOGO_REAL.exists() or VENTAS_REAL is None, reason="Faltan los Excel del caso real")
def test_caso_real_resuelve_en_tiempo_y_sin_violaciones(ejemplo):
    from modulos.analisis_ventas import estadisticas_pedidos, pares_comprobante, resumen_por_producto
    from modulos.cargar_catalogo import cargar_catalogo
    from modulos.cargar_ventas import aplicar_mapeo, leer_reporte, proponer_mapeo, unir_con_catalogo
    catalogo = cargar_catalogo(CATALOGO_REAL.read_bytes(), CATALOGO_REAL.name)["catalogo"]
    tabla, _ = leer_reporte(VENTAS_REAL.read_bytes(), VENTAS_REAL.name)
    ventas, _ = aplicar_mapeo(tabla, proponer_mapeo(tabla)[0])
    dentro, union, _ = unir_con_catalogo(ventas, catalogo)
    resumen = resumen_por_producto(dentro, catalogo)
    estado = estado_inicial("bazar")
    parametros = parametros_activos(estado, "almacen", ejemplo)
    incompat = incompatibilidades_activas(estado)
    limite = 60
    posiciones = medir_distancias(generar_posiciones(ejemplo, parametros), ejemplo, "almacen")
    solucion = optimizar(catalogo, resumen, posiciones, ejemplo, parametros, incompat, pares_comprobante(dentro, 30), "almacen",
                         "bazar", tiempo_limite=limite)
    assert solucion["tiempo_s"] <= limite + 30  # tiempo límite del solver + armado del modelo
    assert solucion["fuente"] in ("modelo", "heuristica")
    assert len(solucion["asignacion"]) >= 0.95 * len(catalogo)
    validacion = validar_solucion(solucion["asignacion"], solucion["productos"], solucion["validas"], ejemplo,
                                  solucion["pares"], parametros, incompat)
    assert validacion["duros"] == []
    # El "después" mejora el costo de acceso frente a la línea base
    estadisticas = estadisticas_pedidos(dentro, union["dias_periodo"])
    antes = linea_base_alfabetica(solucion["productos"], solucion["pares"], solucion["validas"], ejemplo)
    kpi_antes = evaluar(antes, solucion["productos"], solucion["validas"], ejemplo, solucion["pares"], estadisticas)
    kpi_despues = evaluar(solucion["asignacion"], solucion["productos"], solucion["validas"], ejemplo, solucion["pares"], estadisticas)
    assert kpi_despues["costo_acceso_ponderado"] < kpi_antes["costo_acceso_ponderado"]
    assert kpi_despues["distancia_ponderada_m_dia"] < kpi_antes["distancia_ponderada_m_dia"]
    movimientos = lista_reubicacion(antes, solucion["asignacion"], solucion["productos"], solucion["validas"])
    assert movimientos["beneficio_relativo_dia"].is_monotonic_decreasing
    economia = evaluacion_economica(kpi_antes, kpi_despues, len(movimientos))
    assert economia["ahorro_mensual"] > 0 and economia["recuperacion_meses"] is not None
    filas = reporte_final(estado, semaforo_local(estado, ejemplo, [], posiciones, catalogo), validacion,
                          solucion["ubicaciones"], catalogo)
    assert {f["Resultado de la propuesta"] for f in filas} <= {"cumple", "no cumple", "por verificar", "no aplica"}
