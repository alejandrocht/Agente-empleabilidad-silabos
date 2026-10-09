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
        CanonicalEntityParameter("competencia_tecnica_id", "id_habilidad"),
        CanonicalEntityParameter("logro_id", "id_herramienta"),
        CanonicalEntityParameter("curso_id", "id_curso"),
        CanonicalEntityParameter("facultad_id", "id_facultad"),
    )
}

ENTITY_PARAMETER_ALIASES = {
    "habilidad_id": "competencia_tecnica_id",
    "habilidad_ids": "competencia_tecnica_ids",
    "competencia_id": "competencia_tecnica_id",
    "competencia_ids": "competencia_tecnica_ids",
    "herramienta_id": "logro_id",
    "herramienta_ids": "logro_ids",
}


def canonical_entity_parameter(parameter: str) -> str:
    """Normalize legacy entity parameter names to the static ontology contract."""
    return ENTITY_PARAMETER_ALIASES.get(parameter, parameter)


def canonical_id_contract(parameter: str) -> tuple[str, str] | None:
    """Return the exact ID property/operator for a known canonical parameter."""
    parameter = canonical_entity_parameter(parameter)
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
