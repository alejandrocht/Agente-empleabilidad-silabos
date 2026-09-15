# CIAR — Agente de Empleabilidad y Currículo

Agente inteligente basado en LangGraph, Neo4j y FastAPI para la consulta conversacional en lenguaje natural y la normalización analítica de mallas curriculares y datos de empleabilidad universitaria.

---

## 📚 Documentación del Proyecto (OpenWiki)

La documentación técnica y arquitectónica de este repositorio está generada y mantenida con **[OpenWiki](https://github.com/langchain-ai/openwiki)** dentro del directorio [`openwiki/`](openwiki/).

### 🤖 Instrucciones para Agentes de IA / AI Agents

> **Instrucción crítica para cualquier Agente de IA (Antigravity, Cursor, Claude Code, Codex, Copilot, etc.):**
>
> 1. **Fuente de verdad arquitectónica:** Cuando el usuario o desarrollador solicite documentación, pregunte por la arquitectura del proyecto, flujos de datos, seguridad de Neo4j, servicios de backend o el pipeline curricular, consulta directamente las páginas estructuradas en [`openwiki/`](openwiki/) (comenzando por [`openwiki/quickstart.md`](openwiki/quickstart.md)).
> 2. **Lanzar el Visualizador Interactivo:** Siempre que el usuario solicite ver la documentación, entender visualmente el proyecto o explorar las relaciones entre componentes, **inicia el servidor del visualizador interactivo** ejecutando:
>    ```bash
>    openwiki visualize openwiki --port 4321
>    ```
>    E infórmale al usuario que puede abrir [http://127.0.0.1:4321](http://127.0.0.1:4321) en su navegador para explorar el grafo interactivo de nodos y el lector Markdown en tiempo real.

---

## 🗺️ Mapa de la Documentación (`openwiki/`)

| Sección | Descripción | Enlace |
| :--- | :--- | :--- |
| **Inicio Rápido** | Puesta en marcha, variables de entorno y mapa general. | [`openwiki/quickstart.md`](openwiki/quickstart.md) |
| **Arquitectura LangGraph** | Topología del autómata de estados, nodos y memoria conversacional. | [`openwiki/architecture/langgraph-agent.md`](openwiki/architecture/langgraph-agent.md) |
| **Seguridad Neo4j & Cypher** | Reglas de solo lectura, compuerta estática `CypherGuard` y resolución de entidades. | [`openwiki/architecture/neo4j-security.md`](openwiki/architecture/neo4j-security.md) |
| **Servicios API & Dashboard** | Endpoints FastAPI, streaming SSE y caché en memoria. | [`openwiki/services/api-and-dashboard.md`](openwiki/services/api-and-dashboard.md) |
| **Normalizador Curricular** | Pipeline de procesamiento de sílabos y compuertas de aprobación humana. | [`openwiki/pipeline/normalizador-curricular.md`](openwiki/pipeline/normalizador-curricular.md) |
| **Frontend Web** | Interfaz Next.js 16, proxy inverso y visualizaciones Recharts. | [`openwiki/frontend/overview.md`](openwiki/frontend/overview.md) |

---

## 🚀 Puesta en Marcha

Para iniciar el backend (FastAPI en `http://127.0.0.1:8001`) y el frontend (Next.js en `http://localhost:3000`) de forma supervisada con reinicio automático:

```bash
./start_services.sh
```

Para probar el agente de forma directa por terminal:

```bash
cd backend
python scripts/consola.py
```
