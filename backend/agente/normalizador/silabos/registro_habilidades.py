"""Transactional global registry for technical-skill identifiers."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from .analista_tecnico import clave_catalogo

_COMP_REF = re.compile(r"^COMP_TEC_(\d{4})$")
_HAB_REF = re.compile(r"^HAB_TEC_(\d{4})$")
_MAX_SUFFIX = 9999


class RegistroHabilidades:
    """Resolve normalized skill content to globally persistent ``HAB_TEC`` IDs.

    The registry owns one SQLite transaction for the lifetime of the context.
    Official catalog rows reserve their numeric suffixes, while the normalized
    name/description pair remains the global identity of a skill.
    """

    def __init__(self, db_path: str | Path, catalogo_oficial: Any) -> None:
        self._db_path = db_path
        self._official = self._prepare_official_catalog(catalogo_oficial)
        self._connection: sqlite3.Connection | None = None

    def __enter__(self) -> RegistroHabilidades:
        if self._connection is not None:
            raise RuntimeError("RegistroHabilidades context is already open")

        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._db_path)
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys = ON")
        self._connection = connection
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._create_schema()
            self._load_and_seed_official_catalog()
            return self
        except BaseException:
            self._rollback_and_close()
            raise

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> Literal[False]:
        connection = self._connection
        if connection is None:
            return False

        try:
            if exc_type is None:
                connection.commit()
            else:
                connection.rollback()
        finally:
            connection.close()
            self._connection = None
        return False

    def resolve_id(
        self,
        catalogo_ref: str | None,
        nombre: object,
        descripcion: object,
    ) -> str:
        """Resolve one source reference and its content to a global skill ID."""

        connection = self._require_connection()
        pair = self._content_pair(nombre, descripcion)
        reference_kind, suffix = self._parse_reference(catalogo_ref)

        if reference_kind == "COMP":
            assert catalogo_ref is not None
            official = self._official.get(catalogo_ref)
            if official is None:
                row = connection.execute(
                    "SELECT id_habilidad FROM referencias_habilidades WHERE referencia = ?",
                    (catalogo_ref,),
                ).fetchone()
                if row is None:
                    raise KeyError(f"Referencia oficial desconocida: {catalogo_ref}")
                persisted_id = str(row[0])
                persisted_pair = self._pair_for_id(connection, persisted_id)
                if persisted_pair != pair:
                    raise ValueError(f"Contenido incompatible con {catalogo_ref}")
                return persisted_id
            expected_pair, expected_id = official
            if pair != expected_pair:
                raise ValueError(f"Contenido incompatible con {catalogo_ref}")
            return self._reference_id(connection, catalogo_ref, expected_id, pair)

        if reference_kind == "HAB":
            assert catalogo_ref is not None
            assert suffix is not None
            expected_id = f"HAB_TEC_{suffix:04d}"
            registered_pair = self._pair_for_id(connection, expected_id)
            if registered_pair is None:
                raise KeyError(f"Referencia HAB desconocida: {catalogo_ref}")
            if registered_pair != pair:
                raise ValueError(f"Contenido incompatible con {catalogo_ref}")
            return expected_id

        existing_id = self._id_for_pair(connection, pair)
        if existing_id is not None:
            return existing_id

        next_suffix = self._next_suffix(connection)
        if next_suffix > _MAX_SUFFIX:
            raise ValueError("Se agotó el espacio de IDs HAB_TEC de cuatro dígitos")
        identifier = f"HAB_TEC_{next_suffix:04d}"
        try:
            connection.execute(
                """
                INSERT INTO habilidades (id_habilidad, nombre_clave, descripcion_clave)
                VALUES (?, ?, ?)
                """,
                (identifier, pair[0], pair[1]),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"ID HAB conflictivo: {identifier}") from error
        return identifier

    @staticmethod
    def _prepare_official_catalog(catalogo_oficial: Any) -> dict[str, tuple[tuple[str, str], str]]:
        candidates = getattr(catalogo_oficial, "candidatos", catalogo_oficial)
        if isinstance(candidates, (str, bytes)):
            raise ValueError("El catálogo oficial no es una colección de candidatos")
        try:
            iterator = iter(candidates)
        except TypeError as error:
            raise ValueError("El catálogo oficial no es iterable") from error

        official: dict[str, tuple[tuple[str, str], str]] = {}
        for candidate in iterator:
            reference = RegistroHabilidades._candidate_value(candidate, "referencia")
            reference_kind, suffix = RegistroHabilidades._parse_reference(reference)
            if reference_kind != "COMP" or suffix is None:
                raise ValueError(f"Referencia oficial inválida: {reference!r}")
            pair = RegistroHabilidades._content_pair(
                RegistroHabilidades._candidate_value(candidate, "nombre"),
                RegistroHabilidades._candidate_value(candidate, "descripcion"),
            )
            identifier = f"HAB_TEC_{suffix:04d}"
            previous = official.get(reference)
            if previous is not None and previous[0] != pair:
                raise ValueError(f"Referencia oficial conflictiva: {reference}")
            official[reference] = (pair, identifier)
        return official

    @staticmethod
    def _candidate_value(candidate: Any, field: str) -> Any:
        if isinstance(candidate, Mapping):
            if field not in candidate:
                raise ValueError(f"Candidato oficial sin campo {field}: {candidate!r}")
            return candidate[field]
        try:
            return getattr(candidate, field)
        except AttributeError as error:
            raise ValueError(f"Candidato oficial sin campo {field}") from error

    @staticmethod
    def _parse_reference(reference: str | None) -> tuple[str | None, int | None]:
        if reference is None:
            return None, None
        if not isinstance(reference, str):
            raise ValueError(f"Referencia malformada: {reference!r}")
        match = _COMP_REF.fullmatch(reference)
        if match is not None:
            return "COMP", RegistroHabilidades._suffix_from_match(match)
        match = _HAB_REF.fullmatch(reference)
        if match is not None:
            return "HAB", RegistroHabilidades._suffix_from_match(match)
        raise ValueError(f"Referencia malformada: {reference!r}")

    @staticmethod
    def _suffix_from_match(match: re.Match[str]) -> int:
        try:
            return int(match.group(1))
        except (IndexError, TypeError, ValueError) as error:
            raise ValueError("Referencia con sufijo inválido") from error

    @staticmethod
    def _content_pair(nombre: object, descripcion: object) -> tuple[str, str]:
        name_key = clave_catalogo(nombre)
        description_key = clave_catalogo(descripcion)
        if not name_key or not description_key:
            raise ValueError("El nombre y la descripción de la habilidad son obligatorios")
        return name_key, description_key

    def _create_schema(self) -> None:
        connection = self._require_connection()
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS habilidades (
                id_habilidad TEXT PRIMARY KEY,
                nombre_clave TEXT NOT NULL,
                descripcion_clave TEXT NOT NULL,
                UNIQUE (nombre_clave, descripcion_clave)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS referencias_habilidades (
                referencia TEXT PRIMARY KEY,
                id_habilidad TEXT NOT NULL,
                FOREIGN KEY (id_habilidad) REFERENCES habilidades (id_habilidad)
            )
            """
        )

    def _load_and_seed_official_catalog(self) -> None:
        connection = self._require_connection()
        id_to_pair: dict[str, tuple[str, str]] = {}
        pair_to_id: dict[tuple[str, str], str] = {}
        for identifier, name_key, description_key in connection.execute(
            "SELECT id_habilidad, nombre_clave, descripcion_clave FROM habilidades"
        ):
            kind, suffix = self._parse_reference(identifier)
            if kind != "HAB" or suffix is None:
                raise ValueError(f"ID registrado inválido: {identifier!r}")
            pair = self._content_pair(name_key, description_key)
            previous_id = pair_to_id.get(pair)
            if previous_id is not None and previous_id != identifier:
                raise ValueError(f"Contenido registrado con IDs conflictivos: {identifier}")
            id_to_pair[identifier] = pair
            pair_to_id[pair] = identifier

        reference_to_id: dict[str, str] = {}
        for reference, identifier in connection.execute(
            "SELECT referencia, id_habilidad FROM referencias_habilidades"
        ):
            kind, _ = self._parse_reference(reference)
            if kind not in {"COMP", "HAB"} or identifier not in id_to_pair:
                raise ValueError(f"Referencia registrada inválida: {reference!r}")
            previous_id = reference_to_id.get(reference)
            if previous_id is not None and previous_id != identifier:
                raise ValueError(f"Referencia registrada conflictiva: {reference}")
            reference_to_id[reference] = identifier

        for reference, (pair, expected_id) in sorted(self._official.items()):
            registered_pair = id_to_pair.get(expected_id)
            if registered_pair is not None and registered_pair != pair:
                raise ValueError(f"Colisión de ID oficial: {expected_id}")

            identifier = pair_to_id.get(pair)
            if identifier is None:
                identifier = expected_id
                connection.execute(
                    """
                    INSERT INTO habilidades (id_habilidad, nombre_clave, descripcion_clave)
                    VALUES (?, ?, ?)
                    """,
                    (identifier, pair[0], pair[1]),
                )
                id_to_pair[identifier] = pair
                pair_to_id[pair] = identifier

            registered_reference_id = reference_to_id.get(reference)
            if registered_reference_id is not None:
                if id_to_pair[registered_reference_id] != pair:
                    raise ValueError(f"Referencia oficial conflictiva: {reference}")
                continue
            connection.execute(
                "INSERT INTO referencias_habilidades (referencia, id_habilidad) VALUES (?, ?)",
                (reference, identifier),
            )
            reference_to_id[reference] = identifier

    def _reference_id(
        self,
        connection: sqlite3.Connection,
        reference: str,
        expected_id: str,
        pair: tuple[str, str],
    ) -> str:
        row = connection.execute(
            "SELECT id_habilidad FROM referencias_habilidades WHERE referencia = ?",
            (reference,),
        ).fetchone()
        if row is not None:
            identifier = str(row[0])
            registered_pair = self._pair_for_id(connection, identifier)
            if registered_pair != pair:
                raise ValueError(f"Referencia incompatible: {reference}")
            return identifier

        registered_pair = self._pair_for_id(connection, expected_id)
        if registered_pair is not None and registered_pair != pair:
            raise ValueError(f"Colisión de ID oficial: {expected_id}")
        pair_identifier = self._id_for_pair(connection, pair)
        if pair_identifier is None:
            raise ValueError(f"Referencia oficial no registrada: {reference}")
        connection.execute(
            "INSERT INTO referencias_habilidades (referencia, id_habilidad) VALUES (?, ?)",
            (reference, pair_identifier),
        )
        return pair_identifier

    @staticmethod
    def _pair_for_id(connection: sqlite3.Connection, identifier: str) -> tuple[str, str] | None:
        row = connection.execute(
            "SELECT nombre_clave, descripcion_clave FROM habilidades WHERE id_habilidad = ?",
            (identifier,),
        ).fetchone()
        return None if row is None else (str(row[0]), str(row[1]))

    @staticmethod
    def _id_for_pair(connection: sqlite3.Connection, pair: tuple[str, str]) -> str | None:
        row = connection.execute(
            """
            SELECT id_habilidad
            FROM habilidades
            WHERE nombre_clave = ? AND descripcion_clave = ?
            """,
            pair,
        ).fetchone()
        return None if row is None else str(row[0])

    def _next_suffix(self, connection: sqlite3.Connection) -> int:
        reserved = [
            self._suffix_from_match(match)
            for reference in self._official
            for match in [_COMP_REF.fullmatch(reference)]
            if match is not None
        ]
        registered: list[int] = []
        for (identifier,) in connection.execute("SELECT id_habilidad FROM habilidades"):
            match = _HAB_REF.fullmatch(identifier)
            if match is not None:
                registered.append(self._suffix_from_match(match))
        for (reference,) in connection.execute("SELECT referencia FROM referencias_habilidades"):
            _, suffix = self._parse_reference(reference)
            if suffix is not None:
                registered.append(suffix)
        return max((*reserved, *registered), default=0) + 1

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("RegistroHabilidades debe usarse como context manager")
        return self._connection

    def _rollback_and_close(self) -> None:
        connection = self._connection
        if connection is None:
            return
        try:
            connection.rollback()
        finally:
            connection.close()
            self._connection = None
