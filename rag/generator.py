"""
Capa de generación: combina retrieval (RAG) con el LLM de Groq.

Incorpora dos capacidades pedidas por la rúbrica:
- Contexto conversacional: se envía al LLM una ventana acotada del historial
  de la sesión, y la consulta de retrieval se hace sensible al hilo.
- Fuentes internas + externas: el contexto mezcla los chunks internos (Mongo)
  con resultados de una búsqueda web externa, etiquetando el origen de cada uno
  para trazabilidad.

Se usa el SDK oficial de Groq. Los modelos qwen3/qwq/deepseek son de
"razonamiento": se pide `reasoning_format="hidden"` (con reintento seguro y
limpieza de etiquetas <think> como última defensa).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from rag import config
from rag.costs import calcular_costo_chat
from rag.external import buscar_web
from rag.prompts import SYSTEM_PROMPT, construir_prompt_usuario
from rag.retriever import get_retriever

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_MODELOS_RAZONAMIENTO = ("qwen3", "qwq", "deepseek-r1", "reasoning")


def _es_modelo_de_razonamiento(modelo: str) -> bool:
    m = modelo.lower()
    return any(clave in m for clave in _MODELOS_RAZONAMIENTO)


def _limpiar(texto: str) -> str:
    # Quita bloques <think>...</think> cerrados,
    t = _THINK_RE.sub("", texto)
    # un <think> sin cierre (respuesta truncada): borra desde ahí al final,
    t = re.sub(r"<think>.*$", "", t, flags=re.DOTALL | re.IGNORECASE)
    # y cualquier etiqueta suelta que haya quedado.
    t = re.sub(r"</?think>", "", t, flags=re.IGNORECASE)
    return t.strip()


@dataclass
class RespuestaRAG:
    respuesta: str
    fuentes: list[dict[str, Any]] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_salida: int = 0
    costo_usd: float = 0.0


class RAGGenerator:
    def __init__(self) -> None:
        from groq import Groq

        if not config.GROQ_API_KEY:
            logger.warning("GROQ_API_KEY no está definido; las llamadas al LLM fallarán.")
        self.client = Groq(api_key=config.GROQ_API_KEY)
        self.modelo = config.GROQ_MODEL
        self.retriever = get_retriever()

    # --- Contexto conversacional -----------------------------------------
    @staticmethod
    def _historial_a_mensajes(historial: list[dict[str, Any]] | None) -> list[dict[str, str]]:
        """Convierte el historial de la sesión en mensajes para el LLM, acotado
        a los últimos MAX_HISTORY_MSGS mensajes con contenido válido."""
        if not historial:
            return []
        recientes = historial[-config.MAX_HISTORY_MSGS:]
        mensajes = []
        for m in recientes:
            rol = m.get("rol") or m.get("role")
            contenido = (m.get("contenido") or m.get("content") or "").strip()
            if rol in ("user", "assistant") and contenido:
                mensajes.append({"role": rol, "content": contenido})
        return mensajes

    @staticmethod
    def _consulta_contextual(pregunta: str, historial: list[dict[str, Any]] | None) -> str:
        """Consulta de retrieval sensible al hilo: antepone la última pregunta
        del usuario para que los seguimientos ("¿y eso?") recuperen bien."""
        if not historial:
            return pregunta
        ultimas_user = [
            (m.get("contenido") or m.get("content") or "")
            for m in historial
            if (m.get("rol") or m.get("role")) == "user"
        ]
        if ultimas_user:
            return f"{ultimas_user[-1]} {pregunta}".strip()
        return pregunta

    # --- Contexto (interno + externo) ------------------------------------
    def _reunir_contexto(self, pregunta_retrieval: str, top_k: int | None):
        internos = self.retriever.buscar(pregunta_retrieval, top_k=top_k)
        consulta_web = f"{pregunta_retrieval} {config.EXTERNAL_QUERY_CONTEXT}".strip()
        externos = buscar_web(consulta_web, k=config.EXTERNAL_TOP_K) if config.USAR_FUENTE_EXTERNA else []

        bloques = []
        for i, f in enumerate(internos, start=1):
            bloques.append(f"[Interna {i} · {f.fuente}]\n{f.texto}")
        for j, e in enumerate(externos, start=1):
            bloques.append(f"[Externa {j} · {e.url or e.titulo}]\n{e.texto}")
        contexto = "\n\n".join(bloques) if bloques else "No se encontró contexto relevante."

        fuentes = [f.to_dict() for f in internos] + [e.to_dict() for e in externos]
        return contexto, fuentes

    # --- LLM --------------------------------------------------------------
    def _chat(self, mensajes: list[dict[str, str]]):
        kwargs: dict[str, Any] = {
            "model": self.modelo,
            "messages": mensajes,
            "temperature": config.LLM_TEMPERATURE,
            "max_tokens": config.LLM_MAX_TOKENS,
        }
        if _es_modelo_de_razonamiento(self.modelo):
            try:
                return self.client.chat.completions.create(reasoning_format="hidden", **kwargs)
            except Exception as exc:  # noqa: BLE001
                logger.info("reasoning_format no aceptado (%s); reintentando sin él.", exc)
        return self.client.chat.completions.create(**kwargs)

    def responder(
        self,
        pregunta: str,
        historial: list[dict[str, Any]] | None = None,
        top_k: int | None = None,
    ) -> RespuestaRAG:
        consulta = self._consulta_contextual(pregunta, historial)
        contexto, fuentes = self._reunir_contexto(consulta, top_k)

        mensajes = [{"role": "system", "content": SYSTEM_PROMPT}]
        mensajes += self._historial_a_mensajes(historial)
        mensajes.append({"role": "user", "content": construir_prompt_usuario(pregunta, contexto)})

        respuesta = self._chat(mensajes)
        texto = _limpiar(respuesta.choices[0].message.content or "")

        uso = respuesta.usage
        tokens_entrada = getattr(uso, "prompt_tokens", 0) or 0
        tokens_salida = getattr(uso, "completion_tokens", 0) or 0

        return RespuestaRAG(
            respuesta=texto,
            fuentes=fuentes,
            tokens_entrada=tokens_entrada,
            tokens_salida=tokens_salida,
            costo_usd=calcular_costo_chat(self.modelo, tokens_entrada, tokens_salida),
        )


_singleton: RAGGenerator | None = None


def get_rag_generator() -> RAGGenerator:
    global _singleton
    if _singleton is None:
        _singleton = RAGGenerator()
    return _singleton
