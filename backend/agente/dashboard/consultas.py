"""Immutable dashboard queries restricted to the current CIAR graph schema."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final


@dataclass(frozen=True, slots=True)
class DashboardQuery:
    """One allow-listed query and its exact parameter contract."""

    id: str
    cypher: str
    required_parameters: tuple[str, ...]


def _query(query_id: str, cypher: str, *parameters: str) -> DashboardQuery:
    return DashboardQuery(query_id, cypher.strip(), parameters)


DIMENSIONS: Final[dict[str, tuple[str, str, str]]] = {
    "competencias": ("Competencia", "id_competencia", "nombre_competencia"),
    "habilidades": ("Habilidad", "id_habilidad", "nombre_habilidad"),
    "herramientas": ("Herramienta", "id_herramienta", "nombre_herramienta"),
}


_QUERIES: dict[str, DashboardQuery] = {
    "dashboard_carreras": _query(
        "dashboard_carreras",
        """
        MATCH (ca:Carrera)
        WHERE ca.id_carrera IS NOT NULL AND ca.nombre_carrera IS NOT NULL
        OPTIONAL MATCH (ca)-[:ENSENIA]-(cu:Curso)
        RETURN ca.id_carrera AS id,
               ca.nombre_carrera AS nombre,
               count(DISTINCT cu) AS cursos_conectados
        ORDER BY nombre
        LIMIT 100
        """,
    ),
    "dashboard_carrera": _query(
        "dashboard_carrera",
        """
        MATCH (ca:Carrera {id_carrera: $carrera_id})
        OPTIONAL MATCH (ca)-[:ENSENIA]-(cu:Curso)
        RETURN ca.id_carrera AS id,
               ca.nombre_carrera AS nombre,
               count(DISTINCT cu) AS cursos_conectados
        LIMIT 1
        """,
        "carrera_id",
    ),
    "dashboard_rango_ofertas": _query(
        "dashboard_rango_ofertas",
        """
        MATCH (o:Oferta_Laboral)
        WHERE o.fecha_publicacion IS NOT NULL
        RETURN min(o.fecha_publicacion) AS desde,
               max(o.fecha_publicacion) AS hasta
        LIMIT 1
        """,
    ),
    "dashboard_tendencia_global": _query(
        "dashboard_tendencia_global",
        """
        MATCH (o:Oferta_Laboral)
        WHERE o.fecha_publicacion IS NOT NULL
          AND date(o.fecha_publicacion) >= date($desde)
          AND date(o.fecha_publicacion) < date($hasta)
        RETURN o.fecha_publicacion.year AS anio,
               o.fecha_publicacion.month AS mes,
               count(DISTINCT o) AS ofertas
        ORDER BY anio, mes
        LIMIT 100
        """,
        "desde",
        "hasta",
    ),
    "dashboard_tendencia_carrera": _query(
        "dashboard_tendencia_carrera",
        """
        MATCH (ca:Carrera {id_carrera: $carrera_id})-[:DIRIGE_A]-(o:Oferta_Laboral)
        WHERE o.fecha_publicacion IS NOT NULL
          AND date(o.fecha_publicacion) >= date($desde)
          AND date(o.fecha_publicacion) < date($hasta)
        RETURN o.fecha_publicacion.year AS anio,
               o.fecha_publicacion.month AS mes,
               count(DISTINCT o) AS ofertas
        ORDER BY anio, mes
        LIMIT 100
        """,
        "carrera_id",
        "desde",
        "hasta",
    ),
    "dashboard_carreras_demanda": _query(
        "dashboard_carreras_demanda",
        """
        MATCH (o:Oferta_Laboral)-[:DIRIGE_A]->(ca:Carrera)
        WHERE o.fecha_publicacion IS NOT NULL
          AND date(o.fecha_publicacion) >= date($desde)
          AND date(o.fecha_publicacion) < date($hasta)
        RETURN ca.id_carrera AS id,
               ca.nombre_carrera AS elemento,
               count(DISTINCT o) AS ofertas
        ORDER BY ofertas DESC, elemento
        LIMIT $limite
        """,
        "desde",
        "hasta",
        "limite",
    ),
    "dashboard_empresas": _query(
        "dashboard_empresas",
        """
        MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
        WHERE o.fecha_publicacion IS NOT NULL
          AND date(o.fecha_publicacion) >= date($desde)
          AND date(o.fecha_publicacion) < date($hasta)
        RETURN e.id_empresa AS id,
               coalesce(e.nombre, e.razon_social, toString(e.id_empresa)) AS elemento,
               count(DISTINCT o) AS ofertas
        ORDER BY ofertas DESC, elemento
        LIMIT $limite
        """,
        "desde",
        "hasta",
        "limite",
    ),
}


for _slug, (_label, _id_property, _name_property) in DIMENSIONS.items():
    _QUERIES[f"dashboard_demanda_{_slug}"] = _query(
        f"dashboard_demanda_{_slug}",
        f"""
        MATCH (ca:Carrera {{id_carrera: $carrera_id}})-[:DIRIGE_A]-(o:Oferta_Laboral)
              -[:TIENE]-(r:Requerimiento_Laboral)-[:REQUIERE]-(elemento:{_label})
        WHERE o.fecha_publicacion IS NOT NULL
          AND date(o.fecha_publicacion) >= date($desde)
          AND date(o.fecha_publicacion) < date($hasta)
        RETURN elemento.{_id_property} AS id,
               elemento.{_name_property} AS elemento,
               count(DISTINCT o) AS ofertas
        ORDER BY ofertas DESC, elemento
        LIMIT $limite
        """,
        "carrera_id",
        "desde",
        "hasta",
        "limite",
    )
    _QUERIES[f"dashboard_cobertura_{_slug}"] = _query(
        f"dashboard_cobertura_{_slug}",
        f"""
        MATCH (ca:Carrera {{id_carrera: $carrera_id}})-[:ENSENIA]-(curso_total:Curso)
        WITH ca, count(DISTINCT curso_total) AS total_cursos
        MATCH (ca)-[:ENSENIA]-(curso:Curso)-[:TIENE]-(cobertura:Cobertura_Curricular)
              -[:{("CUBRE" if _slug == "competencias" else "ENSENIA")}]-(elemento:{_label})
        RETURN elemento.{_id_property} AS id,
               elemento.{_name_property} AS elemento,
               count(DISTINCT curso) AS cursos_con_cobertura,
               total_cursos
        ORDER BY cursos_con_cobertura DESC, elemento
        LIMIT $limite
        """,
        "carrera_id",
        "limite",
    )
    _QUERIES[f"dashboard_brechas_{_slug}"] = _query(
        f"dashboard_brechas_{_slug}",
        f"""
        MATCH (ca:Carrera {{id_carrera: $carrera_id}})
        OPTIONAL MATCH (ca)-[:DIRIGE_A]-(oferta_total:Oferta_Laboral)
        WHERE oferta_total.fecha_publicacion IS NOT NULL
          AND date(oferta_total.fecha_publicacion) >= date($desde)
          AND date(oferta_total.fecha_publicacion) < date($hasta)
        WITH ca, count(DISTINCT oferta_total) AS total_ofertas
        OPTIONAL MATCH (ca)-[:ENSENIA]-(curso_total:Curso)
        WITH ca, total_ofertas, count(DISTINCT curso_total) AS total_cursos
        MATCH (elemento:{_label})
        OPTIONAL MATCH (ca)-[:ENSENIA]-(curso_cobertura:Curso)-[:TIENE]
                       -(cobertura:Cobertura_Curricular)
                       -[:{("CUBRE" if _slug == "competencias" else "ENSENIA")}]-(elemento)
        WITH elemento, total_cursos, total_ofertas,
             count(DISTINCT curso_cobertura) AS cursos_con_cobertura
        OPTIONAL MATCH (ca)-[:DIRIGE_A]-(oferta_requerida:Oferta_Laboral)-[:TIENE]
                       -(requerimiento:Requerimiento_Laboral)-[:REQUIERE]-(elemento)
        WHERE oferta_requerida.fecha_publicacion IS NOT NULL
          AND date(oferta_requerida.fecha_publicacion) >= date($desde)
          AND date(oferta_requerida.fecha_publicacion) < date($hasta)
        WITH elemento, total_cursos, total_ofertas, cursos_con_cobertura,
             count(DISTINCT oferta_requerida) AS ofertas_que_requieren
        WHERE cursos_con_cobertura > 0 OR ofertas_que_requieren > 0
        WITH elemento, total_cursos, total_ofertas, cursos_con_cobertura,
             ofertas_que_requieren,
             CASE WHEN total_cursos = 0 THEN 0.0
                  ELSE toFloat(cursos_con_cobertura) / total_cursos END AS cobertura,
             CASE WHEN total_ofertas = 0 THEN 0.0
                  ELSE toFloat(ofertas_que_requieren) / total_ofertas END AS demanda
        RETURN elemento.{_id_property} AS id,
               elemento.{_name_property} AS elemento,
               coalesce(cursos_con_cobertura, 0) AS cursos_con_cobertura,
               coalesce(total_cursos, 0) AS total_cursos,
               coalesce(ofertas_que_requieren, 0) AS ofertas_que_requieren,
               coalesce(total_ofertas, 0) AS total_ofertas,
               toFloat(cobertura) AS cobertura,
               toFloat(demanda) AS demanda,
               toFloat(demanda) - toFloat(cobertura) AS brecha
        ORDER BY brecha DESC, ofertas_que_requieren DESC, elemento
        LIMIT $limite
        """,
        "carrera_id",
        "desde",
        "hasta",
        "limite",
    )
    _QUERIES[f"dashboard_industrias_{_slug}"] = _query(
        f"dashboard_industrias_{_slug}",
        f"""
        MATCH (industria:Industria)-[:AGRUPA]-(empresa:Empresa)-[:PUBLICA]-(oferta:Oferta_Laboral)
              -[:TIENE]-(requerimiento:Requerimiento_Laboral)-[:REQUIERE]-
              (elemento:{_label} {{{_id_property}: $elemento_id}})
        WHERE oferta.fecha_publicacion IS NOT NULL
          AND date(oferta.fecha_publicacion) >= date($desde)
          AND date(oferta.fecha_publicacion) < date($hasta)
        RETURN industria.nombre AS industria,
               count(DISTINCT oferta) AS ofertas
        ORDER BY ofertas DESC, industria
        LIMIT $limite
        """,
        "elemento_id",
        "desde",
        "hasta",
        "limite",
    )
    _QUERIES[f"dashboard_industrias_carrera_{_slug}"] = _query(
        f"dashboard_industrias_carrera_{_slug}",
        """
        MATCH (ca:Carrera {id_carrera: $carrera_id})-[:DIRIGE_A]-(o:Oferta_Laboral)
              -[:PUBLICA]-(e:Empresa)-[:AGRUPA]-(i:Industria)
        WHERE o.fecha_publicacion IS NOT NULL
          AND date(o.fecha_publicacion) >= date($desde)
          AND date(o.fecha_publicacion) < date($hasta)
        RETURN i.id_industria AS id,
               i.nombre AS elemento,
               count(DISTINCT o) AS ofertas
        ORDER BY ofertas DESC, elemento
        LIMIT $limite
        """,
        "carrera_id",
        "desde",
        "hasta",
        "limite",
    )


DASHBOARD_QUERIES: Final = MappingProxyType(_QUERIES)


SUPPORTED_DATASETS: Final[tuple[str, ...]] = (
    "tendencia_ofertas",
    "carreras_con_mayor_demanda",
    "industrias_por_carrera",
    "conocimientos_mas_demandados",
    "cobertura_curricular",
    "brechas_demanda_alta",
    "empresas_y_conocimientos",
)

UNSUPPORTED_DATASETS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "senales_revision_vigencia": (
            "The active package has no validated curriculum-only comparison projection."
        ),
        "cursos_con_mayor_correspondencia": (
            "The active package has no validated course-to-market correspondence projection."
        ),
        "diferenciadores_empresas": (
            "The active package has no validated A/B company denominator projection."
        ),
        "conocimientos_liderazgo": (
            "Leadership remains a title heuristic and is not exposed without a current "
            "validated query."
        ),
        "funciones_por_tipo_empresa": (
            "Puesto.nombre is available only as a published title; no normalized function "
            "dataset is active."
        ),
    }
)


def get_dashboard_query(query_id: str) -> DashboardQuery:
    """Return an allow-listed query or fail closed."""
    try:
        return DASHBOARD_QUERIES[query_id]
    except KeyError as exc:
        raise ValueError(f"Unknown dashboard query: {query_id}") from exc


def list_dashboard_queries() -> tuple[DashboardQuery, ...]:
    """Return the immutable query catalog in declaration order."""
    return tuple(DASHBOARD_QUERIES.values())
