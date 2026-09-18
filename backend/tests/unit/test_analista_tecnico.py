from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from agente.config.settings import (
    ConfiguracionNormalizadorCurricular,
    configuracion_normalizador_curricular,
)

analista_tecnico: Any = importlib.import_module("agente.normalizador.silabos.analista_tecnico")


def _configuracion() -> ConfiguracionNormalizadorCurricular:
    return configuracion_normalizador_curricular(
        {
            "NORMALIZADOR_CURRICULAR_LLM": "true",
            "NORMALIZADOR_CURRICULAR_LLM_PROVIDER": "ollama",
            "NORMALIZADOR_CURRICULAR_OLLAMA_BASE_URL": "http://localhost:11434/v1",
            "NORMALIZADOR_CURRICULAR_OLLAMA_MODEL": "qwen3.8:27b",
            "NORMALIZADOR_CURRICULAR_OPENAI_MODEL": "gpt-5.6-luna",
            "NORMALIZADOR_CURRICULAR_ANALYST_REASONING_EFFORT": "medium",
            "NORMALIZADOR_CURRICULAR_LLM_TIMEOUT_SECONDS": "120",
            "NORMALIZADOR_CURRICULAR_LLM_MAX_RETRIES": "2",
            "NORMALIZADOR_CURRICULAR_LLM_BATCH_SIZE": "1",
            "NORMALIZADOR_CURRICULAR_LLM_TEMPERATURE": "0",
            "NORMALIZADOR_CURRICULAR_EMBEDDINGS": "false",
            "NORMALIZADOR_CURRICULAR_EMBEDDING_CARRERAS": "",
            "NORMALIZADOR_CURRICULAR_EMBEDDING_MODEL": "text-embedding-3-small",
            "NORMALIZADOR_CURRICULAR_EMBEDDING_MIN_SIMILARITY": "0.2",
            "NORMALIZADOR_CURRICULAR_EMBEDDING_COMPETENCIA_CANDIDATES": "0",
            "NORMALIZADOR_CURRICULAR_EMBEDDING_HABILIDAD_CANDIDATES": "0",
            "NORMALIZADOR_CURRICULAR_EMBEDDING_HERRAMIENTA_CANDIDATES": "0",
            "NORMALIZADOR_CURRICULAR_LEXICAL_COMPETENCIA_CANDIDATES": "0",
            "NORMALIZADOR_CURRICULAR_LEXICAL_HABILIDAD_CANDIDATES": "0",
            "NORMALIZADOR_CURRICULAR_LEXICAL_HERRAMIENTA_CANDIDATES": "0",
            "NORMALIZADOR_CURRICULAR_CONTEXT_EXAMPLE_LIMIT": "0",
        }
    )


def _registro() -> dict[str, object]:
    return {
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "datos": {
            "nombre_curso": "Arquitectura de software",
            "sumilla": "Diseño de sistemas mantenibles.",
            "logro_general": "Diseña arquitecturas de software.",
            "logros_especificos": [{"descripcion": "Compara patrones arquitectónicos."}],
            "programa_analitico_detalle": [
                {
                    "semana": "4",
                    "tema": "Patrones",
                    "contenido": "Patrones de arquitectura y atributos de calidad.",
                }
            ],
            "herramientas_evidencia": [{"texto": "No debe enviarse"}],
        },
    }


def test_contexto_tecnico_conserva_fuentes_internas_sin_herramientas() -> None:
    contexto = analista_tecnico.construir_contexto_tecnico(_registro())

    assert contexto["nombre_curso"] == "Arquitectura de software"
    assert contexto["periodo"] == ""
    assert contexto["logros"] == [
        {"tipo": "general", "orden": "", "texto": "Diseña arquitecturas de software."},
        {"tipo": "especifico", "orden": "1", "texto": "Compara patrones arquitectónicos."},
    ]
    assert "sumilla" not in contexto
    assert "semanas" not in contexto
    assert "herramientas_evidencia" not in contexto


def test_inferencia_estructurada_conserva_evidencia_y_relaciones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas: dict[str, Any] = {}

    class AnalistaFalso:
        def invoke(self, mensajes: object) -> object:
            llamadas["mensajes"] = mensajes
            return {
                "competencias": [
                    {
                        "nombre_competencia": "Diseño técnico de arquitecturas",
                        "descripcion_breve_competencia": (
                            "Selecciona patrones según atributos de calidad."
                        ),
                        "evidencia": [
                            {
                                "fuente": "logro",
                                "fragmento": "Compara patrones arquitectónicos.",
                            }
                        ],
                        "justificacion": "El logro demuestra decisiones arquitectónicas.",
                    }
                ]
            }

    class LLMFalso:
        def with_structured_output(self, schema: object, *, method: str) -> object:
            llamadas["schema"] = schema
            llamadas["method"] = method
            return AnalistaFalso()

    monkeypatch.setattr(analista_tecnico, "obtener_llm", lambda *_args, **_kwargs: LLMFalso())
    trazas: list[Any] = []

    resultado = analista_tecnico.inferir_competencias_tecnicas(
        [_registro()],
        _configuracion(),
        al_actualizar_progreso_silabo=trazas.append,
    )

    assert [traza.estado_analisis for traza in trazas] == ["procesando", "completado"]
    assert trazas[-1].id_silabo == "SIL_1"
    assert trazas[-1].logros_procesados == 2
    assert trazas[-1].latencia_modelo_ms is not None
    assert trazas[-1].latencia_modelo_ms >= 0
    assert resultado[0]["id_curso"] == "CUR_1"
    assert resultado[0]["id_silabo"] == "SIL_1"
    evidencia = resultado[0]["evidencia"]
    assert isinstance(evidencia, list)
    assert isinstance(evidencia[0], dict)
    assert evidencia[0] == {
        "fuente": "logro",
        "fragmento": "Compara patrones arquitectónicos.",
    }
    assert "confianza" not in resultado[0]
    assert "confianza" not in analista_tecnico.CompetenciaTecnicaInferida.model_fields
    assert llamadas["method"] == "json_schema"
    assert "No debe enviarse" not in str(llamadas["mensajes"])


def test_inferencia_registra_advertencia_para_evidencia_literal_invalida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AnalistaFalso:
        def invoke(self, mensajes: object) -> object:
            return {
                "competencias": [
                    {
                        "nombre_competencia": "Diseño técnico de arquitecturas",
                        "descripcion_breve_competencia": (
                            "Selecciona patrones según atributos de calidad."
                        ),
                        "evidencia": [{"fuente": "logro", "fragmento": "Logro que no existe."}],
                        "justificacion": "La evidencia declarada no pertenece al sílabo.",
                    }
                ]
            }

    class LLMFalso:
        def with_structured_output(self, schema: object, *, method: str) -> object:
            return AnalistaFalso()

    monkeypatch.setattr(analista_tecnico, "obtener_llm", lambda *_args, **_kwargs: LLMFalso())
    auditoria: list[dict[str, object]] = []

    assert (
        analista_tecnico.inferir_competencias_tecnicas(
            [_registro()], _configuracion(), auditoria=auditoria
        )
        == []
    )
    assert auditoria == [
        {
            "codigo": "SILABO_SIN_PROPUESTA_TECNICA",
            "id_silabo": "SIL_1",
            "mensaje": (
                "El sílabo no produjo ninguna propuesta técnica con evidencia literal válida."
            ),
        }
    ]


def test_inferencia_conserva_propuestas_validas_de_otros_silabos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respuestas: list[dict[str, object]] = [
        {"competencias": []},
        {
            "competencias": [
                {
                    "nombre_competencia": "Diseño técnico de arquitecturas",
                    "descripcion_breve_competencia": "Selecciona patrones técnicos.",
                    "evidencia": [
                        {"fuente": "logro", "fragmento": "Compara patrones arquitectónicos."}
                    ],
                    "justificacion": "El logro demuestra una decisión técnica.",
                }
            ]
        },
    ]

    class AnalistaFalso:
        def invoke(self, mensajes: object) -> object:
            return respuestas.pop(0)

    class LLMFalso:
        def with_structured_output(self, schema: object, *, method: str) -> object:
            return AnalistaFalso()

    monkeypatch.setattr(analista_tecnico, "obtener_llm", lambda *_args, **_kwargs: LLMFalso())
    segundo = _registro()
    segundo["id_curso"] = "CUR_2"
    segundo["id_silabo"] = "SIL_2"
    auditoria: list[dict[str, object]] = []

    resultado = analista_tecnico.inferir_competencias_tecnicas(
        [_registro(), segundo], _configuracion(), auditoria=auditoria
    )

    assert [fila["id_silabo"] for fila in resultado] == ["SIL_2"]
    assert auditoria[0]["codigo"] == "SILABO_SIN_PROPUESTA_TECNICA"
    assert auditoria[0]["id_silabo"] == "SIL_1"


def test_carga_catalogo_tecnico_normaliza_carrera_y_asigna_referencia(tmp_path: Path) -> None:
    from openpyxl import Workbook

    libro = Workbook()
    hoja = libro.worksheets[0]
    hoja.title = "Catalogo"
    hoja.append(["Carrera", "Habilidad tecnica", "Descripcion"])
    hoja.append(
        [
            "Ingeniería de Sistemas",
            "Diseñar arquitecturas de software",
            "Seleccionar estructuras y patrones técnicos.",
        ]
    )
    hoja.append(["Marketing", "Diseñar campañas", "Planificar campañas medibles."])
    ruta = tmp_path / "catalogo.xlsx"
    libro.save(ruta)

    catalogo = analista_tecnico.cargar_catalogo_tecnico(ruta)

    candidatos = catalogo.para_carrera("Ingeniería de Sistemas")
    assert len(candidatos) == 1
    assert catalogo.para_carrera("INGENIERIA_DE_SISTEMAS") == ()
    assert candidatos[0].nombre == "Diseñar arquitecturas de software"
    assert candidatos[0].referencia.startswith("CATTEC_")
    assert len(candidatos[0].referencia.removeprefix("CATTEC_")) == 16


def test_catalogo_tecnico_del_repositorio_cubre_las_carreras_del_frontend() -> None:
    ruta = Path(__file__).resolve().parents[2] / "catalogos" / "catalogo_competencias_tecnicas.xlsx"

    catalogo = analista_tecnico.cargar_catalogo_tecnico(ruta)

    carreras = {candidato.carrera for candidato in catalogo.candidatos}
    assert len(catalogo.candidatos) == 277
    assert carreras == {
        "Administración",
        "Arquitectura",
        "Comunicación",
        "Contabilidad y Finanzas",
        "Derecho",
        "Economía",
        "Ingeniería Ambiental",
        "Ingeniería Civil",
        "Ingeniería Industrial",
        "Ingeniería Mecatrónica",
        "Ingeniería de Sistemas",
        "Marketing",
        "Negocios Internacionales",
        "Psicología",
    }
    assert len(catalogo.para_carrera("Ingeniería de Sistemas")) == 26
    assert catalogo.para_carrera("SISTEMAS") == ()


def test_carga_catalogo_csv_separa_carreras_y_exige_match_exacto(tmp_path: Path) -> None:
    ruta = tmp_path / "catalogo.csv"
    ruta.write_text(
        "\ufeffid_competencia,nombre_competencia,descripcion_breve_competencia,"
        "tipo_competencia,codigo_competencia,carreras_origen,cantidad_carreras,"
        "cantidad_apariciones_catalogo,cantidad_silabos_relacionados,"
        "cantidad_logros_relacionados,descripciones_alternativas\n"
        "COMP_1,Arquitectura de software,Capacidad para diseñar arquitecturas,"
        "tecnica,,SISTEMAS; INDUSTRIAL,2,1,2,4,\n"
        "COMP_2,Marketing analítico,Capacidad para analizar campañas,"
        "tecnica,,MARKETING,1,1,1,2,\n",
        encoding="utf-8",
    )

    catalogo = analista_tecnico.cargar_catalogo_tecnico(ruta)

    candidatos = catalogo.para_carrera("SISTEMAS")
    assert [candidato.nombre for candidato in candidatos] == ["Arquitectura de software"]
    assert catalogo.para_carrera("INDUSTRIAL")[0].referencia == candidatos[0].referencia
    assert catalogo.para_carrera("INGENIERIA_DE_SISTEMAS") == ()
    assert catalogo.para_carrera("sistemas") == ()
    assert catalogo.hoja == "CSV"


def test_prompt_tecnico_inyecta_solo_catalogo_y_evidencia_curricular() -> None:
    candidato = analista_tecnico.CandidatoTecnico(
        "CATTEC_1234567890abcdef",
        "Ingeniería de Sistemas",
        "Diseñar arquitecturas de software",
        "Seleccionar estructuras y patrones técnicos.",
        2,
    )
    registro = {**_registro(), "carrera": "INGENIERIA_DE_SISTEMAS", "periodo": "2026-2"}
    contexto = analista_tecnico.construir_contexto_tecnico(registro, [candidato])
    mensajes = analista_tecnico.construir_prompt_tecnico(contexto)
    payload = json.loads(mensajes[1][1].split("\n", maxsplit=1)[1])

    assert set(payload) == {"carrera", "nombre_curso", "logros", "catalogo_tecnico"}
    assert payload["catalogo_tecnico"] == [candidato.a_dict()]
    assert payload["logros"][1]["texto"] == "Compara patrones arquitectónicos."
    serializado = json.dumps(payload, ensure_ascii=False)
    assert all(
        clave not in serializado
        for clave in (
            "periodo",
            "sumilla",
            "semanas",
            "numero_semana",
            "id_curso",
            "id_silabo",
            "competencias_declaradas",
            "herramientas_evidencia",
        )
    )


def test_system_prompt_tecnico_is_english_and_preserves_literal_candidate_rules() -> None:
    contexto = analista_tecnico.construir_contexto_tecnico(_registro())
    mensajes = analista_tecnico.construir_prompt_tecnico(contexto)
    system_message = mensajes[0][1]

    assert system_message.startswith("You are a senior curricular analyst.")
    assert "specific learning outcome copied literally" in system_message
    assert "literal evidence from a learning outcome" in system_message
    assert "Do not summarize or paraphrase learning outcomes." in system_message
    assert "The career catalog contains candidates, not facts" in system_message
    assert "choose a candidate only if the syllabus learning outcomes support it" in system_message
    assert "catalogo_ref=null" in system_message
    assert "pending human approval" in system_message


def test_inferencia_catalogada_crea_propuesta_pendiente_y_copia_fuente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidato = analista_tecnico.CandidatoTecnico(
        "CATTEC_1234567890abcdef",
        "Ingeniería de Sistemas",
        "Diseñar arquitecturas de software",
        "Seleccionar estructuras y patrones técnicos.",
        2,
    )
    catalogo = analista_tecnico.CatalogoTecnico((candidato,), "catalogo.xlsx", "a" * 64, "Catalogo")
    llamadas: dict[str, object] = {}

    class AnalistaFalso:
        def invoke(self, mensajes: object) -> object:
            llamadas["mensajes"] = mensajes
            return {
                "competencias": [
                    {
                        "catalogo_ref": candidato.referencia,
                        "nombre_competencia": "Nombre inventado",
                        "descripcion_breve_competencia": "Descripción inventada suficiente.",
                        "logros": ["Compara patrones arquitectónicos."],
                        "evidencia": [
                            {
                                "fuente": "logro",
                                "fragmento": "Compara patrones arquitectónicos.",
                            }
                        ],
                        "justificacion": "El logro exige decisiones arquitectónicas.",
                    }
                ]
            }

    class LLMFalso:
        def with_structured_output(self, schema: object, *, method: str) -> object:
            assert method == "json_schema"
            return AnalistaFalso()

    monkeypatch.setattr(analista_tecnico, "obtener_llm", lambda *_args, **_kwargs: LLMFalso())
    registro = {**_registro(), "carrera": "Ingeniería de Sistemas", "periodo": "2026-2"}

    resultado = analista_tecnico.inferir_competencias_tecnicas(
        [registro], _configuracion(), catalogo
    )

    assert len(resultado) == 1
    propuesta = resultado[0]
    assert propuesta["nombre_competencia"] == candidato.nombre
    assert propuesta["descripcion_breve_competencia"] == candidato.descripcion
    assert propuesta["origen_propuesta"] == "CATALOGO_CARRERA"
    assert propuesta["estado_aprobacion"] == "PENDIENTE_APROBACION"
    assert propuesta["logros"] == ["Compara patrones arquitectónicos."]
    assert propuesta["evidencia"] == [
        {"fuente": "logro", "fragmento": "Compara patrones arquitectónicos."}
    ]
    assert "confianza" not in propuesta
    assert "id_competencia" not in propuesta
    assert "id_cob_curricular" not in propuesta
    assert str(propuesta["id_propuesta"]).startswith("PROP_TEC_")


def test_escribe_propuestas_tecnicas_como_jsonl_pendiente(tmp_path: Path) -> None:
    ruta = tmp_path / "reportes" / "propuestas_tecnicas.jsonl"

    analista_tecnico.escribir_propuestas_tecnicas(
        ruta,
        [
            {
                "id_propuesta": "PROP_TEC_1234567890abcdef",
                "estado_aprobacion": "PENDIENTE_APROBACION",
            }
        ],
    )

    assert json.loads(ruta.read_text(encoding="utf-8")) == {
        "id_propuesta": "PROP_TEC_1234567890abcdef",
        "estado_aprobacion": "PENDIENTE_APROBACION",
    }
