"""Guarda el progreso de cada proyecto en el servidor para que recargar la página (F5, Ctrl+Shift+R) no lo borre.

Cada proyecto tiene un código que va en el enlace (…/?p=CODIGO). Mientras el usuario use ese enlace, al recargar se
recupera todo: archivos cargados, confirmaciones, diseño, evidencia y costeo. Quien tenga el enlace ve el proyecto,
por eso la app recomienda no compartirlo.

La carpeta se elige con la variable de entorno ACOMODA_DATOS (en Railway, un volumen montado, p. ej. /data).
"""

import os
import pickle
import re
import secrets
import shutil
import time
from pathlib import Path

import pandas as pd

from modulos.comun import CARPETA_PROCESADOS

CARPETA_PROYECTOS = Path(os.environ.get("ACOMODA_DATOS") or CARPETA_PROCESADOS) / "proyectos"
CARPETA_PROYECTOS.mkdir(parents=True, exist_ok=True)
DIAS_CONSERVAR = int(os.environ.get("ACOMODA_DIAS_CONSERVAR", "60"))
_PATRON = re.compile(r"^[a-z0-9]{8,32}$")
# Objetos grandes: se guardan en su propio archivo y solo cuando cambian (así guardar no hace lenta la app)
_GRANDES = (pd.DataFrame, pd.Series)


def codigo_valido(codigo):
    return bool(codigo) and bool(_PATRON.match(str(codigo)))


def nuevo_codigo():
    return secrets.token_hex(6)


def carpeta(codigo):
    return CARPETA_PROYECTOS / codigo


def existe(codigo):
    return codigo_valido(codigo) and (carpeta(codigo) / "estado.pkl").exists()


def guardar(codigo, estado, firmas):
    """Guarda `estado` (dict). `firmas` es un dict que se reutiliza entre ejecuciones para no reescribir lo que no cambió."""
    if not codigo_valido(codigo):
        return
    destino = carpeta(codigo)
    destino.mkdir(parents=True, exist_ok=True)
    pequenos, grandes = {}, []
    for clave, valor in estado.items():
        if _es_grande(valor):
            grandes.append(clave)
            firma = (id(valor), len(valor) if hasattr(valor, "__len__") else 0)
            archivo = destino / f"g_{_nombre(clave)}.pkl"
            if firmas.get(clave) != firma or not archivo.exists():
                if _volcar(archivo, valor):
                    firmas[clave] = firma
        else:
            try:
                # Cada valor se guarda por separado: si uno no se puede recuperar, los demás sí
                datos = pickle.dumps(_plano(valor), protocol=pickle.HIGHEST_PROTOCOL)
                pickle.loads(datos)
                pequenos[clave] = datos
            except Exception:  # objetos que no se pueden guardar (hilos, archivos abiertos): se omiten
                pass
    pequenos["__grandes__"] = grandes
    _volcar(destino / "estado.pkl", pequenos)


def cargar(codigo):
    """Devuelve el dict guardado, o None si no existe o está dañado."""
    if not existe(codigo):
        return None
    origen = carpeta(codigo)
    try:
        with open(origen / "estado.pkl", "rb") as archivo:
            estado = pickle.load(archivo)
    except Exception:
        return None
    grandes = estado.pop("__grandes__", [])
    recuperado = {}
    for clave, datos in estado.items():
        try:
            recuperado[clave] = pickle.loads(datos)
        except Exception:
            pass
    estado = recuperado
    for clave in grandes:
        try:
            with open(origen / f"g_{_nombre(clave)}.pkl", "rb") as archivo:
                estado[clave] = pickle.load(archivo)
        except Exception:
            pass
    return estado


def borrar(codigo):
    if codigo_valido(codigo):
        shutil.rmtree(carpeta(codigo), ignore_errors=True)


def limpiar_antiguos():
    """Borra proyectos que nadie abrió en DIAS_CONSERVAR días (para no llenar el disco del servidor)."""
    limite = time.time() - DIAS_CONSERVAR * 86400
    for proyecto in CARPETA_PROYECTOS.iterdir():
        try:
            if proyecto.is_dir() and (proyecto / "estado.pkl").stat().st_mtime < limite:
                shutil.rmtree(proyecto, ignore_errors=True)
        except OSError:
            pass


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


def _volcar(ruta, valor):
    temporal = ruta.with_suffix(".tmp")
    try:
        with open(temporal, "wb") as archivo:
            pickle.dump(valor, archivo, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temporal, ruta)  # escritura atómica: si el servidor se corta a la mitad, no queda un archivo roto
        return True
    except Exception:
        temporal.unlink(missing_ok=True)
        return False
