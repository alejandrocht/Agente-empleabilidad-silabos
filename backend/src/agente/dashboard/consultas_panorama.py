"""Consultas fijas de la sección Panorama laboral."""

from __future__ import annotations

from typing import Final

from agente.dashboard.consultas_modelo import ConsultaEstrategica, consulta

SECCION: Final = "Panorama laboral"

_TENDENCIA_GENERAL = """
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
"""

_TENDENCIA_ESPECIFICA = """
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
"""

_CARRERAS_GENERAL = """
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
"""

_CARRERAS_ESPECIFICA = """
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
"""

_INDUSTRIAS_GENERAL = """
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
"""

_INDUSTRIAS_ESPECIFICA = """
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
"""

_CONOCIMIENTOS_GENERAL = """
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
"""

_CONOCIMIENTOS_ESPECIFICA = """
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
"""

CONSULTAS_PANORAMA: Final[tuple[ConsultaEstrategica, ...]] = (
    consulta(
        seccion=SECCION,
        slug="tendencia_ofertas",
        pregunta="¿Cómo cambia mes a mes la cantidad de ofertas publicadas?",
        definicion_medible=(
            "Serie mensual de ofertas únicas; el macro usa los últimos 12 meses con datos."
        ),
        limitacion_semantica="Mide publicaciones, no contrataciones ni empleo efectivo.",
        cypher_general=_TENDENCIA_GENERAL,
        cypher_especifica=_TENDENCIA_ESPECIFICA,
        parametros_especificos=("carrera_id", "industria_id", "desde", "hasta"),
        granularidad_general="Un mes por fila, máximo 12 meses.",
        granularidad_especifica="Un mes por fila para carrera, industria y período.",
        metrica_principal="Ofertas únicas publicadas.",
        limite_general=12,
        limite_especifico=20,
        chart_hint="line",
        requiere_curricula=False,
        salidas_general=(
            "periodo_id", "periodo", "value", "ofertas", "numerator_n",
            "denominator_n", "availability",
        ),
        salidas_especifica=(
            "carrera_id", "industria_id", "periodo_id", "periodo", "value",
            "ofertas", "numerator_n", "denominator_n", "availability",
        ),
    ),
    consulta(
        seccion=SECCION,
        slug="carreras_con_mayor_demanda",
        pregunta="¿Qué carreras concentran más ofertas dirigidas?",
        definicion_medible="Ranking por ofertas únicas dirigidas y participación del total.",
        limitacion_semantica=(
            "Una oferta dirigida expresa demanda declarada; no prueba inserción laboral."
        ),
        cypher_general=_CARRERAS_GENERAL,
        cypher_especifica=_CARRERAS_ESPECIFICA,
        parametros_especificos=("facultad_id", "industria_id", "desde", "hasta"),
        granularidad_general="Una carrera por fila, máximo las 14 carreras.",
        granularidad_especifica="Carreras de una facultad e industria en el período.",
        metrica_principal="Ofertas únicas dirigidas.",
        limite_general=14,
        limite_especifico=14,
        chart_hint="ranked_bar",
        requiere_curricula=False,
        salidas_general=(
            "carrera_id", "carrera", "value", "ofertas", "assignment_share", "rank",
            "numerator_n", "denominator_n", "total_assignments", "availability",
        ),
        salidas_especifica=(
            "facultad_id", "facultad", "industria_id", "industria", "carrera_id",
            "carrera", "value", "ofertas", "assignment_share", "rank", "numerator_n",
            "denominator_n", "total_assignments", "availability",
        ),
    ),
    consulta(
        seccion=SECCION,
        slug="industrias_por_carrera",
        pregunta="¿En qué industrias se concentran las ofertas dirigidas a cada carrera?",
        definicion_medible=(
            "Industria líder por carrera en macro y top 10 de industrias en detalle."
        ),
        limitacion_semantica=(
            "Describe industrias de empresas publicadoras, no industrias donde trabajan egresados."
        ),
        cypher_general=_INDUSTRIAS_GENERAL,
        cypher_especifica=_INDUSTRIAS_ESPECIFICA,
        parametros_especificos=("carrera_id", "desde", "hasta"),
        granularidad_general="Una industria líder por carrera, máximo 14 filas.",
        granularidad_especifica="Top 10 industrias de una carrera.",
        metrica_principal="Ofertas únicas por industria.",
        limite_general=14,
        limite_especifico=10,
        chart_hint="bar_drilldown",
        requiere_curricula=False,
        salidas_general=(
            "carrera_id",
            "carrera",
            "industria_id",
            "industria",
            "value",
            "ofertas",
            "empresas",
            "assignment_share",
            "rank",
            "numerator_n",
            "denominator_n",
            "total_assignments",
            "availability",
            "industrias_activas",
        ),
        salidas_especifica=(
            "carrera_id",
            "carrera",
            "industria_id",
            "industria",
            "value",
            "ofertas",
            "empresas",
            "assignment_share",
            "rank",
            "numerator_n",
            "denominator_n",
            "total_assignments",
            "availability",
        ),
    ),
    consulta(
        seccion=SECCION,
        slug="conocimientos_mas_demandados",
        pregunta=(
            "¿Qué competencias, habilidades y herramientas aparecen más en las ofertas "
            "del contexto seleccionado?"
        ),
        definicion_medible=(
            "Top 5 por dimensión en macro y top 20 de la dimensión seleccionada en detalle."
        ),
        limitacion_semantica=(
            "La frecuencia en publicaciones no equivale a dominio personal ni importancia causal."
        ),
        cypher_general=_CONOCIMIENTOS_GENERAL,
        cypher_especifica=_CONOCIMIENTOS_ESPECIFICA,
        parametros_especificos=(
            "carrera_id",
            "industria_id",
            "tipo_conocimiento",
            "desde",
            "hasta",
        ),
        granularidad_general="Top 5 por dimensión, máximo 15 filas.",
        granularidad_especifica="Top 20 de una dimensión y contexto seleccionados.",
        metrica_principal="Ofertas únicas que requieren el conocimiento.",
        limite_general=15,
        limite_especifico=20,
        chart_hint="ranked_bar_tabs",
        requiere_curricula=False,
        salidas_general=(
            "conocimiento_id",
            "conocimiento",
            "dimension",
            "value",
            "ofertas",
            "percentage",
            "rank",
            "numerator_n",
            "denominator_n",
            "availability",
        ),
        salidas_especifica=(
            "carrera_id",
            "carrera",
            "industria_id",
            "industria",
            "conocimiento_id",
            "conocimiento",
            "dimension",
            "value",
            "ofertas",
            "percentage",
            "rank",
            "numerator_n",
            "denominator_n",
            "availability",
        ),
    ),
)
