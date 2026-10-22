"""
Configuración central del proyecto (única fuente de verdad).

Todo lo configurable (credenciales, modelos, dimensiones, ambientes) se lee
desde variables de entorno AQUÍ y en ningún otro módulo. El resto del código
importa desde `rag.config`, de modo que cambiar de modelo de Groq, de modelo
de embeddings o de ambiente es una sola edición / una sola variable de entorno.

Cargar el .env: se hace de forma perezosa en `load_env()` para no obligar a
tener python-dotenv en entornos donde las variables ya vienen inyectadas
(por ejemplo, GitHub Actions con Secrets).
"""

from __future__ import annotations

import os


def load_env() -> None:
    """Carga variables desde un archivo .env si python-dotenv está disponible.

    Es idempotente y silencioso: en CI/CD las variables llegan como env vars
    reales (GitHub Secrets) y no hay .env, por lo que la ausencia de dotenv o
    de archivo no es un error.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(override=False)


load_env()


# --- Ambiente -------------------------------------------------------------
# main | qa | dev. Determina el sufijo de la base de datos Mongo para no
# mezclar datos entre ambientes que comparten el mismo cluster de Atlas.
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev").lower()

# --- MongoDB Atlas --------------------------------------------------------
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
_BASE_DB_NAME = os.getenv("MONGO_DB_BASE", "rag-duoc-groq")
DB_NAME = _BASE_DB_NAME if ENVIRONMENT == "main" else f"{_BASE_DB_NAME}-{ENVIRONMENT}"

CHUNKS_COLLECTION = "chunks"
CONVERSATIONS_COLLECTION = "conversaciones"
FEEDBACK_COLLECTION = "feedback"
# Datos academicos sobre los que opera el agente (lectura y escritura).
TAREAS_COLLECTION = "tareas"
ASISTENCIA_COLLECTION = "asistencia"
VECTOR_INDEX_NAME = os.getenv("VECTOR_INDEX_NAME", "vector_index")

# Identificador del estudiante. El proyecto es de un solo usuario, pero los
# documentos lo guardan para no tener que migrar si despues hay varios.
USUARIO_ID = os.getenv("USUARIO_ID", "estudiante")
ASISTENCIA_MINIMA = int(os.getenv("ASISTENCIA_MINIMA", "70"))

# --- Embeddings (locales, sentence-transformers) --------------------------
# El corpus del curso está en español => modelo multilingüe.
# multilingual-e5-small produce vectores de 384 dimensiones. Si cambias de
# modelo, ajusta EMBEDDING_DIM para que calce con el índice de Atlas.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))

# --- LLM (Groq) -----------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# IMPORTANTE: el modelo tiene que soportar function calling (que el LLM pueda
# pedir la ejecucion de una herramienta). Los sistemas "compound" de Groq NO
# aceptan herramientas propias, por eso ya no sirven para este agente.
# gpt-oss-120b figura en el plan gratuito. IDs en console.groq.com/docs/models
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))
# Tope de vueltas del ciclo del agente: evita que se quede llamando
# herramientas para siempre si se confunde.
MAX_PASOS_AGENTE = int(os.getenv("MAX_PASOS_AGENTE", "5"))

# --- Retrieval / chunking -------------------------------------------------
# Bajo en 3 (antes 5) porque el agente manda mas cosas en cada llamada
# (esquema de herramientas + historial) y el plan gratuito limita por minuto.
TOP_K = int(os.getenv("TOP_K", "3"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))

# --- Fuente de ingesta (repo GitHub o carpeta local con los .md del ramo) ----------------
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# --- Contexto conversacional ----------------------------------------------
# Cantidad máxima de mensajes previos (user+assistant) que se envían al LLM
# como memoria de la conversación. Acota el crecimiento de tokens.
MAX_HISTORY_MSGS = int(os.getenv("MAX_HISTORY_MSGS", "4"))

# --- Fuente externa (búsqueda web) ----------------------------------------
# La rúbrica pide integrar fuentes internas Y externas. Además de los PDFs
# internos (Mongo), se puede consultar la web como fuente externa.
USAR_FUENTE_EXTERNA = os.getenv("USAR_FUENTE_EXTERNA", "true").lower() == "true"
EXTERNAL_TOP_K = int(os.getenv("EXTERNAL_TOP_K", "3"))
# Se agrega a cada consulta web para que los resultados salgan relacionados
# al dominio (DuocUC y sus carreras), no temas al azar.
EXTERNAL_QUERY_CONTEXT = os.getenv("EXTERNAL_QUERY_CONTEXT", "DuocUC Chile informática diseño administración")
