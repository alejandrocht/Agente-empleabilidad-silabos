---
type: architecture
title: Integración con Neo4j y Capa de Seguridad Cypher
description: Arquitectura de acceso seguro a Neo4j, validación estricta de solo lectura mediante Cypher Guard y resolución determinista de entidades.
tags: [neo4j, cypher, security, cypher-guard, entity-resolution]
verified:
  - by: openwiki/0.5.1
    at: 2026-09-15T01:46:01.029Z
sources:
  - id: openwiki-source-07070640438f8be87e0b0109
    resource: repo://backend/agente/nodos/cypher_guard.py
  - id: openwiki-source-9d306a90240e4aff5b0a2859
    resource: repo://backend/agente/nodos/resuelve_entidades.py
  - id: openwiki-source-e9391e54f6cc5d23248c64e6
    resource: repo://backend/agente/utils/cypher_guard.py
  - id: openwiki-source-89c93e447d158380ecebcb6c
    resource: repo://backend/agente/utils/db.py
generated: { by: "codex", at: "2026-09-15T01:46:01.029Z" }
---

# Integración con Neo4j y Capa de Seguridad Cypher

La seguridad del acceso a la base de datos de grafos en CIAR se rige por un principio fundamental: **aislamiento estricto de solo lectura y validación estática de consultas a prueba de fallos (*fail-closed*)**. Ningún endpoint expuesto acepta Cypher arbitrario, y todas las sentencias generadas por modelos de lenguaje son analizadas antes de su ejecución.

## Enrutamiento y Conectividad a Neo4j

El módulo `backend/agente/utils/db.py` encapsula la conectividad con el driver oficial asíncrono de Neo4j (`neo4j.AsyncGraphDatabase`).

```mermaid
sequenceDiagram
    participant LLM as Generador Cypher
    participant ER as resuelve_entidades
    participant Guard as cypher_guard
    participant DB as Gateway Neo4j (db.py)
    participant Neo4j as Instancia Neo4j
    
    LLM->>ER: Cypher candidato + Parámetros
    ER->>Guard: Parámetros resueltos contra esquema
    Guard->>Guard: Validación estática (CypherGuard)
    alt Consulta insegura o cláusula mutacional
        Guard-->>DB: Rechazo inmediato (fail-closed)
    else Consulta segura de solo lectura
        Guard->>DB: Sentencia GuardedCypher
        DB->>Neo4j: Sesión con RoutingControl.READ
        Neo4j-->>DB: Registros validados
    end
```

### Reglas de Conexión y Concurrencia
- **Enrutamiento de solo lectura:** Todas las transacciones de dominio se ejecutan forzando `routing_=RoutingControl.READ`. Esto asegura que el clúster o la instancia desvíe el tráfico exclusivamente a réplicas de lectura y rechace cualquier intento de mutación a nivel del motor.
- **Precedencia de credenciales:** Se da prioridad a las variables de lectura dedicadas (`NEO4J_READ_URI`, `NEO4J_READ_USER`, `NEO4J_READ_PASSWORD`), retrocediendo en bloque a las variables principales (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`) solo si no se configuran las primeras.
- **Timeout y límites:** Las consultas imponen un tiempo límite por defecto (`DEFAULT_QUERY_TIMEOUT_SECONDS = 15.0`) y un límite máximo de resultados por consulta (`MAX_QUERY_LIMIT = 100`).

## Cypher Guard: Validación Estática

La función `cypher_guard` en `backend/agente/nodos/cypher_guard.py` actúa como la última compuerta determinista antes de la base de datos. Utiliza el analizador léxico `guard_cypher()` (`backend/agente/utils/cypher_guard.py`):

1. **Lista de exclusión estricta (*Forbidden Words*):**
   Cualquier consulta que contenga cláusulas de modificación, administración o llamadas a procedimientos arbitrarios es rechazada inmediatamente. Entre las palabras reservadas prohibidas se incluyen:
   - Modificación: `CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`, `REMOVE`
   - Procedimientos y llamadas: `CALL`, `YIELD`, `LOAD`, `FOREACH`
   - Esquema y administración: `DROP`, `ALTER`, `GRANT`, `DENY`, `REVOKE`, `DATABASE`
2. **Parametrización obligatoria:**
   Los valores dinámicos no deben concatenarse en la cadena de consulta; se exige el uso de parámetros tipados (`$parametro`) que son cotejados con el mapa de parámetros de entrada.
3. **Manejo de errores:**
   Si la consulta es rechazada, se emite un error estructurado (`cypher_guard_failed`) y se devuelve un mensaje seguro predefinido (`SAFE_QUERY_ERROR`), evitando exponer detalles internos de la base de datos al usuario.

## Resolución de Entidades

Antes de ingresar al guardián estático, el nodo `resuelve_entidades` (`backend/agente/nodos/resuelve_entidades.py`) asegura que los nombres textuales ingresados en la consulta (ej. carreras, competencias o industrias) concuerden con los nodos reales presentes en el grafo:

- Normaliza cadenas textuales eliminando caracteres especiales y aplicando coincidencias exactas o aproximadas.
- Hidrata los parámetros del estado con identificadores o nombres canónicos verificados.
- Si una entidad no puede ser resuelta de manera inequívoca, aborta con `SAFE_ENTITY_RESOLUTION_ERROR` sin enviar consultas inválidas a Neo4j.
