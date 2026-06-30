"""
Fabrica del LLM (modelo de lenguaje) configurable.

Soporta 3 proveedores para poder testear con cualquiera sin tocar codigo,
solo cambiando LLM_PROVIDER en el .env: "nvidia", "ollama" o "google_genai".
Cada rama importa su paquete solo si ese proveedor esta activo, asi no hace
falta tener instalados los 3 paquetes a la vez.
"""
from __future__ import annotations

import os


def obtener_llm():
    """Crea y devuelve el modelo de lenguaje segun LLM_PROVIDER en el .env."""
    proveedor = os.getenv("LLM_PROVIDER", "nvidia").lower()
    temperatura = float(os.getenv("LLM_TEMPERATURE", "0"))

    if proveedor == "nvidia":
        from langchain_nvidia_ai_endpoints import ChatNVIDIA

        return ChatNVIDIA(
            model=os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct"),
            base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            temperature=float(os.getenv("NVIDIA_TEMPERATURE", temperatura)),
        )

    if proveedor == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "llama3.1"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=float(os.getenv("OLLAMA_TEMPERATURE", temperatura)),
        )

    if proveedor == "google_genai":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=os.getenv("LLM_MODEL", "gemini-2.0-flash"),
            temperature=float(os.getenv("LLM_TEMPERATURE", temperatura)),
        )

    raise ValueError(
        f"LLM_PROVIDER desconocido: {proveedor!r}. Usa 'nvidia', 'ollama' o 'google_genai'."
    )
