"""Fábrica OpenAI con un modelo configurable para cada rol del agente.

La cascada es: variable específica del rol, ``OPENAI_MODEL`` global y finalmente el modelo
seguro del código. ChatOpenAI integra automáticamente las trazas configuradas en LangSmith.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from agente.config.settings import decimal, entero, texto

# El modelo económico es suficiente para extracción, Cypher, resumen y análisis inicial.
MODELO_DEFAULT = "gpt-4o-mini"
ENV_MODELO_POR_ROL: dict[str, str] = {
    "resuelve_entidad": "OPENAI_MODEL_ENTIDAD",
    "genera_cypher": "OPENAI_MODEL_CYPHER",
    "analiza_resultado": "OPENAI_MODEL_ANALISIS",
    "resumen_memoria": "OPENAI_MODEL_RESUMEN",
    "inspector": "OPENAI_MODEL_INSPECTOR",
    "analista_curricular": "OPENAI_MODEL_CURRICULAR",
    "inspector_curricular": "OPENAI_MODEL_INSPECTOR_CURRICULAR",
    "analista_curricular_residual": "OPENAI_MODEL_CURRICULAR_RESIDUAL",
    "inspector_curricular_residual": "OPENAI_MODEL_INSPECTOR_CURRICULAR_RESIDUAL",
}

MODELO_CURRICULAR_DEFAULT = "gpt-5.6-luna"
MODELO_CURRICULAR_RESIDUAL_DEFAULT = "gpt-5.6-terra"


def _modelo_para_rol(rol: str) -> str:
    """Obtiene el modelo específico del rol y aplica la cascada de respaldo local."""
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
    return texto("OPENAI_MODEL", MODELO_DEFAULT) or MODELO_DEFAULT


def obtener_llm(rol: str = "default") -> ChatOpenAI:
    """Crea un ChatOpenAI para el rol o informa claramente que falta la API key."""
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
