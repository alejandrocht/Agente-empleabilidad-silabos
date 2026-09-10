# Ficha técnica de CIAR

> **En una frase:** CIAR permite consultar datos académicos y laborales con preguntas en español y, por separado, ordenar sílabos y archivos de empleabilidad antes de proponer su publicación en Neo4j.

Esta ficha describe el código y la documentación actuales del repositorio. No agrega capacidades que no estén implementadas.

## 1. Resumen rápido


| Estado                        | Qué significa en CIAR                                                                                                                                                              |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Implementado**              | Chat en español, consultas de solo lectura, dashboard de datos permitidos y normalización de fuentes.                                                                              |
| **Implementado con revisión** | El normalizador curricular puede proponer conceptos nuevos, pero la persona revisora decide qué hacer con ellos.                                                                   |
| **Opcional**                  | Extracción desde Cactus, embeddings, escalamiento residual del análisis LLM y bootstrap de perfiles de carrera.                                                                    |
| **Diferido**                  | Algunos indicadores del dashboard todavía no tienen una proyección de datos validada.                                                                                              |
| **Live-only**                 | Una pregunta real a Neo4j, llamadas reales a OpenAI/LangSmith y extracción real desde Cactus necesitan servicios externos conectados. No forman parte de una comprobación offline. |


## 2. ¿Qué es CIAR y qué problema resuelve?

CIAR es una aplicación para dos necesidades relacionadas:

1. **Consultar:** una persona escribe una pregunta normal, por ejemplo: “¿Qué habilidades piden para este tipo de puesto?”. CIAR busca una respuesta usando el grafo Neo4j, sin permitir escrituras desde el chat.
2. **Preparar datos:** un equipo carga sílabos o archivos de empleabilidad. CIAR los valida, limpia, relaciona con catálogos y deja evidencia para decidir si pueden publicarse.

El problema que resuelve es que los datos vienen en formatos distintos y con nombres ambiguos. CIAR intenta ordenarlos sin inventar información: conserva la referencia y la evidencia de la fuente, separa lo dudoso y bloquea la publicación cuando faltan pruebas.

## 3. Quién usa el sistema y sus dos partes


| Persona o función             | Uso principal                                                                                               |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------- |
| **Consultante**               | Hace preguntas en español sobre carreras, cursos, ofertas, empresas, habilidades o herramientas.            |
| **Operador de datos**         | Carga un XLSX, DOCX, PDF o ZIP y revisa el resultado de una ejecución.                                      |
| **Persona revisora**          | Decide qué hacer con una propuesta curricular ambigua o nueva.                                              |
| **Publicador administrativo** | Revisa un paquete aprobado y, solo con confirmación explícita, usa la ruta separada de importación a Neo4j. |


Estas son funciones operativas. No se debe interpretar esta tabla como prueba de que todas las rutas tengan un sistema completo de roles o login.

### Parte A: agente conversacional Neo4j, de solo lectura

- Recibe texto en español.
- Detecta si es un saludo, una pregunta fuera de alcance o una pregunta de datos.
- Para una pregunta de datos, obtiene el esquema, prepara una consulta y la valida.
- Ejecuta únicamente lecturas permitidas y redacta una respuesta comprensible.
- No recibe Cypher arbitrario del usuario y no escribe en Neo4j.

### Parte B: normalizador de empleabilidad y currículo

- Recibe archivos o, de forma opcional, obtiene sílabos desde Cactus.
- Crea una ejecución aislada con un ID, por ejemplo `NOR_...`.
- Valida, limpia, normaliza y guarda reportes de evidencia.
- Deja propuestas dudosas en una cola de pendientes.
- No publica automáticamente: el `release_gate` decide si el paquete puede pasar a la ruta administrativa de importación.

## 4. Entradas y salidas


| Flujo                  | Entrada                                                                         | Salida principal                                                                                |
| ---------------------- | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Chat                   | Pregunta en español y, opcionalmente, `thread_id`.                              | Respuesta en español y un identificador de correlación.                                         |
| Dashboard              | Filtros tipados, como carrera, dimensión, fecha y límite.                       | Datos de consultas permitidas; los datasets diferidos se informan como no disponibles.          |
| Empleabilidad          | XLSX con hojas de `Convenios`, `Informes` y/o `Publicaciones`.                  | Estado de ejecución, staging, CSV de empleabilidad, evidencia, propuestas y cuarentena.         |
| Currículo local        | DOCX o PDF, o ZIP con varios archivos, más `carrera` y `periodo` como `2026-1`. | Cuatro CSV curriculares candidatos, reportes de proveniencia, pendientes y `release_gate.json`. |
| Currículo desde Cactus | `carrera`, `periodo`, usuario y contraseña enviados solo para esa ejecución.    | Los mismos resultados del flujo curricular; las credenciales no aparecen en las salidas.        |


### El almacenamiento de una ejecución

El gestor de ejecuciones usa `NORMALIZADOR_DATA_DIR` —por defecto, el directorio local del normalizador— y crea una carpeta aislada por ejecución. Allí mantiene el manifiesto, los CSV y los reportes auditables. Cuando la ejecución termina, purga las fuentes binarias, el staging y el perfil temporal del navegador; conserva las salidas y los reportes necesarios para auditar.

### Staging no es salida final

**Staging** significa “resultado intermedio de trabajo”.

- `limpios/{rol}.jsonl` contiene registros de empleabilidad estructuralmente limpios.
- `limpios/silabos.jsonl` —el JSONL de limpieza curricular— es staging interno.
- Ninguno de esos JSONL es la salida final del negocio ni debe tratarse como paquete listo para importar.

### Los cuatro CSV canónicos curriculares

El paquete curricular define exactamente estos cuatro CSV bajo `salidas/`:

```yaml
catalogo_competencias.csv
catalogo_habilidades.csv
catalogo_herramientas.csv
cobertura_curricular.csv
```

Sus columnas son fijas:

```text
catalogo_competencias.csv:
id_competencia,nombre_competencia,descripcion_breve_competencia,tipo_competencia

catalogo_habilidades.csv:
id_habilidad,nombre_habilidad,descripcion_breve

catalogo_herramientas.csv:
id_herramienta,nombre_herramienta,descripcion_breve_herramienta

cobertura_curricular.csv:
id_cob_curricular,id_curso,id_silabo,id_competencia,id_habilidad,id_herramienta
```

Si todavía hay pendientes sin decisión, esos CSV canónicos se retiran temporalmente. En ese caso se conserva `salidas/reportes/candidatos_curriculares.json`; los cuatro CSV se materializan cuando todas las propuestas que requieren decisión tienen un resultado explícito.

En `cobertura_curricular.csv`, `id_herramienta` puede quedar vacío. Los demás identificadores conectan la relación con el curso, el sílabo, la competencia y la habilidad de origen.

La evidencia detallada queda fuera de esos CSV, en JSONL como:

- `salidas/reportes/competencias_fuente.jsonl`.
- `salidas/reportes/habilidades_fuente.jsonl`.
- `salidas/reportes/herramientas_fuente.jsonl`.
- `salidas/reportes/cobertura_curricular_fuente.jsonl`.
- `salidas/reportes/pendientes_curriculares.jsonl`.
- `salidas/reportes/decisiones_curriculares.jsonl`.
- `salidas/reportes/release_gate.json`.

El vertical de empleabilidad tiene sus propios CSV, entre ellos `empresa.csv`, `oferta_laboral.csv`, `puesto.csv`, `evaluacion_desempenio.csv`, `catalogo_empleabilidad.csv`, `habilidades_empleabilidad.csv`, `herramientas_empleabilidad.csv` y `requerimiento_laboral.csv`. No deben confundirse con los cuatro CSV canónicos curriculares.

## 5. Flujo completo, paso a paso

### A. Pregunta conversacional

```text
[Pregunta en español]
          |
          v
[FastAPI recibe y valida]
          |
          v
[Filtro de prompt injection]
          |
          v
[Orquestador]
     /                 \
    v                   v
[Respuesta directa]  [Esquema -> Cypher -> resolución de entidades]
                              |
                              v
                    [Cypher guard + gateway READ]
                              |
                              v
                    [Respuesta segura en español]
```

La validación de entrada ocurre antes de consultar el esquema, llamar al modelo o tocar la base. La respuesta final pasa además por un inspector determinista.

### B. Normalización curricular o de empleabilidad

```text
[Archivo local o fuente Cactus opcional]
                |
                v
       [Crear ejecución NOR_...]
                |
                v
       [Validar formato y fuente]
                |
                v
       [Limpiar y guardar staging]
                |
                v
 [Catálogos CHH + evidencia + reglas Python]
                |
                v
 [En currículo: analista LLM, si aplica]
                |
                v
 [Pendientes para revisión humana]
                |
                v
 [release_gate.json]
          /                    \
         v                      v
 [ALLOW_IMPORT]          [BLOCK_IMPORT]
         |                      |
         v                      v
 [Preview y confirmación] [Se conserva evidencia;
 [en ruta administrativa]   no se importa]
```

La validación ocurre en segundo plano. Por eso, una ejecución del normalizador no bloquea el chat ni el dashboard.

En empleabilidad, la limpieza y la normalización de la fuente son deterministas; el analista LLM pertenece al flujo curricular cuando está habilitado y sus propuestas requieren decisión humana.

## 6. Arquitectura y tecnologías reales


| Capa                          | Tecnología o componente                                     | Para qué sirve                                                                                       |
| ----------------------------- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Interfaz                      | Next.js, React y Recharts                                   | Pantallas de chat, dashboard y revisión del normalizador.                                            |
| API                           | FastAPI, ejecutada con Uvicorn                              | Expone chat, dashboard, normalizador y administración de importación.                                |
| Agente                        | LangGraph y LangChain Core                                  | Ordena los pasos del flujo conversacional.                                                           |
| Modelo                        | `langchain-openai` con `ChatOpenAI`                         | Genera o analiza texto cuando el flujo LLM está habilitado. El código activo usa OpenAI.             |
| Grafo                         | Driver oficial de Neo4j                                     | Ejecuta lecturas del dominio y, solo en la ruta administrativa separada, operaciones de publicación. |
| Seguridad de consultas        | `tooler.py`, `cypher_guard.py` y `utils/db.py`              | Limita consultas, valida Cypher y fuerza el acceso de lectura.                                       |
| Normalización de archivos     | `openpyxl`, `pypdf`, `python-docx`, CSV y JSONL             | Lee XLSX, PDF y DOCX y produce salidas trazables.                                                    |
| Fuente Cactus                 | Playwright y Chromium                                       | Descarga sílabos desde Cactus cuando se activa esa opción.                                           |
| Almacenamiento de ejecuciones | Sistema de archivos local y manifiestos JSON                | Aísla cada ejecución y conserva sus reportes y salidas.                                              |
| Catálogos                     | Catálogos CHH configurados por `NORMALIZADOR_CATALOGOS_DIR` | Sirven para contrastar competencias, habilidades y herramientas.                                     |


Detalles importantes:

- `backend/langgraph.json` apunta al entrypoint `agente/grafo/constructor.py:langgraph_entrypoint`.
- El grafo conversacional es **stateless**: no usa un checkpointer de LangGraph. `thread_id` sirve para correlacionar una conversación, no para compartir el estado interno de todas las solicitudes.
- `tooler.py` mantiene 20 plantillas Cypher inmutables y con parámetros validados. Las preguntas inciertas pueden usar una ruta dinámica, pero también pasan por el guard y el gateway de lectura.
- El dashboard usa consultas permitidas y reporta qué datasets están soportados o diferidos. No se deben fabricar métricas para llenar los huecos.

## 7. Seguridad y reglas de seguridad


| Regla                            | Cómo se aplica                                                                                                                                                                                  |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Neo4j de dominio es read-only    | El gateway usa configuración de lectura, `RoutingControl.READ`, `EXPLAIN` y comprueba que Neo4j clasifique la consulta como lectura (`query_type == "r"`) antes y después de ejecutarla.        |
| El Cypher se cierra ante la duda | El guard bloquea comandos de escritura o administración, comentarios, separadores y formas fuera del subconjunto permitido. También exige `RETURN`, parámetros coherentes y un `LIMIT` acotado. |
| No hay Cypher arbitrario         | El usuario envía una pregunta, no una cadena Cypher. Las plantillas y la ruta dinámica deben pasar por el mismo guard; la API pública no tiene un endpoint de Cypher libre.                     |
| El chat no publica datos         | `/chat`, `/chat/stream`, `/preguntar`, el planner, la resolución de entidades y el gateway de dominio no llaman a la ruta de escritura.                                                         |
| La importación está separada     | `/neo4j/validar` solo previsualiza. `/neo4j/importar` es una operación administrativa distinta y exige gate permitido, fingerprint coincidente y confirmación explícita.                        |
| Cactus no guarda la contraseña   | El endpoint recibe la contraseña como `SecretStr` para esa ejecución. No se copia al manifiesto, reportes ni parámetros persistidos; las referencias se liberan después de extraer.             |
| La sesión Cactus se limpia       | El perfil temporal del navegador y las cookies viven en el directorio temporal de la ejecución y se purgan al finalizar.                                                                        |
| La entrada se valida dos veces   | El filtro de prompt injection valida la pregunta original y vuelve a validar el texto contextualizado antes del esquema, el modelo o la base.                                                   |
| La salida pública se revisa      | El inspector determinista rechaza una respuesta vacía, demasiado larga, con ciertos scripts o señales de contenido interno/no permitido y usa un fallback seguro.                               |


El chat también usa una identidad anónima firmada en una cookie `HttpOnly` para correlación. Esa cookie no debe confundirse con una cuenta administrativa.

## 8. Cómo trabaja el normalizador

### Empleabilidad

1. Recibe un XLSX.
2. Busca hojas con los roles `Convenios`, `Informes` y `Publicaciones`, sin exigir años fijos.
3. Comprueba columnas mínimas y calcula el hash SHA-256 de la fuente.
4. Escribe tres JSONL de staging con valores limpios, IDs reproducibles y referencia a hoja y fila.
5. Contrasta empresas, puestos, habilidades y herramientas con el catálogo CHH.
6. Genera CSV, evidencia, propuestas de herramienta y cuarentena cuando faltan datos.

Una ejecución puede terminar como `limpiado`, `limpiado_con_advertencias`, `rechazado`, `error` o estados posteriores de normalización. Si no supera las puertas de publicación, queda como `no_publicado`.

### Currículo y sílabos

El flujo exige `carrera` y `periodo`. Extrae metadatos, sumilla, logro general, logros específicos y programa analítico. La lógica sigue este orden:

1. Registra las competencias declaradas por cada sílabo.
2. Relaciona cada logro con declaraciones del mismo sílabo.
3. Canonicaliza habilidades solo cuando encuentra evidencia suficiente.
4. Acepta herramientas solo en secciones estructuradas de recursos, software, herramientas digitales o programa analítico; no toma bibliografía, URLs ni recursos docentes genéricos como herramientas.
5. Rechaza esquemas inválidos, IDs duplicados, relaciones huérfanas y placeholders.

Ejemplos concretos:

- Si el programa analítico declara `MS Excel` como software, puede normalizarse al alias `Microsoft Excel` con evidencia.
- “Comunicar” por sí solo es demasiado genérico para publicarse automáticamente como habilidad.
- Un código curricular ausente o ambiguo conserva la descripción textual y genera una advertencia; no se inventa una relación.

### Analista LLM

- El analista LLM recibe lotes de hasta 8 casos compactos y devuelve una propuesta estructurada de competencia, habilidad, herramienta y evidencia.
- Python genera los IDs, valida la evidencia contra el texto fuente y rechaza resultados genéricos o sin evidencia.
- Las competencias transversales se excluyen con el motivo auditable `COMPETENCIA_GENERICA`.
- Toda propuesta LLM válida queda pendiente de decisión humana. La confianza declarada por el modelo es metadata auditable, no autoridad de aprobación ni ruteo.
- Si el proveedor LLM falla, el sistema conserva el resultado determinista y registra `ANALISTA_LLM_NO_DISPONIBLE`.
- El análisis y sus decisiones se auditan en `salidas/reportes/decisiones_llm.jsonl` y `salidas/reportes/analisis_llm.json`; esos archivos no cambian las columnas de los cuatro CSV.

En producción, `NORMALIZADOR_CURRICULAR_LLM=true` es la configuración esperada. Poner el LLM en `false` sirve para pruebas offline explícitas, no para representar el producto completo.

### Revisión humana


| Caso                                                   | Resultado                                                  |
| ------------------------------------------------------ | ---------------------------------------------------------- |
| Resultado claro y con evidencia                        | Sigue el flujo sin pedir una decisión manual individual.   |
| Duplicado exacto                                       | Puede deduplicarse automáticamente; la fuente no se borra. |
| Coincidencia semántica dudosa o herramienta sospechosa | Se conserva como pendiente y requiere revisión.            |
| Propuesta semántica del LLM                            | La persona elige `ADD`, `KEEP_PENDING` o `DISCARD`.        |


- `ADD` promueve el concepto únicamente al perfil de la combinación **carrera + periodo** de esa ejecución.
- `KEEP_PENDING` mantiene la evidencia fuera de los CSV canónicos.
- Las decisiones se guardan en `decisiones_curriculares.jsonl` y repetir la misma decisión es idempotente: no duplica filas ni decisiones.
- La revisión se concentra en ambigüedades y evolución del perfil, no en volver a aprobar cada logro claro.

### Release gate: el último control antes de importar

`release_gate.json` revisa, entre otras cosas, cobertura de fuente, proveniencia, relaciones y referencias canónicas, integridad del grafo CHH, errores estructurales, pendientes y materialización de los CSV.


| Decisión       | Significado práctico                                                                                                 |
| -------------- | -------------------------------------------------------------------------------------------------------------------- |
| `ALLOW_IMPORT` | El paquete cumple los bloqueos conocidos y **queda habilitado para la ruta de importación**. No importa por sí solo. |
| `BLOCK_IMPORT` | No se permite importar. Se conservan la evidencia, los reportes y los pendientes para corregir o revisar.            |


La ruta administrativa hace primero una previsualización y después exige confirmar explícitamente el mismo fingerprint. El chatbot nunca usa esa ruta de escritura.

### Opcional, diferido y live-only


| Clasificación         | Elementos                                                                                                                                                                                                   |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Opcional / opt-in** | Embeddings curriculares, escalamiento residual a otro modelo, bootstrap de perfil de carrera y extracción Cactus.                                                                                           |
| **Live-only**         | Pregunta real a Neo4j, llamadas reales a OpenAI, observabilidad externa como LangSmith y acceso real a Cactus.                                                                                              |
| **Diferido**          | `senales_revision_vigencia`, `cursos_con_mayor_correspondencia`, `diferenciadores_empresas`, `conocimientos_liderazgo` y `funciones_por_tipo_empresa`. El backend no debe rellenarlos con datos inventados. |
| **Offline limitado**  | Se puede comprobar estructura y lógica determinista sin afirmar conectividad, respuesta real del modelo ni datos vivos del grafo.                                                                           |


## 9. API principal, agrupada por propósito

La aplicación FastAPI monta estas rutas en `api.servidor:app`.

### Salud y conversación


| Método y ruta       | Uso                                                                         |
| ------------------- | --------------------------------------------------------------------------- |
| `GET /health`       | Comprueba que la API responde.                                              |
| `POST /chat`        | Pregunta JSON con `pregunta` y, opcionalmente, `thread_id`.                 |
| `POST /chat/stream` | La misma conversación mediante eventos SSE, es decir, respuesta progresiva. |
| `POST /preguntar`   | Endpoint conversacional compatible con el campo `texto`.                    |


Ejemplo de entrada:

```json
{
  "pregunta": "¿Qué habilidades se piden para las ofertas de esta carrera?"
}
```

### Dashboard de solo lectura


| Método y ruta                                     | Uso                                                  |
| ------------------------------------------------- | ---------------------------------------------------- |
| `GET /dashboard/metadata`                         | Lista datasets soportados y diferidos.               |
| `GET /dashboard/filtros/carreras`                 | Lista carreras disponibles para filtros.             |
| `GET /dashboard/ofertas/tendencia`                | Tendencia de ofertas.                                |
| `GET /dashboard/carreras/demanda`                 | Demanda por carrera.                                 |
| `GET /dashboard/carreras/{carrera_id}/industrias` | Industrias asociadas a una carrera.                  |
| `GET /dashboard/empresas`                         | Datos de empresas permitidos por el servicio.        |
| `GET /dashboard/dimensiones/{tipo}/demanda`       | Demanda de competencias, habilidades o herramientas. |
| `GET /dashboard/dimensiones/{tipo}/cobertura`     | Cobertura curricular de una dimensión soportada.     |
| `GET /dashboard/dimensiones/{tipo}/brechas`       | Brechas disponibles para una dimensión soportada.    |
| `GET /dashboard/dimensiones/{tipo}/industrias`    | Industrias para una dimensión soportada.             |


Estas rutas usan filtros y consultas allow-list. `allow-list` significa “lista cerrada de opciones permitidas”.

### Normalizador


| Método y ruta                                                             | Uso                                                                            |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `POST /normalizador/empleabilidad`                                        | Inicia una ejecución con XLSX.                                                 |
| `POST /normalizador/silabos`                                              | Inicia una ejecución con archivo curricular, carrera y periodo.                |
| `POST /normalizador/silabos/cactus`                                       | Inicia una ejecución que descarga desde Cactus con credenciales de esa sesión. |
| `GET /normalizador/ejecuciones`                                           | Lista ejecuciones.                                                             |
| `GET /normalizador/ejecuciones/{id_ejecucion}`                            | Consulta estado y resumen.                                                     |
| `GET /normalizador/ejecuciones/{id_ejecucion}/errores`                    | Consulta hallazgos y errores.                                                  |
| `POST /normalizador/ejecuciones/{id_ejecucion}/cancelar`                  | Solicita cancelar una ejecución.                                               |
| `GET /normalizador/ejecuciones/{id_ejecucion}/reporte`                    | Obtiene el reporte de la ejecución.                                            |
| `GET /normalizador/ejecuciones/{id_ejecucion}/outputs/{ruta_salida:path}` | Lee una salida declarada y segura.                                             |
| `GET /normalizador/ejecuciones/{id_ejecucion}/cuarentena`                 | Consulta registros aislados por falta de evidencia o errores.                  |
| `GET /normalizador/ejecuciones/{id_ejecucion}/pendientes`                 | Lista pendientes curriculares.                                                 |
| `POST /normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir`        | Registra `ADD` o `KEEP_PENDING`.                                               |
| `GET /normalizador/ejecuciones/{id_ejecucion}/release-gate`               | Consulta `ALLOW_IMPORT` o `BLOCK_IMPORT` y sus bloqueos.                       |
| `DELETE /normalizador/ejecuciones/{id_ejecucion}/historial`               | Elimina el registro local de historial según la política del gestor.           |


### Administración de publicación en Neo4j: separado del chatbot

Estas rutas no son el chat y sí pueden formar parte de una operación administrativa de publicación:


| Método y ruta                                         | Uso                                                                                    |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `GET /neo4j/estado`                                   | Estado seguro de la dependencia Neo4j.                                                 |
| `POST /neo4j/validar`                                 | Previsualiza formato, referencias, duplicados y novedad; no escribe.                   |
| `POST /neo4j/importar`                                | Escribe únicamente después del gate, fingerprint coincidente y confirmación explícita. |
| `GET /neo4j/importaciones`                            | Lista el historial de importaciones.                                                   |
| `POST /neo4j/importaciones/{id_importacion}/revertir` | Revierte una importación concreta con confirmación explícita.                          |


No hay que convertir estas rutas administrativas en comandos del chatbot. La conversación sigue siendo de solo lectura.

## 10. Prerrequisitos y ejecución local

### Mínimo necesario


| Necesidad                | Detalle                                                                                                                                                                   |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python                   | Versión `>=3.11`.                                                                                                                                                         |
| Gestor de entorno        | `uv`, usando el lockfile del repositorio.                                                                                                                                 |
| Modelo LLM               | Credencial `OPENAI_API_KEY` para las rutas que llamen a OpenAI. No se incluye ningún valor aquí.                                                                          |
| Neo4j                    | URI, usuario y contraseña de lectura configurados como un grupo completo `NEO4J_READ_*` o, si no existe ese grupo, el grupo legado completo. Usar un principal read-only. |
| Catálogo CHH             | Catálogos revisados en la ruta configurada por `NORMALIZADOR_CATALOGOS_DIR` para el normalizador.                                                                         |
| Cactus, solo si se usa   | Playwright y Chromium instalados en el entorno del backend.                                                                                                               |
| Frontend, solo si se usa | Node y dependencias frontend ya instaladas.                                                                                                                               |


### Comandos documentales

Los siguientes comandos se muestran **solo como documentación**. No se ejecutaron durante la creación de esta ficha.

```powershell
cd backend
uv sync --locked --extra dev

# Solo si no existe un .env local. Completar sus valores de forma privada.
Copy-Item .env.example .env

uv run --locked python -m uvicorn api.servidor:app --reload --port 8001
```

Para la consola conversacional, con Neo4j y OpenAI disponibles:

```powershell
cd backend
uv run --locked python scripts/consola.py
```

Para la interfaz web, en otra terminal:

```powershell
cd frontend
npm ci                 # solo la primera vez o cuando cambie package-lock.json
npm run dev
```

Por defecto, el frontend envía sus llamadas al backend en `http://127.0.0.1:8001`. Se puede cambiar con `API_URL`.

Para activar la fuente Cactus, de forma opcional:

```powershell
cd backend
uv run --locked python -m playwright install chromium
```

No se deben colocar contraseñas, tokens ni valores reales en esta ficha. Tampoco se debe leer `backend/.env` para documentar el proyecto.

### Offline no significa “conectado”

Una comprobación offline puede revisar imports, estructura, validadores y reglas deterministas. No puede demostrar una respuesta real de Neo4j, conectividad externa de OpenAI, telemetría externa ni una descarga real desde Cactus. Esas comprobaciones son **live-only** y no se ejecutaron aquí.

## 11. Limitaciones: lo que CIAR no hace

- El chatbot no acepta Cypher libre y no escribe en Neo4j.
- El guard es conservador y estático; no es un parser completo de Cypher ni puede sustituir la comprobación contra el esquema vivo.
- El normalizador no importa automáticamente sus resultados. Primero debe existir `ALLOW_IMPORT`; después se usa la ruta administrativa con preview, fingerprint y confirmación.
- Un LLM puede proponer algo incorrecto. Por eso Python exige evidencia, HITL decide su promoción y el gate puede bloquear.
- `limpios/silabos.jsonl` es staging. No es el producto curricular final.
- Cactus depende de una sesión externa, Playwright, Chromium y credenciales proporcionadas para esa ejecución. Una cobertura parcial bloquea la publicación.
- Embeddings y escalamiento residual no son obligatorios. Si no se activan o fallan, el flujo debe conservar razones y usar sus reglas de fallback, no inventar resultados.
- Cinco datasets del dashboard están diferidos porque no tienen una proyección de datos validada.
- Si el backend no está disponible, la interfaz puede mostrar datos de demostración claramente etiquetados. Eso no representa datos reales de Neo4j.
- No hay un mapa global fijo que permita asumir que códigos como `L1`, `E1` o `G1` significan lo mismo en todas las carreras. La validación se hace dentro de la combinación carrera-periodo y el sílabo que declara el código.

## 12. Glosario corto


| Término          | Significado simple                                                                         |
| ---------------- | ------------------------------------------------------------------------------------------ |
| **API**          | Puertas HTTP para que una interfaz hable con el backend.                                   |
| **Cypher**       | Lenguaje de consultas de Neo4j.                                                            |
| **Neo4j**        | Base de datos que guarda nodos y relaciones en forma de grafo.                             |
| **Read-only**    | Solo lectura: se puede consultar, no crear, cambiar ni borrar datos.                       |
| **LLM**          | Modelo de lenguaje que interpreta texto y devuelve propuestas.                             |
| **CHH**          | Catálogo de competencias, habilidades y herramientas.                                      |
| **Staging**      | Datos intermedios que todavía no son salida final.                                         |
| **JSONL**        | Archivo donde cada línea es un objeto JSON.                                                |
| **CSV**          | Archivo tabular separado por comas.                                                        |
| **Proveniencia** | Evidencia de dónde salió un dato: archivo, hoja, fila, sílabo o sección.                   |
| **Cuarentena**   | Zona para datos que no se pueden publicar por falta de evidencia o errores.                |
| **Pendiente**    | Propuesta que necesita una decisión o más evidencia.                                       |
| **Release gate** | Control final que devuelve `ALLOW_IMPORT` o `BLOCK_IMPORT`.                                |
| **Fingerprint**  | Huella de los archivos revisados; evita importar una versión distinta de la aprobada.      |
| **Idempotente**  | Repetir la misma operación no duplica el resultado.                                        |
| **Embedding**    | Representación numérica usada para sugerir similitudes; no reemplaza la evidencia textual. |
| **Live-only**    | Comprobación que necesita un servicio real conectado.                                      |


## 13. Referencias de código y documentación


| Referencia                                                                                                     | Qué se verificó allí                                                                                 |
| -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| [`AGENTS.md`](AGENTS.md)                                                                                       | Identidad del agente CIAR, stack, read-only, fuentes de verdad y reglas de verificación.             |
| [`CLAUDE.md`](CLAUDE.md)                                                                                       | Flujo del grafo, separación del agente y políticas del normalizador.                                 |
| [`backend/README.md`](backend/README.md)                                                                       | Instalación, endpoints principales, cuatro CSV, Cactus, LLM, evidencia, gate y límites live/offline. |
| [`backend/api/servidor.py`](backend/api/servidor.py)                                                           | App FastAPI, chat, streaming, dashboard, filtro público y cookie anónima.                            |
| [`backend/agente/grafo/constructor.py`](backend/agente/grafo/constructor.py)                                   | Construcción del grafo LangGraph y rutas conversacionales.                                           |
| [`backend/agente/utils/tooler.py`](backend/agente/utils/tooler.py)                                             | Plantillas Cypher inmutables y contrato de parámetros.                                               |
| [`backend/agente/utils/cypher_guard.py`](backend/agente/utils/cypher_guard.py)                                 | Bloqueos de Cypher, parámetros y límites.                                                            |
| [`backend/agente/utils/db.py`](backend/agente/utils/db.py)                                                     | Gateway Neo4j, `EXPLAIN`, `query_type == "r"` y `RoutingControl.READ`.                               |
| [`backend/agente/api/normalizador.py`](backend/agente/api/normalizador.py)                                     | Rutas de empleabilidad, sílabos, Cactus, ejecuciones, pendientes y gate.                             |
| [`backend/agente/normalizador/ejecuciones.py`](backend/agente/normalizador/ejecuciones.py)                     | Aislamiento, manifiestos, estados y limpieza de temporales.                                          |
| [`backend/agente/normalizador/silabos/analista_llm.py`](backend/agente/normalizador/silabos/analista_llm.py)   | Analista por lotes, evidencia, propuestas pendientes y fallback.                                     |
| [`backend/agente/normalizador/silabos/salida.py`](backend/agente/normalizador/silabos/salida.py)               | Esquemas de los cinco CSV, reportes, validación y release gate.                                      |
| [`backend/agente/normalizador/silabos/aprobaciones.py`](backend/agente/normalizador/silabos/aprobaciones.py)   | Decisiones `ADD`/`KEEP_PENDING`, alcance carrera-periodo e idempotencia.                             |
| [`backend/agente/normalizador/silabos/fuente_cactus.py`](backend/agente/normalizador/silabos/fuente_cactus.py) | Extracción Cactus y contrato de credenciales por ejecución.                                          |
| [`backend/agente/api/neo4j_importacion.py`](backend/agente/api/neo4j_importacion.py)                           | Endpoints administrativos separados para estado, preview, importación y reversión.                   |
| [`backend/agente/db/neo4j_importador.py`](backend/agente/db/neo4j_importador.py)                               | Confirmación, fingerprint y escritura administrativa reversible.                                     |
| [`backend/agente/dashboard/consultas.py`](backend/agente/dashboard/consultas.py)                               | Datasets soportados y diferidos del dashboard.                                                       |
| [`frontend/src/components/dashboard/Dashboard.jsx`](frontend/src/components/dashboard/Dashboard.jsx)           | Fallback de demostración explícito cuando el backend no está disponible.                             |

