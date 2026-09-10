"""
Capa de retrieval: dada una consulta, recupera los chunks más relevantes desde
el índice Atlas Vector Search y arma el bloque de contexto para el LLM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from rag import config, vectorstore
from rag.embeddings import get_embeddings

logger = logging.getLogger(__name__)


@dataclass
class Fragmento:
    texto: str
    fuente: str
    score: float
    chunk_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "texto": self.texto,
            "fuente": self.fuente,
            "score": round(self.score, 4),
            "chunk_index": self.chunk_index,
        }


class Retriever:
    def __init__(self, top_k: int | None = None) -> None:
        self.top_k = top_k or config.TOP_K
        self.embeddings = get_embeddings()

    def buscar(self, consulta: str, top_k: int | None = None) -> list[Fragmento]:
        if not consulta or not consulta.strip():
            return []
        vector = self.embeddings.embed_query(consulta)
        docs = vectorstore.vector_search(vector, top_k=top_k or self.top_k)
        fragmentos = [
            Fragmento(
                texto=d.get("texto", ""),
                fuente=d.get("fuente", "desconocida"),
                score=float(d.get("score", 0.0)),
                chunk_index=d.get("chunk_index"),
            )
            for d in docs
        ]
        logger.info("Retrieval '%s...': %d fragmentos.", consulta[:50], len(fragmentos))
        return fragmentos

    @staticmethod
    def construir_contexto(fragmentos: list[Fragmento]) -> str:
        if not fragmentos:
            return "No se encontró contexto relevante en la base de conocimiento."
        bloques = [f"[Fuente {i}: {f.fuente}]\n{f.texto}" for i, f in enumerate(fragmentos, start=1)]
        return "\n\n".join(bloques)


_singleton: Retriever | None = None


def get_retriever() -> Retriever:
    global _singleton
    if _singleton is None:
        _singleton = Retriever()
    return _singleton
