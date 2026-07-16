# Estado actual del proyecto — Agente CIAR

> Documento canónico del **estado real** del proyecto. Última actualización: **2026-07-14**.
> Histórico técnico y decisiones previas en [[agente-langgraph]].

## Resumen ejecutivo

Agente conversacional que responde en español preguntas sobre el grafo **Neo4j** del CIAR
(carreras, cursos, sílabos, empresas, ofertas, competencias, herramientas, industrias).
Convierte lenguaje natural → Cypher, valida que sea **solo lectura**, ejecuta contra Neo4j y
redacta la respuesta. Un único proveedor LLM: **OpenAI** (modelo por rol).

Estado general: **funcional y verificado en local**, con backend modular instalable y frontend
Next.js. Listo para uso/demostración; **aún no productizado** (sin CI/CD, sin contenedores, sin
autenticación en la API). Ver checklist de "proyecto real" más abajo.

---

## Arquitectura actual

### Estructura del repositorio
```
Agente-empleabilidad-silabos/
├── backend/            ← código Python del agente
│   ├── pyproject.toml  — dependencias + calidad (ruff, mypy strict, pytest)
│   ├── langgraph.json  — factoría del grafo para LangGraph
│   ├── src/agente/     — paquete instalable (grafo, nodos, guardas, memoria, plantillas, api)
│   ├── scripts/consola.py — loop de consola
│   ├── tests/unit + tests/integration
│   └── PREGUNTAS_EJEMPLO.md
├── frontend/           ← aplicación Next.js (chat + panel de razonamiento) con Vitest
├── sesiones/           ← Obsidian: histórico técnico y este estado
└── docs/plan_implementacion.md
```

> ⚠️ **Rename en curso:** el paquete se está renombrando `agente_ciar` → `agente`. En el working
> tree los archivos viejos figuran como borrados y `backend/src/agente/` está sin trackear.
> El grafo compila y las rutas son idénticas bajo el nuevo nombre. **Pendiente:** terminar y
> commitear el rename (código + `pyproject.toml` + `langgraph.json` + imports de tests + CLAUDE.md).

### Flujo del agente (real — 9 nodos)

Diagrama: `Downloads/Agente CIAR.drawio (4).xml` (actualizado 2026-07-14, verificado sin cruces).

```
START → obtiene_pregunta ─(saludo/entrada bloqueada)→ devuelve_resultado
                          └(pregunta válida)→ obtiene_grafo → selecciona_estrategia
   ├ caché    → analiza_resultado
   ├ plantilla→ valida_cypher
   └ dinámica → resuelve_entidad → genera_cypher → valida_cypher
valida_cypher ─(ok)→ ejecuta_cypher ─(error, <2)→ genera_cypher ─(error, ≥2)→ devuelve_resultado
ejecuta_cypher ─(filas)→ analiza_resultado ─(error, <2)→ genera_cypher ─(error, ≥2)→ devuelve
analiza_resultado → devuelve_resultado → END
```

Tres estrategias por costo (`selecciona_estrategia`): **caché** (respuesta ya auditada, sin LLM ni
Neo4j) → **plantilla** (Cypher determinista del catálogo, sin LLM) → **dinámica** (LLM genera
Cypher desde cero). Reparación acotada a `MAX_INTENTOS = 2`.

### Componentes clave
- **Guardas** (`guardas/`): `entrada.py` (anti prompt-injection + límite 500 chars) y `cypher.py`
  (solo lectura, valida labels/relaciones contra schema vivo, `EXPLAIN`, prohíbe `CONTAINS`/`nombre_norm`).
- **Plantillas** (`plantillas/`): catálogo de **20 consultas** frecuentes; se elige **una** por
  prioridad y se resuelven ids sin LLM. *No hay composición de múltiples plantillas todavía* (ver roadmap).
- **Memoria** (`memoria/`): entidades activas e historial reciente por sesión con TTL + resumen por
  bloques. “Esa/esta carrera” usa la activa, “la anterior” recupera la penúltima y “la primera”
  recupera la primera entidad mencionada del mismo tipo. El historial se limita con
  `MEMORIA_HISTORIAL_ENTIDADES` (8 por defecto).
- **Caché** (`cache/`): hash(pregunta + ids) → cypher + filas + respuesta, con TTL y tope de entradas.
- **LLM** (`llm/fabrica.py`): OpenAI, modelo por rol (entidad/cypher/análisis/resumen/inspector), lazy.
- **Observabilidad** (`observabilidad/logger.py`): logs JSON por nodo/turno.
- **API** (`api/servidor.py`): FastAPI (`/chat`, `/health`), traduce errores de proveedor, expone la ruta recorrida.

---

## Estado de calidad / verificación (2026-07-14)

| Chequeo | Estado |
|---|---|
| Grafo compila (`construir_grafo`) | ✅ |
| Ruff (`ruff check src tests scripts`) | ✅ limpio |
| Mypy strict (`mypy src`) | ✅ 38 archivos, sin issues |
| Pruebas unitarias (`pytest tests/unit`) | ✅ 28 passed |
| Pruebas de integración (auditoría de flujo) | ✅ presentes |
| Frontend (`npm run check`, Vitest) | ✅ configurado |
| Prueba real contra Neo4j / rama dinámica OpenAI | ⚠️ requiere `.env` con credenciales (pendiente en este entorno) |

---

## Lo que debe tener un proyecto real — checklist

Leyenda: ✅ hecho · ⚠️ parcial · ❌ falta

### Código & arquitectura
- ✅ Paquete instalable, capas separadas (grafo/nodos/guardas/…), estado tipado.
- ✅ Ruteo determinista aislado (`grafo/enrutado.py`).
- ⚠️ Rename `agente_ciar → agente` sin finalizar/commitear.

### Pruebas
- ✅ Unitarias (28) + integración (auditoría de flujo).
- ⚠️ Falta cobertura medida (`coverage`/umbral) y pruebas E2E frontend↔backend (Playwright).
- ❌ Sin pruebas de carga/rendimiento.

### Calidad estática & formato
- ✅ Ruff + Mypy strict configurados en `pyproject.toml`.
- ❌ Sin **pre-commit hooks** (ruff/mypy/pytest no se ejecutan automáticamente antes del commit).

### CI/CD
- ❌ **Sin `.github/workflows`**: no hay pipeline que corra lint + tipos + tests en cada push/PR.
- ❌ Sin publicación/versionado automatizado.

### Observabilidad & operación
- ✅ Logs JSON estructurados por nodo/turno; `/health` con verificación real de Neo4j.
- ⚠️ LangSmith disponible por entorno pero no obligatorio; sin métricas (Prometheus) ni dashboards.
- ❌ Sin alertas ni trazas distribuidas exportadas.

### Seguridad
- ✅ Guardas de entrada (anti-inyección) y Cypher (solo lectura, defensa en profundidad).
- ✅ Sesiones Neo4j `READ_ACCESS`; errores de proveedor no filtran credenciales.
- ❌ **API sin autenticación ni rate limiting** (cualquiera con acceso de red puede consultar `/chat`).
- ❌ Sin escaneo de dependencias/SAST en pipeline (solo `npm audit` manual en frontend).

### Configuración & secretos
- ✅ `.env` no versionado + `.env.example` documentado; config centralizada (`config/settings.py`).
- ⚠️ Gestión de secretos sólo por `.env`; falta un gestor real para producción (Vault/Secret Manager).

### Documentación
- ✅ `CLAUDE.md`, `backend/README.md`, `PREGUNTAS_EJEMPLO.md`, `docs/plan_implementacion.md`, Obsidian.
- ❌ Falta **README raíz**, `LICENSE`, `CONTRIBUTING.md` y `CHANGELOG.md`.
- ⚠️ Diagrama de flujo vive en `Downloads/`, fuera del repo → conviene versionarlo (p. ej. `docs/`).

### Despliegue / infraestructura
- ❌ **Sin `Dockerfile` ni `docker-compose`** (backend, frontend, Neo4j).
- ❌ Sin manifiestos de despliegue (compose/k8s), sin entorno de staging.

### Datos (Neo4j)
- ✅ Introspección de schema **en vivo** (no hardcodeado); plantillas alineadas al schema real.
- ⚠️ Sin control de versiones del modelo de datos ni fixtures reproducibles para tests de integración.

### Producto / capacidades
- ✅ Caché + plantillas + rama dinámica con reparación; memoria conversacional.
- ❌ **Sin composición de múltiples plantillas** (hoy: 1 plantilla o generación desde cero). → roadmap.

---

## Roadmap / pendientes priorizados

**P0 — Higiene inmediata**
- Terminar y commitear el rename `agente_ciar → agente` (código, config, tests, CLAUDE.md).
- Versionar el diagrama de flujo dentro del repo (`docs/`).

**P1 — Productización mínima**
- **CI** en GitHub Actions: ruff + mypy + pytest (backend) y `npm run check` + Vitest (frontend) en cada PR.
- **pre-commit** con ruff/mypy/pytest rápidos.
- **Docker/compose** para backend + frontend + Neo4j; entorno de staging.
- **Auth + rate limiting** en la API (`/chat`) antes de exponerla.
- README raíz + LICENSE.

**P2 — Capacidades del agente**
- **Composición de plantillas** (funcionalidad futura acordada). Enfoques evaluados:
  - *A — Multi-plantilla por `UNION`/subconsultas*: `buscar_plantilla` devuelve varias coincidencias
    y un `componer()` las une con `UNION`/`WITH`/`CALL {}`. Determinista; sólo para plantillas apilables.
  - *B — Plantillas compuestas explícitas* en el catálogo para combinaciones frecuentes. Simple, no escala.
  - *C — Router LLM que planifica* qué plantillas combinar y con qué parámetros. Más potente; reintroduce
    parte del "supervisor-planificador" que hoy no existe.
  - **Decisión firme:** por ahora se mantiene el comportamiento actual (1 plantilla o dinámica); la
    composición queda como mejora futura. Requisito para arrancar: definir enfoque + preguntas
    compuestas reales a cubrir.
- Cobertura medida y pruebas E2E (Playwright) del flujo frontend↔backend.

**P3 — Operación avanzada**
- Métricas/dashboards, alertas, trazas; escaneo de dependencias/SAST en CI; gestor de secretos.

---

## Decisiones de arquitectura firmes
- Solo **Neo4j + OpenAI**; nada de Supabase/pgvector en este agente.
- Consultas Neo4j **solo lectura**, con doble validación (nodo + cliente).
- Schema **introspectado en vivo**, nunca hardcodeado; no depender de `nombre_norm`.
- Estrategias por costo: **caché → plantilla → dinámica**; reparación acotada (`MAX_INTENTOS = 2`).
- El grafo se construye sin abrir conexiones (LLM y Neo4j perezosos).

Relacionado: [[agente-langgraph]]
