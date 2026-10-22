"""
Agente: el LLM decide solo que herramientas llamar y en que orden.

El ciclo es el patron ReAct, escrito a mano para que se pueda seguir leyendo:

    1. se le manda al modelo el prompt + el historial + la pregunta
    2. si el modelo pide herramientas, se ejecutan y se le devuelven los resultados
    3. se repite hasta que el modelo responde sin pedir nada mas (o se agotan los pasos)

Se usa LangChain (ChatGroq + @tool) para el enlace de herramientas, pero el
ciclo queda explicito a proposito: son 30 lineas que se pueden explicar, en vez
de un grafo que hay que creerle.

Memoria:
- corto plazo : el historial de la conversacion abierta (lo pasa la app).
- largo plazo : mensajes de sesiones anteriores, leidos desde Mongo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from rag import config, vectorstore
from rag.herramientas import HERRAMIENTAS, POR_NOMBRE
from rag.prompts import AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class RespuestaAgente:
    respuesta: str
    herramientas_usadas: list[str] = field(default_factory=list)
    pasos: int = 0
    memoria_larga_usada: bool = False
    tokens_entrada: int = 0
    tokens_salida: int = 0


class AgenteAcademico:
    def __init__(self) -> None:
        from langchain_groq import ChatGroq

        if not config.GROQ_API_KEY:
            logger.warning("GROQ_API_KEY no esta definido; las llamadas al LLM fallaran.")
        modelo = ChatGroq(
            api_key=config.GROQ_API_KEY,
            model=config.GROQ_MODEL,
            temperature=config.LLM_TEMPERATURE,
            max_tokens=config.LLM_MAX_TOKENS,
        )
        # bind_tools le pasa al modelo el nombre, la descripcion y los
        # parametros de cada herramienta, para que sepa que puede pedir.
        self.modelo = modelo.bind_tools(HERRAMIENTAS)

    # --- Memoria -----------------------------------------------------------
    @staticmethod
    def _memoria_corto_plazo(historial: list[dict[str, Any]] | None) -> list:
        """Historial de la conversacion abierta, acotado para no inflar tokens."""
        if not historial:
            return []
        mensajes = []
        for m in historial[-config.MAX_HISTORY_MSGS:]:
            rol = m.get("rol") or m.get("role")
            contenido = (m.get("contenido") or m.get("content") or "").strip()
            if not contenido:
                continue
            if rol == "user":
                mensajes.append(HumanMessage(content=contenido))
            elif rol == "assistant":
                mensajes.append(AIMessage(content=contenido))
        return mensajes

    @staticmethod
    def _memoria_largo_plazo(session_id: str | None) -> str:
        if not session_id:
            return ""
        previos = vectorstore.obtener_memoria_larga(session_id)
        if not previos:
            return ""
        lineas = [f"- {p.get('contenido', '')[:160]}" for p in previos]
        return (
            "En sesiones anteriores el estudiante te dijo esto. Usalo solo si viene al caso:\n"
            + "\n".join(lineas)
        )

    # --- Ciclo del agente --------------------------------------------------
    def responder(
        self,
        pregunta: str,
        historial: list[dict[str, Any]] | None = None,
        session_id: str | None = None,
    ) -> RespuestaAgente:
        memoria_larga = self._memoria_largo_plazo(session_id)

        mensajes: list = [SystemMessage(content=AGENT_SYSTEM_PROMPT)]
        if memoria_larga:
            mensajes.append(SystemMessage(content=memoria_larga))
        mensajes += self._memoria_corto_plazo(historial)
        mensajes.append(HumanMessage(content=pregunta))

        usadas: list[str] = []
        tokens_entrada = 0
        tokens_salida = 0
        pasos = 0

        for pasos in range(1, config.MAX_PASOS_AGENTE + 1):
            respuesta = self.modelo.invoke(mensajes)
            mensajes.append(respuesta)

            uso = getattr(respuesta, "usage_metadata", None) or {}
            tokens_entrada += uso.get("input_tokens", 0)
            tokens_salida += uso.get("output_tokens", 0)

            llamadas = getattr(respuesta, "tool_calls", None)
            if not llamadas:
                break

            # El modelo pidio herramientas: se ejecutan y se le devuelve el
            # resultado de cada una como ToolMessage.
            for llamada in llamadas:
                nombre = llamada["name"]
                usadas.append(nombre)
                herramienta = POR_NOMBRE.get(nombre)
                if herramienta is None:
                    salida = f"La herramienta {nombre} no existe."
                else:
                    try:
                        salida = str(herramienta.invoke(llamada["args"]))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Fallo la herramienta %s: %s", nombre, exc)
                        salida = f"La herramienta {nombre} fallo: {exc}"
                mensajes.append(ToolMessage(content=salida, tool_call_id=llamada["id"]))

        texto = getattr(mensajes[-1], "content", "") or ""
        if not texto.strip():
            texto = "Me quede sin pasos antes de poder responder. Intenta preguntarlo mas simple."

        return RespuestaAgente(
            respuesta=str(texto).strip(),
            herramientas_usadas=usadas,
            pasos=pasos,
            memoria_larga_usada=bool(memoria_larga),
            tokens_entrada=tokens_entrada,
            tokens_salida=tokens_salida,
        )


_singleton: AgenteAcademico | None = None


def get_agente() -> AgenteAcademico:
    global _singleton
    if _singleton is None:
        _singleton = AgenteAcademico()
    return _singleton
