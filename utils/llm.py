"""
Fabrica del LLM (modelo de lenguaje) configurable, con PUENTE / fallback.

Soporta varios proveedores sin tocar codigo, solo cambiando el .env:
"openai", "google_genai", "nvidia" u "ollama". Cada rama importa su paquete
solo si ese proveedor se usa, asi no hace falta tener todos instalados a la vez.

PUENTE (fallback automatico):
  - LLM_PROVIDER  = proveedor PRINCIPAL (el que se intenta primero).
  - LLM_FALLBACK  = proveedor(es) de RESPALDO, separados por comas.
  Si el principal falla en tiempo de ejecucion (por ejemplo OpenAI devuelve un
  429 por falta de cuota), LangChain reintenta automaticamente con el siguiente.

  Ejemplo para "usar Gemini ahora y OpenAI cuando tenga saldo":
      LLM_PROVIDER=openai
      LLM_FALLBACK=google_genai
  Hoy OpenAI da error de cuota -> responde Gemini. El dia que cargues credito en
  OpenAI, empezara a responder OpenAI solo, sin cambiar nada mas.

Cada proveedor tiene su PROPIO modelo (el modelo de OpenAI no vale para Gemini),
por eso hay OPENAI_MODEL, GEMINI_MODEL, NVIDIA_MODEL, OLLAMA_MODEL. La variable
LLM_MODEL, si esta definida, solo sobreescribe el modelo del proveedor PRINCIPAL
(se mantiene por compatibilidad con la config anterior).
"""
from __future__ import annotations

import os

# Modelo por defecto de cada proveedor (se usa si no lo defines en el .env).
MODELO_POR_DEFECTO = {
    "openai": "gpt-4o-mini",
    "google_genai": "gemini-2.5-flash",
    "nvidia": "meta/llama-3.3-70b-instruct",
    "ollama": "llama3.1",
}


def _crear_modelo(proveedor: str, temperatura: float, modelo: str | None = None):
    """Crea UN modelo del proveedor indicado. `modelo=None` usa el default del proveedor."""
    proveedor = proveedor.lower()
    # Si no nos pasan modelo explicito, usamos el env por proveedor o el default.
    if proveedor == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=modelo or os.getenv("OPENAI_MODEL", MODELO_POR_DEFECTO["openai"]),
            temperature=temperatura,
        )

    if proveedor == "google_genai":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=modelo or os.getenv("GEMINI_MODEL", MODELO_POR_DEFECTO["google_genai"]),
            temperature=temperatura,
        )

    if proveedor == "nvidia":
        from langchain_nvidia_ai_endpoints import ChatNVIDIA

        return ChatNVIDIA(
            model=modelo or os.getenv("NVIDIA_MODEL", MODELO_POR_DEFECTO["nvidia"]),
            base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            temperature=temperatura,
        )

    if proveedor == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=modelo or os.getenv("OLLAMA_MODEL", MODELO_POR_DEFECTO["ollama"]),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=temperatura,
        )

    raise ValueError(
        f"LLM_PROVIDER desconocido: {proveedor!r}. "
        "Usa 'openai', 'google_genai', 'nvidia' u 'ollama'."
    )


def obtener_llm():
    """Devuelve el LLM principal, envuelto con sus respaldos (puente/fallback) si los hay."""
    temperatura = float(os.getenv("LLM_TEMPERATURE", "0"))

    proveedor = os.getenv("LLM_PROVIDER", "openai").lower()
    # LLM_MODEL (si existe) solo sobreescribe el modelo del proveedor PRINCIPAL.
    modelo_principal = os.getenv("LLM_MODEL") or None

    principal = _crear_modelo(proveedor, temperatura, modelo_principal)

    # Leemos la lista de respaldos: "google_genai, nvidia" -> ["google_genai", "nvidia"].
    # Ignoramos vacios y cualquier respaldo que sea igual al proveedor principal.
    respaldos_raw = os.getenv("LLM_FALLBACK", "")
    nombres_respaldo = [
        p.strip().lower()
        for p in respaldos_raw.split(",")
        if p.strip() and p.strip().lower() != proveedor
    ]

    # Sin respaldos: devolvemos el modelo principal tal cual.
    if not nombres_respaldo:
        return principal

    # Con respaldos: cada uno usa su propio modelo por defecto (nunca LLM_MODEL).
    respaldos = [_crear_modelo(nombre, temperatura) for nombre in nombres_respaldo]
    # with_fallbacks: si el principal lanza una excepcion al invocar, prueba el siguiente.
    return principal.with_fallbacks(respaldos)
