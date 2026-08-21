"""Fixed, read-only dashboard query boundary for the active agent package."""

from agente.dashboard.servicio import (
    ErrorDashboard,
    brechas_dimension,
    carreras_por_demanda,
    cobertura_dimension,
    demanda_dimension,
    empresas_dashboard,
    industrias_elemento,
    industrias_por_carrera,
    listar_carreras,
    metadatos,
    obtener_carrera,
    tendencia_ofertas,
)

__all__ = [
    "ErrorDashboard",
    "brechas_dimension",
    "carreras_por_demanda",
    "cobertura_dimension",
    "demanda_dimension",
    "empresas_dashboard",
    "industrias_elemento",
    "industrias_por_carrera",
    "listar_carreras",
    "metadatos",
    "obtener_carrera",
    "tendencia_ofertas",
]
