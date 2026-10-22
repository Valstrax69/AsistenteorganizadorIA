"""
Corre los casos de evaluation/casos_agente.json contra el agente real y deja
la evidencia en evaluation/resultados_agente.json.

Lo que verifica cada caso: que el agente haya llamado las herramientas que se
esperaban (ni mas ni menos en cuanto a las obligatorias). No verifica el texto
de la respuesta, porque un LLM no da dos veces la misma redaccion.

Uso:
    python -m evaluation.run_agente
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.agente import get_agente  # noqa: E402

RAIZ = Path(__file__).resolve().parent
CASOS = RAIZ / "casos_agente.json"
SALIDA = RAIZ / "resultados_agente.json"


def _evaluar(esperadas: list[str], usadas: list[str]) -> str:
    # PASS si se llamaron todas las esperadas. Para los casos que esperan cero
    # herramientas, PASS solo si efectivamente no llamo ninguna.
    if not esperadas:
        return "PASS" if not usadas else "FAIL"
    return "PASS" if all(e in usadas for e in esperadas) else "FAIL"


def _correr_simple(agente, caso: dict, session_id: str) -> dict:
    r = agente.responder(caso["pregunta"], session_id=session_id)
    return {
        "id": caso["id"],
        "tipo": caso["tipo"],
        "pregunta": caso["pregunta"],
        "herramientas_esperadas": caso["herramientas_esperadas"],
        "herramientas_usadas": r.herramientas_usadas,
        "pasos": r.pasos,
        "respuesta": r.respuesta,
        "resultado": _evaluar(caso["herramientas_esperadas"], r.herramientas_usadas),
    }


def _correr_secuencia(agente, caso: dict, session_id: str) -> dict:
    historial: list[dict] = []
    detalle = []
    ok = True
    for paso in caso["pasos"]:
        r = agente.responder(paso["pregunta"], historial=historial, session_id=session_id)
        resultado = _evaluar(paso["herramientas_esperadas"], r.herramientas_usadas)
        ok = ok and resultado == "PASS"
        historial.append({"rol": "user", "contenido": paso["pregunta"]})
        historial.append({"rol": "assistant", "contenido": r.respuesta})
        detalle.append(
            {
                "pregunta": paso["pregunta"],
                "herramientas_esperadas": paso["herramientas_esperadas"],
                "herramientas_usadas": r.herramientas_usadas,
                "respuesta": r.respuesta,
                "resultado": resultado,
            }
        )
    return {
        "id": caso["id"],
        "tipo": caso["tipo"],
        "pasos_detalle": detalle,
        "resultado": "PASS" if ok else "FAIL",
    }


def main() -> None:
    casos = json.loads(CASOS.read_text(encoding="utf-8"))
    agente = get_agente()
    session_id = f"eval-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    resultados = []
    for caso in casos:
        print(f"-> {caso['id']} ...", flush=True)
        try:
            if "pasos" in caso:
                resultados.append(_correr_secuencia(agente, caso, session_id))
            else:
                resultados.append(_correr_simple(agente, caso, session_id))
        except Exception as exc:  # noqa: BLE001
            resultados.append({"id": caso["id"], "resultado": "ERROR", "detalle": str(exc)})
        print(f"   {resultados[-1]['resultado']}")

    aprobados = sum(1 for r in resultados if r["resultado"] == "PASS")
    snapshot = {
        "ejecutado_en": datetime.now().isoformat(timespec="seconds"),
        "total": len(resultados),
        "aprobados": aprobados,
        "casos": resultados,
    }
    SALIDA.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{aprobados}/{len(resultados)} PASS. Evidencia en {SALIDA.name}")


if __name__ == "__main__":
    main()
