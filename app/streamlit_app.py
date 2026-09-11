"""
Asistente inteligente · organización académica — Chatbot RAG (Streamlit).

Layout tipo dashboard: herramientas distribuidas alrededor del chat.
- Columna izquierda: clases del día, calendario, calculadora de notas.
- Centro: el chat RAG.
- Columna derecha: asistencia, Pomodoro, PDF→resumen, notas arrastrables.
- Abajo (ancho completo): tablero de trabajos grupales estilo Atlassian.

Las herramientas son un componente HTML/JS (paleta de 6 colores, transiciones)
que persiste su estado en el navegador (localStorage).

Ejecutar desde la raíz del proyecto:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

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

try:
    _TOOLS_HTML = (Path(__file__).parent / "tools.html").read_text(encoding="utf-8")
except Exception:  # noqa: BLE001
    _TOOLS_HTML = "<p>No se encontró tools.html</p>__PANELS__"


def _tools(panels: list[str], height: int) -> None:
    html = _TOOLS_HTML.replace("__PANELS__", json.dumps(panels))
    components.html(html, height=height, scrolling=True)


# Paleta de 6 colores (fríos análogos + acentos cálidos, teoría del color).
_CSS = """
<style>
:root{
  --c1:#2563EB; --c2:#4F46E5; --c3:#0EA5A4; --c4:#7C3AED; --c5:#F59E0B; --c6:#F43F5E;
  --s200:#E2E8F0; --s100:#F1F5F9; --s700:#334155; --ink:#0F172A;
}
.stApp{
  background:
    radial-gradient(1200px 420px at 100% -10%, #4f46e51f, transparent),
    radial-gradient(900px 380px at -8% 108%, #0ea5a41c, transparent),
    linear-gradient(160deg,#eef2f9,#e9eef8) !important;
}
[data-testid="stSidebar"], [data-testid="collapsedControl"]{ display:none !important; }
.block-container{ padding-top:1.1rem; max-width:1500px; }

.banner{
  background:linear-gradient(120deg,var(--c2) 0%,var(--c1) 45%,var(--c3) 120%);
  color:#fff; padding:1.05rem 1.4rem; border-radius:18px;
  box-shadow:0 12px 34px rgba(37,99,235,.24); margin-bottom:.8rem;
}
.banner h1{ margin:0; font-size:1.4rem; font-weight:800; }
.banner p{ margin:.25rem 0 0; opacity:.94; font-size:.9rem; }

.chips{ display:flex; flex-wrap:wrap; gap:.4rem; margin:.1rem 0 .5rem; }
.chip{ background:#fff; border:1px solid var(--s200); color:var(--s700);
  border-radius:999px; padding:.2rem .75rem; font-size:.78rem; box-shadow:0 1px 2px rgba(2,6,23,.05); }
.chip b{ color:var(--c2); font-weight:700; }
.chip.ok{ border-color:#86EFAC; color:#166534; } .chip.off{ border-color:#FCA5A5; color:#991B1B; }

/* Chat con acentos de la paleta */
[data-testid="stChatMessage"]{
  background:#fff; border:1px solid var(--s200); border-left:4px solid var(--c1);
  border-radius:14px; padding:.6rem .9rem; box-shadow:0 2px 12px rgba(2,6,23,.06); margin-bottom:.55rem;
}
[data-testid="stChatMessage"]:nth-of-type(even){ border-left-color:var(--c3); }
.col-title{ font-weight:800; color:var(--ink); font-size:.9rem; margin:.1rem 0 .3rem; display:flex; align-items:center; gap:.4rem; }
.col-title::before{ content:""; width:.7rem; height:.7rem; border-radius:3px; background:var(--c1); }
.col-title.r::before{ background:var(--c4); }
.stButton > button{ background:var(--c1); color:#fff; border:0; border-radius:10px; font-weight:600;
  transition:all .16s ease; }
.stButton > button:hover{ filter:brightness(1.08); transform:translateY(-1px); }
[data-testid="stExpander"]{ border:1px solid var(--s200); border-radius:12px; background:#fff; }
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


def _encabezado() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="banner">
          <h1>🎓 Asistente inteligente · organización académica</h1>
          <p>Chatbot RAG + herramientas — DuocUC (Informática, Diseño y Administración)</p>
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
          <span class="chip">Chunks: <b>{_contar_chunks_seguro()}</b></span>
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


def _feedback(indice: int, mensaje: dict) -> None:
    key = f"feedback_{indice}"
    if st.session_state.get(key):
        st.caption(f"Feedback registrado: {st.session_state[key]}")
        return
    c1, c2, _ = st.columns([1, 1, 6])
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
    if not st.session_state.mensajes:
        st.info("👋 Pregúntame sobre DuocUC, tus carreras o tus ramos.")
    for i, m in enumerate(st.session_state.mensajes):
        with st.chat_message(m["rol"]):
            st.markdown(m["contenido"])
            if m["rol"] == "assistant":
                if m.get("fuentes"):
                    with st.expander("📚 Fuentes usadas (internas y externas)"):
                        for f in m["fuentes"]:
                            enc = f"**{f['fuente']}**"
                            if f.get("score") is not None:
                                enc += f" (score: {f['score']})"
                            st.markdown(enc)
                            if f.get("url"):
                                st.caption(f"🔗 {f['url']}")
                            st.caption((f.get("texto") or "")[:300] + "...")
                _feedback(i, m)


def main() -> None:
    _inicializar_sesion()
    _encabezado()
    _panel_opciones()

    col_left, col_center, col_right = st.columns([1.15, 1.7, 1.25], gap="medium")
    with col_left:
        st.markdown('<div class="col-title">Agenda y notas</div>', unsafe_allow_html=True)
        _tools(["clases", "calendario", "calif"], height=780)
    with col_right:
        st.markdown('<div class="col-title r">Estudio y archivos</div>', unsafe_allow_html=True)
        _tools(["asistencia", "pomodoro", "pdf", "notas"], height=900)
    with col_center:
        _render_mensajes()

    st.markdown('<div class="col-title">Trabajos grupales · tablero</div>', unsafe_allow_html=True)
    _tools(["kanban"], height=420)

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
