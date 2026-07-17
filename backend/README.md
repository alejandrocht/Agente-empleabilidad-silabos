# Backend del Agente CIAR

Agente LangGraph que convierte preguntas en español a Cypher, valida que las consultas sean
de solo lectura y consulta el schema vivo de Neo4j. OpenAI es el único proveedor LLM; cada rol
puede seleccionar su modelo desde `.env`.

## Instalación

```powershell
cd backend
python -m pip install -e ".[dev]"
Copy-Item .env.example .env  # solo si todavía no existe
```

Completa `OPENAI_API_KEY` y las credenciales de Neo4j. Para habilitar trazas, completa también
`LANGSMITH_API_KEY`; `LANGSMITH_TRACING=true` ya viene en la plantilla.

## Ejecución

```powershell
python scripts/consola.py
uvicorn agente.api.servidor:app --reload --port 8001
python -m pytest
ruff check src tests scripts
mypy src
```

Todas las consultas pasan por una guarda central y se ejecutan en sesiones Neo4j de lectura.
La caché y la memoria son efímeras, tienen TTL y permanecen acotadas por proceso.

## Logs

En `INFO` aparecen eventos de negocio: memoria recibida y actualizada, decisiones de ruta,
estrategia, caché, entidades, Cypher, filas e inspección de la respuesta. Cada evento incluye
automáticamente la función que lo originó y usa el formato `[campo]: valor` en una sola línea:

```text
18:40:56.601 [nivel]: INFO [sesion]: ses-eb1636cec94a [evento]: decision.ruta_seleccionada [funcion]: agente.grafo.enrutado.ruta_tras_estrategia [desde]: selecciona_estrategia [hacia]: valida_cypher [motivo]: plantilla determinista
```

`DEBUG` agrega una línea por función finalizada con su duración. Los IDs de sesión se
pseudonimizan y los secretos, saltos de línea y campos excesivos se sanean de forma central.
Se controla desde `.env`:

```dotenv
LOG_FORMATO=legible  # usa json para ingestión por máquinas
LOG_NIVEL=INFO       # usa DEBUG para el perfil técnico por función
LOG_FUNCIONES=true
LOG_MAX_CHARS_CAMPO=800
LOG_SESION_COMPLETA=false
```
