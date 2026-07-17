"""Plantillas Cypher cerradas para las métricas del dashboard CIAR.

Las interpolaciones de esta capa se limitan a metadatos definidos en el código
(labels, propiedades y relaciones). Los valores que llegan por HTTP se pasan
siempre como parámetros del driver de Neo4j.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Dimension:
    """Describe un vocabulario comparable entre currículo y mercado."""

    slug: str
    etiqueta: str
    id_propiedad: str
    nombre_propiedad: str
    relacion_curricular: str
    etiqueta_visible: str


DIMENSIONES: Final[dict[str, Dimension]] = {
    "competencias": Dimension(
        slug="competencias",
        etiqueta="Competencia",
        id_propiedad="id_competencia",
        nombre_propiedad="nombre_competencia",
        relacion_curricular="CUBRE",
        etiqueta_visible="Competencias",
    ),
    "habilidades": Dimension(
        slug="habilidades",
        etiqueta="Habilidad",
        id_propiedad="id_habilidad",
        nombre_propiedad="nombre_habilidad",
        relacion_curricular="ENSENIA",
        etiqueta_visible="Habilidades",
    ),
    "herramientas": Dimension(
        slug="herramientas",
        etiqueta="Herramienta",
        id_propiedad="id_herramienta",
        nombre_propiedad="nombre_herramienta",
        relacion_curricular="ENSENIA",
        etiqueta_visible="Herramientas",
    ),
}


CONSULTA_CARRERAS: Final[str] = """
MATCH (ca:Carrera)
WHERE ca.id_carrera IS NOT NULL AND ca.nombre_carrera IS NOT NULL
OPTIONAL MATCH (ca)-[:ENSENIA]-(cu:Curso)
RETURN ca.id_carrera AS id,
       ca.nombre_carrera AS nombre,
       count(DISTINCT cu) AS cursos_conectados
ORDER BY nombre
"""

CONSULTA_CARRERA: Final[str] = """
MATCH (ca:Carrera {id_carrera: $carrera_id})
OPTIONAL MATCH (ca)-[:ENSENIA]-(cu:Curso)
RETURN ca.id_carrera AS id,
       ca.nombre_carrera AS nombre,
       count(DISTINCT cu) AS cursos_conectados
"""

CONSULTA_TENDENCIA_GLOBAL: Final[str] = """
MATCH (o:Oferta_Laboral)
WHERE o.fecha_publicacion >= datetime($desde)
  AND o.fecha_publicacion < datetime($hasta)
RETURN o.fecha_publicacion.year AS anio,
       o.fecha_publicacion.month AS mes,
       count(DISTINCT o) AS ofertas
ORDER BY anio, mes
"""

CONSULTA_RANGO_OFERTAS: Final[str] = """
MATCH (o:Oferta_Laboral)
WHERE o.fecha_publicacion IS NOT NULL
RETURN min(o.fecha_publicacion) AS desde,
       max(o.fecha_publicacion) AS hasta
"""

CONSULTA_TENDENCIA_CARRERA: Final[str] = """
MATCH (ca:Carrera {id_carrera: $carrera_id})-[:DIRIGE_A]-(o:Oferta_Laboral)
WHERE o.fecha_publicacion >= datetime($desde)
  AND o.fecha_publicacion < datetime($hasta)
RETURN o.fecha_publicacion.year AS anio,
       o.fecha_publicacion.month AS mes,
       count(DISTINCT o) AS ofertas
ORDER BY anio, mes
"""


def _consulta_demanda(dimension: Dimension) -> str:
    return f"""
MATCH (ca:Carrera {{id_carrera: $carrera_id}})-[:DIRIGE_A]-(o:Oferta_Laboral)
      -[:TIENE]-(r:Requerimiento_Laboral)-[:REQUIERE]-(elemento:{dimension.etiqueta})
WHERE o.fecha_publicacion >= datetime($desde)
  AND o.fecha_publicacion < datetime($hasta)
RETURN elemento.{dimension.id_propiedad} AS id,
       elemento.{dimension.nombre_propiedad} AS elemento,
       count(DISTINCT o) AS ofertas
ORDER BY ofertas DESC, elemento
LIMIT $limite
"""


def _consulta_cobertura(dimension: Dimension) -> str:
    return f"""
MATCH (ca:Carrera {{id_carrera: $carrera_id}})-[:ENSENIA]-(curso_total:Curso)
WITH ca, count(DISTINCT curso_total) AS total_cursos
MATCH (ca)-[:ENSENIA]-(curso:Curso)-[:TIENE]-(cobertura:Cobertura_Curricular)
      -[:{dimension.relacion_curricular}]-(elemento:{dimension.etiqueta})
RETURN elemento.{dimension.id_propiedad} AS id,
       elemento.{dimension.nombre_propiedad} AS elemento,
       count(DISTINCT curso) AS cursos_con_cobertura,
       total_cursos
ORDER BY cursos_con_cobertura DESC, elemento
LIMIT $limite
"""


def _consulta_brechas(dimension: Dimension) -> str:
    return f"""
MATCH (ca:Carrera {{id_carrera: $carrera_id}})
OPTIONAL MATCH (ca)-[:DIRIGE_A]-(oferta_total:Oferta_Laboral)
WHERE oferta_total.fecha_publicacion >= datetime($desde)
  AND oferta_total.fecha_publicacion < datetime($hasta)
WITH ca, count(DISTINCT oferta_total) AS total_ofertas
OPTIONAL MATCH (ca)-[:ENSENIA]-(curso_total:Curso)
WITH ca, total_ofertas, count(DISTINCT curso_total) AS total_cursos
MATCH (elemento:{dimension.etiqueta})
OPTIONAL MATCH (ca)-[:ENSENIA]-(curso_cobertura:Curso)-[:TIENE]
               -(cobertura:Cobertura_Curricular)-[:{dimension.relacion_curricular}]-(elemento)
WITH ca, elemento, total_cursos, total_ofertas,
     count(DISTINCT curso_cobertura) AS cursos_con_cobertura
OPTIONAL MATCH (ca)-[:DIRIGE_A]-(oferta_requerida:Oferta_Laboral)-[:TIENE]
               -(requerimiento:Requerimiento_Laboral)-[:REQUIERE]-(elemento)
WHERE oferta_requerida.fecha_publicacion >= datetime($desde)
  AND oferta_requerida.fecha_publicacion < datetime($hasta)
WITH elemento, total_cursos, total_ofertas, cursos_con_cobertura,
     count(DISTINCT oferta_requerida) AS ofertas_que_requieren
WHERE cursos_con_cobertura > 0 OR ofertas_que_requieren > 0
WITH elemento, total_cursos, total_ofertas, cursos_con_cobertura,
     ofertas_que_requieren,
     CASE WHEN total_cursos = 0 THEN 0.0
          ELSE toFloat(cursos_con_cobertura) / total_cursos END AS cobertura,
     CASE WHEN total_ofertas = 0 THEN 0.0
          ELSE toFloat(ofertas_que_requieren) / total_ofertas END AS demanda
RETURN elemento.{dimension.id_propiedad} AS id,
       elemento.{dimension.nombre_propiedad} AS elemento,
       cursos_con_cobertura,
       total_cursos,
       ofertas_que_requieren,
       total_ofertas,
       cobertura,
       demanda,
       demanda - cobertura AS brecha
ORDER BY brecha DESC, ofertas_que_requieren DESC, elemento
LIMIT $limite
"""


def _consulta_industrias(dimension: Dimension) -> str:
    return f"""
MATCH (industria:Industria)-[:AGRUPA]-(empresa:Empresa)-[:PUBLICA]-(oferta:Oferta_Laboral)
      -[:TIENE]-(requerimiento:Requerimiento_Laboral)-[:REQUIERE]-
      (elemento:{dimension.etiqueta} {{{dimension.id_propiedad}: $elemento_id}})
WHERE oferta.fecha_publicacion >= datetime($desde)
  AND oferta.fecha_publicacion < datetime($hasta)
RETURN industria.nombre AS industria,
       count(DISTINCT oferta) AS ofertas
ORDER BY ofertas DESC, industria
LIMIT $limite
"""


CONSULTAS_DEMANDA: Final[dict[str, str]] = {
    slug: _consulta_demanda(dimension) for slug, dimension in DIMENSIONES.items()
}
CONSULTAS_COBERTURA: Final[dict[str, str]] = {
    slug: _consulta_cobertura(dimension) for slug, dimension in DIMENSIONES.items()
}
CONSULTAS_BRECHAS: Final[dict[str, str]] = {
    slug: _consulta_brechas(dimension) for slug, dimension in DIMENSIONES.items()
}
CONSULTAS_INDUSTRIAS: Final[dict[str, str]] = {
    slug: _consulta_industrias(dimension) for slug, dimension in DIMENSIONES.items()
}


def todas_las_plantillas() -> dict[str, str]:
    """Devuelve cada Cypher estático para validarlo una vez al iniciar el servicio."""

    plantillas = {
        "dashboard_catalogo_carreras": CONSULTA_CARRERAS,
        "dashboard_carrera": CONSULTA_CARRERA,
        "dashboard_rango_ofertas": CONSULTA_RANGO_OFERTAS,
        "dashboard_ofertas_por_mes": CONSULTA_TENDENCIA_GLOBAL,
        "dashboard_ofertas_por_mes_carrera": CONSULTA_TENDENCIA_CARRERA,
    }
    for slug in DIMENSIONES:
        plantillas[f"dashboard_demanda_{slug}"] = CONSULTAS_DEMANDA[slug]
        plantillas[f"dashboard_cobertura_{slug}"] = CONSULTAS_COBERTURA[slug]
        plantillas[f"dashboard_brechas_{slug}"] = CONSULTAS_BRECHAS[slug]
        plantillas[f"dashboard_industrias_{slug}"] = CONSULTAS_INDUSTRIAS[slug]
    return plantillas
