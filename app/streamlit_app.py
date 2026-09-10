"""
Asistente inteligente · organización académica — Chatbot RAG (Streamlit).

Layout ancho: el chat a la izquierda y, al costado, un calendario del mes y un
bloc de notas. Las opciones (estado de Mongo, ingesta, acciones) viven en un
panel colapsable. Tema corporativo claro con acentos azules.

Ejecutar desde la raíz del proyecto:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import calendar
import datetime as dt
import sys
import uuid
from pathlib import Path

import streamlit as st

# Permite ejecutar el archivo directamente agregando la raíz del proyecto al path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag import config, vectorstore  # noqa: E402
from rag.generator import get_rag_generator  # noqa: E402
from rag.ingest import ingestar_desde_github  # noqa: E402

st.set_page_config(
    page_title="Asistente Académico",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed",
)

_MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

_CSS = """
<style>
:root {
  --azul-900: #1E3A8A;
  --azul-600: #2563EB;
  --azul-100: #DBEAFE;
  --slate-50: #F8FAFC;
  --slate-100: #F1F5F9;
  --slate-200: #E2E8F0;
  --slate-700: #334155;
  --slate-900: #0F172A;
}
.stApp { background-color: var(--slate-50); }
[data-testid="stSidebar"], [data-testid="collapsedControl"] { display: none !important; }
.block-container { padding-top: 1.4rem; max-width: 1200px; }

.banner {
  background: linear-gradient(135deg, var(--azul-900) 0%, var(--azul-600) 100%);
  color: #fff; padding: 1.1rem 1.4rem; border-radius: 14px;
  box-shadow: 0 6px 20px rgba(37, 99, 235, 0.18); margin-bottom: 1rem;
}
.banner h1 { margin: 0; font-size: 1.35rem; font-weight: 700; letter-spacing: .2px; }
.banner p { margin: .25rem 0 0; opacity: .9; font-size: .9rem; }

.chips { display: flex; flex-wrap: wrap; gap: .4rem; margin: .2rem 0 .8rem; }
.chip {
  background: #fff; border: 1px solid var(--slate-200); color: var(--slate-700);
  border-radius: 999px; padding: .18rem .7rem; font-size: .78rem;
}
.chip b { color: var(--azul-900); font-weight: 600; }
.chip.ok { border-color: #86EFAC; color: #166534; }
.chip.off { border-color: #FCA5A5; color: #991B1B; }

.stButton > button {
  background: var(--azul-600); color: #fff; border: 0; border-radius: 10px;
  font-weight: 600; transition: background .15s ease;
}
.stButton > button:hover { background: var(--azul-900); color: #fff; }

[data-testid="stChatMessage"] {
  background: #fff; border: 1px solid var(--slate-200); border-radius: 12px;
  padding: .6rem .9rem; box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
}
[data-testid="stExpander"] {
  border: 1px solid var(--slate-200); border-radius: 12px; background: #fff;
}
[data-testid="stExpander"] summary:hover { color: var(--azul-600); }

/* Panel lateral (calendario + notas) */
.panel {
  background: #fff; border: 1px solid var(--slate-200); border-radius: 12px;
  padding: .7rem .8rem; margin-bottom: .8rem;
}
.panel h4 { margin: 0 0 .5rem; color: var(--azul-900); font-size: .95rem; }
table.cal { width: 100%; border-collapse: collapse; font-size: .8rem; }
table.cal th { color: var(--slate-700); font-weight: 600; padding: .2rem 0; }
table.cal td { text-align: center; padding: .28rem 0; color: var(--slate-900); }
table.cal td.hoy {
  background: var(--azul-600); color: #fff; border-radius: 8px; font-weight: 700;
}
table.cal td.vacio { color: transparent; }
.cal-mes { text-align: center; font-weight: 700; color: var(--azul-900); margin-bottom: .3rem; }
</style>
"""


def _inicializar_sesion() -> None:
    st.session_state.setdefault("session_id", str(uuid.uuid4()))
    st.session_state.setdefault("mensajes", [])


def _contar_chunks_seguro() -> str:
    try:
        return str(vectorstore.contar_chunks())
    except Exception:  # noqa: BLE001
        return "—"


def _calendario_html() -> str:
    hoy = dt.date.today()
    semanas = calendar.monthcalendar(hoy.year, hoy.month)
    filas = ""
    for semana in semanas:
        celdas = ""
        for dia in semana:
            if dia == 0:
                celdas += '<td class="vacio">.</td>'
            elif dia == hoy.day:
                celdas += f'<td class="hoy">{dia}</td>'
            else:
                celdas += f"<td>{dia}</td>"
        filas += f"<tr>{celdas}</tr>"
    encabezado = "".join(f"<th>{d}</th>" for d in ["Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do"])
    return (
        f'<div class="cal-mes">{_MESES[hoy.month - 1]} {hoy.year}</div>'
        f'<table class="cal"><tr>{encabezado}</tr>{filas}</table>'
    )


def _encabezado() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="banner">
          <h1>🎓 Asistente inteligente · organización académica</h1>
          <p>Chatbot RAG — DuocUC (Informática, Diseño y Administración)</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    mongo_ok = vectorstore.ping()
    estado = ("ok", "🟢 conectado") if mongo_ok else ("off", "🔴 sin conexión")
    st.markdown(
        f"""
        <div class="chips">
          <span class="chip {estado[0]}">MongoDB: {estado[1]}</span>
          <span class="chip">Ambiente: <b>{config.ENVIRONMENT}</b></span>
          <span class="chip">Modelo: <b>{config.GROQ_MODEL}</b></span>
          <span class="chip">Chunks indexados: <b>{_contar_chunks_seguro()}</b></span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _panel_opciones() -> None:
    with st.expander("⚙️ Opciones y administración", expanded=False):
        st.caption("Descarga e indexa los archivos .md del repositorio configurado en `GITHUB_REPO`.")
        col_a, col_b = st.columns(2)
        if col_a.button("📥 Ingestar material (.md)", use_container_width=True):
            with st.spinner("Descargando e indexando..."):
                try:
                    resultados = ingestar_desde_github()
                    total = sum(r.chunks_insertados for r in resultados)
                    st.success(f"Ingesta completa: {len(resultados)} archivos, {total} chunks.")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Error durante la ingesta: {exc}")
        if col_b.button("🗑️ Nueva conversación", use_container_width=True):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.mensajes = []
            st.rerun()


def _panel_lateral() -> None:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown("<h4>📅 Calendario</h4>", unsafe_allow_html=True)
    st.markdown(_calendario_html(), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown("<h4>📝 Notas</h4>", unsafe_allow_html=True)
    st.text_area(
        "Notas de la sesión",
        key="notas",
        height=220,
        placeholder="Anota aquí tareas, fechas o recordatorios...",
        label_visibility="collapsed",
    )
    st.markdown("</div>", unsafe_allow_html=True)


def _feedback(indice: int, mensaje: dict) -> None:
    key = f"feedback_{indice}"
    if st.session_state.get(key):
        st.caption(f"Feedback registrado: {st.session_state[key]}")
        return
    c1, c2, _ = st.columns([1, 1, 8])
    for etiqueta, calificacion, col in (("👍", "positivo", c1), ("👎", "negativo", c2)):
        if col.button(etiqueta, key=f"{calificacion}_{indice}"):
            vectorstore.guardar_feedback(
                session_id=st.session_state.session_id,
                pregunta=mensaje.get("pregunta", ""),
                respuesta=mensaje["contenido"],
                calificacion=calificacion,
            )
            st.session_state[key] = etiqueta
            st.rerun()


def _render_mensajes() -> None:
    for i, m in enumerate(st.session_state.mensajes):
        with st.chat_message(m["rol"]):
            st.markdown(m["contenido"])
            if m["rol"] == "assistant":
                if m.get("fuentes"):
                    with st.expander("📚 Fuentes usadas (internas y externas)"):
                        for f in m["fuentes"]:
                            encabezado = f"**{f['fuente']}**"
                            if f.get("score") is not None:
                                encabezado += f" (score: {f['score']})"
                            st.markdown(encabezado)
                            if f.get("url"):
                                st.caption(f"🔗 {f['url']}")
                            st.caption((f.get("texto") or "")[:300] + "...")
                _feedback(i, m)


def main() -> None:
    _inicializar_sesion()
    _encabezado()
    _panel_opciones()

    col_chat, col_side = st.columns([2, 1], gap="large")
    with col_side:
        _panel_lateral()
    with col_chat:
        _render_mensajes()

    pregunta = st.chat_input("Escribe tu pregunta sobre DuocUC o tus ramos...")
    if not pregunta:
        return

    st.session_state.mensajes.append({"rol": "user", "contenido": pregunta})
    vectorstore.guardar_mensaje(st.session_state.session_id, "user", pregunta)

    with st.spinner("Pensando..."):
        resultado = get_rag_generator().responder(
            pregunta, historial=st.session_state.mensajes[:-1]
        )

    st.session_state.mensajes.append(
        {
            "rol": "assistant",
            "contenido": resultado.respuesta,
            "pregunta": pregunta,
            "fuentes": resultado.fuentes,
        }
    )
    vectorstore.guardar_mensaje(
        session_id=st.session_state.session_id,
        rol="assistant",
        contenido=resultado.respuesta,
        fuentes=resultado.fuentes,
        tokens_entrada=resultado.tokens_entrada,
        tokens_salida=resultado.tokens_salida,
    )
    st.rerun()


if __name__ == "__main__":
    main()
