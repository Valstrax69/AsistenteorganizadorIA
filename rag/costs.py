"""
Costo por interacción.

Los embeddings son LOCALES => su costo es 0 (no hay tokens facturados). El
único costo variable es la generación con Groq, que se calcula a partir de los
tokens reales devueltos por la API.

IMPORTANTE: las tarifas de abajo son APROXIMADAS y deben verificarse contra la
página de precios vigente de Groq (https://groq.com/pricing). Puedes
sobreescribirlas sin tocar el código con las variables de entorno
GROQ_PRICE_IN / GROQ_PRICE_OUT (USD por 1.000.000 de tokens).
"""

from __future__ import annotations

import os

# USD por 1.000.000 de tokens. Valores de referencia (verificar en Groq).
PRECIOS_GROQ_USD_POR_1M: dict[str, dict[str, float]] = {
    "qwen/qwen3.6-27b": {"entrada": 0.29, "salida": 0.59},
    "qwen/qwen3-32b": {"entrada": 0.29, "salida": 0.59},
    "llama-3.3-70b-versatile": {"entrada": 0.59, "salida": 0.79},
    "llama-3.1-8b-instant": {"entrada": 0.05, "salida": 0.08},
}

# Tarifa por defecto si el modelo no está en la tabla (evita costo 0 silencioso).
_FALLBACK = {"entrada": 0.30, "salida": 0.60}


def _precios(modelo: str) -> dict[str, float]:
    override_in = os.getenv("GROQ_PRICE_IN")
    override_out = os.getenv("GROQ_PRICE_OUT")
    if override_in is not None and override_out is not None:
        return {"entrada": float(override_in), "salida": float(override_out)}
    return PRECIOS_GROQ_USD_POR_1M.get(modelo, _FALLBACK)


def calcular_costo_chat(modelo: str, tokens_entrada: int, tokens_salida: int) -> float:
    p = _precios(modelo)
    costo = (tokens_entrada / 1_000_000) * p["entrada"] + (tokens_salida / 1_000_000) * p["salida"]
    return round(costo, 8)
