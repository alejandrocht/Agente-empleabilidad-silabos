# Queries de ejemplo para validar el dashboard en Neo4j

Estas son **proyecciones visuales** del catálogo fijo: conservan su lógica de cálculo, pero el `RETURN` final muestra únicamente las columnas que necesita cada gráfico. Los campos técnicos del catálogo (`value`, numeradores, denominadores, soporte, disponibilidad y avisos) se usan dentro de la subconsulta para validar el resultado y no se devuelven en estas pruebas.

## Uso rápido en Neo4j Browser

1. Para una **query general**, copie solo el bloque Cypher: no requiere parámetros.
2. Para una **query específica**, ejecute primero su bloque `:param` y luego el Cypher.
3. Una tabla vacía **no es cero**: esta proyección omite los estados sin datos o sin cobertura (`availability <> 'available'`). Revise la calidad y los avisos en el catálogo o dashboard antes de concluir que no existe demanda o cobertura.

> Los rangos de fechas son semiabiertos: `[desde, hasta)`. Incluyen `desde` y excluyen `hasta`.

## Entidades reales de los ejemplos

| Parámetro | Valor | Entidad |
|---|---|---|
| `carrera_id` | `CAR_01375f53651cff38` | Ingeniería de Sistemas |
| `facultad_id` | `FAC_7ae410ba957c79d1` | Facultad de Ingeniería |
| `industria_id` | `INDU_3b41f23fcb06b8c6` | Actividades de consultoría de gestión |
| `empresa_a_id` | `EMP_a197af00a598b78c` | EVENTIVA S.A.C. |
| `empresa_b_id` | `EMP_47f42efb87384408` | ADECCO CONSULTING S.A. |
| `tipo_conocimiento` | `herramienta` | Dimensión herramienta |

## Límites de interpretación

- El grafo mide ofertas publicadas y relaciones declaradas, no egresados, contrataciones ni empleo efectivo.
- Solo Ingeniería de Sistemas tiene currículo conectado en la instancia validada. Falta de currículo no equivale a 0 % de cobertura.
- `Puesto.nombre` es un título publicado; no es una función normalizada ni existe tamaño empresarial.

## Panorama laboral

### 1. ¿Cómo cambia mes a mes la cantidad de ofertas publicadas?

**Qué busca mostrar.** Serie mensual de ofertas únicas; el macro usa los últimos 12 meses con datos.

**Cómo leer el resultado.** Cada fila es un mes. `ofertas` es el total de publicaciones únicas del período.

**Advertencia semántica.** Mide publicaciones, no contrataciones ni empleo efectivo.

#### Query general

**Columnas visuales:** `periodo`, `ofertas`.
**Alcance:** Un mes por fila, máximo 12 meses.

```cypher
CALL () {
MATCH (oferta:Oferta_Laboral)
WHERE oferta.fecha_publicacion IS NOT NULL
WITH max(oferta.fecha_publicacion) AS fecha_corte
WITH fecha_corte,
     CASE WHEN fecha_corte IS NULL THEN [null] ELSE range(0, 11) END AS meses
UNWIND meses AS desplazamiento
WITH fecha_corte,
     CASE WHEN fecha_corte IS NULL THEN null
          ELSE date({year: fecha_corte.year, month: fecha_corte.month, day: 1})
               - duration('P11M') + duration({months: desplazamiento}) END AS periodo
OPTIONAL MATCH (o:Oferta_Laboral)
WHERE periodo IS NOT NULL
  AND o.fecha_publicacion >= datetime({year: periodo.year, month: periodo.month, day: 1})
  AND o.fecha_publicacion < datetime({year: periodo.year, month: periodo.month, day: 1})
      + duration('P1M')
WITH periodo, count(DISTINCT o) AS ofertas
RETURN toString(periodo) AS periodo_id,
       toString(periodo) AS periodo,
       ofertas AS value,
       ofertas AS ofertas,
       ofertas AS numerator_n,
       null AS denominator_n,
       CASE WHEN ofertas = 0 THEN 'no_data' ELSE 'available' END AS availability
ORDER BY periodo
LIMIT 12
}
WITH *
WHERE availability = 'available'
RETURN periodo,
       ofertas
ORDER BY periodo
```

#### Query específica

**Parámetros de ejemplo verificados:**

```cypher
:param {
  carrera_id: "CAR_01375f53651cff38",
  industria_id: "INDU_3b41f23fcb06b8c6",
  desde: "2025-01-01T00:00:00Z",
  hasta: "2026-01-01T00:00:00Z"
}
```

**Columnas visuales:** `periodo`, `ofertas`.
**Alcance:** Un mes por fila para carrera, industria y período.

```cypher
CALL () {
WITH date(datetime($desde)) AS desde,
     date(datetime($hasta)) AS hasta
WITH desde, hasta,
     date({year: hasta.year, month: hasta.month, day: 1}) AS mes_hasta
WITH desde,
     CASE WHEN hasta = mes_hasta THEN mes_hasta - duration('P1M')
          ELSE mes_hasta END AS ultimo_mes
UNWIND range(0, 19) AS desplazamiento
WITH desde, ultimo_mes - duration({months: desplazamiento}) AS periodo
WHERE periodo + duration('P1M') > desde
OPTIONAL MATCH (ca:Carrera)-[:DIRIGE_A]-(o:Oferta_Laboral)
      -[:PUBLICA]-(:Empresa)-[:AGRUPA]-(i:Industria)
WHERE ca.id_carrera = $carrera_id
  AND i.id_industria = $industria_id
  AND o.fecha_publicacion >= datetime($desde)
  AND o.fecha_publicacion < datetime($hasta)
  AND o.fecha_publicacion >= datetime({year: periodo.year, month: periodo.month, day: 1})
  AND o.fecha_publicacion < datetime({year: periodo.year, month: periodo.month, day: 1})
      + duration('P1M')
WITH periodo, count(DISTINCT o) AS ofertas
RETURN $carrera_id AS carrera_id,
       $industria_id AS industria_id,
       toString(periodo) AS periodo_id,
       toString(periodo) AS periodo,
       ofertas AS value,
       ofertas AS ofertas,
       ofertas AS numerator_n,
       null AS denominator_n,
       CASE WHEN ofertas = 0 THEN 'no_data' ELSE 'available' END AS availability
ORDER BY periodo
LIMIT 20
}
WITH *
WHERE availability = 'available'
RETURN periodo,
       ofertas
ORDER BY periodo
```

**Gráfico sugerido:** `line`. Límite: general 12 filas; específica 20 filas.


### 2. ¿Qué carreras concentran más ofertas dirigidas?

**Qué busca mostrar.** Ranking por ofertas únicas dirigidas y participación del total.

**Cómo leer el resultado.** `participacion` es el peso de la carrera sobre las asignaciones carrera-oferta del contexto; no representa personas ni contrataciones.

**Advertencia semántica.** Una oferta dirigida expresa demanda declarada; no prueba inserción laboral.

#### Query general

**Columnas visuales:** `carrera_id`, `carrera`, `ofertas`, `participacion`, `rank`.
**Alcance:** Una carrera por fila, máximo las 14 carreras.

```cypher
CALL () {
MATCH (oferta:Oferta_Laboral)
WHERE oferta.fecha_publicacion IS NOT NULL
WITH max(oferta.fecha_publicacion) AS fecha_corte
WHERE fecha_corte IS NOT NULL
WITH fecha_corte,
     datetime({year: fecha_corte.year, month: fecha_corte.month, day: 1})
       - duration('P11M') AS fecha_inicio
MATCH (ca:Carrera)-[:DIRIGE_A]-(o:Oferta_Laboral)
WHERE o.fecha_publicacion >= fecha_inicio
  AND o.fecha_publicacion <= fecha_corte
WITH ca, count(DISTINCT o) AS ofertas
ORDER BY ofertas DESC, ca.nombre_carrera
WITH collect({carrera_id: ca.id_carrera, carrera: ca.nombre_carrera,
              ofertas: ofertas}) AS filas,
     sum(ofertas) AS total_asignaciones
UNWIND range(0, size(filas) - 1) AS indice
WITH filas[indice] AS fila, total_asignaciones, indice
RETURN fila.carrera_id AS carrera_id,
       fila.carrera AS carrera,
       fila.ofertas AS value,
       fila.ofertas AS ofertas,
       toFloat(fila.ofertas) / total_asignaciones AS assignment_share,
       indice + 1 AS rank,
       fila.ofertas AS numerator_n,
       total_asignaciones AS denominator_n,
       total_asignaciones AS total_assignments,
       'available' AS availability
ORDER BY rank
LIMIT 14
}
WITH *
WHERE availability = 'available'
RETURN carrera_id,
       carrera,
       ofertas,
       assignment_share AS participacion,
       rank
ORDER BY rank
```

#### Query específica

**Parámetros de ejemplo verificados:**

```cypher
:param {
  facultad_id: "FAC_7ae410ba957c79d1",
  industria_id: "INDU_3b41f23fcb06b8c6",
  desde: "2025-01-01T00:00:00Z",
  hasta: "2026-01-01T00:00:00Z"
}
```

**Columnas visuales:** `carrera_id`, `carrera`, `ofertas`, `participacion`, `rank`.
**Alcance:** Carreras de una facultad e industria en el período.

```cypher
CALL () {
MATCH (f:Facultad)-[:OFRECE]-(ca:Carrera)-[:DIRIGE_A]-(o:Oferta_Laboral)
      -[:PUBLICA]-(:Empresa)-[:AGRUPA]-(i:Industria)
WHERE f.id_facultad = $facultad_id
  AND i.id_industria = $industria_id
  AND o.fecha_publicacion >= datetime($desde)
  AND o.fecha_publicacion < datetime($hasta)
WITH f, ca, i, count(DISTINCT o) AS ofertas
ORDER BY ofertas DESC, ca.nombre_carrera
WITH f, i,
     collect({carrera_id: ca.id_carrera, carrera: ca.nombre_carrera,
              ofertas: ofertas}) AS filas,
     sum(ofertas) AS total_asignaciones
UNWIND range(0, size(filas) - 1) AS indice
WITH f, i, filas[indice] AS fila, total_asignaciones, indice
RETURN f.id_facultad AS facultad_id,
       f.nombre_facultad AS facultad,
       i.id_industria AS industria_id,
       i.nombre AS industria,
       fila.carrera_id AS carrera_id,
       fila.carrera AS carrera,
       fila.ofertas AS value,
       fila.ofertas AS ofertas,
       toFloat(fila.ofertas) / total_asignaciones AS assignment_share,
       indice + 1 AS rank,
       fila.ofertas AS numerator_n,
       total_asignaciones AS denominator_n,
       total_asignaciones AS total_assignments,
       'available' AS availability
ORDER BY rank
LIMIT 14
}
WITH *
WHERE availability = 'available'
RETURN carrera_id,
       carrera,
       ofertas,
       assignment_share AS participacion,
       rank
ORDER BY rank
```

**Gráfico sugerido:** `ranked_bar`. Límite: general 14 filas; específica 14 filas.


### 3. ¿En qué industrias se concentran las ofertas dirigidas a cada carrera?

**Qué busca mostrar.** Industria líder por carrera en macro y top 10 de industrias en detalle.

**Cómo leer el resultado.** `participacion` es el peso de cada industria dentro de las ofertas dirigidas a la carrera. La macro conserva la industria líder por carrera.

**Advertencia semántica.** Describe industrias de empresas publicadoras, no industrias donde trabajan egresados.

#### Query general

**Columnas visuales:** `carrera_id`, `carrera`, `industria_id`, `industria`, `ofertas`, `participacion`, `rank`.
**Alcance:** Una industria líder por carrera, máximo 14 filas.

```cypher
CALL () {
MATCH (oferta:Oferta_Laboral)
WHERE oferta.fecha_publicacion IS NOT NULL
WITH max(oferta.fecha_publicacion) AS fecha_corte
WHERE fecha_corte IS NOT NULL
WITH fecha_corte,
     datetime({year: fecha_corte.year, month: fecha_corte.month, day: 1})
       - duration('P11M') AS fecha_inicio
MATCH (ca:Carrera)-[:DIRIGE_A]-(o:Oferta_Laboral)
      -[:PUBLICA]-(e:Empresa)-[:AGRUPA]-(i:Industria)
WHERE o.fecha_publicacion >= fecha_inicio
  AND o.fecha_publicacion <= fecha_corte
WITH ca, i, count(DISTINCT o) AS ofertas, count(DISTINCT e) AS empresas
ORDER BY ca.id_carrera, ofertas DESC, i.nombre
WITH ca, collect({industria_id: i.id_industria, industria: i.nombre,
                  ofertas: ofertas, empresas: empresas}) AS industrias,
     sum(ofertas) AS total_asignaciones
WITH ca, industrias[0] AS lider, size(industrias) AS industrias_activas,
     total_asignaciones
ORDER BY total_asignaciones DESC, ca.nombre_carrera
WITH collect({carrera_id: ca.id_carrera, carrera: ca.nombre_carrera,
              lider: lider, industrias_activas: industrias_activas,
              total: total_asignaciones}) AS filas
UNWIND range(0, size(filas) - 1) AS indice
WITH filas[indice] AS fila, indice
RETURN fila.carrera_id AS carrera_id,
       fila.carrera AS carrera,
       fila.lider.industria_id AS industria_id,
       fila.lider.industria AS industria,
       fila.lider.ofertas AS value,
       fila.lider.ofertas AS ofertas,
       fila.lider.empresas AS empresas,
       toFloat(fila.lider.ofertas) / fila.total AS assignment_share,
       indice + 1 AS rank,
       fila.lider.ofertas AS numerator_n,
       fila.total AS denominator_n,
       fila.total AS total_assignments,
       'available' AS availability,
       fila.industrias_activas AS industrias_activas
ORDER BY rank
LIMIT 14
}
WITH *
WHERE availability = 'available'
RETURN carrera_id,
       carrera,
       industria_id,
       industria,
       ofertas,
       assignment_share AS participacion,
       rank
ORDER BY rank
```

#### Query específica

**Parámetros de ejemplo verificados:**

```cypher
:param {
  carrera_id: "CAR_01375f53651cff38",
  desde: "2025-01-01T00:00:00Z",
  hasta: "2026-01-01T00:00:00Z"
}
```

**Columnas visuales:** `industria_id`, `industria`, `ofertas`, `participacion`, `rank`.
**Alcance:** Top 10 industrias de una carrera.

```cypher
CALL () {
MATCH (ca:Carrera)-[:DIRIGE_A]-(o:Oferta_Laboral)
      -[:PUBLICA]-(e:Empresa)-[:AGRUPA]-(i:Industria)
WHERE ca.id_carrera = $carrera_id
  AND o.fecha_publicacion >= datetime($desde)
  AND o.fecha_publicacion < datetime($hasta)
WITH ca, i, count(DISTINCT o) AS ofertas, count(DISTINCT e) AS empresas
ORDER BY ofertas DESC, i.nombre
WITH ca,
     collect({industria_id: i.id_industria, industria: i.nombre,
              ofertas: ofertas, empresas: empresas}) AS filas,
     sum(ofertas) AS total_asignaciones
UNWIND range(0, size(filas[0..10]) - 1) AS indice
WITH ca, filas[indice] AS fila, total_asignaciones, indice
RETURN ca.id_carrera AS carrera_id,
       ca.nombre_carrera AS carrera,
       fila.industria_id AS industria_id,
       fila.industria AS industria,
       fila.ofertas AS value,
       fila.ofertas AS ofertas,
       fila.empresas AS empresas,
       toFloat(fila.ofertas) / total_asignaciones AS assignment_share,
       indice + 1 AS rank,
       fila.ofertas AS numerator_n,
       total_asignaciones AS denominator_n,
       total_asignaciones AS total_assignments,
       'available' AS availability
ORDER BY rank
}
WITH *
WHERE availability = 'available'
RETURN industria_id,
       industria,
       ofertas,
       assignment_share AS participacion,
       rank
ORDER BY rank
```

**Gráfico sugerido:** `bar_drilldown`. Límite: general 14 filas; específica 10 filas.


### 4. ¿Qué competencias, habilidades y herramientas aparecen más en las ofertas del contexto seleccionado?

**Qué busca mostrar.** Top 5 por dimensión en macro y top 20 de la dimensión seleccionada en detalle.

**Cómo leer el resultado.** `porcentaje` indica la proporción de ofertas que exige el conocimiento. Los porcentajes no suman 100 %, porque una oferta puede requerir varios conocimientos.

**Advertencia semántica.** La frecuencia en publicaciones no equivale a dominio personal ni importancia causal.

#### Query general

**Columnas visuales:** `conocimiento_id`, `conocimiento`, `dimension`, `ofertas`, `porcentaje`, `rank`.
**Alcance:** Top 5 por dimensión, máximo 15 filas.

```cypher
CALL () {
MATCH (oferta:Oferta_Laboral)
WHERE oferta.fecha_publicacion IS NOT NULL
WITH max(oferta.fecha_publicacion) AS fecha_corte
WHERE fecha_corte IS NOT NULL
WITH fecha_corte,
     datetime({year: fecha_corte.year, month: fecha_corte.month, day: 1})
       - duration('P11M') AS fecha_inicio
MATCH (total:Oferta_Laboral)
WHERE total.fecha_publicacion >= fecha_inicio
  AND total.fecha_publicacion <= fecha_corte
WITH fecha_inicio, fecha_corte, count(DISTINCT total) AS total_ofertas
MATCH (o:Oferta_Laboral)-[:TIENE]-(:Requerimiento_Laboral)-[:REQUIERE]-(x)
WHERE o.fecha_publicacion >= fecha_inicio
  AND o.fecha_publicacion <= fecha_corte
  AND (x:Competencia OR x:Habilidad OR x:Herramienta)
WITH x, total_ofertas, count(DISTINCT o) AS ofertas,
     CASE WHEN x:Competencia THEN 'competencia'
          WHEN x:Habilidad THEN 'habilidad' ELSE 'herramienta' END AS dimension
ORDER BY dimension, ofertas DESC,
         coalesce(x.nombre_competencia, x.nombre_habilidad, x.nombre_herramienta)
WITH dimension, total_ofertas,
     collect({id: coalesce(x.id_competencia, x.id_habilidad, x.id_herramienta),
              nombre: coalesce(x.nombre_competencia, x.nombre_habilidad,
                               x.nombre_herramienta),
              ofertas: ofertas})[0..5] AS filas
UNWIND range(0, size(filas) - 1) AS indice
WITH dimension, filas[indice] AS fila, total_ofertas, indice
RETURN fila.id AS conocimiento_id,
       fila.nombre AS conocimiento,
       dimension,
       fila.ofertas AS value,
       fila.ofertas AS ofertas,
       toFloat(fila.ofertas) / total_ofertas AS percentage,
       indice + 1 AS rank,
       fila.ofertas AS numerator_n,
       total_ofertas AS denominator_n,
       'available' AS availability
ORDER BY dimension, rank
LIMIT 15
}
WITH *
WHERE availability = 'available'
RETURN conocimiento_id,
       conocimiento,
       dimension,
       ofertas,
       percentage AS porcentaje,
       rank
ORDER BY dimension, rank
```

#### Query específica

**Parámetros de ejemplo verificados:**

```cypher
:param {
  carrera_id: "CAR_01375f53651cff38",
  industria_id: "INDU_3b41f23fcb06b8c6",
  tipo_conocimiento: "herramienta",
  desde: "2025-01-01T00:00:00Z",
  hasta: "2026-01-01T00:00:00Z"
}
```

**Columnas visuales:** `conocimiento_id`, `conocimiento`, `dimension`, `ofertas`, `porcentaje`, `rank`.
**Alcance:** Top 20 de una dimensión y contexto seleccionados.

```cypher
CALL () {
MATCH (ca:Carrera)-[:DIRIGE_A]-(total:Oferta_Laboral)
      -[:PUBLICA]-(:Empresa)-[:AGRUPA]-(i:Industria)
WHERE ca.id_carrera = $carrera_id
  AND i.id_industria = $industria_id
  AND total.fecha_publicacion >= datetime($desde)
  AND total.fecha_publicacion < datetime($hasta)
WITH ca, i, count(DISTINCT total) AS total_ofertas
MATCH (ca)-[:DIRIGE_A]-(o:Oferta_Laboral)
      -[:PUBLICA]-(:Empresa)-[:AGRUPA]-(i)
MATCH (o)-[:TIENE]-(:Requerimiento_Laboral)-[:REQUIERE]-(x)
WHERE o.fecha_publicacion >= datetime($desde)
  AND o.fecha_publicacion < datetime($hasta)
  AND (($tipo_conocimiento = 'competencia' AND x:Competencia)
    OR ($tipo_conocimiento = 'habilidad' AND x:Habilidad)
    OR ($tipo_conocimiento = 'herramienta' AND x:Herramienta))
WITH ca, i, x, total_ofertas, count(DISTINCT o) AS ofertas
ORDER BY ofertas DESC,
         coalesce(x.nombre_competencia, x.nombre_habilidad, x.nombre_herramienta)
WITH ca, i, total_ofertas,
     collect({id: coalesce(x.id_competencia, x.id_habilidad, x.id_herramienta),
              nombre: coalesce(x.nombre_competencia, x.nombre_habilidad,
                               x.nombre_herramienta),
              ofertas: ofertas})[0..20] AS filas
UNWIND range(0, size(filas) - 1) AS indice
WITH ca, i, filas[indice] AS fila, total_ofertas, indice
RETURN ca.id_carrera AS carrera_id,
       ca.nombre_carrera AS carrera,
       i.id_industria AS industria_id,
       i.nombre AS industria,
       fila.id AS conocimiento_id,
       fila.nombre AS conocimiento,
       $tipo_conocimiento AS dimension,
       fila.ofertas AS value,
       fila.ofertas AS ofertas,
       toFloat(fila.ofertas) / total_ofertas AS percentage,
       indice + 1 AS rank,
       fila.ofertas AS numerator_n,
       total_ofertas AS denominator_n,
       'available' AS availability
ORDER BY rank
}
WITH *
WHERE availability = 'available'
RETURN conocimiento_id,
       conocimiento,
       dimension,
       ofertas,
       percentage AS porcentaje,
       rank
ORDER BY rank
```

**Gráfico sugerido:** `ranked_bar_tabs`. Límite: general 15 filas; específica 20 filas.


## Alineación curricular

### 5. Para la carrera seleccionada, ¿qué elementos tienen mayor cobertura curricular declarada?

**Qué busca mostrar.** Disponibilidad por carrera en macro y top 20 por proporción de cursos en detalle.

**Cómo leer el resultado.** La macro muestra cursos con cobertura declarada por dimensión. En detalle, `porcentaje_cobertura` es la proporción de cursos de la carrera que cubre el conocimiento.

**Advertencia semántica.** Cobertura declarada no mide profundidad, calidad ni dominio del estudiante.

#### Query general

**Columnas visuales:** `carrera_id`, `carrera`, `cursos`, `cursos_con_competencias`, `cursos_con_habilidades`, `cursos_con_herramientas`.
**Alcance:** Estado de disponibilidad de las 14 carreras.

```cypher
CALL () {
MATCH (ca:Carrera)
OPTIONAL MATCH (ca)-[:ENSENIA]-(cu:Curso)
WITH ca, count(DISTINCT cu) AS total_cursos
OPTIONAL MATCH (ca)-[:ENSENIA]-(:Curso)-[:TIENE]-(cc:Cobertura_Curricular)
               -[rel:CUBRE|ENSENIA]-(x)
WHERE (x:Competencia AND type(rel) = 'CUBRE')
   OR ((x:Habilidad OR x:Herramienta) AND type(rel) = 'ENSENIA')
WITH ca, total_cursos,
     count(DISTINCT CASE WHEN x:Competencia THEN cc END) AS coberturas_competencia,
     count(DISTINCT CASE WHEN x:Habilidad THEN cc END) AS coberturas_habilidad,
     count(DISTINCT CASE WHEN x:Herramienta THEN cc END) AS coberturas_herramienta
WITH ca, total_cursos, coberturas_competencia, coberturas_habilidad,
     coberturas_herramienta,
     CASE WHEN total_cursos = 0 THEN 'unavailable'
          WHEN coberturas_competencia = 0 OR coberturas_habilidad = 0
            OR coberturas_herramienta = 0 THEN 'incomplete'
          ELSE 'available' END AS availability
RETURN ca.id_carrera AS carrera_id,
       ca.nombre_carrera AS carrera,
       CASE WHEN availability = 'available' THEN total_cursos ELSE null END AS value,
       total_cursos AS numerator_n,
       null AS denominator_n,
       coberturas_competencia,
       coberturas_habilidad,
       coberturas_herramienta,
       coberturas_competencia > 0 AS competencia_comparable,
       coberturas_habilidad > 0 AS habilidad_comparable,
       coberturas_herramienta > 0 AS herramienta_comparable,
       availability,
       coberturas_competencia > 0 OR coberturas_habilidad > 0
         OR coberturas_herramienta > 0 AS has_any_comparable_dimension,
       CASE WHEN availability = 'unavailable'
            THEN 'Cobertura curricular no disponible en el grafo.'
            WHEN availability = 'incomplete'
            THEN 'La carrera no tiene cobertura válida en las tres dimensiones.'
            ELSE null END AS warning
ORDER BY has_any_comparable_dimension DESC, total_cursos DESC, carrera
LIMIT 14
}
WITH *
WHERE availability = 'available'
RETURN carrera_id,
       carrera,
       value AS cursos,
       coberturas_competencia AS cursos_con_competencias,
       coberturas_habilidad AS cursos_con_habilidades,
       coberturas_herramienta AS cursos_con_herramientas
ORDER BY carrera
```

#### Query específica

**Parámetros de ejemplo verificados:**

```cypher
:param {
  carrera_id: "CAR_01375f53651cff38",
  tipo_conocimiento: "herramienta"
}
```

**Columnas visuales:** `conocimiento_id`, `conocimiento`, `dimension`, `cursos`, `porcentaje_cobertura`, `rank`.
**Alcance:** Top 20 elementos cubiertos por una carrera.

```cypher
CALL () {
MATCH (ca:Carrera)
WHERE ca.id_carrera = $carrera_id
OPTIONAL MATCH (ca)-[:ENSENIA]-(curso_total:Curso)
WITH ca, collect(DISTINCT curso_total) AS cursos
OPTIONAL MATCH (ca)-[:ENSENIA]-(:Curso)-[:TIENE]-(cc:Cobertura_Curricular)
               -[rel:CUBRE|ENSENIA]-(x)
WHERE ($tipo_conocimiento = 'competencia' AND x:Competencia AND type(rel) = 'CUBRE')
   OR ($tipo_conocimiento = 'habilidad' AND x:Habilidad AND type(rel) = 'ENSENIA')
   OR ($tipo_conocimiento = 'herramienta' AND x:Herramienta AND type(rel) = 'ENSENIA')
WITH ca, cursos, collect(DISTINCT x) AS elementos,
     count(DISTINCT cc) AS coberturas_dimension
WITH ca, cursos, elementos, coberturas_dimension,
     CASE WHEN size(cursos) = 0 THEN 'unavailable'
          WHEN coberturas_dimension = 0 OR size(elementos) = 0 THEN 'incomplete'
          ELSE 'available' END AS availability
UNWIND CASE WHEN availability = 'available' THEN elementos ELSE [null] END AS x
OPTIONAL MATCH (ca)-[:ENSENIA]-(cu:Curso)-[:TIENE]
               -(:Cobertura_Curricular)-[rel:CUBRE|ENSENIA]-(x)
WHERE ($tipo_conocimiento = 'competencia' AND x:Competencia AND type(rel) = 'CUBRE')
   OR ($tipo_conocimiento = 'habilidad' AND x:Habilidad AND type(rel) = 'ENSENIA')
   OR ($tipo_conocimiento = 'herramienta' AND x:Herramienta AND type(rel) = 'ENSENIA')
WITH ca, cursos, coberturas_dimension, availability, x,
     count(DISTINCT cu) AS cursos_con_cobertura
ORDER BY cursos_con_cobertura DESC,
         coalesce(x.nombre_competencia, x.nombre_habilidad, x.nombre_herramienta)
WITH ca, cursos, coberturas_dimension, availability,
     collect({id: coalesce(x.id_competencia, x.id_habilidad, x.id_herramienta),
              nombre: coalesce(x.nombre_competencia, x.nombre_habilidad,
                               x.nombre_herramienta),
              cursos: cursos_con_cobertura})[0..20] AS filas
UNWIND range(0, size(filas) - 1) AS indice
WITH ca, cursos, coberturas_dimension, availability, filas[indice] AS fila, indice
RETURN ca.id_carrera AS carrera_id,
       ca.nombre_carrera AS carrera,
       fila.id AS conocimiento_id,
       fila.nombre AS conocimiento,
       $tipo_conocimiento AS dimension,
       CASE WHEN availability = 'available' THEN fila.cursos ELSE null END AS value,
       CASE WHEN availability = 'available' THEN toFloat(fila.cursos) / size(cursos)
            ELSE null END AS percentage,
       CASE WHEN availability = 'available' THEN indice + 1 ELSE null END AS rank,
       CASE WHEN availability = 'available' THEN fila.cursos ELSE null END AS numerator_n,
       CASE WHEN availability = 'available' THEN size(cursos) ELSE null END AS denominator_n,
       coberturas_dimension AS dimension_coverage_n,
       availability,
       availability = 'available' AS is_comparable,
       CASE WHEN availability = 'unavailable'
            THEN 'Cobertura curricular no disponible en el grafo.'
            WHEN availability = 'incomplete'
            THEN 'No hay cobertura válida para la dimensión seleccionada.'
            ELSE null END AS warning
ORDER BY rank
LIMIT 20
}
WITH *
WHERE availability = 'available'
RETURN conocimiento_id,
       conocimiento,
       dimension,
       value AS cursos,
       percentage AS porcentaje_cobertura,
       rank
ORDER BY rank
```

**Gráfico sugerido:** `coverage_status_then_bar`. Límite: general 14 filas; específica 20 filas.


### 6. ¿En qué elementos la demanda relativa supera más a la cobertura?

**Qué busca mostrar.** Ranking por diferencia entre proporción de ofertas y proporción de cursos.

**Cómo leer el resultado.** `brecha_porcentual` es demanda menos cobertura. Un valor positivo señala que la presencia en ofertas supera la cobertura curricular declarada.

**Advertencia semántica.** Es una señal de revisión sin umbral; dimensiones incompletas quedan excluidas.

#### Query general

**Columnas visuales:** `carrera_id`, `carrera`, `conocimiento_id`, `conocimiento`, `dimension`, `demanda_porcentaje`, `cobertura_porcentaje`, `brecha_porcentual`, `rank`.
**Alcance:** Top 20 diferencias entre contextos comparables.

```cypher
CALL () {
MATCH (todas:Carrera)
WITH count(DISTINCT todas) AS total_carreras
MATCH (oferta:Oferta_Laboral)
WHERE oferta.fecha_publicacion IS NOT NULL
WITH total_carreras, max(oferta.fecha_publicacion) AS fecha_corte
WHERE fecha_corte IS NOT NULL
WITH total_carreras, fecha_corte,
     datetime({year: fecha_corte.year, month: fecha_corte.month, day: 1})
       - duration('P11M') AS fecha_inicio
MATCH (ca:Carrera)-[:ENSENIA]-(cu:Curso)
WITH total_carreras, fecha_inicio, fecha_corte, ca,
     count(DISTINCT cu) AS total_cursos
MATCH (ca)-[:DIRIGE_A]-(o_total:Oferta_Laboral)
WHERE o_total.fecha_publicacion >= fecha_inicio
  AND o_total.fecha_publicacion <= fecha_corte
WITH total_carreras, fecha_inicio, fecha_corte, ca, total_cursos,
     count(DISTINCT o_total) AS total_ofertas
MATCH (x)
WHERE (x:Competencia OR x:Habilidad OR x:Herramienta)
  AND (
    (x:Competencia AND EXISTS {
      MATCH (ca)-[:ENSENIA]-(:Curso)-[:TIENE]
            -(:Cobertura_Curricular)-[:CUBRE]-(:Competencia)
    })
    OR (x:Habilidad AND EXISTS {
      MATCH (ca)-[:ENSENIA]-(:Curso)-[:TIENE]
            -(:Cobertura_Curricular)-[:ENSENIA]-(:Habilidad)
    })
    OR (x:Herramienta AND EXISTS {
      MATCH (ca)-[:ENSENIA]-(:Curso)-[:TIENE]
            -(:Cobertura_Curricular)-[:ENSENIA]-(:Herramienta)
    })
  )
  AND (
    EXISTS {
      MATCH (ca)-[:ENSENIA]-(:Curso)-[:TIENE]
            -(:Cobertura_Curricular)-[rel:CUBRE|ENSENIA]-(x)
      WHERE (x:Competencia AND type(rel) = 'CUBRE')
         OR ((x:Habilidad OR x:Herramienta) AND type(rel) = 'ENSENIA')
    }
    OR EXISTS {
      MATCH (ca)-[:DIRIGE_A]-(o_demanda:Oferta_Laboral)-[:TIENE]
            -(:Requerimiento_Laboral)-[:REQUIERE]-(x)
      WHERE o_demanda.fecha_publicacion >= fecha_inicio
        AND o_demanda.fecha_publicacion <= fecha_corte
    }
  )
OPTIONAL MATCH (ca)-[:DIRIGE_A]-(o_demanda:Oferta_Laboral)-[:TIENE]
               -(:Requerimiento_Laboral)-[:REQUIERE]-(x)
WHERE o_demanda.fecha_publicacion >= fecha_inicio
  AND o_demanda.fecha_publicacion <= fecha_corte
WITH total_carreras, ca, total_cursos, total_ofertas, x,
     count(DISTINCT o_demanda) AS ofertas_demanda
OPTIONAL MATCH (ca)-[:ENSENIA]-(cu_cobertura:Curso)-[:TIENE]
               -(:Cobertura_Curricular)-[rel:CUBRE|ENSENIA]-(x)
WHERE (x:Competencia AND type(rel) = 'CUBRE')
   OR ((x:Habilidad OR x:Herramienta) AND type(rel) = 'ENSENIA')
WITH total_carreras, ca, total_cursos, total_ofertas, x, ofertas_demanda,
     count(DISTINCT cu_cobertura) AS cursos_cobertura
WITH *, toFloat(ofertas_demanda) / total_ofertas AS demanda,
        toFloat(cursos_cobertura) / total_cursos AS cobertura
ORDER BY demanda - cobertura DESC, ofertas_demanda DESC
WITH collect({carrera_id: ca.id_carrera, carrera: ca.nombre_carrera,
              id: coalesce(x.id_competencia, x.id_habilidad, x.id_herramienta),
              nombre: coalesce(x.nombre_competencia, x.nombre_habilidad,
                               x.nombre_herramienta),
              dimension: CASE WHEN x:Competencia THEN 'competencia'
                              WHEN x:Habilidad THEN 'habilidad' ELSE 'herramienta' END,
              ofertas: ofertas_demanda, total_ofertas: total_ofertas,
              cursos: cursos_cobertura, total_cursos: total_cursos,
              demanda: demanda, cobertura: cobertura,
              brecha: demanda - cobertura})[0..20] AS filas,
     total_carreras
UNWIND range(0, size(filas) - 1) AS indice
WITH filas[indice] AS fila, indice, total_carreras
RETURN fila.carrera_id AS carrera_id,
       fila.carrera AS carrera,
       fila.id AS conocimiento_id,
       fila.nombre AS conocimiento,
       fila.dimension AS dimension,
       fila.brecha AS value,
       fila.demanda AS demand_percentage,
       fila.cobertura AS coverage_percentage,
       fila.ofertas AS demand_numerator_n,
       fila.total_ofertas AS demand_denominator_n,
       fila.cursos AS coverage_numerator_n,
       fila.total_cursos AS coverage_denominator_n,
       indice + 1 AS rank,
       'available' AS availability,
       true AS is_comparable,
       total_carreras
ORDER BY rank
}
WITH *
WHERE availability = 'available'
RETURN carrera_id,
       carrera,
       conocimiento_id,
       conocimiento,
       dimension,
       demand_percentage AS demanda_porcentaje,
       coverage_percentage AS cobertura_porcentaje,
       value AS brecha_porcentual,
       rank
ORDER BY rank
```

#### Query específica

**Parámetros de ejemplo verificados:**

```cypher
:param {
  carrera_id: "CAR_01375f53651cff38",
  industria_id: "INDU_3b41f23fcb06b8c6",
  tipo_conocimiento: "herramienta",
  desde: "2025-01-01T00:00:00Z",
  hasta: "2026-01-01T00:00:00Z"
}
```

**Columnas visuales:** `conocimiento_id`, `conocimiento`, `dimension`, `demanda_porcentaje`, `cobertura_porcentaje`, `brecha_porcentual`, `rank`.
**Alcance:** Top 20 diferencias para carrera, industria y dimensión.

```cypher
CALL () {
MATCH (ca:Carrera)
WHERE ca.id_carrera = $carrera_id
MATCH (i:Industria)
WHERE i.id_industria = $industria_id
OPTIONAL MATCH (ca)-[:ENSENIA]-(curso_total:Curso)
WITH ca, i, count(DISTINCT curso_total) AS total_cursos
OPTIONAL MATCH (ca)-[:ENSENIA]-(:Curso)-[:TIENE]-(cc:Cobertura_Curricular)
               -[rel:CUBRE|ENSENIA]-(elemento_dimension)
WHERE ($tipo_conocimiento = 'competencia' AND elemento_dimension:Competencia
       AND type(rel) = 'CUBRE')
   OR ($tipo_conocimiento = 'habilidad' AND elemento_dimension:Habilidad
       AND type(rel) = 'ENSENIA')
   OR ($tipo_conocimiento = 'herramienta' AND elemento_dimension:Herramienta
       AND type(rel) = 'ENSENIA')
WITH ca, i, total_cursos, count(DISTINCT cc) AS coberturas_dimension
OPTIONAL MATCH (ca)-[:DIRIGE_A]-(oferta_total:Oferta_Laboral)
               -[:PUBLICA]-(:Empresa)-[:AGRUPA]-(i)
WHERE oferta_total.fecha_publicacion >= datetime($desde)
  AND oferta_total.fecha_publicacion < datetime($hasta)
WITH ca, i, total_cursos, coberturas_dimension,
     count(DISTINCT oferta_total) AS total_ofertas
WITH ca, i, total_cursos, coberturas_dimension, total_ofertas,
     CASE WHEN total_cursos = 0 THEN 'unavailable'
          WHEN coberturas_dimension = 0 THEN 'incomplete'
          WHEN total_ofertas = 0 THEN 'no_market_data'
          ELSE 'available' END AS availability
OPTIONAL MATCH (x)
WHERE availability = 'available'
  AND (($tipo_conocimiento = 'competencia' AND x:Competencia)
    OR ($tipo_conocimiento = 'habilidad' AND x:Habilidad)
    OR ($tipo_conocimiento = 'herramienta' AND x:Herramienta))
  AND (
    EXISTS {
      MATCH (ca)-[:ENSENIA]-(:Curso)-[:TIENE]
            -(:Cobertura_Curricular)-[rel:CUBRE|ENSENIA]-(x)
      WHERE (x:Competencia AND type(rel) = 'CUBRE')
         OR ((x:Habilidad OR x:Herramienta) AND type(rel) = 'ENSENIA')
    }
    OR EXISTS {
      MATCH (x)-[:REQUIERE]-(:Requerimiento_Laboral)-[:TIENE]
            -(o_demanda:Oferta_Laboral)-[:DIRIGE_A]-(ca),
            (o_demanda)-[:PUBLICA]-(:Empresa)-[:AGRUPA]-(i)
      WHERE o_demanda.fecha_publicacion >= datetime($desde)
        AND o_demanda.fecha_publicacion < datetime($hasta)
    }
  )
OPTIONAL MATCH (x)-[:REQUIERE]-(:Requerimiento_Laboral)-[:TIENE]
               -(o_demanda:Oferta_Laboral)-[:DIRIGE_A]-(ca),
               (o_demanda)-[:PUBLICA]-(:Empresa)-[:AGRUPA]-(industria_demanda:Industria)
WHERE industria_demanda.id_industria = $industria_id
  AND o_demanda.fecha_publicacion >= datetime($desde)
  AND o_demanda.fecha_publicacion < datetime($hasta)
WITH ca, i, total_cursos, coberturas_dimension, total_ofertas, availability, x,
     count(DISTINCT o_demanda) AS ofertas_demanda
OPTIONAL MATCH (ca)-[:ENSENIA]-(cu_cobertura:Curso)-[:TIENE]
               -(:Cobertura_Curricular)-[rel:CUBRE|ENSENIA]-(x)
WHERE ($tipo_conocimiento = 'competencia' AND x:Competencia AND type(rel) = 'CUBRE')
   OR ($tipo_conocimiento = 'habilidad' AND x:Habilidad AND type(rel) = 'ENSENIA')
   OR ($tipo_conocimiento = 'herramienta' AND x:Herramienta AND type(rel) = 'ENSENIA')
WITH ca, i, total_cursos, coberturas_dimension, total_ofertas, availability, x,
     ofertas_demanda, count(DISTINCT cu_cobertura) AS cursos_cobertura
WITH *, CASE WHEN availability = 'available'
             THEN toFloat(ofertas_demanda) / total_ofertas ELSE null END AS demanda,
        CASE WHEN availability = 'available'
             THEN toFloat(cursos_cobertura) / total_cursos ELSE null END AS cobertura
WITH *, CASE WHEN availability = 'available' THEN demanda - cobertura
             ELSE null END AS diferencia
ORDER BY diferencia DESC, ofertas_demanda DESC
WITH ca, i, total_cursos, coberturas_dimension, total_ofertas, availability,
     collect({id: coalesce(x.id_competencia, x.id_habilidad, x.id_herramienta),
              nombre: coalesce(x.nombre_competencia, x.nombre_habilidad,
                               x.nombre_herramienta),
              ofertas: ofertas_demanda, cursos: cursos_cobertura,
              demanda: demanda, cobertura: cobertura, diferencia: diferencia})[0..20] AS filas
UNWIND range(0, size(filas) - 1) AS indice
WITH ca, i, total_cursos, coberturas_dimension, total_ofertas, availability,
     filas[indice] AS fila, indice
RETURN ca.id_carrera AS carrera_id,
       ca.nombre_carrera AS carrera,
       i.id_industria AS industria_id,
       i.nombre AS industria,
       fila.id AS conocimiento_id,
       fila.nombre AS conocimiento,
       $tipo_conocimiento AS dimension,
       fila.diferencia AS value,
       fila.demanda AS demand_percentage,
       fila.cobertura AS coverage_percentage,
       CASE WHEN availability = 'available' THEN fila.ofertas ELSE null END
         AS demand_numerator_n,
       CASE WHEN availability = 'available' THEN total_ofertas ELSE null END
         AS demand_denominator_n,
       CASE WHEN availability = 'available' THEN fila.cursos ELSE null END
         AS coverage_numerator_n,
       CASE WHEN availability = 'available' THEN total_cursos ELSE null END
         AS coverage_denominator_n,
       CASE WHEN availability = 'available' THEN indice + 1 ELSE null END AS rank,
       coberturas_dimension AS dimension_coverage_n,
       availability,
       availability = 'available' AS is_comparable,
       CASE WHEN availability = 'unavailable'
            THEN 'Cobertura curricular no disponible en el grafo.'
            WHEN availability = 'incomplete'
            THEN 'No hay cobertura válida para la dimensión seleccionada.'
            WHEN availability = 'no_market_data'
            THEN 'No hay ofertas en el contexto seleccionado.'
            ELSE null END AS warning
ORDER BY rank
}
WITH *
WHERE availability = 'available'
RETURN conocimiento_id,
       conocimiento,
       dimension,
       demand_percentage AS demanda_porcentaje,
       coverage_percentage AS cobertura_porcentaje,
       value AS brecha_porcentual,
       rank
ORDER BY rank
```

**Gráfico sugerido:** `quadrant_or_grouped_bar`. Límite: general 20 filas; específica 20 filas.


### 7. ¿En cuáles la cobertura supera más a la demanda reciente?

**Qué busca mostrar.** Ranking, sin umbral, por proporción de cursos menos proporción de ofertas recientes.

**Cómo leer el resultado.** `brecha_porcentual` compara demanda reciente y cobertura declarada. Es una señal para revisar contenido, no una prueba de que un conocimiento sea obsoleto.

**Advertencia semántica.** Poca demanda observada no prueba obsolescencia; sin mercado se devuelve estado.

#### Query general

**Columnas visuales:** `carrera_id`, `carrera`, `conocimiento_id`, `conocimiento`, `dimension`, `demanda_porcentaje`, `cobertura_porcentaje`, `brecha_porcentual`, `rank`.
**Alcance:** Top 20 diferencias entre contextos comparables.

```cypher
CALL () {
MATCH (todas:Carrera)
WITH count(DISTINCT todas) AS total_carreras
MATCH (oferta:Oferta_Laboral)
WHERE oferta.fecha_publicacion IS NOT NULL
WITH total_carreras, max(oferta.fecha_publicacion) AS fecha_corte
WHERE fecha_corte IS NOT NULL
WITH total_carreras, fecha_corte,
     datetime({year: fecha_corte.year, month: fecha_corte.month, day: 1})
       - duration('P11M') AS fecha_inicio
MATCH (ca:Carrera)-[:ENSENIA]-(curso_total:Curso)
WITH total_carreras, fecha_inicio, fecha_corte, ca,
     count(DISTINCT curso_total) AS total_cursos
OPTIONAL MATCH (ca)-[:DIRIGE_A]-(oferta_total:Oferta_Laboral)
WHERE oferta_total.fecha_publicacion >= fecha_inicio
  AND oferta_total.fecha_publicacion <= fecha_corte
WITH total_carreras, fecha_inicio, fecha_corte, ca, total_cursos,
     count(DISTINCT oferta_total) AS total_ofertas
MATCH (ca)-[:ENSENIA]-(cu:Curso)-[:TIENE]
      -(:Cobertura_Curricular)-[rel:CUBRE|ENSENIA]-(x)
WHERE (x:Competencia AND type(rel) = 'CUBRE')
   OR ((x:Habilidad OR x:Herramienta) AND type(rel) = 'ENSENIA')
WITH total_carreras, fecha_inicio, fecha_corte, ca, total_cursos, total_ofertas, x,
     count(DISTINCT cu) AS cursos_cobertura
OPTIONAL MATCH (x)-[:REQUIERE]-(:Requerimiento_Laboral)-[:TIENE]
               -(o_demanda:Oferta_Laboral)-[:DIRIGE_A]-(ca)
WHERE o_demanda.fecha_publicacion >= fecha_inicio
  AND o_demanda.fecha_publicacion <= fecha_corte
WITH total_carreras, ca, total_cursos, total_ofertas, x, cursos_cobertura,
     count(DISTINCT o_demanda) AS ofertas_demanda
WITH *, CASE WHEN total_ofertas = 0 THEN null
             ELSE toFloat(ofertas_demanda) / total_ofertas END AS demanda,
        toFloat(cursos_cobertura) / total_cursos AS cobertura,
        CASE WHEN total_ofertas = 0 THEN 'no_market_data'
             ELSE 'available' END AS availability
WITH *, CASE WHEN availability = 'available' THEN cobertura - demanda
             ELSE null END AS brecha
ORDER BY brecha DESC, cursos_cobertura DESC
WITH collect({carrera_id: ca.id_carrera, carrera: ca.nombre_carrera,
              id: coalesce(x.id_competencia, x.id_habilidad, x.id_herramienta),
              nombre: coalesce(x.nombre_competencia, x.nombre_habilidad,
                               x.nombre_herramienta),
              dimension: CASE WHEN x:Competencia THEN 'competencia'
                              WHEN x:Habilidad THEN 'habilidad' ELSE 'herramienta' END,
              ofertas: ofertas_demanda, total_ofertas: total_ofertas,
              cursos: cursos_cobertura, total_cursos: total_cursos,
              demanda: demanda, cobertura: cobertura, brecha: brecha,
              availability: availability})[0..20] AS filas,
     total_carreras
UNWIND range(0, size(filas) - 1) AS indice
WITH filas[indice] AS fila, indice, total_carreras
RETURN fila.carrera_id AS carrera_id,
       fila.carrera AS carrera,
       fila.id AS conocimiento_id,
       fila.nombre AS conocimiento,
       fila.dimension AS dimension,
       fila.brecha AS value,
       fila.demanda AS demand_percentage,
       fila.cobertura AS coverage_percentage,
       CASE WHEN fila.availability = 'available' THEN fila.ofertas ELSE null END
         AS demand_numerator_n,
       CASE WHEN fila.availability = 'available' THEN fila.total_ofertas ELSE null END
         AS demand_denominator_n,
       CASE WHEN fila.availability = 'available' THEN fila.cursos ELSE null END
         AS coverage_numerator_n,
       CASE WHEN fila.availability = 'available' THEN fila.total_cursos ELSE null END
         AS coverage_denominator_n,
       CASE WHEN fila.availability = 'available' THEN indice + 1 ELSE null END AS rank,
       fila.availability AS availability,
       fila.availability = 'available' AS is_comparable,
       total_carreras
ORDER BY rank
}
WITH *
WHERE availability = 'available'
RETURN carrera_id,
       carrera,
       conocimiento_id,
       conocimiento,
       dimension,
       demand_percentage AS demanda_porcentaje,
       coverage_percentage AS cobertura_porcentaje,
       value AS brecha_porcentual,
       rank
ORDER BY rank
```

#### Query específica

**Parámetros de ejemplo verificados:**

```cypher
:param {
  carrera_id: "CAR_01375f53651cff38",
  industria_id: "INDU_3b41f23fcb06b8c6",
  tipo_conocimiento: "herramienta",
  desde: "2025-01-01T00:00:00Z",
  hasta: "2026-01-01T00:00:00Z"
}
```

**Columnas visuales:** `conocimiento_id`, `conocimiento`, `dimension`, `demanda_porcentaje`, `cobertura_porcentaje`, `brecha_porcentual`, `rank`.
**Alcance:** Top 20 diferencias o un estado no_market_data.

```cypher
CALL () {
MATCH (ca:Carrera)
WHERE ca.id_carrera = $carrera_id
MATCH (i:Industria)
WHERE i.id_industria = $industria_id
OPTIONAL MATCH (ca)-[:ENSENIA]-(curso_total:Curso)
WITH ca, i, count(DISTINCT curso_total) AS total_cursos
OPTIONAL MATCH (ca)-[:ENSENIA]-(:Curso)-[:TIENE]-(cc:Cobertura_Curricular)
               -[rel:CUBRE|ENSENIA]-(elemento_dimension)
WHERE ($tipo_conocimiento = 'competencia' AND elemento_dimension:Competencia
       AND type(rel) = 'CUBRE')
   OR ($tipo_conocimiento = 'habilidad' AND elemento_dimension:Habilidad
       AND type(rel) = 'ENSENIA')
   OR ($tipo_conocimiento = 'herramienta' AND elemento_dimension:Herramienta
       AND type(rel) = 'ENSENIA')
WITH ca, i, total_cursos, count(DISTINCT cc) AS coberturas_dimension
OPTIONAL MATCH (ca)-[:DIRIGE_A]-(oferta_total:Oferta_Laboral)
               -[:PUBLICA]-(:Empresa)-[:AGRUPA]-(i)
WHERE oferta_total.fecha_publicacion >= datetime($desde)
  AND oferta_total.fecha_publicacion < datetime($hasta)
WITH ca, i, total_cursos, coberturas_dimension,
     count(DISTINCT oferta_total) AS total_ofertas
WITH ca, i, total_cursos, coberturas_dimension, total_ofertas,
     CASE WHEN total_cursos = 0 THEN 'unavailable'
          WHEN coberturas_dimension = 0 THEN 'incomplete'
          WHEN total_ofertas = 0 THEN 'no_market_data'
          ELSE 'available' END AS availability
OPTIONAL MATCH (x)
WHERE availability = 'available'
  AND (($tipo_conocimiento = 'competencia' AND x:Competencia)
    OR ($tipo_conocimiento = 'habilidad' AND x:Habilidad)
    OR ($tipo_conocimiento = 'herramienta' AND x:Herramienta))
  AND EXISTS {
    MATCH (ca)-[:ENSENIA]-(:Curso)-[:TIENE]
          -(:Cobertura_Curricular)-[rel:CUBRE|ENSENIA]-(x)
    WHERE (x:Competencia AND type(rel) = 'CUBRE')
       OR ((x:Habilidad OR x:Herramienta) AND type(rel) = 'ENSENIA')
  }
OPTIONAL MATCH (x)-[:REQUIERE]-(:Requerimiento_Laboral)-[:TIENE]
               -(o_demanda:Oferta_Laboral)-[:DIRIGE_A]-(ca),
               (o_demanda)-[:PUBLICA]-(:Empresa)-[:AGRUPA]-(industria_demanda:Industria)
WHERE industria_demanda.id_industria = $industria_id
  AND o_demanda.fecha_publicacion >= datetime($desde)
  AND o_demanda.fecha_publicacion < datetime($hasta)
WITH ca, i, total_cursos, coberturas_dimension, total_ofertas, availability, x,
     count(DISTINCT o_demanda) AS ofertas_demanda
OPTIONAL MATCH (ca)-[:ENSENIA]-(cu_cobertura:Curso)-[:TIENE]
               -(:Cobertura_Curricular)-[rel:CUBRE|ENSENIA]-(x)
WHERE ($tipo_conocimiento = 'competencia' AND x:Competencia AND type(rel) = 'CUBRE')
   OR ($tipo_conocimiento = 'habilidad' AND x:Habilidad AND type(rel) = 'ENSENIA')
   OR ($tipo_conocimiento = 'herramienta' AND x:Herramienta AND type(rel) = 'ENSENIA')
WITH ca, i, total_cursos, coberturas_dimension, total_ofertas, availability, x,
     ofertas_demanda, count(DISTINCT cu_cobertura) AS cursos_cobertura
WITH *, CASE WHEN availability = 'available'
             THEN toFloat(ofertas_demanda) / total_ofertas ELSE null END AS demanda,
        CASE WHEN availability = 'available'
             THEN toFloat(cursos_cobertura) / total_cursos ELSE null END AS cobertura
WITH *, CASE WHEN availability = 'available' THEN cobertura - demanda
             ELSE null END AS diferencia
ORDER BY diferencia DESC, ofertas_demanda DESC
WITH ca, i, total_cursos, coberturas_dimension, total_ofertas, availability,
     collect({id: coalesce(x.id_competencia, x.id_habilidad, x.id_herramienta),
              nombre: coalesce(x.nombre_competencia, x.nombre_habilidad,
                               x.nombre_herramienta),
              ofertas: ofertas_demanda, cursos: cursos_cobertura,
              demanda: demanda, cobertura: cobertura, diferencia: diferencia})[0..20] AS filas
UNWIND range(0, size(filas) - 1) AS indice
WITH ca, i, total_cursos, coberturas_dimension, total_ofertas, availability,
     filas[indice] AS fila, indice
RETURN ca.id_carrera AS carrera_id,
       ca.nombre_carrera AS carrera,
       i.id_industria AS industria_id,
       i.nombre AS industria,
       fila.id AS conocimiento_id,
       fila.nombre AS conocimiento,
       $tipo_conocimiento AS dimension,
       fila.diferencia AS value,
       fila.demanda AS demand_percentage,
       fila.cobertura AS coverage_percentage,
       CASE WHEN availability = 'available' THEN fila.ofertas ELSE null END
         AS demand_numerator_n,
       CASE WHEN availability = 'available' THEN total_ofertas ELSE null END
         AS demand_denominator_n,
       CASE WHEN availability = 'available' THEN fila.cursos ELSE null END
         AS coverage_numerator_n,
       CASE WHEN availability = 'available' THEN total_cursos ELSE null END
         AS coverage_denominator_n,
       CASE WHEN availability = 'available' THEN indice + 1 ELSE null END AS rank,
       coberturas_dimension AS dimension_coverage_n,
       availability,
       availability = 'available' AS is_comparable,
       CASE WHEN availability = 'unavailable'
            THEN 'Cobertura curricular no disponible en el grafo.'
            WHEN availability = 'incomplete'
            THEN 'No hay cobertura válida para la dimensión seleccionada.'
            WHEN availability = 'no_market_data'
            THEN 'No hay ofertas en el contexto seleccionado.'
            ELSE null END AS warning
ORDER BY rank
}
WITH *
WHERE availability = 'available'
RETURN conocimiento_id,
       conocimiento,
       dimension,
       demand_percentage AS demanda_porcentaje,
       coverage_percentage AS cobertura_porcentaje,
       value AS brecha_porcentual,
       rank
ORDER BY rank
```

**Gráfico sugerido:** `diverging_bar`. Límite: general 20 filas; específica 20 filas.


### 8. ¿Qué cursos comparten más conocimientos con las ofertas del contexto seleccionado?

**Qué busca mostrar.** Top 20 cursos por ofertas únicas relacionadas y conocimientos compartidos.

**Cómo leer el resultado.** `ofertas` es el soporte de mercado asociado al curso y `conocimientos_compartidos` indica el solapamiento usado para priorizarlo.

**Advertencia semántica.** La correspondencia no implica causalidad, calidad del curso ni contratación.

#### Query general

**Columnas visuales:** `carrera_id`, `carrera`, `curso_id`, `curso`, `ofertas`, `conocimientos_compartidos`, `participacion`, `rank`.
**Alcance:** Top 20 cursos de dimensiones comparables.

```cypher
CALL () {
MATCH (todas:Carrera)
WITH count(DISTINCT todas) AS total_carreras
MATCH (perfilada:Carrera)
WHERE EXISTS { MATCH (perfilada)-[:ENSENIA]-(:Curso) }
WITH total_carreras, count(DISTINCT perfilada) AS carreras_perfiladas
MATCH (oferta:Oferta_Laboral)
WHERE oferta.fecha_publicacion IS NOT NULL
WITH total_carreras, carreras_perfiladas, max(oferta.fecha_publicacion) AS fecha_corte
WHERE fecha_corte IS NOT NULL
WITH total_carreras, carreras_perfiladas, fecha_corte,
     datetime({year: fecha_corte.year, month: fecha_corte.month, day: 1})
       - duration('P11M') AS fecha_inicio
MATCH (ca:Carrera)-[:ENSENIA]-(cu:Curso)-[:TIENE]
      -(:Cobertura_Curricular)-[rel:CUBRE|ENSENIA]-(x)
WHERE (x:Competencia AND type(rel) = 'CUBRE')
   OR ((x:Habilidad OR x:Herramienta) AND type(rel) = 'ENSENIA')
MATCH (x)-[:REQUIERE]-(:Requerimiento_Laboral)-[:TIENE]-(o:Oferta_Laboral)
      -[:DIRIGE_A]-(ca)
WHERE o.fecha_publicacion >= fecha_inicio AND o.fecha_publicacion <= fecha_corte
WITH total_carreras, carreras_perfiladas, ca, cu,
     count(DISTINCT x) AS conocimientos_compartidos,
     count(DISTINCT o) AS ofertas_relacionadas
ORDER BY ofertas_relacionadas DESC, conocimientos_compartidos DESC, cu.nombre_curso
WITH total_carreras, carreras_perfiladas,
     collect({carrera_id: ca.id_carrera, carrera: ca.nombre_carrera,
              curso_id: cu.id_curso, curso: cu.nombre_curso,
              conocimientos: conocimientos_compartidos,
              ofertas: ofertas_relacionadas})[0..20] AS filas,
     sum(ofertas_relacionadas) AS total_soporte
UNWIND range(0, size(filas) - 1) AS indice
WITH filas[indice] AS fila, indice, total_soporte, total_carreras, carreras_perfiladas
RETURN fila.carrera_id AS carrera_id,
       fila.carrera AS carrera,
       fila.curso_id AS curso_id,
       fila.curso AS curso,
       fila.ofertas AS value,
       fila.ofertas AS ofertas,
       fila.conocimientos AS conocimientos_compartidos,
       toFloat(fila.ofertas) / total_soporte AS assignment_share,
       indice + 1 AS rank,
       fila.ofertas AS numerator_n,
       total_soporte AS denominator_n,
       total_soporte AS total_assignments,
       carreras_perfiladas,
       total_carreras,
       'available' AS availability,
       toFloat(carreras_perfiladas) / total_carreras AS coverage_percentage,
       true AS is_comparable
ORDER BY rank
}
WITH *
WHERE availability = 'available'
RETURN carrera_id,
       carrera,
       curso_id,
       curso,
       ofertas,
       conocimientos_compartidos,
       assignment_share AS participacion,
       rank
ORDER BY rank
```

#### Query específica

**Parámetros de ejemplo verificados:**

```cypher
:param {
  carrera_id: "CAR_01375f53651cff38",
  industria_id: "INDU_3b41f23fcb06b8c6",
  tipo_conocimiento: "herramienta",
  desde: "2025-01-01T00:00:00Z",
  hasta: "2026-01-01T00:00:00Z"
}
```

**Columnas visuales:** `curso_id`, `curso`, `dimension`, `ofertas`, `conocimientos_compartidos`, `rank`.
**Alcance:** Top 20 cursos o un estado de indisponibilidad.

```cypher
CALL () {
MATCH (ca:Carrera)
WHERE ca.id_carrera = $carrera_id
MATCH (i:Industria)
WHERE i.id_industria = $industria_id
OPTIONAL MATCH (ca)-[:ENSENIA]-(curso_total:Curso)
WITH ca, i, collect(DISTINCT curso_total) AS cursos
OPTIONAL MATCH (ca)-[:ENSENIA]-(:Curso)-[:TIENE]-(cc:Cobertura_Curricular)
               -[rel:CUBRE|ENSENIA]-(elemento)
WHERE ($tipo_conocimiento = 'competencia' AND elemento:Competencia
       AND type(rel) = 'CUBRE')
   OR ($tipo_conocimiento = 'habilidad' AND elemento:Habilidad
       AND type(rel) = 'ENSENIA')
   OR ($tipo_conocimiento = 'herramienta' AND elemento:Herramienta
       AND type(rel) = 'ENSENIA')
WITH ca, i, cursos, count(DISTINCT cc) AS coberturas_dimension,
     count(DISTINCT elemento) AS elementos_dimension
OPTIONAL MATCH (ca)-[:DIRIGE_A]-(oferta_total:Oferta_Laboral)
               -[:PUBLICA]-(:Empresa)-[:AGRUPA]-(i)
WHERE oferta_total.fecha_publicacion >= datetime($desde)
  AND oferta_total.fecha_publicacion < datetime($hasta)
WITH ca, i, cursos, coberturas_dimension, elementos_dimension,
     count(DISTINCT oferta_total) AS total_ofertas
WITH ca, i, cursos, coberturas_dimension, total_ofertas,
     CASE WHEN size(cursos) = 0 THEN 'unavailable'
          WHEN coberturas_dimension = 0 OR elementos_dimension = 0 THEN 'incomplete'
          WHEN total_ofertas = 0 THEN 'no_market_data'
          ELSE 'available' END AS availability
OPTIONAL MATCH (ca)-[:ENSENIA]-(cu:Curso)-[:TIENE]
               -(:Cobertura_Curricular)-[rel:CUBRE|ENSENIA]-(x)
WHERE availability = 'available'
  AND (($tipo_conocimiento = 'competencia' AND x:Competencia AND type(rel) = 'CUBRE')
    OR ($tipo_conocimiento = 'habilidad' AND x:Habilidad AND type(rel) = 'ENSENIA')
    OR ($tipo_conocimiento = 'herramienta' AND x:Herramienta AND type(rel) = 'ENSENIA'))
OPTIONAL MATCH (x)-[:REQUIERE]-(:Requerimiento_Laboral)-[:TIENE]
               -(o:Oferta_Laboral)-[:DIRIGE_A]-(ca),
               (o)-[:PUBLICA]-(:Empresa)-[:AGRUPA]-(industria_oferta:Industria)
WHERE industria_oferta.id_industria = $industria_id
  AND o.fecha_publicacion >= datetime($desde)
  AND o.fecha_publicacion < datetime($hasta)
WITH ca, i, cursos, coberturas_dimension, total_ofertas, availability, cu,
     count(DISTINCT CASE WHEN o IS NOT NULL THEN x END) AS conocimientos_compartidos,
     count(DISTINCT o) AS ofertas_relacionadas
ORDER BY ofertas_relacionadas DESC, conocimientos_compartidos DESC, cu.nombre_curso
WITH ca, i, cursos, coberturas_dimension, total_ofertas, availability,
     collect({curso_id: cu.id_curso, curso: cu.nombre_curso,
              conocimientos: conocimientos_compartidos,
              ofertas: ofertas_relacionadas})[0..20] AS filas
UNWIND range(0, size(filas) - 1) AS indice
WITH ca, i, cursos, coberturas_dimension, total_ofertas, availability,
     filas[indice] AS fila, indice
RETURN ca.id_carrera AS carrera_id,
       ca.nombre_carrera AS carrera,
       i.id_industria AS industria_id,
       i.nombre AS industria,
       fila.curso_id AS curso_id,
       fila.curso AS curso,
       $tipo_conocimiento AS dimension,
       CASE WHEN availability = 'available' THEN fila.ofertas ELSE null END AS value,
       CASE WHEN availability = 'available' THEN fila.ofertas ELSE null END AS numerator_n,
       CASE WHEN availability = 'available' THEN total_ofertas ELSE null END AS denominator_n,
       CASE WHEN availability = 'available' THEN fila.conocimientos ELSE null END
         AS conocimientos_compartidos,
       CASE WHEN availability = 'available' THEN indice + 1 ELSE null END AS rank,
       coberturas_dimension AS dimension_coverage_n,
       availability,
       availability = 'available' AS is_comparable,
       CASE WHEN availability = 'unavailable'
            THEN 'Cobertura curricular no disponible en el grafo.'
            WHEN availability = 'incomplete'
            THEN 'No hay cobertura válida para la dimensión seleccionada.'
            WHEN availability = 'no_market_data'
            THEN 'No hay ofertas en el contexto seleccionado.'
            ELSE null END AS warning
ORDER BY rank
}
WITH *
WHERE availability = 'available'
RETURN curso_id,
       curso,
       dimension,
       value AS ofertas,
       conocimientos_compartidos,
       rank
ORDER BY rank
```

**Gráfico sugerido:** `ranked_bar`. Límite: general 20 filas; específica 20 filas.


## Empresas y funciones

### 9. ¿Qué empresas concentran las ofertas del contexto y qué conocimientos solicitan?

**Qué busca mostrar.** Top 20 empresas y su conocimiento más frecuente.

**Cómo leer el resultado.** El gráfico ordena empresas por publicaciones; `conocimiento_lider` es el conocimiento más frecuente en las ofertas de cada empresa.

**Advertencia semántica.** Describe publicaciones de las empresas, no capacidades internas ni contrataciones.

#### Query general

**Columnas visuales:** `empresa_id`, `empresa`, `conocimiento_id`, `conocimiento_lider`, `ofertas`, `participacion`, `rank`.
**Alcance:** Top 20 empresas recientes.

```cypher
CALL () {
MATCH (oferta:Oferta_Laboral)
WHERE oferta.fecha_publicacion IS NOT NULL
WITH max(oferta.fecha_publicacion) AS fecha_corte
WHERE fecha_corte IS NOT NULL
WITH fecha_corte,
     datetime({year: fecha_corte.year, month: fecha_corte.month, day: 1})
       - duration('P11M') AS fecha_inicio
MATCH (e:Empresa)-[:PUBLICA]-(o_total:Oferta_Laboral)
WHERE o_total.fecha_publicacion >= fecha_inicio
  AND o_total.fecha_publicacion <= fecha_corte
WITH fecha_inicio, fecha_corte, e, count(DISTINCT o_total) AS ofertas
MATCH (e)-[:PUBLICA]-(o:Oferta_Laboral)-[:TIENE]
      -(:Requerimiento_Laboral)-[:REQUIERE]-(x)
WHERE o.fecha_publicacion >= fecha_inicio AND o.fecha_publicacion <= fecha_corte
  AND (x:Competencia OR x:Habilidad OR x:Herramienta)
WITH e, ofertas, x, count(DISTINCT o) AS ofertas_con_conocimiento
ORDER BY e.id_empresa, ofertas_con_conocimiento DESC,
         coalesce(x.nombre_competencia, x.nombre_habilidad, x.nombre_herramienta)
WITH e, ofertas,
     collect({id: coalesce(x.id_competencia, x.id_habilidad, x.id_herramienta),
              nombre: coalesce(x.nombre_competencia, x.nombre_habilidad,
                               x.nombre_herramienta),
              ofertas: ofertas_con_conocimiento})[0] AS lider
ORDER BY ofertas DESC, e.nombre
WITH collect({empresa_id: e.id_empresa, empresa: e.nombre,
              ofertas: ofertas, lider: lider})[0..20] AS filas,
     sum(ofertas) AS total_asignaciones
UNWIND range(0, size(filas) - 1) AS indice
WITH filas[indice] AS fila, indice, total_asignaciones
RETURN fila.empresa_id AS empresa_id,
       fila.empresa AS empresa,
       fila.lider.id AS conocimiento_id,
       fila.lider.nombre AS conocimiento_lider,
       fila.ofertas AS value,
       fila.ofertas AS ofertas,
       fila.lider.ofertas AS ofertas_con_conocimiento_lider,
       toFloat(fila.ofertas) / total_asignaciones AS assignment_share,
       indice + 1 AS rank,
       fila.ofertas AS numerator_n,
       total_asignaciones AS denominator_n,
       total_asignaciones AS total_assignments,
       'available' AS availability
ORDER BY rank
}
WITH *
WHERE availability = 'available'
RETURN empresa_id,
       empresa,
       conocimiento_id,
       conocimiento_lider,
       ofertas,
       assignment_share AS participacion,
       rank
ORDER BY rank
```

#### Query específica

**Parámetros de ejemplo verificados:**

```cypher
:param {
  carrera_id: "CAR_01375f53651cff38",
  industria_id: "INDU_3b41f23fcb06b8c6",
  desde: "2025-01-01T00:00:00Z",
  hasta: "2026-01-01T00:00:00Z"
}
```

**Columnas visuales:** `empresa_id`, `empresa`, `conocimiento_id`, `conocimiento_lider`, `ofertas`, `participacion`, `rank`.
**Alcance:** Top 20 empresas para carrera, industria y período.

```cypher
CALL () {
MATCH (ca:Carrera)-[:DIRIGE_A]-(o_total:Oferta_Laboral)
      -[:PUBLICA]-(e:Empresa)-[:AGRUPA]-(i:Industria)
WHERE ca.id_carrera = $carrera_id
  AND i.id_industria = $industria_id
  AND o_total.fecha_publicacion >= datetime($desde)
  AND o_total.fecha_publicacion < datetime($hasta)
WITH ca, i, e, count(DISTINCT o_total) AS ofertas
MATCH (ca)-[:DIRIGE_A]-(o:Oferta_Laboral)-[:PUBLICA]-(e)
MATCH (o)-[:TIENE]-(:Requerimiento_Laboral)-[:REQUIERE]-(x)
WHERE o.fecha_publicacion >= datetime($desde)
  AND o.fecha_publicacion < datetime($hasta)
  AND (x:Competencia OR x:Habilidad OR x:Herramienta)
WITH ca, i, e, ofertas, x, count(DISTINCT o) AS ofertas_con_conocimiento
ORDER BY e.id_empresa, ofertas_con_conocimiento DESC,
         coalesce(x.nombre_competencia, x.nombre_habilidad, x.nombre_herramienta)
WITH ca, i, e, ofertas,
     collect({id: coalesce(x.id_competencia, x.id_habilidad, x.id_herramienta),
              nombre: coalesce(x.nombre_competencia, x.nombre_habilidad,
                               x.nombre_herramienta),
              ofertas: ofertas_con_conocimiento})[0] AS lider
ORDER BY ofertas DESC, e.nombre
WITH ca, i,
     collect({empresa_id: e.id_empresa, empresa: e.nombre,
              ofertas: ofertas, lider: lider})[0..20] AS filas,
     sum(ofertas) AS total_asignaciones
UNWIND range(0, size(filas) - 1) AS indice
WITH ca, i, filas[indice] AS fila, indice, total_asignaciones
RETURN ca.id_carrera AS carrera_id,
       ca.nombre_carrera AS carrera,
       i.id_industria AS industria_id,
       i.nombre AS industria,
       fila.empresa_id AS empresa_id,
       fila.empresa AS empresa,
       fila.lider.id AS conocimiento_id,
       fila.lider.nombre AS conocimiento_lider,
       fila.ofertas AS value,
       fila.ofertas AS ofertas,
       fila.lider.ofertas AS ofertas_con_conocimiento_lider,
       toFloat(fila.ofertas) / total_asignaciones AS assignment_share,
       indice + 1 AS rank,
       fila.ofertas AS numerator_n,
       total_asignaciones AS denominator_n,
       total_asignaciones AS total_assignments,
       'available' AS availability
ORDER BY rank
}
WITH *
WHERE availability = 'available'
RETURN empresa_id,
       empresa,
       conocimiento_id,
       conocimiento_lider,
       ofertas,
       assignment_share AS participacion,
       rank
ORDER BY rank
```

**Gráfico sugerido:** `ranked_bar_with_detail`. Límite: general 20 filas; específica 20 filas.


### 10. ¿Qué conocimientos aparecen proporcionalmente más en las ofertas de Empresa A que de Empresa B?

**Qué busca mostrar.** Lift con soporte mínimo en macro; diferencias positivas A−B en detalle.

**Cómo leer el resultado.** En macro, `lift` compara la frecuencia de cada conocimiento contra el mercado. En detalle, `diferencia_pp` es Empresa A menos Empresa B, en puntos porcentuales.

**Advertencia semántica.** Compara demanda publicada; ambas empresas deben existir y tener soporte.

#### Query general

**Columnas visuales:** `empresa_id`, `empresa`, `conocimiento_id`, `conocimiento`, `lift`, `rank`.
**Alcance:** Top 20 lifts empresa-conocimiento con soporte mínimo 5.

```cypher
CALL () {
MATCH (oferta:Oferta_Laboral)
WHERE oferta.fecha_publicacion IS NOT NULL
WITH max(oferta.fecha_publicacion) AS fecha_corte
WHERE fecha_corte IS NOT NULL
WITH fecha_corte,
     datetime({year: fecha_corte.year, month: fecha_corte.month, day: 1})
       - duration('P11M') AS fecha_inicio
MATCH (total:Oferta_Laboral)
WHERE total.fecha_publicacion >= fecha_inicio AND total.fecha_publicacion <= fecha_corte
WITH fecha_inicio, fecha_corte, count(DISTINCT total) AS total_ofertas
MATCH (o_global:Oferta_Laboral)-[:TIENE]
      -(:Requerimiento_Laboral)-[:REQUIERE]-(x)
WHERE o_global.fecha_publicacion >= fecha_inicio
  AND o_global.fecha_publicacion <= fecha_corte
  AND (x:Competencia OR x:Habilidad OR x:Herramienta)
WITH fecha_inicio, fecha_corte, total_ofertas, x,
     count(DISTINCT o_global) AS global_numerator_n
MATCH (e:Empresa)-[:PUBLICA]-(o_empresa:Oferta_Laboral)-[:TIENE]
      -(:Requerimiento_Laboral)-[:REQUIERE]-(x)
WHERE o_empresa.fecha_publicacion >= fecha_inicio
  AND o_empresa.fecha_publicacion <= fecha_corte
WITH fecha_inicio, fecha_corte, total_ofertas, x, global_numerator_n, e,
     count(DISTINCT o_empresa) AS numerator_n
WITH *, COUNT {
       MATCH (e)-[:PUBLICA]-(o_denominador:Oferta_Laboral)
       WHERE o_denominador.fecha_publicacion >= fecha_inicio
         AND o_denominador.fecha_publicacion <= fecha_corte
     } AS denominator_n
WHERE denominator_n >= 5 AND numerator_n >= 2
WITH e, x, denominator_n, numerator_n, total_ofertas, global_numerator_n,
     (toFloat(numerator_n) / denominator_n)
       / (toFloat(global_numerator_n) / total_ofertas) AS lift
ORDER BY lift DESC, numerator_n DESC, e.nombre
WITH collect({empresa_id: e.id_empresa, empresa: e.nombre,
              id: coalesce(x.id_competencia, x.id_habilidad, x.id_herramienta),
              nombre: coalesce(x.nombre_competencia, x.nombre_habilidad,
                               x.nombre_herramienta),
              numerator_n: numerator_n, denominator_n: denominator_n,
              global_numerator_n: global_numerator_n,
              global_denominator_n: total_ofertas, lift: lift})[0..20] AS filas
UNWIND range(0, size(filas) - 1) AS indice
WITH filas[indice] AS fila, indice
RETURN fila.empresa_id AS empresa_id,
       fila.empresa AS empresa,
       fila.id AS conocimiento_id,
       fila.nombre AS conocimiento,
       fila.lift AS value,
       fila.lift AS lift,
       fila.numerator_n AS numerator_n,
       fila.denominator_n AS denominator_n,
       fila.global_numerator_n AS global_numerator_n,
       fila.global_denominator_n AS global_denominator_n,
       indice + 1 AS rank,
       'available' AS availability,
       5 AS minimum_support_n
ORDER BY rank
}
WITH *
WHERE availability = 'available'
RETURN empresa_id,
       empresa,
       conocimiento_id,
       conocimiento,
       lift,
       rank
ORDER BY rank
```

#### Query específica

**Parámetros de ejemplo verificados:**

```cypher
:param {
  empresa_a_id: "EMP_a197af00a598b78c",
  empresa_b_id: "EMP_47f42efb87384408",
  desde: "2025-01-01T00:00:00Z",
  hasta: "2026-01-01T00:00:00Z"
}
```

**Columnas visuales:** `empresa_a`, `empresa_b`, `conocimiento_id`, `conocimiento`, `dimension`, `porcentaje_empresa_a`, `porcentaje_empresa_b`, `diferencia_pp`, `rank`.
**Alcance:** Top 20 diferencias positivas entre dos empresas.

```cypher
CALL () {
MATCH (empresa_a:Empresa)
WHERE empresa_a.id_empresa = $empresa_a_id
OPTIONAL MATCH (empresa_b:Empresa)
WHERE empresa_b.id_empresa = $empresa_b_id
OPTIONAL MATCH (empresa_a)-[:PUBLICA]-(oferta_a:Oferta_Laboral)
WHERE oferta_a.fecha_publicacion >= datetime($desde)
  AND oferta_a.fecha_publicacion < datetime($hasta)
WITH empresa_a, empresa_b, count(DISTINCT oferta_a) AS denominator_n_a
OPTIONAL MATCH (empresa_b)-[:PUBLICA]-(oferta_b:Oferta_Laboral)
WHERE oferta_b.fecha_publicacion >= datetime($desde)
  AND oferta_b.fecha_publicacion < datetime($hasta)
WITH empresa_a, empresa_b, denominator_n_a,
     count(DISTINCT oferta_b) AS denominator_n_b
WITH empresa_a, empresa_b, denominator_n_a, denominator_n_b,
     CASE WHEN empresa_a IS NULL OR empresa_b IS NULL THEN 'company_not_found'
          WHEN denominator_n_a = 0 OR denominator_n_b = 0 THEN 'no_market_data'
          ELSE 'available' END AS availability
OPTIONAL MATCH (empresa:Empresa)-[:PUBLICA]-(o:Oferta_Laboral)-[:TIENE]
      -(:Requerimiento_Laboral)-[:REQUIERE]-(x)
WHERE availability = 'available'
  AND empresa.id_empresa IN [$empresa_a_id, $empresa_b_id]
  AND o.fecha_publicacion >= datetime($desde)
  AND o.fecha_publicacion < datetime($hasta)
  AND (x:Competencia OR x:Habilidad OR x:Herramienta)
WITH empresa_a, empresa_b, denominator_n_a, denominator_n_b, availability, x,
     count(DISTINCT CASE WHEN empresa.id_empresa = $empresa_a_id THEN o END)
       AS numerator_n_a,
     count(DISTINCT CASE WHEN empresa.id_empresa = $empresa_b_id THEN o END)
       AS numerator_n_b
WITH empresa_a, empresa_b, denominator_n_a, denominator_n_b, availability, x,
     numerator_n_a, numerator_n_b,
     CASE WHEN availability = 'available' THEN toFloat(numerator_n_a) / denominator_n_a
          ELSE null END AS percentage_a,
     CASE WHEN availability = 'available' THEN toFloat(numerator_n_b) / denominator_n_b
          ELSE null END AS percentage_b
WITH *, CASE WHEN availability = 'available' THEN percentage_a - percentage_b
             ELSE null END AS difference_pp
ORDER BY difference_pp DESC, numerator_n_a DESC,
         coalesce(x.nombre_competencia, x.nombre_habilidad, x.nombre_herramienta)
WITH empresa_a, empresa_b, denominator_n_a, denominator_n_b, availability,
     [fila IN collect({
              id: coalesce(x.id_competencia, x.id_habilidad, x.id_herramienta),
              nombre: coalesce(x.nombre_competencia, x.nombre_habilidad,
                               x.nombre_herramienta),
              dimension: CASE WHEN x:Competencia THEN 'competencia'
                              WHEN x:Habilidad THEN 'habilidad'
                              WHEN x:Herramienta THEN 'herramienta' ELSE null END,
              numerator_n_a: numerator_n_a, numerator_n_b: numerator_n_b,
              percentage_a: percentage_a, percentage_b: percentage_b,
              difference_pp: difference_pp})
      WHERE availability <> 'available' OR fila.difference_pp > 0][0..20] AS datos
WITH empresa_a, empresa_b, denominator_n_a, denominator_n_b,
     CASE WHEN availability = 'available' AND size(datos) = 0
          THEN 'no_positive_difference' ELSE availability END AS availability,
     CASE WHEN size(datos) = 0
          THEN [{id: null, nombre: null, dimension: null, numerator_n_a: null,
                 numerator_n_b: null, percentage_a: null, percentage_b: null,
                 difference_pp: null}]
          ELSE datos END AS filas
UNWIND range(0, size(filas) - 1) AS indice
WITH empresa_a, empresa_b, denominator_n_a, denominator_n_b, availability,
     filas[indice] AS fila, indice
RETURN $empresa_a_id AS empresa_a_id,
       empresa_a.nombre AS empresa_a,
       $empresa_b_id AS empresa_b_id,
       empresa_b.nombre AS empresa_b,
       fila.id AS conocimiento_id,
       fila.nombre AS conocimiento,
       fila.dimension AS dimension,
       fila.difference_pp AS value,
       fila.percentage_a AS empresa_a_percentage,
       fila.percentage_b AS empresa_b_percentage,
       fila.difference_pp AS difference_pp,
       CASE WHEN availability = 'available' THEN fila.numerator_n_a ELSE null END
         AS numerator_n_a,
       CASE WHEN empresa_a IS NOT NULL THEN denominator_n_a ELSE null END AS denominator_n_a,
       CASE WHEN availability = 'available' THEN fila.numerator_n_b ELSE null END
         AS numerator_n_b,
       CASE WHEN empresa_b IS NOT NULL THEN denominator_n_b ELSE null END AS denominator_n_b,
       CASE WHEN availability = 'available' THEN indice + 1 ELSE null END AS rank,
       availability,
       CASE WHEN availability = 'company_not_found' THEN 'Una empresa no existe.'
            WHEN availability = 'no_market_data'
            THEN 'Ambas empresas necesitan ofertas en el período.'
            WHEN availability = 'no_positive_difference'
            THEN 'No hay conocimientos con diferencia positiva para Empresa A.'
            ELSE null END AS warning
ORDER BY rank
}
WITH *
WHERE availability = 'available'
RETURN empresa_a,
       empresa_b,
       conocimiento_id,
       conocimiento,
       dimension,
       empresa_a_percentage AS porcentaje_empresa_a,
       empresa_b_percentage AS porcentaje_empresa_b,
       difference_pp AS diferencia_pp,
       rank
ORDER BY rank
```

**Gráfico sugerido:** `diverging_bar`. Límite: general 20 filas; específica 20 filas.


### 11. ¿Qué conocimientos aparecen con mayor frecuencia en ofertas cuyos títulos tienen señal textual de liderazgo en una industria?

**Qué busca mostrar.** Industrias con más títulos señalados y top 10 conocimientos al seleccionar una.

**Cómo leer el resultado.** `porcentaje` es la proporción dentro de las ofertas con señal textual de liderazgo. La señal se obtiene del título publicado, no de una función normalizada.

**Advertencia semántica.** Es una heurística por términos inequívocos del título, no una función normalizada.

#### Query general

**Columnas visuales:** `industria_id`, `industria`, `ofertas_liderazgo`, `porcentaje`, `rank`.
**Alcance:** Top 20 industrias por títulos con señal textual.

```cypher
CALL () {
MATCH (oferta:Oferta_Laboral)
WHERE oferta.fecha_publicacion IS NOT NULL
WITH max(oferta.fecha_publicacion) AS fecha_corte
WHERE fecha_corte IS NOT NULL
WITH fecha_corte,
     datetime({year: fecha_corte.year, month: fecha_corte.month, day: 1})
       - duration('P11M') AS fecha_inicio
MATCH (i:Industria)-[:AGRUPA]-(:Empresa)-[:PUBLICA]-(o:Oferta_Laboral)
WHERE o.fecha_publicacion >= fecha_inicio AND o.fecha_publicacion <= fecha_corte
WITH i, fecha_inicio, fecha_corte, count(DISTINCT o) AS total_ofertas
OPTIONAL MATCH (i)-[:AGRUPA]-(:Empresa)-[:PUBLICA]-(o_lider:Oferta_Laboral)
               -[:OFRECE]-(p:Puesto)
WHERE o_lider.fecha_publicacion >= fecha_inicio
  AND o_lider.fecha_publicacion <= fecha_corte
  AND p.nombre =~ '(?i).*(^|[^a-záéíóúüñ0-9])(jefe|gerente|director|directora|líder|lider|supervisor|supervisora|chief|head of|team lead)($|[^a-záéíóúüñ0-9]).*'
WITH i, total_ofertas, count(DISTINCT o_lider) AS ofertas_liderazgo
WHERE ofertas_liderazgo > 0
ORDER BY ofertas_liderazgo DESC, i.nombre
WITH collect({industria_id: i.id_industria, industria: i.nombre,
              liderazgo: ofertas_liderazgo, total: total_ofertas})[0..20] AS datos
WITH CASE WHEN size(datos) = 0
          THEN [{industria_id: null, industria: null, liderazgo: null, total: null}]
          ELSE datos END AS filas
UNWIND range(0, size(filas) - 1) AS indice
WITH filas[indice] AS fila, indice
RETURN fila.industria_id AS industria_id,
       fila.industria AS industria,
       fila.liderazgo AS value,
       fila.liderazgo AS titulos_con_senal_liderazgo,
       CASE WHEN fila.total IS NOT NULL THEN toFloat(fila.liderazgo) / fila.total
            ELSE null END AS percentage,
       CASE WHEN fila.total IS NOT NULL THEN indice + 1 ELSE null END AS rank,
       fila.liderazgo AS numerator_n,
       fila.total AS denominator_n,
       CASE WHEN fila.total IS NULL THEN 'no_data' ELSE 'available' END AS availability
ORDER BY rank
}
WITH *
WHERE availability = 'available'
RETURN industria_id,
       industria,
       titulos_con_senal_liderazgo AS ofertas_liderazgo,
       percentage AS porcentaje,
       rank
ORDER BY rank
```

#### Query específica

**Parámetros de ejemplo verificados:**

```cypher
:param {
  industria_id: "INDU_3b41f23fcb06b8c6",
  desde: "2024-01-01T00:00:00Z",
  hasta: "2025-01-01T00:00:00Z"
}
```

**Columnas visuales:** `conocimiento_id`, `conocimiento`, `dimension`, `ofertas`, `porcentaje`, `rank`.
**Alcance:** Top 10 conocimientos de los títulos señalados.

```cypher
CALL () {
MATCH (i:Industria)
WHERE i.id_industria = $industria_id
OPTIONAL MATCH (i)-[:AGRUPA]-(:Empresa)-[:PUBLICA]-(o_total:Oferta_Laboral)
               -[:OFRECE]-(p_total:Puesto)
WHERE o_total.fecha_publicacion >= datetime($desde)
  AND o_total.fecha_publicacion < datetime($hasta)
  AND p_total.nombre =~ '(?i).*(^|[^a-záéíóúüñ0-9])(jefe|gerente|director|directora|líder|lider|supervisor|supervisora|chief|head of|team lead)($|[^a-záéíóúüñ0-9]).*'
WITH i, count(DISTINCT o_total) AS total_liderazgo
WITH i, total_liderazgo,
     CASE WHEN total_liderazgo = 0 THEN 'no_data' ELSE 'available' END AS availability
OPTIONAL MATCH (i)-[:AGRUPA]-(:Empresa)-[:PUBLICA]-(o:Oferta_Laboral)
               -[:OFRECE]-(p:Puesto),
               (o)-[:TIENE]-(:Requerimiento_Laboral)-[:REQUIERE]-(x)
WHERE availability = 'available'
  AND o.fecha_publicacion >= datetime($desde)
  AND o.fecha_publicacion < datetime($hasta)
  AND p.nombre =~ '(?i).*(^|[^a-záéíóúüñ0-9])(jefe|gerente|director|directora|líder|lider|supervisor|supervisora|chief|head of|team lead)($|[^a-záéíóúüñ0-9]).*'
  AND (x:Competencia OR x:Habilidad OR x:Herramienta)
WITH i, total_liderazgo, availability, x, count(DISTINCT o) AS ofertas
ORDER BY ofertas DESC,
         coalesce(x.nombre_competencia, x.nombre_habilidad, x.nombre_herramienta)
WITH i, total_liderazgo, availability,
     collect({id: coalesce(x.id_competencia, x.id_habilidad, x.id_herramienta),
              nombre: coalesce(x.nombre_competencia, x.nombre_habilidad,
                               x.nombre_herramienta),
              dimension: CASE WHEN x:Competencia THEN 'competencia'
                              WHEN x:Habilidad THEN 'habilidad'
                              WHEN x:Herramienta THEN 'herramienta' ELSE null END,
              ofertas: ofertas})[0..10] AS filas
UNWIND range(0, size(filas) - 1) AS indice
WITH i, total_liderazgo, availability, filas[indice] AS fila, indice
RETURN i.id_industria AS industria_id,
       i.nombre AS industria,
       fila.id AS conocimiento_id,
       fila.nombre AS conocimiento,
       fila.dimension AS dimension,
       CASE WHEN availability = 'available' THEN fila.ofertas ELSE null END AS value,
       CASE WHEN availability = 'available' THEN fila.ofertas ELSE null END AS ofertas,
       CASE WHEN availability = 'available' THEN toFloat(fila.ofertas) / total_liderazgo
            ELSE null END AS percentage,
       CASE WHEN availability = 'available' THEN indice + 1 ELSE null END AS rank,
       CASE WHEN availability = 'available' THEN fila.ofertas ELSE null END AS numerator_n,
       CASE WHEN availability = 'available' THEN total_liderazgo ELSE null END AS denominator_n,
       availability
ORDER BY rank
}
WITH *
WHERE availability = 'available'
RETURN conocimiento_id,
       conocimiento,
       dimension,
       ofertas,
       percentage AS porcentaje,
       rank
ORDER BY rank
```

**Gráfico sugerido:** `ranked_bar_drilldown`. Límite: general 20 filas; específica 10 filas.


### 12. ¿Cómo cambia la distribución de títulos de puesto para una carrera según el tipo de empresa?

**Qué busca mostrar.** Hasta 4 tipos con mayor soporte y top 5 títulos elegibles por tipo.

**Cómo leer el resultado.** `participacion` es el peso del título dentro de su tipo de empresa. El título se normaliza solo en mayúsculas/minúsculas y espacios.

**Advertencia semántica.** No existe tamaño empresarial; Puesto.nombre es título publicado, no función normalizada.

#### Query general

**Columnas visuales:** `tipo_empresa`, `titulo_publicado`, `ofertas`, `participacion`, `rank`.
**Alcance:** Hasta 4 tipos y 5 títulos por tipo, máximo 20 filas.

```cypher
CALL () {
MATCH (oferta:Oferta_Laboral)
WHERE oferta.fecha_publicacion IS NOT NULL
WITH max(oferta.fecha_publicacion) AS fecha_corte
WHERE fecha_corte IS NOT NULL
WITH fecha_corte,
     datetime({year: fecha_corte.year, month: fecha_corte.month, day: 1})
       - duration('P11M') AS fecha_inicio
MATCH (o:Oferta_Laboral)-[:PUBLICA]-(e:Empresa)
MATCH (o)-[:OFRECE]-(p:Puesto)
WHERE o.fecha_publicacion >= fecha_inicio
  AND o.fecha_publicacion <= fecha_corte
  AND e.tipo IS NOT NULL
  AND p.nombre IS NOT NULL
  AND trim(p.nombre) <> ''
WITH e.tipo AS tipo_empresa, toLower(trim(p.nombre)) AS titulo_publicado,
     count(DISTINCT o) AS ofertas
ORDER BY tipo_empresa, ofertas DESC, titulo_publicado
WITH tipo_empresa,
     collect({titulo: titulo_publicado, ofertas: ofertas}) AS titulos,
     sum(ofertas) AS total_assignments
ORDER BY total_assignments DESC, tipo_empresa
WITH collect({tipo: tipo_empresa, titulos: titulos,
              total: total_assignments})[0..4] AS tipos
UNWIND tipos AS tipo
UNWIND range(0, size(tipo.titulos[0..5]) - 1) AS indice
WITH tipo, tipo.titulos[indice] AS fila, indice
RETURN tipo.tipo AS tipo_empresa_id,
       tipo.tipo AS tipo_empresa,
       fila.titulo AS titulo_publicado,
       fila.ofertas AS value,
       fila.ofertas AS ofertas,
       toFloat(fila.ofertas) / tipo.total AS assignment_share,
       indice + 1 AS rank,
       fila.ofertas AS numerator_n,
       tipo.total AS denominator_n,
       tipo.total AS total_assignments,
       'available' AS availability
ORDER BY denominator_n DESC, tipo_empresa, rank
LIMIT 20
}
WITH *
WHERE availability = 'available'
RETURN tipo_empresa,
       titulo_publicado,
       ofertas,
       assignment_share AS participacion,
       rank
ORDER BY tipo_empresa, rank
```

#### Query específica

**Parámetros de ejemplo verificados:**

```cypher
:param {
  carrera_id: "CAR_01375f53651cff38",
  desde: "2024-01-01T00:00:00Z",
  hasta: "2025-01-01T00:00:00Z"
}
```

**Columnas visuales:** `tipo_empresa`, `titulo_publicado`, `ofertas`, `participacion`, `rank`.
**Alcance:** Hasta 4 tipos y 5 títulos por tipo, máximo 20 filas.

```cypher
CALL () {
MATCH (ca:Carrera)-[:DIRIGE_A]-(o:Oferta_Laboral)-[:PUBLICA]-(e:Empresa)
MATCH (o)-[:OFRECE]-(p:Puesto)
WHERE ca.id_carrera = $carrera_id
  AND o.fecha_publicacion >= datetime($desde)
  AND o.fecha_publicacion < datetime($hasta)
  AND e.tipo IS NOT NULL
  AND p.nombre IS NOT NULL
  AND trim(p.nombre) <> ''
WITH ca, e.tipo AS tipo_empresa, toLower(trim(p.nombre)) AS titulo_publicado,
     count(DISTINCT o) AS ofertas
ORDER BY tipo_empresa, ofertas DESC, titulo_publicado
WITH ca, tipo_empresa,
     collect({titulo: titulo_publicado, ofertas: ofertas}) AS titulos,
     sum(ofertas) AS total_assignments
ORDER BY total_assignments DESC, tipo_empresa
WITH ca, collect({tipo: tipo_empresa, titulos: titulos,
                  total: total_assignments})[0..4] AS tipos
UNWIND tipos AS tipo
UNWIND range(0, size(tipo.titulos[0..5]) - 1) AS indice
WITH ca, tipo, tipo.titulos[indice] AS fila, indice
RETURN ca.id_carrera AS carrera_id,
       ca.nombre_carrera AS carrera,
       tipo.tipo AS tipo_empresa_id,
       tipo.tipo AS tipo_empresa,
       fila.titulo AS titulo_publicado,
       fila.ofertas AS value,
       fila.ofertas AS ofertas,
       toFloat(fila.ofertas) / tipo.total AS assignment_share,
       indice + 1 AS rank,
       fila.ofertas AS numerator_n,
       tipo.total AS denominator_n,
       tipo.total AS total_assignments,
       'available' AS availability
ORDER BY denominator_n DESC, tipo_empresa, rank
LIMIT 20
}
WITH *
WHERE availability = 'available'
RETURN tipo_empresa,
       titulo_publicado,
       ofertas,
       assignment_share AS participacion,
       rank
ORDER BY tipo_empresa, rank
```

**Gráfico sugerido:** `grouped_bar_drilldown`. Límite: general 20 filas; específica 20 filas.


## Evidencia de validación

| # | Consulta | Vistas | Contrato visual |
|---:|---|---|---|
| 1 | `tendencia_ofertas` | general y específica | período, ofertas |
| 2 | `carreras_con_mayor_demanda` | general y específica | carrera, ofertas, participación, rank |
| 3 | `industrias_por_carrera` | general y específica | industria, ofertas, participación, rank |
| 4 | `conocimientos_mas_demandados` | general y específica | conocimiento, ofertas, porcentaje, rank |
| 5 | `cobertura_curricular` | general y específica | cobertura curricular por carrera o conocimiento |
| 6 | `brechas_demanda_alta` | general y específica | demanda, cobertura, brecha, rank |
| 7 | `senales_revision_vigencia` | general y específica | demanda, cobertura, brecha, rank |
| 8 | `cursos_con_mayor_correspondencia` | general y específica | curso, ofertas, conocimientos compartidos, rank |
| 9 | `empresas_y_conocimientos` | general y específica | empresa, conocimiento líder, ofertas, participación |
| 10 | `diferenciadores_empresas` | general y específica | lift o comparación porcentual entre empresas |
| 11 | `conocimientos_liderazgo` | general y específica | industria o conocimiento, porcentaje, rank |
| 12 | `funciones_por_tipo_empresa` | general y específica | tipo de empresa, título, ofertas, participación |

Las queries generales no requieren parámetros. El carácter `$` que aparece dentro de la expresión regular de liderazgo es un ancla de fin de texto, no un parámetro Cypher.

## Checklist antes de graficar

- [ ] La query general corre sin parámetros.
- [ ] La query específica usa exactamente los parámetros de su bloque `:param`.
- [ ] Las columnas devueltas corresponden al gráfico indicado; no contienen aliases técnicos duplicados.
- [ ] Una tabla vacía se interpreta como falta de datos/cobertura verificable, nunca como cero.
- [ ] Las conclusiones respetan los límites semánticos de la pregunta.
