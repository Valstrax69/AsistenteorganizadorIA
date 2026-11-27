"""Visor local para el operador. Ejecutar por separado del chat."""

import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rag.observabilidad import leer
from scripts.dashboard_ep3 import render_html

st.set_page_config(page_title="Monitor del agente", layout="wide")
st.button("Actualizar trazas locales")
try:
    components.html(render_html(leer()), height=1240, scrolling=True)
except Exception:
    st.error(
        "No se pudieron leer las trazas locales. Revisa OBS_DB y los permisos del archivo."
    )
