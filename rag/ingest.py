"""
Pipeline de ingesta: Markdown (.md) -> chunks -> embeddings (locales) -> MongoDB.

El material del conocimiento se maneja en Markdown (no PDF): es texto plano, no
requiere extracción y es fácil de versionar/editar.

Fuentes soportadas:
- `ingestar_desde_github()`: descarga los .md de un repo público de GitHub
  (variable GITHUB_REPO) usando la API de contenidos.
- `ingestar_carpeta_local()`: indexa los .md de una carpeta del disco
  (por defecto ./data). Es el camino simple para probar sin depender de GitHub.
- `ingestar_texto()`: indexa texto plano (útil para tests).
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from rag import config, vectorstore
from rag.embeddings import get_embeddings

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com/repos"
DEFAULT_LOCAL_DIR = "data"


@dataclass
class ResultadoIngesta:
    fuente: str
    chunks_insertados: int


# --- Chunking -------------------------------------------------------------
def dividir_en_chunks(
    texto: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """Divide el texto en fragmentos con solapamiento, cortando de preferencia
    en saltos de párrafo o de oración para no partir ideas a la mitad."""
    chunk_size = chunk_size or config.CHUNK_SIZE
    overlap = overlap or config.CHUNK_OVERLAP
    if chunk_size <= overlap:
        raise ValueError("chunk_size debe ser mayor que overlap")

    texto = texto.strip()
    if not texto:
        return []

    chunks: list[str] = []
    inicio, longitud = 0, len(texto)
    while inicio < longitud:
        fin = min(inicio + chunk_size, longitud)
        if fin < longitud:
            corte = texto.rfind("\n\n", inicio, fin)
            if corte == -1:
                corte = texto.rfind(". ", inicio, fin)
            if corte != -1 and corte > inicio:
                fin = corte + 1
        fragmento = texto[inicio:fin].strip()
        if fragmento:
            chunks.append(fragmento)
        siguiente = fin - overlap
        inicio = siguiente if siguiente > inicio else fin
    return chunks


# --- Núcleo: indexar un texto --------------------------------------------
def ingestar_texto(texto: str, fuente: str, metadata: dict[str, Any] | None = None) -> ResultadoIngesta:
    chunks = dividir_en_chunks(texto)
    if not chunks:
        logger.warning("La fuente '%s' no produjo chunks (¿archivo vacío?).", fuente)
        return ResultadoIngesta(fuente=fuente, chunks_insertados=0)

    vectores = get_embeddings().embed_documents(chunks)
    documento_id = str(uuid.uuid4())
    ahora = datetime.now(timezone.utc)
    registros = [
        {
            "documento_id": documento_id,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "texto": chunk,
            "embedding": vector,
            "fuente": fuente,
            "metadata": metadata or {},
            "creado_en": ahora,
        }
        for i, (chunk, vector) in enumerate(zip(chunks, vectores))
    ]
    insertados = vectorstore.insertar_chunks(registros)
    logger.info("Ingestados %d chunks desde '%s'.", insertados, fuente)
    return ResultadoIngesta(fuente=fuente, chunks_insertados=insertados)


# --- Fuente: GitHub (.md) -------------------------------------------------
def _parsear_repo(url: str) -> tuple[str, str]:
    partes = url.rstrip("/").removesuffix(".git").split("/")
    return partes[-2], partes[-1]


def _listar_md_github(url_repo: str, path: str = "") -> list[dict[str, Any]]:
    owner, repo = _parsear_repo(url_repo)
    url = f"{GITHUB_API_BASE}/{owner}/{repo}/contents/{path}"
    headers = {"Accept": "application/vnd.github+json"}
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    archivos: list[dict[str, Any]] = []
    for item in resp.json():
        if item["type"] == "dir":
            archivos.extend(_listar_md_github(url_repo, item["path"]))
        elif item["type"] == "file" and item["name"].lower().endswith((".md", ".markdown")):
            archivos.append(item)
    return archivos


def ingestar_desde_github(url_repo: str | None = None) -> list[ResultadoIngesta]:
    url_repo = url_repo or config.GITHUB_REPO
    if not url_repo:
        raise ValueError("Define GITHUB_REPO en el .env o pasa la URL del repo.")
    archivos = _listar_md_github(url_repo)
    logger.info("Se encontraron %d archivos .md en %s", len(archivos), url_repo)
    resultados = []
    for md in archivos:
        texto = requests.get(md["download_url"], timeout=60).text
        resultados.append(ingestar_texto(texto, fuente=md["path"], metadata={"repo": url_repo}))
    return resultados


# --- Fuente: carpeta local (.md) ------------------------------------------
def ingestar_carpeta_local(carpeta: str | None = None) -> list[ResultadoIngesta]:
    ruta = Path(carpeta or DEFAULT_LOCAL_DIR)
    if not ruta.is_dir():
        raise ValueError(f"No es una carpeta válida: {ruta}")
    archivos = sorted(list(ruta.rglob("*.md")) + list(ruta.rglob("*.markdown")))
    logger.info("Se encontraron %d archivos .md en %s", len(archivos), ruta)
    resultados = []
    for md in archivos:
        texto = md.read_text(encoding="utf-8", errors="replace")
        resultados.append(ingestar_texto(texto, fuente=md.name, metadata={"ruta": str(md)}))
    return resultados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    local = os.getenv("INGEST_LOCAL_DIR")
    if local:
        resultados = ingestar_carpeta_local(local)
    elif config.GITHUB_REPO:
        resultados = ingestar_desde_github()
    elif Path(DEFAULT_LOCAL_DIR).is_dir():
        resultados = ingestar_carpeta_local(DEFAULT_LOCAL_DIR)
    else:
        raise SystemExit("Nada que ingestar: define GITHUB_REPO, INGEST_LOCAL_DIR o crea ./data con .md")
    for r in resultados:
        print(f"{r.fuente}: {r.chunks_insertados} chunks")
