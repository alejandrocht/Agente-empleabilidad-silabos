"""Public output contracts for persisted curricular executions by mode.

This module intentionally contains only standard-library types. It is a
boundary for persistence, not a builder, validator, catalog, or approval
implementation.
"""

from __future__ import annotations

from collections.abc import Mapping

ARCHIVOS_CURRICULARES_LEGACY = frozenset(
    {
        "salidas/curso.csv",
        "salidas/catalogo_competencias.csv",
        "salidas/catalogo_habilidades.csv",
        "salidas/catalogo_herramientas.csv",
        "salidas/cobertura_curricular.csv",
    }
)
ARCHIVOS_CURRICULARES_TECNICOS = frozenset(
    {
        "salidas/curso.csv",
        "salidas/silabo.csv",
        "salidas/catalogo_competencias.csv",
        "salidas/catalogo_logros.csv",
        "salidas/cobertura_curricular.csv",
    }
)
REPORTES_CURRICULARES_PRE_HITL = frozenset({"release_gate.json", "extraccion_cactus.json"})
REPORTES_CURRICULARES_TECNICOS = frozenset(
    {
        "release_gate.json",
        "analisis_tecnico.json",
        "propuestas_tecnicas.jsonl",
        "decisiones_tecnicas.jsonl",
    }
)


def es_modo_tecnico(configuracion: object) -> bool:
    """Return the sole supported mode for persisted curricular executions."""

    return True


def gate_permite_salidas_tecnicas(gate: object) -> bool:
    """Return whether the technical release gate permits CSV publication."""

    return isinstance(gate, Mapping) and gate.get("decision") == "ALLOW_IMPORT"


def hitl_curricular_completado(release_gate: object) -> bool:
    """Determine whether the legacy curricular package completed its HITL gate."""

    if not isinstance(release_gate, Mapping) or release_gate.get("decision") != "ALLOW_IMPORT":
        return False
    checks = release_gate.get("checks")
    if not isinstance(checks, Mapping):
        return False
    aprobacion = checks.get("approval")
    canonical_materialized = (
        aprobacion.get("canonical_materialized") if isinstance(aprobacion, Mapping) else None
    )
    return (
        isinstance(aprobacion, Mapping)
        and isinstance(canonical_materialized, bool)
        and canonical_materialized
        and aprobacion.get("pending_decision") == 0
    )


def filtrar_outputs_curriculares(
    outputs: list[dict[str, object]],
    *,
    modo_tecnico: bool = False,
    release_gate: object = None,
    hitl_completado: bool = False,
) -> list[dict[str, object]]:
    """Filter persisted outputs without exposing non-contract artifacts."""

    contract = ARCHIVOS_CURRICULARES_TECNICOS if modo_tecnico else ARCHIVOS_CURRICULARES_LEGACY
    if modo_tecnico and not gate_permite_salidas_tecnicas(release_gate):
        return []
    if not modo_tecnico and not hitl_completado:
        return []
    return [
        output
        for output in outputs
        if isinstance(output.get("archivo"), str) and output["archivo"] in contract
    ]


def reporte_curricular_visible(
    nombre: str,
    *,
    modo_tecnico: bool,
    hitl_completado: bool,
) -> bool:
    """Return whether a curricular report name belongs in the public report."""

    if modo_tecnico:
        return nombre in REPORTES_CURRICULARES_TECNICOS
    return hitl_completado or nombre in REPORTES_CURRICULARES_PRE_HITL


def filtrar_estado_publico(datos: dict[str, object]) -> dict[str, object]:
    """Apply the mode-aware output contract to a persisted manifest."""

    if datos.get("tipo") != "silabos":
        return datos
    estado = dict(datos)
    configuracion = estado.get("configuracion_curricular")
    modo_tecnico = es_modo_tecnico(configuracion)
    release_gate = estado.get("release_gate")
    if not isinstance(release_gate, Mapping):
        limpieza = estado.get("limpieza_silabos")
        if isinstance(limpieza, Mapping):
            release_gate = limpieza.get("release_gate")
    hitl_completado = hitl_curricular_completado(release_gate)

    outputs = estado.get("outputs")
    if isinstance(outputs, list):
        estado["outputs"] = filtrar_outputs_curriculares(
            [dict(output) for output in outputs if isinstance(output, dict)],
            modo_tecnico=modo_tecnico,
            release_gate=release_gate,
            hitl_completado=hitl_completado,
        )
    limpieza = estado.get("limpieza_silabos")
    if isinstance(limpieza, Mapping):
        limpieza_publica = dict(limpieza)
        outputs_limpieza = limpieza_publica.get("outputs")
        if isinstance(outputs_limpieza, list):
            limpieza_publica["outputs"] = filtrar_outputs_curriculares(
                [dict(output) for output in outputs_limpieza if isinstance(output, dict)],
                modo_tecnico=modo_tecnico,
                release_gate=release_gate,
                hitl_completado=hitl_completado,
            )
        estado["limpieza_silabos"] = limpieza_publica
    return estado
