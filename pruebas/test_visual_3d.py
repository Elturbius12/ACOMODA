"""Fase 7: la vista 3D se genera y el HTML independiente es válido (y abre en un navegador si hay uno)."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import plotly.graph_objects as go
import pytest

from conftest import catalogo_sintetico, local_un_estante, resumen_sintetico
from modulos.interpretar_local import generar_posiciones, medir_distancias
from modulos.modelo_optimo import optimizar
from modulos.normas import estado_inicial, parametros_activos
from modulos.visual_2d import plano_2d
from modulos.visual_3d import figura_3d, guardar_html, recorrido_pedido

NAVEGADORES = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
               Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")]


def _revisar_html(ruta):
    texto = Path(ruta).read_text(encoding="utf-8")
    assert "Plotly.newPlot" in texto
    assert "plotly.js" in texto.lower() or "plotly" in texto[:5000].lower()  # librería incluida: abre sin internet
    datos = re.search(r"Plotly\.newPlot\(\s*\"[^\"]+\",\s*(\[.*?\]),\s*\{", texto, re.S)
    assert datos, "no se encontró la figura dentro del HTML"
    trazas = json.loads(datos.group(1))
    assert len(trazas) > 5
    return trazas


def _abre_en_navegador(ruta):
    navegador = next((n for n in NAVEGADORES if n.exists()), None) or (shutil.which("msedge") and Path(shutil.which("msedge")))
    if not navegador:
        pytest.skip("No hay navegador para la prueba visual")
    resultado = subprocess.run([str(navegador), "--headless=new", "--disable-gpu", "--use-angle=swiftshader",
                                "--enable-unsafe-swiftshader", "--virtual-time-budget=10000", "--dump-dom",
                                Path(ruta).resolve().as_uri()], capture_output=True, text=True, timeout=120,
                               encoding="utf-8", errors="ignore")
    dom = resultado.stdout
    assert "plot-container" in dom or "gl-container" in dom or "main-svg" in dom, "Plotly no dibujó la figura"


def test_3d_local_de_ejemplo(ejemplo, tmp_path):
    figura = figura_3d(ejemplo, parametros_activos(estado_inicial("bazar"), "almacen", ejemplo))
    assert isinstance(figura, go.Figure)
    nombres = {t.name for t in figura.data}
    assert {"Piso", "Columna", "Extintor", "Salida emergencia", "Zonas prohibidas", "Bandejas de estante"} <= nombres
    ruta = guardar_html(figura, tmp_path / "local.html")
    _revisar_html(ruta)
    _abre_en_navegador(ruta)


def test_3d_con_productos_antes_despues_y_recorrido(tmp_path):
    catalogo = catalogo_sintetico([{"largo_cm": 20, "ancho_cm": 15, "alto_cm": 18, "peso_kg": 0.5} for _ in range(8)])
    catalogo.loc[0, "origen_medidas"] = "estimado"
    local = local_un_estante(niveles=3)
    parametros = dict(parametros_activos(estado_inicial("bazar"), "almacen", local), dias_cobertura=0)
    posiciones = medir_distancias(generar_posiciones(local, parametros), local)
    solucion = optimizar(catalogo, resumen_sintetico(catalogo, [8, 7, 6, 5, 4, 3, 2, 1]), posiciones, local, parametros, [],
                         tiempo_limite=20)
    antes = {i: j for i, j in zip(sorted(solucion["asignacion"]), reversed(sorted(solucion["asignacion"].values())))}
    ruta_picking = recorrido_pedido(local, solucion["validas"], solucion["asignacion"], list(catalogo["id_producto"][:3]),
                                    solucion["productos"])
    assert ruta_picking and len(ruta_picking) > 3
    figura = figura_3d(local, parametros, solucion, asignacion_antes=antes, recorrido=ruta_picking)
    nombres = [t.name for t in figura.data]
    assert any(n and n.startswith("Productos clase") for n in nombres)
    assert any(n and n.startswith("Antes clase") for n in nombres)
    assert "Recorrido de picking" in nombres and "Borde punteado: medida estimada" in nombres
    ruta = guardar_html(figura, tmp_path / "visual_3d.html")
    texto = Path(ruta).read_text(encoding="utf-8")
    assert "Planta" in texto and "Isom" in texto and "hasta nivel" in texto  # botones y deslizador
    _revisar_html(ruta)
    _abre_en_navegador(ruta)
    # filtros de la versión en pantalla
    filtrada = figura_3d(local, parametros, solucion, clases=["A"], altura_max=0.5, modo_color="rotacion")
    assert len(filtrada.data) < len(figura.data)
    assert plano_2d(local, solucion["posiciones"], solucion["ubicaciones"], "rotacion").data
