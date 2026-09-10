"""
Capa de datos sobre MongoDB Atlas.

Centraliza la conexión y expone:
- `chunks`          : texto + embedding + metadata (base de conocimiento RAG).
- `conversaciones`  : historial de mensajes por sesión de chat.
- `feedback`        : 👍/👎 de los usuarios sobre respuestas del asistente.

La búsqueda semántica usa `$vectorSearch` contra el índice de Atlas Vector
Search creado con `scripts/create_index.py`. Las dimensiones del índice deben
coincidir con `config.EMBEDDING_DIM`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Iterable

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from rag import config

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    logger.info("Conectando a MongoDB (ambiente=%s, db=%s)", config.ENVIRONMENT, config.DB_NAME)
    return MongoClient(config.MONGODB_URI, serverSelectionTimeoutMS=5000)


def get_db() -> Database:
    return get_client()[config.DB_NAME]


def get_collection(nombre: str) -> Collection:
    return get_db()[nombre]


def ping() -> bool:
    try:
        get_client().admin.command("ping")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sin conexión a MongoDB: %s", exc)
        return False


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# --- Base de conocimiento (chunks) ---------------------------------------
def insertar_chunks(documentos: Iterable[dict[str, Any]]) -> int:
    documentos = list(documentos)
    if not documentos:
        return 0
    resultado = get_collection(config.CHUNKS_COLLECTION).insert_many(documentos)
    return len(resultado.inserted_ids)


def contar_chunks() -> int:
    return get_collection(config.CHUNKS_COLLECTION).count_documents({})


def vector_search(query_embedding: list[float], top_k: int | None = None) -> list[dict[str, Any]]:
    """Ejecuta `$vectorSearch` sobre la colección `chunks`."""
    top_k = top_k or config.TOP_K
    coleccion = get_collection(config.CHUNKS_COLLECTION)
    pipeline = [
        {
            "$vectorSearch": {
                "index": config.VECTOR_INDEX_NAME,
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": max(top_k * 10, 50),
                "limit": top_k,
            }
        },
        {"$set": {"score": {"$meta": "vectorSearchScore"}}},
        {"$project": {"embedding": 0}},
    ]
    try:
        return list(coleccion.aggregate(pipeline))
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Falló el vector search. ¿Creaste el índice con scripts/create_index.py "
            "y coincide EMBEDDING_DIM (%s) con el índice? Detalle: %s",
            config.EMBEDDING_DIM,
            exc,
        )
        return []


# --- Historial de conversación -------------------------------------------
def guardar_mensaje(
    session_id: str,
    rol: str,
    contenido: str,
    fuentes: list[dict[str, Any]] | None = None,
    tokens_entrada: int = 0,
    tokens_salida: int = 0,
    costo_usd: float = 0.0,
) -> None:
    """Persiste un mensaje. Best-effort: si Mongo no responde, no rompe el chat
    (el historial es deseable, no imprescindible)."""
    documento = {
        "session_id": session_id,
        "rol": rol,  # "user" | "assistant"
        "contenido": contenido,
        "fuentes": fuentes or [],
        "tokens_entrada": tokens_entrada,
        "tokens_salida": tokens_salida,
        "costo_usd": costo_usd,
        "creado_en": _ahora(),
    }
    try:
        get_collection(config.CONVERSATIONS_COLLECTION).insert_one(documento)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo guardar el mensaje (Mongo): %s", exc)


def obtener_historial(session_id: str) -> list[dict[str, Any]]:
    try:
        cursor = (
            get_collection(config.CONVERSATIONS_COLLECTION)
            .find({"session_id": session_id})
            .sort("creado_en", 1)
        )
        return list(cursor)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo leer el historial (Mongo): %s", exc)
        return []


# --- Feedback -------------------------------------------------------------
def guardar_feedback(
    session_id: str,
    pregunta: str,
    respuesta: str,
    calificacion: str,
    comentario: str | None = None,
) -> None:
    """Guarda feedback (positivo/negativo). Best-effort, igual que el historial."""
    documento = {
        "session_id": session_id,
        "pregunta": pregunta,
        "respuesta": respuesta,
        "calificacion": calificacion,  # "positivo" | "negativo"
        "comentario": comentario,
        "creado_en": _ahora(),
    }
    try:
        get_collection(config.FEEDBACK_COLLECTION).insert_one(documento)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo guardar el feedback (Mongo): %s", exc)
