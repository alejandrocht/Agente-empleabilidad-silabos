# Dashboard CIAR: preguntas, métricas y consultas fijas

## Decisión

El producto será un **dashboard general con filtros progresivos y drill-down**, organizado en tres secciones: **Panorama laboral**, **Alineación curricular** y **Empresas y funciones**.

La vista inicial debe explicar el panorama sin configuración. Los filtros refinan el mismo contexto y el clic sobre una entidad abre un detalle acotado. El dashboard no ejecutará preguntas libres ni Cypher generado por un LLM: cada visualización consumirá uno de los 12 datasets fijos definidos en `backend/src/agente/dashboard/`.

## Quick path

1. Abrir el dashboard sin filtros para leer tendencias macro acotadas.
2. Elegir período, facultad, carrera, industria o dimensión cuando el gráfico lo permita.
3. Seleccionar una barra, punto o entidad para solicitar la vista específica de la misma pregunta.
4. Revisar numeradores, denominadores y estado de disponibilidad antes de interpretar el resultado.

> **Regla de producto:** general primero, contexto después, detalle bajo demanda. Ninguna vista general devuelve matrices exhaustivas.

## Qué puede afirmar el dashboard

| El grafo sí permite observar | El grafo no permite afirmar |
| --- | --- |
| Ofertas publicadas y dirigidas a carreras | Empleo efectivo o trayectoria de egresados |
| Industria y tipo de la empresa publicadora | Tamaño de empresa |
| Títulos publicados en `Puesto.nombre` | Funciones ocupacionales normalizadas |
| Competencias, habilidades y herramientas requeridas | Conocimientos de una persona |
| Cobertura curricular declarada por curso | Dominio adquirido, calidad o profundidad formativa |
| Correspondencias entre currículo y publicaciones | Causalidad entre un curso y una contratación |

No existen entidades `Persona`, `Estudiante`, `Egresado`, contrato ni postulación. `Puesto.nombre` se presenta siempre como **título publicado**. La dimensión “conocimiento” reúne `Competencia`, `Habilidad` y `Herramienta`, pero mantiene visible el tipo de cada elemento.

## Filtros progresivos

| Nivel | Filtros | Comportamiento |
| --- | --- | --- |
| Global | Período | La vista general temporal usa los últimos 12 meses relativos a `max(fecha_publicacion)`, no al reloj del navegador. |
| Académico | Facultad → Carrera | Carrera depende de Facultad. Las vistas curriculares exigen una carrera con currículo conectado. |
| Mercado | Industria → Empresa | Industria restringe el contexto de ofertas; Empresa habilita comparaciones A/B. |
| Analítico | Competencia / Habilidad / Herramienta | Cambia la dimensión sin mezclar denominadores. |
| Drill-down | Entidad seleccionada | Ejecuta el Cypher específico con `desde` y `hasta` explícitos cuando la pregunta usa tiempo. |

Los filtros incompatibles con una pregunta no deben enviarse ni simularse en el frontend. El catálogo declara los parámetros exactos de cada vista específica.

**Alcance actual:** este work unit entrega una vista macro sin parámetros y un drill-down
completamente filtrado por pregunta. El runner no acepta combinaciones opcionales intermedias.
Las combinaciones progresivas —por ejemplo, carrera sin industria o facultad con período— serán
variantes tipadas del work unit de API; no se resolverán interpolando filtros ni enviando `null`.

## Las 12 preguntas del dashboard

### 1. Panorama laboral

Esta sección responde qué está ocurriendo en el mercado publicado antes de incorporar el currículo.

| Slug | Pregunta | Definición medible | Gráfico | Filtros específicos | Vista macro | Drill-down |
| --- | --- | --- | --- | --- | --- | --- |
| `tendencia_ofertas` | ¿Cómo cambia mes a mes la cantidad de ofertas publicadas? | Ofertas únicas por mes. | Línea | Carrera, industria, desde, hasta | 12 meses relativos al último dato. | Hasta 20 meses del contexto. |
| `carreras_con_mayor_demanda` | ¿Qué carreras concentran más ofertas dirigidas? | Ofertas únicas y participación por carrera. | Barras ordenadas | Facultad, industria, desde, hasta | Las 14 carreras. | Carreras de la facultad e industria. |
| `industrias_por_carrera` | ¿En qué industrias se concentran las ofertas dirigidas a cada carrera? | Industria líder por carrera; top industrias al seleccionar una. | Barras con drill-down | Carrera, desde, hasta | Una fila por carrera. | Top 10 industrias. |
| `conocimientos_mas_demandados` | ¿Qué competencias, habilidades y herramientas aparecen más en las ofertas del contexto seleccionado? | Proporción de ofertas únicas que requiere cada elemento. | Barras por pestaña | Carrera, industria, dimensión, desde, hasta | Top 5 por dimensión, máximo 15. | Top 20 del contexto. |

### 2. Alineación curricular

Esta sección compara demanda publicada con cobertura declarada. Sus resultados son **señales de revisión**, no juicios automáticos sobre una carrera o curso.

| Slug | Pregunta | Definición medible | Gráfico | Filtros específicos | Vista macro | Drill-down |
| --- | --- | --- | --- | --- | --- | --- |
| `cobertura_curricular` | Para la carrera seleccionada, ¿qué elementos tienen mayor cobertura curricular declarada? | Cursos que cubren el elemento / cursos conectados de la carrera. | Estado + barras | Carrera, dimensión | Disponibilidad y flag independiente para cada dimensión en las 14 carreras. | Top 20 elementos. |
| `brechas_demanda_alta` | ¿En qué elementos la demanda relativa supera más a la cobertura? | Diferencia, sin umbral, entre proporción de ofertas y proporción de cursos. | Cuadrantes o barras agrupadas | Carrera, industria, dimensión, desde, hasta | Top 20 solo entre dimensiones comparables. | Top 20 del contexto. |
| `senales_revision_vigencia` | ¿En cuáles la cobertura supera más a la demanda reciente? | Diferencia, sin umbral, entre proporción de cursos y proporción de ofertas recientes. | Barras divergentes | Carrera, industria, dimensión, desde, hasta | Top 20 solo entre dimensiones comparables. | Top 20 o estado `no_market_data`. |
| `cursos_con_mayor_correspondencia` | ¿Qué cursos comparten más conocimientos con las ofertas del contexto seleccionado? | Ofertas únicas y conocimientos compartidos por curso. | Barras ordenadas | Carrera, industria, dimensión, desde, hasta | Top 20 solo entre carreras comparables. | Top 20 del contexto. |

### 3. Empresas y funciones

Esta sección explica patrones de publicaciones empresariales. No se presenta como información interna de las empresas ni como headhunting de personas.

| Slug | Pregunta | Definición medible | Gráfico | Filtros específicos | Vista macro | Drill-down |
| --- | --- | --- | --- | --- | --- | --- |
| `empresas_y_conocimientos` | ¿Qué empresas concentran las ofertas del contexto y qué conocimientos solicitan? | Ofertas únicas por empresa y conocimiento líder. | Barras con detalle | Carrera, industria, desde, hasta | Top 20 empresas. | Top 20 del contexto. |
| `diferenciadores_empresas` | ¿Qué conocimientos aparecen proporcionalmente más en las ofertas de Empresa A que de Empresa B? | Lift con soporte mínimo en macro; diferencias positivas A−B en detalle. | Barras divergentes | Empresas A/B distintas, desde, hasta | Top 20 lifts con soporte mínimo 5. | Top 20 diferencias positivas; ambas empresas requieren soporte. |
| `conocimientos_liderazgo` | ¿Qué conocimientos aparecen con mayor frecuencia en ofertas cuyos títulos tienen señal textual de liderazgo? | Heurística sobre términos inequívocos del título y conocimiento requerido. | Barras con drill-down | Industria, desde, hasta | Top 20 industrias. | Top 10 conocimientos. |
| `funciones_por_tipo_empresa` | ¿Cómo cambia la distribución de títulos de puesto para una carrera según el tipo de empresa? | Ofertas con título no vacío por tipo y texto normalizado. | Barras agrupadas | Carrera, desde, hasta | Top 4 tipos y top 5 títulos, máximo 20. | La misma población para una carrera. |

## Contrato de datos

Cada entrada del catálogo publica:

- sección, slug, pregunta, definición medible y limitación semántica;
- `cypher_general`, sin referencias `$param`;
- `cypher_especifica` y su conjunto exacto de parámetros;
- granularidad macro y específica;
- métrica principal, límite de filas, `chart_hint` y `requiere_curricula`;
- nombres exactos y separados de salida para general y específica.

Las salidas usan IDs y nombres para navegación. Toda razón expone `numerator_n` y
`denominator_n`; las comparaciones currículo--mercado usan pares con prefijo `demand_` y
`coverage_`. Los shares de recorridos muchos-a-muchos se llaman `assignment_share` y publican
`total_assignments`: no se presentan como participación de ofertas únicas. Toda demanda usa
`count(DISTINCT oferta)` para evitar que varios requerimientos inflen la métrica.

### Límites de cardinalidad

- General: máximo 20 filas.
- Excepciones: `carreras_con_mayor_demanda` y disponibilidad curricular, máximo 14.
- Detalle: top 10 o 20 según el contrato de la pregunta.
- No se devuelven matrices carrera × industria × conocimiento completas.

## Calidad y disponibilidad curricular

La instancia auditada contiene 14 carreras, pero solo **Ingeniería de Sistemas** tiene currículo conectado por `Carrera-ENSENIA-Curso`. Esto es una limitación de disponibilidad, no evidencia de cobertura cero en las otras 13 carreras.

| Estado | Condición | Presentación |
| --- | --- | --- |
| `available` | Existen cursos conectados y un denominador curricular válido. | Habilitar cobertura, brechas, vigencia y cursos. |
| `unavailable` | No existen cursos/coberturas conectados. | Mostrar “Cobertura curricular no disponible en el grafo”. |
| Sin ofertas | El período/contexto no contiene ofertas. | Mostrar “No hay ofertas en el contexto seleccionado”. |
| Soporte bajo | El denominador es insuficiente para una lectura estable. | Mostrar numerador y denominador; no ocultarlos. |
| Dimensión sin resultados | No hay elementos del tipo elegido. | Mostrar estado vacío, nunca convertirlo en 0 %. |

La comparabilidad se evalúa por dimensión: debe haber cursos y coberturas válidas de la
dimensión seleccionada. El macro publica `competencia_comparable`, `habilidad_comparable` y
`herramienta_comparable`; la ausencia de una dimensión nunca bloquea otra. Cursos sin cobertura
de la dimensión elegida producen `incomplete`, métricas nulas e `is_comparable=false`. Sin ofertas, las comparaciones temporales producen
`no_market_data`, no porcentajes cero. El frontend debe respetar ese estado antes de graficar.

En brechas, una dimensión perfilada habilita el universo combinado de elementos demandados y
curriculares. Un elemento demandado sin cobertura puede tener cobertura 0 %; eso es una
medición válida dentro de una dimensión disponible, no un dato faltante. Vigencia usa únicamente
el universo curricular.

Si `Oferta_Laboral` está vacío, la serie P1 devuelve `no_data`. Las demás plantillas temporales
críticas protegen `fecha_corte` nula y devuelven un dataset vacío, que el API deberá traducir al
mismo estado `no_data` sin fabricar períodos o rankings.

## Arquitectura del catálogo

```text
backend/src/agente/dashboard/
├── consultas_modelo.py          # contrato tipado
├── consultas_panorama.py        # P1-P4
├── consultas_alineacion.py      # A1-A4
├── consultas_empresas.py        # E1-E4
└── consultas_estrategicas.py    # registry y re-export compatible

backend/scripts/
└── ejecutar_consultas_estrategicas.py
```

El runner mantiene `--listar`, `--vista general|especifica` y `--mostrar-query`. Ejecuta Neo4j directamente en modo lectura; no usa LangGraph, OpenAI ni APOC.

## Plan de entrega por work units

### WU1 — Contrato de producto y catálogo fijo

**Incluye:** este documento, los cuatro módulos del catálogo, el registry compatible y el runner.

**No incluye:** endpoints, integración del dashboard ni componentes de visualización.

**Verificación:** tipos, lint, guarda de solo lectura, parámetros, `EXPLAIN` y ejecución controlada contra Neo4j.

**Rollback:** eliminar `consultas_modelo.py`, `consultas_panorama.py`, `consultas_alineacion.py` y `consultas_empresas.py`; restaurar este plan, `consultas_estrategicas.py` y el runner. API y frontend permanecen intactos.

### WU2 — API tipada del dashboard

- Exponer únicamente slugs permitidos y filtros tipados.
- Validar IDs, dimensión y rangos temporales.
- Añadir timeout transaccional y presupuesto de filas/costo por plantilla; el runner de este
  work unit no modifica el servicio de base de datos.
- `diferenciadores_empresas` macro no será apto para request síncrono si su medición permanece
  por encima de 5 s: WU2 deberá precalcularlo o servirlo desde caché con invalidación explícita.
- Devolver estados de disponibilidad y soporte sin reinterpretarlos.
- Añadir pruebas de contrato y cardinalidad.

### WU3 — Panorama laboral

- Implementar filtros persistentes y las cuatro visualizaciones de Panorama.
- Incorporar tablas accesibles y estados vacíos.
- Validar macro → drill-down con datos reales.

### WU4 — Alineación curricular

- Añadir el gate de disponibilidad antes de ejecutar comparaciones.
- Implementar cobertura, brechas, vigencia y correspondencia.
- Mostrar numeradores, denominadores y advertencias.

### WU5 — Empresas y funciones

- Implementar selección de empresas A/B.
- Etiquetar liderazgo como aproximación por título.
- Presentar `Puesto.nombre` como título publicado.

### WU6 — Validación funcional

- Revisar preguntas y umbrales con usuarios académicos y de empleabilidad.
- Medir tiempos y soportes reales.
- Ajustar top-N y advertencias sin cambiar la semántica de las métricas.

## Criterios de aceptación de WU1

- [ ] Existen exactamente 12 slugs únicos, cuatro por sección.
- [ ] Cada general contiene cero referencias a parámetros y respeta su límite declarado.
- [ ] Cada específica referencia exactamente los parámetros declarados.
- [ ] Las 24 consultas pasan la guarda de solo lectura y `EXPLAIN` sin APOC.
- [ ] Las 12 generales se ejecutan contra Neo4j sin OOM y dentro de su cardinalidad.
- [ ] Se prueban además P1 general, P3 para Ingeniería de Sistemas y una consulta curricular real.
- [ ] `--listar` y `--mostrar-query` funcionan sin conectarse a Neo4j.
- [ ] `py_compile`, Ruff y mypy strict pasan sobre catálogo y runner.
- [ ] No se modifican endpoints ni frontend en este work unit.

## Referencia operativa

```powershell
cd backend

# Descubrir el catálogo
python scripts/ejecutar_consultas_estrategicas.py --listar

# Ver un Cypher general sin conectarse
python scripts/ejecutar_consultas_estrategicas.py `
  --consulta industrias_por_carrera --vista general --mostrar-query

# Ver un drill-down sin ejecutarlo
python scripts/ejecutar_consultas_estrategicas.py `
  --consulta industrias_por_carrera --vista especifica `
  --param carrera_id=CAR_01375f53651cff38 `
  --param desde=2025-01-01T00:00:00Z `
  --param hasta=2026-01-01T00:00:00Z `
  --mostrar-query
```
