# Prueba Neo4j CIAR

Consola local para cargar la ontologia completa del grafico CIAR y consultarla con LangGraph + LangSmith + un LLM local por Ollama.

## 1. Preparar entorno

```bash
cd "Prueba Neo4j"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Si Neo4j corre en otra PC de la misma red, cambia `NEO4J_URI` en `.env`:

```env
NEO4J_URI=bolt://192.168.1.25:7687
```

## 2. Descargar modelo local

Modelo recomendado para empezar fluido:

```bash
ollama pull qwen3:14b
```

Modelo mas potente si la PC lo aguanta:

```bash
ollama pull qwen3-coder:30b
```

## 3. Cargar grafo

```bash
python3 cargar_ontologia.py --reset
```

El loader respeta los IDs hash de los CSVs. No recalcula `FAC_`, `CAR_`, `CUR_`, `EMP_`, etc.

## 4. Correr agente

```bash
python3 agente_consola.py
```

O con otro modelo:

```bash
python3 agente_consola.py --model qwen3-coder:30b
```

Si el agente corre en la PC potente y Neo4j en esta Mac:

```env
NEO4J_URI=bolt://IP_DE_LA_MAC:7687
OLLAMA_BASE_URL=http://localhost:11434
```

Si el agente corre en esta Mac y Ollama en la PC potente:

```env
OLLAMA_BASE_URL=http://IP_PC_POTENTE:11434
```

Comandos dentro de consola:

```text
/schema
/salir
```

## 5. LangSmith

Para activar trazas:

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=tu_api_key
LANGSMITH_PROJECT=ciar-local-langgraph
```

El agente manda tags y metadata por corrida. Tambien exporta el grafo LangGraph a:

```text
langgraph_agent.mmd
```

## Estado validado

La carga incremental en Neo4j local dejo:

```text
14 labels
26 relaciones declaradas
44,401 OfertaLaboral
120,817 RequerimientoLaboral
36,909 EvalDesempeno
```

Nota: `ASOCIADA_A` queda declarada, pero no se poblo porque las evaluaciones apuntan a requerimientos sin `id_puesto` ni oferta asociada en los CSV actuales.
# Agente-empleabilidad-silabos
