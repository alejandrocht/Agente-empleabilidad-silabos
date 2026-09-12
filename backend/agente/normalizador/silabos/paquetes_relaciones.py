"""Source-scoped CHH relation selection used by package assembly."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from agente.normalizador.silabos import paquetes_componentes as _paquetes_componentes

PACKAGE_ID_FIELD = "id_paquete_chh"
PACKAGE_ID_ALIASES = (PACKAGE_ID_FIELD, "package_id", "id_paquete")
PACKAGE_SOURCE_KEY_FIELD = "package_source_key"
PACKAGE_SOURCE_IDENTITY_FIELD = _paquetes_componentes.PACKAGE_SOURCE_IDENTITY_FIELD
_REQUIRED_IDENTITY_FIELDS = (
    "id_ejecucion",
    "carrera",
    "periodo",
    "id_curso",
    "id_silabo",
    "id_habilidad_fuente",
)
SOURCE_RELATION_ID_FIELD = "id_cob_curricular"
IDENTITY_FIELDS = (*_REQUIRED_IDENTITY_FIELDS, SOURCE_RELATION_ID_FIELD)
RELATION_KEYS = (
    "id_cob_curricular",
    "id_curso",
    "id_silabo",
    "id_competencia",
    "id_logro",
    "id_herramienta",
)
_SOURCE_RELATIONS_FILE = "cobertura_curricular_fuente.jsonl"

_TYPE_ORDER = _paquetes_componentes._TYPE_ORDER
_UNRESOLVED_RESOLUTION_STATES = _paquetes_componentes._UNRESOLVED_RESOLUTION_STATES
_SOURCE_FILES = _paquetes_componentes._SOURCE_FILES
_CATALOGS = _paquetes_componentes._CATALOGS
_TECHNICAL_NAME = _paquetes_componentes._TECHNICAL_NAME
_HASH_NAME = _paquetes_componentes._HASH_NAME
project_components = _paquetes_componentes.project_components
_relaciones_canonicas = _paquetes_componentes._relaciones_canonicas
_propuesta_pendiente = _paquetes_componentes._propuesta_pendiente
_add_source_components = _paquetes_componentes._add_source_components
_catalog_names_by_id = _paquetes_componentes._catalog_names_by_id
_add_canonical_components = _paquetes_componentes._add_canonical_components
_component_from_row = _paquetes_componentes._component_from_row
_unique_components = _paquetes_componentes._unique_components
_component_identifier = _paquetes_componentes._component_identifier
_component_name = _paquetes_componentes._component_name
_component_key = _paquetes_componentes._component_key
_component_source_key = _paquetes_componentes._component_source_key
_has_structured_proposal = _paquetes_componentes._has_structured_proposal
_is_provisional_component = _paquetes_componentes._is_provisional_component
_with_component_provenance = _paquetes_componentes._with_component_provenance
_component_provenance = _paquetes_componentes._component_provenance
_merge_components = _paquetes_componentes._merge_components
_normalized_name = _paquetes_componentes._normalized_name
_usable_display_name = _paquetes_componentes._usable_display_name
Counter = _paquetes_componentes.Counter
re = _paquetes_componentes.re
unicodedata = _paquetes_componentes.unicodedata

_IdentityKey = tuple[str, str, str, str, str, str, str]
_CourseSyllabusKey = tuple[str, str]
_PackageIdFactory = Callable[[Mapping[str, str]], str]


@dataclass(frozen=True)
class _PackageAssemblyIndex:
    """Immutable, call-local selections for source-scoped package assembly."""

    source_relations: Mapping[_IdentityKey, tuple[Mapping[str, object], ...]]
    sources: Mapping[_IdentityKey, Mapping[str, tuple[Mapping[str, object], ...]]]
    coverage_relations: Mapping[_IdentityKey, tuple[Mapping[str, object], ...]]
    package_relations: Mapping[_IdentityKey, tuple[Mapping[str, object], ...]]


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
        for filename, *_ in _paquetes_componentes._SOURCE_FILES.values()
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
        for kind, (filename, *_rest) in _paquetes_componentes._SOURCE_FILES.items():
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
        and _text(relation.get("id_logro")) in skills
        and _text(relation.get("id_competencia")) in competencies
        and (not tool or tool in tools)
    )


def relaciones_fuente_para_paquete_chh(
    relaciones: Sequence[Mapping[str, object]],
    identity: Mapping[str, object],
    *,
    package_id: str = "",
    id_paquete: _PackageIdFactory,
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
        scoped[PACKAGE_ID_FIELD] = package_id or id_paquete(
            {key: _text(identity.get(key)) for key in IDENTITY_FIELDS}
        )
        selected.append(scoped)
    selected.sort(key=lambda row: tuple(_text(row.get(key)) for key in RELATION_KEYS))
    return selected


def relaciones_para_paquete_chh(
    relaciones: Sequence[Mapping[str, object]],
    identity: Mapping[str, object],
    *,
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    package_id: str = "",
    source_relations: Sequence[Mapping[str, object]] | None = None,
    preselected: bool = False,
    id_paquete: _PackageIdFactory,
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
        scoped[PACKAGE_ID_FIELD] = package_id or id_paquete(
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
        and _text(relation.get("id_logro")) in scoped_skills
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


def _identity_complete(identity: Mapping[str, object]) -> bool:
    return all(_text(identity.get(key)) for key in _REQUIRED_IDENTITY_FIELDS)


def _identity_equal(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    return all(_text(left.get(key)) == _text(right.get(key)) for key in IDENTITY_FIELDS)


def _first(mapping: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        if _text(mapping.get(key)):
            return _text(mapping.get(key))
    return ""


def _text(value: object) -> str:
    return str(value or "").strip()


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}
