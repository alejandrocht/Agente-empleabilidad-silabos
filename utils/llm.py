"""
Fabrica del LLM (modelo de lenguaje) configurable.

Aqui aislamos COMO se crea el modelo de IA. La gracia es que NO sabemos todavia que
proveedor usaremos (Gemini, Groq, OpenAI/GPT, Together...). Por eso usamos
init_chat_model de LangChain, que con una sola linea soporta muchos proveedores.

Para cambiar de proveedor solo se edita el .env (LLM_PROVIDER y LLM_MODEL), nunca el codigo.
"""
from __future__ import annotations

import os

# init_chat_model es la funcion "universal" de LangChain: le dices el proveedor y el
# modelo, y te devuelve el objeto de chat listo para usar (.invoke(...)).
from langchain.chat_models import init_chat_model


def obtener_llm():
    """Crea y devuelve el modelo de lenguaje segun lo configurado en el .env."""
    # Proveedor: de donde sale la IA. Por defecto Google Gemini ("google_genai").
    # Otros valores validos: "groq", "openai", "together", etc.
    proveedor = os.getenv("LLM_PROVIDER", "google_genai")

    # Modelo concreto dentro de ese proveedor. Por defecto un Gemini rapido.
    modelo = os.getenv("LLM_MODEL", "gemini-2.0-flash")

    # Temperatura: que tan "creativa" es la IA. 0 = respuestas precisas y estables,
    # que es justo lo que queremos para generar Cypher correcto.
    temperatura = float(os.getenv("LLM_TEMPERATURE", "0"))

    # Construimos el modelo. init_chat_model lee solo la API key del proveedor desde
    # las variables de entorno (ej. GOOGLE_API_KEY para Gemini).
    return init_chat_model(
        model=modelo,
        model_provider=proveedor,
        temperature=temperatura,
    )
