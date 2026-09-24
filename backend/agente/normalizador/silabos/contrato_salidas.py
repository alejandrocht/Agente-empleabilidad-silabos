"""Public output contract for persisted technical syllabus executions."""

from __future__ import annotations

from collections.abc import Mapping

ARCHIVOS_CURRICULARES_TECNICOS = frozenset(
    {
        "salidas/curso.csv",
        "salidas/silabo.csv",
        "salidas/catalogo_competencias.csv",
        "salidas/catalogo_habilidades.csv",
        "salidas/catalogo_logros.csv",
        "salidas/cobertura_curricular.csv",
    }
)
REPORTES_CURRICULARES_TECNICOS = frozenset(
    {
        "release_gate.json",
        "analisis_tecnico.json",
        "propuestas_tecnicas.jsonl",
        "decisiones_tecnicas.jsonl",
    }
)


def gate_permite_salidas_tecnicas(gate: object) -> bool:
    """Return whether the technical release gate permits CSV publication."""

    return isinstance(gate, Mapping) and gate.get("decision") == "ALLOW_IMPORT"


def filtrar_outputs_curriculares(
    outputs: list[dict[str, object]],
    *,
    release_gate: object = None,
) -> list[dict[str, object]]:
    """Filter persisted outputs to the technical contract after gate approval."""

    if not gate_permite_salidas_tecnicas(release_gate):
        return []
    return [
        output
        for output in outputs
        if isinstance(output.get("archivo"), str)
        and output["archivo"] in ARCHIVOS_CURRICULARES_TECNICOS
    ]


def reporte_curricular_visible(nombre: str) -> bool:
    """Return whether a technical report belongs in the public report."""

    return nombre in REPORTES_CURRICULARES_TECNICOS


def filtrar_estado_publico(datos: dict[str, object]) -> dict[str, object]:
    """Apply the technical output contract to a persisted syllabus manifest."""

    if datos.get("tipo") != "silabos":
        return datos
    estado = dict(datos)
    release_gate = estado.get("release_gate")
    if not isinstance(release_gate, Mapping):
        limpieza = estado.get("limpieza_silabos")
        if isinstance(limpieza, Mapping):
            release_gate = limpieza.get("release_gate")

    outputs = estado.get("outputs")
    if isinstance(outputs, list):
        estado["outputs"] = filtrar_outputs_curriculares(
            [dict(output) for output in outputs if isinstance(output, dict)],
            release_gate=release_gate,
        )
    limpieza = estado.get("limpieza_silabos")
    if isinstance(limpieza, Mapping):
        limpieza_publica = dict(limpieza)
        outputs_limpieza = limpieza_publica.get("outputs")
        if isinstance(outputs_limpieza, list):
            limpieza_publica["outputs"] = filtrar_outputs_curriculares(
                [dict(output) for output in outputs_limpieza if isinstance(output, dict)],
                release_gate=release_gate,
            )
        estado["limpieza_silabos"] = limpieza_publica
    return estado
