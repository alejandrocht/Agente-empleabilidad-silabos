import hashlib
import json

import pytest

from agente.normalizador.silabos import paquetes as paquetes_modulo
from agente.normalizador.silabos import (
    paquetes_componentes,
    paquetes_componentes_nombres,
    paquetes_relaciones,
)
from agente.normalizador.silabos.paquetes import (
    IdentidadFuenteIncompleta,
    ensamblar_paquetes_chh,
    id_paquete_chh,
    identidad_fuente_chh,
    revision_paquetes_chh,
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


def test_component_projection_reexports_preserve_canonical_bytes_and_review_hash():
    packages = ensamblar_paquetes_chh(
        [_row()], id_ejecucion="NOR_1", carrera="MARKETING", periodo="2026-1"
    )
    payload = json.dumps(packages, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    assert hashlib.sha256(payload.encode("utf-8")).hexdigest() == (
        "b77ed9e1da2e7520d387341a06c847d4e92b3d89349f76b7ac847e840942b8e3"
    )
    assert revision_paquetes_chh(packages) == "4c9079e957468df1"
    assert (
        paquetes_modulo.PACKAGE_SOURCE_IDENTITY_FIELD
        is paquetes_componentes.PACKAGE_SOURCE_IDENTITY_FIELD
    )
    assert paquetes_modulo._component_from_row is paquetes_componentes._component_from_row
    assert paquetes_modulo._unique_components is paquetes_componentes._unique_components
    for name in (
        "_unique_components",
        "_component_identifier",
        "_component_name",
        "_component_key",
        "_component_source_key",
        "_has_structured_proposal",
        "_is_provisional_component",
        "_with_component_provenance",
        "_component_provenance",
        "_merge_components",
        "_normalized_name",
        "_usable_display_name",
    ):
        assert getattr(paquetes_componentes, name) is getattr(paquetes_componentes_nombres, name)
        assert getattr(paquetes_relaciones, name) is getattr(paquetes_componentes_nombres, name)
        assert getattr(paquetes_modulo, name) is getattr(paquetes_componentes_nombres, name)
    for name in (
        "PACKAGE_SOURCE_IDENTITY_FIELD",
        "_TYPE_ORDER",
        "_UNRESOLVED_RESOLUTION_STATES",
        "_TECHNICAL_NAME",
        "_HASH_NAME",
    ):
        assert getattr(paquetes_componentes, name) is getattr(paquetes_componentes_nombres, name)
        assert getattr(paquetes_relaciones, name) is getattr(paquetes_componentes_nombres, name)
        assert getattr(paquetes_modulo, name) is getattr(paquetes_componentes_nombres, name)
    assert "paquetes" not in paquetes_componentes.__dict__
    assert "paquetes_componentes" not in paquetes_componentes_nombres.__dict__
    assert "paquetes_relaciones" not in paquetes_componentes_nombres.__dict__
    assert paquetes_modulo.PACKAGE_ID_FIELD is paquetes_relaciones.PACKAGE_ID_FIELD
    assert paquetes_modulo._PackageAssemblyIndex is paquetes_relaciones._PackageAssemblyIndex
    assert paquetes_modulo._identity_key is paquetes_relaciones._identity_key
    assert paquetes_modulo._source_relation_matches is paquetes_relaciones._source_relation_matches
    assert (
        paquetes_modulo.relaciones_para_paquete_chh
        is not paquetes_relaciones.relaciones_para_paquete_chh
    )
    assert paquetes_relaciones._paquetes_componentes is paquetes_componentes
    assert "paquetes" not in paquetes_relaciones.__dict__


def test_relation_wrappers_inject_facade_package_hash(monkeypatch: pytest.MonkeyPatch):
    identity = identidad_fuente_chh(
        _row(), id_ejecucion="NOR_1", carrera="MARKETING", periodo="2026-1"
    )
    monkeypatch.setattr(paquetes_modulo, "id_paquete_chh", lambda _: "PKG_MONKEYPATCHED")

    selected = paquetes_modulo.relaciones_fuente_para_paquete_chh(
        [{**identity, "id_competencia": "COMP_1", "id_logro": "HAB_1"}], identity
    )

    assert selected[0]["id_paquete_chh"] == "PKG_MONKEYPATCHED"


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
            "id_logro": "HAB_1",
            "id_herramienta": "",
        },
        {
            "id_curso": "CUR_1",
            "id_silabo": "SIL_1",
            "id_competencia": "COMP_2",
            "id_logro": "HAB_2",
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
        "habilidades": [{"id_logro": "HAB_1", "id_canonico": "HAB_1"}],
        "herramientas": [{"id_herramienta": "HERR_1", "id_canonico": "HERR_1"}],
        "componentes": {
            "competencias": [{"id_competencia": "COMP_1", "id_canonico": "COMP_1"}],
            "habilidades": [{"id_logro": "HAB_1", "id_canonico": "HAB_1"}],
            "herramientas": [{"id_herramienta": "HERR_1", "id_canonico": "HERR_1"}],
        },
        "relaciones": [
            {
                "id_cob_curricular": "COB_1",
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_competencia": "COMP_1",
                "id_logro": "HAB_1",
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
                "id_logro": "HAB_2",
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


def test_pending_skill_package_inherits_competency_from_source_coverage():
    row = _row(
        tipo="habilidad",
        propuesta=None,
        estado_resolucion="PENDIENTE_CATALOGACION",
    )
    fuentes = {
        "competencias_fuente.jsonl": [
            {
                "id_ejecucion": "NOR_1",
                "carrera": "MARKETING",
                "periodo": "2026-1",
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_competencia_fuente": "SRC_COMP",
                "id_competencia_canonica": "COMP_1",
                "nombre_competencia_fuente": "Gestionar campañas",
            }
        ],
        "habilidades_fuente.jsonl": [
            {
                "id_ejecucion": "NOR_1",
                "carrera": "MARKETING",
                "periodo": "2026-1",
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_habilidad_fuente": "SRC_SKILL",
                "id_habilidad_canonica": "",
                "descripcion_fuente": "Analizar campañas",
            }
        ],
        "herramientas_fuente.jsonl": [],
        "cobertura_curricular_fuente.jsonl": [
            {
                "id_ejecucion": "NOR_1",
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_competencia": "SRC_COMP",
                "id_logro": "SRC_SKILL",
                "id_herramienta": "",
                "id_competencia_fuente": "SRC_COMP",
                "id_habilidad_fuente": "SRC_SKILL",
                "id_competencia_canonica": "COMP_1",
                "id_habilidad_canonica": "",
                "id_herramienta_canonica": "",
            }
        ],
    }

    package = ensamblar_paquetes_chh(
        [row],
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
        fuentes=fuentes,
    )[0]

    assert {item["id_canonico"] for item in package["competencias"]} == {"COMP_1"}
    assert package["decision_state"] == "PENDING"
    assert package["source_relationships"]
    assert validar_integridad_paquetes_chh([package]) == ()


def test_skill_source_description_stays_metadata_and_never_becomes_component_name():
    source_description = "Diseña un plan de comunicación para clientes B2B."
    package = ensamblar_paquetes_chh(
        [
            _row(
                tipo="habilidad",
                propuesta=None,
                descripcion_fuente=source_description,
            )
        ],
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
        fuentes={
            "habilidades_fuente.jsonl": [
                {
                    "id_ejecucion": "NOR_1",
                    "carrera": "MARKETING",
                    "periodo": "2026-1",
                    "id_curso": "CUR_1",
                    "id_silabo": "SIL_1",
                    "id_habilidad_fuente": "SRC_SKILL",
                    "id_habilidad_canonica": "",
                    "descripcion_fuente": source_description,
                }
            ]
        },
    )[0]

    assert all(item["nombre"] == "" for item in package["habilidades"])
    skill = package["habilidades"][0]
    assert skill["id_fuente"] == "SRC_SKILL"
    assert skill["descripcion"] == source_description
    assert package["filas"][0]["descripcion_fuente"] == source_description


def test_skill_source_name_stays_metadata_when_no_proposal_or_catalog_name_exists():
    source_name = "Nombre de habilidad declarado por la fuente"
    package = ensamblar_paquetes_chh(
        [
            _row(
                tipo="habilidad",
                propuesta=None,
                nombre_habilidad=source_name,
                descripcion_fuente="Describe la actividad del sílabo.",
            )
        ],
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
    )[0]

    skill = package["habilidades"][0]
    assert skill["nombre"] == ""
    assert skill["nombre_fuente"] == source_name
    assert skill["row"]["nombre_habilidad"] == source_name


def test_skill_proposal_name_remains_displayable_without_source_description():
    source_description = "Diseña un plan de comunicación para clientes B2B."
    package = ensamblar_paquetes_chh(
        [
            _row(
                tipo="habilidad",
                propuesta={"id": "HAB_LLM", "nombre": "Planificación de comunicación"},
                descripcion_fuente=source_description,
            )
        ],
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
        fuentes={
            "habilidades_fuente.jsonl": [
                {
                    "id_ejecucion": "NOR_1",
                    "carrera": "MARKETING",
                    "periodo": "2026-1",
                    "id_curso": "CUR_1",
                    "id_silabo": "SIL_1",
                    "id_habilidad_fuente": "SRC_SKILL",
                    "id_habilidad_canonica": "",
                    "descripcion_fuente": source_description,
                }
            ]
        },
    )[0]

    names = {item["nombre"] for item in package["habilidades"]}
    assert "Planificación de comunicación" in names
    assert source_description not in names


def test_package_component_prefers_catalog_name_and_keeps_llm_proposal_metadata():
    identity = {
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
                tipo="habilidad",
                propuesta={"id": "HAB_CAN", "nombre": "Nombre propuesto por el LLM"},
            )
        ],
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
        fuentes={
            "habilidades_fuente.jsonl": [
                {**identity, "id_habilidad_canonica": "HAB_CAN"}
            ]
        },
        archivos={
            "cobertura_curricular.csv": [
                {
                    "id_curso": "CUR_1",
                    "id_silabo": "SIL_1",
                    "id_competencia": "COMP_CAN",
                    "id_logro": "HAB_CAN",
                    "id_herramienta": "",
                    "source_identity": identity,
                }
            ],
            "catalogo_logros.csv": [
                {"id_logro": "HAB_CAN", "nombre_logro": "Nombre del catálogo"}
            ],
        },
    )[0]

    habilidades = package["habilidades"]
    assert len(habilidades) == 1
    assert habilidades[0]["nombre"] == "Nombre del catálogo"
    assert habilidades[0]["nombre_propuesto"] == "Nombre propuesto por el LLM"
    assert habilidades[0]["propuesta"]["nombre"] == "Nombre propuesto por el LLM"


def test_skill_proposal_id_without_name_is_not_a_display_name():
    package = ensamblar_paquetes_chh(
        [
            _row(
                tipo="habilidad",
                propuesta={"id": "HAB_SRC_proposal_only", "nombre": ""},
            )
        ],
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
    )[0]

    skill = package["habilidades"][0]
    assert skill["nombre"] == ""
    assert skill["id_canonico"] == "HAB_SRC_proposal_only"


def test_skill_catalog_name_replaces_blank_source_projection():
    source_description = "Diseña un plan de comunicación para clientes B2B."
    identity = {
        "id_ejecucion": "NOR_1",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "id_habilidad_fuente": "SRC_SKILL",
    }
    package = ensamblar_paquetes_chh(
        [_row(tipo="habilidad", propuesta=None, descripcion_fuente=source_description)],
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
        fuentes={
            "habilidades_fuente.jsonl": [
                {
                    **identity,
                    "id_habilidad_canonica": "HAB_CAN",
                    "descripcion_fuente": source_description,
                }
            ]
        },
        archivos={
            "cobertura_curricular.csv": [
                {
                    "id_curso": "CUR_1",
                    "id_silabo": "SIL_1",
                    "id_competencia": "COMP_1",
                    "id_logro": "HAB_CAN",
                    "id_herramienta": "",
                    "source_identity": identity,
                }
            ],
            "catalogo_logros.csv": [
                {"id_logro": "HAB_CAN", "nombre_logro": "Planificación de comunicación"}
            ],
        },
    )[0]

    names = {item["nombre"] for item in package["habilidades"]}
    assert "Planificación de comunicación" in names
    assert source_description not in names
    source_projection = next(
        item for item in package["habilidades"] if item.get("source")
    )
    assert source_projection["id_fuente"] == "SRC_SKILL"
    assert source_projection["source"]["descripcion_fuente"] == source_description


def test_skill_catalog_name_survives_without_canonical_coverage():
    source_description = "Diseña un plan de comunicación para clientes B2B."
    identity = {
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
                id_pendiente="PEN_COMP",
                tipo="competencia",
                propuesta={"id": "COMP_1", "nombre": "Gestionar campañas"},
            ),
            _row(
                id_pendiente="PEN_SKILL",
                tipo="habilidad",
                propuesta=None,
                estado_resolucion="PENDIENTE_CATALOGACION",
                descripcion_fuente=source_description,
            ),
        ],
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
        fuentes={
            "habilidades_fuente.jsonl": [
                {
                    **identity,
                    "id_habilidad_canonica": "HAB_CAN",
                    "descripcion_fuente": source_description,
                }
            ]
        },
        archivos={
            "cobertura_curricular.csv": [],
            "catalogo_logros.csv": [
                {"id_logro": "HAB_CAN", "nombre_logro": "Planificación de comunicación"}
            ],
        },
    )[0]

    source_projection = next(item for item in package["habilidades"] if item.get("source"))
    assert source_projection["nombre"] == "Planificación de comunicación"
    assert package["decision_state"] == "PENDING"
    assert package["relaciones"] == []
    assert package["source_relationships"] == []


def test_empty_competency_references_keep_distinct_source_provenance():
    source_relations = [
        {
            "id_ejecucion": "NOR_1",
            "id_curso": "CUR_1",
            "id_silabo": "SIL_1",
            "id_habilidad_fuente": "SRC_SKILL",
            "id_competencia_fuente": f"COMP_REF_{index}",
            "id_competencia_canonica": "",
            "id_habilidad_canonica": "",
            "id_herramienta_canonica": "",
        }
        for index in ("A", "B")
    ]
    fuentes = {
        "competencias_fuente.jsonl": [
            {
                "id_ejecucion": "NOR_1",
                "carrera": "MARKETING",
                "periodo": "2026-1",
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_competencia_fuente": f"COMP_REF_{index}",
                "id_competencia_canonica": "",
                "nombre_competencia_fuente": "",
            }
            for index in ("A", "B")
        ],
        "cobertura_curricular_fuente.jsonl": source_relations,
    }

    package = ensamblar_paquetes_chh(
        [_row(tipo="habilidad", propuesta={"id": "HAB_1", "nombre": "Analizar datos"})],
        id_ejecucion="NOR_1",
        carrera="MARKETING",
        periodo="2026-1",
        fuentes=fuentes,
    )[0]

    references = [
        item for item in package["competencias"] if item["id_fuente"].startswith("COMP_REF_")
    ]
    assert {item["id_fuente"] for item in references} == {"COMP_REF_A", "COMP_REF_B"}
    assert all(item["nombre"] == "" for item in references)
    assert {
        item["source"]["id_competencia_fuente"] for item in references
    } == {"COMP_REF_A", "COMP_REF_B"}
