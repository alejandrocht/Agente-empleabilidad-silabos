# Consultas listas para validar las 12 preguntas del dashboard en Neo4j

Este documento permite copiar, pegar y ejecutar el catálogo fijo del dashboard directamente en Neo4j Browser. Cada pregunta incluye una vista general para descubrir la tendencia y una vista específica para profundizar con filtros reales.

## Inicio rápido en Neo4j Browser

1. Limpie el editor cuando cambie de prueba:

   ```cypher
   :clear
   ```

2. Para una **query general**, pegue y ejecute solamente el bloque Cypher. No requiere parámetros.
3. Para una **query específica**, ejecute primero su bloque `:param` y después el bloque Cypher. Neo4j Browser conserva los parámetros hasta que los cambie o cierre la sesión.
4. Lea `availability` antes de interpretar métricas. `available` habilita la comparación; otros estados explican por qué faltan datos.

> [!NOTE]
> Los rangos usan el intervalo semiabierto `[desde, hasta)`: incluyen `desde` y excluyen `hasta`. Los ejemplos usan 12 meses, por debajo del máximo permitido de 20 buckets mensuales.

### Entidades reales utilizadas

| Parámetro | Valor real usado | Entidad |
|---|---|---|
| `carrera_id` | `CAR_01375f53651cff38` | Ingeniería de Sistemas |
| `facultad_id` | `FAC_7ae410ba957c79d1` | Facultad de Ingeniería |
| `industria_id` | `INDU_3b41f23fcb06b8c6` | Actividades de consultoría de gestión |
| `empresa_a_id` | `EMP_a197af00a598b78c` | EVENTIVA S.A.C. |
| `empresa_b_id` | `EMP_47f42efb87384408` | ADECCO CONSULTING S.A. |
| `tipo_conocimiento` | `herramienta` | Dimensión herramienta |

## Límites de interpretación

> [!IMPORTANT]
> El grafo no contiene egresados ni personas. Las consultas miden ofertas publicadas y relaciones declaradas; no permiten afirmar dónde trabajan los graduados ni quién fue contratado.

> [!CAUTION]
> En la instancia validada, solo Ingeniería de Sistemas tiene currículo conectado. Para otras carreras, la ausencia de currículo debe mostrarse como `unavailable` o `incomplete`, nunca como cobertura de 0 %.

> [!WARNING]
> `Puesto.nombre` es un título publicado, no una función normalizada. Además, liderazgo se detecta mediante términos del título; es una heurística y puede producir falsos positivos o negativos.

> [!NOTE]
> Ausencia de datos de mercado o currículo no equivale a valor cero. Respete `availability`, `warning` e `is_comparable` antes de graficar o comparar.

## Índice

| Sección | Preguntas |
|---|---|
| Panorama laboral | 1-4 |
| Alineación curricular | 5-8 |
| Empresas y funciones | 9-12 |

## Panorama laboral

### 1. ¿Cómo cambia mes a mes la cantidad de ofertas publicadas?

**Qué busca mostrar.** La evolución mensual de publicaciones y los meses de aceleración, caída o estabilidad dentro del contexto elegido.

**Cómo leer el resultado.** `value` y `ofertas` son ofertas únicas del mes. Los meses sin publicaciones se conservan con cero; `availability` distingue una serie válida. No existe denominador porcentual para esta métrica.

**Advertencia semántica.** Mide publicaciones, no contrataciones ni empleo efectivo.

#### Query general

**Alcance:** Un mes por fila, máximo 12 meses.

```cypher
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

```cypher
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
```

**Resultado esperado.** La vista general devuelve hasta **12 filas** y la específica hasta **20 filas**. Con los parámetros anteriores, la ejecución verificada devolvió **12 filas** con estado **`available`**. Gráfico sugerido: **línea**.

### 2. ¿Qué carreras concentran más ofertas dirigidas?

**Qué busca mostrar.** Qué carreras reciben más asignaciones de ofertas y cuánto pesa cada una dentro de la demanda observada.

**Cómo leer el resultado.** `rank` ordena carreras por `ofertas`. `assignment_share = numerator_n / denominator_n` mide participación sobre asignaciones carrera-oferta, no sobre personas ni contrataciones.

**Advertencia semántica.** Una oferta dirigida expresa demanda declarada; no prueba inserción laboral.

#### Query general

**Alcance:** Una carrera por fila, máximo las 14 carreras.

```cypher
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

```cypher
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
```

**Resultado esperado.** La vista general devuelve hasta **14 filas** y la específica hasta **14 filas**. Con los parámetros anteriores, la ejecución verificada devolvió **3 filas** con estado **`available`**. Gráfico sugerido: **barras ordenadas**.

### 3. ¿En qué industrias se concentran las ofertas dirigidas a cada carrera?

**Qué busca mostrar.** La industria líder de cada carrera en la vista macro y la concentración industrial de una carrera al profundizar.

**Cómo leer el resultado.** `rank` ordena industrias por ofertas; `assignment_share` usa como denominador todas las asignaciones industria-oferta de la carrera. `empresas` da soporte adicional y `industrias_activas` solo aparece en la vista macro.

**Advertencia semántica.** Describe industrias de empresas publicadoras, no industrias donde trabajan egresados.

#### Query general

**Alcance:** Una industria líder por carrera, máximo 14 filas.

```cypher
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

```cypher
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
```

**Resultado esperado.** La vista general devuelve hasta **14 filas** y la específica hasta **10 filas**. Con los parámetros anteriores, la ejecución verificada devolvió **10 filas** con estado **`available`**. Gráfico sugerido: **barras con detalle**.

### 4. ¿Qué competencias, habilidades y herramientas aparecen más en las ofertas del contexto seleccionado?

**Qué busca mostrar.** Los conocimientos más repetidos en las ofertas, separados en competencias, habilidades y herramientas.

**Cómo leer el resultado.** `percentage = numerator_n / denominator_n`: ofertas que requieren el conocimiento sobre todas las ofertas del contexto. Una oferta puede exigir varios conocimientos, por lo que los porcentajes no tienen que sumar 100 %.

**Advertencia semántica.** La frecuencia en publicaciones no equivale a dominio personal ni importancia causal.

#### Query general

**Alcance:** Top 5 por dimensión, máximo 15 filas.

```cypher
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

```cypher
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
```

**Resultado esperado.** La vista general devuelve hasta **15 filas** y la específica hasta **20 filas**. Con los parámetros anteriores, la ejecución verificada devolvió **20 filas** con estado **`available`**. Gráfico sugerido: **barras ordenadas por pestañas**.

## Alineación curricular

### 5. Para la carrera seleccionada, ¿qué elementos tienen mayor cobertura curricular declarada?

**Qué busca mostrar.** La disponibilidad de información curricular y, para una carrera, qué conocimientos aparecen cubiertos por más cursos.

**Cómo leer el resultado.** `percentage = numerator_n / denominator_n`: cursos que cubren el conocimiento sobre los cursos de la carrera. Revise `availability`, `is_comparable` y `dimension_coverage_n` antes de comparar.

**Advertencia semántica.** Cobertura declarada no mide profundidad, calidad ni dominio del estudiante.

#### Query general

**Alcance:** Estado de disponibilidad de las 14 carreras.

```cypher
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
```

#### Query específica

**Parámetros de ejemplo verificados:**

```cypher
:param {
  carrera_id: "CAR_01375f53651cff38",
  tipo_conocimiento: "herramienta"
}
```

```cypher
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
```

**Resultado esperado.** La vista general devuelve hasta **14 filas** y la específica hasta **20 filas**. Con los parámetros anteriores, la ejecución verificada devolvió **20 filas** con estado **`available`**. Gráfico sugerido: **estado de cobertura y barras**.

### 6. ¿En qué elementos la demanda relativa supera más a la cobertura?

**Qué busca mostrar.** Los conocimientos cuya presencia relativa en ofertas supera su presencia relativa en cursos, para priorizar revisión curricular.

**Cómo leer el resultado.** `value = demand_percentage - coverage_percentage`. Un valor positivo prioriza una posible brecha. Los cuatro campos de numerador y denominador permiten auditar la comparación; `rank` no es una calificación académica.

**Advertencia semántica.** Es una señal de revisión sin umbral; dimensiones incompletas quedan excluidas.

#### Query general

**Alcance:** Top 20 diferencias entre contextos comparables.

```cypher
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

```cypher
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
```

**Resultado esperado.** La vista general devuelve hasta **20 filas** y la específica hasta **20 filas**. Con los parámetros anteriores, la ejecución verificada devolvió **20 filas** con estado **`available`**. Gráfico sugerido: **cuadrantes o barras agrupadas**.

### 7. ¿En cuáles la cobertura supera más a la demanda reciente?

**Qué busca mostrar.** Los conocimientos con mayor presencia curricular relativa que demanda reciente observada, como señal para investigar vigencia.

**Cómo leer el resultado.** `value = coverage_percentage - demand_percentage`. Un valor alto solo señala desalineación observada para revisión; no demuestra obsolescencia. `no_market_data` significa que no hubo base de mercado comparable.

**Advertencia semántica.** Poca demanda observada no prueba obsolescencia; sin mercado se devuelve estado.

#### Query general

**Alcance:** Top 20 diferencias entre contextos comparables.

```cypher
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

```cypher
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
```

**Resultado esperado.** La vista general devuelve hasta **20 filas** y la específica hasta **20 filas**. Con los parámetros anteriores, la ejecución verificada devolvió **20 filas** con estado **`available`**. Gráfico sugerido: **barras divergentes**.

### 8. ¿Qué cursos comparten más conocimientos con las ofertas del contexto seleccionado?

**Qué busca mostrar.** Los cursos que comparten más conocimientos con las ofertas del contexto, útiles para orientar contenidos o programas de prácticas.

**Cómo leer el resultado.** `value` es el número de ofertas únicas vinculadas mediante conocimientos compartidos. `conocimientos_compartidos` explica la amplitud del cruce y `denominator_n` da el universo de ofertas.

**Advertencia semántica.** La correspondencia no implica causalidad, calidad del curso ni contratación.

#### Query general

**Alcance:** Top 20 cursos de dimensiones comparables.

```cypher
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

```cypher
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
```

**Resultado esperado.** La vista general devuelve hasta **20 filas** y la específica hasta **20 filas**. Con los parámetros anteriores, la ejecución verificada devolvió **20 filas** con estado **`available`**. Gráfico sugerido: **barras ordenadas**.

## Empresas y funciones

### 9. ¿Qué empresas concentran las ofertas del contexto y qué conocimientos solicitan?

**Qué busca mostrar.** Las empresas que concentran publicaciones y el conocimiento más frecuente asociado a sus ofertas.

**Cómo leer el resultado.** `rank` ordena empresas por ofertas y `assignment_share` muestra su peso en las asignaciones del contexto. `conocimiento_lider` es el más frecuente para esa empresa, no su única demanda.

**Advertencia semántica.** Describe publicaciones de las empresas, no capacidades internas ni contrataciones.

#### Query general

**Alcance:** Top 20 empresas recientes.

```cypher
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

```cypher
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
```

**Resultado esperado.** La vista general devuelve hasta **20 filas** y la específica hasta **20 filas**. Con los parámetros anteriores, la ejecución verificada devolvió **20 filas** con estado **`available`**. Gráfico sugerido: **barras ordenadas con detalle**.

### 10. ¿Qué conocimientos aparecen proporcionalmente más en las ofertas de Empresa A que de Empresa B?

**Qué busca mostrar.** Los conocimientos proporcionalmente más frecuentes en Empresa A que en Empresa B, controlando por el volumen de ofertas de cada una.

**Cómo leer el resultado.** `difference_pp = empresa_a_percentage - empresa_b_percentage`; se muestran diferencias positivas para A. Compare también `numerator_n_*` y `denominator_n_*`: una diferencia grande con poco soporte es menos estable.

**Advertencia semántica.** Compara demanda publicada; ambas empresas deben existir y tener soporte.

#### Query general

**Alcance:** Top 20 lifts empresa-conocimiento con soporte mínimo 5.

```cypher
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

```cypher
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
```

**Resultado esperado.** La vista general devuelve hasta **20 filas** y la específica hasta **20 filas**. Con los parámetros anteriores, la ejecución verificada devolvió **20 filas** con estado **`available`**. Gráfico sugerido: **barras divergentes**.

### 11. ¿Qué conocimientos aparecen con mayor frecuencia en ofertas cuyos títulos tienen señal textual de liderazgo en una industria?

**Qué busca mostrar.** Qué conocimientos aparecen en ofertas cuyo título contiene señales textuales de liderazgo dentro de una industria.

**Cómo leer el resultado.** `percentage = numerator_n / denominator_n`: ofertas señaladas que requieren el conocimiento sobre todas las ofertas señaladas de la industria. `rank` expresa frecuencia, no importancia causal.

**Advertencia semántica.** Es una heurística por términos inequívocos del título, no una función normalizada.

#### Query general

**Alcance:** Top 20 industrias por títulos con señal textual.

```cypher
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

```cypher
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
```

**Resultado esperado.** La vista general devuelve hasta **20 filas** y la específica hasta **10 filas**. Con los parámetros anteriores, la ejecución verificada devolvió **10 filas** con estado **`available`**. Gráfico sugerido: **barras con profundización**.

### 12. ¿Cómo cambia la distribución de títulos de puesto para una carrera según el tipo de empresa?

**Qué busca mostrar.** Cómo se distribuyen los títulos publicados para una carrera entre los tipos de empresa disponibles en el grafo.

**Cómo leer el resultado.** `assignment_share = numerator_n / denominator_n` mide el peso del título dentro de su tipo de empresa. Los títulos se normalizan solo a minúsculas y espacios; variantes semánticas pueden permanecer separadas.

**Advertencia semántica.** No existe tamaño empresarial; Puesto.nombre es título publicado, no función normalizada.

#### Query general

**Alcance:** Hasta 4 tipos y 5 títulos por tipo, máximo 20 filas.

```cypher
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

```cypher
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
```

**Resultado esperado.** La vista general devuelve hasta **20 filas** y la específica hasta **20 filas**. Con los parámetros anteriores, la ejecución verificada devolvió **12 filas** con estado **`available`**. Gráfico sugerido: **barras agrupadas con profundización**.

## Evidencia de validación

| # | Consulta | `EXPLAIN` general | `EXPLAIN` específica | Ejecución específica | Filas |
|---:|---|---|---|---|---:|
| 1 | `tendencia_ofertas` | OK | OK | `available` | 12 |
| 2 | `carreras_con_mayor_demanda` | OK | OK | `available` | 3 |
| 3 | `industrias_por_carrera` | OK | OK | `available` | 10 |
| 4 | `conocimientos_mas_demandados` | OK | OK | `available` | 20 |
| 5 | `cobertura_curricular` | OK | OK | `available` | 20 |
| 6 | `brechas_demanda_alta` | OK | OK | `available` | 20 |
| 7 | `senales_revision_vigencia` | OK | OK | `available` | 20 |
| 8 | `cursos_con_mayor_correspondencia` | OK | OK | `available` | 20 |
| 9 | `empresas_y_conocimientos` | OK | OK | `available` | 20 |
| 10 | `diferenciadores_empresas` | OK | OK | `available` | 20 |
| 11 | `conocimientos_liderazgo` | OK | OK | `available` | 10 |
| 12 | `funciones_por_tipo_empresa` | OK | OK | `available` | 12 |

> [!NOTE]
> La query general de liderazgo contiene el carácter `$` dentro de una expresión regular como ancla de fin de texto. No es un parámetro; ninguna query general contiene referencias de la forma `$nombre`.

## Checklist antes de llevar una query al dashboard

- [ ] La query general se ejecuta sin parámetros y no contiene referencias `$nombre`.
- [ ] La query específica recibe exactamente los parámetros declarados en su bloque `:param`.
- [ ] El rango de fechas pertenece al dataset y no supera 20 buckets mensuales.
- [ ] `availability` permite interpretar la fila y `warning` está vacío o fue atendido.
- [ ] Numerador y denominador corresponden a la métrica mostrada.
- [ ] La cardinalidad respeta el límite del catálogo y es adecuada para el gráfico.
- [ ] La visualización no presenta ausencia de datos como cero.
- [ ] Las conclusiones respetan las limitaciones semánticas de la pregunta.

## Runner alternativo

Desde `backend/`, puede consultar el catálogo sin usar LangGraph ni OpenAI:

```powershell
python scripts/ejecutar_consultas_estrategicas.py --listar
```

Para imprimir una query exacta:

```powershell
python scripts/ejecutar_consultas_estrategicas.py `
  --consulta industrias_por_carrera `
  --vista general `
  --mostrar-query
```

Para imprimir la variante específica, cambie `--vista general` por `--vista especifica` y agregue todos los `--param CLAVE=VALOR` exigidos por la consulta.
