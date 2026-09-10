"""Closed catalog resolution for the isolated LangExtract diagnostic runner."""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz, process, utils

_CATALOGS = {
    "competencia": (
        "catalogo_competencias.csv",
        "id_competencia",
        "nombre_competencia",
        (
            "id_competencia",
            "nombre_competencia",
            "descripcion_breve_competencia",
            "tipo_competencia",
        ),
    ),
    "habilidad": (
        "catalogo_habilidades.csv",
        "id_habilidad",
        "nombre_habilidad",
        ("id_habilidad", "nombre_habilidad", "descripcion_breve"),
    ),
    "herramienta": (
        "catalogo_herramientas.csv",
        "id_herramienta",
        "nombre_herramienta",
        ("id_herramienta", "nombre_herramienta", "descripcion_breve_herramienta"),
    ),
}
_SYLLABUS_METADATA = {
    "career": (
        re.compile(r"(?im)^\s*(?:carrera|career)\s*:\s*(.+?)\s*$"),
        re.compile(r"(?im)^\s*carrera\s+de\s+(.+?)\s*$"),
    ),
    "period": (
        re.compile(r"(?im)^\s*(?:periodo|per[ií]odo|period)\s*:\s*(.+?)\s*$"),
        re.compile(r"(?im)^\s*s[ií]labo\s+(\d{4}-\d+)\s*$"),
    ),
}
_REFERENCE_SCORE_CUTOFF = 75


@dataclass(frozen=True, slots=True)
class CatalogSelection:
    directory: Path
    career: str
    period: str
    version: str


@dataclass(frozen=True, slots=True)
class ReferenceCatalogSelection:
    """Advisory catalog scope; it intentionally carries no canonical metadata."""

    directory: Path


@dataclass(frozen=True, slots=True)
class _Term:
    identifier: str
    name: str


@dataclass(frozen=True, slots=True)
class _ReferenceTerm:
    name: str
    description: str
    source: str
    kind: str


class _CatalogError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CatalogPreflightError(ValueError):
    """Raised before extraction when the selected immutable catalog is unusable."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _Catalog:
    def __init__(
        self,
        selection: CatalogSelection,
        terms: Mapping[str, tuple[_Term, ...]],
        aliases: Mapping[str, Mapping[str, _Term]],
        alias_literals: Mapping[str, tuple[str, ...]],
    ) -> None:
        self.selection = selection
        self.terms = terms
        self.aliases = aliases
        self.alias_literals = alias_literals
        self._by_literal = {
            kind: _term_index(catalog_terms, _literal_key)
            for kind, catalog_terms in terms.items()
        }
        self._by_name = {
            kind: _term_index(catalog_terms, _key)
            for kind, catalog_terms in terms.items()
        }

    def candidates(self, kind: str, proposal: str) -> tuple[_Term, ...]:
        literal_matches = self._by_literal[kind].get(_literal_key(proposal))
        if literal_matches is not None:
            return literal_matches
        normalized_matches = self._by_name[kind].get(_key(proposal))
        if normalized_matches is not None:
            return normalized_matches
        term = self.aliases[kind].get(_key(proposal))
        return (term,) if term is not None else ()

    def resolve(self, kind: str, proposal: str) -> tuple[_Term | None, str | None]:
        key = _key(proposal)
        if not key:
            return None, "CATALOGO_PROPUESTA_VACIA"
        matches = self.candidates(kind, proposal)
        if len(matches) == 1:
            return matches[0], None
        if matches:
            return None, "CATALOGO_NOMBRE_AMBIGUO"
        return None, _missing_code(kind)


class _ToolCatalog:
    """Exact tool terms loaded from a standalone catalog CSV."""

    def __init__(self, terms: tuple[_Term, ...]) -> None:
        self.terms = {"herramienta": terms}
        self.alias_literals = {"herramienta": ()}
        self._by_literal = _term_index(terms, _literal_key)
        self._by_name = _term_index(terms, _key)

    def candidates(self, kind: str, proposal: str) -> tuple[_Term, ...]:
        if kind != "herramienta":
            raise ValueError(f"Unsupported standalone catalog kind: {kind}")
        literal_matches = self._by_literal.get(_literal_key(proposal))
        if literal_matches is not None:
            return literal_matches
        normalized_matches = self._by_name.get(_key(proposal))
        return normalized_matches if normalized_matches is not None else ()

    def resolve(self, kind: str, proposal: str) -> tuple[_Term | None, str | None]:
        matches = self.candidates(kind, proposal)
        if len(matches) == 1:
            return matches[0], None
        if matches:
            return None, "CATALOGO_NOMBRE_AMBIGUO"
        return None, _missing_code(kind)


class _ReferenceCatalog:
    def __init__(
        self,
        selection: ReferenceCatalogSelection,
        terms: Mapping[str, tuple[_ReferenceTerm, ...]],
        aliases: Mapping[str, tuple[tuple[str, _ReferenceTerm], ...]],
    ) -> None:
        self.selection = selection
        self.terms = terms
        self.aliases = aliases

    def suggest(self, kind: str, proposal: object) -> list[dict[str, object]]:
        if not isinstance(proposal, str) or not proposal.strip():
            return []
        aliases = self.aliases[kind]
        matches = process.extract(
            proposal,
            [alias for alias, _ in aliases],
            scorer=fuzz.WRatio,
            processor=utils.default_process,
            limit=3,
            score_cutoff=_REFERENCE_SCORE_CUTOFF,
        )
        candidates: list[dict[str, object]] = []
        seen: set[tuple[str, str, str]] = set()
        for _, score, index in matches:
            term = aliases[index][1]
            key = (term.source, term.kind, term.name)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "nombre": term.name,
                    "descripcion": term.description,
                    "score": round(float(score), 2),
                    "catalog_source": term.source,
                    "catalog_type": term.kind,
                }
            )
        return candidates


def resolve_catalog_document(
    catalog: _Catalog,
    reasoned_text: str,
    syllabus_text: str,
    packages: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Return canonical diagnostic fields without changing the raw LangExtract output."""

    metadata = _syllabus_metadata(syllabus_text)
    if not _metadata_matches(metadata, catalog.selection):
        return _pending_document(packages, "CATALOGO_METADATA_NO_COINCIDE", catalog.selection)

    serialized_packages = [_resolve_package(catalog, package) for package in packages]
    detected_tools = _tool_mentions(catalog, syllabus_text)
    unlinked = _resolve_tools(
        catalog, reasoned_text, syllabus_text, packages, serialized_packages
    )
    return {
        "catalogo": {
            "estado": "RESUELTO",
            "career": catalog.selection.career,
            "period": catalog.selection.period,
            "version": catalog.selection.version,
        },
        "paquetes": serialized_packages,
        "herramientas_detectadas": [mention for mention, _, _ in detected_tools],
        "herramientas_sin_vinculo": unlinked,
    }


def detect_catalog_tools(
    catalog: _Catalog | _ToolCatalog, syllabus_text: str
) -> list[dict[str, object]]:
    """Detect exact canonical tool mentions anywhere in the supplied syllabus text."""
    return [mention for mention, _, _ in _tool_mentions(catalog, syllabus_text)]


def suggest_reference_catalog_document(
    catalog: _ReferenceCatalog, packages: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    """Attach HITL-only candidate rankings without publishing catalog identities."""

    serialized_packages: list[dict[str, object]] = []
    for package in packages:
        result = dict(package)
        tools = package.get("herramientas")
        reference: dict[str, object] = {
            kind: {
                "propuesta": package.get(f"{kind}_propuesta"),
                "candidatos_humanos": catalog.suggest(
                    kind, package.get(f"{kind}_propuesta")
                ),
            }
            for kind in ("competencia", "habilidad")
        }
        reference["herramientas"] = (
            [
                {
                    "propuesta": tool,
                    "candidatos_humanos": catalog.suggest("herramienta", tool),
                }
                for tool in tools
                if isinstance(tool, str) and tool.strip()
            ]
            if isinstance(tools, list)
            else []
        )
        result["referencia"] = reference
        serialized_packages.append(result)
    return {
        "catalogo_referencia": {
            "modo": "reference_only",
            "alcance": str(catalog.selection.directory),
        },
        "paquetes": serialized_packages,
    }


def preflight_catalog(selection: CatalogSelection) -> _Catalog:
    """Load the selected catalog once, before a document can reach the extractor."""
    try:
        return _load_catalog(selection)
    except _CatalogError as error:
        raise CatalogPreflightError(error.code) from error


def preflight_tool_catalog(path: Path) -> _ToolCatalog:
    """Load a standalone tool catalog once before local detection."""
    _, identifier_column, name_column, headers = _CATALOGS["herramienta"]
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != headers:
                raise _CatalogError("CATALOGO_CSV_INVALIDO")
            terms = tuple(
                _Term(row.get(identifier_column, "").strip(), row.get(name_column, "").strip())
                for row in reader
            )
    except OSError as error:
        raise CatalogPreflightError("CATALOGO_CSV_INVALIDO") from error
    if not terms or any(not term.identifier or not _key(term.name) for term in terms):
        raise CatalogPreflightError("CATALOGO_CSV_INVALIDO")
    if len({term.identifier for term in terms}) != len(terms):
        raise CatalogPreflightError("CATALOGO_IDENTIFICADOR_DUPLICADO")
    return _ToolCatalog(terms)


def preflight_reference_catalog(selection: ReferenceCatalogSelection) -> _ReferenceCatalog:
    """Load an advisory catalog without requiring or reading canonical metadata."""
    try:
        terms = {kind: _load_reference_terms(selection.directory, kind) for kind in _CATALOGS}
        return _ReferenceCatalog(
            selection, terms, _load_reference_aliases(selection.directory, terms)
        )
    except _CatalogError as error:
        raise CatalogPreflightError(error.code) from error


def _load_catalog(selection: CatalogSelection) -> _Catalog:
    if not all(_key(value) for value in (selection.career, selection.period, selection.version)):
        raise _CatalogError("CATALOGO_SELECCION_INVALIDA")
    metadata_path = selection.directory / "catalogo_metadata.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise _CatalogError("CATALOGO_METADATA_INVALIDA") from error
    if not isinstance(metadata, dict) or not _selection_matches_metadata(selection, metadata):
        raise _CatalogError("CATALOGO_SELECCION_NO_COINCIDE")

    terms = {kind: _load_terms(selection.directory, kind) for kind in _CATALOGS}
    aliases, alias_literals = _load_aliases(metadata, terms)
    return _Catalog(selection, terms, aliases, alias_literals)


def _load_terms(directory: Path, kind: str) -> tuple[_Term, ...]:
    filename, identifier_column, name_column, headers = _CATALOGS[kind]
    try:
        with (directory / filename).open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != headers:
                raise _CatalogError("CATALOGO_CSV_INVALIDO")
            terms = tuple(
                _Term(row.get(identifier_column, "").strip(), row.get(name_column, "").strip())
                for row in reader
            )
    except OSError as error:
        raise _CatalogError("CATALOGO_CSV_INVALIDO") from error
    if not terms or any(not term.identifier or not _key(term.name) for term in terms):
        raise _CatalogError("CATALOGO_CSV_INVALIDO")
    if len({term.identifier for term in terms}) != len(terms):
        raise _CatalogError("CATALOGO_IDENTIFICADOR_DUPLICADO")
    return terms


def _load_reference_terms(directory: Path, kind: str) -> tuple[_ReferenceTerm, ...]:
    filename, _, name_column, headers = _CATALOGS[kind]
    try:
        with (directory / filename).open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != headers:
                raise _CatalogError("CATALOGO_REFERENCIA_CSV_INVALIDO")
            terms = tuple(
                _ReferenceTerm(
                    row.get(name_column, "").strip(),
                    row.get(headers[2], "").strip(),
                    filename,
                    kind,
                )
                for row in reader
            )
    except OSError as error:
        raise _CatalogError("CATALOGO_REFERENCIA_CSV_INVALIDO") from error
    if not terms or any(not _key(term.name) for term in terms):
        raise _CatalogError("CATALOGO_REFERENCIA_CSV_INVALIDO")
    return terms


def _load_aliases(
    metadata: Mapping[str, object], terms: Mapping[str, tuple[_Term, ...]]
) -> tuple[dict[str, dict[str, _Term]], dict[str, tuple[str, ...]]]:
    raw_aliases = metadata.get("aliases", {})
    if not isinstance(raw_aliases, dict):
        raise _CatalogError("CATALOGO_ALIASES_INVALIDOS")
    resolved: dict[str, dict[str, _Term]] = {kind: {} for kind in _CATALOGS}
    literals: dict[str, list[str]] = {kind: [] for kind in _CATALOGS}
    for kind, aliases in raw_aliases.items():
        if kind not in _CATALOGS or not isinstance(aliases, dict):
            raise _CatalogError("CATALOGO_ALIASES_INVALIDOS")
        for alias, target in aliases.items():
            if not isinstance(alias, str) or not isinstance(target, str):
                raise _CatalogError("CATALOGO_ALIASES_INVALIDOS")
            alias_key = _key(alias)
            target_terms = _term_matches(terms[kind], target)
            target_term = target_terms[0] if len(target_terms) == 1 else None
            if not alias_key or target_term is None or alias_key in resolved[kind]:
                raise _CatalogError("CATALOGO_ALIASES_INVALIDOS")
            resolved[kind][alias_key] = target_term
            literals[kind].append(alias)
    return resolved, {kind: tuple(values) for kind, values in literals.items()}


def _load_reference_aliases(
    directory: Path, terms: Mapping[str, tuple[_ReferenceTerm, ...]]
) -> dict[str, tuple[tuple[str, _ReferenceTerm], ...]]:
    path = directory / "catalogo_aliases.json"
    try:
        raw_aliases = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError) as error:
        raise _CatalogError("CATALOGO_REFERENCIA_ALIASES_INVALIDOS") from error
    if not isinstance(raw_aliases, dict):
        raise _CatalogError("CATALOGO_REFERENCIA_ALIASES_INVALIDOS")
    aliases: dict[str, list[tuple[str, _ReferenceTerm]]] = {kind: [] for kind in _CATALOGS}
    for kind, catalog_terms in terms.items():
        for term in catalog_terms:
            aliases[kind].extend((alias, term) for alias in _mechanical_aliases(term.name))
    for kind, values in raw_aliases.items():
        if kind not in _CATALOGS or not isinstance(values, dict):
            raise _CatalogError("CATALOGO_REFERENCIA_ALIASES_INVALIDOS")
        by_name = {_key(term.name): term for term in terms[kind]}
        for alias, target in values.items():
            if not isinstance(alias, str) or not isinstance(target, str):
                raise _CatalogError("CATALOGO_REFERENCIA_ALIASES_INVALIDOS")
            target_term = by_name.get(_key(target))
            if not alias.strip() or target_term is None:
                raise _CatalogError("CATALOGO_REFERENCIA_ALIASES_INVALIDOS")
            aliases[kind].append((alias, target_term))
    return {kind: tuple(values) for kind, values in aliases.items()}


def _selection_matches_metadata(
    selection: CatalogSelection, metadata: Mapping[str, object]
) -> bool:
    provenance = metadata.get("provenance")
    return (
        isinstance(provenance, str)
        and bool(provenance.strip())
        and all(
            isinstance(metadata.get(field), str) and _key(str(metadata[field])) == _key(value)
            for field, value in (
                ("career", selection.career),
                ("period", selection.period),
                ("version", selection.version),
            )
        )
    )


def _syllabus_metadata(source_text: str) -> dict[str, str | None]:
    return {
        field: next(
            (
                match.group(1).strip()
                for pattern in patterns
                if (match := pattern.search(source_text))
            ),
            None,
        )
        for field, patterns in _SYLLABUS_METADATA.items()
    }


def _metadata_matches(metadata: Mapping[str, str | None], selection: CatalogSelection) -> bool:
    return all(
        metadata.get(field) is not None and _key(str(metadata[field])) == _key(value)
        for field, value in (("career", selection.career), ("period", selection.period))
    )


def _resolve_package(catalog: _Catalog, package: Mapping[str, object]) -> dict[str, object]:
    result = dict(package)
    result["catalogo"] = {
        "habilidad": _resolution(catalog, "habilidad", package.get("habilidad_propuesta")),
        "competencia": _resolution(catalog, "competencia", package.get("competencia_propuesta")),
        "herramientas_vinculadas": [],
    }
    return result


def _resolution(catalog: _Catalog, kind: str, value: object) -> dict[str, object]:
    proposal = value if isinstance(value, str) else ""
    term, code = catalog.resolve(kind, proposal)
    resolution: dict[str, object] = {
        "propuesta": proposal or None,
        "estado": "RESUELTO" if term is not None else "PENDIENTE",
        "codigo": code,
        "id": term.identifier if term is not None else None,
    }
    if code == "CATALOGO_NOMBRE_AMBIGUO":
        resolution["candidatos"] = _candidate_records(catalog.candidates(kind, proposal))
    return resolution


def _resolve_tools(
    catalog: _Catalog,
    source_text: str,
    syllabus_text: str,
    raw_packages: Sequence[Mapping[str, object]],
    packages: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    if any(package.get("herramientas_catalogo") for package in raw_packages):
        unlinked: list[dict[str, object]] = []
        for mention, start, end in _tool_mentions(catalog, syllabus_text):
            attached = False
            for raw_package, package in zip(raw_packages, packages, strict=True):
                if not _catalog_tool_explicitly_associated(raw_package, mention, start, end):
                    continue
                catalog_data = package["catalogo"]
                if not isinstance(catalog_data, dict):
                    continue
                linked = catalog_data["herramientas_vinculadas"]
                if isinstance(linked, list) and mention not in linked:
                    linked.append(mention)
                attached = True
            if not attached and mention not in unlinked:
                unlinked.append(mention)
        return unlinked

    mentions = _tool_mentions(catalog, source_text)
    unlinked: list[dict[str, object]] = []
    for mention, start, end in mentions:
        attached = False
        for raw_package, package in zip(raw_packages, packages, strict=True):
            if not _tool_explicitly_associated(catalog, raw_package, mention, start, end):
                continue
            catalog_data = package["catalogo"]
            if not isinstance(catalog_data, dict):
                continue
            linked = catalog_data["herramientas_vinculadas"]
            if isinstance(linked, list) and mention not in linked:
                linked.append(mention)
            attached = True
        if not attached and mention not in unlinked:
            unlinked.append(mention)
    return unlinked


def _tool_mentions(
    catalog: _Catalog | _ToolCatalog,
    source_text: str,
) -> list[tuple[dict[str, object], int, int]]:
    candidates = [term.name for term in catalog.terms["herramienta"]]
    candidates.extend(catalog.alias_literals["herramienta"])
    matches: list[tuple[int, int, tuple[_Term, ...], str]] = []
    seen: set[tuple[int, int, str]] = set()
    for candidate in dict.fromkeys(candidates):
        terms = catalog.candidates("herramienta", candidate)
        if not terms:
            continue
        for start, end, literal in _literal_matches(source_text, candidate):
            key = (start, end, candidate)
            if key in seen:
                continue
            seen.add(key)
            matches.append((start, end, terms, literal))

    selected: list[tuple[int, int, tuple[_Term, ...], str]] = []
    for match in sorted(
        matches,
        key=lambda item: (item[0], -(item[1] - item[0]), item[2][0].name),
    ):
        start, end, _, _ = match
        if any(
            start < selected_end and selected_start < end
            for selected_start, selected_end, _, _ in selected
        ):
            continue
        selected.append(match)
    return [
        (
            {
                "propuesta": terms[0].name if len(terms) == 1 else literal,
                "nombre": terms[0].name if len(terms) == 1 else literal,
                "evidencia_literal": literal,
                "start_pos": start,
                "end_pos": end,
                "estado": "RESUELTO" if len(terms) == 1 else "PENDIENTE",
                "codigo": None if len(terms) == 1 else "CATALOGO_NOMBRE_AMBIGUO",
                "id": terms[0].identifier if len(terms) == 1 else None,
                **({"candidatos": _candidate_records(terms)} if len(terms) > 1 else {}),
            },
            start,
            end,
        )
        for start, end, terms, literal in selected
    ]


def _literal_matches(source_text: str, candidate: str) -> list[tuple[int, int, str]]:
    if not candidate.strip():
        return []
    pattern = re.compile(rf"(?<!\w){re.escape(candidate)}(?!\w|\.\w)", re.IGNORECASE)
    return [
        (match.start(), match.end(), match.group())
        for match in pattern.finditer(source_text)
    ]


def _tool_explicitly_associated(
    catalog: _Catalog | _ToolCatalog,
    package: Mapping[str, object],
    mention: Mapping[str, object],
    start: int,
    end: int,
) -> bool:
    tools = package.get("herramientas")
    proposal = mention.get("propuesta")
    if not isinstance(tools, list) or not isinstance(proposal, str):
        return False
    term, _ = catalog.resolve("herramienta", proposal)
    if term is None or not any(
        isinstance(tool, str) and catalog.resolve("herramienta", tool)[0] == term for tool in tools
    ):
        return False
    evidence = package.get("evidencia_principal")
    if not isinstance(evidence, Mapping):
        return False
    evidence_start = evidence.get("start_pos")
    evidence_end = evidence.get("end_pos")
    return (
        isinstance(evidence_start, int)
        and isinstance(evidence_end, int)
        and start < evidence_end
        and evidence_start < end
    )


def _catalog_tool_explicitly_associated(
    package: Mapping[str, object], mention: Mapping[str, object], start: int, end: int
) -> bool:
    links = package.get("herramientas_catalogo")
    return isinstance(links, list) and any(
        isinstance(link, Mapping)
        and link.get("id") == mention.get("id")
        and link.get("start_pos") == start
        and link.get("end_pos") == end
        for link in links
    )


def _pending_document(
    packages: Sequence[Mapping[str, object]], code: str, selection: CatalogSelection
) -> dict[str, object]:
    resolved = []
    for package in packages:
        result = dict(package)
        catalog_data: dict[str, object] = {
            kind: {
                "propuesta": package.get(f"{kind}_propuesta"),
                "estado": "PENDIENTE",
                "codigo": code,
                "id": None,
            }
            for kind in ("habilidad", "competencia")
        }
        catalog_data["herramientas_vinculadas"] = []
        result["catalogo"] = catalog_data
        resolved.append(result)
    return {
        "catalogo": {
            "estado": "PENDIENTE",
            "codigo": code,
            "career": selection.career,
            "period": selection.period,
            "version": selection.version,
        },
        "paquetes": resolved,
        "paquetes_crudos": [dict(package) for package in packages],
        "herramientas_detectadas": [],
        "herramientas_sin_vinculo": [],
    }


def _missing_code(kind: str) -> str:
    return {
        "competencia": "COMPETENCIA_CATALOGO_NO_ENCONTRADA",
        "habilidad": "HABILIDAD_CATALOGO_NO_ENCONTRADA",
        "herramienta": "HERRAMIENTA_CATALOGO_NO_ENCONTRADA",
    }[kind]


def _mechanical_aliases(name: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKD", name)
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return tuple(
        dict.fromkeys(
            (
                name,
                name.casefold(),
                _key(name),
                re.sub(r"[^\w]+", "", without_accents.casefold()),
            )
        )
    )


def _key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^\w]+", " ", without_accents.casefold()).split())


def _literal_key(value: str) -> str:
    return value.strip().casefold()


def _term_index(
    terms: Sequence[_Term], key: Callable[[str], str]
) -> dict[str, tuple[_Term, ...]]:
    indexed: dict[str, list[_Term]] = {}
    for term in terms:
        indexed.setdefault(key(term.name), []).append(term)
    return {name: tuple(matches) for name, matches in indexed.items()}


def _term_matches(terms: Sequence[_Term], proposal: str) -> tuple[_Term, ...]:
    literal_matches = _term_index(terms, _literal_key).get(_literal_key(proposal))
    if literal_matches is not None:
        return literal_matches
    normalized_matches = _term_index(terms, _key).get(_key(proposal))
    return normalized_matches if normalized_matches is not None else ()


def _candidate_records(terms: Sequence[_Term]) -> list[dict[str, str]]:
    return [{"id": term.identifier, "nombre": term.name} for term in terms]
