# Imagen del Asistente RAG (Groq + embeddings locales).
# Objetivo: que un tercero pueda construir y correr con un solo comando.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/hf_cache \
    HOME=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# torch CPU PRIMERO: evita descargar las ruedas CUDA (varios GB) que
# sentence-transformers traería por defecto.
RUN pip install --upgrade pip \
    && pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

# Pre-descarga del modelo de embeddings EN EL BUILD, para que el arranque no
# dependa de bajar ~470 MB desde HuggingFace en runtime. Si cambias de modelo,
# reconstruye con: --build-arg EMBEDDING_MODEL=<otro-modelo>.
ARG EMBEDDING_MODEL=intfloat/multilingual-e5-small
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

COPY . .

# Ejecutar como usuario no root (buena práctica; evita warnings de seguridad).
RUN useradd -r -d /app appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# entrypoint.sh se invoca con sh para no depender del bit +x (que Windows no
# preserva al clonar el repo).
ENTRYPOINT ["sh", "entrypoint.sh"]
