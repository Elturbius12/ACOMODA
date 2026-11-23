"""Análisis descriptivo de ventas (no es otro modelo): rotación, ABC, margen,
estacionalidad, productos vendidos juntos y lenta salida."""

from collections import Counter
from itertools import combinations

import numpy as np
import pandas as pd

from modulos.comun import cargar_ajustes

SIN_ROTACION = "SIN ROTACIÓN"


def filtrar_periodo(ventas, desde=None, hasta=None):
    datos = ventas
    if desde is not None:
        datos = datos[datos["fecha_hora"] >= pd.Timestamp(desde)]
    if hasta is not None:
        datos = datos[datos["fecha_hora"] < pd.Timestamp(hasta) + pd.Timedelta(days=1)]
    return datos


def dias_del_periodo(ventas, desde=None, hasta=None):
    if desde is not None and hasta is not None:
        return max(1, (pd.Timestamp(hasta) - pd.Timestamp(desde)).days + 1)
    if not len(ventas):
        return 1
    return max(1, (ventas["fecha_hora"].max().normalize() - ventas["fecha_hora"].min().normalize()).days + 1)


def clasificar_abc(tabla, corte_a=None, corte_b=None):
    """Agrega participacion, acumulado y clase_abc según ventas en soles (A 80 %, B 15 %, C 5 %)."""
    ajustes = cargar_ajustes()["abc"]
    corte_a = ajustes["corte_a"] if corte_a is None else corte_a
    corte_b = ajustes["corte_b"] if corte_b is None else corte_b
    tabla = tabla.sort_values("ventas_soles", ascending=False).reset_index(drop=True)
    total = tabla["ventas_soles"].clip(lower=0).sum()
    tabla["participacion"] = tabla["ventas_soles"].clip(lower=0) / total if total > 0 else 0.0
    tabla["acumulado"] = tabla["participacion"].cumsum()
    acumulado = tabla["acumulado"] - 1e-9
    primero = tabla.index == 0  # el producto que más vende siempre es A
    clase = np.where((acumulado <= corte_a) | primero, "A", np.where(acumulado <= corte_b, "B", "C"))
    tabla["clase_abc"] = np.where(tabla["unidades"] > 0, clase, SIN_ROTACION)
    return tabla


def resumen_por_producto(ventas, catalogo, desde=None, hasta=None, base="periodo", meses_recientes=3):
    """Una fila por producto del catálogo (incluye los que no vendieron)."""
    periodo = filtrar_periodo(ventas, desde, hasta)
    dias = dias_del_periodo(periodo, desde, hasta)
    agrupado = periodo.groupby("id_producto").agg(
        unidades=("cantidad", "sum"), ventas_soles=("total", "sum"), lineas=("cantidad", "size"),
        comprobantes=("comprobante", "nunique"), ultima_venta=("fecha_hora", "max"),
        costo_ventas=("costo", "mean")).reset_index()
    if base == "recientes" and len(periodo):
        fin = periodo["fecha_hora"].max()
        inicio = fin - pd.DateOffset(months=meses_recientes)
        recientes = periodo[periodo["fecha_hora"] > inicio]
        dias_recientes = max(1, (fin.normalize() - inicio.normalize()).days)
        rotacion = (recientes.groupby("id_producto")["cantidad"].sum() / dias_recientes).rename("rotacion_diaria")
    else:
        rotacion = (agrupado.set_index("id_producto")["unidades"] / dias).rename("rotacion_diaria")
    tabla = catalogo[["id_producto", "producto", "categoria", "precio_compra", "precio_venta", "stock"]].merge(
        agrupado, on="id_producto", how="left").merge(rotacion.reset_index(), on="id_producto", how="left")
    for columna in ("unidades", "ventas_soles", "lineas", "comprobantes", "rotacion_diaria"):
        tabla[columna] = tabla[columna].fillna(0.0)
    tabla["rotacion_diaria"] = tabla["rotacion_diaria"].clip(lower=0)
    costo = tabla["precio_compra"].where(tabla["precio_compra"].fillna(0) > 0, tabla["costo_ventas"])
    precio = tabla["precio_venta"].where(tabla["precio_venta"].fillna(0) > 0,
                                         tabla["ventas_soles"] / tabla["unidades"].replace(0, np.nan))
    tabla["margen_unitario"] = (precio - costo).fillna(0.0)
    tabla["margen_diario"] = tabla["margen_unitario"].clip(lower=0) * tabla["rotacion_diaria"]
    tabla = clasificar_abc(tabla)
    con_ventas = tabla[tabla["unidades"] > 0]
    umbral_lento = con_ventas["rotacion_diaria"].quantile(0.10) if len(con_ventas) else 0
    fecha_fin = periodo["fecha_hora"].max() if len(periodo) else pd.Timestamp.now()
    sin_venta_reciente = (fecha_fin - tabla["ultima_venta"]).dt.days > 60
    tabla["lenta_salida"] = (tabla["unidades"] > 0) & ((tabla["rotacion_diaria"] <= umbral_lento) | sin_venta_reciente.fillna(False))
    tabla["dias_periodo"] = dias
    return tabla.drop(columns=["costo_ventas"])


def ventas_por_mes(ventas):
    if not len(ventas):
        return pd.DataFrame(columns=["mes", "unidades", "ventas_soles", "comprobantes"])
    tabla = ventas.assign(mes=ventas["fecha_hora"].dt.to_period("M").astype(str)).groupby("mes").agg(
        unidades=("cantidad", "sum"), ventas_soles=("total", "sum"), comprobantes=("comprobante", "nunique")).reset_index()
    promedio = tabla["ventas_soles"].mean()
    tabla["indice_estacional"] = (tabla["ventas_soles"] / promedio).round(2) if promedio else 1.0
    return tabla


def ventas_por_unidad_tiempo(ventas, unidad="M"):
    """unidad: 'D' día, 'W' semana, 'M' mes."""
    if not len(ventas):
        return pd.DataFrame(columns=["periodo", "ventas_soles"])
    regla = {"D": "D", "W": "W-MON", "M": "MS"}[unidad]
    serie = ventas.set_index("fecha_hora")["total"].resample(regla).sum()
    return serie.rename("ventas_soles").reset_index().rename(columns={"fecha_hora": "periodo"})


def pares_comprobante(ventas, maximo=30, max_lineas=30):
    """Pares de productos que aparecen juntos en un mismo comprobante (más frecuentes primero)."""
    contador = Counter()
    if not len(ventas):
        return pd.DataFrame(columns=["id_a", "id_b", "veces"])
    for _, productos in ventas.groupby("comprobante")["id_producto"]:
        unicos = sorted(set(productos))
        if 2 <= len(unicos) <= max_lineas:
            contador.update(combinations(unicos, 2))
    filas = [{"id_a": a, "id_b": b, "veces": n} for (a, b), n in contador.most_common(maximo)]
    return pd.DataFrame(filas, columns=["id_a", "id_b", "veces"])


def estadisticas_pedidos(ventas, dias):
    """Líneas promedio por pedido y pedidos por día (para el tiempo por pedido)."""
    if not len(ventas):
        return {"lineas_por_pedido": 1.0, "pedidos_por_dia": 0.0}
    por_pedido = ventas.groupby("comprobante")["id_producto"].nunique()
    return {"lineas_por_pedido": round(float(por_pedido.mean()), 2),
            "pedidos_por_dia": round(len(por_pedido) / max(dias, 1), 2)}
