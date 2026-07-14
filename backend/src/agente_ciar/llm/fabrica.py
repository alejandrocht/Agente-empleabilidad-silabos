"""Fábrica OpenAI con un modelo configurable para cada rol del agente.

La cascada es: variable específica del rol, ``OPENAI_MODEL`` global y finalmente el modelo
seguro del código. ChatOpenAI integra automáticamente las trazas configuradas en LangSmith.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from agente_ciar.config.settings import decimal, texto

# El modelo económico es suficiente para extracción, Cypher, resumen y análisis inicial.
MODELO_DEFAULT = "gpt-4o-mini"
ENV_MODELO_POR_ROL: dict[str, str] = {
    "resuelve_entidad": "OPENAI_MODEL_ENTIDAD",
    "genera_cypher": "OPENAI_MODEL_CYPHER",
    "analiza_resultado": "OPENAI_MODEL_ANALISIS",
    "resumen_memoria": "OPENAI_MODEL_RESUMEN",
    "inspector": "OPENAI_MODEL_INSPECTOR",
}


def _modelo_para_rol(rol: str) -> str:
    """Obtiene el modelo específico del rol y aplica la cascada de respaldo local."""
    variable = ENV_MODELO_POR_ROL.get(rol)
    if variable:
        modelo_rol = texto(variable)
        if modelo_rol:
            return modelo_rol
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
        max_retries=3,
    )
