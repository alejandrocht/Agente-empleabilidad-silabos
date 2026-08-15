# Backend del Agente CIAR

Agente LangGraph que convierte preguntas en español a Cypher, valida que las consultas sean
de solo lectura y consulta el schema vivo de Neo4j. OpenAI es el único proveedor LLM; cada rol
puede seleccionar su modelo desde `.env`.

## Instalación

```powershell
cd backend
python -m pip install -e ".[dev]"
Copy-Item .env.example .env  # solo si todavía no existe
```

Completa `OPENAI_API_KEY` y las credenciales de Neo4j. Para habilitar trazas, completa también
`LANGSMITH_API_KEY`; `LANGSMITH_TRACING=true` ya viene en la plantilla.

## Ejecución

```powershell
python scripts/consola.py
uvicorn agente.api.servidor:app --reload --port 8001
python -m pytest
ruff check src tests scripts
mypy src
```

Todas las consultas pasan por una guarda central y se ejecutan en sesiones Neo4j de lectura.
La caché y la memoria son efímeras, tienen TTL y permanecen acotadas por proceso.

## Normalizadores de Empleabilidad y Sílabos

El primer vertical del normalizador recibe el XLSX sin exigir años fijos. Identifica las hojas
por los roles `Convenios`, `Informes` y `Publicaciones`, valida sus columnas mínimas, calcula el
hash de la fuente y devuelve un ID de ejecución. La validación ocurre en segundo plano y no
bloquea el chat ni el dashboard.

```text
POST /normalizador/empleabilidad
GET  /normalizador/ejecuciones/{id_ejecucion}
GET  /normalizador/ejecuciones/{id_ejecucion}/errores
```

La respuesta distingue `limpiado`, `limpiado_con_advertencias`, `rechazado` y `error`. Cuando la
entrada es válida, genera tres JSONL de staging bajo `limpios/`, con valores estructuralmente
limpios, IDs reproducibles y referencia a la hoja/fila de origen. Luego aplica el catálogo CHH
versionado, conserva la evidencia y separa las propuestas de herramienta que requieren revisión.
Una ejecución pasa a `normalizado` solo si las relaciones candidatas cumplen las puertas de
publicación; en caso contrario queda en `no_publicado` con hallazgos y cuarentena consultables.

El vertical curricular recibe una fuente declarando carrera y periodo. Acepta un DOCX o PDF
individual, o un ZIP con varios archivos seguros:

```text
POST /normalizador/silabos
     multipart: archivo, carrera, periodo
GET  /normalizador/ejecuciones/{id_ejecucion}
GET  /normalizador/ejecuciones/{id_ejecucion}/errores
GET  /normalizador/ejecuciones/{id_ejecucion}/cuarentena
```

El corte curricular valida el paquete, extrae metadatos, sumilla, logro general, logros específicos
y programa analítico. El JSONL de limpieza es staging interno y no se ofrece como salida de negocio.
Cuando pasan las puertas curriculares, se publican exactamente cuatro CSV:

```text
salidas/catalogo_competencias.csv
salidas/catalogo_habilidades.csv
salidas/catalogo_herramientas.csv
salidas/cobertura_curricular.csv
```

La cobertura solo contiene `id_cob_curricular`, `id_curso`, `id_silabo`, `id_competencia`,
`id_habilidad` e `id_herramienta`. El último campo puede estar vacío; los demás identifican la
relación atómica y conectan cada resultado con el curso y el sílabo de origen. Si alguna puerta falla,
los CSV no se publican y la ejecución queda en `no_publicado` con hallazgos y cuarentena consultables.

Cada ejecución curricular está aislada por la pareja declarada `carrera` + `periodo`: esa pareja se
normaliza, se conserva en el registro y forma parte de los IDs de curso y sílabo. No se aplica un
mapa global fijo de `L1`, `E1` o `G1`; esos códigos se validan dentro del sílabo que los declara.
Cuando un logro referencia un código ausente o ambiguo, la descripción textual del logro conserva la
relación y el catálogo CHH solo ayuda a canonicalizarla. La inconsistencia se reporta como advertencia;
solo una falta de evidencia utilizable genera cuarentena.

El alcance de competencias es curricular, no global: si existe
`catalogos/carreras/{CARRERA}/{PERIODO}/`, se usa ese catálogo; si aún no existe, se construye un perfil
provisional con las competencias declaradas por los sílabos de la ejecución. El catálogo global conserva
el vocabulario compartido de habilidades y herramientas, pero no puede inventar una competencia de otra
carrera. Las referencias no declaradas (por ejemplo, `EE`) se conservan como evidencia de fuente y se
reportan para revisión. DOCX y PDF admiten códigos `E/G` numéricos y alfabéticos de forma acotada.

### Analista curricular LLM por carrera

Por defecto la ejecución curricular es determinista y no consume tokens. Para activar el analista
semántico y su inspector:

```dotenv
NORMALIZADOR_CURRICULAR_LLM=true
NORMALIZADOR_CURRICULAR_INSPECTOR=true
OPENAI_MODEL_CURRICULAR=gpt-5.6-luna
# Opcional: si no se define, el inspector curricular usa el mismo modelo.
OPENAI_MODEL_INSPECTOR_CURRICULAR=gpt-5.6-luna
# Opcional: Terra solo para residuales semánticos; por defecto permanece desactivado.
NORMALIZADOR_CURRICULAR_ESCALAR_RESIDUALES=false
OPENAI_MODEL_CURRICULAR_RESIDUAL=gpt-5.6-terra
OPENAI_MODEL_INSPECTOR_CURRICULAR_RESIDUAL=gpt-5.6-terra
LLM_TIMEOUT_SECONDS=120
LLM_MAX_RETRIES=2
```

La primera pasada usa Luna para el analista y el inspector (`OPENAI_MODEL_CURRICULAR` y
`OPENAI_MODEL_INSPECTOR_CURRICULAR`). El escalamiento residual está desactivado por defecto con
`NORMALIZADOR_CURRICULAR_ESCALAR_RESIDUALES=false`; al activarlo, solo los residuales semánticos
se envían a Terra mediante `OPENAI_MODEL_CURRICULAR_RESIDUAL` y
`OPENAI_MODEL_INSPECTOR_CURRICULAR_RESIDUAL`. Se escalan únicamente decisiones con
`LLM_SOLICITA_REVISION` o `CONFIANZA_BAJA`. No se escalan fallos mecánicos de evidencia,
herramientas o formato: Python los conserva como revisión determinista.

El analista recibe lotes compactos de logros, sumilla, contenido y perfil de la carrera. Devuelve
competencia, habilidad, herramientas y evidencia en JSON estructurado; Python genera los IDs,
normaliza nominalizaciones cerradas y valida la evidencia estructurada del programa analítico.
También rechaza habilidades genéricas, herramientas no detectadas, evidencia ausente o baja
confianza. El inspector puede aprobar, revisar o rechazar cada decisión. Si el proveedor falla,
se conserva el resultado determinista y se registra `ANALISTA_LLM_NO_DISPONIBLE`.

La auditoría se guarda fuera de los CSV en `salidas/reportes/decisiones_llm.jsonl` y
`salidas/reportes/analisis_llm.json`. Los reportes incluyen los modelos y las decisiones escaladas
para mantener la trazabilidad. Python no modifica los CSV: los cuatro archivos mantienen exactamente
sus columnas actuales.

Las herramientas no se buscan en el texto completo: únicamente se aceptan cuando aparecen en una sección
estructurada de recursos, software, herramientas digitales o programa analítico. El programa analítico es
una fuente estructurada válida después de excluir bibliografía, URLs y recursos docentes genéricos; esas
fuentes siguen sin ser herramientas publicables. Esto también impide publicar coincidencias de apellidos o
términos financieros. Cada evidencia incluye sección, texto fuente y coincidencia en
`herramientas_fuente.jsonl`; se reconocen alias explícitos como `MS Excel` → `Microsoft Excel`.

### Contrato evidence-first y esquemas CSV

El flujo curricular es determinista y respeta la evidencia en este orden:

1. registra todas las competencias declaradas por cada sílabo;
2. resuelve el logro contra esas declaraciones dentro del mismo sílabo; si el código es
   ambiguo o no está declarado, conserva el código como referencia de fuente y solo usa la
   descripción para una relación textual revisable;
3. intenta canonicalizar la habilidad contra el catálogo de habilidades, primero por nombre exacto
   y luego con coincidencia lexical fuerte; si no hay evidencia suficiente, no inventa una fila
   pública y la conserva en el reporte de fuente;
4. busca herramientas explícitas solo en secciones curriculares estructuradas y las relaciona con la
   competencia principal de la habilidad, evitando productos cartesianos; y
5. ejecuta un juez determinista que rechaza esquemas inválidos, IDs duplicados, relaciones huérfanas
   y competencias placeholder.

Los cuatro CSV publicados conservan exactamente las columnas de los catálogos existentes; no se
agregan columnas ni archivos CSV alternativos:

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

La evidencia que no puede expresarse en ese contrato se guarda como JSONL de auditoría en
`salidas/reportes/`: `competencias_fuente.jsonl`, `habilidades_fuente.jsonl`,
`herramientas_fuente.jsonl`, `cobertura_curricular_fuente.jsonl` y
`cobertura_curricular_canonica.jsonl`. Las resoluciones incluyen método, puntaje y segundo puntaje para
que coincidencias ambiguas se mantengan en revisión. Esos reportes no alteran los esquemas CSV y permiten
revisar qué declaró cada sílabo sin publicar placeholders.

### Perfil bootstrap por carrera

Después de revisar una ejecución, se puede generar un perfil inicial sin alterar los esquemas CSV:

```bash
PYTHONPATH=src .venv/bin/python scripts/generar_perfil_carrera.py \
  --ejecucion .normalizador/NOR_xxx \
  --catalogos "/ruta/Normalizacion CIAR/catalogos" \
  --carrera Marketing --periodo 2026-1
```

El resultado queda en `catalogos/carreras/MARKETING/2026-1/` con los tres catálogos y cobertura opcional.
`perfil.json` lo identifica explícitamente como `REQUIERE_REVISION_HUMANA`; las habilidades no canónicas
quedan en `reportes/habilidades_pendientes.jsonl`, no en columnas nuevas ni como conceptos inventados. Mientras
un perfil está en bootstrap, especializa el espacio de **competencias**; las habilidades y herramientas aún se
contrastan contra el catálogo global para que un perfil incompleto no elimine candidatos y fuerce falsos positivos.

## Logs

En `INFO` aparecen eventos de negocio: memoria recibida y actualizada, decisiones de ruta,
estrategia, caché, entidades, Cypher, filas e inspección de la respuesta. Cada evento incluye
automáticamente la función que lo originó y usa el formato `[campo]: valor` en una sola línea:

```text
18:40:56.601 [nivel]: INFO [sesion]: ses-eb1636cec94a [evento]: decision.ruta_seleccionada [funcion]: agente.grafo.enrutado.ruta_tras_estrategia [desde]: selecciona_estrategia [hacia]: valida_cypher [motivo]: plantilla determinista
```

`DEBUG` agrega una línea por función finalizada con su duración. Los IDs de sesión se
pseudonimizan y los secretos, saltos de línea y campos excesivos se sanean de forma central.
Se controla desde `.env`:

```dotenv
LOG_FORMATO=legible  # usa json para ingestión por máquinas
LOG_NIVEL=INFO       # usa DEBUG para el perfil técnico por función
LOG_FUNCIONES=true
LOG_MAX_CHARS_CAMPO=800
LOG_SESION_COMPLETA=false
```
