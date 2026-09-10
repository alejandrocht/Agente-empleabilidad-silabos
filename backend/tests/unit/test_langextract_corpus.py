from __future__ import annotations

import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from agente.normalizador.silabos.langextract_corpus import (
    CorpusInputError,
    build_corpus_cases,
)

_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _write_minimal_docx(path: Path, paragraphs: list[str]) -> None:
    body = "".join(f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs)
    document_xml = f'<w:document xmlns:w="{_WORD_NAMESPACE}"><w:body>{body}</w:body></w:document>'
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)


def _write_docx_with_weekly_table(path: Path) -> None:
    document_xml = f'''<w:document xmlns:w="{_WORD_NAMESPACE}"><w:body>
    <w:p><w:r><w:t>Programa analítico</w:t></w:r></w:p>
    <w:tbl>
      <w:tr><w:tc><w:p><w:r><w:t>Semana</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Tema</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Contenido</w:t></w:r></w:p></w:tc></w:tr>
      <w:tr><w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc>
      <w:tc><w:p><w:r><w:t>Análisis de requisitos</w:t></w:r></w:p></w:tc>
      <w:tc><w:p><w:r><w:t>Identificar necesidades de usuarios.</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
    </w:body></w:document>'''
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)


def test_build_corpus_cases_preserves_source_and_prepares_empty_annotation_matrix(
    tmp_path: Path,
) -> None:
    syllabus = tmp_path / "syllabus.docx"
    _write_minimal_docx(
        syllabus,
        ["Programa semanal", "Semana 1: Fundamentos", "Semana 2: Aplicacion"],
    )

    [case] = build_corpus_cases([syllabus])

    assert case["source_text"] == "Programa semanal\nSemana 1: Fundamentos\nSemana 2: Aplicacion"
    assert case["source"] == {
        "path": str(syllabus),
        "sha256": hashlib.sha256(syllabus.read_bytes()).hexdigest(),
    }
    assert case["structural_metadata"] == {
        "has_weekly_program": True,
        "weeks": [
            {"number": 1, "literal_evidence": "Semana 1: Fundamentos"},
            {"number": 2, "literal_evidence": "Semana 2: Aplicacion"},
        ],
    }
    assert case["evaluation_matrix"] == {
        "expected_literal_evidence": [],
        "expected_packages": [],
        "exclusions": [],
        "expected_pending": [],
    }


def test_build_corpus_cases_tags_weekly_evidence_and_excludes_non_teaching_sections(
    tmp_path: Path,
) -> None:
    syllabus = tmp_path / "sectioned.docx"
    _write_minimal_docx(
        syllabus,
        [
            "Sumilla",
            "Curso de desarrollo de aplicaciones.",
            "Competencias",
            "Desarrolla soluciones de software.",
            "Resultados de aprendizaje",
            "Implementa servicios web.",
            "Programa semanal",
            "Tabla 1",
            "Semana 1: Taller: Desarrolla APIs web con Node.js y Express.",
            "Bibliografia",
            "Node.js Design Patterns.",
            "Metodologia",
            "Discusion en clase.",
        ],
    )

    [case] = build_corpus_cases([syllabus])

    assert case["secciones_razonamiento"] == {
        "evidencia_primaria": {
            "programa_semanal": (
                "Programa semanal\nSemana 1: Taller: Desarrolla APIs web con Node.js y Express."
            )
        },
        "contexto_complementario": {
            "sumilla": "Sumilla\nCurso de desarrollo de aplicaciones.",
            "competencias_declaradas": "Competencias\nDesarrolla soluciones de software.",
            "resultados_aprendizaje": "Resultados de aprendizaje\nImplementa servicios web.",
        },
        "evidencia_excluida": {
            "bibliografia": "Bibliografia\nNode.js Design Patterns.",
            "metodologia": "Metodologia\nDiscusion en clase.",
        },
    }
    assert "Node.js Design Patterns" not in case["texto_razonado"]
    assert "Discusion en clase" not in case["texto_razonado"]
    assert "Node.js y Express" in case["texto_razonado"]


def test_build_corpus_cases_reconstructs_programa_analitico_table_rows(tmp_path: Path) -> None:
    syllabus = tmp_path / "programa-analitico.docx"
    _write_docx_with_weekly_table(syllabus)

    [case] = build_corpus_cases([syllabus])

    primary = case["secciones_razonamiento"]["evidencia_primaria"]["programa_semanal"]
    assert (
        primary
        == "Programa analítico\nAnálisis de requisitos\nIdentificar necesidades de usuarios."
    )
    assert "Semana 1" not in case["texto_razonado"]
    assert case["structural_metadata"]["weeks"] == [
        {
            "number": 1,
            "literal_evidence": "Análisis de requisitos\nIdentificar necesidades de usuarios.",
        }
    ]


@pytest.mark.parametrize("path", [Path("missing.docx"), Path("not-a-docx.txt")])
def test_build_corpus_cases_rejects_missing_or_non_docx_inputs(path: Path, tmp_path: Path) -> None:
    candidate = path if path.name == "missing.docx" else tmp_path / path.name
    if candidate.suffix == ".txt":
        candidate.write_text("not a docx")

    with pytest.raises(CorpusInputError):
        build_corpus_cases([candidate])


def test_build_corpus_cases_requires_explicit_paths() -> None:
    with pytest.raises(CorpusInputError, match="explicit DOCX path"):
        build_corpus_cases([])
