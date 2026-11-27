"""Trazas locales por turno. Solo se persisten campos técnicos construidos aquí."""

import json
import logging
import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter_ns, thread_time_ns
from uuid import uuid4

from rag import config

logger = logging.getLogger(__name__)
NOMBRES = frozenset(
    (
        "buscar_material",
        "buscar_en_web",
        "listar_tareas",
        "estado_asistencia",
        "crear_tarea",
        "mover_tarea",
        "registrar_asistencia",
        "planificar_semana",
    )
)


def clase_error(exc):
    if isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower():
        return "timeout"
    if getattr(exc, "status_code", None) == 429:
        return "cuota"
    if isinstance(exc, ImportError):
        return "dependencia"
    return "excepcion"


class Traza:
    def __init__(self):
        self.inicio = perf_counter_ns()
        self.cpu = thread_time_ns()
        self.datos = {
            "id": uuid4().hex,
            "utc": datetime.now(UTC).isoformat(),
            "estado": "ok",
            "eventos": [],
            "tokens": None,
            "pasos": 0,
        }

    @contextmanager
    def tramo(self, etapa, paso=0, herramienta=None):
        inicio = perf_counter_ns()
        evento = {
            "etapa": etapa,
            "paso": paso,
            "estado": "ok",
            "inicio_ms": round((inicio - self.inicio) / 1e6, 4),
        }
        if herramienta is not None:
            evento["herramienta"] = (
                herramienta if herramienta in NOMBRES else "desconocida"
            )
        self.datos["eventos"].append(evento)
        try:
            yield evento
        except Exception as exc:
            evento["estado"] = clase_error(exc)
            raise
        finally:
            evento["ms"] = round((perf_counter_ns() - inicio) / 1e6, 4)

    def cerrar(self):
        self.datos["ms"] = round((perf_counter_ns() - self.inicio) / 1e6, 4)
        self.datos["cpu_ms"] = round((thread_time_ns() - self.cpu) / 1e6, 4)
        return self.datos


def _corte():
    return (datetime.now(UTC) - timedelta(days=config.OBS_RETENCION_DIAS)).isoformat()


def guardar(traza):
    """Una transacción por turno. Un fallo del disco no modifica la respuesta."""
    if not config.OBS_ACTIVA:
        return
    try:
        ruta = Path(config.OBS_DB)
        ruta.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with closing(sqlite3.connect(ruta, timeout=0.5)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS trazas (id TEXT PRIMARY KEY, utc TEXT, datos TEXT)"
            )
            db.execute("CREATE INDEX IF NOT EXISTS trazas_utc ON trazas(utc)")
            db.execute("DELETE FROM trazas WHERE utc < ?", (_corte(),))
            db.execute(
                "INSERT INTO trazas VALUES (?,?,?)",
                (traza["id"], traza["utc"], json.dumps(traza)),
            )
    except (OSError, sqlite3.Error):
        logger.warning("No se pudo guardar la traza local.")


def leer():
    ruta = Path(config.OBS_DB)
    if not ruta.is_file():
        return []
    with closing(sqlite3.connect(ruta, timeout=2)) as db, db:
        db.execute("DELETE FROM trazas WHERE utc < ?", (_corte(),))
        return [
            json.loads(fila[0])
            for fila in db.execute("SELECT datos FROM trazas ORDER BY utc")
        ]
