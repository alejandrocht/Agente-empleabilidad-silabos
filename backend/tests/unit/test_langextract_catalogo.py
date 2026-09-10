from __future__ import annotations

import csv
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from agente.normalizador.silabos import langextract_catalogo
from agente.normalizador.silabos.langextract_catalogo import (
    CatalogSelection,
    ReferenceCatalogSelection,
    preflight_reference_catalog,
    preflight_tool_catalog,
    suggest_reference_catalog_document,
)
from agente.normalizador.silabos.langextract_ciar import construir_payload_langextract
from agente.normalizador.silabos.langextract_runner import (
    ejecutar_corpus_langextract,
    resolver_resultados_guardados,
)

_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _write_docx(path: Path, paragraphs: list[str]) -> None:
    body = "".join(f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs)
    document_xml = f'<w:document xmlns:w="{_WORD_NAMESPACE}"><w:body>{body}</w:body></w:document>'
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)


def _write_catalog(directory: Path) -> CatalogSelection:
    directory.mkdir()
    rows = {
        "catalogo_competencias.csv": [
            [
                "id_competencia",
                "nombre_competencia",
                "descripcion_breve_competencia",
                "tipo_competencia",
            ],
            ["COMP_BUILD", "Construcción de software", "Construir software.", "dura"],
        ],
        "catalogo_habilidades.csv": [
            ["id_habilidad", "nombre_habilidad", "descripcion_breve"],
            ["HAB_NODE", "Implementar servicios", "Implementar servicios."],
            ["HAB_SAP", "Configurar procesos", "Configurar procesos."],
        ],
        "catalogo_herramientas.csv": [
            ["id_herramienta", "nombre_herramienta", "descripcion_breve_herramienta"],
            ["TOOL_NODE", "Node.js", "Runtime."],
            ["TOOL_GIT", "Git", "Version control."],
            ["TOOL_SAP", "SAP", "ERP."],
            ["TOOL_SAP_ONE", "SAP Business One", "ERP."],
        ],
    }
    for filename, contents in rows.items():
        with (directory / filename).open("w", newline="", encoding="utf-8-sig") as stream:
            csv.writer(stream).writerows(contents)
    (directory / "catalogo_metadata.json").write_text(
        json.dumps(
            {
                "career": "Generic Software",
                "period": "2026-1",
                "version": "test-v1",
                "provenance": "catalog export 2026-1",
                "aliases": {"herramienta": {"Node": "Node.js"}},
            }
        ),
        encoding="utf-8",
    )
    return CatalogSelection(directory, "Generic Software", "2026-1", "test-v1")


def _extractor(documento: object) -> dict[str, object]:
    text = getattr(documento, "contenido_documental")
    catalog_candidates = getattr(documento, "catalog_tool_candidates")

    def package(skill: str, evidence: str, competence: str, tools: list[str]) -> dict[str, object]:
        start = text.index(evidence)
        selected_candidates = [
            candidate
            for tool in tools
            if (
                candidate := next(
                    (
                        candidate
                        for candidate in catalog_candidates
                        if candidate["nombre"] == tool
                    ),
                    None,
                )
            )
            is not None
        ]
        catalog_links = [
            {
                "id_catalogo": candidate["id"],
                "start_pos": candidate["start_pos"],
                "end_pos": candidate["end_pos"],
                "evidencia_uso": candidate["evidencia_literal"],
            }
            for candidate in selected_candidates
        ]
        return {
            "extraction_class": "paquete_respaldado",
            "extraction_text": evidence,
            "char_interval": {"start_pos": start, "end_pos": start + len(evidence)},
            "attributes": {
                "habilidad_propuesta": skill,
                "competencia_propuesta": competence,
                "herramientas": [
                    {
                        "nombre": tool,
                        "tipo_ontologia": "software",
                        "seccion_fuente": "programa_semanal",
                        "cita_fuente": {
                            "texto": evidence,
                            "start_pos": start,
                            "end_pos": start + len(evidence),
                        },
                        "evidencia_uso": tool,
                    }
                    for tool in tools
                    if not any(candidate["nombre"] == tool for candidate in selected_candidates)
                ],
                "herramientas_catalogo": catalog_links,
                "contexto_relacion": evidence,
            },
        }

    return {
        "text": text,
        "extractions": [
            package(
                "Implementar servicios",
                "Semana 1: Implementar servicios con Node.js y Git.",
                "Construcción de software",
                ["Node.js", "Git"],
            ),
            package(
                "Configurar procesos",
                "Semana 2: Configurar procesos con SAP.",
                "Construcción de software",
                ["SAP"],
            ),
            package(
                "Desarrollar una app",
                "Semana 3: Desarrollar una app con Dart.",
                "Construcción de software",
                ["Dart"],
            ),
        ],
    }


def test_selected_catalog_resolves_exact_names_and_keeps_tools_in_their_week(
    tmp_path: Path,
) -> None:
    catalog = _write_catalog(tmp_path / "generic-catalog")
    syllabus = tmp_path / "syllabus.docx"
    _write_docx(
        syllabus,
        [
            "Carrera: Generic Software",
            "Periodo: 2026-1",
            "Semana 1: Implementar servicios con Node.js y Git.",
            "Semana 2: Configurar procesos con SAP.",
            "Semana 3: Desarrollar una app con Dart.",
            "Semana 4: Revisar SAP y Node sin habilidad extraída.",
        ],
    )

    [document] = ejecutar_corpus_langextract([syllabus], _extractor, catalog)["documentos"]

    first, second, third = document["paquetes"]
    assert first["catalogo"]["habilidad"]["id"] == "HAB_NODE"
    assert first["catalogo"]["competencia"]["id"] == "COMP_BUILD"
    assert [tool["id"] for tool in first["catalogo"]["herramientas_vinculadas"]] == [
        "TOOL_NODE",
        "TOOL_GIT",
    ]
    assert [tool["id"] for tool in second["catalogo"]["herramientas_vinculadas"]] == ["TOOL_SAP"]
    assert third["catalogo"]["herramientas_vinculadas"] == []
    assert [tool["id"] for tool in document["herramientas_sin_vinculo"]] == [
        "TOOL_SAP",
        "TOOL_NODE",
    ]


def test_mismatched_catalog_stays_pending_without_canonical_ids(tmp_path: Path) -> None:
    catalog = _write_catalog(tmp_path / "generic-catalog")
    syllabus = tmp_path / "syllabus.docx"
    _write_docx(
        syllabus,
        [
            "Carrera: Another Career",
            "Periodo: 2026-1",
            "Semana 1: Implementar servicios con Node.js y Git.",
            "Semana 2: Configurar procesos con SAP.",
            "Semana 3: Desarrollar una app con Dart.",
        ],
    )

    [document] = ejecutar_corpus_langextract([syllabus], _extractor, catalog)["documentos"]

    assert document["catalogo"]["codigo"] == "CATALOGO_METADATA_NO_COINCIDE"
    assert document["paquetes"][0]["catalogo"]["habilidad"] == {
        "propuesta": "Implementar servicios",
        "estado": "PENDIENTE",
        "codigo": "CATALOGO_METADATA_NO_COINCIDE",
        "id": None,
    }
    assert document["paquetes_crudos"][0]["habilidad_propuesta"] == "Implementar servicios"


def test_catalog_metadata_accepts_carrera_de_and_silabo_period(tmp_path: Path) -> None:
    catalog = _write_catalog(tmp_path / "generic-catalog")
    syllabus = tmp_path / "syllabus.docx"
    _write_docx(
        syllabus,
        [
            "CARRERA DE GENERIC SOFTWARE",
            "SÍLABO 2026-1",
            "Semana 1: Implementar servicios con Node.js y Git.",
            "Semana 2: Configurar procesos con SAP.",
            "Semana 3: Desarrollar una app con Dart.",
        ],
    )

    [document] = ejecutar_corpus_langextract([syllabus], _extractor, catalog)["documentos"]

    assert document["catalogo"]["estado"] == "RESUELTO"


def test_catalog_does_not_link_a_same_week_tool_without_package_evidence(tmp_path: Path) -> None:
    catalog = _write_catalog(tmp_path / "generic-catalog")
    syllabus = tmp_path / "syllabus.docx"
    _write_docx(
        syllabus,
        [
            "Carrera: Generic Software",
            "Periodo: 2026-1",
            "Semana 1: Analizar requisitos. Instalar Git.",
        ],
    )

    def extractor(documento: object) -> dict[str, object]:
        text = getattr(documento, "contenido_documental")
        evidence = "Analizar requisitos"
        start = text.index(evidence)
        return {
            "text": text,
            "extractions": [
                {
                    "extraction_class": "paquete_respaldado",
                    "extraction_text": evidence,
                    "char_interval": {"start_pos": start, "end_pos": start + len(evidence)},
                    "attributes": {"habilidad_propuesta": "Analizar requisitos"},
                }
            ],
        }

    [document] = ejecutar_corpus_langextract([syllabus], extractor, catalog)["documentos"]

    assert document["paquetes"][0]["catalogo"]["herramientas_vinculadas"] == []
    assert [tool["id"] for tool in document["herramientas_sin_vinculo"]] == ["TOOL_GIT"]


def test_catalog_detects_complete_text_tools_and_preserves_timeout_evidence(tmp_path: Path) -> None:
    catalog = _write_catalog(tmp_path / "generic-catalog")
    syllabus = tmp_path / "syllabus.docx"
    _write_docx(
        syllabus,
        [
            "Carrera: Generic Software",
            "Periodo: 2026-1",
            "Semana 1: Analizar requisitos.",
            "Bibliografía: SAP Business One.",
        ],
    )

    def timeout(_: object) -> object:
        raise TimeoutError("request exceeded deadline")

    [document] = ejecutar_corpus_langextract(
        [syllabus],
        timeout,
        tool_catalog_path=catalog.directory / "catalogo_herramientas.csv",
    )["documentos"]

    assert [pending["codigo"] for pending in document["pendientes"]] == ["LLM_REQUEST_TIMEOUT"]
    assert document["herramientas_detectadas"] == [
        {
            "propuesta": "SAP Business One",
            "nombre": "SAP Business One",
            "evidencia_literal": "SAP Business One",
            "start_pos": document["herramientas_detectadas"][0]["start_pos"],
            "end_pos": document["herramientas_detectadas"][0]["end_pos"],
            "estado": "RESUELTO",
            "codigo": None,
            "id": "TOOL_SAP_ONE",
        }
    ]
    tool = document["herramientas_detectadas"][0]
    assert tool["end_pos"] - tool["start_pos"] == len(tool["evidencia_literal"])


def test_tool_catalog_candidates_link_only_supported_package_tools(tmp_path: Path) -> None:
    catalog = _write_catalog(tmp_path / "generic-catalog")
    syllabus = tmp_path / "syllabus.docx"
    _write_docx(
        syllabus,
        [
            "Carrera: Generic Software",
            "Periodo: 2026-1",
            "Semana 1: Implementar servicios.",
            "Bibliografía: Node.js se utiliza para implementar servicios.",
            "Bibliografía: Git para control de versiones.",
        ],
    )
    received_payload: dict[str, str] = {}

    def extractor(documento: object) -> dict[str, object]:
        nonlocal received_payload
        received_payload = construir_payload_langextract(documento)  # type: ignore[arg-type]
        texto = getattr(documento, "contenido_documental")
        evidence = "Implementar servicios"
        start = texto.index(evidence)
        node = next(
            candidate
            for candidate in getattr(documento, "catalog_tool_candidates")
            if candidate["id"] == "TOOL_NODE"
        )
        return {
            "text": texto,
            "extractions": [
                {
                    "extraction_class": "paquete_respaldado",
                    "extraction_text": evidence,
                    "char_interval": {"start_pos": start, "end_pos": start + len(evidence)},
                    "attributes": {
                        "habilidad_propuesta": "Implementar servicios",
                        "competencia_propuesta": "Construcción de software",
                        "contexto_relacion": (
                            "La habilidad Implementar servicios usa Node.js para construir APIs."
                        ),
                        "herramientas_catalogo": [
                            {
                                "id_catalogo": node["id"],
                                "start_pos": node["start_pos"],
                                "end_pos": node["end_pos"],
                                "evidencia_uso": "Node.js",
                            }
                        ],
                    },
                }
            ],
        }

    [document] = ejecutar_corpus_langextract(
        [syllabus],
        extractor,
        tool_catalog_path=catalog.directory / "catalogo_herramientas.csv",
    )["documentos"]

    assert "TOOL_NODE" in received_payload["text_or_documents"]
    assert "TOOL_SAP" not in received_payload["text_or_documents"]
    assert document["pendientes"] == []
    node = next(tool for tool in document["herramientas_detectadas"] if tool["id"] == "TOOL_NODE")
    assert document["paquetes"][0]["herramientas_catalogo"] == [
        {
            "id": "TOOL_NODE",
            "nombre": "Node.js",
            "evidencia_literal": "Node.js",
            "seccion_fuente": "silabo_completo",
            "start_pos": node["start_pos"],
            "end_pos": node["end_pos"],
        }
    ]
    assert [tool["id"] for tool in document["herramientas_sin_vinculo"]] == ["TOOL_GIT"]
    assert document["herramientas_sin_vinculo"][0]["motivo_sin_vinculo"] == (
        "SIN_ASIGNACION_RESPALDADA_A_HABILIDAD"
    )


def test_catalog_prefers_longest_overlapping_tool_name(tmp_path: Path) -> None:
    catalog = _write_catalog(tmp_path / "generic-catalog")
    syllabus = tmp_path / "syllabus.docx"
    _write_docx(
        syllabus,
        [
            "Carrera: Generic Software",
            "Periodo: 2026-1",
            "Bibliografía: SAP Business One y SAP.",
        ],
    )

    def forbidden_provider(_: object) -> object:
        raise AssertionError("tools_only must not call the extractor")

    [document] = ejecutar_corpus_langextract(
        [syllabus],
        forbidden_provider,
        tools_only=True,
        tool_catalog_path=catalog.directory / "catalogo_herramientas.csv",
    )["documentos"]

    assert [tool["nombre"] for tool in document["herramientas_detectadas"]] == [
        "SAP Business One",
        "SAP",
    ]
    assert [tool["id"] for tool in document["herramientas_detectadas"]] == [
        "TOOL_SAP_ONE",
        "TOOL_SAP",
    ]


def test_tool_catalog_keeps_normalized_collisions_and_records_true_ambiguity(
    tmp_path: Path,
) -> None:
    catalog = _write_catalog(tmp_path / "collision-catalog")
    tool_catalog = catalog.directory / "catalogo_herramientas.csv"
    with tool_catalog.open("w", newline="", encoding="utf-8-sig") as stream:
        csv.writer(stream).writerows(
            [
                ["id_herramienta", "nombre_herramienta", "descripcion_breve_herramienta"],
                ["TOOL_CSHARP", "C#", "Language."],
                ["TOOL_CPP", "C++", "Language."],
                ["TOOL_WORD_A", "Tool", "First candidate."],
                ["TOOL_WORD_B", "tool", "Second candidate."],
            ]
        )
    syllabus = tmp_path / "syllabus.docx"
    _write_docx(syllabus, ["Bibliografía: C#; c++; Tool."])

    [document] = ejecutar_corpus_langextract(
        [syllabus],
        None,
        tools_only=True,
        tool_catalog_path=tool_catalog,
    )["documentos"]

    detected = document["herramientas_detectadas"]
    assert [(tool["nombre"], tool["id"]) for tool in detected[:2]] == [
        ("C#", "TOOL_CSHARP"),
        ("C++", "TOOL_CPP"),
    ]
    assert [tool["evidencia_literal"] for tool in detected[:2]] == ["C#", "c++"]
    assert all(
        tool["end_pos"] - tool["start_pos"] == len(tool["evidencia_literal"])
        for tool in detected
    )
    assert detected[2]["estado"] == "PENDIENTE"
    assert detected[2]["codigo"] == "CATALOGO_NOMBRE_AMBIGUO"
    assert detected[2]["candidatos"] == [
        {"id": "TOOL_WORD_A", "nombre": "Tool"},
        {"id": "TOOL_WORD_B", "nombre": "tool"},
    ]

    tool_catalog_instance = preflight_tool_catalog(tool_catalog)
    assert tool_catalog_instance.resolve("herramienta", "c") == (
        None,
        "CATALOGO_NOMBRE_AMBIGUO",
    )


def test_selected_catalog_loads_once_for_multiple_documents(
    tmp_path: Path, monkeypatch: object
) -> None:
    catalog = _write_catalog(tmp_path / "generic-catalog")
    syllabi = [tmp_path / f"syllabus-{number}.docx" for number in (1, 2)]
    for syllabus in syllabi:
        _write_docx(
            syllabus,
            [
                "Carrera: Generic Software",
                "Periodo: 2026-1",
                "Semana 1: Implementar servicios con Node.js y Git.",
                "Semana 2: Configurar procesos con SAP.",
                "Semana 3: Desarrollar una app con Dart.",
            ],
        )
    calls = 0
    original = langextract_catalogo._load_catalog

    def counted(selection: CatalogSelection) -> object:
        nonlocal calls
        calls += 1
        return original(selection)

    monkeypatch.setattr(langextract_catalogo, "_load_catalog", counted)

    ejecutar_corpus_langextract(syllabi, _extractor, catalog)

    assert calls == 1


def test_resolve_only_replays_saved_raw_results_without_an_extractor(tmp_path: Path) -> None:
    catalog = _write_catalog(tmp_path / "generic-catalog")
    syllabus = tmp_path / "syllabus.docx"
    results = tmp_path / "external-results"
    _write_docx(
        syllabus,
        [
            "Carrera: Generic Software",
            "Periodo: 2026-1",
            "Semana 1: Implementar servicios con Node.js y Git.",
            "Semana 2: Configurar procesos con SAP.",
            "Semana 3: Desarrollar una app con Dart.",
        ],
    )

    ejecutar_corpus_langextract([syllabus], _extractor, results_dir=results)
    [document] = resolver_resultados_guardados(results, catalog)["documentos"]

    assert document["paquetes"][0]["catalogo"]["habilidad"]["id"] == "HAB_NODE"


def test_no_catalog_preserves_the_existing_runner_diagnostic(tmp_path: Path) -> None:
    syllabus = tmp_path / "syllabus.docx"
    _write_docx(
        syllabus,
        [
            "Semana 1: Implementar servicios con Node.js y Git.",
            "Semana 2: Configurar procesos con SAP.",
            "Semana 3: Desarrollar una app con Dart.",
        ],
    )

    [document] = ejecutar_corpus_langextract([syllabus], _extractor)["documentos"]

    assert "catalogo" not in document
    assert "herramientas_sin_vinculo" not in document
    assert document["paquetes"][0]["herramientas"] == ["Node.js", "Git"]


def test_reference_catalog_suggests_mechanical_aliases_for_all_chh_types(tmp_path: Path) -> None:
    directory = tmp_path / "reference-catalog"
    directory.mkdir()
    rows = {
        "catalogo_competencias.csv": [
            [
                "id_competencia",
                "nombre_competencia",
                "descripcion_breve_competencia",
                "tipo_competencia",
            ],
            ["COMP_SECURITY", "Análisis de procesos", "Mejora procesos.", "dura"],
        ],
        "catalogo_habilidades.csv": [
            ["id_habilidad", "nombre_habilidad", "descripcion_breve"],
            ["HAB_INCIDENTS", "Gestionar incidencias", "Atender incidencias."],
        ],
        "catalogo_herramientas.csv": [
            ["id_herramienta", "nombre_herramienta", "descripcion_breve_herramienta"],
            ["TOOL_ERP", "SAP S/4HANA", "Sistema ERP."],
        ],
    }
    for filename, contents in rows.items():
        with (directory / filename).open("w", newline="", encoding="utf-8-sig") as stream:
            csv.writer(stream).writerows(contents)

    catalog = preflight_reference_catalog(ReferenceCatalogSelection(directory))
    document = suggest_reference_catalog_document(
        catalog,
        [
            {
                "competencia_propuesta": "analisis-de-procesos",
                "habilidad_propuesta": "gestionar incidencias",
                "herramientas": ["SAPS4HANA"],
            }
        ],
    )

    [package] = document["paquetes"]
    reference = package["referencia"]
    assert document["catalogo_referencia"] == {
        "modo": "reference_only",
        "alcance": str(directory),
    }
    assert reference["competencia"]["candidatos_humanos"][0] == {
        "nombre": "Análisis de procesos",
        "descripcion": "Mejora procesos.",
        "score": 100.0,
        "catalog_source": "catalogo_competencias.csv",
        "catalog_type": "competencia",
    }
    assert reference["habilidad"]["candidatos_humanos"][0]["nombre"] == "Gestionar incidencias"
    assert reference["herramientas"][0]["candidatos_humanos"][0]["nombre"] == "SAP S/4HANA"
    assert all(
        identifier not in str(document)
        for identifier in ("COMP_SECURITY", "HAB_INCIDENTS", "TOOL_ERP")
    )
