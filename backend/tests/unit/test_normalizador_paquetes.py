import pytest

from agente.normalizador.silabos.paquetes import (
    IdentidadFuenteIncompleta,
    ensamblar_paquetes_chh,
    id_paquete_chh,
    identidad_fuente_chh,
    validar_integridad_paquetes_chh,
)


def _row(**overrides):
    row = {
        "id_pendiente": "PEN_1",
        "tipo": "competencia",
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "id_habilidad_fuente": "SRC_SKILL",
        "propuesta": {"nombre": "Gestionar campañas"},
        "evidencia": ["Gestionar campañas."],
    }
    row.update(overrides)
    return row


def test_package_identity_includes_execution_and_course_context():
    first = identidad_fuente_chh(
        _row(), id_ejecucion="NOR_1", carrera="MARKETING", periodo="2026-1"
    )
    second = identidad_fuente_chh(
        _row(id_curso="CUR_2"), id_ejecucion="NOR_2", carrera="MARKETING", periodo="2026-1"
    )

    assert first["id_habilidad_fuente"] == second["id_habilidad_fuente"]
    assert id_paquete_chh(first) != id_paquete_chh(second)


def test_packages_keep_same_label_from_different_source_packages_separate():
    packages = ensamblar_paquetes_chh(
        [
            _row(id_pendiente="PEN_1", id_curso="CUR_1"),
            _row(id_pendiente="PEN_2", id_curso="CUR_2"),
        ],
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
    )

    assert len(packages) == 2
    assert all(package["requiere_decision"] for package in packages)


def test_relations_for_same_course_and_syllabus_do_not_cross_source_packages():
    rows = [
        _row(id_pendiente="PEN_1", id_habilidad_fuente="SRC_1"),
        _row(id_pendiente="PEN_2", id_habilidad_fuente="SRC_2"),
    ]
    fuentes = {
        "competencias_fuente.jsonl": [
            {
                "id_ejecucion": "NOR_1",
                "carrera": "MARKETING",
                "periodo": "2026-1",
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_habilidad_fuente": "SRC_1",
                "id_competencia_canonica": "COMP_1",
            },
            {
                "id_ejecucion": "NOR_1",
                "carrera": "MARKETING",
                "periodo": "2026-1",
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_habilidad_fuente": "SRC_2",
                "id_competencia_canonica": "COMP_2",
            },
        ],
        "habilidades_fuente.jsonl": [
            {
                "id_ejecucion": "NOR_1",
                "carrera": "MARKETING",
                "periodo": "2026-1",
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_habilidad_fuente": "SRC_1",
                "id_habilidad_canonica": "HAB_1",
            },
            {
                "id_ejecucion": "NOR_1",
                "carrera": "MARKETING",
                "periodo": "2026-1",
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_habilidad_fuente": "SRC_2",
                "id_habilidad_canonica": "HAB_2",
            },
        ],
        "herramientas_fuente.jsonl": [],
    }
    relaciones = [
        {
            "id_curso": "CUR_1",
            "id_silabo": "SIL_1",
            "id_competencia": "COMP_1",
            "id_habilidad": "HAB_1",
            "id_herramienta": "",
        },
        {
            "id_curso": "CUR_1",
            "id_silabo": "SIL_1",
            "id_competencia": "COMP_2",
            "id_habilidad": "HAB_2",
            "id_herramienta": "",
        },
    ]

    packages = ensamblar_paquetes_chh(
        rows,
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
        fuentes=fuentes,
        relaciones=relaciones,
    )

    assert len(packages) == 2
    assert {
        (package["id_habilidad_fuente"], package["relaciones"][0]["id_competencia"])
        for package in packages
    } == {("SRC_1", "COMP_1"), ("SRC_2", "COMP_2")}


def test_competency_only_package_is_valid_and_six_field_relation_maps_correctly():
    competency_only = ensamblar_paquetes_chh(
        [_row()], id_ejecucion="NOR_1", carrera="MARKETING", periodo="2026-1"
    )[0]
    assert validar_integridad_paquetes_chh([competency_only]) == ()

    package = {
        **competency_only,
        "habilidades": [{"id_habilidad": "HAB_1", "id_canonico": "HAB_1"}],
        "herramientas": [{"id_herramienta": "HERR_1", "id_canonico": "HERR_1"}],
        "componentes": {
            "competencias": [{"id_competencia": "COMP_1", "id_canonico": "COMP_1"}],
            "habilidades": [{"id_habilidad": "HAB_1", "id_canonico": "HAB_1"}],
            "herramientas": [{"id_herramienta": "HERR_1", "id_canonico": "HERR_1"}],
        },
        "relaciones": [
            {
                "id_cob_curricular": "COB_1",
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_competencia": "COMP_1",
                "id_habilidad": "HAB_1",
                "id_herramienta": "HERR_1",
                "source_identity": competency_only["source_identity"],
            }
        ],
    }
    assert validar_integridad_paquetes_chh([package]) == ()


def test_package_identity_fails_closed_without_source_skill():
    with pytest.raises(IdentidadFuenteIncompleta, match="id_habilidad_fuente"):
        ensamblar_paquetes_chh(
            [_row(id_habilidad_fuente="")],
            id_ejecucion="NOR_1",
            carrera="MARKETING",
            periodo="2026-1",
        )


def test_competency_only_package_does_not_inherit_another_packages_skill_requirement():
    competency_only = _row(id_pendiente="PEN_COMP_ONLY", id_habilidad_fuente="SRC_ONLY")
    skill_package_competency = _row(
        id_pendiente="PEN_COMP_WITH_SKILL",
        id_habilidad_fuente="SRC_WITH_SKILL",
        propuesta={"id": "COMP_2", "nombre": "Otra competencia"},
    )
    skill = _row(
        id_pendiente="PEN_SKILL",
        tipo="habilidad",
        id_habilidad_fuente="SRC_WITH_SKILL",
        propuesta={"id": "HAB_2", "nombre": "Otra habilidad"},
    )
    packages = ensamblar_paquetes_chh(
        [competency_only, skill_package_competency, skill],
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
        relaciones=[
            {
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_competencia": "COMP_2",
                "id_habilidad": "HAB_2",
                "id_herramienta": "",
                "source_identity": {
                    "id_ejecucion": "NOR_1",
                    "carrera": "MARKETING",
                    "periodo": "2026-1",
                    "id_curso": "CUR_1",
                    "id_silabo": "SIL_1",
                    "id_habilidad_fuente": "SRC_WITH_SKILL",
                },
            }
        ],
    )

    assert len(packages) == 2
    assert validar_integridad_paquetes_chh(packages) == ()
