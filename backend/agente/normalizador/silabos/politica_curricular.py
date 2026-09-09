"""Políticas deterministas previas a la proyección curricular canónica."""

from __future__ import annotations

from agente.normalizador.empleabilidad.catalogo import clave_concepto

MOTIVO_COMPETENCIA_GENERICA = "COMPETENCIA_GENERICA"

_COMPETENCIAS_GENERICAS = frozenset(
    clave_concepto(nombre)
    for nombre in (
        "Trabajo en equipo",
        "Comunicación efectiva",
        "Comunicación eficaz",
        "Pensamiento crítico",
        "Aprendizaje autónomo",
        "Ética profesional",
    )
)


def es_competencia_generica(nombre: object) -> bool:
    """Reconoce conceptos transversales excluidos del catálogo disciplinar."""

    return clave_concepto(nombre) in _COMPETENCIAS_GENERICAS
