from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from agente.normalizador.silabos import analista_tecnico

session_analyst: Any = importlib.import_module("agente.normalizador.silabos.session_analyst")


def _registro(silabo: str = "SIL_1", carrera: str = "Psicología") -> dict[str, object]:
    return {
        "id_curso": f"CUR_{silabo}",
        "id_silabo": silabo,
        "carrera": carrera,
        "periodo": "2026-2",
        "datos": {
            "nombre_curso": "Psicología clínica",
            "logro_general": "Analiza procesos psicológicos en contexto clínico.",
            "logros_especificos": [
                {"descripcion": "Formula hipótesis a partir de entrevistas clínicas."}
            ],
        },
    }


def _respuesta(catalogo_ref: str | None = "COMP_TEC_1") -> dict[str, object]:
    return {
        "competencias": [
            {
                "catalogo_ref": catalogo_ref,
                "nombre_competencia": "Nombre sugerido ignorado al usar catálogo",
                "descripcion_breve_competencia": "Descripción sugerida ignorada al usar catálogo.",
                "logros": ["Formula hipótesis a partir de entrevistas clínicas."],
                "evidencia": [
                    {
                        "fuente": "logro",
                        "fragmento": "Formula hipótesis a partir de entrevistas clínicas.",
                    }
                ],
                "justificacion": "El logro requiere analizar entrevistas clínicas.",
            }
        ]
    }


def _catalogo() -> analista_tecnico.CatalogoTecnico:
    return analista_tecnico.CatalogoTecnico(
        (
            analista_tecnico.CandidatoTecnico(
                "COMP_TEC_1",
                "Psicología",
                "Evaluar información clínica",
                "Integra información clínica para sustentar evaluaciones.",
                2,
            ),
        ),
        "carrera_competencia_oficial.csv+catalogo_competencias_tecnicas.xlsx",
        "a" * 64,
        "Catalogo",
    )


def _hash_registro(registro: dict[str, object]) -> str:
    canonico = json.dumps(
        registro, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(canonico).hexdigest()


def _fila(
    registro: dict[str, object],
    respuesta: dict[str, object],
    catalogo: analista_tecnico.CatalogoTecnico | None = None,
) -> dict[str, object]:
    catalogo = catalogo or _catalogo()
    return {
        "id_silabo": registro["id_silabo"],
        "registro_sha256": _hash_registro(registro),
        "catalogo_sha256": catalogo.sha256,
        **respuesta,
    }


def _escribir_jsonl(ruta: Path, filas: list[dict[str, object]]) -> None:
    ruta.write_text("".join(json.dumps(fila, ensure_ascii=False) + "\n" for fila in filas))


def test_carga_y_materializa_respuestas_por_id_silabo_sin_invocar_modelo(tmp_path: Path) -> None:
    ruta = tmp_path / "respuestas.jsonl"
    registro = _registro()
    _escribir_jsonl(ruta, [_fila(registro, _respuesta())])

    propuestas, auditoria, provenance = session_analyst.analizar_respuestas_sesion(
        [registro], ruta, _catalogo()
    )

    assert len(propuestas) == 1
    assert propuestas[0]["id_silabo"] == "SIL_1"
    assert propuestas[0]["catalogo_ref"] == "COMP_TEC_1"
    assert propuestas[0]["nombre_competencia"] == "Evaluar información clínica"
    assert propuestas[0]["estado_aprobacion"] == "PENDIENTE_APROBACION"
    assert propuestas[0]["origen_propuesta"] == "CATALOGO_CARRERA"
    assert auditoria == []
    assert provenance["catalogo_sha256"] == _catalogo().sha256
    assert len(provenance["respuestas_sha256"]) == 64
    assert provenance["respuesta_origen"] == "respuestas.jsonl"
    assert "/" not in provenance["respuesta_origen"]
    assert provenance["vinculacion"] == "id_silabo+registro_sha256+catalogo_sha256"


def test_rechaza_respuestas_faltantes_desconocidas_y_ids_fuente_duplicados(
    tmp_path: Path,
) -> None:
    ruta = tmp_path / "respuestas.jsonl"
    registro = _registro()
    _escribir_jsonl(ruta, [_fila(registro, _respuesta())])

    with pytest.raises(session_analyst.SessionAnalystInputError, match="faltante"):
        session_analyst.analizar_respuestas_sesion(
            [_registro(), _registro("SIL_2")], ruta, _catalogo()
        )

    _escribir_jsonl(
        ruta,
        [
            _fila(_registro(), _respuesta()),
            _fila({**_registro(), "id_silabo": "UNKNOWN"}, _respuesta()),
        ],
    )
    with pytest.raises(session_analyst.SessionAnalystInputError, match="desconocido"):
        session_analyst.analizar_respuestas_sesion([_registro()], ruta, _catalogo())

    _escribir_jsonl(ruta, [_fila(_registro(), _respuesta())])
    with pytest.raises(session_analyst.SessionAnalystInputError, match="duplicado"):
        session_analyst.analizar_respuestas_sesion([_registro(), _registro()], ruta, _catalogo())

    _escribir_jsonl(
        ruta,
        [
            _fila(_registro(), _respuesta()),
            _fila(_registro(), _respuesta()),
        ],
    )
    with pytest.raises(session_analyst.SessionAnalystInputError, match="duplicado"):
        session_analyst.analizar_respuestas_sesion([_registro()], ruta, _catalogo())


def test_falla_cerrado_para_catalogo_no_oficial_evidencia_invalida_y_linea_malformada(
    tmp_path: Path,
) -> None:
    ruta = tmp_path / "respuestas.jsonl"
    _escribir_jsonl(ruta, [_fila(_registro(), _respuesta("NO_EXISTE"))])
    with pytest.raises(session_analyst.SessionAnalystInputError, match="catálogo"):
        session_analyst.analizar_respuestas_sesion([_registro()], ruta, _catalogo())

    invalida: dict[str, Any] = _respuesta()
    competencia = invalida["competencias"][0]
    competencia["evidencia"] = [{"fuente": "logro", "fragmento": "Texto inventado literal."}]
    _escribir_jsonl(ruta, [_fila(_registro(), invalida)])
    with pytest.raises(session_analyst.SessionAnalystInputError, match="evidencia"):
        session_analyst.analizar_respuestas_sesion([_registro()], ruta, _catalogo())

    ruta.write_text('{"id_silabo":"SIL_1",bad}\n', encoding="utf-8")
    with pytest.raises(session_analyst.SessionAnalystInputError, match="JSONL"):
        session_analyst.analizar_respuestas_sesion([_registro()], ruta, _catalogo())


def test_conserva_cobertura_repetida_entre_silabos_y_no_forja_latency(tmp_path: Path) -> None:
    ruta = tmp_path / "respuestas.jsonl"
    registros = [_registro(), _registro("SIL_2")]
    _escribir_jsonl(
        ruta,
        [_fila(registro, _respuesta()) for registro in registros],
    )

    propuestas, _auditoria, _provenance = session_analyst.analizar_respuestas_sesion(
        registros, ruta, _catalogo()
    )

    assert [propuesta["id_silabo"] for propuesta in propuestas] == ["SIL_1", "SIL_2"]
    assert propuestas[0]["id_propuesta"] != propuestas[1]["id_propuesta"]
    assert all("latencia_modelo_ms" not in propuesta for propuesta in propuestas)


def test_respuesta_de_sesion_rechaza_habilidades_nuevas(tmp_path: Path) -> None:
    ruta = tmp_path / "respuestas.jsonl"
    registro = _registro()
    respuesta = _respuesta()
    competencias = respuesta["competencias"]
    assert isinstance(competencias, list)
    competencias[0]["catalogo_ref"] = None
    _escribir_jsonl(ruta, [_fila(registro, respuesta)])
    with pytest.raises(session_analyst.SessionAnalystInputError, match="no materializable"):
        session_analyst.analizar_respuestas_sesion([registro], ruta, _catalogo())


def test_rechaza_fuente_o_catalogo_obsoletos_aunque_id_y_evidencia_coincidan(
    tmp_path: Path,
) -> None:
    ruta = tmp_path / "respuestas.jsonl"
    registro = _registro()
    fila = _fila(registro, _respuesta())
    registro_modificado = _registro()
    datos = registro_modificado["datos"]
    assert isinstance(datos, dict)
    datos["sumilla"] = "Contenido adicional que conserva el mismo id y logro citado."
    _escribir_jsonl(ruta, [fila])

    with pytest.raises(session_analyst.SessionAnalystInputError, match="registro_sha256"):
        session_analyst.analizar_respuestas_sesion([registro_modificado], ruta, _catalogo())

    fila = _fila(registro, _respuesta())
    fila["catalogo_sha256"] = "b" * 64
    _escribir_jsonl(ruta, [fila])
    with pytest.raises(session_analyst.SessionAnalystInputError, match="catalogo_sha256"):
        session_analyst.analizar_respuestas_sesion([registro], ruta, _catalogo())


def test_modo_sesion_no_se_activa_en_preprocesamiento_deterministico() -> None:
    assert session_analyst.ruta_respuestas_sesion_activa(False, "respuestas.jsonl") is None
    assert session_analyst.ruta_respuestas_sesion_activa(True, "respuestas.jsonl") == (
        "respuestas.jsonl"
    )


def test_rechaza_claves_extra_en_contrato_de_respuesta(tmp_path: Path) -> None:
    ruta = tmp_path / "respuestas.jsonl"
    fila: dict[str, object] = _fila(_registro(), _respuesta())
    fila["latencia_modelo_ms"] = 5
    _escribir_jsonl(ruta, [fila])

    with pytest.raises(session_analyst.SessionAnalystInputError, match="campos"):
        session_analyst.analizar_respuestas_sesion([_registro()], ruta, _catalogo())

    respuesta: dict[str, Any] = _respuesta()
    competencia = respuesta["competencias"][0]
    competencia["latencia_modelo_ms"] = 5
    fila = _fila(_registro(), {"competencias": [competencia]})
    _escribir_jsonl(ruta, [fila])
    with pytest.raises(session_analyst.SessionAnalystInputError, match="campos"):
        session_analyst.analizar_respuestas_sesion([_registro()], ruta, _catalogo())
