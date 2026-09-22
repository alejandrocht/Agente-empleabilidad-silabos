"""Versioned static schema contract for the CIAR Neo4j graph."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "2026-09-21"


_SCHEMA: dict[str, Any] = {
    "node_props": {
        "Facultad": [
            "id_facultad",
            "nombre_facultad",
            "decano",
            "descripcion_breve_facultad",
            "codigo_facultad",
        ],
        "Carrera": [
            "id_carrera",
            "nombre_carrera",
            "descripcion_breve_carrera",
            "codigo_carrera",
            "coordinador",
        ],
        "Logros": [
            "id_herramienta",
            "nombre_herramienta",
            "descripcion_breve_herramienta",
        ],
        "Curso": [
            "id_curso",
            "nombre_curso",
            "coordinador",
            "creditos",
            "nivel",
            "tipo_curso",
            "codigo_curso",
        ],
        "Cobertura_Curricular": ["id_cob_curricular"],
        "Industria": [
            "id_industria",
            "nombre",
            "ciiu",
            "sector_macro",
            "descripcion_breve",
        ],
        "Oferta_Laboral": [
            "id_ofe_laboral",
            "fecha_publicacion",
            "fecha_finalizacion",
            "area",
            "area_especifica",
            "cargo",
            "descripcion_breve",
            "tipo_puesto",
        ],
        "competencia_tecnica": [
            "id_habilidad",
            "nombre_habilidad",
            "descripcion_breve",
        ],
        "Requerimiento_Laboral": ["id_req_laboral", "tipo"],
        "Puesto": ["id_puesto", "nombre", "ciclo_requerido"],
        "Empresa": [
            "id_empresa",
            "nombre",
            "ruc",
            "razon_social",
            "tipo",
            "descripcion_breve",
            "ruc_original",
        ],
        "Silabo": ["id_silabo", "codigo_silabo", "sumilla"],
    },
    "rel_props": {},
    "relationships": [
        {"start": "Facultad", "type": "OFRECE", "end": "Carrera"},
        {"start": "Curso", "type": "TIENE", "end": "Silabo"},
        {"start": "Curso", "type": "TIENE", "end": "Cobertura_Curricular"},
        {"start": "Silabo", "type": "DECLARA", "end": "Cobertura_Curricular"},
        {"start": "Cobertura_Curricular", "type": "CUBRE", "end": "competencia_tecnica"},
        {"start": "Cobertura_Curricular", "type": "CUBRE", "end": "Logros"},
        {"start": "Requerimiento_Laboral", "type": "REQUIERE", "end": "competencia_tecnica"},
        {"start": "Puesto", "type": "DEFIINE", "end": "Requerimiento_Laboral"},
        {"start": "Empresa", "type": "PUBLICA", "end": "Oferta_Laboral"},
        {"start": "Oferta_Laboral", "type": "DIRIGE_A", "end": "Carrera"},
        {"start": "Oferta_Laboral", "type": "OFRECE", "end": "Puesto"},
        {"start": "Oferta_Laboral", "type": "TIENE", "end": "Requerimiento_Laboral"},
        {"start": "Industria", "type": "AGRUPA", "end": "Empresa"},
        {"start": "Empresa", "type": "PIDE", "end": "Requerimiento_Laboral"},
        {"start": "Carrera", "type": "ENSENIA", "end": "Curso"},
        {"start": "Silabo", "type": "DECLARA", "end": "competencia_tecnica"},
        {"start": "Curso", "type": "DESARROLLA", "end": "competencia_tecnica"},
    ],
}


def static_schema() -> dict[str, Any]:
    """Return an isolated copy of the versioned schema contract."""
    return deepcopy(_SCHEMA)
