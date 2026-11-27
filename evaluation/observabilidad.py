"""Banco aislado. Ejecuta el ciclo y herramientas reales contra datos académicos ficticios."""

import argparse
import json
from contextlib import ExitStack
from datetime import date, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

import mongomock
from langchain_core.messages import AIMessage, ToolMessage

from rag import config, vectorstore
from rag.agente import AgenteAcademico, get_agente

# Para cada escenario, las dos formulaciones tienen la misma intención y el mismo estado inicial.
CASOS = {
    "agenda breve": (
        "Lista mis tareas.",
        "¿Qué tareas tengo registradas?",
        ["listar_tareas"],
        1,
    ),
    "agenda extensa": (
        "Lista mis 40 tareas.",
        "Enumera las cuarenta tareas registradas.",
        ["listar_tareas"],
        40,
    ),
    "prioridad": (
        "Ordena mis pendientes por prioridad.",
        "¿Qué actividad debería hacer primero?",
        ["planificar_semana"],
        2,
    ),
    "cerrar y planificar": (
        "Marca Tarea-001 como hecha y ordena lo que queda.",
        "Terminé Tarea-001. Actualiza el estado y prioriza las demás.",
        ["mover_tarea", "planificar_semana"],
        3,
    ),
    "falta fecha": (
        "Anota mi control de física.",
        "Guarda un control, todavía no sé para cuándo.",
        [],
        0,
    ),
    "fallo de herramienta": (
        "¿Qué tareas hay?",
        "Enumera mis pendientes.",
        ["listar_tareas"],
        1,
    ),
    "límite de pasos": (
        "Lista las tareas.",
        "Enumera las tareas.",
        ["listar_tareas"],
        1,
    ),
    "caída de modelo": ("Ordena las tareas.", "Prioriza lo que queda.", [], 2),
}
FALLOS = {"fallo de herramienta", "límite de pasos", "caída de modelo"}


class ModeloControlado:
    """Solicita una secuencia fija. La respuesta final se construye con la salida real de la herramienta."""

    def __init__(self, caso, ruta):
        self.caso, self.ruta, self.posicion = caso, ruta, 0

    def invoke(self, mensajes):
        if self.caso == "caída de modelo":
            raise TimeoutError("fallo controlado")
        if self.caso == "límite de pasos" or self.posicion < len(self.ruta):
            nombre = self.ruta[self.posicion % len(self.ruta)]
            self.posicion += 1
            args = (
                {"titulo": "Tarea-001", "nuevo_estado": "hecho"}
                if nombre == "mover_tarea"
                else {}
            )
            return AIMessage(
                content="",
                tool_calls=[{"id": str(self.posicion), "name": nombre, "args": args}],
            )
        if self.caso == "falta fecha":
            return AIMessage(content="¿Cuál es la fecha de entrega?")
        if self.caso == "fallo de herramienta":
            return AIMessage(content="No pude consultar las tareas.")
        return AIMessage(
            content=next(
                m.content for m in reversed(mensajes) if isinstance(m, ToolMessage)
            )
        )


def preparar(coleccion, cantidad):
    for i in range(1, cantidad + 1):
        coleccion.insert_one(
            {
                "usuario": config.USUARIO_ID,
                "titulo": f"Tarea-{i:03}",
                "ramo": "DEMO",
                "fecha": str(date.today() + timedelta(days=i)),
                "ponderacion": 70 if i == 2 else 10,
                "estado": "por_hacer",
            }
        )


def verificar(caso, respuesta, coleccion, cantidad):
    import re

    texto = respuesta.lower()
    ids = [int(v) for v in re.findall(r"tarea[-\s]*0*(\d+)\b", texto)]
    if caso.startswith("agenda"):
        return sorted(ids) == list(range(1, cantidad + 1))
    if caso == "prioridad":
        return ids == [2, 1]
    if caso == "cerrar y planificar":
        hecha = (
            coleccion.count_documents({"titulo": "Tarea-001", "estado": "hecho"}) == 1
        )
        # La respuesta puede confirmar el cierre antes de mostrar la agenda restante.
        # El banco exige que la lista de prioridad contenga solo las dos pendientes.
        pendientes = [v for v in ids if v != 1]
        return hecha and pendientes == [2, 3] and (1 not in ids or ids == [1, 2, 3])
    if caso == "falta fecha":
        return "fecha" in texto and "?" in texto and coleccion.count_documents({}) == 0
    return None


def ejecutar(caso, variante, agente_groq=None):
    q1, q2, esperada, cantidad = CASOS[caso]
    db = mongomock.MongoClient().ep3
    tareas = db[config.TAREAS_COLLECTION]
    preparar(tareas, cantidad)
    agente = agente_groq
    if agente is None:
        agente = AgenteAcademico.__new__(AgenteAcademico)
        agente.modelo = ModeloControlado(caso, esperada)
    trazas = []
    respuesta = ""
    with ExitStack() as contexto:
        contexto.enter_context(
            patch.object(vectorstore, "get_collection", side_effect=lambda n: db[n])
        )
        contexto.enter_context(
            patch("rag.observabilidad.guardar", side_effect=trazas.append)
        )
        if caso == "fallo de herramienta":
            contexto.enter_context(
                patch("rag.herramientas._tareas", side_effect=TimeoutError())
            )
        # En modo Groq la batería solo expone herramientas locales a datos ficticios:
        # aun si el modelo pide búsqueda web/RAG, se registra como herramienta desconocida.
        if agente_groq is not None:
            from rag.agente import POR_NOMBRE

            contexto.enter_context(
                patch(
                    "rag.agente.POR_NOMBRE",
                    {
                        n: h
                        for n, h in POR_NOMBRE.items()
                        if n not in {"buscar_material", "buscar_en_web"}
                    },
                )
            )
        try:
            respuesta = agente.responder((q1, q2)[variante]).respuesta
        except Exception:
            if not trazas or trazas[0]["estado"] != "error":
                raise
    (traza,) = trazas
    ruta = [e["herramienta"] for e in traza["eventos"] if e["etapa"] == "herramienta"]
    aprobada = None
    if caso not in FALLOS:
        aprobada = (
            traza["estado"] == "ok"
            and ruta == esperada
            and verificar(caso, respuesta, tareas, cantidad)
        )
    traza.update(
        caso=caso,
        variante=variante + 1,
        evaluada=aprobada,
        origen="Groq con datos ficticios" if agente_groq else "Banco controlado",
    )
    return traza


def guardar_json(archivo, filas):
    archivo.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w", dir=archivo.parent, delete=False, encoding="utf8"
    ) as f:
        json.dump(filas, f, ensure_ascii=False, indent=2)
        tmp = Path(f.name)
    tmp.replace(archivo)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repeticiones", type=int, default=3)
    p.add_argument(
        "--groq",
        action="store_true",
        help="Consume API de Groq con datos ficticios y almacenamiento en memoria.",
    )
    p.add_argument("--salida", type=Path, default=Path(".observabilidad/banco.json"))
    args = p.parse_args()
    if args.repeticiones < 2:
        p.error("Se necesitan al menos dos repeticiones para medir consistencia.")
    if args.groq and not config.GROQ_API_KEY:
        p.error("Falta GROQ_API_KEY para la modalidad de inferencia externa.")
    agente = get_agente() if args.groq else None
    filas = []
    for caso in CASOS:
        if args.groq and caso in FALLOS:
            continue
        for variante in (0, 1):
            for _ in range(args.repeticiones):
                filas.append(ejecutar(caso, variante, agente))
    guardar_json(args.salida, filas)
    print(f"{len(filas)} trazas en {args.salida}")


if __name__ == "__main__":
    main()
