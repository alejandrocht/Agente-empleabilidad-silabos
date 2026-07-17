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

Los eventos aparecen en la terminal en un formato legible. También se registra la entrada,
salida y duración de cada función del paquete `agente`, sin incluir argumentos ni valores de
retorno. Se controla desde `.env`:

```dotenv
LOG_FORMATO=legible  # usa json para ingestión por máquinas
LOG_NIVEL=INFO
LOG_FUNCIONES=true   # usa false en producción si se necesita menos volumen
```
