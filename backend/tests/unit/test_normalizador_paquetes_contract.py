"""Contract regressions for source-scoped CHH package validation."""

from __future__ import annotations

import pytest

from agente.normalizador.silabos import paquetes as paquetes_modulo
from agente.normalizador.silabos.paquetes import (
    ensamblar_paquetes_chh,
    validar_integridad_paquetes_chh,
)


def _row(*, pending_id: str, kind: str, concept_id: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id_pendiente": pending_id,
        "tipo": kind,
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "id_habilidad_fuente": "SRC_SKILL",
        "propuesta": {"id": concept_id, "nombre": concept_id},
        "decision": "ADD",
        "estado_resolucion": "ACEPTADA_POR_USUARIO",
    }
    row.update(overrides)
    return row


def _assemble(
    rows: list[dict[str, object]],
    relaciones: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return ensamblar_paquetes_chh(
        rows,
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
        relaciones=relaciones,
    )[0]


def _relation(competency: str, skill: str, tool: str = "") -> dict[str, str]:
    return {
        "id_ejecucion": "NOR_1",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "id_habilidad_fuente": "SRC_SKILL",
        "id_competencia": competency,
        "id_logro": skill,
        "id_herramienta": tool,
    }


def test_competency_only_package_is_valid() -> None:
    package = _assemble([_row(pending_id="PEN_COMP", kind="competencia", concept_id="COMP_1")])

    assert package["decision_state"] == "DECIDED"
    assert validar_integridad_paquetes_chh([package]) == ()


def test_skill_only_package_is_a_structural_error_not_a_decided_package() -> None:
    package = _assemble([_row(pending_id="PEN_SKILL", kind="habilidad", concept_id="HAB_1")])

    assert package["decision_state"] == "STRUCTURAL_ERROR"
    assert "PAQUETE_HABILIDAD_SIN_COMPETENCIA" in {
        finding.codigo for finding in validar_integridad_paquetes_chh([package])
    }


def test_same_skill_can_belong_to_two_competencies() -> None:
    package = _assemble(
        [
            _row(pending_id="PEN_COMP_1", kind="competencia", concept_id="COMP_1"),
            _row(pending_id="PEN_COMP_2", kind="competencia", concept_id="COMP_2"),
            _row(pending_id="PEN_SKILL", kind="habilidad", concept_id="HAB_1"),
        ],
        [_relation("COMP_1", "HAB_1"), _relation("COMP_2", "HAB_1")],
    )

    assert validar_integridad_paquetes_chh([package]) == ()


def test_skill_can_have_two_tools() -> None:
    package = _assemble(
        [
            _row(pending_id="PEN_COMP", kind="competencia", concept_id="COMP_1"),
            _row(pending_id="PEN_SKILL", kind="habilidad", concept_id="HAB_1"),
            _row(pending_id="PEN_TOOL_1", kind="herramienta", concept_id="HERR_1"),
            _row(pending_id="PEN_TOOL_2", kind="herramienta", concept_id="HERR_2"),
        ],
        [_relation("COMP_1", "HAB_1", "HERR_1"), _relation("COMP_1", "HAB_1", "HERR_2")],
    )

    assert validar_integridad_paquetes_chh([package]) == ()


def test_source_relation_identity_splits_shared_skill_without_losing_nn_edges() -> None:
    base = {
        "id_ejecucion": "NOR_1",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "id_habilidad_fuente": "SRC_SKILL",
    }
    source_relations = [
        {
            **base,
            "id_cob_curricular": "COB_SRC_COMP_1_TOOL_1",
            "id_competencia_fuente": "SRC_COMP_1",
            "id_herramienta_fuente": "SRC_TOOL_1",
            "id_competencia_canonica": "COMP_1",
            "id_habilidad_canonica": "HAB_1",
            "id_herramienta_canonica": "HERR_1",
        },
        {
            **base,
            "id_cob_curricular": "COB_SRC_COMP_2_TOOL_2",
            "id_competencia_fuente": "SRC_COMP_2",
            "id_herramienta_fuente": "SRC_TOOL_2",
            "id_competencia_canonica": "COMP_2",
            "id_habilidad_canonica": "HAB_1",
            "id_herramienta_canonica": "HERR_2",
        },
    ]
    rows = [
        _row(
            pending_id="PEN_1",
            kind="habilidad",
            concept_id="HAB_1",
            **base,
            id_cob_curricular="COB_SRC_COMP_1_TOOL_1",
        ),
        _row(
            pending_id="PEN_2",
            kind="habilidad",
            concept_id="HAB_1",
            **base,
            id_cob_curricular="COB_SRC_COMP_2_TOOL_2",
        ),
    ]
    fuentes = {
        "competencias_fuente.jsonl": [
            {**base, "id_competencia_fuente": "SRC_COMP_1", "id_competencia_canonica": "COMP_1"},
            {**base, "id_competencia_fuente": "SRC_COMP_2", "id_competencia_canonica": "COMP_2"},
        ],
        "habilidades_fuente.jsonl": [{**base, "id_habilidad_canonica": "HAB_1"}],
        "herramientas_fuente.jsonl": [
            {**base, "id_herramienta_fuente": "SRC_TOOL_1", "id_herramienta_canonica": "HERR_1"},
            {**base, "id_herramienta_fuente": "SRC_TOOL_2", "id_herramienta_canonica": "HERR_2"},
        ],
        "cobertura_curricular_fuente.jsonl": source_relations,
    }
    archivos = {
        "cobertura_curricular.csv": [
            _relation("COMP_1", "HAB_1", "HERR_1"),
            _relation("COMP_2", "HAB_1", "HERR_2"),
        ],
        "catalogo_competencias.csv": [
            {"id_competencia": "COMP_1", "nombre_competencia": "Competencia 1"},
            {"id_competencia": "COMP_2", "nombre_competencia": "Competencia 2"},
        ],
        "catalogo_logros.csv": [{"id_logro": "HAB_1", "nombre_logro": "Habilidad"}],
        "catalogo_herramientas.csv": [
            {"id_herramienta": "HERR_1", "nombre_herramienta": "Herramienta 1"},
            {"id_herramienta": "HERR_2", "nombre_herramienta": "Herramienta 2"},
        ],
    }

    packages = ensamblar_paquetes_chh(rows, fuentes=fuentes, archivos=archivos)

    assert len(packages) == 2
    assert {package["id_paquete_chh"] for package in packages}
    assert {package["source_identity"]["id_cob_curricular"] for package in packages} == {
        "COB_SRC_COMP_1_TOOL_1",
        "COB_SRC_COMP_2_TOOL_2",
    }
    assert all(len(package["source_relationships"]) == 1 for package in packages)
    source_components = [
        component
        for package in packages
        for component_group in package["componentes"].values()
        for component in component_group
        if component.get("source")
    ]
    assert source_components
    assert all(
        component["source_identity"] == package["source_identity"]
        for package in packages
        for component_group in package["componentes"].values()
        for component in component_group
        if component.get("source")
    )
    assert all(
        "id_cob_curricular" not in component["source"]
        for component in source_components
    )
    assert {
        (
            package["competencias"][0]["id_canonico"],
            package["herramientas"][0]["id_canonico"],
        )
        for package in packages
    } == {("COMP_1", "HERR_1"), ("COMP_2", "HERR_2")}


def test_identical_canonical_tuple_from_distinct_source_relations_stays_separate() -> None:
    base = {
        "id_ejecucion": "NOR_1",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "id_habilidad_fuente": "SRC_SKILL",
    }
    source_relations = [
        {
            **base,
            "id_cob_curricular": "COB_SRC_1",
            "id_competencia_fuente": "SRC_COMP",
            "id_herramienta_fuente": "SRC_TOOL",
            "id_competencia_canonica": "COMP_1",
            "id_habilidad_canonica": "HAB_1",
            "id_herramienta_canonica": "HERR_1",
        },
        {
            **base,
            "id_cob_curricular": "COB_SRC_2",
            "id_competencia_fuente": "SRC_COMP",
            "id_herramienta_fuente": "SRC_TOOL",
            "id_competencia_canonica": "COMP_1",
            "id_habilidad_canonica": "HAB_1",
            "id_herramienta_canonica": "HERR_1",
        },
    ]

    packages = ensamblar_paquetes_chh(
        [
            _row(
                pending_id="PEN_1",
                kind="habilidad",
                concept_id="HAB_1",
                **base,
                id_cob_curricular="COB_SRC_1",
            ),
            _row(
                pending_id="PEN_2",
                kind="habilidad",
                concept_id="HAB_1",
                **base,
                id_cob_curricular="COB_SRC_2",
            ),
        ],
        fuentes={
            "competencias_fuente.jsonl": [
                {
                    **base,
                    "id_competencia_fuente": "SRC_COMP",
                    "id_competencia_canonica": "COMP_1",
                }
            ],
            "habilidades_fuente.jsonl": [{**base, "id_habilidad_canonica": "HAB_1"}],
            "herramientas_fuente.jsonl": [
                {
                    **base,
                    "id_herramienta_fuente": "SRC_TOOL",
                    "id_herramienta_canonica": "HERR_1",
                }
            ],
            "cobertura_curricular_fuente.jsonl": source_relations,
        },
        archivos={
            "cobertura_curricular.csv": [_relation("COMP_1", "HAB_1", "HERR_1")],
            "catalogo_competencias.csv": [
                {"id_competencia": "COMP_1", "nombre_competencia": "Competencia"}
            ],
            "catalogo_logros.csv": [
                {"id_logro": "HAB_1", "nombre_logro": "Habilidad"}
            ],
            "catalogo_herramientas.csv": [
                {"id_herramienta": "HERR_1", "nombre_herramienta": "Herramienta"}
            ],
        },
    )

    assert len(packages) == 2
    assert len({package["id_paquete_chh"] for package in packages}) == 2
    assert [len(package["source_relationships"]) for package in packages] == [1, 1]
    assert {
        tuple(row["id_cob_curricular"] for row in package["source_relationships"])
        for package in packages
    } == {("COB_SRC_1",), ("COB_SRC_2",)}


def test_component_name_dedupe_keeps_provenance_and_nn_relations() -> None:
    package = _assemble(
        [
            _row(
                pending_id="PEN_COMP_1",
                kind="competencia",
                concept_id="COMP_1",
                propuesta={"id": "COMP_1", "nombre": "Gestionar campañas"},
            ),
            _row(
                pending_id="PEN_COMP_2",
                kind="competencia",
                concept_id="COMP_1",
                propuesta={"id": "COMP_1", "nombre": "gestionar CAMPAÑAS"},
            ),
            _row(pending_id="PEN_SKILL", kind="habilidad", concept_id="HAB_1"),
            _row(pending_id="PEN_TOOL_1", kind="herramienta", concept_id="HERR_1"),
            _row(pending_id="PEN_TOOL_2", kind="herramienta", concept_id="HERR_2"),
        ],
        [
            _relation("COMP_1", "HAB_1", "HERR_1"),
            _relation("COMP_1", "HAB_1", "HERR_2"),
        ],
    )

    assert len(package["competencias"]) == 1
    assert len(package["competencias"][0]["provenance"]) == 2
    assert len(package["relaciones"]) == 2
    assert {row["id_herramienta"] for row in package["relaciones"]} == {
        "HERR_1",
        "HERR_2",
    }
    assert validar_integridad_paquetes_chh([package]) == ()


@pytest.mark.parametrize("resolution", ["PENDIENTE_CATALOGACION", "REQUIERE_REVISION_HUMANA"])
def test_pending_or_review_row_never_marks_package_as_decided(resolution: str) -> None:
    package = _assemble(
        [
            _row(
                pending_id="PEN_COMP",
                kind="competencia",
                concept_id="COMP_1",
                estado_resolucion=resolution,
            )
        ]
    )

    assert package["decision_state"] == "PENDING"
    assert package["requiere_decision"] is True


def test_pending_hitl_proposal_does_not_report_missing_relations_as_structure() -> None:
    package = _assemble(
        [
            _row(
                pending_id="PEN_COMP",
                kind="competencia",
                concept_id="COMP_1",
                decision="",
                estado_resolucion="REQUIERE_REVISION_HUMANA",
            ),
            _row(
                pending_id="PEN_SKILL",
                kind="habilidad",
                concept_id="HAB_1",
                decision="",
                estado_resolucion="REQUIERE_REVISION_HUMANA",
            ),
        ]
    )

    assert package["decision_state"] == "PENDING"
    assert validar_integridad_paquetes_chh([package]) == ()


def test_indice_de_ensamblaje_conserva_componentes_y_relaciones_por_paquete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = {"id_ejecucion": "NOR_1", "carrera": "MARKETING", "periodo": "2026-1"}
    filas = [
        _row(
            pending_id="PEN_1",
            kind="competencia",
            concept_id="COMP_1",
            **base,
            id_curso="CUR_1",
            id_silabo="SIL_1",
            id_habilidad_fuente="SRC_1",
        ),
        _row(
            pending_id="PEN_2",
            kind="competencia",
            concept_id="COMP_2",
            **base,
            id_curso="CUR_1",
            id_silabo="SIL_1",
            id_habilidad_fuente="SRC_2",
        ),
    ]
    fuentes = {
        "competencias_fuente.jsonl": [
            {
                "id_competencia_fuente": "COMP_SRC_1",
                "id_competencia_canonica": "COMP_1",
            },
            {
                "id_competencia_fuente": "COMP_SRC_2",
                "id_competencia_canonica": "COMP_2",
            },
        ],
        "habilidades_fuente.jsonl": [
            {
                **base,
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_habilidad_fuente": "SRC_1",
                "id_habilidad_canonica": "HAB_1",
            },
            {
                **base,
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_habilidad_fuente": "SRC_2",
                "id_habilidad_canonica": "HAB_2",
            },
        ],
        "herramientas_fuente.jsonl": [],
        "cobertura_curricular_fuente.jsonl": [
            {
                **base,
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_habilidad_fuente": "SRC_1",
                "id_competencia_fuente": "COMP_SRC_1",
                "id_competencia_canonica": "COMP_1",
                "id_habilidad_canonica": "HAB_1",
            },
            {
                **base,
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_habilidad_fuente": "SRC_2",
                "id_competencia_fuente": "COMP_SRC_2",
                "id_competencia_canonica": "COMP_2",
                "id_habilidad_canonica": "HAB_2",
            },
        ],
    }
    relaciones = [
        {
            **base,
            "id_curso": "CUR_1",
            "id_silabo": "SIL_1",
            "id_habilidad_fuente": "SRC_1",
            "id_competencia": "COMP_1",
            "id_logro": "HAB_1",
            "id_herramienta": "",
        },
        {
            **base,
            "id_curso": "CUR_1",
            "id_silabo": "SIL_1",
            "id_habilidad_fuente": "SRC_2",
            "id_competencia": "COMP_2",
            "id_logro": "HAB_2",
            "id_herramienta": "",
        },
    ]
    archivos = {
        "cobertura_curricular.csv": relaciones,
        "catalogo_competencias.csv": [
            {"id_competencia": "COMP_1", "nombre_competencia": "Competencia 1"},
            {"id_competencia": "COMP_2", "nombre_competencia": "Competencia 2"},
        ],
        "catalogo_logros.csv": [
            {"id_logro": "HAB_1", "nombre_logro": "Habilidad 1"},
            {"id_logro": "HAB_2", "nombre_logro": "Habilidad 2"},
        ],
        "catalogo_herramientas.csv": [],
    }
    preparadas = [paquetes_modulo.preparar_fila_paquete(fila) for fila in filas]
    agrupadas: dict[str, list[dict[str, object]]] = {}
    for fila in preparadas:
        agrupadas.setdefault(str(fila["id_paquete_chh"]), []).append(fila)
    esperado_sin_indice = [
        paquetes_modulo._assemble_one(
            package_id,
            filas_paquete,
            fuentes=fuentes,
            relaciones=relaciones,
            archivos=archivos,
        )
        for package_id, filas_paquete in sorted(agrupadas.items())
    ]
    llamadas = 0
    original = paquetes_modulo._source_row_matches_package

    def contar_busqueda(*args: object, **kwargs: object) -> bool:
        nonlocal llamadas
        llamadas += 1
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(paquetes_modulo, "_source_row_matches_package", contar_busqueda)

    resultado = ensamblar_paquetes_chh(
        filas,
        fuentes=fuentes,
        relaciones=relaciones,
        archivos=archivos,
    )

    assert llamadas == 0
    assert resultado == esperado_sin_indice
    assert len(resultado) == 2
    assert [paquete["id_habilidad_fuente"] for paquete in resultado] == ["SRC_1", "SRC_2"]
    assert [
        paquete["competencias"][0]["id_canonico"] for paquete in resultado
    ] == ["COMP_1", "COMP_2"]
    assert [
        paquete["relaciones"][0]["id_logro"] for paquete in resultado
    ] == ["HAB_1", "HAB_2"]
    assert [len(paquete["source_relationships"]) for paquete in resultado] == [1, 1]


def test_contract_exposes_explicit_canonical_triples_and_pending_separately() -> None:
    package = _assemble(
        [
            _row(
                pending_id="PEN_COMP",
                kind="competencia",
                concept_id="COMP_1",
                decision="",
                estado_resolucion="PENDIENTE_CATALOGACION",
            ),
            _row(
                pending_id="PEN_SKILL",
                kind="habilidad",
                concept_id="HAB_1",
                decision="",
                estado_resolucion="PENDIENTE_CATALOGACION",
            ),
        ],
        relaciones=[_relation("COMP_1", "HAB_1")],
    )

    assert package["relaciones_canonicas"] == []
    assert {item["id_pendiente"] for item in package["propuestas_pendientes"]} == {
        "PEN_COMP",
        "PEN_SKILL",
    }
    assert package["source_evidence"]["rows"] == package["filas"]


def test_profile_proposal_on_canonical_candidate_stays_pending_and_visible() -> None:
    package = _assemble(
        [
            _row(
                pending_id="PEN_COMP",
                kind="competencia",
                concept_id="COMP_1",
            ),
            _row(
                pending_id="PEN_PROFILE",
                kind="habilidad",
                concept_id="HAB_1",
                decision="",
                estado_resolucion="CANONIZADA_CON_PROPUESTA_PERFIL",
                propuesta={"id": "HAB_PROFILE", "nombre": "Optimizar campañas"},
            )
        ]
    )

    assert package["decision_state"] == "PENDING"
    assert package["requiere_decision"] is True
    assert package["propuestas_pendientes"] == [
        {
            "tipo": "habilidad",
            "nombre": "Optimizar campañas",
            "descripcion": "",
            "id_pendiente": "PEN_PROFILE",
            "evidencia": [],
            "source_identity": package["source_identity"],
        }
    ]


def test_trusted_source_tool_name_may_equal_its_description() -> None:
    package = ensamblar_paquetes_chh(
        [
            _row(
                pending_id="PEN_TOOL",
                kind="herramienta",
                concept_id="HERR_EXCEL",
                propuesta=None,
                decision="",
                estado_resolucion="PENDIENTE_CATALOGACION",
            )
        ],
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
        fuentes={
            "herramientas_fuente.jsonl": [
                {
                    "id_ejecucion": "NOR_1",
                    "carrera": "MARKETING",
                    "periodo": "2026-1",
                    "id_curso": "CUR_1",
                    "id_silabo": "SIL_1",
                    "id_habilidad_fuente": "SRC_SKILL",
                    "id_herramienta_fuente": "SRC_EXCEL",
                    "id_herramienta_canonica": "",
                    "nombre_herramienta": "Excel",
                    "texto_evidencia": "Excel",
                }
            ]
        },
    )[0]

    source_tool = next(item for item in package["herramientas"] if item.get("source"))
    assert source_tool["nombre"] == "Excel"


@pytest.mark.parametrize(
    "estado_resolucion",
    ("PENDIENTE_AMPLIACION_PERFIL", "CANONIZADA_CON_PROPUESTA_PERFIL"),
)
def test_unresolved_profile_proposal_is_not_merged_into_accepted_component(
    estado_resolucion: str,
) -> None:
    base = {
        "id_ejecucion": "NOR_1",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "id_habilidad_fuente": "SRC_SKILL",
    }
    package = ensamblar_paquetes_chh(
        [
            _row(
                pending_id="PEN_PROFILE",
                kind="habilidad",
                concept_id="HAB_PROFILE",
                decision="",
                estado_resolucion=estado_resolucion,
                id_canonico="HAB_PROFILE",
                propuesta={"id": "HAB_PROFILE", "nombre": "Optimizar campañas"},
                **base,
            )
        ],
        fuentes={
            "competencias_fuente.jsonl": [
                {
                    **base,
                    "id_competencia_fuente": "SRC_COMP",
                    "id_competencia_canonica": "COMP_1",
                    "nombre_competencia_fuente": "Gestionar campañas",
                }
            ],
            "habilidades_fuente.jsonl": [
                {
                    **base,
                    "id_habilidad_canonica": "HAB_1",
                    "descripcion_fuente": "Optimizar campañas",
                }
            ],
            "cobertura_curricular_fuente.jsonl": [
                {
                    **base,
                    "id_cob_curricular": "COB_SRC_1",
                    "id_competencia_fuente": "SRC_COMP",
                    "id_habilidad_canonica": "HAB_1",
                    "id_competencia_canonica": "COMP_1",
                    "id_herramienta_canonica": "",
                }
            ],
        },
        archivos={
            "catalogo_logros.csv": [
                {"id_logro": "HAB_1", "nombre_logro": "Optimizar campañas"}
            ]
        },
    )[0]

    accepted = next(skill for skill in package["habilidades"] if skill["canonical"])
    pending = next(skill for skill in package["habilidades"] if not skill["canonical"])

    assert len(package["habilidades"]) == 2
    assert accepted["id_canonico"] == "HAB_1"
    assert pending["id_canonico"] == ""
    assert pending["id_canonico_propuesto"] == "HAB_PROFILE"
    assert pending["provenance"][0]["id_canonico_propuesto"] == "HAB_PROFILE"
    assert package["relaciones_canonicas"] == []


def test_comp_ref_is_an_explicit_pending_competency_blocker() -> None:
    source_relation = {
        "id_ejecucion": "NOR_1",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "id_habilidad_fuente": "SRC_SKILL",
        "id_cob_curricular": "COB_SRC_REF",
        "id_competencia_fuente": "COMP_REF_UNKNOWN",
        "id_habilidad_canonica": "",
        "id_competencia_canonica": "",
        "id_herramienta_canonica": "",
    }
    package = ensamblar_paquetes_chh(
        [
            _row(
                pending_id="PEN_SKILL",
                kind="habilidad",
                concept_id="HAB_1",
                decision="",
                estado_resolucion="REQUIERE_REVISION_HUMANA",
                id_cob_curricular="COB_SRC_REF",
            )
        ],
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
        fuentes={
            "competencias_fuente.jsonl": [
                {
                    **source_relation,
                    "nombre_competencia_fuente": "",
                    "estado_resolucion": "REFERENCIA_NO_DECLARADA",
                }
            ],
            "cobertura_curricular_fuente.jsonl": [source_relation],
        },
    )[0]

    assert package["decision_state"] == "PENDING"
    assert package["relaciones_canonicas"] == []
    assert package["competency_blockers"] == [
        {
            "code": "COMPETENCY_SOURCE_MAPPING_REQUIRED",
            "id_competencia_fuente": "COMP_REF_UNKNOWN",
            "id_cob_curricular": "COB_SRC_REF",
        }
    ]
    assert "COMPETENCY_SOURCE_MAPPING_REQUIRED" in {
        finding.codigo for finding in validar_integridad_paquetes_chh([package])
    }

    mapped_relation = {
        **source_relation,
        "id_competencia_canonica": "COMP_1",
    }
    mapped = ensamblar_paquetes_chh(
        [
            _row(
                pending_id="PEN_SKILL",
                kind="habilidad",
                concept_id="HAB_1",
                decision="",
                estado_resolucion="REQUIERE_REVISION_HUMANA",
                id_cob_curricular="COB_SRC_REF",
            )
        ],
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
        fuentes={
            "competencias_fuente.jsonl": [
                {
                    **mapped_relation,
                    "nombre_competencia_fuente": "Competencia mapeada",
                    "estado_resolucion": "RESUELTA_POR_USUARIO",
                }
            ],
            "cobertura_curricular_fuente.jsonl": [mapped_relation],
        },
    )[0]

    assert mapped["competency_blockers"] == []
    assert "COMPETENCY_SOURCE_MAPPING_REQUIRED" not in {
        finding.codigo for finding in validar_integridad_paquetes_chh([mapped])
    }


def test_multi_tool_source_package_opens_into_unique_complete_triples() -> None:
    base = _assemble(
        [
            _row(pending_id="PEN_COMP", kind="competencia", concept_id="Competencia A"),
            _row(pending_id="PEN_SKILL", kind="habilidad", concept_id="Habilidad A"),
            _row(pending_id="PEN_TOOL_A", kind="herramienta", concept_id="Herramienta A"),
            _row(pending_id="PEN_TOOL_B", kind="herramienta", concept_id="Herramienta B"),
        ]
    )

    fans = paquetes_modulo._abrir_paquetes_por_triple(base)

    assert len(fans) == 2
    assert len({fan["id_paquete_chh"] for fan in fans}) == 2
    for fan in fans:
        assert len(fan["competencias"]) == 1
        assert len(fan["habilidades"]) == 1
        assert len(fan["herramientas"]) == 1
    filas_por_herramienta = {
        fan["herramientas"][0]["nombre"]: {fila["id_pendiente"] for fila in fan["filas"]}
        for fan in fans
    }
    assert filas_por_herramienta == {
        "Herramienta A": {"PEN_COMP", "PEN_SKILL", "PEN_TOOL_A"},
        "Herramienta B": {"PEN_COMP", "PEN_SKILL", "PEN_TOOL_B"},
    }


def test_source_package_without_complete_triple_is_not_offered_for_decision() -> None:
    base = _assemble(
        [
            _row(pending_id="PEN_COMP", kind="competencia", concept_id="Competencia A"),
            _row(pending_id="PEN_SKILL", kind="habilidad", concept_id="Habilidad A"),
        ]
    )

    assert paquetes_modulo._abrir_paquetes_por_triple(base) == []


def test_single_complete_triple_keeps_the_source_package_identity() -> None:
    base = _assemble(
        [
            _row(pending_id="PEN_COMP", kind="competencia", concept_id="Competencia A"),
            _row(pending_id="PEN_SKILL", kind="habilidad", concept_id="Habilidad A"),
            _row(pending_id="PEN_TOOL_A", kind="herramienta", concept_id="Herramienta A"),
        ]
    )

    [fan] = paquetes_modulo._abrir_paquetes_por_triple(base)

    assert fan["id_paquete_chh"] == base["id_paquete_chh"]
    assert [componente["nombre"] for componente in fan["herramientas"]] == ["Herramienta A"]
