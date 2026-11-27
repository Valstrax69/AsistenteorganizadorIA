"""Prueba integrada del chat y el monitor de Streamlit, sin servicios externos."""

import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import mongomock
from streamlit.testing.v1 import AppTest

from evaluation.observabilidad import ModeloControlado
from rag import config, observabilidad, vectorstore
from rag.agente import AgenteAcademico


class InterfazTest(unittest.TestCase):
    def test_chat_genera_traza_que_lee_el_monitor(self):
        raiz = Path(__file__).resolve().parents[1]
        db = mongomock.MongoClient().ep3
        agente = AgenteAcademico.__new__(AgenteAcademico)
        agente.modelo = ModeloControlado("falta fecha", [])
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as contexto:
            contexto.enter_context(
                patch.object(config, "OBS_DB", str(Path(tmp) / "trazas.db"))
            )
            contexto.enter_context(patch.object(config, "OBS_ACTIVA", True))
            contexto.enter_context(patch.object(config, "MEMORIA_PERSONAL", False))
            contexto.enter_context(patch.object(vectorstore, "ping", return_value=True))
            contexto.enter_context(patch.object(vectorstore, "get_db", return_value=db))
            contexto.enter_context(patch("rag.agente.get_agente", return_value=agente))
            chat = AppTest.from_file(str(raiz / "app/streamlit_app.py")).run()
            self.assertFalse(chat.exception)
            chat.chat_input[0].set_value("Anota mi evaluación.").run()
            self.assertFalse(chat.exception)
            msg = chat.session_state["mensajes"][-1]
            self.assertIn("fecha", msg["contenido"])
            (traza,) = observabilidad.leer()
            self.assertEqual(msg["diagnostico"]["traza"], traza["id"])
            self.assertNotIn("evaluación", json.dumps(traza, ensure_ascii=False))
            self.assertEqual(db[config.CONVERSATIONS_COLLECTION].count_documents({}), 0)
            monitor = AppTest.from_file(str(raiz / "app/monitor_ep3.py")).run()
            self.assertFalse(monitor.exception)
            self.assertIn(traza["id"], monitor.get("iframe")[0].proto.srcdoc)
            monitor.button[0].click().run()
            self.assertFalse(monitor.exception)


if __name__ == "__main__":
    unittest.main()
