import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

import mongomock
from langchain_core.messages import AIMessage

from evaluation.observabilidad import (
    CASOS,
    FALLOS,
    ModeloControlado,
    ejecutar,
    verificar,
)
from rag import config, vectorstore
from rag import observabilidad as obs
from rag.agente import AgenteAcademico
from rag.herramientas import buscar_en_web
from scripts.dashboard_ep3 import render_html


class ObservabilidadTest(unittest.TestCase):
    def test_cinco_tareas_funcionales(self):
        for caso in CASOS.keys() - FALLOS:
            for variante in (0, 1):
                with self.subTest(caso=caso, variante=variante):
                    t = ejecutar(caso, variante)
                    self.assertTrue(t["evaluada"])
                    self.assertEqual(t["estado"], "ok")
                    self.assertGreaterEqual(
                        t["ms"], sum(e["ms"] for e in t["eventos"]) - 0.001
                    )
                    self.assertGreaterEqual(t["cpu_ms"], 0)
                    self.assertIsNone(t["tokens"])

    def test_registra_incidentes_inyectados(self):
        for caso, estado, codigo in [
            ("caída de modelo", "error", "timeout"),
            ("fallo de herramienta", "degradado", "timeout"),
            ("límite de pasos", "limite", "ok"),
        ]:
            with self.subTest(caso=caso):
                t = ejecutar(caso, 0)
                self.assertEqual(t["estado"], estado)
                self.assertIsNone(t["evaluada"])
                self.assertIn(codigo, [e["estado"] for e in t["eventos"]])

    def test_tope_no_muestra_salida_de_herramienta(self):
        agente = AgenteAcademico.__new__(AgenteAcademico)
        agente.modelo = ModeloControlado("límite de pasos", ["listar_tareas"])
        tool = Mock()
        tool.invoke.return_value = "contenido PRIVADO"
        with (
            patch("rag.agente.POR_NOMBRE", {"listar_tareas": tool}),
            patch.object(obs, "guardar") as guardar,
        ):
            r = agente.responder("mi-pregunta@privada.cl")
        self.assertNotIn("PRIVADO", r.respuesta)
        t = guardar.call_args.args[0]
        self.assertEqual(r.traza_id, t["id"])
        self.assertNotIn("privada.cl", json.dumps(t))
        self.assertNotIn("PRIVADO", json.dumps(t))

    def test_error_no_filtra_texto_del_proveedor(self):
        agente = AgenteAcademico.__new__(AgenteAcademico)
        agente.modelo = Mock()
        agente.modelo.invoke.side_effect = TimeoutError("secreto-proveedor")
        with patch.object(obs, "guardar") as guardar, self.assertRaises(TimeoutError):
            agente.responder("otra-pregunta-privada", session_id="sesion-secreta")
        cadena = json.dumps(guardar.call_args.args[0])
        for texto in ["secreto-proveedor", "otra-pregunta-privada", "sesion-secreta"]:
            self.assertNotIn(texto, cadena)

    def test_conteo_del_proveedor(self):
        agente = AgenteAcademico.__new__(AgenteAcademico)
        agente.modelo = Mock()
        agente.modelo.invoke.return_value = AIMessage(
            content="Hola",
            usage_metadata={"input_tokens": 6, "output_tokens": 2, "total_tokens": 8},
        )
        with patch.object(obs, "guardar") as guardar:
            r = agente.responder("hola")
        self.assertEqual((r.tokens_entrada, r.tokens_salida), (6, 2))
        self.assertEqual(guardar.call_args.args[0]["tokens"], 8)

    def test_concurrencia_retencion_desactivacion(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch.object(config, "OBS_DB", str(Path(d) / "trazas.db")),
            patch.object(config, "OBS_ACTIVA", True),
        ):
            filas = [obs.Traza().cerrar() for _ in range(12)]
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(obs.guardar, filas))
            self.assertEqual(len(obs.leer()), 12)
            with closing(sqlite3.connect(config.OBS_DB)) as db, db:
                db.execute(
                    "UPDATE trazas SET utc='2000-01-01' WHERE id=?", (filas[0]["id"],)
                )
            self.assertEqual(len(obs.leer()), 11)
            with patch.object(config, "OBS_ACTIVA", False):
                obs.guardar(obs.Traza().cerrar())
            self.assertEqual(len(obs.leer()), 11)

    def test_disco_inaccesible_no_interrumpe_agente(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch.object(config, "OBS_DB", d),
            self.assertLogs(obs.logger, level="WARNING"),
        ):
            obs.guardar(obs.Traza().cerrar())

    def test_memoria_excluye_otro_perfil_y_filas_sin_dueno(self):
        db = mongomock.MongoClient().ep3
        with (
            patch.object(vectorstore, "get_collection", side_effect=lambda n: db[n]),
            patch.object(config, "USUARIO_ID", "perfil-a"),
        ):
            vectorstore.guardar_mensaje("uno", "user", "propio")
            with patch.object(config, "USUARIO_ID", "perfil-b"):
                vectorstore.guardar_mensaje("dos", "user", "ajeno")
            db[config.CONVERSATIONS_COLLECTION].insert_one(
                {"session_id": "tres", "rol": "user", "contenido": "legacy"}
            )
            self.assertEqual(
                [r["contenido"] for r in vectorstore.obtener_memoria_larga("actual")],
                ["propio"],
            )

    def test_web_desactivada_no_envia_consultas(self):
        with (
            patch.object(config, "USAR_FUENTE_EXTERNA", False),
            patch("rag.herramientas._buscar_web") as web,
        ):
            buscar_en_web.invoke({"consulta": "datos locales"})
            web.assert_not_called()

    def test_oraculo_rechaza_duplicados(self):
        col = mongomock.MongoClient().ep3.tareas
        self.assertFalse(verificar("agenda breve", "Tarea-001, Tarea-001", col, 1))
        self.assertFalse(verificar("prioridad", "1. Tarea-001, 2. Tarea-002", col, 2))

    def test_json_incrustado_y_vista_vacia(self):
        self.assertIn('type="application/json">[]</script>', render_html([]))
        self.assertNotIn(
            "</script><script>alert", render_html([{"caso": "</script><script>alert"}])
        )


if __name__ == "__main__":
    unittest.main()
