---
type: quickstart
title: Guía de Inicio Rápido
description: Visión general de CIAR Agente Empleabilidad, requisitos de entorno, comandos de arranque y mapa de navegación de la wiki.
tags: [quickstart, overview, setup, guides]
verified:
  - by: openwiki/0.5.1
    at: 2026-09-15T01:46:01.029Z
sources:
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-a2371d6362e5db4bc834ad03
    resource: repo://CLAUDE.md
  - id: openwiki-source-253475e5d5e371c938204b1d
    resource: repo://start_services.sh
generated: { by: "codex", at: "2026-09-15T01:46:01.029Z" }
---

# Guía de Inicio Rápido — CIAR Agente Empleabilidad

Bienvenido a la documentación técnica de **CIAR (Agente de Empleabilidad y Currículo)**. Este sistema conecta el análisis del mercado laboral con la oferta académica universitaria, permitiendo realizar consultas en lenguaje natural en español contra una base de datos en grafo (Neo4j) y procesar analíticamente mallas curriculares y sílabos.

---

## Propósito y Principios Centrales

1. **Solo Lectura en Base de Datos:** El agente jamás realiza mutaciones en Neo4j. Cualquier consulta pasa por un analizador estático (`cypher_guard`) que bloquea cláusulas de escritura.
2. **Proveedor LLM Único:** OpenAI es el proveedor de modelos para las tareas conversacionales y de razonamiento.
3. **Auditabilidad de Datos:** La normalización curricular conserva proveniencia completa y requiere aprobación humana para publicar cambios hacia el grafo.

---

## Puesta en Marcha Rápida

### Requisitos Previos
- **Python:** `>= 3.11` con entorno virtual configurado en `backend/.venv`.
- **Node.js:** `>= 18` para la aplicación web en `frontend/`.
- **Instancia Neo4j:** Con credenciales de lectura configuradas en `backend/.env`.

### Variables de Entorno Críticas (`backend/.env`)
```bash
# Neo4j (Modo Solo Lectura)
NEO4J_READ_URI=bolt://localhost:7687
NEO4J_READ_USER=neo4j
NEO4J_READ_PASSWORD=secreto
NEO4J_DATABASE=neo4j

# Modelos OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL_ORQUESTADOR=gpt-4o-mini
OPENAI_MODEL_GENERADOR_CYPHER=gpt-4o
OPENAI_MODEL_ANALISTA=gpt-4o
```

### Ejecución de Servicios

Para arrancar el stack completo (backend FastAPI + frontend Next.js) de forma supervisada con auto-reinicio:

```bash
./start_services.sh
```

- **Backend (FastAPI):** `http://127.0.0.1:8001` (Documentación Swagger en `/docs`)
- **Frontend (Next.js):** `http://localhost:3000`

### Verificación por Consola

Si deseas probar el agente de forma directa desde la terminal sin levantar la interfaz gráfica:

```bash
cd backend
python scripts/consola.py
```

---

## Mapa de Navegación de la Documentación

Utiliza los siguientes enlaces para explorar las distintas capas arquitectónicas del sistema:

| Sección | Descripción | Enlace |
| :--- | :--- | :--- |
| **Arquitectura LangGraph** | Topología de nodos, manejo de estado `Estado` y memoria acotada. | [/architecture/langgraph-agent.md](/openwiki/architecture/langgraph-agent.md) |
| **Seguridad Neo4j & Cypher** | Reglas de solo lectura, `CypherGuard` y resolución de entidades. | [/architecture/neo4j-security.md](/openwiki/architecture/neo4j-security.md) |
| **API & Dashboard** | Endpoints REST, streaming SSE y caché en memoria de métricas. | [/services/api-and-dashboard.md](/openwiki/services/api-and-dashboard.md) |
| **Normalizador Curricular** | Pipeline de procesamiento de sílabos y release gates. | [/pipeline/normalizador-curricular.md](/openwiki/pipeline/normalizador-curricular.md) |
| **Frontend Web** | Interfaz Next.js, proxy de streaming y componentes visuales. | [/frontend/overview.md](/openwiki/frontend/overview.md) |
