from __future__ import annotations

from typing import Any, cast

from agente.normalizador.silabos.paquetes import ensamblar_paquetes_chh


def test_technical_competency_proposal_name_survives_package_projection() -> None:
    row: dict[str, object] = {
        "id_pendiente": "PEN_TEC_1",
        "tipo": "competencia",
        "estado_resolucion": "PENDIENTE_CATALOGACION",
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "id_habilidad_fuente": "SRC_SKILL",
        "propuesta": {
            "nombre_competencia": "Diseño técnico de arquitecturas",
            "descripcion_breve_competencia": (
                "Selecciona patrones según atributos de calidad."
            ),
        },
        "evidencia": ["Diseña arquitecturas de software."],
    }
    package = cast(
        dict[str, Any],
        ensamblar_paquetes_chh(
            [row],
            id_ejecucion="NOR_1",
            carrera="MARKETING",
            periodo="2026-1",
        )[0],
    )

    assert package["competencias"][0]["nombre"] == "Diseño técnico de arquitecturas"
    assert package["propuestas_pendientes"][0]["nombre"] == (
        "Diseño técnico de arquitecturas"
    )
    assert package["propuestas_pendientes"][0]["descripcion"] == (
        "Selecciona patrones según atributos de calidad."
    )
