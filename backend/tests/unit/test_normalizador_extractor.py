"""Contratos deterministas de la fachada de extracción CHH."""

from __future__ import annotations

import json

from agente.normalizador.empleabilidad import extractor, extractor_reglas
from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH


def _catalogo() -> CatalogoCHH:
    return CatalogoCHH(
        competencias=(
            ConceptoCHH("COMP_DATA", "Análisis de datos", "Analizar datos."),
            ConceptoCHH("COMP_ADAPT", "Adaptabilidad", "Adaptarse a cambios."),
        ),
        habilidades=(
            ConceptoCHH(
                "HAB_DATA",
                "Analizar datos para obtener hallazgos",
                "Analizar datos para obtener hallazgos.",
            ),
            ConceptoCHH(
                "HAB_ADAPT",
                "Adaptarse a cambios del entorno",
                "Adaptarse a cambios del entorno.",
            ),
        ),
        herramientas=(ConceptoCHH("TOOL_SQL", "SQL", "Lenguaje de consulta."),),
        ejemplos_por_habilidad={},
        origen=("test",),
        version="test",
    )


def test_extractor_reexports_reglas_with_exact_identity() -> None:
    for nombre in (
        "ReglaCHH",
        "REGLAS_VERSION",
        "_regla",
        "REGLAS_LABORALES",
        "INFERENCIAS_HERRAMIENTA",
        "ALIASES_HERRAMIENTAS",
        "HERRAMIENTAS_REGLAS_PREFERIDAS",
        "AREA_DEFAULTS",
        "INFORME_CAMPOS",
    ):
        assert getattr(extractor, nombre) is getattr(extractor_reglas, nombre)


def test_extractor_serialization_is_deterministic() -> None:
    catalogo = _catalogo()
    datos = {"compet_adapta_bilidad": "Sí", "funciones_iniciales": "Analizar datos con SQL."}

    serializado = [
        json.dumps(
            extractor.extraer_informe(datos, catalogo).a_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        for _ in range(2)
    ]

    assert serializado[0] == serializado[1]
    assert [cadena["regla"] for cadena in json.loads(serializado[0])["cadenas"]] == [
        "empleabilidad-chh-0.1.0:INFORME_COMPET_ADAPTA_BILIDAD",
        "empleabilidad-chh-0.1.0:LAB_DATA_001",
    ]
