"""Fábrica OpenAI heredada y limitada al normalizador curricular.

El agente conversacional usa los perfiles explícitos de ``agente.utils.llm``. Esta fábrica
permanece únicamente para los cuatro roles del análisis curricular.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from agente.config.settings import decimal, entero, texto

ENV_MODELO_POR_ROL: dict[str, str] = {
    "analista_curricular": "OPENAI_MODEL_CURRICULAR",
    "inspector_curricular": "OPENAI_MODEL_INSPECTOR_CURRICULAR",
    "analista_curricular_residual": "OPENAI_MODEL_CURRICULAR_RESIDUAL",
    "inspector_curricular_residual": "OPENAI_MODEL_INSPECTOR_CURRICULAR_RESIDUAL",
}

MODELO_CURRICULAR_DEFAULT = "gpt-5.6-luna"
MODELO_CURRICULAR_RESIDUAL_DEFAULT = "gpt-5.6-terra"


def _modelo_para_rol(rol: str) -> str:
    """Obtiene un modelo curricular explícito o rechaza roles ajenos."""
    variable = ENV_MODELO_POR_ROL.get(rol)
    if variable:
        modelo_rol = texto(variable)
        if modelo_rol:
            return modelo_rol
    if rol in {"analista_curricular", "inspector_curricular"}:
        return texto("OPENAI_MODEL_CURRICULAR", MODELO_CURRICULAR_DEFAULT) \
            or MODELO_CURRICULAR_DEFAULT
    if rol in {"analista_curricular_residual", "inspector_curricular_residual"}:
        return texto(
            "OPENAI_MODEL_CURRICULAR_RESIDUAL",
            MODELO_CURRICULAR_RESIDUAL_DEFAULT,
        ) or MODELO_CURRICULAR_RESIDUAL_DEFAULT
    raise ValueError(f"Rol curricular no soportado: {rol}")


def obtener_llm(rol: str = "analista_curricular") -> ChatOpenAI:
    """Crea un ChatOpenAI para uno de los roles del normalizador curricular."""
    api_key = texto("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY no está definida en backend/.env")

    # Tres reintentos cubren errores transitorios de red y límites temporales de OpenAI.
    return ChatOpenAI(
        model=_modelo_para_rol(rol),
        temperature=decimal("LLM_TEMPERATURE", 0),
        api_key=SecretStr(api_key),
        timeout=decimal("LLM_TIMEOUT_SECONDS", 120),
        max_retries=entero("LLM_MAX_RETRIES", 2),
    )
