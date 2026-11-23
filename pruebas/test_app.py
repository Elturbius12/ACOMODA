"""Prueba de la aplicación completa (Streamlit AppTest): recorre los 8 pasos (v3) con el caso real y el
local de ejemplo, comprueba las compuertas, el botón «Corregir», escenarios, sensibilidad y entregables."""

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from conftest import CATALOGO_REAL, VENTAS_REAL

APP = str(Path(__file__).resolve().parent.parent / "app.py")
pytestmark = pytest.mark.skipif(not CATALOGO_REAL.exists() or VENTAS_REAL is None, reason="Faltan los Excel del caso real")


def _pasos(at):
    """Botones de la barra lateral que representan pasos: {número: botón}."""
    return {int(m.group(1)): b for b in at.sidebar.button if (m := re.match(r"^\S+ (\d)\. ", b.label))}


def _sin_errores(at):
    assert not at.exception, [e.value for e in at.exception]


def _boton(at, texto):
    return next(b for b in at.button if b.label.startswith(texto))


def _casilla(at, texto):
    return next(c for c in at.checkbox if c.label.startswith(texto))


def _confirmar(at, texto_casilla):
    _casilla(at, texto_casilla).check().run()
    _boton(at, "Confirmar y continuar").click().run()
    _sin_errores(at)


def test_recorrido_completo_de_la_app():
    at = AppTest.from_file(APP, default_timeout=900).run()
    _sin_errores(at)
    # Compuerta: sin catálogo confirmado, los pasos 2 a 8 están bloqueados
    pasos = _pasos(at)
    assert len(pasos) == 8 and not pasos[1].disabled
    assert all(pasos[n].disabled and pasos[n].label.startswith("🔒") for n in range(2, 9))
    _boton(at, "Usar el catálogo de prueba").click().run()
    _sin_errores(at)
    # Sin responsable no se puede confirmar
    _casilla(at, "Confirmo que los datos del catálogo").check().run()
    assert _boton(at, "Confirmar y continuar").disabled
    at.sidebar.text_input[0].set_value("Responsable de prueba").run()
    _boton(at, "Confirmar y continuar").click().run()
    _sin_errores(at)

    # Paso 2: local de ejemplo, corrección y confirmación
    next(r for r in at.radio if r.label.startswith("¿Cómo entregará")).set_value("D. Local de ejemplo (EJEMPLO, NO ES REAL)").run()
    _boton(at, "Cargar el local de ejemplo").click().run()
    _boton(at, "Dimensiones").click().run()
    _boton(at, "Aplicar corrección").click().run()
    _sin_errores(at)
    assert _boton(at, "Confirmo que el local está bien interpretado").disabled
    for casilla in at.checkbox:
        if casilla.label.startswith("¿"):
            casilla.check()
    at.run()
    _boton(at, "Confirmo que el local está bien interpretado").click().run()
    _sin_errores(at)

    # Paso 3: ventas
    _boton(at, "Usar el reporte de prueba").click().run()
    _boton(at, "Aplicar equivalencias").click().run()
    _sin_errores(at)
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Productos del catálogo con ventas"] == "740"
    _casilla(at, "¿La fecha").check()
    _casilla(at, "Las cantidades").check()
    _confirmar(at, "Confirmo el reporte")

    # Paso 4: normativas (cambiar el límite de peso queda registrado)
    limite = next(s for s in at.selectbox if s.label.startswith("limite_peso_kg"))
    limite.set_value(15).run()
    _sin_errores(at)
    assert any("Se registraron" in w.value for w in at.warning)
    _confirmar(at, "Confirmo las normativas")

    # Paso 5: diseñar y optimizar (el programa diseña los racks; propuesta rápida y luego completa)
    _boton(at, "⚡ Propuesta rápida").click().run()
    _sin_errores(at)
    assert {m.label: m.value for m in at.metric}["Estado del solver"].startswith("Propuesta rápida")
    _boton(at, "Calcular propuesta completa").click().run()
    _sin_errores(at)
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Estado del solver"] in ("Óptimo", "Factible (se detuvo por tiempo)")
    assert int(metricas["Módulos nuevos"]) > 0
    _confirmar(at, "Acepto esta propuesta")

    # Paso 6: cada vista se calcula al abrirla; escenarios y sensibilidad con tiempos cortos
    ver = next(r for r in at.radio if r.label == "Ver")
    ver.set_value("Escenarios").run()
    next(c for c in at.number_input if c.label.startswith("Tiempo límite por escenario")).set_value(5).run()
    _boton(at, "Calcular escenarios").click().run()
    _sin_errores(at)
    next(r for r in at.radio if r.label == "Ver").set_value("Sensibilidad").run()
    next(c for c in at.number_input if c.label.startswith("Tiempo límite por corrida")).set_value(5).run()
    _boton(at, "Calcular sensibilidad").click().run()
    _sin_errores(at)
    next(r for r in at.radio if r.label == "Ver").set_value("Vista 3D").run()
    _boton(at, "Preparar visual_3d.html").click().run()
    _sin_errores(at)
    next(r for r in at.radio if r.label == "Ver").set_value("Reporte normativo").run()
    _sin_errores(at)
    _confirmar(at, "He revisado los resultados")

    # Paso 7: evidencia con pedidos reales
    _boton(at, "Calcular la evidencia").click().run()
    _sin_errores(at)
    # Lo primero que se ve es la decisión, clara y sin estadística
    metricas = {m.label: m.value for m in at.metric}
    assert {"Recorrido por pedido", "Ahorro al mes", "Inversión", "Se paga en"} <= set(metricas)
    assert any("Decisión" in m.value for m in at.markdown)
    assert "Valor p" not in metricas
    # El detalle técnico aparece solo al pedirlo
    at.toggle(key="ver_detalle_evidencia").set_value(True).run()
    _sin_errores(at)
    metricas = {m.label: m.value for m in at.metric}
    assert "Valor p" in metricas and "Prueba" in metricas
    assert any("Límites de la evidencia" in m.value for m in at.markdown)
    assert any("Veredicto" in e.value for e in list(at.success) + list(at.warning) + list(at.error))
    _confirmar(at, "Revisé la evidencia")

    # Paso 8: costeo, informe gerencial, paquete del artículo y entregables
    assert any(m.label == "Inversión total" for m in at.metric)
    _boton(at, "📄 Exportar informe gerencial").click().run()
    _sin_errores(at)
    _boton(at, "Preparar los archivos del artículo").click().run()
    _sin_errores(at)
    _boton(at, "📦 Generar paquete del artículo").click().run()
    _sin_errores(at)
    _boton(at, "Generar todos los entregables").click().run()
    _sin_errores(at)
    etiquetas = [d.label for d in at.get("download_button")]
    for esperado in ("propuesta_distribucion.xlsx", "visual_3d.html", "informe_gerencial.docx", "informe_gerencial.xlsx",
                     "Paquete del artículo", "Lista de compra", "Borrador del artículo (Word)"):
        assert any(esperado in e for e in etiquetas), esperado
    _confirmar(at, "Entregables revisados")
    assert all(b.label.startswith(("✅", "⚠️")) for b in _pasos(at).values())
