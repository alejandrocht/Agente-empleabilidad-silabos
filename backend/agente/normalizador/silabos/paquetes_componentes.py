"""Pure CHH component projection used by package assembly."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from agente.normalizador.silabos.paquetes_componentes_nombres import (  # noqa: F401
    _HASH_NAME,
    _TECHNICAL_NAME,
    _TYPE_ORDER,
    _UNRESOLVED_RESOLUTION_STATES,
    PACKAGE_SOURCE_IDENTITY_FIELD,
    Counter,
    _component_identifier,
    _component_key,
    _component_name,
    _component_provenance,
    _component_source_key,
    _has_structured_proposal,
    _is_provisional_component,
    _merge_components,
    _normalized_name,
    _unique_components,
    _usable_display_name,
    _with_component_provenance,
    re,
    unicodedata,
)

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
    "habilidad": ("catalogo_logros.csv", "id_logro", "nombre_logro"),
    "herramienta": ("catalogo_herramientas.csv", "id_herramienta", "nombre_herramienta"),
}


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
            _text(relacion.get("id_logro")),
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
        filename="catalogo_logros.csv",
        id_key="id_logro",
        name_key="nombre_logro",
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
