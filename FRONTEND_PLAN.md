# Plan de implementación — Frontend del Agente CIAR (Demo)

> Documento de planificación. **No es código de producción**, sino la guía para construir
> una interfaz web de demostración sobre el agente LangGraph existente.
> Stack objetivo: **React + Tailwind**, con **cache de historial de conversaciones** en el navegador.

---

## 1. Objetivo y alcance

Construir una interfaz tipo *chat* que permita mostrar en vivo cómo el agente:

1. Recibe una pregunta en español.
2. La convierte en Cypher.
3. Consulta Neo4j.
4. Responde en lenguaje natural.

**Enfoque demo (no producción):**
- Simplicidad primero: mínimo de dependencias, código legible y comentado.
- Mostrar el "razonamiento" del agente (paso por cada nodo del grafo) como valor diferencial de la demo.
- Persistir el historial de conversaciones en el navegador (cache local), sin base de datos extra.

**Fuera de alcance (por ahora):** autenticación, multiusuario real, despliegue productivo, edición del grafo Neo4j.

---

## 2. Problema de arquitectura: el agente es CLI

Hoy el agente vive en `main.py` como un bucle de consola. **No expone HTTP.**
Un frontend React no puede llamar directamente a Python/LangGraph. Necesitamos una **capa API delgada**.

```
┌──────────────┐      HTTP/JSON        ┌──────────────┐    invoke/stream    ┌──────────────┐    Cypher    ┌────────┐
│  React (SPA) │  ───────────────────► │  FastAPI     │  ─────────────────► │  Grafo       │  ──────────► │ Neo4j  │
│  + Tailwind  │  ◄─────────────────── │  (puente)    │  ◄───────────────── │  LangGraph   │  ◄────────── │        │
└──────────────┘   respuesta + pasos   └──────────────┘   estado por nodo   └──────────────┘   filas       └────────┘
      │                                                          │
      ▼                                                          ▼
 localStorage                                            utils/memoria.py
 (cache historial front)                                 (memoria RAM por id_sesion)
```

**Regla clave:** el `id_sesion` que maneja el front debe usarse como `thread_id` en el backend.
Así la memoria conversacional que ya existe (`utils/memoria.py`) sigue funcionando y el agente resuelve
referencias como *"esa carrera"* entre turnos.

> Nota de reutilización (DRY): la API **no** reimplementa lógica del agente. Solo llama a
> `construir_grafo()` una vez al arrancar y reutiliza `grafo.stream(...)` igual que `main.py`.

---

## 3. Capa API mínima (FastAPI)

Contrato pequeño y estable. Solo lo necesario para la demo.

### 3.1 Endpoints

| Método | Ruta        | Propósito                                                        |
|--------|-------------|------------------------------------------------------------------|
| `GET`  | `/health`   | Verificar que el grafo y Neo4j están arriba.                     |
| `POST` | `/chat`     | Enviar una pregunta y recibir respuesta + pasos del flujo.       |
| `POST` | `/chat/stream` | (Opcional, fase 2) Igual que `/chat` pero streaming SSE por nodo. |

### 3.2 `POST /chat` — request

```jsonc
{
  "pregunta": "¿Cuántos cursos tiene Ingeniería de Sistemas?",
  "id_sesion": "sesion-abc123"   // el front lo genera y lo reutiliza como thread_id
}
```

### 3.3 `POST /chat` — response

Se expone el estado del agente que ya existe en `estado.py` (`EstadoAgente`).
No inventamos campos nuevos: mapeamos 1:1 lo que el grafo ya produce.

```jsonc
{
  "respuesta": "Ingeniería de Sistemas tiene 52 cursos.",  // texto final en español
  "cypher": "MATCH (c:Carrera {id:'CAR_...'})-[:TIENE_CURSO]->(x:Curso) RETURN count(x)",
  "entidades": [                                            // entidades resueltas contra Neo4j
    { "texto": "Ingeniería de Sistemas", "label": "Carrera", "id": "CAR_...", "nombre": "INGENIERIA DE SISTEMAS" }
  ],
  "filas": [ { "count(x)": 52 } ],                          // filas crudas devueltas por Neo4j
  "pasos": [                                                // recorrido por los nodos (para el panel de razonamiento)
    "obtiene_pregunta", "obtiene_grafo", "resuelve_entidad",
    "genera_cypher", "valida_cypher", "ejecuta_cypher",
    "analiza_resultado", "devuelve_resultado"
  ],
  "error": null                                             // mensaje si valida_cypher bloqueó algo, si no null
}
```

### 3.4 Esbozo del puente (ilustrativo, comentado)

```python
# api.py — puente HTTP sobre el agente. NO duplica lógica: reutiliza el grafo existente.
from fastapi import FastAPI
from pydantic import BaseModel
from agent import construir_grafo          # mismo builder que usa main.py
from utils.config import cargar_entorno

cargar_entorno()                            # carga .env (Neo4j + LLM)
grafo = construir_grafo()                   # se construye UNA sola vez al arrancar
app = FastAPI()

class ChatIn(BaseModel):
    pregunta: str
    id_sesion: str

@app.post("/chat")
def chat(body: ChatIn):
    # thread_id = id_sesion  → así se reaprovecha la memoria RAM del backend
    config = {"configurable": {"thread_id": body.id_sesion}, "recursion_limit": 15}
    entrada = {"pregunta": body.pregunta, "id_sesion": body.id_sesion}

    pasos, estado_final = [], {}
    # Mismo patrón de stream que main.py: acumulamos el estado y guardamos el nombre de cada nodo.
    for paso in grafo.stream(entrada, config=config, stream_mode="updates"):
        for nombre_nodo, cambios in paso.items():
            pasos.append(nombre_nodo)
            if cambios:
                estado_final.update(cambios)

    # Devolvemos solo el subconjunto del estado que el front necesita.
    return {
        "respuesta": estado_final.get("respuesta", "(sin respuesta)"),
        "cypher":    estado_final.get("cypher"),
        "entidades": estado_final.get("entidades", []),
        "filas":     estado_final.get("filas", []),
        "pasos":     pasos,
        "error":     estado_final.get("error"),
    }
```

---

## 4. Stack del frontend

| Capa            | Elección                | Motivo                                                        |
|-----------------|-------------------------|---------------------------------------------------------------|
| Build/dev       | **Vite**                | Arranque rápido, cero config para demo.                       |
| UI              | **React** (18)          | Requerido.                                                    |
| Estilos         | **Tailwind CSS**        | Requerido. Estilos utilitarios, sin CSS suelto.              |
| Estado          | Hooks nativos (`useState`, `useReducer`) | Demo pequeña; no hace falta Redux/Zustand.  |
| HTTP            | `fetch` nativo          | Sin axios; menos dependencias.                               |
| Cache historial | **localStorage**        | Persiste conversaciones entre recargas, sin backend extra.  |
| Iconos          | `lucide-react`          | Ligero (opcional).                                           |

**Descartado a propósito:** librerías de estado global, UI kits pesados, react-query.
La demo no los necesita y agregan ruido.

---

## 5. Estructura de carpetas del front

```
frontend/
├── index.html
├── package.json
├── tailwind.config.js
├── vite.config.js
└── src/
    ├── main.jsx                 # punto de entrada React
    ├── App.jsx                  # layout: Sidebar + ChatWindow
    ├── api/
    │   └── agente.js            # única función que habla con la API (fetch a /chat)
    ├── hooks/
    │   ├── useConversaciones.js # cache de historial en localStorage (ver §7)
    │   └── useChat.js           # envía pregunta, maneja loading/error
    ├── components/
    │   ├── Sidebar.jsx          # lista de conversaciones + botón "nueva"
    │   ├── ChatWindow.jsx       # contenedor del chat activo
    │   ├── ListaMensajes.jsx    # renderiza los turnos
    │   ├── Burbuja.jsx          # una burbuja (usuario o agente)
    │   ├── PanelRazonamiento.jsx# muestra pasos por nodo + Cypher + entidades
    │   ├── TablaFilas.jsx       # renderiza `filas` crudas como tabla
    │   └── BarraInput.jsx       # textarea + botón enviar + sugerencias
    └── lib/
        └── ids.js               # genera id_sesion / id de conversación
```

---

## 6. Componentes clave

- **`App.jsx`** — layout de dos columnas: `Sidebar` (historial) a la izquierda, `ChatWindow` a la derecha.
- **`Sidebar.jsx`** — lista de conversaciones cacheadas (título + fecha), botón *"+ Nueva conversación"*, click para cambiar de conversación, opción borrar.
- **`ChatWindow.jsx`** — orquesta la conversación activa: `ListaMensajes` + `BarraInput`.
- **`Burbuja.jsx`** — dos variantes: usuario (derecha, simple) y agente (izquierda, con acordeón hacia `PanelRazonamiento`).
- **`PanelRazonamiento.jsx`** — **el diferenciador de la demo**. Acordeón colapsable que muestra:
  - Los `pasos` (nodos recorridos) como *stepper* horizontal.
  - El `cypher` generado en bloque de código con botón *copiar*.
  - Las `entidades` resueltas (chips: label + nombre + id).
  - Si `error != null`, banner rojo *"Consulta bloqueada por seguridad"*.
- **`TablaFilas.jsx`** — convierte `filas` (array de objetos) en una tabla; si es un solo número, lo muestra grande.
- **`BarraInput.jsx`** — textarea con envío por Enter, y **chips de preguntas sugeridas** (las 10 de §9) para lanzar la demo sin escribir.

---

## 7. Cache de historial de conversaciones (localStorage)

### 7.1 Esquema de datos

```jsonc
// Clave en localStorage: "ciar.conversaciones"
{
  "conversaciones": [
    {
      "id": "conv-abc123",          // id de conversación (front)
      "id_sesion": "sesion-abc123", // se envía a la API como thread_id (memoria backend)
      "titulo": "Cursos de Sistemas", // se autogenera con la 1ª pregunta
      "creada": 1720300000000,
      "actualizada": 1720300500000,
      "mensajes": [
        { "rol": "usuario", "texto": "¿Cuántos cursos tiene Ingeniería de Sistemas?" },
        {
          "rol": "agente",
          "texto": "Ingeniería de Sistemas tiene 52 cursos.",
          "cypher": "MATCH ...",
          "entidades": [ /* ... */ ],
          "filas": [ { "count(x)": 52 } ],
          "pasos": [ "obtiene_pregunta", "..." ],
          "error": null
        }
      ]
    }
  ],
  "activa": "conv-abc123"           // qué conversación está abierta
}
```

### 7.2 Hook `useConversaciones` (ilustrativo, comentado)

```jsx
// hooks/useConversaciones.js
// Fuente única de verdad del historial. Lee/escribe localStorage y expone acciones.
import { useState, useEffect } from "react";

const CLAVE = "ciar.conversaciones";

function cargar() {
  // Lee el cache; si no existe o está corrupto, empieza vacío.
  try { return JSON.parse(localStorage.getItem(CLAVE)) ?? { conversaciones: [], activa: null }; }
  catch { return { conversaciones: [], activa: null }; }
}

export function useConversaciones() {
  const [estado, setEstado] = useState(cargar);

  // Cada cambio de estado se persiste automáticamente en el cache.
  useEffect(() => { localStorage.setItem(CLAVE, JSON.stringify(estado)); }, [estado]);

  const nuevaConversacion = () => { /* crea id + id_sesion y la marca activa */ };
  const agregarMensaje = (convId, mensaje) => { /* push + actualiza `actualizada` */ };
  const seleccionar = (convId) => setEstado(s => ({ ...s, activa: convId }));
  const borrar = (convId) => { /* filtra la conversación fuera del array */ };

  return { estado, nuevaConversacion, agregarMensaje, seleccionar, borrar };
}
```

### 7.3 Reglas de la cache

- **El `id_sesion` es estable por conversación**: se genera al crear la conversación y se reenvía en cada `/chat`. No regenerarlo por mensaje (rompería la memoria backend).
- **Título automático**: primera pregunta recortada a ~40 caracteres.
- **Límite blando**: si hay >30 conversaciones, avisar/podar las más viejas (evita llenar localStorage, ~5 MB).
- **Botón "Limpiar historial"** en Sidebar para reiniciar la demo.
- La cache del front (persistente) y la memoria del backend (RAM, se pierde al reiniciar la API) son **independientes**: si la API se reinicia, el front conserva el texto pero el agente pierde el contexto conversacional. Aceptable para demo.

---

## 8. Estados de la UI durante una consulta

| Estado         | Qué muestra el front                                                       |
|----------------|----------------------------------------------------------------------------|
| `idle`         | Chat listo, chips de preguntas sugeridas visibles.                        |
| `enviando`     | Burbuja del agente con *skeleton* + texto "Generando Cypher…".            |
| `ok`           | Respuesta + acordeón de razonamiento colapsado.                           |
| `bloqueado`    | `error != null`: banner "Consulta no permitida (solo lectura)".           |
| `error_red`    | Fallo de fetch/timeout: toast "No se pudo contactar al agente".           |

> Fase 2 (streaming SSE): en `enviando` se puede iluminar el *stepper* nodo por nodo en tiempo real,
> replicando el `[Flujo] Paso por el nodo: '...'` que hoy imprime `main.py`. Alto impacto visual para demo.

---

## 9. Batería de pruebas: 10 tipos de preguntas y respuesta esperada

Casos elegidos para cubrir los distintos comportamientos del agente y validar el render del front.
Basados en `PREGUNTAS_EJEMPLO.md` y el flujo real del grafo.

| # | Tipo | Pregunta | Comportamiento esperado del agente | Cómo lo renderiza el front |
|---|------|----------|-------------------------------------|-----------------------------|
| 1 | **Conteo simple** | ¿Cuántas carreras hay? | Cypher `MATCH (c:Carrera) RETURN count(c)`. Sin entidad a resolver. Respuesta: 1 número. | Número grande + texto. |
| 2 | **Conteo con entidad** | ¿Cuántos cursos tiene Ingeniería de Sistemas? | Resuelve "Ingeniería de Sistemas" → id de Carrera; cuenta cursos. | Número + chip de entidad resuelta. |
| 3 | **Listado** | ¿Qué facultades existen? | Devuelve varias filas (nombres). | `TablaFilas` en una columna. |
| 4 | **Relación 1-a-N** | ¿Qué carreras ofrece la Facultad de Ingeniería? | Resuelve Facultad → lista de Carreras relacionadas. | Lista + chip de entidad. |
| 5 | **Superlativo / agregación** | ¿Qué carrera tiene más cursos? | `ORDER BY count DESC LIMIT 1`. Una fila ganadora. | Respuesta destacada; tabla opcional. |
| 6 | **Ranking / Top-N** | Top 10 herramientas más solicitadas en ofertas de Ingeniería de Sistemas. | Agregación + `ORDER BY ... DESC LIMIT 10`. | Tabla ordenada de 10 filas. |
| 7 | **Cruce currícula ↔ mercado** | ¿Qué herramientas piden las ofertas de Ing. Industrial que NO se enseñan en su currícula? | Consulta con doble patrón + `WHERE NOT`. Puede devolver 0..N. | Lista; si vacío, mensaje "no se encontró brecha". |
| 8 | **Referencia conversacional** | (tras la #2) "¿Y qué competencias desarrolla?" | Usa la **memoria** (`memoria_texto`) para resolver "esa carrera" = Sistemas. | Demuestra continuidad; chip de entidad heredada. |
| 9 | **Consulta insegura (bloqueo)** | Elimina la carrera de Derecho / borra todos los cursos. | `valida_cypher` bloquea (no `DELETE`/`SET`). `error` poblado, sin ejecución. | Banner rojo "Consulta no permitida (solo lectura)". |
| 10 | **Fuera de dominio / sin datos** | ¿Cuál es el clima en Lima hoy? | No hay entidad ni patrón en el grafo; filas vacías o Cypher sin resultado. | Mensaje honesto: "No tengo esa información en el grafo del CIAR". |

**Qué valida cada caso en el front:**
- 1–6 → render correcto de número, lista y tabla.
- 7 → manejo de resultado vacío.
- 8 → que el `id_sesion` estable reactiva la memoria backend.
- 9 → que el `error` se muestra distinto (no como respuesta normal).
- 10 → tono honesto ante lo que el grafo no sabe.

> Estas 10 preguntas también alimentan los **chips sugeridos** de `BarraInput`, para correr la demo con un click.

---

## 10. Diseño visual (Tailwind)

- **Layout**: 2 columnas. Sidebar `w-72` fija; chat `flex-1` centrado con `max-w-3xl`.
- **Tema**: claro por defecto, con opción oscuro (`dark:` de Tailwind).
- **Burbujas**: usuario `bg-blue-600 text-white` a la derecha; agente `bg-slate-100 dark:bg-slate-800` a la izquierda.
- **Cypher**: bloque `font-mono text-sm bg-slate-900 text-emerald-300 rounded-lg` con botón copiar.
- **Stepper de nodos**: chips pequeños; el nodo activo se ilumina (`bg-emerald-500 animate-pulse` en fase streaming).
- **Accesible**: contraste AA, foco visible en input, `aria-label` en botones de icono.

---

## 11. Roadmap de implementación

| Fase | Entregable | Verificación |
|------|-----------|--------------|
| **0. Puente API** | `api.py` FastAPI con `/health` y `/chat` sobre el grafo existente. | `GET /health` OK + 1 pregunta real contra Neo4j responde JSON. |
| **1. Scaffold front** | Vite + React + Tailwind corriendo, layout vacío. | `npm run dev` abre y estiliza. |
| **2. Chat básico** | Enviar pregunta → mostrar respuesta (sin razonamiento aún). | Pregunta #1 devuelve número en pantalla. |
| **3. Panel de razonamiento** | Stepper de nodos + Cypher + entidades + `TablaFilas`. | Preguntas #3, #6 renderizan tabla; #9 muestra banner. |
| **4. Cache de historial** | `useConversaciones` + Sidebar; persiste al recargar. | Recargar mantiene conversaciones; `id_sesion` estable (caso #8 funciona). |
| **5. Pulido demo** | Chips sugeridos, tema oscuro, estados de carga/error. | Las 10 preguntas de §9 se ven correctas. |
| **6. (Opcional) Streaming** | `/chat/stream` SSE + stepper en tiempo real. | Nodos se iluminan uno a uno. |

---

## 12. Criterios de éxito de la demo

1. Un evaluador escribe (o clickea) cualquiera de las 10 preguntas y recibe respuesta correcta.
2. Puede **ver el Cypher** que el agente generó y los nodos que recorrió.
3. La pregunta de seguridad (#9) se **bloquea visiblemente**, demostrando que es solo lectura.
4. La referencia conversacional (#8) funciona, demostrando memoria.
5. Al recargar la página, el **historial sigue ahí** (cache local).
6. Cero configuración manual para el evaluador más allá de tener la API arriba.
