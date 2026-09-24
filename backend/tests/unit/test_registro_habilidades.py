"""TDD tests for RegistroHabilidades skill registry with SQLite persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from agente.normalizador.silabos.analista_tecnico import CandidatoTecnico
from agente.normalizador.silabos.registro_habilidades import RegistroHabilidades


@pytest.fixture
def catalogo_oficial_minimo() -> list[CandidatoTecnico]:
    """Minimal official catalog seeded with COMP_TEC references."""
    return [
        CandidatoTecnico(
            referencia="COMP_TEC_0001",
            carrera="Ingeniería",
            nombre="Python",
            descripcion="Lenguaje de programación interpretado",
            fila=2,
        ),
        CandidatoTecnico(
            referencia="COMP_TEC_0002",
            carrera="Ingeniería",
            nombre="SQL",
            descripcion="Lenguaje de consulta estructurada",
            fila=3,
        ),
    ]


def test_official_comp_maps_to_hab_and_normalized_content_reuses_id(
    tmp_path: Path, catalogo_oficial_minimo: list[CandidatoTecnico]
) -> None:
    """Official COMP references map to HAB IDs and normalized content reuses them."""
    db_path = tmp_path / "test.db"

    with RegistroHabilidades(str(db_path), catalogo_oficial_minimo) as registro:
        official_id = registro.resolve_id(
            "COMP_TEC_0001",
            "Python",
            "Lenguaje de programación interpretado",
        )
        assert official_id == "HAB_TEC_0001"

        normalized_id = registro.resolve_id(
            None,
            " python ",
            "LENGUAJE DE PROGRAMACIÓN INTERPRETADO",
        )
        assert normalized_id == "HAB_TEC_0001"


def test_hab_ref_accepts_identical_content_and_rejects_different_content(
    tmp_path: Path, catalogo_oficial_minimo: list[CandidatoTecnico]
) -> None:
    """An existing HAB reference is valid only for identical normalized content."""
    db_path = tmp_path / "test.db"

    with RegistroHabilidades(str(db_path), catalogo_oficial_minimo) as registro:
        allocated_id = registro.resolve_id(
            None,
            "JavaScript",
            "Lenguaje de programación de cliente",
        )
        assert allocated_id == "HAB_TEC_0003"

        existing_id = registro.resolve_id(
            "HAB_TEC_0003",
            " javascript ",
            "LENGUAJE DE PROGRAMACIÓN DE CLIENTE",
        )
        assert existing_id == "HAB_TEC_0003"

        with pytest.raises((ValueError, KeyError)):
            registro.resolve_id(
                "HAB_TEC_0003",
                "TypeScript",
                "Lenguaje con tipos estáticos",
            )


def test_persisted_comp_alias_resolves_without_official_catalog(
    tmp_path: Path, catalogo_oficial_minimo: list[CandidatoTecnico]
) -> None:
    """A persisted COMP alias recovers when the official catalog snapshot is unavailable."""
    db_path = tmp_path / "test.db"

    with RegistroHabilidades(str(db_path), catalogo_oficial_minimo) as registro:
        assert (
            registro.resolve_id(
                "COMP_TEC_0001",
                "Python",
                "Lenguaje de programación interpretado",
            )
            == "HAB_TEC_0001"
        )

    with RegistroHabilidades(str(db_path), []) as registro:
        assert (
            registro.resolve_id(
                "COMP_TEC_0001",
                " python ",
                "LENGUAJE DE PROGRAMACIÓN INTERPRETADO",
            )
            == "HAB_TEC_0001"
        )

        with pytest.raises(ValueError):
            registro.resolve_id(
                "COMP_TEC_0001",
                "SQL",
                "Lenguaje de consulta estructurada",
            )

        with pytest.raises(KeyError):
            registro.resolve_id(
                "COMP_TEC_9999",
                "Python",
                "Lenguaje de programación interpretado",
            )


def test_unmatched_skill_allocates_next_suffix_persists_and_distinct_content_gets_new_id(
    tmp_path: Path, catalogo_oficial_minimo: list[CandidatoTecnico]
) -> None:
    """Unmatched content gets the next suffix, persists, and does not alias distinct content."""
    db_path = tmp_path / "test.db"

    with RegistroHabilidades(str(db_path), catalogo_oficial_minimo) as registro:
        allocated_id = registro.resolve_id(
            None,
            "JavaScript",
            "Lenguaje de programación de cliente",
        )
        assert allocated_id == "HAB_TEC_0003"

    with RegistroHabilidades(str(db_path), catalogo_oficial_minimo) as registro:
        persisted_id = registro.resolve_id(
            None,
            "JavaScript",
            "Lenguaje de programación de cliente",
        )
        assert persisted_id == "HAB_TEC_0003"

        distinct_id = registro.resolve_id(
            None,
            "TypeScript",
            "Lenguaje con tipos estáticos",
        )
        assert distinct_id == "HAB_TEC_0004"


def test_transaction_rolls_back_allocations_on_exception(
    tmp_path: Path, catalogo_oficial_minimo: list[CandidatoTecnico]
) -> None:
    """An exception exiting the context rolls back allocations."""
    db_path = tmp_path / "test.db"

    with pytest.raises(RuntimeError, match="simulated error"):
        with RegistroHabilidades(str(db_path), catalogo_oficial_minimo) as registro:
            allocated_id = registro.resolve_id(
                None,
                "Go",
                "Lenguaje compilado concurrente",
            )
            assert allocated_id == "HAB_TEC_0003"
            raise RuntimeError("simulated error")

    with RegistroHabilidades(str(db_path), catalogo_oficial_minimo) as registro:
        retried_id = registro.resolve_id(
            None,
            "Go",
            "Lenguaje compilado concurrente",
        )
        assert retried_id == "HAB_TEC_0003"

        next_id = registro.resolve_id(
            None,
            "Rust",
            "Lenguaje de sistemas seguro",
        )
        assert next_id == "HAB_TEC_0004"


def test_future_official_comp_collision_fails_during_context_initialization(
    tmp_path: Path, catalogo_oficial_minimo: list[CandidatoTecnico]
) -> None:
    """A future official COMP suffix cannot collide with different registered HAB content."""
    db_path = tmp_path / "test.db"

    with RegistroHabilidades(str(db_path), catalogo_oficial_minimo) as registro:
        generated_id = registro.resolve_id(
            None,
            "C++",
            "Lenguaje compilado de bajo nivel",
        )
        assert generated_id == "HAB_TEC_0003"

    catalogo_con_nueva_oficial = [
        *catalogo_oficial_minimo,
        CandidatoTecnico(
            referencia="COMP_TEC_0003",
            carrera="Ingeniería",
            nombre="Ruby",
            descripcion="Lenguaje dinámico interpretado",
            fila=4,
        ),
    ]

    with pytest.raises((ValueError, KeyError)):
        with RegistroHabilidades(str(db_path), catalogo_con_nueva_oficial):
            pass
