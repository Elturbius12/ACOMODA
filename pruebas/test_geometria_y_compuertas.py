"""Fase 4: local, validaciones geométricas, DXF y compuertas."""

import copy
import io

import ezdxf

from conftest import local_un_estante
from modulos.cargar_local import analizar_dxf, leer_dxf, local_desde_trazos
from modulos.comun import pasos_a_invalidar, puede_abrir_paso
from modulos.interpretar_local import (PREGUNTAS_CONFIRMACION_LOCAL, agregar_estante_libre, generar_posiciones,
                                       hay_errores_graves, medir_distancias, niveles_estante, puede_confirmar_local,
                                       rutas_evacuacion, validar_local)


def test_local_de_ejemplo_sin_errores(ejemplo):
    avisos = validar_local(ejemplo)
    assert not hay_errores_graves(avisos)
    posiciones = generar_posiciones(ejemplo)
    assert len(posiciones) == 569 and posiciones["valida"].all()
    assert rutas_evacuacion(ejemplo, 1.2) == []


def test_detecta_choque_con_columna_y_pasillo_angosto(ejemplo):
    local = copy.deepcopy(ejemplo)
    # E10 (x 3.9–6.3, y 5.0) se mueve sobre la columna C1 (x 7.1–7.5)
    e10 = next(e for e in local["estantes"] if e["id"] == "E10")
    e10["x_m"] = 5.5
    # La fila superior baja: el pasillo frente a ella queda de 0.6 m
    for estante in local["estantes"]:
        if estante["y_m"] == 11.5:
            estante["y_m"] = 9.0
    avisos = validar_local(local)
    mensajes = " | ".join(a["mensaje"] for a in avisos)
    assert any(a["gravedad"] == "grave" and "choca con columna C1" in a["mensaje"] for a in avisos), mensajes
    assert any("Pasillo frente a E25" in a["mensaje"] for a in avisos), mensajes
    posiciones = generar_posiciones(local)
    assert posiciones.loc[posiciones["estante"] == "E25", "motivo_eliminacion"].str.contains("pasillo").all()
    # El botón no se activa: hay error grave
    habilitado, motivo = puede_confirmar_local([True] * 4, avisos, "Ana")
    assert not habilitado and "graves" in motivo


def test_boton_confirmar_local_solo_con_todas_las_casillas(ejemplo):
    avisos = validar_local(ejemplo)
    for casillas in ([False] * 4, [True, True, True, False], [True] * 3):
        assert not puede_confirmar_local(casillas, avisos, "Ana")[0]
    assert not puede_confirmar_local([True] * 4, avisos, "")[0]  # sin responsable
    assert puede_confirmar_local([True] * len(PREGUNTAS_CONFIRMACION_LOCAL), avisos, "Ana")[0]


def test_estante_que_bloquea_salida_y_extintor(ejemplo):
    local = copy.deepcopy(ejemplo)
    local["estantes"].append({"id": "EX", "tipo": "gondola", "x_m": 14.8, "y_m": 5.0, "largo_m": 0.9, "fondo_m": 0.4, "alto_m": 1.5,
                              "niveles": 3, "alturas_niveles_m": "", "capacidad_kg_nivel": 50, "orientacion": 270,
                              "costo_soles": 0, "zona_controlada": "no", "permite_peligrosos": "no"})
    avisos = validar_local(local)
    assert any(a["id"] == "EX" and "salida de emergencia" in a["mensaje"] and a["gravedad"] == "grave" for a in avisos)
    local = copy.deepcopy(ejemplo)
    local["estantes"][0]["x_m"] = 0.6  # E1 queda a menos de 1 m del extintor X1? (X1 en y 5.0; E1 en y 2.6 → no)
    local["obstaculos"].append({"id": "X9", "tipo": "extintor", "x_m": 1.5, "y_m": 2.0, "largo_m": 0.3, "ancho_m": 0.3, "alto_m": 1.5})
    posiciones = generar_posiciones(local)
    assert posiciones["motivo_eliminacion"].str.contains("extintor X9").any()


def test_unidades_dudosas():
    local = local_un_estante()
    local["largo_m"], local["ancho_m"] = 600, 400
    assert any("centímetros" in a["mensaje"] for a in validar_local(local))


def test_nivel_sobre_altura_libre_se_elimina():
    local = local_un_estante(niveles=3)
    local["altura_libre_m"] = 1.2
    posiciones = generar_posiciones(local)
    assert (~posiciones[posiciones["nivel"] == 3]["valida"]).all()
    assert posiciones[posiciones["nivel"] == 1]["valida"].all()


def test_distancia_caminando_rodea_obstaculos(ejemplo):
    posiciones = medir_distancias(generar_posiciones(ejemplo), ejemplo)
    # E5 mira hacia arriba (y 4.0): el acceso exige rodear la góndola, más que la línea recta desde el despacho
    fila = posiciones[posiciones["id_posicion"] == "E5-N1-T2"].iloc[0]
    recta = ((fila["x_acceso"] - 1.55) ** 2 + (fila["y_acceso"] - 1.05) ** 2) ** 0.5
    assert fila["distancia_m"] > recta + 0.5


def test_niveles_con_alturas_distintas():
    niveles = niveles_estante({"alto_m": 2.0, "niveles": 3, "alturas_niveles_m": "0.5;0.4;0.3"})
    assert [round(n[1], 2) for n in niveles] == [0.5, 0.4, 0.3]
    assert niveles[1][0] > niveles[0][0] + 0.5


def test_dxf_con_capas(tmp_path):
    documento = ezdxf.new()
    documento.header["$INSUNITS"] = 5  # centímetros
    espacio = documento.modelspace()
    espacio.add_lwpolyline([(0, 0), (1000, 0), (1000, 800), (0, 800)], close=True, dxfattribs={"layer": "MUROS"})
    espacio.add_lwpolyline([(200, 300), (440, 300), (440, 350), (200, 350)], close=True, dxfattribs={"layer": "ESTANTES"})
    espacio.add_lwpolyline([(600, 400), (640, 400), (640, 440), (600, 440)], close=True, dxfattribs={"layer": "COLUMNAS"})
    espacio.add_lwpolyline([(400, 0), (500, 0), (500, 10), (400, 10)], close=True, dxfattribs={"layer": "PUERTAS"})
    ruta = tmp_path / "plano.dxf"
    documento.saveas(ruta)
    contenido = ruta.read_bytes()
    info = analizar_dxf(contenido)
    assert info["unidad"] == "centímetros" and info["mapeo"]["ESTANTES"] == "estante"
    local = leer_dxf(contenido, info["mapeo"], info["factor"], 3.0)
    assert local["largo_m"] == 10.0 and local["ancho_m"] == 8.0
    assert len(local["estantes"]) == 1 and local["estantes"][0]["largo_m"] == 2.4 and local["estantes"][0]["estimado"]
    assert {o["tipo"] for o in local["obstaculos"]} == {"columna", "puerta"}


def test_trazos_sobre_imagen():
    objetos = [{"type": "rect", "left": 10, "top": 10, "width": 500, "height": 400, "stroke": "#000000"},
               {"type": "rect", "left": 60, "top": 60, "width": 120, "height": 25, "stroke": "#1f77b4"}]
    local = local_desde_trazos(objetos, 0.02, 3.0)
    assert local["largo_m"] == 10.0 and local["ancho_m"] == 8.0
    estante = local["estantes"][0]
    assert estante["largo_m"] == 2.4 and abs(estante["y_m"] - (410 - 85) * 0.02) < 1e-6
    assert local["fuente"] == "imagen"


def test_compuertas():
    assert puede_abrir_paso(1, {})
    assert not puede_abrir_paso(2, {})
    assert not puede_abrir_paso(4, {1: True, 2: True, 3: False})
    assert puede_abrir_paso(4, {1: True, 2: True, 3: True})
    assert pasos_a_invalidar(3) == [3, 4, 5, 6, 7, 8]


def test_estante_extra_en_lugar_libre(ejemplo):
    nuevo, estante = agregar_estante_libre(ejemplo)
    assert estante is not None
    assert not [a for a in validar_local(nuevo) if a["id"] == estante["id"]]
