# Agente local Ollama + Neo4j — sesión

> Track del **agente consola local** (LangGraph + Ollama + LangSmith) sobre Neo4j Desktop.
> Distinto del bot CIAR canónico (Gemini Flash 2.0 + AuraDB) en `/Desktop/CIAR`.
> Carpeta del proyecto: `/Users/alejandromcht/Desktop/Prueba Neo4j`

---

## 2026-06-24 — Setup inicial, carga de data, fix de conexión

### Arquitectura original (punto de partida)
- **Neo4j Desktop 2026.05.0** (Instance02, id `9af4a8b5-92ae-466e-82c4-ae9f4f542623`) local en Mac. Bolt `127.0.0.1:7687`.
- **`agente_consola.py`**: grafo LangGraph `assistant ⇄ tools` (`MemorySaver`, recursion_limit 8).
- **Modelo**: `ChatOllama`, `qwen2.5:7b`, `temperature=0`, `num_ctx=32768`.
- **2 tools originales**: `buscar_grafo_ciar`, `describir_ontologia_ciar`.
- **Schema**: derivado de `ontologia.json` (hardcodeado).
- **`cargar_ontologia.py`**: loader incremental desde CSVs. IDs hash con prefijos (`FAC_`, `CAR_`, `CUR_`, `EMP_`, ...). `--reset` recarga todo.

### Data en Neo4j (conteos reales verificados con cypher-shell)
| Label | Total |
|---|---|
| RequerimientoLaboral | 120,817 |
| OfertaLaboral | 44,401 |
| Puesto | 44,401 |
| EvalDesempeno | 36,909 |
| Empresa | 9,483 |
| CoberturaCurricular | 455 |
| Industria | 314 |
| Herramienta | 121 |
| Habilidad | 117 |
| Curso / Silabo | 73 / 73 |
| Competencia | 54 |
| Carrera | 14 |
| Facultad | 7 |

### Bug resuelto: "Instance connection URL is not valid"
- **Causa**: bug UI Neo4j Desktop 2026.05.0 — concatena `server.default_advertised_address` (`127.0.0.1`) + host de `server.bolt.listen_address` (`0.0.0.0`) → URI basura `neo4j://127.0.0.10.0.0.0:7687`. La DB nunca estuvo rota.
- **Blocker real del agente**: `.env` tenía `NEO4J_PASSWORD=CHANGE_ME`. Con pass real (`CHANGE_ME`) conecta OK.
- **Fix**: comentar en `conf/neo4j.conf`:
  ```
  #server.bolt.listen_address=0.0.0.0:7687
  #server.bolt.advertised_address=127.0.0.1:7687
  ```
  Requiere Stop/Start de la instancia en Neo4j Desktop.
- **Cypher-shell**: necesita JRE bundled del Desktop, no el del sistema.

---

## 2026-06-25 — Refactor completo del agente (sesión activa)

### Problema del venv (importante para cualquier modelo que retome)
El proyecto se movió de `~/Downloads/Prueba Neo4j` a `~/Desktop/Prueba Neo4j`. El `.venv` NO es portable: `activate` queda con `VIRTUAL_ENV=` vacío.  
**Siempre correr con ruta directa**:
```bash
cd "/Users/alejandromcht/Desktop/Prueba Neo4j"
.venv/bin/python agente_consola.py
```
Alternativa permanente: `rm -rf .venv && /opt/homebrew/bin/python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt`.

---

### Cambio 1: Schema live desde Neo4j (eliminación de ontologia.json como fuente del LLM)

**Qué había**: `build_schema_text()` leía `ontologia.json` (1392 items). Lista plana de labels y relaciones, hardcodeada y potencialmente desactualizada.

**Qué hay ahora**: `introspect_schema()` cacheada con `@lru_cache(maxsize=1)` — corre 4 queries Cypher al startup, cachea por sesión:

1. **Labels + conteos**: `MATCH (n) RETURN labels(n)[0], count(n)`
2. **Props por label**: `CALL db.schema.nodeTypeProperties()`
3. **Topología con frecuencia**: `CALL db.schema.visualization()` + `MATCH ()-[r]->() RETURN type(r), count(*)`
4. **Samples de nombres reales**: detecta prop nombre por label (`nombre`, `nombre_carrera`, `nombre_curso`, etc., excepto `nombre_norm`) → 5 ejemplos reales por label

**Por qué samples importa**: el modelo ve nombres reales ("INGENIERÍA DE SISTEMAS", "Python", "BCP") en el schema → no inventa nombres.

**Detección de prop nombre por label** (crítico — cada label usa distinta prop):
```python
for p in props:
    if p == "nombre": name_prop = p; break
    if p.startswith("nombre_") and p != "nombre_norm": name_prop = p
```

**APOC NO instalado** en la instancia. Solo procs nativos: `db.schema.visualization()`, `db.schema.nodeTypeProperties()`, `db.labels()`.

`ontologia.json` queda **solo para el loader** (`cargar_ontologia.py`). El agente no lo lee.

---

### Cambio 2: LangSmith activado

En `load_env()`:
```python
os.environ.setdefault("LANGSMITH_PROJECT", "ciar-local-langgraph")
# si hay key y tracing no definido → activa automático
# replica aliases LANGCHAIN_* para compatibilidad
```
Variables en `.env`:
```
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=lsv2_pt_xxx
LANGSMITH_PROJECT=ciar-local-langgraph
```
Trazas suben solas. URL: https://smith.langchain.com → proyecto `ciar-local-langgraph`.

---

### Cambio 3: Emojis eliminados de todos los logs

`run_console()` ya no tiene emojis en ningún print. Logs limpios.

---

### Cambio 4: Few-shot examples + patrón 2 pasos (id-first)

**Problema raíz de alucinación**: el LLM generaba `WHERE c.nombre_norm CONTAINS 'sistemas'` o `{nombre_norm: 'INGENIERÍA DE SISTEMAS'}` (con mayúsculas y tilde). `nombre_norm` guarda `'ingenieria de sistemas'` (lowercase sin tilde) → match 0 filas.

**Solución arquitectónica**: **patrón 2 pasos obligatorio**:
1. `resolver_entidad(texto, label?)` → obtiene `id_*` real desde Neo4j
2. `buscar_grafo_ciar(pregunta_con_id)` → Cypher usa `{id_carrera: 'CAR_...'}` (exact match, O(1))

`CONTAINS` y `nombre_norm` **prohibidos en el Cypher final**. Solo viven dentro de `resolver_entidad`.

`FEW_SHOT_EXAMPLES` en `generate_cypher` — 8 ejemplos reales en el prompt:
- Con entidad nombrada: siempre muestran 2 pasos (resolver → id en Cypher)
- Sin entidad: Cypher directo (conteos globales, rankings)

---

### Cambio 5: Tool nueva — `resolver_entidad(texto, label="")`

```python
@tool
def resolver_entidad(texto: str, label: str = "") -> str:
```

- Normaliza `texto` con `unicodedata` (lowercase, sin tildes)
- Si `label` dado: busca solo en ese label
- Si no: busca en todos los labels que tengan `nombre_norm`
- Query: `MATCH (n:Label) WHERE n.nombre_norm CONTAINS $q RETURN nombre, id LIMIT 5`
- Devuelve JSON: `{texto_normalizado, matches: {Label: [{nombre, id}]}}`
- Si 0 matches: devuelve sugerencia de ortografía

**Ejemplo**:
```python
resolver_entidad("sistemas", "Carrera")
# → {"matches": {"Carrera": [{"nombre": "INGENIERÍA DE SISTEMAS", "id": "CAR_01375f53651cff38"}]}}

resolver_entidad("bcp")
# → {"matches": {"Puesto": ["BCP INTERN", "PRACTICANTE BCP"], "Empresa": ["BANCO DE CREDITO BCP"]}}
```

---

### Cambio 6: Validadores de Cypher

**`validate_read_only_cypher`** (existía): verifica que empiece en `MATCH/WITH/RETURN/CALL db.*` y no contenga palabras write (`CREATE/MERGE/DELETE/SET/...`).

**`validate_cypher_schema`** (nuevo): 3 validaciones:
1. **Labels inventados**: extrae `:Label` del Cypher con regex → compara contra labels reales de `introspect_schema()` → rechaza si hay desconocidos
2. **Rel types inventados**: extrae `[:REL]` → compara contra topología real
3. **CONTAINS bloqueado**: `re.search(r'\bCONTAINS\b', cypher)` → rechaza con mensaje "llama a resolver_entidad primero"
4. **nombre_norm con igualdad bloqueado**: `re.search(r'nombre_norm\s*[=:]\s*[\'"]', cypher)` → rechaza igual

Ambas validaciones corren en `generate_cypher` tras generar el Cypher. Si falla → `previous_error` se pasa al retry.

---

### Cambio 7: tool_choice="any" en primer turno

```python
has_tool_result = any(getattr(m, "type", None) == "tool" for m in state["messages"])
model = base.bind_tools(TOOLS) if has_tool_result else base.bind_tools(TOOLS, tool_choice="any")
```

Primer turno: fuerza uso de alguna tool (el modelo chico tiende a responder directo sin consultar Neo4j).
Turnos siguientes: libre.
Fallback: si `tool_choice` no soportado → `bind_tools` normal.

---

### Cambio 8: Fix recursion limit

**Error**: `Recursion limit of 8 reached without hitting a stop condition`

**Causa**: nuevo validador rechaza CONTAINS → `buscar_grafo_ciar` devuelve error → assistant reintenta → mismo Cypher malo → loop hasta límite 8.

**Fix 1**: `buscar_grafo_ciar` detecta error de validación CONTAINS/nombre_norm y devuelve `accion_requerida: resolver_entidad` en lugar de reintentar → rompe el loop:
```python
if "CONTAINS" in error_msg or "nombre_norm" in error_msg:
    return json.dumps({"accion_requerida": "resolver_entidad", "instruccion": "..."})
```

**Fix 2**: `.env` → `LANGGRAPH_RECURSION_LIMIT=20` (era 8, flujo 2 pasos necesita ~10-12 steps mínimo).

---

### Estado actual del agente (2026-06-25)

#### Tools disponibles (3)
| Tool | Qué hace |
|---|---|
| `buscar_grafo_ciar(pregunta)` | Genera Cypher con LLM + few-shot, valida schema, ejecuta en Neo4j, 2 intentos. Si ve CONTAINS → devuelve instrucción de usar resolver_entidad. |
| `describir_ontologia_ciar()` | Devuelve ontología completa en vivo (labels+conteos, props, topología, samples). |
| `resolver_entidad(texto, label?)` | Busca entidad por nombre normalizado. Devuelve id_* real. ÚNICO lugar donde vive CONTAINS. |

#### Flujo para preguntas con entidad nombrada
```
Usuario: "cursos de Ingeniería de Sistemas"
  1. assistant → resolver_entidad("sistemas", "Carrera")
     → {id_carrera: "CAR_01375f53651cff38", nombre: "INGENIERÍA DE SISTEMAS"}
  2. assistant → buscar_grafo_ciar("cursos de la carrera con id_carrera CAR_01375f53651cff38")
     → generate_cypher → MATCH (c:Carrera {id_carrera: 'CAR_01375f53651cff38'})-[:CONTIENE]->(cu:Curso) RETURN ...
     → validate_read_only_cypher ✓
     → validate_cypher_schema ✓ (no CONTAINS, labels reales)
     → ejecuta → filas reales
  3. assistant → responde en español con los datos
```

#### Flujo para preguntas globales (sin entidad específica)
```
Usuario: "top 5 empresas con más ofertas"
  1. assistant → buscar_grafo_ciar("top 5 empresas con mas ofertas")
     → MATCH (e:Empresa)-[:PUBLICA]->(o:OfertaLaboral) RETURN e.nombre, count(o) ORDER BY ... LIMIT 5
     → ejecuta → filas reales
  2. assistant → responde
```

#### Archivo .env actual
```env
NEO4J_URI=neo4j://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=CHANGE_ME
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_NUM_CTX=32768
OLLAMA_TEMPERATURE=0
LANGGRAPH_RECURSION_LIMIT=20
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=lsv2_pt_xxx
LANGSMITH_PROJECT=ciar-local-langgraph
```

#### Estructura de archivos clave
```
/Users/alejandromcht/Desktop/Prueba Neo4j/
├── agente_consola.py       ← ARCHIVO PRINCIPAL (681 líneas, Python 3.14)
├── cargar_ontologia.py     ← loader CSVs → Neo4j (no tocar)
├── ontologia.json          ← solo para cargar_ontologia.py, el agente NO lo lee
├── requirements.txt        ← dependencias
├── .env                    ← secrets (no subir a git)
├── .venv/                  ← venv roto si se mueve, usar .venv/bin/python directo
└── sesiones/
    ├── _index.md
    └── agente-local-ollama-neo4j.md  ← este archivo
```

---

### Pendientes / Bugs conocidos

1. **`qwen2.5:7b` débil en tool-calling**: el modelo emite tool calls como texto plano en lugar de structured output. Alucinaciones siguen posibles. Recomendado: `ollama pull llama3.1:8b` y cambiar `OLLAMA_MODEL=llama3.1:8b` en `.env`.

2. **`ASOCIADA_A` sin poblar**: relación declarada en ontología pero los CSVs de `EvalDesempeno` no tienen `id_puesto`/`id_oferta` → 0 conexiones.

3. **Venv no portable**: si se mueve la carpeta, `activate` rompe. Usar `.venv/bin/python` siempre.

4. **Neo4j Desktop botón Connect**: puede seguir mostrando URI basura visual. No afecta al agente (usa `.env`). Fix real: Stop/Start de la instancia con `server.bolt.*` comentados en `neo4j.conf`.

5. **Sin mejoras #4 y #6** de la lista propuesta (pendientes):
   - **#4**: `ChatOllama(format="json")` + parser fallback para tool calls como texto plano
   - **#6**: self-check de respuesta final (segunda llamada LLM que verifica si las filas responden la pregunta)

---

### Cómo correr
```bash
cd "/Users/alejandromcht/Desktop/Prueba Neo4j"
.venv/bin/python agente_consola.py
# Comandos en consola: /schema, /salir
# O con modelo específico: .venv/bin/python agente_consola.py --model llama3.1:8b
```

### Verificar Neo4j antes de correr
```bash
# Verificar que Neo4j Desktop Instance02 esté corriendo (icono verde)
# Verificar Ollama:
curl http://localhost:11434/api/tags
# Verificar Neo4j:
python3 -c "from neo4j import GraphDatabase; d=GraphDatabase.driver('neo4j://127.0.0.1:7687', auth=('neo4j','CHANGE_ME')); d.verify_connectivity(); print('OK')"
```
