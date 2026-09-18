"""Fábrica LLM con configuración inmutable por rol y proveedor.

El flujo curricular usa OpenAI o el endpoint compatible de Ollama según el snapshot de la
ejecución. Los demás roles mantienen la cascada histórica de modelos OpenAI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from agente.config.settings import (
    ConfiguracionNormalizadorCurricular,
    decimal,
    entero,
    modelo_dev,
    modo_dev,
    texto,
)

# El modelo económico es suficiente para extracción, Cypher, resumen y análisis inicial.
MODELO_DEFAULT = "gpt-4o-mini"
ENV_MODELO_POR_ROL: dict[str, str] = {
    "resuelve_entidad": "OPENAI_MODEL_ENTIDAD",
    "genera_cypher": "OPENAI_MODEL_CYPHER",
    "analiza_resultado": "OPENAI_MODEL_ANALISIS",
    "resumen_memoria": "OPENAI_MODEL_RESUMEN",
    "inspector": "OPENAI_MODEL_INSPECTOR",
}

_ROLES_CURRICULARES = frozenset(
    {
        "analista_curricular",
    }
)

_RUTA_ENV = Path(__file__).resolve().parents[2] / ".env"


def _api_key_openai() -> str:
    """Read the key from the process, then backend/.env without exposing it."""
    api_key = texto("OPENAI_API_KEY")
    if api_key:
        return api_key
    valores = dotenv_values(_RUTA_ENV)
    return str(valores.get("OPENAI_API_KEY") or "").strip()


def _modelo_para_rol(
    rol: str,
    configuracion_curricular: ConfiguracionNormalizadorCurricular | None,
) -> str:
    """Obtiene el modelo del snapshot curricular o la cascada no curricular."""
    if modo_dev():
        return modelo_dev()
    if rol in _ROLES_CURRICULARES:
        if configuracion_curricular is None:
            raise ValueError(
                "Los roles curriculares requieren configuracion_curricular de la ejecución"
            )
        return configuracion_curricular.modelo_para_rol(rol)
    variable = ENV_MODELO_POR_ROL.get(rol)
    if variable:
        modelo_rol = texto(variable)
        if modelo_rol:
            return modelo_rol
    return texto("OPENAI_MODEL", MODELO_DEFAULT) or MODELO_DEFAULT


def obtener_llm(
    rol: str = "default",
    *,
    configuracion_curricular: ConfiguracionNormalizadorCurricular | None = None,
) -> ChatOpenAI:
    """Crea el cliente del proveedor configurado para el rol solicitado."""
    if rol in _ROLES_CURRICULARES and configuracion_curricular is None:
        raise ValueError(
            "Los roles curriculares requieren configuracion_curricular de la ejecución"
        )
    configuracion = configuracion_curricular if rol in _ROLES_CURRICULARES else None
    proveedor = configuracion.proveedor_llm if configuracion is not None else "openai"
    en_dev = modo_dev()
    if en_dev:
        api_key = texto("DEV_API_KEY", "dev-not-needed")
    elif proveedor == "openai":
        api_key = _api_key_openai()
    else:
        api_key = "ollama"
    if proveedor == "openai" and not en_dev and not api_key:
        raise ValueError("OPENAI_API_KEY no está definida en backend/.env")

    kwargs: dict[str, Any] = {
        "model": _modelo_para_rol(rol, configuracion),
        "temperature": (
            configuracion.temperatura_llm
            if configuracion is not None
            else decimal("LLM_TEMPERATURE", 0)
        ),
        "api_key": SecretStr(api_key if en_dev or proveedor == "openai" else "ollama"),
        "timeout": (
            configuracion.timeout_llm_seconds
            if configuracion is not None
            else decimal("LLM_TIMEOUT_SECONDS", 120)
        ),
        "max_retries": (
            configuracion.max_reintentos_llm
            if configuracion is not None
            else entero("LLM_MAX_RETRIES", 2)
        ),
    }
    dev_base_url = texto("DEV_BASE_URL") if en_dev else ""
    if dev_base_url:
        kwargs["base_url"] = dev_base_url
    elif configuracion is not None and proveedor == "ollama":
        kwargs["base_url"] = configuracion.base_url_llm
    if configuracion is not None and proveedor != "ollama":
        kwargs["reasoning_effort"] = configuracion.esfuerzo_para_rol(rol)
    return ChatOpenAI(**kwargs)
