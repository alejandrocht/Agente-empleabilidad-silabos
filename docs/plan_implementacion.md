# Plan de Implementación — Agente CIAR v2 (profesional, por fases)

> Documento único y definitivo. Contiene: reglas de código obligatorias, la estructura de
> carpetas profesional (investigada), el mapa de migración, y el plan fase por fase con el
> detalle necesario para implementar sin ambigüedad.

---

## 1. Reglas de código — OBLIGATORIAS (no negociables)

Estas reglas aplican a **todo** el código que se escriba en este proyecto. Si un cambio no
las cumple, no se acepta.

| # | Regla | Cómo se verifica |
|---|-------|------------------|
| R1 | **Comentar cada parte del código.** Cada bloque explica *qué* hace y *por qué*. | Revisión de código |
| R2 | **Código limpio:** nombres claros, funciones cortas de una sola responsabilidad, sin duplicación. | `ruff` + revisión |
| R3 | **No sobre-programar.** Escribir lo eficiente y suficiente, no soluciones "de experto" innecesarias. Si algo no se necesita hoy, no se construye. | Revisión |
| R4 | **Cada paso (nodo) se registra en un log.** Ningún nodo se ejecuta en silencio. | `test` + revisión de logs |
| R5 | **Observabilidad con LangSmith** activada en todas las llamadas al LLM. | Trazas visibles en LangSmith |
| R6 | **Solo OpenAI** como proveedor de LLM, con modelo configurable por nodo. | `.env` + fábrica |
| R7 | **Pruebas de auditoría del flujo** para cada pieza nueva. | `pytest` pasa |
| R8 | **Consultas Neo4j solo lectura.** Prohibido cualquier tipo de escritura. | `cypher_guard` + tests |

> Sobre R3: preferimos *legible y correcto* antes que *ingenioso*. El comentario de cada
> bloque es parte del entregable, no un extra.

---

## 2. Infraestructura — orden de carpetas profesional

### 2.1 Qué dicen las convenciones (investigación)

Basado en la documentación oficial de LangChain y las guías de estructura de proyectos Python
profesionales, los puntos clave son:

1. **Layout `src/`**: el código va en `src/<paquete>/` y se instala como paquete real. Evita
   errores de import y hace el código testeable y reutilizable.
2. **`langgraph.json`** en la raíz: archivo de configuración de LangGraph que apunta al grafo,
   dependencias y variables de entorno (necesario para `langgraph dev` / despliegue).
3. **`pyproject.toml`** como única fuente de verdad de dependencias (moderno; reemplaza al
   `requirements.txt` suelto). Se gestiona con `uv`, `poetry` o `pip`.
4. **Subcarpetas por función**: `nodos/`, `grafo/` (grafo + estado), `prompts/`, `utils/`,
   `config/`, `tools/`.
5. **Estado mínimo, explícito y tipado** (`TypedDict`).
6. **`tests/`** separado en `unit/` e `integration/` con `conftest.py`.
7. **Secretos en `.env`**; ajustes (modelos, temperatura) por variables de entorno/config.
8. **Producción**: usar `SqliteSaver`/`PostgresSaver` en vez de `MemorySaver` (para nosotros
   es a futuro; hoy la memoria es caché en RAM, ver Fase 4).

Fuentes:
- [Application structure — Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/application-structure)
- [Structure LangChain Projects for Deployment — apxml](https://apxml.com/courses/langchain-production-llm/chapter-7-deployment-strategies-production/structuring-projects-deployment)
- [LangGraph Best Practices — Swarnendu De](https://www.swarnendu.de/blog/langgraph-best-practices/)
- [Python Project Structure: Why the 'src' Layout Beats Flat Folders — Medium](https://medium.com/@adityaghadge99/python-project-structure-why-the-src-layout-beats-flat-folders-and-how-to-use-my-free-template-808844d16f35)
- [The Cleanest Way to Structure a Python Project in 2025 — Medium](https://medium.com/the-pythonworld/the-cleanest-way-to-structure-a-python-project-in-2025-4f04ccb8602f)
- [langgraph-example-pyproject — GitHub](https://github.com/langchain-ai/langgraph-example-pyproject)

### 2.2 Estructura objetivo (árbol comentado)

Mantenemos `backend/` y `frontend/` como dos aplicaciones separadas (monorepo). El backend
adopta el layout `src/` profesional. Los nombres de módulos se mantienen en español para ser
consistentes con el código existente (principio de código limpio: consistencia).

```
Agente-empleabilidad-silabos/
│
├── backend/                              ← Aplicación Python del agente
│   │
│   ├── pyproject.toml                    — Dependencias + config de ruff/mypy (fuente de verdad)
│   ├── langgraph.json                    — Config LangGraph (apunta al grafo)
│   ├── README.md                         — Cómo correr el backend
│   ├── .env                              — Secretos y ajustes (NO versionado)
│   ├── .env.example                      — Plantilla del .env
│   │
│   ├── src/
│   │   └── agente_ciar/                  ← El paquete instalable (pip install -e .)
│   │       ├── __init__.py
│   │       │
│   │       ├── config/                   — Configuración centralizada
│   │       │   ├── __init__.py
│   │       │   └── settings.py           — Carga .env y expone ajustes tipados
│   │       │
│   │       ├── grafo/                    — Construcción del grafo y su estado
│   │       │   ├── __init__.py
│   │       │   ├── constructor.py        — (antes agent.py) arma y compila el StateGraph
│   │       │   ├── estado.py             — EstadoAgente (TypedDict)
│   │       │   └── enrutado.py           — Funciones de routing condicional
│   │       │
│   │       ├── nodos/                    — Un archivo por nodo del flujo
│   │       │   ├── __init__.py
│   │       │   ├── base.py               — (antes nodo.py) Nodo y NodoLLM
│   │       │   ├── obtiene_pregunta.py
│   │       │   ├── obtiene_grafo.py
│   │       │   ├── selecciona_estrategia.py   — NUEVO (Fase 6)
│   │       │   ├── resuelve_entidad.py
│   │       │   ├── genera_cypher.py
│   │       │   ├── valida_cypher.py
│   │       │   ├── ejecuta_cypher.py
│   │       │   ├── analiza_resultado.py
│   │       │   └── devuelve_resultado.py
│   │       │
│   │       ├── llm/                      — Fábrica de modelos OpenAI por rol
│   │       │   ├── __init__.py
│   │       │   └── fabrica.py            — (antes utils/llm.py) modelo por nodo
│   │       │
│   │       ├── memoria/                  — Memoria conversacional + por bloques
│   │       │   ├── __init__.py
│   │       │   ├── conversacional.py     — Estado vivo (entidades activas) + TTL
│   │       │   └── bloques.py            — Resumen cada 12 mensajes (usa LLM)
│   │       │
│   │       ├── cache/                    — Caché de consultas (Cypher + resultados)
│   │       │   ├── __init__.py
│   │       │   └── consultas.py          — Dict en RAM con TTL
│   │       │
│   │       ├── guardas/                  — Seguridad
│   │       │   ├── __init__.py
│   │       │   ├── entrada.py            — Input guard (prompts adversariales)
│   │       │   └── cypher.py             — Allowlist/blocklist Cypher
│   │       │
│   │       ├── plantillas/               — Catálogo + motor de plantillas Cypher
│   │       │   ├── __init__.py
│   │       │   ├── catalogo.py           — Las 20 plantillas
│   │       │   └── motor.py              — Match y render
│   │       │
│   │       ├── db/                       — Cliente Neo4j
│   │       │   ├── __init__.py
│   │       │   └── neo4j.py              — (antes utils/neo4j.py) driver, schema, lectura
│   │       │
│   │       ├── observabilidad/           — Logs + LangSmith
│   │       │   ├── __init__.py
│   │       │   └── logger.py             — log_paso, log_inicio/fin_turno
│   │       │
│   │       ├── prompts/                  — Plantillas de prompt (texto)
│   │       │   ├── cargador.py           — (antes utils/prompts.py) lee los .md
│   │       │   ├── resuelve_entidad.md
│   │       │   ├── genera_cypher.md
│   │       │   ├── analiza_resultado.md
│   │       │   └── resumen_memoria.md    — NUEVO (Fase 4)
│   │       │
│   │       └── api/                      — Servidor HTTP
│   │           ├── __init__.py
│   │           └── servidor.py           — (antes api.py) FastAPI + middleware guard
│   │
│   ├── scripts/
│   │   └── consola.py                    — (antes main.py) entrypoint de consola
│   │
│   └── tests/
│       ├── conftest.py                   — Fixtures + desactiva LangSmith en tests
│       ├── unit/                         — Pruebas de piezas aisladas
│       │   ├── test_guardas.py
│       │   ├── test_plantillas.py
│       │   ├── test_cache.py
│       │   └── test_memoria.py
│       └── integration/                  — Pruebas end-to-end del flujo
│           └── test_flujo_auditoria.py
│
├── frontend/                             ← Next.js (sin cambios)
├── docs/                                 ← Documentación (este plan, análisis, diagramas)
└── sesiones/                             ← Historial técnico
```

### 2.3 Archivos raíz clave

**`backend/pyproject.toml`** — dependencias y config de calidad:

```toml
[project]
name = "agente-ciar"
version = "2.0.0"
requires-python = ">=3.11"
dependencies = [
    "langgraph",            # motor del grafo de estados
    "langchain-core",       # tipos base de LangChain
    "langchain-openai",     # cliente OpenAI (único proveedor)
    "langchain-neo4j",      # integración Neo4j
    "neo4j",                # driver oficial
    "fastapi",              # API HTTP
    "uvicorn",              # servidor ASGI
    "pydantic",             # validación de request/response
]

[project.optional-dependencies]
dev = ["pytest", "ruff", "mypy"]   # solo para desarrollo/CI

[tool.ruff]
line-length = 100                   # límite de línea (código limpio)

[tool.mypy]
strict = true                       # tipos estrictos

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

**`backend/langgraph.json`** — config de LangGraph:

```json
{
  "dependencies": ["."],
  "graphs": {
    "agente_ciar": "./src/agente_ciar/grafo/constructor.py:construir_grafo"
  },
  "env": ".env"
}
```

> `construir_grafo` es la función factoría que devuelve el grafo compilado. LangGraph la
> importa para servir el agente con `langgraph dev`.

### 2.4 Mapa de migración (dónde va cada archivo actual)

| Archivo actual | Nuevo lugar | Nota |
|----------------|-------------|------|
| `backend/agent.py` | `src/agente_ciar/grafo/constructor.py` | Las funciones de routing salen a `enrutado.py` |
| `backend/estado.py` | `src/agente_ciar/grafo/estado.py` | + campos `estrategia`, `plantilla_id` |
| `backend/nodo.py` | `src/agente_ciar/nodos/base.py` | `NodoLLM` pasa su nombre a la fábrica |
| `backend/nodos/*.py` | `src/agente_ciar/nodos/*.py` | Ajustar imports |
| `backend/api.py` | `src/agente_ciar/api/servidor.py` | + middleware input guard |
| `backend/main.py` | `scripts/consola.py` | Entrypoint |
| `backend/utils/config.py` | `src/agente_ciar/config/settings.py` | |
| `backend/utils/llm.py` | `src/agente_ciar/llm/fabrica.py` | Reescrita: OpenAI por rol |
| `backend/utils/neo4j.py` | `src/agente_ciar/db/neo4j.py` | |
| `backend/utils/memoria.py` | `src/agente_ciar/memoria/conversacional.py` + `bloques.py` | Refactor a 2 niveles |
| `backend/utils/prompts.py` | `src/agente_ciar/prompts/cargador.py` | |
| `backend/utils/historial.py` | *(eliminar)* | Legacy no usado |
| `backend/prompts/*.md` | `src/agente_ciar/prompts/*.md` | |
| `backend/tests/test_memoria.py` | `tests/unit/test_memoria.py` | |
| — | `src/agente_ciar/guardas/`, `cache/`, `plantillas/`, `observabilidad/` | NUEVO |

---

## 3. Cómo cada problema del XML se resuelve (mapa problema → fase)

| Problema del diagrama XML | Se resuelve en |
|---------------------------|----------------|
| #1 Pedir aclaración → FIN (callejón sin salida) | Fase 6 (flujo sin ramas terminales que maten la sesión) |
| #2 Estrategias sin criterio | Fase 6 (`selecciona_estrategia` con jerarquía) |
| #3 Validador duplicado | Fase 3 (`guardas/cypher.py` único módulo) |
| #4 Bucle sin freno | Fase 6 (tope de intentos; multi-paso queda con `MAX_PASOS`) |
| #5 Errores que nadie lee | Fase 1 (logs) + Fase 6 (reintento lee el error) |
| #6 Memoria sin caducidad | Fase 4 (TTL en memoria conversacional y caché) |
| #7 Revisión Global vacía | Fase 7 (inspector determinista + LLM opcional) |
| #8 Sin observabilidad | Fase 1 (logs + LangSmith) |

---

## 4. Fases de implementación

Cada fase tiene: **Objetivo · Depende de · Archivos · Código clave (comentado) · Reglas
aplicadas · Pruebas de auditoría · Criterio de aceptación.**

---

### FASE 0 — Reestructuración profesional (base)

**Objetivo:** dejar el esqueleto de carpetas profesional ANTES de agregar funcionalidad. No
cambia lógica: solo mueve archivos y arregla imports. Así las fases siguientes construyen
sobre una base ordenada.

**Depende de:** nada (es la primera).

**Archivos:**
- Crear `pyproject.toml`, `langgraph.json`, `README.md`.
- Mover todo según el mapa de migración (2.4) usando `git mv` para preservar historial.
- Ajustar todos los imports a la forma del paquete: `from agente_ciar.grafo.estado import EstadoAgente`.
- `pip install -e .` para instalar el paquete en modo editable.

**Código clave — `config/settings.py`** (centraliza la lectura de `.env`):

```python
# src/agente_ciar/config/settings.py
"""
Configuración centralizada.
Lee el .env una vez y expone los ajustes como funciones tipadas.
Así ningún módulo llama a os.getenv() suelto (código limpio: una sola fuente).
"""
from __future__ import annotations

import os
from pathlib import Path

# Raíz del backend (subimos desde src/agente_ciar/config/ hasta backend/)
BASE_DIR = Path(__file__).resolve().parents[3]


def cargar_entorno() -> None:
    """Lee el archivo .env (si existe) y vuelca sus valores al entorno del proceso."""
    ruta_env = BASE_DIR / ".env"
    if not ruta_env.exists():
        return
    # Recorremos línea por línea, ignorando vacíos y comentarios.
    for linea in ruta_env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        # setdefault no pisa variables ya definidas en el entorno real.
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))
```

**Reglas aplicadas:** R1 (comentarios), R2 (código limpio: una sola fuente de config), R3 (no
se agrega nada nuevo, solo se ordena).

**Pruebas de auditoría:**
- `python scripts/consola.py` arranca igual que antes.
- `pytest tests/` pasa (los tests migrados siguen verdes).

**Criterio de aceptación:** el agente responde una pregunta real contra Neo4j **exactamente
igual que antes**, pero desde la nueva estructura. Cero cambios de comportamiento.

---

### FASE 1 — Observabilidad (logs + LangSmith)

**Objetivo:** que cada paso del flujo quede registrado (R4) y que cada llamada al LLM sea
visible en LangSmith (R5). Es la primera fase funcional porque **todo lo demás se depura con
esto**.

**Depende de:** Fase 0.

**Archivos:**
- Crear `observabilidad/logger.py`.
- Añadir `log_paso()` en los 8 nodos.
- Activar LangSmith en `.env`.

**Código clave — `observabilidad/logger.py`:**

```python
# src/agente_ciar/observabilidad/logger.py
"""
Logger centralizado del agente.
Todos los nodos llaman a log_paso() para registrar su ejecución (regla R4).
Formato JSON estructurado para poder filtrar y analizar después.

LangSmith se activa solo con variables de entorno (LANGSMITH_TRACING=true);
LangChain lo detecta automáticamente, no requiere código extra aquí.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# Configuramos el logger una sola vez al importar el módulo.
_logger = logging.getLogger("agente_ciar")
if not _logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))  # el mensaje ya es JSON
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)


def log_paso(
    nodo: str,
    evento: str,
    id_sesion: str = "",
    data: dict[str, Any] | None = None,
    nivel: str = "info",
) -> None:
    """
    Registra un evento de un nodo.
      nodo:      nombre del nodo (ej. "genera_cypher")
      evento:    qué pasó (ej. "cypher_generado")
      id_sesion: sesión conversacional
      data:      datos extra (cypher, error, etc.)
      nivel:     "info" | "warning" | "error"
    """
    entrada = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "sesion": id_sesion or "desconocida",
        "nodo": nodo,
        "evento": evento,
        "data": data or {},
    }
    mensaje = json.dumps(entrada, ensure_ascii=False)
    # Elegimos el nivel de log según la severidad del evento.
    {"error": _logger.error, "warning": _logger.warning}.get(nivel, _logger.info)(mensaje)


def log_inicio_turno(id_sesion: str, pregunta: str) -> None:
    """Marca el inicio de un turno conversacional."""
    log_paso("turno", "inicio", id_sesion, {"pregunta": pregunta[:120]})


def log_fin_turno(id_sesion: str, respuesta: str, nodos: list[str]) -> None:
    """Marca el fin de un turno con la respuesta y los nodos recorridos."""
    log_paso("turno", "fin", id_sesion, {"respuesta_chars": len(respuesta), "nodos": nodos})
```

**Uso en un nodo (patrón para los 8):**

```python
def __call__(self, estado: EstadoAgente) -> dict:
    # Registramos que entramos a este nodo (regla R4).
    log_paso(self.nombre, "inicio", estado.get("id_sesion", ""))
    # ... lógica del nodo ...
    # Registramos el resultado relevante.
    log_paso(self.nombre, "cypher_generado", estado.get("id_sesion", ""), {"cypher": cypher[:200]})
    return {...}
```

**`.env` (LangSmith):**
```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=ciar-agente-v2
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

**Reglas aplicadas:** R1, R2, R4, R5.

**Pruebas de auditoría (`tests/unit/`):**
- `log_paso()` produce un JSON válido con las claves esperadas.
- Un turno de consola imprime al menos un log por nodo visitado.

**Criterio de aceptación:** cada turno genera logs JSON por nodo, y las llamadas al LLM
aparecen como trazas en LangSmith.

---

### FASE 2 — Modelo OpenAI por nodo

**Objetivo:** cambiar la fábrica de LLM a **solo OpenAI**, con un modelo elegible por nodo
(R6). Reintentos automáticos ante fallos transitorios.

**Depende de:** Fase 0.

**Modelos por nodo:**

| Nodo / lugar | Modelo base | Cuándo subir | Env var |
|--------------|-------------|--------------|---------|
| `resuelve_entidad` | `gpt-4o-mini` | casi nunca | `OPENAI_MODEL_ENTIDAD` |
| `genera_cypher` | `gpt-4o-mini` | ⬆️ `gpt-4o` si LangSmith muestra reintentos | `OPENAI_MODEL_CYPHER` |
| `analiza_resultado` | `gpt-4o-mini` | casi nunca | `OPENAI_MODEL_ANALISIS` |
| `resumen_memoria` | `gpt-4o-mini` | nunca | `OPENAI_MODEL_RESUMEN` |
| `inspector` (opcional) | determinista (sin LLM) | opcional `gpt-4o-mini` | `OPENAI_MODEL_INSPECTOR` |

**Código clave — `llm/fabrica.py`:**

```python
# src/agente_ciar/llm/fabrica.py
"""
Fábrica del LLM. Solo OpenAI (regla R6).
El modelo se elige por el NOMBRE del nodo, con cascada de fallback:
  variable del rol → OPENAI_MODEL global → MODELO_DEFAULT del código.
Así un rol sin su env var propia nunca queda sin modelo (auditoría A8).
"""
from __future__ import annotations

import os
from langchain_openai import ChatOpenAI

# Modelo global por defecto (último recurso).
MODELO_DEFAULT = "gpt-4o-mini"

# Cada rol (nombre de nodo) → su variable de entorno.
ENV_MODELO_POR_ROL: dict[str, str] = {
    "resuelve_entidad":  "OPENAI_MODEL_ENTIDAD",
    "genera_cypher":     "OPENAI_MODEL_CYPHER",
    "analiza_resultado": "OPENAI_MODEL_ANALISIS",
    "resumen_memoria":   "OPENAI_MODEL_RESUMEN",
    "inspector":         "OPENAI_MODEL_INSPECTOR",
}


def _modelo_para_rol(rol: str) -> str:
    """Devuelve el nombre del modelo OpenAI para un rol/nodo (con cascada de fallback)."""
    env_var = ENV_MODELO_POR_ROL.get(rol)
    # 1) Variable propia del rol, si está definida.
    if env_var and os.getenv(env_var):
        return os.getenv(env_var)
    # 2) Modelo global, o 3) default del código.
    return os.getenv("OPENAI_MODEL", MODELO_DEFAULT)


def obtener_llm(rol: str = "default") -> ChatOpenAI:
    """Crea el cliente OpenAI para un rol/nodo. Se llama una vez al instanciar el nodo LLM."""
    modelo = _modelo_para_rol(rol)
    temperatura = float(os.getenv("LLM_TEMPERATURE", "0"))
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY no está definida en el .env")
    return ChatOpenAI(
        model=modelo,
        temperature=temperatura,
        api_key=api_key,
        max_retries=3,  # reintenta solo ante 429/500 de OpenAI (auditoría A5)
    )
```

**`nodos/base.py` — `NodoLLM` pasa su nombre:**

```python
class NodoLLM(Nodo):
    def __init__(self) -> None:
        # El modelo se elige por el nombre del nodo.
        self.llm = obtener_llm(self.nombre)
        self.prompt = cargar_prompt(self.nombre)
```

**Reglas aplicadas:** R1, R2, R3 (fábrica simple, sin multi-proveedor innecesario), R6.

**Pruebas de auditoría:**
- Un rol con su env var definida devuelve ese modelo.
- Un rol **sin** env var cae al `OPENAI_MODEL` global (verifica A8).
- Sin `OPENAI_API_KEY` lanza error claro.

**Criterio de aceptación:** cada nodo LLM usa el modelo configurado; cambiar un modelo se hace
solo en `.env`, sin tocar código.

---

### FASE 3 — Seguridad (guardas)

**Objetivo:** dos guardas independientes: filtrar la entrada del usuario y validar el Cypher.
Resuelve los problemas #3 (validador único) y agrega la capa de input que faltaba.

**Depende de:** Fase 1 (para loggear los rechazos).

**Archivos:** `guardas/entrada.py`, `guardas/cypher.py`; `valida_cypher.py` usa el guard.

**Código clave — `guardas/entrada.py`:**

```python
# src/agente_ciar/guardas/entrada.py
"""
Input guard: detecta intentos de manipular el sistema antes de gastar un LLM.
Se usa como middleware en la API y como chequeo en el primer nodo.
"""
from __future__ import annotations

import re

# Patrones típicos de inyección de prompt.
_PATRONES = [
    r"ignora\s+tus\s+instrucciones", r"olvida\s+(todo|las\s+instrucciones)",
    r"ahora\s+eres", r"nuevo\s+rol", r"system\s*prompt", r"jailbreak",
    r"act[uú]a\s+como", r"modo\s+desarrollador",
]
_REGEX = re.compile("|".join(_PATRONES), flags=re.IGNORECASE)

# Longitud máxima de una pregunta (evita "bombas" de texto).
MAX_CHARS = 500


def validar_entrada(texto: str) -> tuple[bool, str]:
    """Devuelve (True, '') si es segura, o (False, motivo) si es sospechosa."""
    if len(texto) > MAX_CHARS:
        return False, f"Pregunta demasiado larga ({len(texto)}/{MAX_CHARS})"
    if _REGEX.search(texto):
        return False, "La pregunta contiene patrones no permitidos"
    return True, ""
```

**Código clave — `guardas/cypher.py`** (módulo ÚNICO compartido, corrige #3):

```python
# src/agente_ciar/guardas/cypher.py
"""
Reglas de seguridad del Cypher en un solo lugar (corrige el problema #3 del XML:
antes había lógica duplicada). valida_cypher las importa desde aquí.
"""
from __future__ import annotations

# Palabras que indican escritura o riesgo → prohibidas (regla R8).
PALABRAS_BLOQUEADAS: frozenset[str] = frozenset({
    "create", "merge", "delete", "detach", "set", "remove",
    "drop", "load", "periodic", "dbms", "constraint", "index",
    # Añadidas en v2 según el benchmark (brecha B9):
    "foreach", "show", "grant", "deny", "revoke",
})

# La consulta debe empezar con una de estas (solo lectura).
INICIOS_PERMITIDOS: tuple[str, ...] = ("match", "with", "return", "call db.", "call apoc.meta")
```

**Reglas aplicadas:** R1, R2, R3, R8; log del rechazo (R4).

**Pruebas de auditoría (`tests/unit/test_guardas.py`):**
- Input guard bloquea "ignora tus instrucciones" y textos > 500 chars.
- Input guard acepta una pregunta normal.
- `PALABRAS_BLOQUEADAS` contiene `merge`, `foreach`, `show`.

**Criterio de aceptación:** una entrada adversarial se rechaza antes de llegar al LLM; el
Cypher con escritura se bloquea.

---

### FASE 4 — Memoria de dos niveles + caché

**Objetivo:** implementar la memoria como la definiste: **conversacional (estado vivo)** que
se actualiza en cada cambio de entidad, **por bloques** cada 12 mensajes (con LLM), y la
**caché de consultas** con TTL. Todo en RAM. Resuelve el problema #6 (caducidad).

**Depende de:** Fase 1 (logs), Fase 2 (LLM para el resumen).

**Archivos:** `memoria/conversacional.py`, `memoria/bloques.py`, `cache/consultas.py`,
`prompts/resumen_memoria.md`.

**4.1 Memoria conversacional (estado vivo + TTL):**

```python
# src/agente_ciar/memoria/conversacional.py
"""
Memoria conversacional: el ESTADO VIVO de la sesión.
Guarda las entidades activas por tipo (Carrera, Empresa, Industria, Puesto...).
Se actualiza cada vez que cambia una entidad (sobreescribe el slot, no acumula).
TTL: si el último cambio fue hace más de MEMORIA_TTL_SEGUNDOS, el contexto se suelta
(corrige el problema #6: no servir "leche vencida").
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from threading import RLock
from typing import Any

_TTL = int(os.getenv("MEMORIA_TTL_SEGUNDOS", "1800"))  # 30 min por defecto
_CACHE: dict[str, dict[str, Any]] = {}
_LOCK = RLock()


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _nueva() -> dict[str, Any]:
    """Crea una memoria conversacional vacía."""
    return {"entidades_activas": {}, "tema_actual": "", "updated_at": _ahora().isoformat()}


def obtener(id_sesion: str) -> dict[str, Any]:
    """Devuelve el estado vivo de la sesión, ya limpio si venció el TTL."""
    with _LOCK:
        mem = _CACHE.setdefault(id_sesion, _nueva())
        # Si el contexto venció, lo reiniciamos antes de entregarlo.
        vencido = (_ahora() - datetime.fromisoformat(mem["updated_at"])).total_seconds() > _TTL
        if vencido:
            mem = _CACHE[id_sesion] = _nueva()
        return dict(mem)


def actualizar_entidades(id_sesion: str, entidades: list[dict]) -> None:
    """Sobreescribe el slot de cada entidad resuelta (Carrera, Empresa, etc.)."""
    if not entidades:
        return
    with _LOCK:
        mem = _CACHE.setdefault(id_sesion, _nueva())
        for ent in entidades:
            label = ent.get("label")
            if label:  # cada label es un "slot"; el nuevo valor pisa al anterior
                mem["entidades_activas"][label] = {"nombre": ent.get("nombre"), "id": ent.get("id")}
        mem["updated_at"] = _ahora().isoformat()
```

**4.2 Memoria por bloques (resumen cada 12 mensajes con LLM):**

```python
# src/agente_ciar/memoria/bloques.py
"""
Memoria por bloques: resumen histórico de la conversación.
Cada MEMORIA_BLOQUE_CADA (12) mensajes, un LLM resume esos turnos en un bloque.
Es el ÚNICO punto de memoria que llama al LLM (rol "resumen_memoria").
"""
from __future__ import annotations

import os
from threading import RLock
from typing import Any

from agente_ciar.llm.fabrica import obtener_llm
from agente_ciar.prompts.cargador import cargar_prompt

_CADA = int(os.getenv("MEMORIA_BLOQUE_CADA", "12"))
_CACHE: dict[str, dict[str, Any]] = {}
_LOCK = RLock()


def registrar_mensaje(id_sesion: str, pregunta: str, respuesta: str) -> None:
    """Suma un mensaje; cada 12, dispara el resumen del bloque."""
    with _LOCK:
        est = _CACHE.setdefault(id_sesion, {"contador": 0, "pendientes": [], "bloques": []})
        est["contador"] += 1
        est["pendientes"].append(f"P: {pregunta} | R: {respuesta}")
        # Al llegar a 12, resumimos y reiniciamos la ventana.
        if est["contador"] >= _CADA:
            est["bloques"].append(_resumir(est["pendientes"]))
            est["pendientes"] = []
            est["contador"] = 0


def _resumir(turnos: list[str]) -> str:
    """Pide al LLM un resumen breve de los últimos turnos."""
    llm = obtener_llm("resumen_memoria")  # modelo del rol (gpt-4o-mini)
    prompt = cargar_prompt("resumen_memoria").replace("{turnos}", "\n".join(turnos))
    return str(llm.invoke(prompt).content).strip()
```

**4.3 Caché de consultas (Cypher + resultado, con TTL):**

```python
# src/agente_ciar/cache/consultas.py
"""
Caché en RAM de consultas ya resueltas. Guarda:
  - el Cypher generado (para no volver a llamar al LLM)
  - el Cypher + su resultado (para no volver a ejecutar en Neo4j)
Clave: hash de (pregunta normalizada + entidades). TTL configurable.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from threading import RLock
from typing import Any

_TTL = int(os.getenv("CACHE_TTL_SEGUNDOS", "600"))  # 10 min
_CACHE: dict[str, dict[str, Any]] = {}
_LOCK = RLock()


def _clave(pregunta: str, entidades: list[dict]) -> str:
    """Clave determinista para la combinación pregunta + entidades."""
    p = " ".join(pregunta.lower().split())
    e = sorted([{"label": x.get("label", ""), "id": x.get("id", "")} for x in entidades],
               key=lambda x: (x["label"], x["id"]))
    return hashlib.sha256(json.dumps({"p": p, "e": e}, ensure_ascii=False).encode()).hexdigest()[:16]


def buscar(pregunta: str, entidades: list[dict]) -> dict[str, Any] | None:
    """Devuelve {cypher, filas} si hay entrada vigente; None si no existe o venció."""
    clave = _clave(pregunta, entidades)
    with _LOCK:
        ent = _CACHE.get(clave)
        if not ent:
            return None
        # Revisamos el TTL antes de devolver (no servir datos vencidos).
        if (datetime.now(timezone.utc) - datetime.fromisoformat(ent["creado_en"])).total_seconds() >= _TTL:
            del _CACHE[clave]
            return None
        return {"cypher": ent["cypher"], "filas": ent["filas"]}


def guardar(pregunta: str, entidades: list[dict], cypher: str, filas: list[dict]) -> None:
    """Guarda el Cypher y su resultado."""
    with _LOCK:
        _CACHE[_clave(pregunta, entidades)] = {
            "cypher": cypher, "filas": filas, "creado_en": datetime.now(timezone.utc).isoformat(),
        }
```

**Reglas aplicadas:** R1, R2, R3, R4 (loggear hits/miss y resúmenes), R5.

**Pruebas de auditoría (`tests/unit/`):**
- Memoria conversacional: al resolver una `Carrera`, el slot queda; con timestamp viejo, se limpia (TTL, verifica A9).
- Bloques: a los 12 mensajes se genera 1 bloque (con LLM mockeado).
- Caché: guardar + buscar devuelve; pregunta distinta → miss; entrada vencida → miss.

**Criterio de aceptación:** referencias implícitas ("esa carrera") se resuelven con el slot
activo; la misma pregunta repetida **no** genera un segundo LLM call (visible en LangSmith).

---

### FASE 5 — Plantillas Cypher (20 plantillas)

**Objetivo:** responder las preguntas más comunes **sin llamar al LLM**, instanciando
plantillas parametrizadas. Reduce costo y da reproducibilidad.

**Depende de:** Fase 0.

**Archivos:** `plantillas/catalogo.py` (las 20), `plantillas/motor.py` (match + render).

**Las 20 plantillas** (id, ejemplo de pregunta, Cypher, parámetro):

| # | id | Pregunta ejemplo | Parámetro |
|---|-----|------------------|-----------|
| 1 | `contar_carreras` | ¿cuántas carreras hay? | — |
| 2 | `listar_carreras` | ¿qué carreras hay? | — |
| 3 | `cursos_de_carrera` | ¿qué cursos tiene sistemas? | Carrera |
| 4 | `contar_cursos_de_carrera` | ¿cuántos cursos tiene civil? | Carrera |
| 5 | `facultad_de_carrera` | ¿a qué facultad pertenece industrial? | Carrera |
| 6 | `top_empresas_ofertas` | top empresas con más ofertas | — |
| 7 | `ofertas_de_empresa` | ¿cuántas ofertas publicó BCP? | Empresa |
| 8 | `puestos_de_empresa` | ¿qué puestos ofrece Interbank? | Empresa |
| 9 | `listar_empresas` | ¿qué empresas hay? | — |
| 10 | `competencias_demandadas_carrera` | competencias para industrial | Carrera |
| 11 | `top_competencias_ofertas` | competencias más demandadas | — |
| 12 | `habilidades_para_puesto` | habilidades para analista de datos | Puesto |
| 13 | `herramientas_mas_requeridas` | herramientas más requeridas | — |
| 14 | `herramientas_de_carrera` | ¿qué herramientas enseña sistemas? | Carrera |
| 15 | `puestos_mas_demandados` | puestos más demandados | — |
| 16 | `industrias_con_mas_ofertas` | industrias con más ofertas | — |
| 17 | `empresas_de_industria` | empresas del sector financiero | Industria |
| 18 | `silabo_de_curso` | sílabo de cálculo I | Curso |
| 19 | `carreras_que_tienen_curso` | ¿qué carreras tienen estadística? | Curso |
| 20 | `cursos_para_competencia` | cursos que desarrollan liderazgo | Competencia |

**Estructura de una plantilla (patrón para las 20):**

```python
# src/agente_ciar/plantillas/catalogo.py  (extracto — las 20 siguen este molde)
"""
Catálogo de plantillas Cypher parametrizadas para las preguntas más comunes.
Cada plantilla se evalúa por prioridad (mayor primero). Las de mayor prioridad
son las que requieren entidad (más específicas).
"""
from __future__ import annotations
from typing import TypedDict


class Plantilla(TypedDict):
    id: str
    descripcion: str
    patrones: list[str]      # palabras clave que activan la plantilla
    cypher: str              # Cypher con {placeholder} (string literal, NO f-string)
    params: dict[str, str]   # placeholder → "entidad.<Label>.<campo>"
    prioridad: int


PLANTILLAS: list[Plantilla] = [
    {
        "id": "contar_carreras",
        "descripcion": "Total de carreras registradas",
        "patrones": ["cuantas carreras", "total carreras", "numero de carreras"],
        "cypher": "MATCH (c:Carrera) RETURN count(c) AS total",
        "params": {},              # sin parámetros → prioridad baja
        "prioridad": 10,
    },
    {
        "id": "cursos_de_carrera",
        "descripcion": "Cursos de una carrera específica",
        "patrones": ["cursos de", "cursos tiene", "que cursos"],
        # El motor reemplaza {id_carrera} por el id real de la entidad resuelta.
        "cypher": "MATCH (c:Carrera {id_carrera: '{id_carrera}'})-[:CONTIENE]-(cu:Curso) "
                  "RETURN cu.nombre AS curso ORDER BY curso LIMIT 25",
        "params": {"id_carrera": "entidad.Carrera.id"},  # requiere entidad Carrera
        "prioridad": 20,           # más específica → prioridad alta
    },
    # ... las otras 18 plantillas siguen exactamente este molde ...
]
```

**Motor — `plantillas/motor.py`:**

```python
# src/agente_ciar/plantillas/motor.py
"""
Motor de plantillas: elige la mejor plantilla para una pregunta y la renderiza.
  buscar_plantilla(pregunta, entidades) → Plantilla | None
  renderizar(plantilla, entidades) → str (Cypher listo)
Si no hay plantilla que calce, el flujo cae a genera_cypher (LLM).
"""
from __future__ import annotations

import re
import unicodedata

from agente_ciar.plantillas.catalogo import PLANTILLAS, Plantilla


def _norm(texto: str) -> str:
    """Minúsculas sin tildes ni signos, para comparar patrones."""
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", t).split())


def buscar_plantilla(pregunta: str, entidades: list[dict]) -> Plantilla | None:
    """Devuelve la plantilla de mayor prioridad cuyo patrón calce y tenga sus parámetros."""
    p = _norm(pregunta)
    candidatas = [
        pl for pl in PLANTILLAS
        if any(pat in p for pat in pl["patrones"]) and _params_ok(pl, entidades)
    ]
    return max(candidatas, key=lambda x: x["prioridad"]) if candidatas else None


def _params_ok(plantilla: Plantilla, entidades: list[dict]) -> bool:
    """Verifica que cada parámetro requerido tenga una entidad resuelta con id."""
    for ruta in plantilla["params"].values():
        _, label, campo = ruta.split(".")  # "entidad.Carrera.id"
        if not any(e.get("label") == label and e.get(campo) for e in entidades):
            return False
    return True


def renderizar(plantilla: Plantilla, entidades: list[dict]) -> str:
    """Reemplaza los placeholders del Cypher por los valores de las entidades."""
    cypher = plantilla["cypher"]
    for placeholder, ruta in plantilla["params"].items():
        _, label, campo = ruta.split(".")
        for e in entidades:
            if e.get("label") == label:
                cypher = cypher.replace("{" + placeholder + "}", e.get(campo, ""))
                break
    return cypher
```

**Reglas aplicadas:** R1, R2, R3 (molde único repetido, sin abstracción excesiva).

**Pruebas de auditoría (`tests/unit/test_plantillas.py`):**
- "cuántas carreras hay" → `contar_carreras`.
- "cursos de sistemas" **sin** entidad → None (no calza sin parámetro).
- "cursos de sistemas" **con** entidad Carrera → renderiza con el id real.

**Criterio de aceptación:** las preguntas comunes con y sin entidad seleccionan la plantilla
correcta y producen Cypher válido sin LLM.

---

### FASE 6 — Nodo `selecciona_estrategia` + flujo actualizado

**Objetivo:** implementar la **jerarquía de decisión** que faltaba en el XML (#2), enrutar
sin ramas terminales que maten la sesión (#1), y mantener el freno de reintentos (#4).

**Depende de:** Fases 4 y 5 (usa caché y plantillas).

**Archivos:** `nodos/selecciona_estrategia.py`, `grafo/estado.py` (nuevos campos),
`grafo/enrutado.py` (nuevo routing), `nodos/devuelve_resultado.py` (guarda en caché).

**Código clave — `nodos/selecciona_estrategia.py`:**

```python
# src/agente_ciar/nodos/selecciona_estrategia.py
"""
Selección de estrategia (corrige el problema #2 del XML: antes no había criterio).
Jerarquía, de más barato a más caro:
  1. ¿Está en caché y vigente? → usa el resultado (0 LLM, 0 Neo4j)
  2. ¿Hay plantilla que calce?  → instancia el Cypher (0 LLM)
  3. Si no → generación dinámica con el LLM
"""
from __future__ import annotations

from agente_ciar.cache.consultas import buscar as buscar_cache
from agente_ciar.grafo.estado import EstadoAgente
from agente_ciar.nodos.base import Nodo
from agente_ciar.observabilidad.logger import log_paso
from agente_ciar.plantillas.motor import buscar_plantilla, renderizar


class SeleccionaEstrategia(Nodo):
    """Decide si usar caché, plantilla o generación dinámica."""

    nombre = "selecciona_estrategia"

    def __call__(self, estado: EstadoAgente) -> dict:
        pregunta = estado.get("pregunta", "")
        entidades = estado.get("entidades", [])
        sesion = estado.get("id_sesion", "")

        # 1) Caché: si ya respondimos esto y sigue fresco, cortamos aquí.
        hit = buscar_cache(pregunta, entidades)
        if hit:
            log_paso(self.nombre, "cache_hit", sesion)
            return {"cypher": hit["cypher"], "filas": hit["filas"], "estrategia": "cache"}

        # 2) Plantilla: si hay una que calza, renderizamos su Cypher.
        plantilla = buscar_plantilla(pregunta, entidades)
        if plantilla:
            cypher = renderizar(plantilla, entidades)
            log_paso(self.nombre, "plantilla_usada", sesion, {"id": plantilla["id"]})
            return {"cypher": cypher, "estrategia": "plantilla", "plantilla_id": plantilla["id"]}

        # 3) Default: generación dinámica con el LLM.
        log_paso(self.nombre, "generacion_dinamica", sesion)
        return {"estrategia": "dinamica"}
```

**`grafo/enrutado.py` — routing tras la estrategia:**

```python
def ruta_tras_estrategia(estado: EstadoAgente) -> str:
    """Según la estrategia elegida, saltamos lo que ya está resuelto."""
    estrategia = estado.get("estrategia", "dinamica")
    if estrategia == "cache":
        return "analiza_resultado"   # ya tenemos cypher Y filas
    if estrategia == "plantilla":
        return "valida_cypher"       # ya tenemos cypher, falta validar y ejecutar
    return "resuelve_entidad"        # flujo dinámico completo
```

**Flujo resultante (sin callejones sin salida):**

```
obtiene_pregunta ─(saludo/entrada inválida)→ devuelve_resultado → END
      │
obtiene_grafo → selecciona_estrategia ─(caché)──→ analiza_resultado
      │                                └(plantilla)→ valida_cypher
      │                                └(dinámica)→ resuelve_entidad → genera_cypher
genera_cypher → valida_cypher ─(error, <2 intentos)→ genera_cypher
                              └(ok)→ ejecuta_cypher ─(error,<2)→ genera_cypher
                                            └(ok)→ analiza_resultado
analiza_resultado → devuelve_resultado → END   (siempre responde y espera el próximo mensaje)
```

**Reglas aplicadas:** R1, R2, R3, R4.

**Pruebas de auditoría:** las 3 ramas (caché/plantilla/dinámica) enrutadas correctamente;
ninguna termina en un FIN que corte la sesión.

**Criterio de aceptación:** una pregunta con plantilla salta `resuelve_entidad`+`genera_cypher`;
una repetida usa caché; el resto va al flujo dinámico. Todo trazable en LangSmith.

---

### FASE 7 — Inspector de calidad

**Objetivo:** dar sustancia al "Revisión Global" del XML (#7). Chequeo determinista siempre,
juez LLM opcional.

**Depende de:** Fases 1 y 2.

**Código clave — chequeo determinista (dentro de `devuelve_resultado`):**

```python
# src/agente_ciar/nodos/devuelve_resultado.py  (extracto del inspector)
import os
import re

# Regex que detecta caracteres chinos/CJK (fallo típico de otros modelos).
_CJK = re.compile(r"[一-鿿]")


def _inspeccionar(respuesta: str) -> tuple[bool, str]:
    """Validación determinista de la respuesta. Devuelve (ok, motivo)."""
    if not respuesta or len(respuesta.strip()) < 10:
        return False, "respuesta vacía o demasiado corta"
    if len(respuesta) > 2000:
        return False, "respuesta demasiado larga"
    if _CJK.search(respuesta):
        return False, "respuesta contiene caracteres no permitidos (CJK)"
    return True, ""
```

**Juez LLM opcional** (solo si `INSPECTOR_LLM=true`): un `gpt-4o-mini` recibe pregunta + filas
+ respuesta y responde si la respuesta inventó datos. Apagado por defecto (R3: no pagar en
cada turno sin necesidad).

**Reglas aplicadas:** R1, R2, R3, R4 (loggear rechazos del inspector).

**Pruebas de auditoría (`tests/unit/`):** respuesta vacía, con chino, o de 3000 chars → rechazada;
respuesta normal → aceptada.

**Criterio de aceptación:** ninguna respuesta vacía, en otro idioma o desmedida llega al usuario.

---

### FASE 8 — Auditoría integral del flujo

**Objetivo:** una batería de pruebas end-to-end que valide que TODO el flujo funciona junto.

**Depende de:** todas las anteriores.

**Archivo:** `tests/integration/test_flujo_auditoria.py`.

**Cobertura:**
- Saludo cortocircuita sin tocar Neo4j ni LLM.
- Entrada adversarial rechazada por el input guard.
- Pregunta con plantilla resuelta sin LLM.
- Pregunta repetida servida desde caché.
- Cypher con `CREATE` bloqueado por el guard.
- Referencia implícita resuelta con la entidad activa de la memoria conversacional.
- Cada test verifica que se generaron los logs esperados (R4).

**`conftest.py`** desactiva LangSmith en tests (auditoría A6):

```python
# tests/conftest.py
import os
# En pruebas no queremos trazas reales en LangSmith.
os.environ["LANGSMITH_TRACING"] = "false"
```

**Criterio de aceptación:** `pytest` pasa al 100%; el flujo queda auditado de punta a punta.

---

## 5. Orden y dependencias entre fases

```
FASE 0 (estructura)
   │
   ├──► FASE 1 (logs + LangSmith) ──► FASE 2 (OpenAI por nodo)
   │                                       │
   │                                       ├──► FASE 3 (guardas)
   │                                       │
   │                                       ├──► FASE 4 (memoria + caché)
   │                                       │
   │            FASE 5 (plantillas) ◄──────┘
   │                                       │
   │                        FASE 6 (estrategia + flujo) ◄── depende de 4 y 5
   │                                       │
   │                        FASE 7 (inspector)
   │                                       │
   └──────────────────────► FASE 8 (auditoría integral)
```

Ruta crítica sugerida: **0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8**. Las Fases 3, 4 y 5 pueden
solaparse porque son independientes entre sí (solo dependen de 0-2).

---

## 6. Auditoría del plan

> Recordatorio: esta auditoría revisa **el plan** (no el diseño del agente). Sus hallazgos ya
> están resueltos aquí. Es distinta de los 8 problemas del XML (esos se cierran en las fases).

### Checklist de completitud

| Ítem | Estado |
|------|--------|
| Reglas de código explícitas y verificables | ✅ (§1) |
| Estructura de carpetas profesional investigada + fuentes | ✅ (§2) |
| `pyproject.toml` y `langgraph.json` definidos | ✅ (§2.3) |
| Mapa de migración archivo por archivo | ✅ (§2.4) |
| Cada problema del XML mapeado a una fase | ✅ (§3) |
| 8 fases con objetivo/dependencias/código/pruebas/criterio | ✅ (§4) |
| Cada paso se registra en log (R4) | ✅ (Fase 1 + uso en todos los nodos) |
| LangSmith activado (R5) | ✅ (Fase 1) |
| Solo OpenAI, modelo por nodo (R6) | ✅ (Fase 2) |
| 20 plantillas | ✅ (Fase 5) |
| Memoria de 2 niveles + caché con TTL | ✅ (Fase 4) |
| Inspector determinista + LLM opcional | ✅ (Fase 7) |
| Pruebas de auditoría por fase + integrales | ✅ (Fases + Fase 8) |
| Orden y dependencias entre fases | ✅ (§5) |

### Hallazgos de la auditoría del plan

- **A1 — Estado incompleto:** los campos `estrategia` y `plantilla_id` deben añadirse a
  `EstadoAgente` en la Fase 6. *(Anotado en la Fase 6.)*
- **A2 — Salto de caché:** el routing a `analiza_resultado` cuando hay caché debe probarse
  explícitamente en la Fase 8. *(Cubierto.)*
- **A5 — Reintentos OpenAI:** `max_retries=3` en la fábrica. *(Resuelto en Fase 2.)*
- **A6 — LangSmith en tests:** desactivado en `conftest.py`. *(Resuelto en Fase 8.)*
- **A8 — Modelos sin env var:** cascada de fallback en `_modelo_para_rol`. *(Resuelto en Fase 2.)*
- **A9 — TTL memoria conversacional:** `obtener()` limpia si venció. *(Resuelto en Fase 4.)*
- **A10 (nuevo) — Migración de imports:** la Fase 0 cambia todos los imports al paquete
  `agente_ciar.*`. Riesgo de imports rotos. *Mitigación:* correr `pytest` y la consola al
  final de la Fase 0 como criterio de aceptación antes de avanzar.
- **A11 (nuevo) — `langgraph.json` apunta a una factoría:** verificar que `construir_grafo`
  sea importable sin ejecutar efectos secundarios pesados al importar (no conectar a Neo4j en
  el import). *Mitigación:* la conexión a Neo4j ya es lazy (`lru_cache`), se mantiene así.

### Resultado

**Plan completo y auditado.** Los hallazgos son de bajo riesgo y están mitigados dentro de las
fases. La ruta crítica está clara y cada fase tiene un criterio de aceptación objetivo.

**Listo para empezar por la Fase 0.**
