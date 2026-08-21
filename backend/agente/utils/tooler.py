"""Safe, catalog-backed Cypher tools for employment-offer analytics.

This module intentionally exposes no arbitrary-Cypher execution function. Every
query is an immutable template with an explicit parameter contract and executes
through the read-only ``agente.utils.db.run_query`` boundary.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Any

from agente.utils.cypher_guard import guard_cypher

MAX_QUERY_LIMIT = 100
MAX_QUERY_OFFSET = 10_000
MAX_QUERY_TEXT_LENGTH = 200
MAX_QUERY_IDENTIFIER_LENGTH = 128


@dataclass(frozen=True, slots=True)
class CypherTemplate:
    """An immutable, allow-listed Cypher query and its parameter contract."""

    id: str
    description: str
    cypher: str
    required_parameters: tuple[str, ...]
    question_patterns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TemplateQuestionMatch:
    """A complete, validated match from one public question to one template."""

    template_id: str
    parameters: dict[str, Any]


ParameterValidator = Callable[[Any, str], Any]


def _validate_iso_date(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO-8601 date string")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 date (YYYY-MM-DD)") from exc


def _validate_identifier(value: Any, name: str) -> str:
    """Normalize a bounded schema identifier without allowing query syntax."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a valid identifier")
    normalized = str(value).strip() if isinstance(value, (str, int)) else ""
    if (
        not normalized
        or len(normalized) > MAX_QUERY_IDENTIFIER_LENGTH
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", normalized) is None
    ):
        raise ValueError(f"{name} must be a valid identifier")
    return normalized


def _validate_positive_limit(value: Any, name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > MAX_QUERY_LIMIT
    ):
        raise ValueError(f"{name} must be between 1 and {MAX_QUERY_LIMIT}")
    return value


def _validate_nonnegative_offset(value: Any, name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > MAX_QUERY_OFFSET
    ):
        raise ValueError(f"{name} must be between 0 and {MAX_QUERY_OFFSET}")
    return value


def _validate_nonblank_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonblank string")
    normalized = value.strip()
    if len(normalized) > MAX_QUERY_TEXT_LENGTH:
        raise ValueError(f"{name} cannot exceed {MAX_QUERY_TEXT_LENGTH} characters")
    return normalized


_PARAMETER_VALIDATORS: Mapping[str, ParameterValidator] = MappingProxyType(
    {
        "desde": _validate_iso_date,
        "hasta": _validate_iso_date,
        "carrera_id": _validate_identifier,
        "industria_id": _validate_identifier,
        "empresa_id": _validate_identifier,
        "puesto_id": _validate_identifier,
        "limite": _validate_positive_limit,
        "offset": _validate_nonnegative_offset,
        "texto": _validate_nonblank_text,
    }
)


TEMPLATES: Mapping[str, CypherTemplate] = MappingProxyType(
    {
        "resumen_general_ofertas": CypherTemplate(
            id="resumen_general_ofertas",
            description="Resume ofertas, empresas y carreras publicadas en un periodo.",
            required_parameters=("desde", "hasta"),
            cypher="""
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
OPTIONAL MATCH (o)-[:DIRIGE_A]->(c:Carrera)
RETURN
  count(DISTINCT o) AS total_ofertas,
  count(DISTINCT e) AS total_empresas,
  count(DISTINCT c) AS total_carreras,
  min(o.fecha_publicacion) AS primera_publicacion,
  max(o.fecha_publicacion) AS ultima_publicacion
LIMIT 1
""".strip(),
        ),
        "evolucion_mensual_ofertas": CypherTemplate(
            id="evolucion_mensual_ofertas",
            description="Agrupa las ofertas publicadas por mes dentro de un periodo.",
            required_parameters=("desde", "hasta"),
            cypher="""
MATCH (:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
WITH date.truncate('month', date(o.fecha_publicacion)) AS periodo,
     count(DISTINCT o) AS total_ofertas
RETURN periodo, total_ofertas
ORDER BY periodo
LIMIT 100
""".strip(),
        ),
        "industrias_mayor_demanda": CypherTemplate(
            id="industrias_mayor_demanda",
            description="Devuelve las industrias con más ofertas y empresas publicadoras.",
            required_parameters=("desde", "hasta", "limite"),
            cypher="""
MATCH (i:Industria)-[:AGRUPA]->(e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
RETURN i.id_industria AS industria_id,
       i.nombre AS industria,
       i.sector_macro AS sector_macro,
       count(DISTINCT o) AS total_ofertas,
       count(DISTINCT e) AS total_empresas
ORDER BY total_ofertas DESC, industria ASC
LIMIT $limite
""".strip(),
        ),
        "empresas_mayor_ofertas": CypherTemplate(
            id="empresas_mayor_ofertas",
            description="Identifica empresas con más oportunidades publicadas en un periodo.",
            required_parameters=("desde", "hasta", "limite"),
            cypher="""
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
RETURN e.id_empresa AS empresa_id,
       coalesce(e.nombre, e.razon_social, toString(e.id_empresa)) AS empresa,
       count(DISTINCT o) AS total_ofertas,
       max(o.fecha_publicacion) AS ultima_publicacion
ORDER BY total_ofertas DESC, ultima_publicacion DESC
LIMIT $limite
""".strip(),
        ),
        "carreras_mayor_oportunidades": CypherTemplate(
            id="carreras_mayor_oportunidades",
            description="Cuenta ofertas dirigidas explícitamente a cada carrera.",
            required_parameters=("desde", "hasta", "limite"),
            cypher="""
MATCH (o:Oferta_Laboral)-[:DIRIGE_A]->(c:Carrera)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
RETURN c.id_carrera AS carrera_id,
       c.nombre_carrera AS carrera,
       count(DISTINCT o) AS total_ofertas,
       count(DISTINCT o.cargo) AS cargos_distintos
ORDER BY total_ofertas DESC, carrera ASC
LIMIT $limite
""".strip(),
        ),
        "ofertas_por_carrera": CypherTemplate(
            id="ofertas_por_carrera",
            description="Lista ofertas de una carrera, con empresa e industria opcional.",
            required_parameters=("carrera_id", "desde", "hasta", "offset", "limite"),
            cypher="""
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)-[:DIRIGE_A]->(c:Carrera)
WHERE c.id_carrera = $carrera_id
  AND o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
OPTIONAL MATCH (i:Industria)-[:AGRUPA]->(e)
RETURN DISTINCT o.id_ofe_laboral AS oferta_id,
       o.cargo AS cargo,
       o.area AS area,
       o.area_especifica AS area_especifica,
       o.descripcion_breve AS descripcion,
       o.fecha_publicacion AS fecha_publicacion,
       o.fecha_finalizacion AS fecha_finalizacion,
       e.id_empresa AS empresa_id,
       coalesce(e.nombre, e.razon_social, toString(e.id_empresa)) AS empresa,
       i.id_industria AS industria_id,
       i.nombre AS industria
ORDER BY fecha_publicacion DESC
SKIP $offset
LIMIT $limite
""".strip(),
        ),
        "ofertas_por_industria": CypherTemplate(
            id="ofertas_por_industria",
            description="Lista ofertas de una industria y sus carreras relacionadas.",
            required_parameters=("industria_id", "desde", "hasta", "offset", "limite"),
            cypher="""
MATCH (i:Industria)-[:AGRUPA]->(e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
WHERE i.id_industria = $industria_id
  AND o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
OPTIONAL MATCH (o)-[:DIRIGE_A]->(c:Carrera)
WITH i, e, o,
     [carrera IN collect(DISTINCT c) WHERE carrera IS NOT NULL |
      {carrera_id: carrera.id_carrera, carrera: carrera.nombre_carrera}] AS carreras
RETURN o.id_ofe_laboral AS oferta_id,
       o.cargo AS cargo,
       o.area AS area,
       o.area_especifica AS area_especifica,
       o.descripcion_breve AS descripcion,
       o.fecha_publicacion AS fecha_publicacion,
       o.fecha_finalizacion AS fecha_finalizacion,
       e.id_empresa AS empresa_id,
       coalesce(e.nombre, e.razon_social, toString(e.id_empresa)) AS empresa,
       i.id_industria AS industria_id,
       i.nombre AS industria,
       carreras
ORDER BY fecha_publicacion DESC
SKIP $offset
LIMIT $limite
""".strip(),
        ),
        "demanda_carrera_industria": CypherTemplate(
            id="demanda_carrera_industria",
            description="Compara demanda de ofertas por combinación carrera e industria.",
            required_parameters=("desde", "hasta", "limite"),
            cypher="""
MATCH (i:Industria)-[:AGRUPA]->(e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
MATCH (o)-[:DIRIGE_A]->(c:Carrera)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
RETURN c.id_carrera AS carrera_id,
       c.nombre_carrera AS carrera,
       i.id_industria AS industria_id,
       i.nombre AS industria,
       count(DISTINCT o) AS total_ofertas,
       count(DISTINCT e) AS total_empresas
ORDER BY total_ofertas DESC, carrera ASC, industria ASC
LIMIT $limite
""".strip(),
        ),
        "elementos_demandados": CypherTemplate(
            id="elementos_demandados",
            description="Rankea habilidades, herramientas y competencias requeridas.",
            required_parameters=("desde", "hasta", "limite"),
            cypher="""
MATCH (o:Oferta_Laboral)-[:TIENE]->(r:Requerimiento_Laboral)-[:REQUIERE]->(elemento)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
  AND any(etiqueta IN labels(elemento)
          WHERE etiqueta IN ['Habilidad', 'Herramienta', 'Competencia'])
WITH CASE
       WHEN elemento:Habilidad THEN 'habilidad'
       WHEN elemento:Herramienta THEN 'herramienta'
       WHEN elemento:Competencia THEN 'competencia'
     END AS categoria,
     elemento,
     count(DISTINCT o) AS total_ofertas,
     count(DISTINCT r) AS total_requerimientos
RETURN categoria,
       CASE
         WHEN elemento:Habilidad THEN elemento.id_habilidad
         WHEN elemento:Herramienta THEN elemento.id_herramienta
         WHEN elemento:Competencia THEN elemento.id_competencia
       END AS elemento_id,
       CASE
         WHEN elemento:Habilidad THEN elemento.nombre_habilidad
         WHEN elemento:Herramienta THEN elemento.nombre_herramienta
         WHEN elemento:Competencia THEN elemento.nombre_competencia
       END AS elemento,
       total_ofertas,
       total_requerimientos
ORDER BY total_ofertas DESC, categoria ASC, elemento ASC
LIMIT $limite
""".strip(),
        ),
        "buscar_ofertas_texto": CypherTemplate(
            id="buscar_ofertas_texto",
            description="Busca ofertas por texto en cargo, áreas o descripción.",
            required_parameters=("desde", "hasta", "texto", "offset", "limite"),
            cypher="""
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
  AND (toLower(coalesce(o.cargo, '')) CONTAINS toLower($texto)
       OR toLower(coalesce(o.area, '')) CONTAINS toLower($texto)
       OR toLower(coalesce(o.area_especifica, '')) CONTAINS toLower($texto)
       OR toLower(coalesce(o.descripcion_breve, '')) CONTAINS toLower($texto))
OPTIONAL MATCH (o)-[:DIRIGE_A]->(c:Carrera)
WITH e, o,
     [carrera IN collect(DISTINCT c) WHERE carrera IS NOT NULL |
      {carrera_id: carrera.id_carrera, carrera: carrera.nombre_carrera}] AS carreras
RETURN o.id_ofe_laboral AS oferta_id,
       o.cargo AS cargo,
       o.area AS area,
       o.area_especifica AS area_especifica,
       o.descripcion_breve AS descripcion,
       o.fecha_publicacion AS fecha_publicacion,
       o.fecha_finalizacion AS fecha_finalizacion,
       e.id_empresa AS empresa_id,
       coalesce(e.nombre, e.razon_social, toString(e.id_empresa)) AS empresa,
       carreras
ORDER BY fecha_publicacion DESC
SKIP $offset
LIMIT $limite
""".strip(),
        ),
        "contar_empresas": CypherTemplate(
            id="contar_empresas",
            description="Cuenta las empresas registradas en el grafo.",
            required_parameters=(),
            question_patterns=(
                "¿Cuántas empresas hay registradas?",
                "¿Cuántas empresas están registradas?",
            ),
            cypher="""
MATCH (e:Empresa)
RETURN count(e) AS total_empresas
LIMIT 1
""".strip(),
        ),
        "listar_empresas": CypherTemplate(
            id="listar_empresas",
            description="Lista empresas registradas con su identificador y nombre.",
            required_parameters=(),
            question_patterns=("¿Qué empresas hay?",),
            cypher="""
MATCH (e:Empresa)
RETURN e.id_empresa AS empresa_id,
       coalesce(e.nombre, e.razon_social, toString(e.id_empresa)) AS empresa
ORDER BY empresa ASC, empresa_id ASC
LIMIT 100
""".strip(),
        ),
        "ofertas_de_empresa": CypherTemplate(
            id="ofertas_de_empresa",
            description="Cuenta las ofertas publicadas por una empresa.",
            required_parameters=("empresa_id",),
            question_patterns=(
                "¿Cuántas ofertas publicó {empresa_id}?",
                "¿Cuántas ofertas laborales publicó {empresa_id}?",
                "¿Cuántas ofertas publicó la empresa {empresa_id}?",
            ),
            cypher="""
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)
WHERE e.id_empresa = $empresa_id
RETURN count(DISTINCT o) AS total_ofertas
LIMIT 1
""".strip(),
        ),
        "puestos_de_empresa": CypherTemplate(
            id="puestos_de_empresa",
            description="Lista los puestos publicados por una empresa.",
            required_parameters=("empresa_id", "limite"),
            cypher="""
MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)-[:OFRECE]->(p:Puesto)
WHERE e.id_empresa = $empresa_id
RETURN p.id_puesto AS puesto_id,
       p.nombre AS puesto,
       count(DISTINCT o) AS total_ofertas
ORDER BY total_ofertas DESC, puesto ASC
LIMIT $limite
""".strip(),
        ),
        "empresas_de_industria": CypherTemplate(
            id="empresas_de_industria",
            description="Lista las empresas agrupadas en una industria.",
            required_parameters=("industria_id", "limite"),
            cypher="""
MATCH (i:Industria)-[:AGRUPA]->(e:Empresa)
WHERE i.id_industria = $industria_id
RETURN e.id_empresa AS empresa_id,
       coalesce(e.nombre, e.razon_social, toString(e.id_empresa)) AS empresa
ORDER BY empresa ASC, empresa_id ASC
LIMIT $limite
""".strip(),
        ),
        "competencias_demandadas_carrera": CypherTemplate(
            id="competencias_demandadas_carrera",
            description="Cuenta las competencias requeridas en ofertas dirigidas a una carrera.",
            required_parameters=("carrera_id", "limite"),
            cypher="""
MATCH (o:Oferta_Laboral)-[:DIRIGE_A]->(c:Carrera)
MATCH (o)-[:TIENE]->(:Requerimiento_Laboral)-[:REQUIERE]->(x:Competencia)
WHERE c.id_carrera = $carrera_id
RETURN x.id_competencia AS competencia_id,
       x.nombre_competencia AS competencia,
       count(DISTINCT o) AS total_ofertas
ORDER BY total_ofertas DESC, competencia ASC
LIMIT $limite
""".strip(),
        ),
        "habilidades_para_puesto": CypherTemplate(
            id="habilidades_para_puesto",
            description="Lista las habilidades requeridas para un puesto.",
            required_parameters=("puesto_id", "limite"),
            cypher="""
MATCH (p:Puesto)-[:DEFIINE]->(:Requerimiento_Laboral)-[:REQUIERE]->(h:Habilidad)
WHERE p.id_puesto = $puesto_id
RETURN h.id_habilidad AS habilidad_id,
       h.nombre_habilidad AS habilidad
ORDER BY habilidad ASC, habilidad_id ASC
LIMIT $limite
""".strip(),
        ),
        "top_competencias_ofertas": CypherTemplate(
            id="top_competencias_ofertas",
            description="Rankea las competencias más requeridas en ofertas de un periodo.",
            required_parameters=("desde", "hasta", "limite"),
            cypher="""
MATCH (o:Oferta_Laboral)-[:TIENE]->(:Requerimiento_Laboral)-[:REQUIERE]->(x:Competencia)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
RETURN x.id_competencia AS competencia_id,
       x.nombre_competencia AS competencia,
       count(DISTINCT o) AS total_ofertas
ORDER BY total_ofertas DESC, competencia ASC
LIMIT $limite
""".strip(),
        ),
        "herramientas_mas_requeridas": CypherTemplate(
            id="herramientas_mas_requeridas",
            description="Rankea las herramientas más requeridas en ofertas de un periodo.",
            required_parameters=("desde", "hasta", "limite"),
            cypher="""
MATCH (o:Oferta_Laboral)-[:TIENE]->(:Requerimiento_Laboral)-[:REQUIERE]->(x:Herramienta)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
RETURN x.id_herramienta AS herramienta_id,
       x.nombre_herramienta AS herramienta,
       count(DISTINCT o) AS total_ofertas
ORDER BY total_ofertas DESC, herramienta ASC
LIMIT $limite
""".strip(),
        ),
        "puestos_mas_demandados": CypherTemplate(
            id="puestos_mas_demandados",
            description="Rankea los puestos publicados con más ofertas en un periodo.",
            required_parameters=("desde", "hasta", "limite"),
            cypher="""
MATCH (o:Oferta_Laboral)-[:OFRECE]->(p:Puesto)
WHERE o.fecha_publicacion IS NOT NULL
  AND date(o.fecha_publicacion) >= date($desde)
  AND date(o.fecha_publicacion) < date($hasta)
RETURN p.id_puesto AS puesto_id,
       p.nombre AS puesto,
       count(DISTINCT o) AS total_ofertas
ORDER BY total_ofertas DESC, puesto ASC
LIMIT $limite
""".strip(),
        ),
    }
)
_ENTITY_CANDIDATE_PATTERN = re.compile(r"^[^;\x00-\x1f\x7f`{}]{1,200}$")
_ENTITY_CANDIDATE_UNSAFE = re.compile(r"//|/\*|\*/")
_ENTITY_PARAMETER_NAMES = frozenset(
    {
        "carrera_id",
        "industria_id",
        "empresa_id",
        "puesto_id",
        "habilidad_id",
        "herramienta_id",
        "competencia_id",
        "curso_id",
        "facultad_id",
    }
)


def list_templates() -> tuple[CypherTemplate, ...]:
    """Return the complete immutable catalog in declaration order."""
    return tuple(TEMPLATES.values())


_QUESTION_PLACEHOLDER = re.compile(r"^\{([a-z][a-z0-9_]*)\}$")


def _normalize_question(text: str, *, preserve_case: bool = False) -> str:
    """Normalize only orthographic variants used by exact catalog patterns."""
    source = text if preserve_case else text.casefold()
    decomposed = unicodedata.normalize("NFKD", source)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^A-Za-z0-9{}_-]+", " ", without_marks).split())


def _question_pattern_regex(pattern: str) -> re.Pattern[str]:
    tokens = _normalize_question(pattern).split()
    parts: list[str] = []
    for token in tokens:
        placeholder = _QUESTION_PLACEHOLDER.fullmatch(token)
        if placeholder is None:
            parts.append(re.escape(token))
            continue
        parameter_name = placeholder.group(1)
        parts.append(
            rf"(?P<{parameter_name}>[A-Za-z0-9][A-Za-z0-9_-]*)"
        )
    return re.compile(r"\A" + r"\s+".join(parts) + r"\Z")


def find_template_for_question(question: str) -> TemplateQuestionMatch | None:
    """Find one exact safe template match; return ``None`` on any uncertainty."""
    if not isinstance(question, str):
        return None

    normalized = _normalize_question(question)
    raw_tokens = _normalize_question(question, preserve_case=True).split()
    candidates: list[TemplateQuestionMatch] = []
    for template in list_templates():
        for pattern in template.question_patterns:
            pattern_tokens = _normalize_question(pattern).split()
            match = _question_pattern_regex(pattern).fullmatch(normalized)
            if match is None:
                continue
            parameters = {
                placeholder.group(1): raw_tokens[index]
                for index, token in enumerate(pattern_tokens)
                if (placeholder := _QUESTION_PLACEHOLDER.fullmatch(token)) is not None
            }
            try:
                validated = validate_template_parameters(template.id, parameters)
                guard_cypher(template.cypher, validated)
            except (TypeError, ValueError):
                continue
            candidates.append(TemplateQuestionMatch(template.id, validated))

    unique_candidates = {
        (candidate.template_id, tuple(sorted(candidate.parameters.items())))
        for candidate in candidates
    }
    template_ids = {candidate.template_id for candidate in candidates}
    if len(template_ids) != 1 or len(unique_candidates) != 1:
        return None
    return candidates[0]


def get_template(template_id: str) -> CypherTemplate:
    """Return an allow-listed template or fail closed for an unknown ID."""
    try:
        return TEMPLATES[template_id]
    except KeyError as exc:
        raise ValueError(f"Unknown Cypher template: {template_id}") from exc


def validate_template_parameters(
    template_id: str,
    parameters: Mapping[str, Any],
    *,
    allow_entity_candidates: bool = False,
) -> dict[str, Any]:
    """Validate a template's exact parameter set and return normalized values."""
    template = get_template(template_id)
    supplied = set(parameters)
    expected = set(template.required_parameters)
    missing = expected - supplied
    unexpected = supplied - expected
    if missing:
        raise ValueError(f"Missing required parameters: {', '.join(sorted(missing))}")
    if unexpected:
        raise ValueError(f"Unexpected parameters: {', '.join(sorted(unexpected))}")

    validated: dict[str, Any] = {}
    for name in template.required_parameters:
        value = parameters[name]
        if (
            allow_entity_candidates
            and name in _ENTITY_PARAMETER_NAMES
            and isinstance(value, (str, int))
            and not isinstance(value, bool)
        ):
            candidate = str(value).strip()
            if (
                not _ENTITY_CANDIDATE_PATTERN.fullmatch(candidate)
                or _ENTITY_CANDIDATE_UNSAFE.search(candidate)
            ):
                raise ValueError(f"{name} must be a valid entity candidate")
            validated[name] = candidate
        else:
            validated[name] = _PARAMETER_VALIDATORS[name](value, name)
    if validated.get("desde") is not None and validated.get("hasta") is not None:
        if validated["desde"] >= validated["hasta"]:
            raise ValueError("desde must be earlier than hasta")
    return validated
