"""
Fuente de información EXTERNA: búsqueda web.

La rúbrica exige integrar fuentes internas (los PDFs indexados en Mongo) y
externas. Este módulo aporta la parte externa mediante una búsqueda web sin
API key (DuckDuckGo, vía el paquete `ddgs` — antes `duckduckgo_search`).

Es "fail-soft": si el paquete no está instalado o no hay red, devuelve una
lista vacía y el pipeline sigue funcionando sólo con las fuentes internas.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ResultadoWeb:
    titulo: str
    url: str
    texto: str

    def to_dict(self) -> dict:
        return {"fuente": f"web: {self.titulo}".strip(), "url": self.url, "texto": self.texto, "score": None}


def _cargar_ddgs():
    try:
        from ddgs import DDGS  # nombre nuevo del paquete
        return DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # nombre antiguo
            return DDGS
        except ImportError:
            logger.warning("Paquete de búsqueda web no instalado (ddgs); se omite la fuente externa.")
            return None


def buscar_web(consulta: str, k: int = 3) -> list[ResultadoWeb]:
    if not consulta or not consulta.strip():
        return []
    DDGS = _cargar_ddgs()
    if DDGS is None:
        return []
    try:
        with DDGS() as ddgs:
            crudos = list(ddgs.text(consulta, max_results=k))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falló la búsqueda web (fuente externa): %s", exc)
        return []

    resultados = []
    for r in crudos:
        resultados.append(
            ResultadoWeb(
                titulo=(r.get("title") or "").strip(),
                url=(r.get("href") or r.get("url") or "").strip(),
                texto=(r.get("body") or "").strip(),
            )
        )
    logger.info("Fuente externa: %d resultados web para '%s...'", len(resultados), consulta[:50])
    return resultados
