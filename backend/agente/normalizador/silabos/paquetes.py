"""Source-scoped CHH packages used by the human approval checkpoint."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from agente.normalizador.modelos import Hallazgo
from agente.normalizador.silabos.clasificacion import estado_clasificacion

PACKAGE_ID_FIELD = "id_paquete_chh"
PACKAGE_ID_ALIASES = (PACKAGE_ID_FIELD, "package_id", "id_paquete")
PACKAGE_SOURCE_KEY_FIELD = "package_source_key"
PACKAGE_SOURCE_IDENTITY_FIELD = "source_identity"
_REQUIRED_IDENTITY_FIELDS = (
    "id_ejecucion",
    "carrera",
    "periodo",
    "id_curso",
    "id_silabo",
    "id_habilidad_fuente",
)
# A source coverage row is the review boundary whenever it is available.  The
# empty value keeps historical, relation-less pending rows on their existing
# source-skill scope; it is never synthesized from relation content.
SOURCE_RELATION_ID_FIELD = "id_cob_curricular"
IDENTITY_FIELDS = (*_REQUIRED_IDENTITY_FIELDS, SOURCE_RELATION_ID_FIELD)
RELATION_KEYS = (
    "id_cob_curricular",
    "id_curso",
    "id_silabo",
    "id_competencia",
    "id_habilidad",
    "id_herramienta",
)
_TYPE_ORDER = {"competencia": 0, "habilidad": 1, "herramienta": 2}
_UNRESOLVED_RESOLUTION_STATES = {
    "CANONIZADA_CON_PROPUESTA_PERFIL",
    "PENDIENTE",
    "PENDIENTE_CATALOGACION",
    "PENDIENTE_AMPLIACION_PERFIL",
    "REQUIERE_REVISION_HUMANA",
    "MANTENIDA_PENDIENTE",
    "PENDING",
    "REVIEW",
    "REQUIRES_HUMAN_REVIEW",
}
_SOURCE_FILES = {
    "competencia": (
        "competencias_fuente.jsonl",
        "id_competencia_fuente",
        "id_competencia_canonica",
        "nombre_competencia_fuente",
    ),
    "habilidad": (
        "habilidades_fuente.jsonl",
        "id_habilidad_fuente",
        "id_habilidad_canonica",
        None,
    ),
    "herramienta": (
        "herramientas_fuente.jsonl",
        "id_herramienta_fuente",
        "id_herramienta_canonica",
        "nombre_herramienta",
    ),
}
_SOURCE_RELATIONS_FILE = "cobertura_curricular_fuente.jsonl"
_CATALOGS = {
    "competencia": ("catalogo_competencias.csv", "id_competencia", "nombre_competencia"),
    "habilidad": ("catalogo_habilidades.csv", "id_habilidad", "nombre_habilidad"),
    "herramienta": ("catalogo_herramientas.csv", "id_herramienta", "nombre_herramienta"),
}
_TECHNICAL_NAME = re.compile(
    r"^(?:HAB|COMP|HERR|PROP|PROPOSAL|PEN|PKG)(?:[_-][A-Za-z0-9:-]+)+$",
    re.IGNORECASE,
)
_HASH_NAME = re.compile(r"^(?:sha256:)?[0-9a-f]{16,}$", re.IGNORECASE)

_IdentityKey = tuple[str, str, str, str, str, str, str]
_CourseSyllabusKey = tuple[str, str]


@dataclass(frozen=True)
class _PackageAssemblyIndex:
    """Immutable, call-local selections for source-scoped package assembly."""

    source_relations: Mapping[_IdentityKey, tuple[Mapping[str, object], ...]]
    sources: Mapping[_IdentityKey, Mapping[str, tuple[Mapping[str, object], ...]]]
    coverage_relations: Mapping[_IdentityKey, tuple[Mapping[str, object], ...]]
    package_relations: Mapping[_IdentityKey, tuple[Mapping[str, object], ...]]


class IdentidadFuenteIncompleta(ValueError):
    """A package cannot be assembled without its complete source identity."""


def identidad_fuente_chh(
    fila: Mapping[str, object], *, id_ejecucion: str = "", carrera: str = "", periodo: str = ""
) -> dict[str, str]:
    """Build a collision-safe identity; a raw source skill ID is never sufficient."""
    nested = _mapping(fila.get(PACKAGE_SOURCE_IDENTITY_FIELD))
    source_skill = _first(
        fila,
        "id_habilidad_fuente",
        "source_skill_id",
        "id_habilidad_source",
    ) or _first(nested, "id_habilidad_fuente")
    syllabus = _first(fila, "id_silabo", "syllabus_id", "silabo") or _first(nested, "id_silabo")
    identity = {
        "id_ejecucion": _first(fila, "id_ejecucion", "execution_id")
        or _first(nested, "id_ejecucion")
        or id_ejecucion,
        "carrera": _first(fila, "carrera", "career") or _first(nested, "carrera") or carrera,
        "periodo": _first(fila, "periodo", "period") or _first(nested, "periodo") or periodo,
        "id_curso": _first(fila, "id_curso", "course_id") or _first(nested, "id_curso"),
        "id_silabo": syllabus,
        "id_habilidad_fuente": source_skill,
        SOURCE_RELATION_ID_FIELD: _first(
            fila, SOURCE_RELATION_ID_FIELD, "id_relacion_fuente", "source_relation_id"
        )
        or _first(nested, SOURCE_RELATION_ID_FIELD, "id_relacion_fuente", "source_relation_id"),
    }
    missing = [key for key in _REQUIRED_IDENTITY_FIELDS if not identity[key]]
    if missing:
        raise IdentidadFuenteIncompleta(
            "Identidad de paquete CHH incompleta; faltan: " + ", ".join(missing) + "."
        )
    return identity


def clave_fuente_chh(identity: Mapping[str, str]) -> str:
    payload = {key: _text(identity.get(key)) for key in _REQUIRED_IDENTITY_FIELDS}
    if relation_id := _text(identity.get(SOURCE_RELATION_ID_FIELD)):
        payload[SOURCE_RELATION_ID_FIELD] = relation_id
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def id_paquete_chh(identity: Mapping[str, str]) -> str:
    digest = hashlib.sha256(clave_fuente_chh(identity).encode("utf-8")).hexdigest()
    return f"PKG_CHH_{digest[:20]}"


def preparar_fila_paquete(
    fila: Mapping[str, object], *, id_ejecucion: str = "", carrera: str = "", periodo: str = ""
) -> dict[str, object]:
    prepared = dict(fila)
    identity = identidad_fuente_chh(
        prepared, id_ejecucion=id_ejecucion, carrera=carrera, periodo=periodo
    )
    package_id = id_paquete_chh(identity)
    prepared.update(
        {
            PACKAGE_ID_FIELD: package_id,
            "package_id": package_id,
            PACKAGE_SOURCE_KEY_FIELD: clave_fuente_chh(identity),
            "clave_paquete_chh": clave_fuente_chh(identity),
            PACKAGE_SOURCE_IDENTITY_FIELD: identity,
            "execution_id": identity["id_ejecucion"],
            "career": identity["carrera"],
            "period": identity["periodo"],
        }
    )
    return prepared


def ensamblar_paquetes_chh(
    filas: Sequence[Mapping[str, object]],
    *,
    id_ejecucion: str = "",
    carrera: str = "",
    periodo: str = "",
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    relaciones: Sequence[Mapping[str, object]] | None = None,
    archivos: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
) -> list[dict[str, object]]:
    prepared = [
        preparar_fila_paquete(row, id_ejecucion=id_ejecucion, carrera=carrera, periodo=periodo)
        for row in filas
    ]
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in prepared:
        grouped.setdefault(_first(row, *PACKAGE_ID_ALIASES), []).append(row)
    index = _index_package_assembly(
        [_mapping(rows[0].get(PACKAGE_SOURCE_IDENTITY_FIELD)) for rows in grouped.values() if rows],
        fuentes=fuentes,
        relaciones=relaciones,
        archivos=archivos,
    )
    return [
        _assemble_one(
            package_id,
            rows,
            fuentes=fuentes,
            relaciones=relaciones,
            archivos=archivos,
            index=index,
        )
        for package_id, rows in sorted(grouped.items())
    ]


def construir_paquetes_chh(
    filas: Sequence[Mapping[str, object]],
    *,
    id_ejecucion: str = "",
    carrera: str = "",
    periodo: str = "",
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    relaciones: Sequence[Mapping[str, object]] | None = None,
    archivos: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
) -> list[dict[str, object]]:
    return ensamblar_paquetes_chh(
        filas,
        id_ejecucion=id_ejecucion,
        carrera=carrera,
        periodo=periodo,
        fuentes=fuentes,
        relaciones=relaciones,
        archivos=archivos,
    )


def validar_integridad_paquetes_chh(
    paquetes: Sequence[Mapping[str, object]],
) -> tuple[Hallazgo, ...]:
    """Validate package-local coverage. A competency-only package is valid."""
    findings: list[Hallazgo] = []
    for package in paquetes:
        package_id = _first(package, *PACKAGE_ID_ALIASES)
        identity = _mapping(package.get(PACKAGE_SOURCE_IDENTITY_FIELD))
        if not _identity_complete(identity):
            findings.append(
                _finding(
                    "PAQUETE_IDENTIDAD_INCOMPLETA",
                    "El paquete debe conservar toda la identidad de su fuente.",
                    package_id,
                )
            )
        else:
            expected_package_id = id_paquete_chh(
                {key: _text(identity.get(key)) for key in IDENTITY_FIELDS}
            )
            if package_id != expected_package_id:
                findings.append(
                    _finding(
                        "PAQUETE_ID_INVALIDO",
                        "El id del paquete no coincide con su identidad fuente.",
                        package_id or expected_package_id,
                    )
                )
        grouped = _mapping(package.get("componentes"))
        competencies = _components(package, grouped, "competencias", "competency")
        skills = _components(package, grouped, "habilidades", "skills")
        tools = _components(package, grouped, "herramientas", "tools")
        pending_hitl = _package_waiting_for_decision(package)
        for blocker in _list_value(package.get("competency_blockers")):
            if not isinstance(blocker, Mapping):
                continue
            findings.append(
                _finding(
                    _text(blocker.get("code")) or "COMPETENCY_SOURCE_MAPPING_REQUIRED",
                    "La referencia de competencia fuente requiere un mapeo canónico real: "
                    + _text(blocker.get("id_competencia_fuente")),
                    package_id,
                )
            )
        competency_ids = _component_ids(competencies, "competencia")
        skill_ids = _component_ids(skills, "habilidad")
        tool_ids = _component_ids(tools, "herramienta")
        if not competencies:
            findings.append(
                _finding(
                    "PAQUETE_SIN_COMPETENCIA",
                    "Todo paquete CHH debe contener una competencia.",
                    package_id,
                )
            )
            if skills:
                findings.append(
                    _finding(
                        "PAQUETE_HABILIDAD_SIN_COMPETENCIA",
                        "Una habilidad sin competencia es un error de estructura del paquete.",
                        package_id,
                    )
                )
        parsed: list[tuple[str, ...]] = []
        for index, relation in enumerate(_relationships(package), start=1):
            values = _relation_values(relation)
            if values is None or not values[1] or not values[2] or not values[3] or not values[4]:
                findings.append(
                    _finding(
                        "PAQUETE_RELACION_INVALIDA",
                        "Una relación debe conservar curso, sílabo, competencia y habilidad.",
                        package_id,
                        fila=index,
                    )
                )
                continue
            if isinstance(relation, Mapping) and not _scope_matches(relation, identity):
                findings.append(
                    _finding(
                        "PAQUETE_RELACION_FUERA_DE_SCOPE",
                        "Las relaciones deben pertenecer al mismo paquete fuente.",
                        package_id,
                        fila=index,
                    )
                )
            if (
                values[3] not in competency_ids
                or values[4] not in skill_ids
                or (values[5] and values[5] not in tool_ids)
            ):
                findings.append(
                    _finding(
                        "PAQUETE_RELACION_REFERENCIA_INVALIDA",
                        "Una relación apunta a un componente ausente del paquete.",
                        package_id,
                        fila=index,
                    )
                )
            parsed.append(values)
        skills_without_relation = skill_ids - {
            value[4] for value in parsed if value[3] in competency_ids and value[4] in skill_ids
        }
        if skills and not pending_hitl and skills_without_relation:
            findings.append(
                _finding(
                    "PAQUETE_HABILIDAD_SIN_RELACION",
                    "Toda habilidad presente debe conservar una relación del paquete.",
                    package_id,
                )
            )
        tools_without_chain = tool_ids - {
            value[5]
            for value in parsed
            if value[3] in competency_ids and value[4] in skill_ids and value[5] in tool_ids
        }
        if tools and not pending_hitl and tools_without_chain:
            findings.append(
                _finding(
                    "PAQUETE_HERRAMIENTA_SIN_RELACION",
                    "Toda herramienta presente debe conservar una relación con "
                    "habilidad y competencia.",
                    package_id,
                )
            )
        for row in _rows(package):
            row_identity = _mapping(row.get(PACKAGE_SOURCE_IDENTITY_FIELD))
            if row_identity and identity and not _identity_equal(row_identity, identity):
                findings.append(
                    _finding(
                        "PAQUETE_FUENTE_FUERA_DE_SCOPE",
                        "Las filas fuente deben pertenecer al mismo paquete.",
                        package_id,
                    )
                )
                break
    return tuple(findings)


def validar_paquetes_chh(paquetes: Sequence[Mapping[str, object]]) -> tuple[Hallazgo, ...]:
    return validar_integridad_paquetes_chh(paquetes)


def revision_paquetes_chh(paquetes: Sequence[Mapping[str, object]]) -> str:
    snapshot = [
        {
            PACKAGE_ID_FIELD: _first(package, *PACKAGE_ID_ALIASES),
            "decision": _text(package.get("decision")),
            "rows": sorted(_text(row.get("id_pendiente")) for row in _rows(package)),
        }
        for package in paquetes
    ]
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


assemble_chh_packages = ensamblar_paquetes_chh
validate_chh_packages = validar_integridad_paquetes_chh


def _index_package_assembly(
    identities: Sequence[Mapping[str, object]],
    *,
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None,
    relaciones: Sequence[Mapping[str, object]] | None,
    archivos: Mapping[str, Sequence[Mapping[str, object]]] | None,
) -> _PackageAssemblyIndex:
    """Preselect every source and relation once for this assembly invocation."""

    identity_keys = tuple(
        dict.fromkeys(
            key for identity in identities if (key := _identity_key(identity)) is not None
        )
    )
    source_rows = fuentes or {}
    source_relations = source_rows.get(_SOURCE_RELATIONS_FILE, ())
    relation_buckets = _source_relation_buckets(source_relations)
    source_buckets = {
        filename: _identity_buckets(source_rows.get(filename, ()))
        for filename, *_ in _SOURCE_FILES.values()
    }
    competency_by_source = _value_buckets(
        source_rows.get("competencias_fuente.jsonl", ()), "id_competencia_fuente"
    )
    coverage_buckets = _relation_buckets((archivos or {}).get("cobertura_curricular.csv", ()))
    package_buckets = _relation_buckets(relaciones or ())

    indexed_source_relations: dict[_IdentityKey, tuple[Mapping[str, object], ...]] = {}
    indexed_sources: dict[_IdentityKey, Mapping[str, tuple[Mapping[str, object], ...]]] = {}
    indexed_coverage: dict[_IdentityKey, tuple[Mapping[str, object], ...]] = {}
    indexed_package_relations: dict[_IdentityKey, tuple[Mapping[str, object], ...]] = {}
    for identity_key in identity_keys:
        scoped_source_relations = _source_relations_for_key(identity_key, relation_buckets)
        indexed_source_relations[identity_key] = scoped_source_relations
        fallback_competencies = {
            _text(relation.get("id_competencia_fuente")) for relation in scoped_source_relations
        }
        fallback_competencies.discard("")
        selected_sources: dict[str, tuple[Mapping[str, object], ...]] = {}
        for kind, (filename, *_rest) in _SOURCE_FILES.items():
            direct = _ordered_rows(
                source_buckets[filename].get(identity_key, ()),
                source_buckets[filename].get(_base_identity_key(identity_key), ()),
            )
            fallback = (
                tuple(
                    candidate
                    for source_id in fallback_competencies
                    for candidate in competency_by_source.get(source_id, ())
                )
                if kind == "competencia"
                else ()
            )
            candidates = tuple(
                {id(row): row for row in (*direct, *(row for _position, row in fallback))}.values()
            )
            selected_sources[filename] = (
                tuple(
                    source
                    for source in candidates
                    if _source_row_matches_relation_unit(
                        source, kind, _identity_from_key(identity_key), scoped_source_relations
                    )
                )
                if identity_key[-1]
                else candidates
            )
        indexed_sources[identity_key] = MappingProxyType(selected_sources)
        indexed_coverage[identity_key] = _scoped_relations_for_key(
            identity_key, coverage_buckets, selected_sources, scoped_source_relations
        )
        indexed_package_relations[identity_key] = _scoped_relations_for_key(
            identity_key, package_buckets, selected_sources, scoped_source_relations
        )
    return _PackageAssemblyIndex(
        source_relations=MappingProxyType(indexed_source_relations),
        sources=MappingProxyType(indexed_sources),
        coverage_relations=MappingProxyType(indexed_coverage),
        package_relations=MappingProxyType(indexed_package_relations),
    )


def _identity_key(identity: Mapping[str, object]) -> _IdentityKey | None:
    values = tuple(_text(identity.get(field)) for field in IDENTITY_FIELDS)
    return values if all(values[: len(_REQUIRED_IDENTITY_FIELDS)]) else None  # type: ignore[return-value]


def _base_identity_key(identity: _IdentityKey) -> _IdentityKey:
    """Drop optional relation identity for source records that predate it."""

    return (*identity[: len(_REQUIRED_IDENTITY_FIELDS)], "")


def _identity_from_key(identity: _IdentityKey) -> dict[str, str]:
    return dict(zip(IDENTITY_FIELDS, identity, strict=True))


def _row_identity_key(row: Mapping[str, object]) -> _IdentityKey | None:
    nested = _mapping(row.get(PACKAGE_SOURCE_IDENTITY_FIELD))
    if nested:
        return _identity_key(nested)
    return _identity_key(
        {
            "id_ejecucion": _first(row, "id_ejecucion", "execution_id"),
            "carrera": _first(row, "carrera", "career"),
            "periodo": _first(row, "periodo", "period"),
            "id_curso": _first(row, "id_curso", "course_id"),
            "id_silabo": _first(row, "id_silabo", "syllabus_id", "silabo"),
            "id_habilidad_fuente": _first(row, "id_habilidad_fuente", "source_skill_id"),
            SOURCE_RELATION_ID_FIELD: _first(
                row, SOURCE_RELATION_ID_FIELD, "id_relacion_fuente", "source_relation_id"
            ),
        }
    )


def _identity_buckets(
    rows: Sequence[Mapping[str, object]],
) -> dict[_IdentityKey, tuple[tuple[int, Mapping[str, object]], ...]]:
    buckets: dict[_IdentityKey, list[tuple[int, Mapping[str, object]]]] = {}
    for position, row in enumerate(rows):
        if (key := _row_identity_key(row)) is not None:
            buckets.setdefault(key, []).append((position, row))
    return {key: tuple(values) for key, values in buckets.items()}


def _value_buckets(
    rows: Sequence[Mapping[str, object]], key: str
) -> dict[str, tuple[tuple[int, Mapping[str, object]], ...]]:
    buckets: dict[str, list[tuple[int, Mapping[str, object]]]] = {}
    for position, row in enumerate(rows):
        if value := _text(row.get(key)):
            buckets.setdefault(value, []).append((position, row))
    return {value: tuple(rows) for value, rows in buckets.items()}


def _source_relation_buckets(
    rows: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str, str], tuple[tuple[int, Mapping[str, object]], ...]]:
    buckets: dict[tuple[str, str, str], list[tuple[int, Mapping[str, object]]]] = {}
    for position, row in enumerate(rows):
        key = (
            _text(row.get("id_curso")),
            _text(row.get("id_silabo")),
            _text(row.get("id_habilidad_fuente")),
        )
        buckets.setdefault(key, []).append((position, row))
    return {key: tuple(values) for key, values in buckets.items()}


def _source_relations_for_key(
    identity: _IdentityKey,
    buckets: Mapping[tuple[str, str, str], Sequence[tuple[int, Mapping[str, object]]]],
) -> tuple[Mapping[str, object], ...]:
    candidates = buckets.get((identity[3], identity[4], identity[5]), ())
    return tuple(
        row
        for _position, row in candidates
        if (not _text(row.get("id_ejecucion")) or _text(row.get("id_ejecucion")) == identity[0])
        and (not identity[-1] or _text(row.get(SOURCE_RELATION_ID_FIELD)) == identity[-1])
    )


def _relation_buckets(
    rows: Sequence[Mapping[str, object]],
) -> tuple[
    Mapping[_IdentityKey, tuple[tuple[int, Mapping[str, object]], ...]],
    Mapping[_CourseSyllabusKey, tuple[tuple[int, Mapping[str, object]], ...]],
]:
    by_identity: dict[_IdentityKey, list[tuple[int, Mapping[str, object]]]] = {}
    by_course_syllabus: dict[_CourseSyllabusKey, list[tuple[int, Mapping[str, object]]]] = {}
    for position, row in enumerate(rows):
        if (identity_key := _row_identity_key(row)) is not None:
            by_identity.setdefault(identity_key, []).append((position, row))
        course_syllabus = (
            _first(row, "id_curso", "course_id"),
            _first(row, "id_silabo", "syllabus_id", "silabo"),
        )
        by_course_syllabus.setdefault(course_syllabus, []).append((position, row))
    return (
        {key: tuple(values) for key, values in by_identity.items()},
        {key: tuple(values) for key, values in by_course_syllabus.items()},
    )


def _ordered_rows(
    *groups: Sequence[tuple[int, Mapping[str, object]]],
) -> tuple[Mapping[str, object], ...]:
    selected: dict[int, Mapping[str, object]] = {}
    for group in groups:
        for position, row in group:
            selected.setdefault(position, row)
    return tuple(row for _position, row in sorted(selected.items()))


def _scoped_relations_for_key(
    identity: _IdentityKey,
    buckets: tuple[
        Mapping[_IdentityKey, tuple[tuple[int, Mapping[str, object]], ...]],
        Mapping[_CourseSyllabusKey, tuple[tuple[int, Mapping[str, object]], ...]],
    ],
    selected_sources: Mapping[str, Sequence[Mapping[str, object]]],
    source_relations: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    direct, by_course_syllabus = buckets
    candidates = _ordered_rows(
        direct.get(identity, ()), by_course_syllabus.get((identity[3], identity[4]), ())
    )
    direct_rows = {id(row) for _position, row in direct.get(identity, ())}
    scoped_ids = _scoped_canonical_ids(selected_sources, source_relations)
    return tuple(
        relation
        for relation in candidates
        if id(relation) in direct_rows
        or _relation_matches_scoped_ids(relation, identity, scoped_ids)
    )


def _scoped_canonical_ids(
    sources: Mapping[str, Sequence[Mapping[str, object]]],
    source_relations: Sequence[Mapping[str, object]],
) -> tuple[set[str], set[str], set[str]]:
    skills = {
        _text(row.get("id_habilidad_canonica"))
        for row in sources.get("habilidades_fuente.jsonl", ())
        if _text(row.get("id_habilidad_canonica"))
    }
    competencies = {
        _text(row.get("id_competencia_canonica"))
        for row in sources.get("competencias_fuente.jsonl", ())
        if _text(row.get("id_competencia_canonica"))
    }
    tools = {
        _text(row.get("id_herramienta_canonica"))
        for row in sources.get("herramientas_fuente.jsonl", ())
        if _text(row.get("id_herramienta_canonica"))
    }
    for relation in source_relations:
        skills.add(_text(relation.get("id_habilidad_canonica")))
        competencies.add(_text(relation.get("id_competencia_canonica")))
        tools.add(_text(relation.get("id_herramienta_canonica")))
    skills.discard("")
    competencies.discard("")
    tools.discard("")
    return skills, competencies, tools


def _relation_matches_scoped_ids(
    relation: Mapping[str, object],
    identity: _IdentityKey,
    scoped_ids: tuple[set[str], set[str], set[str]],
) -> bool:
    skills, competencies, tools = scoped_ids
    tool = _text(relation.get("id_herramienta"))
    return (
        bool(identity[5])
        and _text(relation.get("id_habilidad")) in skills
        and _text(relation.get("id_competencia")) in competencies
        and (not tool or tool in tools)
    )


def _assemble_one(
    package_id: str,
    rows: Sequence[Mapping[str, object]],
    *,
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None,
    relaciones: Sequence[Mapping[str, object]] | None,
    archivos: Mapping[str, Sequence[Mapping[str, object]]] | None,
    index: _PackageAssemblyIndex | None = None,
) -> dict[str, object]:
    ordered = sorted((dict(row) for row in rows), key=_row_sort_key)
    identity = _mapping(ordered[0].get(PACKAGE_SOURCE_IDENTITY_FIELD))
    identity_text = {key: _text(identity.get(key)) for key in IDENTITY_FIELDS}
    identity_key = _identity_key(identity)
    indexed_source_relations = index.source_relations.get(identity_key, ()) if index else ()
    source_package_relations = relaciones_fuente_para_paquete_chh(
        indexed_source_relations if index else (fuentes or {}).get(_SOURCE_RELATIONS_FILE, ()),
        identity,
        package_id=package_id,
    )
    by_type: dict[str, list[dict[str, object]]] = {key: [] for key in _TYPE_ORDER}
    for row in ordered:
        kind = _text(row.get("tipo")).casefold()
        if kind in by_type:
            by_type[kind].append(_component_from_row(row, kind))
    _add_source_components(
        by_type,
        identity,
        fuentes,
        source_package_relations,
        archivos=archivos,
        source_rows=index.sources.get(identity_key) if index else None,
        preselected=bool(index),
    )
    _add_canonical_components(
        by_type,
        identity,
        fuentes,
        archivos,
        source_package_relations,
        scoped_relations=index.coverage_relations.get(identity_key) if index else None,
        preselected=bool(index),
    )
    for kind in by_type:
        by_type[kind] = _unique_components(by_type[kind])
    aliases: list[dict[str, object]] = []
    for row in ordered:
        if not estado_clasificacion(row).auto_deduplicated:
            continue
        evidence = row.get("evidencia")
        aliases.append(
            {
                "id_pendiente": _text(row.get("id_pendiente")),
                "representative_id": _text(estado_clasificacion(row).representative_id),
                "evidence": list(evidence) if isinstance(evidence, list) else [],
                PACKAGE_SOURCE_IDENTITY_FIELD: dict(identity),
            }
        )
    competency_blockers: list[dict[str, str]] = []
    open_rows = [row for row in ordered if _requires_human_decision(row)]
    unresolved_rows = [row for row in ordered if _is_unresolved_row(row)]
    decisions = {
        _text(row.get("decision")).upper() for row in ordered if _text(row.get("decision"))
    }
    decision = next(iter(decisions)) if len(decisions) == 1 else "MIXED" if decisions else None
    package_relations = relaciones_para_paquete_chh(
        index.package_relations.get(identity_key, ()) if index else relaciones or (),
        identity,
        fuentes=fuentes,
        package_id=package_id,
        source_relations=source_package_relations,
        preselected=bool(index),
    )
    package_relations.sort(key=lambda row: tuple(_text(row.get(key)) for key in RELATION_KEYS))
    components = {
        "competencias": by_type["competencia"],
        "habilidades": by_type["habilidad"],
        "herramientas": by_type["herramienta"],
    }
    # These three fields are the package contract consumed by new callers.
    # ``relaciones`` and ``componentes`` remain compatibility aliases for the
    # existing CSV/HITL pipeline, but must not be combined to infer a cartesian
    # CHH relation in a presentation layer.
    # A pending proposal is source evidence, not an accepted canonical edge.
    # Keep the raw relation for HITL, but never project it as canonical until
    # every row in this source package is resolved.
    relaciones_canonicas = (
        []
        if unresolved_rows or competency_blockers
        else _relaciones_canonicas(package_relations, components)
    )
    propuestas_pendientes = [
        _propuesta_pendiente(row)
        for row in ordered
        if _is_unresolved_row(row) and not estado_clasificacion(row).auto_deduplicated
    ]
    structural_error = not components["competencias"]
    return {
        PACKAGE_ID_FIELD: package_id,
        "package_id": package_id,
        PACKAGE_SOURCE_KEY_FIELD: clave_fuente_chh(identity_text),
        "clave_paquete_chh": clave_fuente_chh(identity_text),
        PACKAGE_SOURCE_IDENTITY_FIELD: dict(identity),
        **{key: _text(identity.get(key)) for key in IDENTITY_FIELDS},
        "componentes": components,
        **components,
        "relaciones": package_relations,
        "relationships": package_relations,
        "relaciones_canonicas": relaciones_canonicas,
        "propuestas_pendientes": propuestas_pendientes,
        "competency_blockers": competency_blockers,
        "source_relationships": source_package_relations,
        "source_evidence": {
            "relationships": source_package_relations,
            "rows": ordered,
        },
        "filas": ordered,
        "legacy_rows": ordered,
        "id_pendientes": [_text(row.get("id_pendiente")) for row in ordered],
        "manual_review_rows": [_text(row.get("id_pendiente")) for row in open_rows],
        "alias_ids": [_text(alias["id_pendiente"]) for alias in aliases],
        "aliases": aliases,
        "exact_duplicate_aliases": aliases,
        "flags": sorted(
            {
                _text(flag)
                for row in ordered
                for flag in estado_clasificacion(row).flags
                if _text(flag)
            }
        ),
        "requires_human_decision": bool(open_rows or competency_blockers),
        "requiere_decision": bool(open_rows or competency_blockers),
        "decision": decision,
        "package_decision": decision,
        "decision_state": (
            "STRUCTURAL_ERROR"
            if structural_error
            else "PENDING"
            if unresolved_rows or competency_blockers
            else "MIXED"
            if decision == "MIXED"
            else "DECIDED"
        ),
    }


def _relaciones_canonicas(
    relaciones: Sequence[Mapping[str, object]],
    componentes: Mapping[str, Sequence[Mapping[str, object]]],
) -> list[dict[str, dict[str, str]]]:
    """Project explicit CHH triples without creating a cross-product."""

    nombres: dict[str, dict[str, str]] = {}
    for tipo, grupo in (
        ("competencia", componentes.get("competencias", ())),
        ("habilidad", componentes.get("habilidades", ())),
        ("herramienta", componentes.get("herramientas", ())),
    ):
        nombres[tipo] = {
            _component_identifier(componente): _component_name(componente)
            for componente in grupo
            if _component_identifier(componente)
        }
    triples: list[dict[str, dict[str, str]]] = []
    seen: set[tuple[str, str, str]] = set()
    for relacion in relaciones:
        ids = (
            _text(relacion.get("id_competencia")),
            _text(relacion.get("id_habilidad")),
            _text(relacion.get("id_herramienta")),
        )
        if not ids[0] or not ids[1] or ids in seen:
            continue
        seen.add(ids)
        triples.append(
            {
                "competencia": {"id": ids[0], "nombre": nombres["competencia"].get(ids[0], "")},
                "habilidad": {"id": ids[1], "nombre": nombres["habilidad"].get(ids[1], "")},
                "herramienta": {"id": ids[2], "nombre": nombres["herramienta"].get(ids[2], "")},
            }
        )
    return triples


def _propuesta_pendiente(row: Mapping[str, object]) -> dict[str, object]:
    propuesta = _mapping(row.get("propuesta"))
    descripcion = _text(propuesta.get("descripcion") or row.get("descripcion_fuente"))
    return {
        "tipo": _text(row.get("tipo")),
        "nombre": _usable_display_name(propuesta.get("nombre"), description=descripcion),
        "descripcion": descripcion,
        "id_pendiente": _text(row.get("id_pendiente")),
        "evidencia": _list_value(row.get("evidencia")),
        "source_identity": dict(_mapping(row.get(PACKAGE_SOURCE_IDENTITY_FIELD))),
    }


def _add_source_components(
    by_type: dict[str, list[dict[str, object]]],
    identity: Mapping[str, object],
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None,
    source_relations: Sequence[Mapping[str, object]] = (),
    *,
    archivos: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    source_rows: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    preselected: bool = False,
) -> None:
    if not fuentes:
        return
    skill_catalog_names = _catalog_names_by_id(
        archivos,
        filename="catalogo_habilidades.csv",
        id_key="id_habilidad",
        name_key="nombre_habilidad",
    )
    for kind, (filename, source_id_key, canonical_key, name_key) in _SOURCE_FILES.items():
        for source in (source_rows or fuentes).get(filename, ()):
            if not preselected and not _source_row_matches_package(
                source, kind, identity, fuentes, source_relations
            ):
                continue
            canonical = _text(source.get(canonical_key))
            description = _text(source.get("descripcion_fuente") or source.get("texto_evidencia"))
            name = _usable_display_name(
                source.get(name_key),
                description=description,
                trusted_tool_name=kind == "herramienta",
            )
            if kind == "habilidad" and canonical:
                name = _usable_display_name(
                    skill_catalog_names.get(canonical), description=description
                )
            source_id = _text(source.get(source_id_key))
            if canonical or name or (kind == "competencia" and source_id and source_relations):
                # Source rows are reusable audit evidence and can predate the
                # relation identifier. The component projection is package-local.
                source_identity = dict(identity)
                by_type[kind].append(
                    {
                        "tipo": kind,
                        "id_fuente": source_id,
                        "id_canonico": canonical,
                        f"id_{kind}": canonical,
                        "nombre": name,
                        "nombre_fuente": name,
                        "nombre_propuesto": "",
                        "display_name": name,
                        "estado_nombre": "" if name else "PENDIENTE_CATALOGACION",
                        "descripcion": description,
                        "propuesta": {},
                        "source_identity": source_identity,
                        "source": dict(source),
                        "canonical": bool(canonical),
                    }
                )


def _catalog_names_by_id(
    archivos: Mapping[str, Sequence[Mapping[str, object]]] | None,
    *,
    filename: str,
    id_key: str,
    name_key: str,
) -> dict[str, str]:
    if not archivos:
        return {}
    names_by_id: dict[str, set[str]] = {}
    for row in archivos.get(filename, ()):
        identifier = _text(row.get(id_key))
        if not identifier:
            continue
        names_by_id.setdefault(identifier, set()).add(_text(row.get(name_key)))
    return {
        identifier: next(iter(names))
        for identifier, names in names_by_id.items()
        if len(names) == 1 and next(iter(names))
    }


def relaciones_fuente_para_paquete_chh(
    relaciones: Sequence[Mapping[str, object]],
    identity: Mapping[str, object],
    *,
    package_id: str = "",
) -> list[dict[str, object]]:
    """Keep source coverage attached without treating it as canonical."""

    if not _identity_complete(identity):
        return []
    selected: list[dict[str, object]] = []
    for relation in relaciones:
        if not _source_relation_matches(relation, identity):
            continue
        scoped = dict(relation)
        scoped[PACKAGE_SOURCE_IDENTITY_FIELD] = dict(identity)
        scoped[PACKAGE_ID_FIELD] = package_id or id_paquete_chh(
            {key: _text(identity.get(key)) for key in IDENTITY_FIELDS}
        )
        selected.append(scoped)
    selected.sort(key=lambda row: tuple(_text(row.get(key)) for key in RELATION_KEYS))
    return selected


def _add_canonical_components(
    by_type: dict[str, list[dict[str, object]]],
    identity: Mapping[str, object],
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None,
    archivos: Mapping[str, Sequence[Mapping[str, object]]] | None,
    source_relations: Sequence[Mapping[str, object]] = (),
    *,
    scoped_relations: Sequence[Mapping[str, object]] | None = None,
    preselected: bool = False,
) -> None:
    if not archivos:
        return
    for relation in (
        scoped_relations
        if scoped_relations is not None
        else archivos.get("cobertura_curricular.csv", ())
    ):
        if not preselected and not _relation_scope_matches(
            relation, identity, fuentes, source_relations=source_relations
        ):
            continue
        for kind, (filename, id_key, name_key) in _CATALOGS.items():
            identifier = _text(relation.get(id_key))
            if not identifier:
                continue
            catalog_row = next(
                (
                    item
                    for item in archivos.get(filename, ())
                    if _text(item.get(id_key)) == identifier
                ),
                {},
            )
            by_type[kind].append(
                {
                    "tipo": kind,
                    "id_canonico": identifier,
                    id_key: identifier,
                    "nombre": _usable_display_name(
                        catalog_row.get(name_key),
                        description=_text(
                            catalog_row.get("descripcion_breve")
                            or catalog_row.get("descripcion_breve_herramienta")
                            or catalog_row.get("descripcion_breve_competencia")
                        ),
                        trusted_tool_name=kind == "herramienta",
                    ),
                    "nombre_fuente": "",
                    "nombre_propuesto": "",
                    "display_name": _usable_display_name(
                        catalog_row.get(name_key),
                        description=_text(
                            catalog_row.get("descripcion_breve")
                            or catalog_row.get("descripcion_breve_herramienta")
                            or catalog_row.get("descripcion_breve_competencia")
                        ),
                        trusted_tool_name=kind == "herramienta",
                    ),
                    "estado_nombre": "",
                    "descripcion": _text(
                        catalog_row.get("descripcion_breve")
                        or catalog_row.get("descripcion_breve_herramienta")
                        or catalog_row.get("descripcion_breve_competencia")
                    ),
                    "propuesta": {},
                    "source_identity": dict(identity),
                    "canonical": True,
                }
            )


def _component_from_row(row: Mapping[str, object], kind: str) -> dict[str, object]:
    proposal = _mapping(row.get("propuesta"))
    description = _text(row.get("descripcion_fuente"))
    proposed_name = _usable_display_name(proposal.get("nombre"), description=description)
    source_name = _usable_display_name(
        row.get(f"nombre_{kind}_fuente") or row.get(f"nombre_{kind}"),
        description=description,
        trusted_tool_name=kind == "herramienta",
    )
    name = proposed_name or (source_name if kind != "habilidad" else "")
    proposed_identifier = (
        _text(row.get(f"id_{kind}")) or _text(row.get("id_canonico")) or _text(proposal.get("id"))
    )
    unresolved = _is_unresolved_row(row)
    # A candidate ID suggested during HITL must not become a canonical
    # component merely by travelling in an ``id_canonico`` compatibility
    # field. Preserve it separately so a later explicit ADD can materialize
    # it without merging it into an accepted source projection.
    identifier = "" if unresolved else proposed_identifier
    canonical = not unresolved and bool(
        row.get("canonical") or row.get(f"id_{kind}") or row.get("id_canonico")
    )
    return {
        "tipo": kind,
        "id_pendiente": _text(row.get("id_pendiente")),
        "id_fuente": _text(row.get("id_habilidad_fuente")),
        "id_canonico": identifier,
        "id_canonico_propuesto": proposed_identifier if unresolved else "",
        f"id_{kind}": identifier,
        "nombre": name,
        "nombre_fuente": source_name,
        "nombre_propuesto": proposed_name,
        "display_name": name,
        "estado_nombre": "" if name else "PENDIENTE_CATALOGACION",
        "descripcion": _text(proposal.get("descripcion") or row.get("descripcion_fuente")),
        "propuesta": dict(proposal),
        "estado_resolucion": _text(row.get("estado_resolucion")),
        "decision": _text(row.get("decision")),
        "source_identity": dict(_mapping(row.get(PACKAGE_SOURCE_IDENTITY_FIELD))),
        "row": dict(row),
        "canonical": canonical,
    }


def _unique_components(values: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    canonical_ids = {
        (_text(value.get("tipo")), _component_identifier(value))
        for value in values
        if value.get("canonical") and _component_identifier(value)
    }
    canonical_names = {
        (_text(value.get("tipo")), _normalized_name(_component_name(value)))
        for value in values
        if value.get("canonical") and _component_name(value)
    }
    canonical_source_counts = Counter(
        source_key
        for value in values
        if value.get("canonical") and (source_key := _component_source_key(value)) is not None
    )
    unique: dict[tuple[str, str, str], dict[str, object]] = {}
    for value in values:
        item = dict(value)
        key = _component_key(item, canonical_ids, canonical_names)
        source_key = _component_source_key(item)
        if item.get("canonical") and source_key and canonical_source_counts[source_key] == 1:
            pending_matches = [
                existing_key
                for existing_key, existing in unique.items()
                if (
                    not existing.get("canonical")
                    and not _is_provisional_component(existing)
                    and _has_structured_proposal(existing)
                    and _component_source_key(existing) == source_key
                )
            ]
            if len(pending_matches) == 1:
                unique[pending_matches[0]] = _merge_components(unique[pending_matches[0]], item)
                continue
        if (
            key not in unique
            and not item.get("canonical")
            and not _is_provisional_component(item)
            and _has_structured_proposal(item)
        ):
            canonical_matches = [
                existing_key
                for existing_key, existing in unique.items()
                if existing.get("canonical")
                and source_key
                and _component_source_key(existing) == source_key
            ]
            if len(canonical_matches) == 1:
                key = canonical_matches[0]
        if key in unique:
            unique[key] = _merge_components(unique[key], item)
        else:
            unique[key] = _with_component_provenance(item)
    return sorted(
        unique.values(),
        key=lambda item: (
            _TYPE_ORDER.get(_text(item.get("tipo")), 99),
            _text(item.get("nombre")).casefold(),
            _text(item.get("id_canonico")),
            _text(item.get("id_pendiente")),
        ),
    )


def _component_identifier(value: Mapping[str, object]) -> str:
    kind = _text(value.get("tipo"))
    return _text(value.get(f"id_{kind}") or value.get("id_canonico"))


def _component_name(value: Mapping[str, object]) -> str:
    description = _text(value.get("descripcion"))
    candidates = [
        value.get("nombre"),
        value.get("nombre_propuesto"),
    ]
    if _text(value.get("tipo")).casefold() != "habilidad":
        candidates.append(value.get("nombre_fuente"))
    return next(
        (
            name
            for candidate in candidates
            if (
                name := _usable_display_name(
                    candidate,
                    description=description,
                    trusted_tool_name=(
                        _text(value.get("tipo")).casefold() == "herramienta"
                        and bool(value.get("canonical") or value.get("source"))
                    ),
                )
            )
        ),
        "",
    )


def _component_key(
    value: Mapping[str, object],
    canonical_ids: set[tuple[str, str]],
    canonical_names: set[tuple[str, str]],
) -> tuple[str, str, str]:
    kind = _text(value.get("tipo"))
    identifier = _component_identifier(value)
    if identifier and (value.get("canonical") or (kind, identifier) in canonical_ids):
        return ("canonical", kind, identifier)
    name = _component_name(value)
    normalized = _normalized_name(name)
    if normalized:
        return ("name", kind, normalized)
    source_identity = json.dumps(
        _mapping(value.get(PACKAGE_SOURCE_IDENTITY_FIELD)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        "source",
        kind,
        "|".join(
            (
                source_identity,
                _text(value.get("id_fuente")),
                _text(value.get("id_pendiente")),
            )
        ),
    )


def _component_source_key(value: Mapping[str, object]) -> tuple[str, str, str] | None:
    source_id = _text(value.get("id_fuente"))
    if not source_id:
        return None
    identity = json.dumps(
        _mapping(value.get(PACKAGE_SOURCE_IDENTITY_FIELD)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (_text(value.get("tipo")), identity, source_id)


def _has_structured_proposal(value: Mapping[str, object]) -> bool:
    proposal = _mapping(value.get("propuesta"))
    return bool(_text(proposal.get("nombre") or proposal.get("id")))


def _is_provisional_component(value: Mapping[str, object]) -> bool:
    return (
        bool(_text(value.get("id_canonico_propuesto")))
        or _text(value.get("estado_resolucion")).upper() in _UNRESOLVED_RESOLUTION_STATES
    )


def _with_component_provenance(value: Mapping[str, object]) -> dict[str, object]:
    result = dict(value)
    result["provenance"] = [_component_provenance(value)]
    return result


def _component_provenance(value: Mapping[str, object]) -> dict[str, object]:
    return {
        field: value[field]
        for field in (
            "id_pendiente",
            "id_fuente",
            "id_canonico",
            "id_canonico_propuesto",
            "nombre_propuesto",
            "propuesta",
            "source_identity",
            "source",
            "row",
        )
        if field in value and value[field]
    }


def _merge_components(
    first: Mapping[str, object], second: Mapping[str, object]
) -> dict[str, object]:
    result = dict(first)
    provenance = [
        item
        for item in (_list_value(first.get("provenance")) + [_component_provenance(second)])
        if isinstance(item, Mapping) and item
    ]
    unique_provenance: list[dict[str, object]] = []
    for item in provenance:
        if dict(item) not in unique_provenance:
            unique_provenance.append(dict(item))
    result["provenance"] = unique_provenance

    for field, singular in (
        ("id_pendientes", "id_pendiente"),
        ("id_fuentes", "id_fuente"),
        ("source_identities", "source_identity"),
        ("propuestas", "propuesta"),
    ):
        values: list[object] = []
        for item in (first, second):
            existing = item.get(field)
            candidates = existing if isinstance(existing, list) else [item.get(singular)]
            for candidate in candidates:
                if candidate and candidate not in values:
                    values.append(candidate)
        if values:
            result[field] = values

    proposed_names: list[str] = []
    for item in (first, second):
        name = _usable_display_name(
            item.get("nombre_propuesto"), description=_text(item.get("descripcion"))
        )
        if name and name not in proposed_names:
            proposed_names.append(name)
    if proposed_names:
        result["nombre_propuesto"] = proposed_names[0]
        result["nombres_propuestos"] = proposed_names

    candidates: list[tuple[int, str]] = []
    for item in (first, second):
        name = _component_name(item)
        if not name:
            continue
        if item.get("canonical") and _usable_display_name(
            item.get("nombre"),
            description=_text(item.get("descripcion")),
            trusted_tool_name=(
                _text(item.get("tipo")).casefold() == "herramienta"
                and bool(item.get("canonical") or item.get("source"))
            ),
        ):
            rank = 3
        elif _usable_display_name(
            item.get("nombre_propuesto"), description=_text(item.get("descripcion"))
        ):
            rank = 2
        else:
            rank = 1
        candidates.append((rank, name))
    display_name = max(candidates, key=lambda candidate: candidate[0])[1] if candidates else ""
    result["nombre"] = display_name
    result["display_name"] = display_name
    result["estado_nombre"] = "" if display_name else "PENDIENTE_CATALOGACION"
    result["canonical"] = bool(first.get("canonical") or second.get("canonical"))
    if result["canonical"] and _component_identifier(second) and second.get("canonical"):
        kind = _text(second.get("tipo"))
        result["id_canonico"] = _component_identifier(second)
        result[f"id_{kind}"] = _component_identifier(second)
    return result


def _normalized_name(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", _text(value))
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", without_accents.casefold()).strip()


def _usable_display_name(
    value: object,
    *,
    description: str = "",
    trusted_tool_name: bool = False,
) -> str:
    name = _text(value)
    if not name or _TECHNICAL_NAME.fullmatch(name) or _HASH_NAME.fullmatch(name):
        return ""
    if (
        not trusted_tool_name
        and description
        and _normalized_name(name) == _normalized_name(description)
    ):
        return ""
    return name


def _components(
    package: Mapping[str, object], grouped: Mapping[str, object], key: str, alias: str
) -> list[Mapping[str, object]]:
    values = package.get(key)
    grouped_values = grouped.get(key) or grouped.get(alias)
    if not isinstance(values, list) or not values:
        values = grouped_values
    elif isinstance(grouped_values, list) and not any(
        _text(
            value.get("id_canonico")
            or value.get("id_competencia")
            or value.get("id_habilidad")
            or value.get("id_herramienta")
        )
        for value in values
        if isinstance(value, Mapping)
    ):
        values = grouped_values
    return (
        [value for value in values if isinstance(value, Mapping)]
        if isinstance(values, list)
        else []
    )


def _component_ids(values: Sequence[Mapping[str, object]], kind: str) -> set[str]:
    return {
        _text(value.get(f"id_{kind}") or value.get("id_canonico"))
        for value in values
        if _text(value.get(f"id_{kind}") or value.get("id_canonico"))
    }


def _relationships(package: Mapping[str, object]) -> list[Mapping[str, object] | Sequence[object]]:
    value = package.get("relaciones") or package.get("relationships")
    return (
        [item for item in value if isinstance(item, (Mapping, tuple, list))]
        if isinstance(value, list)
        else []
    )


def _relation_values(value: Mapping[str, object] | Sequence[object]) -> tuple[str, ...] | None:
    if isinstance(value, Mapping):
        values = tuple(_text(value.get(key)) for key in RELATION_KEYS)
    elif isinstance(value, (tuple, list)) and len(value) in (5, 6):
        values = tuple(_text(item) for item in value)
        if len(values) == 5:
            values = ("",) + values
    else:
        return None
    return values if any(values) else None


def _scope_matches(row: Mapping[str, object], identity: Mapping[str, object]) -> bool:
    row_package, expected_package = (
        _first(row, *PACKAGE_ID_ALIASES),
        _first(identity, *PACKAGE_ID_ALIASES),
    )
    if not _identity_complete(identity):
        return False
    if row_package and expected_package and row_package != expected_package:
        return False
    aliases = {
        "id_ejecucion": ("id_ejecucion", "execution_id"),
        "carrera": ("carrera", "career"),
        "periodo": ("periodo", "period"),
        "id_curso": ("id_curso", "course_id"),
        "id_silabo": ("id_silabo", "syllabus_id", "silabo"),
        "id_habilidad_fuente": ("id_habilidad_fuente", "source_skill_id"),
        SOURCE_RELATION_ID_FIELD: (
            SOURCE_RELATION_ID_FIELD,
            "id_relacion_fuente",
            "source_relation_id",
        ),
    }
    row_identity = _mapping(row.get(PACKAGE_SOURCE_IDENTITY_FIELD))
    if row_identity:
        return _identity_equal(row_identity, identity)
    return all(
        not _text(identity.get(key)) or _first(row, *keys) == _text(identity.get(key))
        for key, keys in aliases.items()
    )


def relaciones_para_paquete_chh(
    relaciones: Sequence[Mapping[str, object]],
    identity: Mapping[str, object],
    *,
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    package_id: str = "",
    source_relations: Sequence[Mapping[str, object]] | None = None,
    preselected: bool = False,
) -> list[dict[str, object]]:
    """Return only relations proven to belong to one complete source package."""

    if not _identity_complete(identity):
        return []
    scoped_source_relations = (
        source_relations
        if source_relations is not None
        else _source_relations_for_identity(
            (fuentes or {}).get(_SOURCE_RELATIONS_FILE, ()), identity
        )
    )
    selected: list[dict[str, object]] = []
    for relation in relaciones:
        if not preselected and not _relation_scope_matches(
            relation, identity, fuentes, source_relations=scoped_source_relations
        ):
            continue
        scoped = dict(relation)
        scoped[PACKAGE_SOURCE_IDENTITY_FIELD] = dict(identity)
        scoped["id_habilidad_fuente"] = _text(identity.get("id_habilidad_fuente"))
        scoped[PACKAGE_ID_FIELD] = package_id or id_paquete_chh(
            {key: _text(identity.get(key)) for key in IDENTITY_FIELDS}
        )
        selected.append(scoped)
    return selected


def _relation_scope_matches(
    relation: Mapping[str, object],
    identity: Mapping[str, object],
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None,
    *,
    source_relations: Sequence[Mapping[str, object]] = (),
) -> bool:
    if _scope_matches(relation, identity):
        return True
    relation_course = _first(relation, "id_curso", "course_id")
    relation_syllabus = _first(relation, "id_silabo", "syllabus_id", "silabo")
    if relation_course != _text(identity.get("id_curso")) or relation_syllabus != _text(
        identity.get("id_silabo")
    ):
        return False
    if not fuentes:
        return False
    source_skill = _text(identity.get("id_habilidad_fuente"))
    scoped_skills = {
        _text(item.get("id_habilidad_canonica"))
        for item in fuentes.get("habilidades_fuente.jsonl", ())
        if _scope_matches(item, identity) and _text(item.get("id_habilidad_canonica"))
    }
    scoped_competencies = {
        _text(item.get("id_competencia_canonica"))
        for item in fuentes.get("competencias_fuente.jsonl", ())
        if _source_row_matches_package(item, "competencia", identity, fuentes, source_relations)
        and _text(item.get("id_competencia_canonica"))
    }
    scoped_tools = {
        _text(item.get("id_herramienta_canonica"))
        for item in fuentes.get("herramientas_fuente.jsonl", ())
        if _scope_matches(item, identity) and _text(item.get("id_herramienta_canonica"))
    }
    for source_relation in source_relations or _source_relations_for_identity(
        fuentes.get(_SOURCE_RELATIONS_FILE, ()), identity
    ):
        if not _source_relation_matches(source_relation, identity):
            continue
        scoped_skills.add(_text(source_relation.get("id_habilidad_canonica")))
        scoped_competencies.add(_text(source_relation.get("id_competencia_canonica")))
        scoped_tools.add(_text(source_relation.get("id_herramienta_canonica")))
    scoped_skills.discard("")
    scoped_competencies.discard("")
    scoped_tools.discard("")
    return (
        bool(source_skill)
        and _text(relation.get("id_habilidad")) in scoped_skills
        and _text(relation.get("id_competencia")) in scoped_competencies
        and (
            not _text(relation.get("id_herramienta"))
            or _text(relation.get("id_herramienta")) in scoped_tools
        )
    )


def _source_row_matches_package(
    source: Mapping[str, object],
    kind: str,
    identity: Mapping[str, object],
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None,
    source_relations: Sequence[Mapping[str, object]] = (),
) -> bool:
    if _text(identity.get(SOURCE_RELATION_ID_FIELD)):
        return _source_row_matches_relation_unit(source, kind, identity, source_relations)
    if _scope_matches(source, identity):
        return True
    if kind != "competencia" or not fuentes:
        return False
    source_id = _text(source.get("id_competencia_fuente"))
    return bool(source_id) and any(
        _source_relation_matches(relation, identity)
        and _text(relation.get("id_competencia_fuente")) == source_id
        for relation in (
            source_relations
            or _source_relations_for_identity(fuentes.get(_SOURCE_RELATIONS_FILE, ()), identity)
        )
    )


def _source_row_matches_relation_unit(
    source: Mapping[str, object],
    kind: str,
    identity: Mapping[str, object],
    source_relations: Sequence[Mapping[str, object]],
) -> bool:
    source_key = {
        "competencia": "id_competencia_fuente",
        "habilidad": "id_habilidad_fuente",
        "herramienta": "id_herramienta_fuente",
    }[kind]
    source_id = _text(source.get(source_key))
    return bool(source_id) and any(
        _source_relation_matches(relation, identity)
        and _text(relation.get(source_key)) == source_id
        for relation in source_relations
    )


def _source_relation_matches(
    relation: Mapping[str, object], identity: Mapping[str, object]
) -> bool:
    if not _identity_complete(identity):
        return False
    relation_execution = _text(relation.get("id_ejecucion"))
    if relation_execution and relation_execution != _text(identity.get("id_ejecucion")):
        return False
    return (
        _text(relation.get("id_curso")) == _text(identity.get("id_curso"))
        and _text(relation.get("id_silabo")) == _text(identity.get("id_silabo"))
        and _text(relation.get("id_habilidad_fuente")) == _text(identity.get("id_habilidad_fuente"))
        and (
            not _text(identity.get(SOURCE_RELATION_ID_FIELD))
            or _text(relation.get(SOURCE_RELATION_ID_FIELD))
            == _text(identity.get(SOURCE_RELATION_ID_FIELD))
        )
    )


def _source_relations_for_identity(
    relations: Sequence[Mapping[str, object]], identity: Mapping[str, object]
) -> list[Mapping[str, object]]:
    return [relation for relation in relations if _source_relation_matches(relation, identity)]


def _identity_complete(identity: Mapping[str, object]) -> bool:
    return all(_text(identity.get(key)) for key in _REQUIRED_IDENTITY_FIELDS)


def _identity_equal(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    return all(_text(left.get(key)) == _text(right.get(key)) for key in IDENTITY_FIELDS)


def _rows(package: Mapping[str, object]) -> list[Mapping[str, object]]:
    value = package.get("filas") or package.get("legacy_rows")
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _package_waiting_for_decision(package: Mapping[str, object]) -> bool:
    return bool(package.get("requires_human_decision") or package.get("requiere_decision")) or (
        _text(package.get("decision_state")).upper() == "PENDING"
    )


def _requires_human_decision(row: Mapping[str, object]) -> bool:
    if estado_clasificacion(row).auto_deduplicated:
        return False
    if not _text(row.get("decision")) and estado_clasificacion(row).requires_human_decision:
        return True
    resolution = _text(row.get("estado_resolucion")).upper()
    return resolution in _UNRESOLVED_RESOLUTION_STATES - {"MANTENIDA_PENDIENTE"}


def _is_unresolved_row(row: Mapping[str, object]) -> bool:
    if estado_clasificacion(row).auto_deduplicated:
        return False
    resolution = _text(row.get("estado_resolucion")).upper()
    if resolution in _UNRESOLVED_RESOLUTION_STATES or resolution.startswith("PENDIENTE_"):
        return True
    return _text(row.get("decision")).upper() == "KEEP_PENDING"


def _row_sort_key(row: Mapping[str, object]) -> tuple[object, ...]:
    kind, proposal = _text(row.get("tipo")).casefold(), _mapping(row.get("propuesta"))
    return (
        _TYPE_ORDER.get(kind, 99),
        _text(proposal.get("nombre") or proposal.get("id")).casefold(),
        _text(row.get("id_pendiente")),
    )


def _first(mapping: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        if _text(mapping.get(key)):
            return _text(mapping.get(key))
    return ""


def _text(value: object) -> str:
    return str(value or "").strip()


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_value(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _finding(code: str, message: str, package_id: str, *, fila: int | None = None) -> Hallazgo:
    return Hallazgo(
        codigo=code,
        severidad="error",
        mensaje=message,
        hoja="cobertura_curricular.csv",
        fila=fila,
        detalle=package_id,
    )
