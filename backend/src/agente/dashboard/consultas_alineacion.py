"""Consultas fijas de la sección Alineación curricular."""

from __future__ import annotations

from typing import Final

from agente.dashboard.consultas_modelo import ConsultaEstrategica, consulta

SECCION: Final = "Alineación curricular"

_DISPONIBILIDAD_GENERAL = """
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
"""

_COBERTURA_ESPECIFICA = """
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
"""

_BRECHAS_GENERAL = """
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
"""

_BRECHAS_ESPECIFICA = """
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
"""

_VIGENCIA_GENERAL = """
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
"""

def _crear_vigencia_especifica() -> str:
    """Deriva A3 con universo curricular, separado del universo combinado de A2."""

    inicio_busqueda = _BRECHAS_ESPECIFICA.index("OPTIONAL MATCH (x)")
    inicio_universo = _BRECHAS_ESPECIFICA.index("  AND (\n    EXISTS {", inicio_busqueda)
    fin_universo = _BRECHAS_ESPECIFICA.index(
        "\nOPTIONAL MATCH (x)-[:REQUIERE]", inicio_universo
    )
    universo_curricular = """  AND EXISTS {
    MATCH (ca)-[:ENSENIA]-(:Curso)-[:TIENE]
          -(:Cobertura_Curricular)-[rel:CUBRE|ENSENIA]-(x)
    WHERE (x:Competencia AND type(rel) = 'CUBRE')
       OR ((x:Habilidad OR x:Herramienta) AND type(rel) = 'ENSENIA')
  }"""
    cypher = (
        _BRECHAS_ESPECIFICA[:inicio_universo]
        + universo_curricular
        + _BRECHAS_ESPECIFICA[fin_universo:]
    )
    return cypher.replace("demanda - cobertura", "cobertura - demanda")


_VIGENCIA_ESPECIFICA = _crear_vigencia_especifica()

_CURSOS_GENERAL = """
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
"""

_CURSOS_ESPECIFICA = """
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
"""

_PARAMETROS_CONTEXTO: Final = (
    "carrera_id",
    "industria_id",
    "tipo_conocimiento",
    "desde",
    "hasta",
)

CONSULTAS_ALINEACION: Final[tuple[ConsultaEstrategica, ...]] = (
    consulta(
        seccion=SECCION,
        slug="cobertura_curricular",
        pregunta=(
            "Para la carrera seleccionada, ¿qué elementos tienen mayor cobertura "
            "curricular declarada?"
        ),
        definicion_medible=(
            "Disponibilidad por carrera en macro y top 20 por proporción de cursos en detalle."
        ),
        limitacion_semantica=(
            "Cobertura declarada no mide profundidad, calidad ni dominio del estudiante."
        ),
        cypher_general=_DISPONIBILIDAD_GENERAL,
        cypher_especifica=_COBERTURA_ESPECIFICA,
        parametros_especificos=("carrera_id", "tipo_conocimiento"),
        granularidad_general="Estado de disponibilidad de las 14 carreras.",
        granularidad_especifica="Top 20 elementos cubiertos por una carrera.",
        metrica_principal="Cursos con cobertura válida en la dimensión seleccionada.",
        limite_general=14,
        limite_especifico=20,
        chart_hint="coverage_status_then_bar",
        requiere_curricula=True,
        salidas_general=(
            "carrera_id", "carrera", "value", "numerator_n", "denominator_n",
            "coberturas_competencia", "coberturas_habilidad", "coberturas_herramienta",
            "competencia_comparable", "habilidad_comparable", "herramienta_comparable",
            "availability", "has_any_comparable_dimension", "warning",
        ),
        salidas_especifica=(
            "carrera_id", "carrera", "conocimiento_id", "conocimiento", "dimension",
            "value", "percentage", "rank", "numerator_n", "denominator_n",
            "dimension_coverage_n", "availability", "is_comparable", "warning",
        ),
    ),
    consulta(
        seccion=SECCION,
        slug="brechas_demanda_alta",
        pregunta="¿En qué elementos la demanda relativa supera más a la cobertura?",
        definicion_medible=(
            "Ranking por diferencia entre proporción de ofertas y proporción de cursos."
        ),
        limitacion_semantica=(
            "Es una señal de revisión sin umbral; dimensiones incompletas quedan excluidas."
        ),
        cypher_general=_BRECHAS_GENERAL,
        cypher_especifica=_BRECHAS_ESPECIFICA,
        parametros_especificos=_PARAMETROS_CONTEXTO,
        granularidad_general="Top 20 diferencias entre contextos comparables.",
        granularidad_especifica="Top 20 diferencias para carrera, industria y dimensión.",
        metrica_principal="Índice de demanda menos índice de cobertura.",
        limite_general=20,
        limite_especifico=20,
        chart_hint="quadrant_or_grouped_bar",
        requiere_curricula=True,
        salidas_general=(
            "carrera_id", "carrera", "conocimiento_id", "conocimiento", "dimension",
            "value", "demand_percentage", "coverage_percentage", "demand_numerator_n",
            "demand_denominator_n", "coverage_numerator_n", "coverage_denominator_n",
            "rank", "availability", "is_comparable", "total_carreras",
        ),
        salidas_especifica=(
            "carrera_id", "carrera", "industria_id", "industria", "conocimiento_id",
            "conocimiento", "dimension", "value", "demand_percentage",
            "coverage_percentage", "demand_numerator_n", "demand_denominator_n",
            "coverage_numerator_n", "coverage_denominator_n", "rank",
            "dimension_coverage_n", "availability", "is_comparable", "warning",
        ),
    ),
    consulta(
        seccion=SECCION,
        slug="senales_revision_vigencia",
        pregunta="¿En cuáles la cobertura supera más a la demanda reciente?",
        definicion_medible=(
            "Ranking, sin umbral, por proporción de cursos menos proporción de ofertas recientes."
        ),
        limitacion_semantica=(
            "Poca demanda observada no prueba obsolescencia; sin mercado se devuelve estado."
        ),
        cypher_general=_VIGENCIA_GENERAL,
        cypher_especifica=_VIGENCIA_ESPECIFICA,
        parametros_especificos=_PARAMETROS_CONTEXTO,
        granularidad_general="Top 20 diferencias entre contextos comparables.",
        granularidad_especifica="Top 20 diferencias o un estado no_market_data.",
        metrica_principal="Índice de cobertura menos índice de demanda reciente.",
        limite_general=20,
        limite_especifico=20,
        chart_hint="diverging_bar",
        requiere_curricula=True,
        salidas_general=(
            "carrera_id", "carrera", "conocimiento_id", "conocimiento", "dimension",
            "value", "demand_percentage", "coverage_percentage", "demand_numerator_n",
            "demand_denominator_n", "coverage_numerator_n", "coverage_denominator_n",
            "rank", "availability", "is_comparable", "total_carreras",
        ),
        salidas_especifica=(
            "carrera_id", "carrera", "industria_id", "industria", "conocimiento_id",
            "conocimiento", "dimension", "value", "demand_percentage",
            "coverage_percentage", "demand_numerator_n", "demand_denominator_n",
            "coverage_numerator_n", "coverage_denominator_n", "rank",
            "dimension_coverage_n", "availability", "is_comparable", "warning",
        ),
    ),
    consulta(
        seccion=SECCION,
        slug="cursos_con_mayor_correspondencia",
        pregunta=(
            "¿Qué cursos comparten más conocimientos con las ofertas del contexto seleccionado?"
        ),
        definicion_medible=(
            "Top 20 cursos por ofertas únicas relacionadas y conocimientos compartidos."
        ),
        limitacion_semantica=(
            "La correspondencia no implica causalidad, calidad del curso ni contratación."
        ),
        cypher_general=_CURSOS_GENERAL,
        cypher_especifica=_CURSOS_ESPECIFICA,
        parametros_especificos=_PARAMETROS_CONTEXTO,
        granularidad_general="Top 20 cursos de dimensiones comparables.",
        granularidad_especifica="Top 20 cursos o un estado de indisponibilidad.",
        metrica_principal="Ofertas únicas que comparten conocimientos con el curso.",
        limite_general=20,
        limite_especifico=20,
        chart_hint="ranked_bar",
        requiere_curricula=True,
        salidas_general=(
            "carrera_id", "carrera", "curso_id", "curso", "value", "ofertas",
            "conocimientos_compartidos", "assignment_share", "rank", "numerator_n",
            "denominator_n", "total_assignments", "carreras_perfiladas", "total_carreras",
            "availability", "coverage_percentage", "is_comparable",
        ),
        salidas_especifica=(
            "carrera_id", "carrera", "industria_id", "industria", "curso_id", "curso",
            "dimension", "value", "numerator_n", "denominator_n",
            "conocimientos_compartidos", "rank", "dimension_coverage_n", "availability",
            "is_comparable", "warning",
        ),
    ),
)
