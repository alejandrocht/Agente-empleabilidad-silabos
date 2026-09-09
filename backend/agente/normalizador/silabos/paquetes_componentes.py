"""Pure CHH component projection used by package assembly."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

PACKAGE_SOURCE_IDENTITY_FIELD = "source_identity"
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


class _RelationScopeMatcher(Protocol):
    def __call__(
        self,
        relation: Mapping[str, object],
        identity: Mapping[str, object],
        fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None,
        *,
        source_relations: Sequence[Mapping[str, object]] = (),
    ) -> bool: ...


def project_components(
    rows: Sequence[Mapping[str, object]],
    identity: Mapping[str, object],
    *,
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None,
    archivos: Mapping[str, Sequence[Mapping[str, object]]] | None,
    source_relations: Sequence[Mapping[str, object]] = (),
    source_rows: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    scoped_relations: Sequence[Mapping[str, object]] | None = None,
    preselected: bool = False,
    is_unresolved_row: Callable[[Mapping[str, object]], bool],
    source_row_matches_package: Callable[
        [
            Mapping[str, object],
            str,
            Mapping[str, object],
            Mapping[str, Sequence[Mapping[str, object]]] | None,
            Sequence[Mapping[str, object]],
        ],
        bool,
    ],
    relation_scope_matches: _RelationScopeMatcher,
) -> dict[str, list[dict[str, object]]]:
    """Project source, catalog and pending rows without importing package assembly."""

    by_type: dict[str, list[dict[str, object]]] = {key: [] for key in _TYPE_ORDER}
    for row in rows:
        kind = _text(row.get("tipo")).casefold()
        if kind in by_type:
            by_type[kind].append(
                _component_from_row(row, kind, is_unresolved_row=is_unresolved_row)
            )
    _add_source_components(
        by_type,
        identity,
        fuentes,
        source_relations,
        archivos=archivos,
        source_rows=source_rows,
        preselected=preselected,
        source_row_matches_package=source_row_matches_package,
    )
    _add_canonical_components(
        by_type,
        identity,
        fuentes,
        archivos,
        source_relations,
        scoped_relations=scoped_relations,
        preselected=preselected,
        relation_scope_matches=relation_scope_matches,
    )
    return {kind: _unique_components(values) for kind, values in by_type.items()}


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
    source_row_matches_package: Callable[
        [
            Mapping[str, object],
            str,
            Mapping[str, object],
            Mapping[str, Sequence[Mapping[str, object]]] | None,
            Sequence[Mapping[str, object]],
        ],
        bool,
    ]
    | None = None,
) -> None:
    if not fuentes:
        return
    if source_row_matches_package is None:
        source_row_matches_package = _default_source_row_matches_package
    skill_catalog_names = _catalog_names_by_id(
        archivos,
        filename="catalogo_habilidades.csv",
        id_key="id_habilidad",
        name_key="nombre_habilidad",
    )
    for kind, (filename, source_id_key, canonical_key, name_key) in _SOURCE_FILES.items():
        for source in (source_rows or fuentes).get(filename, ()):
            if not preselected and not source_row_matches_package(
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


def _add_canonical_components(
    by_type: dict[str, list[dict[str, object]]],
    identity: Mapping[str, object],
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None,
    archivos: Mapping[str, Sequence[Mapping[str, object]]] | None,
    source_relations: Sequence[Mapping[str, object]] = (),
    *,
    scoped_relations: Sequence[Mapping[str, object]] | None = None,
    preselected: bool = False,
    relation_scope_matches: _RelationScopeMatcher | None = None,
) -> None:
    if not archivos:
        return
    matcher: _RelationScopeMatcher = relation_scope_matches or _default_relation_scope_matches
    relations = (
        scoped_relations
        if scoped_relations is not None
        else archivos.get("cobertura_curricular.csv", ())
    )
    for relation in relations:
        if not preselected and not matcher(
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
            description = _text(
                catalog_row.get("descripcion_breve")
                or catalog_row.get("descripcion_breve_herramienta")
                or catalog_row.get("descripcion_breve_competencia")
            )
            name = _usable_display_name(
                catalog_row.get(name_key),
                description=description,
                trusted_tool_name=kind == "herramienta",
            )
            by_type[kind].append(
                {
                    "tipo": kind,
                    "id_canonico": identifier,
                    id_key: identifier,
                    "nombre": name,
                    "nombre_fuente": "",
                    "nombre_propuesto": "",
                    "display_name": name,
                    "estado_nombre": "",
                    "descripcion": description,
                    "propuesta": {},
                    "source_identity": dict(identity),
                    "canonical": True,
                }
            )


def _component_from_row(
    row: Mapping[str, object],
    kind: str,
    *,
    is_unresolved_row: Callable[[Mapping[str, object]], bool] | None = None,
) -> dict[str, object]:
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
    unresolved = (is_unresolved_row or _default_is_unresolved_row)(row)
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
    candidates = [value.get("nombre"), value.get("nombre_propuesto")]
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
            field_values: list[object] = (
                list(existing) if isinstance(existing, list) else [item.get(singular)]
            )
            for candidate in field_values:
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
    display_name = ""
    if candidates:
        display_name = max(candidates, key=lambda candidate: candidate[0])[1]
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


def _default_is_unresolved_row(row: Mapping[str, object]) -> bool:
    resolution = _text(row.get("estado_resolucion")).upper()
    return resolution in _UNRESOLVED_RESOLUTION_STATES or resolution.startswith("PENDIENTE_")


def _default_source_row_matches_package(
    source: Mapping[str, object],
    _kind: str,
    identity: Mapping[str, object],
    _fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None,
    _source_relations: Sequence[Mapping[str, object]],
) -> bool:
    source_identity = _mapping(source.get(PACKAGE_SOURCE_IDENTITY_FIELD))
    if source_identity:
        return source_identity == _mapping(identity)
    return all(
        not _text(identity.get(key)) or _text(source.get(key)) == _text(identity.get(key))
        for key in (
            "id_ejecucion",
            "carrera",
            "periodo",
            "id_curso",
            "id_silabo",
            "id_habilidad_fuente",
        )
    )


def _default_relation_scope_matches(
    relation: Mapping[str, object],
    identity: Mapping[str, object],
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None,
    *,
    source_relations: Sequence[Mapping[str, object]] = (),
) -> bool:
    del fuentes
    return _default_source_row_matches_package(relation, "", identity, None, source_relations)


def _text(value: object) -> str:
    return str(value or "").strip()


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_value(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []
