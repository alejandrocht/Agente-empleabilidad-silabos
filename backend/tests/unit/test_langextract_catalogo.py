from __future__ import annotations

import csv
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from agente.normalizador.silabos import langextract_catalogo
from agente.normalizador.silabos.langextract_catalogo import CatalogSelection
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

    def package(skill: str, evidence: str, competence: str, tools: list[str]) -> dict[str, object]:
        start = text.index(evidence)
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
                ],
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
    assert third["catalogo"]["herramientas_vinculadas"] == [
        {
            "propuesta": "Dart",
            "evidencia_literal": "Dart",
            "estado": "PENDIENTE",
            "codigo": "HERRAMIENTA_CATALOGO_NO_ENCONTRADA",
            "id": None,
        }
    ]
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
