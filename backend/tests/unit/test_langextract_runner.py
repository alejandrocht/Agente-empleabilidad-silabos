from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from agente.normalizador.silabos import langextract_runner
from agente.normalizador.silabos.langextract_catalogo import CatalogSelection
from agente.normalizador.silabos.langextract_runner import (
    FragmentoLangExtractCIAR,
    ResultadoFragmentadoLangExtractCIAR,
    ejecutar_corpus_langextract,
)

_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _write_minimal_docx(path: Path, paragraphs: list[str]) -> None:
    body = "".join(f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs)
    document_xml = f'<w:document xmlns:w="{_WORD_NAMESPACE}"><w:body>{body}</w:body></w:document>'
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)


def _write_docx_with_programa_analitico_table(path: Path) -> None:
    document_xml = f'''<w:document xmlns:w="{_WORD_NAMESPACE}"><w:body>
    <w:p><w:r><w:t>Programa analítico</w:t></w:r></w:p>
    <w:tbl>
      <w:tr><w:tc><w:p><w:r><w:t>Semana</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Tema</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Contenido</w:t></w:r></w:p></w:tc></w:tr>
      <w:tr><w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc>
      <w:tc><w:p><w:r><w:t>Análisis de requisitos</w:t></w:r></w:p></w:tc>
      <w:tc><w:p><w:r><w:t>Identificar necesidades de usuarios.</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
    <w:p><w:r><w:t>Bibliografía</w:t></w:r></w:p>
    </w:body></w:document>'''
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)


@pytest.mark.parametrize(
    ("model", "reasoning_effort", "expected_kwargs"),
    [
        (
            "gpt-5.6-luna",
            "high",
            {
                "model_id": "ciar-openai/gpt-5.6-luna",
                "api_key": "test-key",
                "reasoning_effort": "high",
            },
        ),
        (
            None,
            None,
            {"model_id": "ciar-openai/gpt-4o-mini", "api_key": "test-key"},
        ),
    ],
)
def test_runner_defaults_model_and_reasoning_effort_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    model: str | None,
    reasoning_effort: str | None,
    expected_kwargs: dict[str, str],
) -> None:
    calls: list[dict[str, str]] = []

    class FakeProvider:
        def __init__(self, **kwargs: str) -> None:
            calls.append(kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    for name, value in (
        ("CIAR_LANGEXTRACT_MODEL", model),
        ("CIAR_LANGEXTRACT_REASONING_EFFORT", reasoning_effort),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    monkeypatch.setattr(langextract_runner, "OpenAICiarLanguageModel", FakeProvider)
    monkeypatch.setattr(langextract_runner, "ejecutar_corpus_langextract", lambda *_, **__: {})

    assert langextract_runner.main(["--profile", "strict", "syllabus.docx"]) == 0
    assert calls == [{**expected_kwargs, "request_timeout_seconds": 120.0, "max_retries": 0}]


def test_runner_uses_injected_fake_without_network_and_returns_diagnostics(tmp_path: Path) -> None:
    syllabus = tmp_path / "syllabus.docx"
    _write_minimal_docx(syllabus, ["Semana 1: Analiza datos con Python."])

    def fake_extractor(documento: object) -> dict[str, object]:
        texto = getattr(documento, "contenido_documental")
        cita = "Analiza datos"
        inicio = texto.index(cita)
        return {
            "text": texto,
            "extractions": [
                {
                    "extraction_class": "paquete_respaldado",
                    "extraction_text": cita,
                    "char_interval": {"start_pos": inicio, "end_pos": inicio + len(cita)},
                    "attributes": {"habilidad_propuesta": "Analizar datos"},
                }
            ],
        }

    diagnostico = ejecutar_corpus_langextract([syllabus], fake_extractor)

    [documento] = diagnostico["documentos"]
    assert documento["source"]["path"] == str(syllabus)
    assert len(documento["source"]["sha256"]) == 64
    assert documento["errores"] == []
    assert documento["pendientes"] == []
    assert documento["paquetes"][0]["habilidad_propuesta"] == "Analizar datos"


def test_runner_marks_programa_analitico_table_as_weekly_evidence(tmp_path: Path) -> None:
    syllabus = tmp_path / "programa-analitico.docx"
    _write_docx_with_programa_analitico_table(syllabus)
    seen_documents: list[object] = []

    def fake_extractor(documento: object) -> dict[str, object]:
        seen_documents.append(documento)
        return {
            "text": getattr(documento, "contenido_documental"),
            "extractions": [
                {
                    "extraction_class": "pendiente",
                    "extraction_text": "Sin propuesta respaldada.",
                    "attributes": {
                        "codigo": "PENDIENTE_DECLARADO_POR_MODELO",
                        "motivo": "Sin propuesta respaldada.",
                    },
                }
            ],
        }

    diagnostico = ejecutar_corpus_langextract([syllabus], fake_extractor)

    [documento] = diagnostico["documentos"]
    texto_recibido = getattr(seen_documents[0], "contenido_documental")
    assert "[PRIMARY EVIDENCE: PROGRAMA_SEMANAL]" in texto_recibido
    assert "Análisis de requisitos" in texto_recibido
    assert "Identificar necesidades de usuarios." in texto_recibido
    assert documento["structural_metadata"]["weeks"]
    assert documento["structural_metadata"]["has_weekly_program"] is True
    assert [pendiente["codigo"] for pendiente in documento["pendientes"]] == [
        "PENDIENTE_DECLARADO_POR_MODELO"
    ]


def test_runner_exposes_invalid_evidence_and_document_failure_as_pending(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.docx"
    failing = tmp_path / "failing.docx"
    _write_minimal_docx(invalid, ["Semana 1: Analiza datos con Python."])
    _write_minimal_docx(failing, ["Semana 2: Fallo controlado."])

    def fake_extractor(documento: object) -> dict[str, object]:
        texto = getattr(documento, "contenido_documental")
        if "Fallo controlado" in texto:
            raise RuntimeError("respuesta parcial no disponible")
        return {
            "text": texto,
            "extractions": [
                {
                    "extraction_class": "paquete_respaldado",
                    "extraction_text": "Analisis inventado",
                    "char_interval": {"start_pos": 0, "end_pos": 8},
                    "attributes": {"habilidad_propuesta": "Analizar datos"},
                }
            ],
        }

    diagnostico = ejecutar_corpus_langextract([invalid, failing], fake_extractor)

    assert [pendiente["codigo"] for pendiente in diagnostico["documentos"][0]["pendientes"]] == [
        "CITA_PRINCIPAL_NO_LITERAL"
    ]
    assert [pendiente["codigo"] for pendiente in diagnostico["documentos"][1]["pendientes"]] == [
        "EXTRACCION_LANGEXTRACT_FALLIDA"
    ]
    assert diagnostico["documentos"][1]["errores"] == [
        {"tipo": "RuntimeError", "mensaje": "respuesta parcial no disponible"}
    ]
    assert diagnostico["documentos"][0]["resumen"] == {
        "propuestas_generadas": 1,
        "paquetes_aceptados": 0,
        "pendientes_por_motivo": {"CITA_PRINCIPAL_NO_LITERAL": 1},
        "errores": 0,
    }


def test_runner_exposes_each_explicit_chunk_and_rebases_valid_evidence(tmp_path: Path) -> None:
    syllabus = tmp_path / "chunked.docx"
    _write_minimal_docx(syllabus, ["Semana 1: Analiza datos con Python."])

    def fake_extractor(documento: object) -> ResultadoFragmentadoLangExtractCIAR:
        texto = getattr(documento, "contenido_documental")
        inicio = texto.index("Analiza datos")
        fragmento = texto[inicio:]
        return ResultadoFragmentadoLangExtractCIAR(
            fragmentos=(
                FragmentoLangExtractCIAR(
                    inicio=0,
                    fin=inicio,
                    error_tipo="RuntimeError",
                    error_mensaje="fragmento incompleto",
                ),
                FragmentoLangExtractCIAR(
                    inicio=inicio,
                    fin=len(texto),
                    resultado={
                        "text": fragmento,
                        "extractions": [
                            {
                                "extraction_class": "paquete_respaldado",
                                "extraction_text": "Analiza datos",
                                "char_interval": {"start_pos": 0, "end_pos": 13},
                                "attributes": {"habilidad_propuesta": "Analizar datos"},
                            }
                        ],
                    },
                ),
            )
        )

    diagnostico = ejecutar_corpus_langextract([syllabus], fake_extractor)

    [documento] = diagnostico["documentos"]
    assert len(documento["fragmentos"]) == 2
    assert documento["fragmentos"][0]["errores"] == [
        {"tipo": "RuntimeError", "mensaje": "fragmento incompleto"}
    ]
    assert documento["paquetes"][0]["evidencia_principal"]["start_pos"] > 10
    assert [pendiente["codigo"] for pendiente in documento["pendientes"]] == [
        "EXTRACCION_LANGEXTRACT_FALLIDA"
    ]


def test_runner_emits_each_document_before_a_later_timeout(tmp_path: Path) -> None:
    first = tmp_path / "first.docx"
    timed_out = tmp_path / "timed-out.docx"
    third = tmp_path / "third.docx"
    for syllabus, paragraph in (
        (first, "Semana 1: Primer documento."),
        (timed_out, "Semana 2: Documento con timeout."),
        (third, "Semana 3: Ultimo documento."),
    ):
        _write_minimal_docx(syllabus, [paragraph])
    emitted: list[dict[str, object]] = []

    def fake_extractor(documento: object) -> dict[str, object]:
        text = getattr(documento, "contenido_documental")
        if "timeout" in text:
            raise TimeoutError("request exceeded deadline")
        return {"text": text, "extractions": []}

    diagnostico = ejecutar_corpus_langextract(
        [first, timed_out, third], fake_extractor, on_document=emitted.append
    )

    assert [documento["source"]["path"] for documento in emitted] == [
        str(first),
        str(timed_out),
        str(third),
    ]
    assert [pendiente["codigo"] for pendiente in emitted[1]["pendientes"]] == [
        "LLM_REQUEST_TIMEOUT"
    ]
    assert float(emitted[1]["errores"][0]["duracion_segundos"]) >= 0
    assert len(diagnostico["documentos"]) == 3


def test_runner_keeps_raw_packages_when_catalog_metadata_is_invalid(tmp_path: Path) -> None:
    syllabus = tmp_path / "syllabus.docx"
    _write_minimal_docx(syllabus, ["Semana 1: Implementar servicios con Node.js."])

    def fake_extractor(documento: object) -> dict[str, object]:
        text = getattr(documento, "contenido_documental")
        evidence = "Semana 1: Implementar servicios con Node.js."
        start = text.index(evidence)
        return {
            "text": text,
            "extractions": [
                {
                    "extraction_class": "paquete_respaldado",
                    "extraction_text": evidence,
                    "char_interval": {"start_pos": start, "end_pos": start + len(evidence)},
                    "attributes": {
                        "competencia_propuesta": "Construccion de software",
                        "habilidad_propuesta": "Implementar servicios",
                        "herramientas": ["Node.js"],
                    },
                }
            ],
        }

    calls = 0

    def never_extract(documento: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return fake_extractor(documento)

    diagnostico = ejecutar_corpus_langextract(
        [syllabus],
        never_extract,
        CatalogSelection(tmp_path / "catalogo-invalido", "Software", "2026-1", "v1"),
    )

    assert calls == 0
    assert diagnostico == {
        "documentos": [],
        "catalogo_preflight": {
            "estado": "BLOQUEADO",
            "codigo": "CATALOGO_METADATA_INVALIDA",
            "career": "Software",
            "period": "2026-1",
            "version": "v1",
        },
    }


def test_stream_prints_document_records_then_a_summary_without_absolute_paths(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    document = {
        "source": {"path": "/private/source/syllabus.docx", "sha256": "a" * 64},
        "structural_metadata": {},
        "paquetes": [],
        "pendientes": [],
        "errores": [],
        "fragmentos": [],
        "resumen": {
            "propuestas_generadas": 0,
            "paquetes_aceptados": 0,
            "pendientes_por_motivo": {},
            "errores": 0,
        },
    }

    def fake_run(*_: object, on_document: object, **__: object) -> dict[str, object]:
        assert callable(on_document)
        on_document(document)
        return {"documentos": [document]}

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(langextract_runner, "OpenAICiarLanguageModel", lambda **_: object())
    monkeypatch.setattr(langextract_runner, "ejecutar_corpus_langextract", fake_run)

    assert langextract_runner.main(["--stream", "syllabus.docx"]) == 0

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [record["tipo"] for record in records] == ["documento", "resumen"]
    assert records[0]["documento"]["source"]["path"] == "syllabus.docx"
    assert "/private/source" not in json.dumps(records[0])
    assert records[1]["duracion_total_segundos"] >= 0


def test_resume_reprocesses_only_failed_documents(tmp_path: Path) -> None:
    successful = tmp_path / "successful.docx"
    failed = tmp_path / "failed.docx"
    results = tmp_path / "external-results"
    _write_minimal_docx(successful, ["Semana 1: Documento correcto."])
    _write_minimal_docx(failed, ["Semana 2: Documento fallido."])
    calls: list[str] = []

    def extractor(documento: object) -> dict[str, object]:
        text = getattr(documento, "contenido_documental")
        calls.append(text)
        if "fallido" in text and len(calls) == 2:
            raise RuntimeError("fallo recuperable")
        return {"text": text, "extractions": []}

    ejecutar_corpus_langextract([successful, failed], extractor, results_dir=results)
    ejecutar_corpus_langextract([successful, failed], extractor, results_dir=results, resume=True)

    assert len(calls) == 3
    assert "correcto" not in calls[-1]


def test_non_stream_main_keeps_legacy_json_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    diagnostico = {"documentos": []}
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(langextract_runner, "OpenAICiarLanguageModel", lambda **_: object())
    monkeypatch.setattr(
        langextract_runner, "ejecutar_corpus_langextract", lambda *_, **__: diagnostico
    )

    assert langextract_runner.main(["syllabus.docx"]) == 0

    assert capsys.readouterr().out == json.dumps(diagnostico, ensure_ascii=False, indent=2) + "\n"


def test_baseline_profile_forces_legacy_openai_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []

    class FakeProvider:
        def __init__(self, **kwargs: str) -> None:
            calls.append(kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("CIAR_LANGEXTRACT_PROFILE", "baseline")
    monkeypatch.setenv("CIAR_LANGEXTRACT_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("CIAR_LANGEXTRACT_REASONING_EFFORT", "high")
    monkeypatch.setattr(langextract_runner, "OpenAICiarLanguageModel", FakeProvider)
    monkeypatch.setattr(langextract_runner, "ejecutar_corpus_langextract", lambda *_, **__: {})

    assert (
        langextract_runner.main(
            ["--model", "gpt-5.6-luna", "--reasoning-effort", "high", "syllabus.docx"]
        )
        == 0
    )

    assert calls == [
        {
            "model_id": "ciar-openai/gpt-4o-mini",
            "api_key": "test-key",
            "temperature": 0,
            "request_timeout_seconds": 120.0,
            "max_retries": 0,
        }
    ]


def test_baseline_rejects_catalog_before_canonical_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def preflight(_: object) -> object:
        nonlocal called
        called = True
        return object()

    monkeypatch.setattr(langextract_runner, "preflight_catalog", preflight)

    with pytest.raises(SystemExit):
        langextract_runner.main(
            [
                "--profile",
                "baseline",
                "--catalog-dir",
                "catalogo",
                "--career",
                "Software",
                "--period",
                "2026-1",
                "--catalog-version",
                "v1",
                "syllabus.docx",
            ]
        )

    assert not called


def test_baseline_uses_full_syllabus_and_tags_raw_diagnostic(tmp_path: Path) -> None:
    syllabus = tmp_path / "syllabus.docx"
    _write_minimal_docx(
        syllabus,
        [
            "Objetivos",
            "Usar Tableau para analizar indicadores.",
            "Semana 1: Gestionar datos con Software.",
        ],
    )

    evidence: list[str] = []

    def fake_extractor(documento: object) -> dict[str, object]:
        texto = getattr(documento, "contenido_documental")
        evidence.append(texto)
        evidencia = "Gestionar datos"
        inicio = texto.index(evidencia)
        return {
            "text": texto,
            "extractions": [
                {
                    "extraction_class": "paquete_respaldado",
                    "extraction_text": evidencia,
                    "char_interval": {"start_pos": inicio, "end_pos": inicio + len(evidencia)},
                    "attributes": {
                        "competencia_propuesta": "Competencia sin catalogar",
                        "habilidad_propuesta": "Gestion",
                        "herramientas": [{"nombre": "Software"}],
                    },
                }
            ],
        }

    [documento] = ejecutar_corpus_langextract([syllabus], fake_extractor, profile="baseline")[
        "documentos"
    ]

    assert documento["profile"] == "baseline_unverified"
    assert documento["paquetes"][0]["herramientas"] == ["Software"]
    assert evidence == [
        "Objetivos\nUsar Tableau para analizar indicadores.\n"
        "Semana 1: Gestionar datos con Software."
    ]
