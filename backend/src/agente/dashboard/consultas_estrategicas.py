"""Registry compatible de las doce consultas estratégicas del dashboard."""

from __future__ import annotations

from typing import Final

from agente.dashboard.consultas_alineacion import CONSULTAS_ALINEACION
from agente.dashboard.consultas_empresas import CONSULTAS_EMPRESAS
from agente.dashboard.consultas_modelo import ConsultaEstrategica
from agente.dashboard.consultas_panorama import CONSULTAS_PANORAMA

_CONSULTAS: Final[tuple[ConsultaEstrategica, ...]] = (
    *CONSULTAS_PANORAMA,
    *CONSULTAS_ALINEACION,
    *CONSULTAS_EMPRESAS,
)

CONSULTAS_ESTRATEGICAS: Final[dict[str, ConsultaEstrategica]] = {
    consulta.slug: consulta for consulta in _CONSULTAS
}


def todas_las_consultas_estrategicas() -> tuple[ConsultaEstrategica, ...]:
    """Devuelve el catálogo completo en el orden de presentación."""

    return _CONSULTAS


__all__ = [
    "CONSULTAS_ESTRATEGICAS",
    "ConsultaEstrategica",
    "todas_las_consultas_estrategicas",
]
