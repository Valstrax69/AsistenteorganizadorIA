"""
Crea el índice de Atlas Vector Search sobre la colección `chunks`, necesario
para la búsqueda semántica (`$vectorSearch`).

Las dimensiones del índice se toman de config.EMBEDDING_DIM, de modo que
coincidan con el modelo de embeddings configurado. Si cambias de modelo (y por
lo tanto de dimensiones), borra el índice y vuelve a crearlo.

Uso:
    python -m scripts.create_index

Requiere un cluster de MongoDB Atlas con Atlas Vector Search (funciona en el
tier gratuito M0). No aplica a un MongoDB local.
"""

from __future__ import annotations

import logging
import time

from pymongo.operations import SearchIndexModel

from rag import config, vectorstore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def crear_indice() -> None:
    coleccion = vectorstore.get_collection(config.CHUNKS_COLLECTION)

    existentes = list(coleccion.list_search_indexes())
    if any(idx.get("name") == config.VECTOR_INDEX_NAME for idx in existentes):
        logger.info("El índice '%s' ya existe. No se crea de nuevo.", config.VECTOR_INDEX_NAME)
        return

    modelo = SearchIndexModel(
        name=config.VECTOR_INDEX_NAME,
        type="vectorSearch",
        definition={
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": config.EMBEDDING_DIM,
                    "similarity": "cosine",
                }
            ]
        },
    )
    logger.info(
        "Creando índice '%s' (%d dims) en %s.%s...",
        config.VECTOR_INDEX_NAME, config.EMBEDDING_DIM, config.DB_NAME, config.CHUNKS_COLLECTION,
    )
    coleccion.create_search_index(model=modelo)

    for _ in range(30):
        indices = list(coleccion.list_search_indexes(config.VECTOR_INDEX_NAME))
        if indices and indices[0].get("status") == "READY":
            logger.info("Índice '%s' listo (READY).", config.VECTOR_INDEX_NAME)
            return
        time.sleep(2)
    logger.warning("Índice creado pero aún no READY; puede tardar un poco más.")


if __name__ == "__main__":
    crear_indice()
