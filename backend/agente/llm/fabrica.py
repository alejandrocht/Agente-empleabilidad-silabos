"""Fábrica OpenAI con un modelo configurable para cada rol del agente.

La cascada es: variable específica del rol, ``OPENAI_MODEL`` global y finalmente el modelo
seguro del código. ChatOpenAI integra automáticamente las trazas configuradas en LangSmith.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from agente.config.settings import (
    ConfiguracionNormalizadorCurricular,
    decimal,
    entero,
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


def _modelo_para_rol(
    rol: str,
    configuracion_curricular: ConfiguracionNormalizadorCurricular | None,
) -> str:
    """Obtiene el modelo del snapshot curricular o la cascada no curricular."""
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
    """Crea un ChatOpenAI; los roles curriculares requieren su snapshot explícito."""
    api_key = texto("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY no está definida en backend/.env")
    if rol in _ROLES_CURRICULARES and configuracion_curricular is None:
        raise ValueError(
            "Los roles curriculares requieren configuracion_curricular de la ejecución"
        )
    configuracion = configuracion_curricular if rol in _ROLES_CURRICULARES else None

    kwargs: dict[str, object] = {
        "model": _modelo_para_rol(rol, configuracion),
        "temperature": (
            configuracion.temperatura_llm
            if configuracion is not None
            else decimal("LLM_TEMPERATURE", 0)
        ),
        "api_key": SecretStr(api_key),
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
    if configuracion is not None:
        kwargs["reasoning_effort"] = configuracion.esfuerzo_para_rol(rol)
    return ChatOpenAI(**kwargs)
