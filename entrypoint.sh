#!/bin/sh
# Arranque del contenedor. Inicialización (índice + ingesta) OPCIONAL:
# actívala con INIT_ON_START=true (requiere MongoDB Atlas alcanzable, red y
# GITHUB_REPO con .md). Si algo falla, se avisa y la app arranca igual.
set -e

if [ "${INIT_ON_START:-false}" = "true" ]; then
  echo "[entrypoint] INIT_ON_START=true -> inicializando."
  echo "[entrypoint] Creando índice vectorial (idempotente)..."
  python -m scripts.create_index || echo "[entrypoint] AVISO: no se pudo crear el índice (¿Atlas / allowlist / red?)."
  echo "[entrypoint] Ingestando si la colección está vacía..."
  python - <<'PY' || echo "[entrypoint] AVISO: ingesta omitida o fallida."
from rag import vectorstore
from rag.ingest import ingestar_desde_github
try:
    n = vectorstore.contar_chunks()
except Exception:
    n = 0
if n == 0:
    print("[entrypoint] Colección vacía; ingestando desde GITHUB_REPO...")
    r = ingestar_desde_github()
    print("[entrypoint] Ingesta:", sum(x.chunks_insertados for x in r), "chunks.")
else:
    print(f"[entrypoint] Ya hay {n} chunks; no se re-ingesta.")
PY
fi

echo "[entrypoint] Iniciando Streamlit en :${PORT:-8501}"
exec streamlit run app/streamlit_app.py \
  --server.port="${PORT:-8501}" \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --browser.gatherUsageStats=false
