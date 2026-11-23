"""Fase 1: plantillas descargables y validación celda por celda."""

import io

from openpyxl import load_workbook

from modulos import plantillas
from modulos.cargar_catalogo import cargar_catalogo
from modulos.cargar_local import leer_plantilla_local, local_de_ejemplo


def _llenar(contenido, hoja, filas):
    libro = load_workbook(io.BytesIO(contenido))
    datos = libro[hoja]
    encabezados = [c.value for c in datos[1]]
    for numero, fila in enumerate(filas, start=2):
        for clave, valor in fila.items():
            datos.cell(row=numero, column=encabezados.index(clave) + 1, value=valor)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def test_las_tres_plantillas_tienen_hojas_y_version():
    for tipo, generar, hoja in (("catalogo", plantillas.generar_plantilla_catalogo, "DATOS"),
                                ("ventas", plantillas.generar_plantilla_ventas, "DATOS"),
                                ("local", plantillas.generar_plantilla_local, "PREFERENCIAS_Y_PRESUPUESTO")):
        libro = load_workbook(io.BytesIO(generar()))
        assert "INSTRUCCIONES" in libro.sheetnames and hoja in libro.sheetnames
        assert any(n.startswith("EJEMPLO") for n in libro.sheetnames)
        assert libro["INSTRUCCIONES"]["B2"].value == plantillas.VERSION_PLANTILLA
        assert libro["INSTRUCCIONES"]["B3"].value == tipo
        if tipo != "ventas":  # la plantilla de ventas no tiene columnas con lista
            assert libro[hoja].data_validations.dataValidation, "faltan listas desplegables"


def test_error_plantado_se_reporta_con_fila_y_columna():
    contenido = _llenar(plantillas.generar_plantilla_catalogo(), "DATOS", [
        {"codigo_barras": "7750000000011", "producto": "PRUEBA UNO", "largo_cm": 10, "ancho_cm": 5, "alto_cm": 20, "peso_kg": 0.5},
        {"codigo_barras": "7750000000028", "producto": "PRUEBA DOS", "largo_cm": 10, "ancho_cm": 5, "alto_cm": -3, "peso_kg": 0.5},
    ])
    resultado = plantillas.validar_plantilla(contenido, "catalogo")
    assert resultado["rechazada"] is None
    errores = resultado["errores"]
    assert len(errores) == 1
    assert errores[0]["fila"] == 3 and errores[0]["columna"] == "alto_cm"
    assert "mayor que 0" in errores[0]["mensaje"]
    texto = plantillas.describir_error(errores[0])
    assert "fila 3" in texto and "alto_cm" in texto
    # El archivo de errores pinta la celda en rojo
    marcado = load_workbook(io.BytesIO(plantillas.archivo_con_errores(contenido, errores)))["DATOS"]
    columna = [c.value for c in marcado[1]].index("alto_cm") + 1
    assert marcado.cell(row=3, column=columna).fill.fgColor.rgb.endswith(plantillas.COLOR_ERROR)


def test_plantilla_llena_se_carga_como_catalogo_real():
    contenido = _llenar(plantillas.generar_plantilla_catalogo(), "DATOS", [
        {"codigo_barras": "7750000000011", "producto": "PRUEBA UNO", "categoria": "HOGAR", "precio_venta": 5,
         "largo_cm": 10, "ancho_cm": 5, "alto_cm": 20, "peso_kg": 0.5},
        {"codigo_barras": "7750000000028", "producto": "GASEOSA 500ML", "precio_venta": 2},
    ])
    resultado = cargar_catalogo(contenido, "plantilla_catalogo.xlsx")
    catalogo = resultado["catalogo"].set_index("codigo_barras")
    assert catalogo.at["7750000000011", "origen_medidas"] == "real"
    assert catalogo.at["7750000000028", "origen_medidas"] == "estimado"


def test_version_antigua_se_rechaza():
    libro = load_workbook(io.BytesIO(plantillas.generar_plantilla_catalogo()))
    libro["INSTRUCCIONES"]["B2"] = "1.0"
    salida = io.BytesIO()
    libro.save(salida)
    resultado = plantillas.validar_plantilla(salida.getvalue(), "catalogo")
    assert resultado["rechazada"] and "versión antigua" in resultado["rechazada"]


def test_plantilla_de_otro_tipo_se_rechaza():
    resultado = plantillas.validar_plantilla(plantillas.generar_plantilla_ventas(), "catalogo")
    assert resultado["rechazada"]


def test_local_ida_y_vuelta_por_plantilla():
    local = local_de_ejemplo()
    leido, validacion = leer_plantilla_local(plantillas.generar_plantilla_local(local))
    assert not validacion["errores"], validacion["errores"]
    assert len(leido["estantes"]) == len(local["estantes"])
    assert leido["largo_m"] == local["largo_m"] and leido["altura_libre_m"] == local["altura_libre_m"]
    assert {o["id"] for o in leido["obstaculos"]} == {o["id"] for o in local["obstaculos"]}


def test_plantilla_prellenada_ordena_por_importancia():
    import pandas as pd
    from conftest import catalogo_sintetico
    catalogo = catalogo_sintetico([{"producto": "A"}, {"producto": "B"}, {"producto": "C"}])
    catalogo["origen_medidas"] = "estimado"
    importancia = pd.DataFrame({"id_producto": catalogo["id_producto"], "ventas_soles": [10, 500, 90]})
    libro = load_workbook(io.BytesIO(plantillas.generar_plantilla_catalogo(catalogo, importancia)))
    datos = libro["DATOS"]
    columna = [c.value for c in datos[1]].index("codigo_barras") + 1
    assert [datos.cell(row=f, column=columna).value for f in (2, 3, 4)] == list(catalogo["codigo_barras"].iloc[[1, 2, 0]])
    assert "80 %" in " ".join(str(c.value) for c in libro["INSTRUCCIONES"]["A"] if c.value)
    columna_largo = [c.value for c in datos[1]].index("largo_cm") + 1
    assert datos.cell(row=2, column=columna_largo).value is None  # lo estimado no se copia como real
