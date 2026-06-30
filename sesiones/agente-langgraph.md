# Agente LangGraph (consola)

Agente de consola que responde preguntas en español sobre el grafo Neo4j del CIAR (carreras, cursos, evaluación de desempeño, etc.), convirtiendo lenguaje natural a Cypher con un LLM.

## Arquitectura

`main.py` carga `.env`, construye el grafo (`agent.py`) y corre loop de consola (`input()` → stream del grafo → imprime respuesta + camino recorrido).

Grafo LangGraph de 8 nodos, lineal con reintento:

```
START → obtiene_pregunta → obtiene_grafo → resuelve_entidad → genera_cypher
      → valida_cypher ──(error, quedan intentos)──→ genera_cypher
      → valida_cypher ──(error, sin intentos)──→ devuelve_resultado
      → valida_cypher ──(ok)──→ ejecuta_cypher ──(error)──→ genera_cypher / devuelve_resultado
      → ejecuta_cypher ──(ok)──→ analiza_resultado → devuelve_resultado → END
```

`MAX_INTENTOS = 2` (agent.py). Estado compartido (`estado.py:EstadoAgente`, TypedDict total=False): `pregunta, schema_texto, entidades, cypher, filas, respuesta, intentos, error`.

### Nodos (`nodos/`)

| Nodo | Usa LLM | Rol |
|---|---|---|
| `obtiene_pregunta` | No | Limpia (`strip`) la pregunta del usuario |
| `obtiene_grafo` | No | Mete en el estado el schema de Neo4j en texto (`utils/neo4j.construir_schema_texto`, cacheado con `lru_cache`) |
| `resuelve_entidad` | Sí | Anti-alucinación: LLM detecta entidades mencionadas por nombre → busca su `id_*` real en Neo4j con `apoc.text.clean()` (sin depender de campo `nombre_norm`) |
| `genera_cypher` | Sí | LLM convierte pregunta + schema + entidades resueltas → Cypher. Limpia bloques ```` ``` ```` del LLM |
| `valida_cypher` | No | Seguridad: solo lectura (bloquea CREATE/MERGE/DELETE/SET/...), labels/relaciones deben existir en el schema real, prohíbe `CONTAINS`/`nombre_norm` y flechas `->`/`<-` en el Cypher final, valida sintaxis con `EXPLAIN` (no ejecuta) |
| `ejecuta_cypher` | No | Corre el Cypher validado (`execute_read`), guarda filas o error |
| `analiza_resultado` | Sí | Redacta la respuesta final en español a partir de las filas crudas |
| `devuelve_resultado` | No | Si hubo error en el camino, arma mensaje amable; si no, deja la respuesta lista |

`nodos/nodo.py`: `Nodo` (clase base, `__call__` abstracto) y `NodoLLM` (subclase que en `__init__` ya crea `self.llm = obtener_llm()` y carga `self.prompt` desde `prompts/<nombre>.md`).

### Utils (`utils/`)

- `config.py` — `cargar_entorno()` lee `.env` a mano (sin librerías) y mete los valores en `os.environ`.
- `llm.py` — `obtener_llm()` instancia directamente la clase de chat del proveedor activo (`ChatNVIDIA` / `ChatOllama` / `ChatGoogleGenerativeAI`) segun `LLM_PROVIDER` (default `nvidia`). Cada rama importa su paquete solo si esta activa. Ver seccion "Multi-proveedor" abajo.
- `neo4j.py` — driver cacheado (`lru_cache`), introspección de schema en vivo (labels, props, topología de relaciones con frecuencia, ejemplos de nombres reales), `ejecutar_lectura()` (transacción de solo lectura) y `validar_sintaxis()` (vía `EXPLAIN`, no ejecuta).
- `prompts.py` — `cargar_prompt(nombre)` lee `prompts/<nombre>.md`.

Prompts en `prompts/`: `resuelve_entidad.md`, `genera_cypher.md` (incluye "REGLA DE ORO": usar `id_*` de entidades ya resueltas, nunca `CONTAINS`/`nombre_norm`/flechas en el Cypher final, solo lectura, `LIMIT 25`), `analiza_resultado.md` (fuerza español, prohíbe inventar datos).

## Problema encontrado (2026-06-30) — migración a NVIDIA quedó a medias

Commit `a220f6a` ("nvidia llm") agregó `langchain-nvidia-ai-endpoints` a `requirements.txt` y configuró `.env` con variables propias (`NVIDIA_API_KEY`, `NVIDIA_MODEL`, `NVIDIA_BASE_URL`, `NVIDIA_TEMPERATURE`), pero **nunca se tocó `utils/llm.py`**:

- `obtener_llm()` solo lee `LLM_PROVIDER` / `LLM_MODEL` (default `google_genai` / `gemini-2.0-flash`) — no existe ningún `grep` de `NVIDIA` en el código Python.
- El `.env` real no tiene `LLM_PROVIDER` ni `GOOGLE_API_KEY` → con la config actual el agente intentaría usar Gemini sin key.
- `.env.example` tampoco se actualizó: sigue documentando solo Gemini.
- Además el `.venv` actual no tiene el paquete base `langchain` instalado (solo `langchain-core`, `langchain-nvidia-ai-endpoints`, `langchain-ollama` — este último ni siquiera está en `requirements.txt`). `from langchain.chat_models import init_chat_model` (utils/llm.py:16) falla con `ModuleNotFoundError` apenas arranca, antes de llegar a ningún proveedor.

Resultado (antes del fix): `python main.py` no corría tal cual estaba.

## Fix aplicado (2026-06-30) — `utils/llm.py` multi-proveedor

Alcance real pedido por el usuario: no era solo "arreglar NVIDIA", sino poder testear con cualquiera de los 3 proveedores ya probados (Ollama local, NVIDIA, Gemini) cambiando solo el `.env`.

`obtener_llm()` ahora hace branching explícito por `LLM_PROVIDER` (`nvidia` | `ollama` | `google_genai`, default `nvidia`), instanciando directamente `ChatNVIDIA` / `ChatOllama` / `ChatGoogleGenerativeAI` con import perezoso dentro de cada rama — así no hace falta tener los 3 paquetes instalados a la vez, y se evita depender de `init_chat_model` (que requiere el paquete base `langchain`, no instalado en el venv y ya no usado en el codigo).

Variables por proveedor (todas en `.env.example`):
- `nvidia`: `NVIDIA_API_KEY`, `NVIDIA_MODEL`, `NVIDIA_BASE_URL`, `NVIDIA_TEMPERATURE`
- `ollama`: `OLLAMA_MODEL`, `OLLAMA_BASE_URL` (default `http://localhost:11434`), `OLLAMA_TEMPERATURE`
- `google_genai`: `LLM_MODEL`, `GOOGLE_API_KEY`, usa `LLM_TEMPERATURE`

`requirements.txt`: se quitó `langchain` (base, ya sin uso) y se agregó `langchain-ollama` (usado en el código pero faltaba declarado).

Verificado: `obtener_llm()` instancia correctamente `ChatNVIDIA` y `ChatOllama`; `python main.py` corrió end-to-end con NVIDIA contra Neo4j real (pregunta "cuantos nodos hay en total" → respuesta correcta, recorrido completo de los 8 nodos).
