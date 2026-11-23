"""Guarda el progreso de cada proyecto en el servidor para que recargar la página (F5, Ctrl+Shift+R) no lo borre.

Cada proyecto tiene un código que va en el enlace (…/?p=CODIGO). Mientras el usuario use ese enlace, al recargar se
recupera todo: archivos cargados, confirmaciones, diseño, evidencia y costeo. Quien tenga el enlace ve el proyecto,
por eso la app recomienda no compartirlo.

Dónde se guarda:
- Si existe la variable DATABASE_URL (Postgres de Render u otro), en la tabla acomoda_proyectos.
- Si no, en una carpeta (variable ACOMODA_DATOS; por defecto datos_procesados/proyectos).
"""

import os
import pickle
import re
import secrets
import shutil
import time
import zlib
from pathlib import Path

import pandas as pd

from modulos.comun import CARPETA_PROCESADOS

CARPETA_PROYECTOS = Path(os.environ.get("ACOMODA_DATOS") or CARPETA_PROCESADOS) / "proyectos"
CARPETA_PROYECTOS.mkdir(parents=True, exist_ok=True)
DIAS_CONSERVAR = int(os.environ.get("ACOMODA_DIAS_CONSERVAR", "60"))
_PATRON = re.compile(r"^[a-z0-9]{8,32}$")
# Objetos grandes: se guardan aparte y solo cuando cambian (así guardar no hace lenta la app)
_GRANDES = (pd.DataFrame, pd.Series)


def codigo_valido(codigo):
    return bool(codigo) and bool(_PATRON.match(str(codigo)))


def nuevo_codigo():
    return secrets.token_hex(6)


def carpeta(codigo):
    return CARPETA_PROYECTOS / codigo


# --------------------------------------------------------------------------------------
# Dónde se guarda: Postgres si existe DATABASE_URL (Render, Railway…); si no, una carpeta en disco
# --------------------------------------------------------------------------------------

def _url_postgres():
    return os.environ.get("DATABASE_URL", "").strip()


_conexion = None


def _pg():
    """Conexión única a Postgres (se reabre sola si se cortó; Render free duerme la app y corta conexiones)."""
    global _conexion
    import psycopg
    if _conexion is None or _conexion.closed or _conexion.broken:
        _conexion = psycopg.connect(_url_postgres(), autocommit=True, connect_timeout=15)
        _conexion.execute("""CREATE TABLE IF NOT EXISTS acomoda_proyectos (
                               codigo TEXT NOT NULL, nombre TEXT NOT NULL, datos BYTEA NOT NULL,
                               actualizado TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (codigo, nombre))""")
    return _conexion


def _sql(consulta, parametros=(), devolver=False):
    global _conexion
    for intento in range(2):
        try:
            with _pg().cursor() as cursor:
                cursor.execute(consulta, parametros)
                return cursor.fetchall() if devolver else None
        except Exception:
            _conexion = None
            if intento:
                raise


def _escribir(codigo, nombre, datos):
    datos = zlib.compress(datos, 1)  # la base gratuita tiene poco espacio: se comprime
    if _url_postgres():
        _sql("""INSERT INTO acomoda_proyectos (codigo, nombre, datos, actualizado) VALUES (%s, %s, %s, now())
                ON CONFLICT (codigo, nombre) DO UPDATE SET datos = EXCLUDED.datos, actualizado = now()""",
             (codigo, nombre, datos))
        return
    destino = carpeta(codigo)
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"{nombre}.pkl"
    temporal = ruta.with_suffix(".tmp")
    temporal.write_bytes(datos)
    os.replace(temporal, ruta)  # escritura atómica: si el servidor se corta a la mitad, no queda un archivo roto


def _leer(codigo, nombre):
    if _url_postgres():
        filas = _sql("SELECT datos FROM acomoda_proyectos WHERE codigo = %s AND nombre = %s", (codigo, nombre), True)
        datos = bytes(filas[0][0]) if filas else None
    else:
        ruta = carpeta(codigo) / f"{nombre}.pkl"
        datos = ruta.read_bytes() if ruta.exists() else None
    return None if datos is None else zlib.decompress(datos)


def existe(codigo):
    if not codigo_valido(codigo):
        return False
    if _url_postgres():
        try:
            return bool(_sql("SELECT 1 FROM acomoda_proyectos WHERE codigo = %s AND nombre = 'estado'", (codigo,), True))
        except Exception:
            return False
    return (carpeta(codigo) / "estado.pkl").exists()


def guardar(codigo, estado, firmas):
    """Guarda `estado` (dict). `firmas` se reutiliza entre ejecuciones para no reescribir lo grande que no cambió."""
    if not codigo_valido(codigo):
        return
    pequenos, grandes = {}, []
    for clave, valor in estado.items():
        if _es_grande(valor):
            grandes.append(clave)
            firma = (id(valor), len(valor) if hasattr(valor, "__len__") else 0)
            if firmas.get(clave) != firma:
                try:
                    _escribir(codigo, f"g_{_nombre(clave)}", pickle.dumps(_plano(valor), protocol=pickle.HIGHEST_PROTOCOL))
                    firmas[clave] = firma
                except Exception:
                    pass
        else:
            try:
                # Cada valor se guarda por separado: si uno no se puede recuperar, los demás sí
                datos = pickle.dumps(_plano(valor), protocol=pickle.HIGHEST_PROTOCOL)
                pickle.loads(datos)
                pequenos[clave] = datos
            except Exception:  # objetos que no se pueden guardar (hilos, archivos abiertos): se omiten
                pass
    pequenos["__grandes__"] = grandes
    datos = pickle.dumps(pequenos, protocol=pickle.HIGHEST_PROTOCOL)
    if firmas.get("__estado__") != hash(datos):  # no reescribir si nada cambió (ahorra tráfico a la base)
        _escribir(codigo, "estado", datos)
        firmas["__estado__"] = hash(datos)


def cargar(codigo):
    """Devuelve el dict guardado, o None si no existe o está dañado."""
    if not existe(codigo):
        return None
    try:
        estado = pickle.loads(_leer(codigo, "estado"))
    except Exception:
        return None
    grandes = estado.pop("__grandes__", [])
    recuperado = {}
    for clave, datos in estado.items():
        try:
            recuperado[clave] = pickle.loads(datos)
        except Exception:
            pass
    for clave in grandes:
        try:
            recuperado[clave] = pickle.loads(_leer(codigo, f"g_{_nombre(clave)}"))
        except Exception:
            pass
    return recuperado


def borrar(codigo):
    if not codigo_valido(codigo):
        return
    if _url_postgres():
        _sql("DELETE FROM acomoda_proyectos WHERE codigo = %s", (codigo,))
    else:
        shutil.rmtree(carpeta(codigo), ignore_errors=True)


def limpiar_antiguos():
    """Borra proyectos que nadie abrió en DIAS_CONSERVAR días (para no llenar el disco o la base)."""
    if _url_postgres():
        _sql("""DELETE FROM acomoda_proyectos WHERE codigo IN (SELECT codigo FROM acomoda_proyectos GROUP BY codigo
                HAVING max(actualizado) < now() - make_interval(days => %s))""", (DIAS_CONSERVAR,))
        return
    limite = time.time() - DIAS_CONSERVAR * 86400
    for proyecto in CARPETA_PROYECTOS.iterdir():
        try:
            if proyecto.is_dir() and (proyecto / "estado.pkl").stat().st_mtime < limite:
                shutil.rmtree(proyecto, ignore_errors=True)
        except OSError:
            pass


def donde_se_guarda():
    return "base de datos Postgres" if _url_postgres() else f"carpeta {CARPETA_PROYECTOS}"


def _es_grande(valor):
    if isinstance(valor, _GRANDES) or hasattr(valor, "to_plotly_json"):
        return True
    if isinstance(valor, (bytes, bytearray)):
        return len(valor) > 200_000
    if type(valor) is dict and valor:
        return any(isinstance(v, _GRANDES + (bytes, bytearray)) or hasattr(v, "to_plotly_json")
                   for v in list(valor.values())[:50])
    return False


def _plano(valor):
    """Los estados de widgets de Streamlit son dict de solo lectura que no se pueden volver a cargar: se copian como dict."""
    if isinstance(valor, dict) and type(valor) is not dict:
        return {k: _plano(v) for k, v in valor.items()}
    return valor


def _nombre(clave):
    return re.sub(r"[^A-Za-z0-9_]", "_", str(clave))[:80]
