"""Consultas fijas de la sección Empresas y funciones."""

from __future__ import annotations

from typing import Final

from agente.dashboard.consultas_modelo import ConsultaEstrategica, consulta

SECCION: Final = "Empresas y funciones"
_LIDERAZGO_REGEX: Final = (
    "(?i).*(^|[^a-záéíóúüñ0-9])"
    "(jefe|gerente|director|directora|líder|lider|supervisor|supervisora|"
    "chief|head of|team lead)"
    "($|[^a-záéíóúüñ0-9]).*"
)

_EMPRESAS_GENERAL = """
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
"""

_EMPRESAS_ESPECIFICA = """
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
"""

_DIFERENCIADORES_GENERAL = """
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
"""

_DIFERENCIADORES_ESPECIFICA = """
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
"""

_LIDERAZGO_GENERAL = """
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
  AND p.nombre =~ '__LIDERAZGO_REGEX__'
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
""".replace("__LIDERAZGO_REGEX__", _LIDERAZGO_REGEX)

_LIDERAZGO_ESPECIFICA = """
MATCH (i:Industria)
WHERE i.id_industria = $industria_id
OPTIONAL MATCH (i)-[:AGRUPA]-(:Empresa)-[:PUBLICA]-(o_total:Oferta_Laboral)
               -[:OFRECE]-(p_total:Puesto)
WHERE o_total.fecha_publicacion >= datetime($desde)
  AND o_total.fecha_publicacion < datetime($hasta)
  AND p_total.nombre =~ '__LIDERAZGO_REGEX__'
WITH i, count(DISTINCT o_total) AS total_liderazgo
WITH i, total_liderazgo,
     CASE WHEN total_liderazgo = 0 THEN 'no_data' ELSE 'available' END AS availability
OPTIONAL MATCH (i)-[:AGRUPA]-(:Empresa)-[:PUBLICA]-(o:Oferta_Laboral)
               -[:OFRECE]-(p:Puesto),
               (o)-[:TIENE]-(:Requerimiento_Laboral)-[:REQUIERE]-(x)
WHERE availability = 'available'
  AND o.fecha_publicacion >= datetime($desde)
  AND o.fecha_publicacion < datetime($hasta)
  AND p.nombre =~ '__LIDERAZGO_REGEX__'
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
""".replace("__LIDERAZGO_REGEX__", _LIDERAZGO_REGEX)

_FUNCIONES_GENERAL = """
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
"""

_FUNCIONES_ESPECIFICA = """
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
"""

CONSULTAS_EMPRESAS: Final[tuple[ConsultaEstrategica, ...]] = (
    consulta(
        seccion=SECCION,
        slug="empresas_y_conocimientos",
        pregunta=(
            "¿Qué empresas concentran las ofertas del contexto y qué conocimientos solicitan?"
        ),
        definicion_medible="Top 20 empresas y su conocimiento más frecuente.",
        limitacion_semantica=(
            "Describe publicaciones de las empresas, no capacidades internas ni contrataciones."
        ),
        cypher_general=_EMPRESAS_GENERAL,
        cypher_especifica=_EMPRESAS_ESPECIFICA,
        parametros_especificos=("carrera_id", "industria_id", "desde", "hasta"),
        granularidad_general="Top 20 empresas recientes.",
        granularidad_especifica="Top 20 empresas para carrera, industria y período.",
        metrica_principal="Ofertas únicas publicadas por empresa.",
        limite_general=20,
        limite_especifico=20,
        chart_hint="ranked_bar_with_detail",
        requiere_curricula=False,
        salidas_general=(
            "empresa_id", "empresa", "conocimiento_id", "conocimiento_lider", "value",
            "ofertas", "ofertas_con_conocimiento_lider", "assignment_share", "rank",
            "numerator_n", "denominator_n", "total_assignments", "availability",
        ),
        salidas_especifica=(
            "carrera_id", "carrera", "industria_id", "industria", "empresa_id", "empresa",
            "conocimiento_id", "conocimiento_lider", "value", "ofertas",
            "ofertas_con_conocimiento_lider", "assignment_share", "rank", "numerator_n",
            "denominator_n", "total_assignments", "availability",
        ),
    ),
    consulta(
        seccion=SECCION,
        slug="diferenciadores_empresas",
        pregunta=(
            "¿Qué conocimientos aparecen proporcionalmente más en las ofertas de Empresa A "
            "que de Empresa B?"
        ),
        definicion_medible=(
            "Lift con soporte mínimo en macro; diferencias positivas A−B en detalle."
        ),
        limitacion_semantica=(
            "Compara demanda publicada; ambas empresas deben existir y tener soporte."
        ),
        cypher_general=_DIFERENCIADORES_GENERAL,
        cypher_especifica=_DIFERENCIADORES_ESPECIFICA,
        parametros_especificos=("empresa_a_id", "empresa_b_id", "desde", "hasta"),
        granularidad_general="Top 20 lifts empresa-conocimiento con soporte mínimo 5.",
        granularidad_especifica="Top 20 diferencias positivas entre dos empresas.",
        metrica_principal="Lift general y diferencia de proporciones A−B específica.",
        limite_general=20,
        limite_especifico=20,
        chart_hint="diverging_bar",
        requiere_curricula=False,
        salidas_general=(
            "empresa_id", "empresa", "conocimiento_id", "conocimiento", "value", "lift",
            "numerator_n", "denominator_n", "global_numerator_n", "global_denominator_n",
            "rank", "availability", "minimum_support_n",
        ),
        salidas_especifica=(
            "empresa_a_id", "empresa_a", "empresa_b_id", "empresa_b", "conocimiento_id",
            "conocimiento", "dimension", "value", "empresa_a_percentage",
            "empresa_b_percentage", "difference_pp", "numerator_n_a", "denominator_n_a",
            "numerator_n_b", "denominator_n_b", "rank", "availability", "warning",
        ),
    ),
    consulta(
        seccion=SECCION,
        slug="conocimientos_liderazgo",
        pregunta=(
            "¿Qué conocimientos aparecen con mayor frecuencia en ofertas cuyos títulos "
            "tienen señal textual de liderazgo en una industria?"
        ),
        definicion_medible=(
            "Industrias con más títulos señalados y top 10 conocimientos al seleccionar una."
        ),
        limitacion_semantica=(
            "Es una heurística por términos inequívocos del título, no una función normalizada."
        ),
        cypher_general=_LIDERAZGO_GENERAL,
        cypher_especifica=_LIDERAZGO_ESPECIFICA,
        parametros_especificos=("industria_id", "desde", "hasta"),
        granularidad_general="Top 20 industrias por títulos con señal textual.",
        granularidad_especifica="Top 10 conocimientos de los títulos señalados.",
        metrica_principal="Ofertas con título que contiene una señal textual de liderazgo.",
        limite_general=20,
        limite_especifico=10,
        chart_hint="ranked_bar_drilldown",
        requiere_curricula=False,
        salidas_general=(
            "industria_id", "industria", "value", "titulos_con_senal_liderazgo",
            "percentage", "rank", "numerator_n", "denominator_n", "availability",
        ),
        salidas_especifica=(
            "industria_id", "industria", "conocimiento_id", "conocimiento", "dimension",
            "value", "ofertas", "percentage", "rank", "numerator_n", "denominator_n",
            "availability",
        ),
    ),
    consulta(
        seccion=SECCION,
        slug="funciones_por_tipo_empresa",
        pregunta=(
            "¿Cómo cambia la distribución de títulos de puesto para una carrera según "
            "el tipo de empresa?"
        ),
        definicion_medible=(
            "Hasta 4 tipos con mayor soporte y top 5 títulos elegibles por tipo."
        ),
        limitacion_semantica=(
            "No existe tamaño empresarial; Puesto.nombre es título publicado, "
            "no función normalizada."
        ),
        cypher_general=_FUNCIONES_GENERAL,
        cypher_especifica=_FUNCIONES_ESPECIFICA,
        parametros_especificos=("carrera_id", "desde", "hasta"),
        granularidad_general="Hasta 4 tipos y 5 títulos por tipo, máximo 20 filas.",
        granularidad_especifica="Hasta 4 tipos y 5 títulos por tipo, máximo 20 filas.",
        metrica_principal="Ofertas únicas por tipo y título publicado no vacío.",
        limite_general=20,
        limite_especifico=20,
        chart_hint="grouped_bar_drilldown",
        requiere_curricula=False,
        salidas_general=(
            "tipo_empresa_id", "tipo_empresa", "titulo_publicado", "value", "ofertas",
            "assignment_share", "rank", "numerator_n", "denominator_n",
            "total_assignments", "availability",
        ),
        salidas_especifica=(
            "carrera_id", "carrera", "tipo_empresa_id", "tipo_empresa", "titulo_publicado",
            "value", "ofertas", "assignment_share", "rank", "numerator_n",
            "denominator_n", "total_assignments", "availability",
        ),
    ),
)

