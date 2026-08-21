"""Canonical entity parameter-to-property contracts shared by generation guards."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CanonicalEntityParameter:
    parameter: str
    id_property: str

    @property
    def plural_parameter(self) -> str:
        return f"{self.parameter.removesuffix('_id')}_ids"


CANONICAL_ENTITY_PARAMETERS = {
    parameter.parameter: parameter
    for parameter in (
        CanonicalEntityParameter("carrera_id", "id_carrera"),
        CanonicalEntityParameter("empresa_id", "id_empresa"),
        CanonicalEntityParameter("industria_id", "id_industria"),
        CanonicalEntityParameter("puesto_id", "id_puesto"),
        CanonicalEntityParameter("habilidad_id", "id_habilidad"),
        CanonicalEntityParameter("herramienta_id", "id_herramienta"),
        CanonicalEntityParameter("competencia_id", "id_competencia"),
        CanonicalEntityParameter("curso_id", "id_curso"),
        CanonicalEntityParameter("facultad_id", "id_facultad"),
    )
}


def canonical_id_contract(parameter: str) -> tuple[str, str] | None:
    """Return the exact ID property/operator for a known canonical parameter."""
    singular = CANONICAL_ENTITY_PARAMETERS.get(parameter)
    if singular is not None:
        return singular.id_property, "="
    plural = next(
        (
            contract
            for contract in CANONICAL_ENTITY_PARAMETERS.values()
            if contract.plural_parameter == parameter
        ),
        None,
    )
    if plural is None:
        return None
    return plural.id_property, "IN"
