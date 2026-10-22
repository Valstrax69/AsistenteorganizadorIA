"""
Prueba del ciclo del agente SIN llamar a Groq ni a Mongo.

Reemplaza el modelo por uno falso que devuelve respuestas preparadas, y las
herramientas por versiones en memoria. Sirve para verificar que el bucle
ReAct encadena bien: pide herramienta -> la ejecuta -> se la devuelve ->
responde. No gasta cuota de API.

Uso:
    python -m evaluation.test_ciclo_mock
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import AIMessage  # noqa: E402

from rag.agente import AgenteAcademico  # noqa: E402


class ModeloFalso:
    """Devuelve una respuesta por turno, en orden."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = 0

    def invoke(self, mensajes):
        self.llamadas += 1
        return self.respuestas.pop(0)


def _agente_con(respuestas, herramientas_falsas):
    agente = AgenteAcademico.__new__(AgenteAcademico)  # sin __init__: no crea cliente Groq
    agente.modelo = ModeloFalso(respuestas)
    import rag.agente as mod
    mod.POR_NOMBRE = herramientas_falsas
    return agente


def _tool_falsa(nombre, salida):
    class T:
        def invoke(self, args):
            return salida
    return T()


def caso_una_herramienta():
    respuestas = [
        AIMessage(content="", tool_calls=[{"name": "listar_tareas", "args": {}, "id": "1"}]),
        AIMessage(content="Tienes 2 tareas pendientes."),
    ]
    tools = {"listar_tareas": _tool_falsa("listar_tareas", "- EP2 (ISY0101)\n- Taller (MAT6130)")}
    r = _agente_con(respuestas, tools).responder("que tengo pendiente?")
    ok = r.herramientas_usadas == ["listar_tareas"] and r.pasos == 2
    return "una herramienta", ok, f"usadas={r.herramientas_usadas} pasos={r.pasos}"


def caso_encadenado():
    respuestas = [
        AIMessage(content="", tool_calls=[{"name": "mover_tarea", "args": {}, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "planificar_semana", "args": {}, "id": "2"}]),
        AIMessage(content="Listo, y ahora sigue la EP2."),
    ]
    tools = {
        "mover_tarea": _tool_falsa("mover_tarea", "Taller quedo en hecho."),
        "planificar_semana": _tool_falsa("planificar_semana", "1. EP2 (ISY0101)"),
    }
    r = _agente_con(respuestas, tools).responder("ya termine el taller, que sigue?")
    ok = r.herramientas_usadas == ["mover_tarea", "planificar_semana"] and r.pasos == 3
    return "encadenado", ok, f"usadas={r.herramientas_usadas} pasos={r.pasos}"


def caso_sin_herramientas():
    respuestas = [AIMessage(content="Eso se escapa de lo academico.")]
    r = _agente_con(respuestas, {}).responder("como hago pizza?")
    ok = r.herramientas_usadas == [] and r.pasos == 1
    return "sin herramientas", ok, f"usadas={r.herramientas_usadas} pasos={r.pasos}"


def caso_herramienta_que_falla():
    class TRota:
        def invoke(self, args):
            raise RuntimeError("Mongo caido")
    respuestas = [
        AIMessage(content="", tool_calls=[{"name": "listar_tareas", "args": {}, "id": "1"}]),
        AIMessage(content="No pude leer tus tareas ahora."),
    ]
    r = _agente_con(respuestas, {"listar_tareas": TRota()}).responder("que tengo?")
    ok = r.pasos == 2 and "No pude" in r.respuesta
    return "herramienta que falla", ok, f"respuesta={r.respuesta!r}"


def caso_tope_de_pasos():
    from rag import config
    respuestas = [
        AIMessage(content="", tool_calls=[{"name": "listar_tareas", "args": {}, "id": str(i)}])
        for i in range(config.MAX_PASOS_AGENTE)
    ]
    tools = {"listar_tareas": _tool_falsa("listar_tareas", "nada")}
    r = _agente_con(respuestas, tools).responder("loop")
    ok = r.pasos == config.MAX_PASOS_AGENTE
    return "tope de pasos", ok, f"pasos={r.pasos} (tope {config.MAX_PASOS_AGENTE})"


def main():
    casos = [
        caso_una_herramienta,
        caso_encadenado,
        caso_sin_herramientas,
        caso_herramienta_que_falla,
        caso_tope_de_pasos,
    ]
    fallos = 0
    for c in casos:
        nombre, ok, detalle = c()
        print(f"[{'PASS' if ok else 'FAIL'}] {nombre}: {detalle}")
        fallos += 0 if ok else 1
    print(f"\n{len(casos) - fallos}/{len(casos)} PASS")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
