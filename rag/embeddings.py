"""
Embeddings locales con sentence-transformers.

A diferencia de una solución basada en OpenAI, aquí los embeddings se calculan
en el propio equipo/contenedor: no se necesita API key ni hay costo por token
de embeddings. El modelo por defecto es multilingüe (español).

Detalle importante de los modelos E5: esperan un prefijo distinto para las
consultas ("query: ") y para los documentos ("passage: "). Respetarlo mejora
notablemente la calidad del retrieval; por eso el cliente distingue ambos
casos en vez de codificar todo igual.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from rag import config

logger = logging.getLogger(__name__)


class LocalEmbeddings:
    def __init__(self, model_name: str | None = None) -> None:
        # Import perezoso: sentence-transformers (y torch) son pesados; así los
        # módulos que sólo importan tipos no pagan el costo de cargarlos.
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name or config.EMBEDDING_MODEL
        logger.info("Cargando modelo de embeddings local: %s", self.model_name)
        self.model = SentenceTransformer(self.model_name)
        self._is_e5 = "e5" in self.model_name.lower()

    def _con_prefijo(self, textos: list[str], tipo: str) -> list[str]:
        if not self._is_e5:
            return textos
        prefijo = "query: " if tipo == "query" else "passage: "
        return [prefijo + t for t in textos]

    def embed_documents(self, textos: list[str]) -> list[list[float]]:
        """Embeddings para documentos/chunks (se guardan en Mongo)."""
        preparados = self._con_prefijo([t.strip() for t in textos], "passage")
        vectores = self.model.encode(
            preparados, normalize_embeddings=True, convert_to_numpy=True
        )
        return [v.tolist() for v in vectores]

    def embed_query(self, texto: str) -> list[float]:
        """Embedding para una consulta del usuario (tiempo de retrieval)."""
        preparado = self._con_prefijo([texto.strip()], "query")
        vector = self.model.encode(
            preparado, normalize_embeddings=True, convert_to_numpy=True
        )[0]
        return vector.tolist()

    @property
    def dim(self) -> int:
        return int(self.model.get_sentence_embedding_dimension())


@lru_cache(maxsize=1)
def get_embeddings() -> LocalEmbeddings:
    return LocalEmbeddings()
