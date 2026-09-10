"""
Evaluación del pipeline RAG.

Recorre las preguntas de `evaluation/dataset.json`, ejecuta el pipeline
completo (retrieval + generación con Groq) y calcula métricas de calidad.

Se intenta usar RAGAS con:
- LLM juez = Groq (vía langchain-groq), y
- embeddings = los mismos embeddings locales del proyecto.

RAGAS por defecto asume OpenAI, así que hay que inyectarle ambos clientes.
Si RAGAS no está instalado o su API cambió de versión, se cae a un conjunto de
métricas simples (cobertura de contexto y solapamiento léxico) para que la
evaluación siempre produzca un resultado. Requiere las dependencias de
`requirements-eval.txt`.

Uso:
    python -m evaluation.run_eval
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from rag.config import GROQ_API_KEY, GROQ_MODEL
from rag.generator import get_rag_generator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATASET_PATH = Path(__file__).parent / "dataset.json"
RESULTS_PATH = Path(__file__).parent / "results.json"


def _ejecutar_pipeline() -> list[dict]:
    casos = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    generador = get_rag_generator()
    filas = []
    for caso in casos:
        logger.info("RAG: %s", caso["pregunta"])
        r = generador.responder(caso["pregunta"])
        filas.append(
            {
                "user_input": caso["pregunta"],
                "response": r.respuesta,
                "retrieved_contexts": [f["texto"] for f in r.fuentes] or [""],
                "reference": caso["referencia"],
            }
        )
    return filas


def _evaluar_con_ragas(filas: list[dict]) -> dict | None:
    try:
        from langchain_groq import ChatGroq
        from langchain_core.embeddings import Embeddings
        from ragas import EvaluationDataset, evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )

        from rag.embeddings import get_embeddings

        class _EmbeddingsLocales(Embeddings):
            def __init__(self) -> None:
                self._e = get_embeddings()

            def embed_documents(self, textos):
                return self._e.embed_documents(list(textos))

            def embed_query(self, texto):
                return self._e.embed_query(texto)

        juez = LangchainLLMWrapper(ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=0))
        emb = LangchainEmbeddingsWrapper(_EmbeddingsLocales())

        dataset = EvaluationDataset.from_list(filas)
        resultado = evaluate(
            dataset=dataset,
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
            llm=juez,
            embeddings=emb,
        )
        logger.info("RAGAS OK: %s", resultado)
        return {"motor": "ragas", "metricas": resultado.to_pandas().to_dict(orient="records")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAGAS no disponible o falló (%s). Usando métricas simples.", exc)
        return None


def _tokens(texto: str) -> set[str]:
    return {t for t in "".join(c.lower() if c.isalnum() else " " for c in texto).split() if len(t) > 3}


def _evaluar_simple(filas: list[dict]) -> dict:
    """Fallback sin dependencias externas: proxies de recall de contexto y de
    cobertura de la respuesta respecto a la referencia (solapamiento léxico)."""
    detalle = []
    for f in filas:
        ref = _tokens(f["reference"])
        ctx = _tokens(" ".join(f["retrieved_contexts"]))
        resp = _tokens(f["response"])
        recall_ctx = len(ref & ctx) / len(ref) if ref else 0.0
        cobertura_resp = len(ref & resp) / len(ref) if ref else 0.0
        detalle.append(
            {
                "user_input": f["user_input"],
                "context_recall_proxy": round(recall_ctx, 3),
                "answer_coverage_proxy": round(cobertura_resp, 3),
            }
        )
    prom = lambda k: round(sum(d[k] for d in detalle) / len(detalle), 3) if detalle else 0.0
    return {
        "motor": "simple",
        "promedios": {
            "context_recall_proxy": prom("context_recall_proxy"),
            "answer_coverage_proxy": prom("answer_coverage_proxy"),
        },
        "detalle": detalle,
    }


def main() -> None:
    filas = _ejecutar_pipeline()
    resultado = _evaluar_con_ragas(filas) or _evaluar_simple(filas)
    RESULTS_PATH.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Resultados guardados en %s (motor=%s)", RESULTS_PATH, resultado["motor"])
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
