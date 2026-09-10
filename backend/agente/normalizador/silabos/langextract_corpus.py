"""Build read-only, human-annotation-ready corpus cases from explicit DOCX paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ElementTree
from collections.abc import Sequence
from pathlib import Path
from zipfile import BadZipFile, ZipFile

_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_PARAGRAPH_TAG = f"{{{_WORD_NAMESPACE}}}p"
_TEXT_TAG = f"{{{_WORD_NAMESPACE}}}t"
_BODY_TAG = f"{{{_WORD_NAMESPACE}}}body"
_TABLE_TAG = f"{{{_WORD_NAMESPACE}}}tbl"
_ROW_TAG = f"{{{_WORD_NAMESPACE}}}tr"
_CELL_TAG = f"{{{_WORD_NAMESPACE}}}tc"
_WEEK_PATTERN = re.compile(
    r"\bsemana\s*(?:n(?:u|\u00fa)mero\s*)?(?P<number>\d{1,2})\b",
    re.IGNORECASE,
)
_TABLE_NUMBERING_PATTERN = re.compile(r"(?:tabla|cuadro)\s*\d+\b", re.IGNORECASE)
_SECTION_HEADINGS = {
    "programa_semanal": (
        "programa semanal",
        "programa analitico",
        "cronograma",
        "contenidos por semana",
    ),
    "sumilla": ("sumilla",),
    "competencias_declaradas": ("competencias",),
    "resultados_aprendizaje": ("resultados de aprendizaje", "logros de aprendizaje"),
    "bibliografia": ("bibliografia", "referencias"),
    "metodologia": ("metodologia", "estrategias metodologicas"),
    "administracion": ("datos generales", "informacion general", "creditos", "docente"),
}
_PRIMARY_SECTION = "programa_semanal"
_COMPLEMENTARY_SECTIONS = (
    "sumilla",
    "competencias_declaradas",
    "resultados_aprendizaje",
)
_EXCLUDED_SECTIONS = ("bibliografia", "metodologia", "administracion")


class CorpusInputError(ValueError):
    """Raised when an input is not an explicit, readable DOCX file."""


def build_corpus_cases(docx_paths: Sequence[str | Path]) -> list[dict[str, object]]:
    """Create one reproducible, annotation-ready case per explicitly supplied DOCX path."""
    if not docx_paths:
        raise CorpusInputError("At least one explicit DOCX path is required.")

    return [_build_corpus_case(_validate_docx_path(path)) for path in docx_paths]


def _validate_docx_path(docx_path: str | Path) -> Path:
    path = Path(docx_path)
    if not path.is_file():
        raise CorpusInputError(f"DOCX path does not exist or is not a file: {path}")
    if path.suffix.lower() != ".docx":
        raise CorpusInputError(f"Expected a DOCX file: {path}")
    return path


def _build_corpus_case(path: Path) -> dict[str, object]:
    paragraphs, tables = _extract_docx_content(path)
    source_text = "\n".join((*paragraphs, *(cell for row in tables for cell in row)))
    secciones = _clasificar_secciones(paragraphs, tables)
    weeks = _detect_weeks(paragraphs) + _detect_table_weeks(tables)
    primary_weekly_evidence = secciones["evidencia_primaria"].get(_PRIMARY_SECTION, "")
    return {
        "source": {"path": str(path), "sha256": _sha256(path)},
        "source_text": source_text,
        "secciones_razonamiento": secciones,
        "texto_razonado": _texto_razonado(secciones),
        "structural_metadata": {
            "has_weekly_program": bool(weeks and primary_weekly_evidence),
            "weeks": weeks,
        },
        "evaluation_matrix": {
            "expected_literal_evidence": [],
            "expected_packages": [],
            "exclusions": [],
            "expected_pending": [],
        },
    }


def _clasificar_secciones(
    paragraphs: Sequence[str], tables: Sequence[Sequence[str]]
) -> dict[str, dict[str, str]]:
    agrupadas: dict[str, list[str]] = {clave: [] for clave in _SECTION_HEADINGS}
    seccion_actual: str | None = None
    for paragraph in paragraphs:
        encabezado = _encabezado_seccion(paragraph)
        if encabezado is not None:
            seccion_actual = encabezado
        elif _WEEK_PATTERN.search(paragraph):
            seccion_actual = _PRIMARY_SECTION
        if seccion_actual is not None and not _es_numeracion_tabla(paragraph):
            agrupadas[seccion_actual].append(paragraph)

    if agrupadas[_PRIMARY_SECTION]:
        for row in tables:
            if len(row) >= 3 and row[0].strip().isdigit():
                agrupadas[_PRIMARY_SECTION].append("\n".join(cell for cell in row[1:] if cell))

    return {
        "evidencia_primaria": _secciones_texto(agrupadas, (_PRIMARY_SECTION,)),
        "contexto_complementario": _secciones_texto(agrupadas, _COMPLEMENTARY_SECTIONS),
        "evidencia_excluida": _secciones_texto(agrupadas, _EXCLUDED_SECTIONS),
    }


def _encabezado_seccion(paragraph: str) -> str | None:
    normalizado = _normalizar_encabezado(paragraph)
    for seccion, encabezados in _SECTION_HEADINGS.items():
        if normalizado in encabezados:
            return seccion
    return None


def _normalizar_encabezado(texto: str) -> str:
    return " ".join(
        texto.casefold().translate(str.maketrans("áéíóú", "aeiou")).strip(" .:-").split()
    )


def _es_numeracion_tabla(paragraph: str) -> bool:
    texto = paragraph.strip()
    return bool(re.fullmatch(r"\d+(?:\.\d+)*", texto) or _TABLE_NUMBERING_PATTERN.fullmatch(texto))


def _secciones_texto(agrupadas: dict[str, list[str]], secciones: Sequence[str]) -> dict[str, str]:
    return {seccion: "\n".join(agrupadas[seccion]) for seccion in secciones if agrupadas[seccion]}


def _texto_razonado(secciones: dict[str, dict[str, str]]) -> str:
    bloques: list[str] = []
    for seccion, texto in secciones["evidencia_primaria"].items():
        bloques.append(f"[PRIMARY EVIDENCE: {seccion.upper()}]\n{texto}")
    for seccion, texto in secciones["contexto_complementario"].items():
        bloques.append(f"[COMPLEMENTARY CONTEXT: {seccion.upper()}]\n{texto}")
    return "\n\n".join(bloques)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_docx_content(path: Path) -> tuple[list[str], list[list[str]]]:
    try:
        with ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml")
    except (BadZipFile, KeyError) as error:
        raise CorpusInputError(f"Invalid DOCX document: {path}") from error

    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError as error:
        raise CorpusInputError(f"Invalid DOCX XML document: {path}") from error

    body = root.find(_BODY_TAG)
    if body is None:
        raise CorpusInputError(f"Invalid DOCX XML document: {path}")
    paragraphs: list[str] = []
    tables: list[list[str]] = []
    for child in body:
        if child.tag == _PARAGRAPH_TAG:
            text = _paragraph_text(child)
            if text:
                paragraphs.append(text)
        elif child.tag == _TABLE_TAG:
            for row in child.iter(_ROW_TAG):
                cells = [
                    "\n".join(
                        filter(None, (_paragraph_text(item) for item in cell.iter(_PARAGRAPH_TAG)))
                    )
                    for cell in row.iter(_CELL_TAG)
                ]
                if any(cells):
                    tables.append(cells)
    return paragraphs, tables


def _paragraph_text(paragraph: ElementTree.Element[str]) -> str:
    return "".join(text_node.text or "" for text_node in paragraph.iter(_TEXT_TAG)).strip()


def _detect_weeks(paragraphs: Sequence[str]) -> list[dict[str, object]]:
    weeks: list[dict[str, object]] = []
    for paragraph in paragraphs:
        for match in _WEEK_PATTERN.finditer(paragraph):
            weeks.append(
                {
                    "number": int(match["number"]),
                    "literal_evidence": paragraph,
                }
            )
    return weeks


def _detect_table_weeks(tables: Sequence[Sequence[str]]) -> list[dict[str, object]]:
    return [
        {"number": int(row[0]), "literal_evidence": "\n".join(cell for cell in row[1:] if cell)}
        for row in tables
        if len(row) >= 3 and row[0].strip().isdigit()
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create annotation-ready corpus cases from explicit DOCX paths."
    )
    parser.add_argument("docx_paths", nargs="+", metavar="DOCX")
    arguments = parser.parse_args(argv)
    print(json.dumps(build_corpus_cases(arguments.docx_paths), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
