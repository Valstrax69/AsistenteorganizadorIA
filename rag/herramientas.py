"""
Herramientas del agente.

Cada funcion marcada con @tool queda disponible para que el LLM la llame solo.
Se agrupan en tres tipos, que son los que pide el encargo:

- consulta  : buscar_material, buscar_en_web, listar_tareas, estado_asistencia
- escritura : crear_tarea, mover_tarea, registrar_asistencia
- razonamiento: planificar_semana

El docstring de cada funcion NO es decorativo: es lo que lee el modelo para
decidir cuando llamarla. Si el docstring es vago, el agente se equivoca.
"""

from __future__ import annotations

from datetime import date, datetime

from langchain_core.tools import tool

from rag import config, vectorstore
from rag.external import buscar_web as _buscar_web
from rag.retriever import get_retriever


def _tareas():
    return vectorstore.get_collection(config.TAREAS_COLLECTION)


def _asistencia():
    return vectorstore.get_collection(config.ASISTENCIA_COLLECTION)


def _filtro_usuario(extra: dict | None = None) -> dict:
    filtro = {"usuario": config.USUARIO_ID}
    if extra:
        filtro.update(extra)
    return filtro


# --- Consulta -------------------------------------------------------------
@tool
def buscar_material(consulta: str) -> str:
    """Busca informacion en el material interno de DuocUC (reglamentos, carreras,
    organizacion academica) usando busqueda semantica. Usala para preguntas sobre
    la institucion, las carreras o las normas."""
    fragmentos = get_retriever().buscar(consulta)
    if not fragmentos:
        return "No se encontro material interno sobre eso."
    bloques = [
        f"[Interna {i} - {f.fuente} - score {f.score:.3f}]\n{f.texto}"
        for i, f in enumerate(fragmentos, start=1)
    ]
    return "\n\n".join(bloques)


@tool
def buscar_en_web(consulta: str) -> str:
    """Busca en la web cuando el material interno no alcanza. Usala solo si
    buscar_material no devolvio nada util."""
    resultados = _buscar_web(f"{consulta} {config.EXTERNAL_QUERY_CONTEXT}", k=config.EXTERNAL_TOP_K)
    if not resultados:
        return "La busqueda web no devolvio resultados."
    bloques = [f"[Externa {i} - {r.url}]\n{r.texto}" for i, r in enumerate(resultados, start=1)]
    return "\n\n".join(bloques)


@tool
def listar_tareas(estado: str = "todas") -> str:
    """Lista las tareas y evaluaciones del estudiante. El estado puede ser
    'por_hacer', 'en_progreso', 'hecho' o 'todas'."""
    extra = None if estado == "todas" else {"estado": estado}
    lista = list(_tareas().find(_filtro_usuario(extra), {"_id": 0, "usuario": 0}))
    if not lista:
        return "No hay tareas registradas."
    lineas = [
        f"- {t['titulo']} ({t['ramo']}) | entrega {t['fecha']} | {t['ponderacion']}% | {t['estado']}"
        for t in lista
    ]
    return "\n".join(lineas)


@tool
def estado_asistencia(ramo: str) -> str:
    """Devuelve el porcentaje de asistencia de un ramo y avisa si esta bajo el
    minimo exigido."""
    registros = list(_asistencia().find(_filtro_usuario({"ramo": ramo})))
    if not registros:
        return f"No hay registros de asistencia para {ramo}."
    asistidas = sum(1 for r in registros if r.get("asistio"))
    porcentaje = asistidas / len(registros) * 100
    aviso = f" ALERTA: bajo el minimo de {config.ASISTENCIA_MINIMA}%." if porcentaje < config.ASISTENCIA_MINIMA else ""
    return f"{ramo}: {porcentaje:.0f}% ({asistidas} de {len(registros)} clases).{aviso}"


# --- Escritura ------------------------------------------------------------
@tool
def crear_tarea(titulo: str, ramo: str, fecha_entrega: str, ponderacion: int = 10) -> str:
    """Crea una tarea o evaluacion. La fecha va en formato AAAA-MM-DD y la
    ponderacion en porcentaje de la nota del ramo."""
    try:
        datetime.strptime(fecha_entrega, "%Y-%m-%d")
    except ValueError:
        return "La fecha debe venir en formato AAAA-MM-DD."
    _tareas().insert_one(
        {
            "usuario": config.USUARIO_ID,
            "titulo": titulo,
            "ramo": ramo,
            "fecha": fecha_entrega,
            "ponderacion": ponderacion,
            "estado": "por_hacer",
            "creado_en": datetime.now().isoformat(timespec="seconds"),
        }
    )
    return f"Tarea '{titulo}' creada para el {fecha_entrega}."


@tool
def mover_tarea(titulo: str, nuevo_estado: str) -> str:
    """Cambia el estado de una tarea. Estados validos: por_hacer, en_progreso, hecho."""
    if nuevo_estado not in ("por_hacer", "en_progreso", "hecho"):
        return "Estado no valido. Usa por_hacer, en_progreso o hecho."
    resultado = _tareas().update_one(
        _filtro_usuario({"titulo": titulo}), {"$set": {"estado": nuevo_estado}}
    )
    if not resultado.matched_count:
        return f"No encontre una tarea llamada '{titulo}'."
    return f"'{titulo}' quedo en estado {nuevo_estado}."


@tool
def registrar_asistencia(ramo: str, asistio: bool) -> str:
    """Registra si el estudiante fue o no a una clase de un ramo hoy."""
    _asistencia().insert_one(
        {
            "usuario": config.USUARIO_ID,
            "ramo": ramo,
            "asistio": asistio,
            "fecha": str(date.today()),
        }
    )
    estado = "asistencia" if asistio else "inasistencia"
    return f"Registrada la {estado} en {ramo}."


# --- Razonamiento ---------------------------------------------------------
@tool
def planificar_semana() -> str:
    """Ordena las tareas pendientes por prioridad, combinando cuanto pesa cada
    una en la nota y cuantos dias faltan para entregarla."""
    hoy = date.today()
    pendientes = list(_tareas().find(_filtro_usuario({"estado": {"$ne": "hecho"}})))
    if not pendientes:
        return "No hay tareas pendientes."

    for t in pendientes:
        dias = (datetime.strptime(t["fecha"], "%Y-%m-%d").date() - hoy).days
        t["dias"] = dias
        # Mas ponderacion y menos dias = mas urgente. El max(dias,1) evita
        # dividir por cero cuando la entrega es hoy o ya paso.
        t["prioridad"] = t["ponderacion"] / max(dias, 1)

    pendientes.sort(key=lambda t: t["prioridad"], reverse=True)

    lineas = []
    for i, t in enumerate(pendientes, start=1):
        if t["dias"] < 0:
            plazo = f"ATRASADA hace {abs(t['dias'])} dias"
        elif t["dias"] == 0:
            plazo = "ENTREGA HOY"
        else:
            plazo = f"quedan {t['dias']} dias"
        lineas.append(f"{i}. {t['titulo']} ({t['ramo']}) | {t['ponderacion']}% | {plazo}")
    return "\n".join(lineas)


HERRAMIENTAS = [
    buscar_material,
    buscar_en_web,
    listar_tareas,
    estado_asistencia,
    crear_tarea,
    mover_tarea,
    registrar_asistencia,
    planificar_semana,
]

POR_NOMBRE = {h.name: h for h in HERRAMIENTAS}
