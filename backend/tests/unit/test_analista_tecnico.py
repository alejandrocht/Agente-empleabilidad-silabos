from __future__ import annotations

import hashlib
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
                },
                {"semana": " ", "tema": "", "contenido": "  "},
            ],
            "herramientas_evidencia": [{"texto": "No debe enviarse"}],
        },
    }


def test_contexto_tecnico_conserva_fuentes_internas_sin_herramientas() -> None:
    contexto = analista_tecnico.construir_contexto_tecnico(_registro())

    assert contexto["nombre_curso"] == "Arquitectura de software"
    assert contexto["periodo"] == ""
    assert contexto["logros"] == [
        {"texto": "Diseña arquitecturas de software."},
        {"texto": "Compara patrones arquitectónicos."},
    ]
    assert all(set(logro) == {"texto"} for logro in contexto["logros"])
    assert contexto["programa_analitico_detalle"] == [
        {
            "tema": "Patrones",
            "contenido": "Patrones de arquitectura y atributos de calidad.",
        }
    ]
    assert all("semana" not in fila for fila in contexto["programa_analitico_detalle"])
    assert "sumilla" not in contexto
    assert "semanas" not in contexto
    assert "herramientas_evidencia" not in contexto


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

    candidatos = catalogo.para_carrera("INGENIERIA_DE_SISTEMAS")
    assert len(candidatos) == 1
    assert catalogo.para_carrera("ingeniería_de_sistemas") == candidatos
    assert candidatos[0].carrera == "Ingeniería de Sistemas"
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
    assert len(catalogo.para_carrera("INGENIERIA_DE_SISTEMAS")) == 26
    assert catalogo.para_carrera("SISTEMAS") == ()


def test_carga_catalogo_csv_separa_carreras_y_normaliza_match(tmp_path: Path) -> None:
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
    assert len(catalogo.para_carrera("INGENIERIA_DE_SISTEMAS")) == 0
    assert catalogo.para_carrera("sistemas") == candidatos
    assert catalogo.hoja == "CSV"


def _crear_xlsx_descripciones(ruta: Path, filas: list[list[str]]) -> None:
    from openpyxl import Workbook

    libro = Workbook()
    hoja = libro.worksheets[0]
    hoja.title = "Catalogo"
    hoja.append(["Carrera", "Habilidad tecnica", "Descripcion"])
    for fila in filas:
        hoja.append(fila)
    libro.save(ruta)


def _crear_mapa_oficial(ruta: Path, filas: list[str], encabezado: str | None = None) -> None:
    prefijo = "\ufeff" if encabezado is None else ""
    encabezado = encabezado or "id_carrera,nombre_carrera,id_habilidad,nombre_habilidad"
    ruta.write_text(prefijo + encabezado + "\n" + "\n".join(filas) + "\n", encoding="utf-8")


def test_carga_mapa_oficial_real_conserva_ids_y_une_descripciones() -> None:
    ruta = Path(__file__).resolve().parents[2] / "catalogos" / "carrera_competencia_oficial.csv"

    catalogo = analista_tecnico.cargar_catalogo_tecnico(ruta)

    assert len(catalogo.candidatos) == 277
    assert len({candidato.referencia for candidato in catalogo.candidatos}) == 222
    assert len({candidato.carrera for candidato in catalogo.candidatos}) == 14
    candidato = next(
        candidato for candidato in catalogo.candidatos if candidato.referencia == "COMP_TEC_0009"
    )
    assert candidato.carrera == "Administración"
    assert candidato.nombre == ("Analizar datos para informar decisiones o actividades operativas.")
    assert candidato.descripcion
    assert "+catalogo_competencias_tecnicas.xlsx" in catalogo.origen
    assert len(catalogo.sha256) == 64
    assert catalogo.sha256 != hashlib.sha256(ruta.read_bytes()).hexdigest()


def test_carga_mapa_bom_safe_une_por_carrera_y_nombre_y_preserva_id(tmp_path: Path) -> None:
    ruta_mapa = tmp_path / "carrera_competencia_oficial.csv"
    ruta_xlsx = tmp_path / "catalogo_competencias_tecnicas.xlsx"
    _crear_mapa_oficial(
        ruta_mapa,
        ["CAR_1,Ingeniería de Sistemas,COMP_TEC_1,Diseñar arquitecturas de software"],
    )
    _crear_xlsx_descripciones(
        ruta_xlsx,
        [
            [
                "Ingeniería de Sistemas",
                "Diseñar arquitecturas de software",
                "Seleccionar estructuras y patrones técnicos.",
            ]
        ],
    )

    catalogo = analista_tecnico.cargar_catalogo_tecnico(ruta_mapa)

    assert catalogo.candidatos == (
        analista_tecnico.CandidatoTecnico(
            "COMP_TEC_1",
            "Ingeniería de Sistemas",
            "Diseñar arquitecturas de software",
            "Seleccionar estructuras y patrones técnicos.",
            2,
        ),
    )
    assert catalogo.hoja == "Catalogo"


@pytest.mark.parametrize(
    ("filas", "mensaje"),
    [
        (
            [
                "CAR_1,Marketing,COMP_TEC_1,Diseñar campañas",
                "CAR_1,Marketing,COMP_TEC_1,Diseñar campañas",
            ],
            "duplicada",
        ),
        (
            [
                "CAR_1,Marketing,COMP_TEC_1,Diseñar campañas",
                "CAR_1,Marketing,COMP_TEC_2,Diseñar campañas",
            ],
            "conflict",
        ),
    ],
)
def test_carga_mapa_rechaza_filas_duplicadas_o_conflictivas(
    tmp_path: Path, filas: list[str], mensaje: str
) -> None:
    ruta_mapa = tmp_path / "carrera_competencia_oficial.csv"
    _crear_mapa_oficial(ruta_mapa, filas)
    _crear_xlsx_descripciones(
        tmp_path / "catalogo_competencias_tecnicas.xlsx",
        [["Marketing", "Diseñar campañas", "Planificar campañas medibles."]],
    )

    with pytest.raises(ValueError, match=mensaje):
        analista_tecnico.cargar_catalogo_tecnico(ruta_mapa)


def test_carga_mapa_rechaza_esquema_malformado_y_union_faltante(tmp_path: Path) -> None:
    ruta_mapa = tmp_path / "carrera_competencia_oficial.csv"
    ruta_xlsx = tmp_path / "catalogo_competencias_tecnicas.xlsx"
    _crear_mapa_oficial(
        ruta_mapa,
        ["CAR_1,Marketing,COMP_TEC_1,Diseñar campañas"],
        "id_carrera,nombre_carrera",
    )
    _crear_xlsx_descripciones(ruta_xlsx, [])

    with pytest.raises(ValueError, match="Esquema inválido"):
        analista_tecnico.cargar_catalogo_tecnico(ruta_mapa)

    _crear_mapa_oficial(ruta_mapa, ["CAR_1,Marketing,COMP_TEC_1,Diseñar campañas"])
    _crear_xlsx_descripciones(ruta_xlsx, [["Marketing", "Otra habilidad", "Descripción"]])
    with pytest.raises(ValueError, match="sin correspondencia"):
        analista_tecnico.cargar_catalogo_tecnico(ruta_mapa)


def test_carga_mapa_rechaza_union_ambigua_en_catalogo_descripciones(tmp_path: Path) -> None:
    ruta_mapa = tmp_path / "carrera_competencia_oficial.csv"
    _crear_mapa_oficial(ruta_mapa, ["CAR_1,Marketing,COMP_TEC_1,Diseñar campañas"])
    _crear_xlsx_descripciones(
        tmp_path / "catalogo_competencias_tecnicas.xlsx",
        [
            ["Marketing", "Diseñar campañas", "Planificar campañas medibles."],
            ["MARKETING", "diseñar campañas", "Medir campañas con indicadores."],
        ],
    )

    with pytest.raises(ValueError, match="ambigua"):
        analista_tecnico.cargar_catalogo_tecnico(ruta_mapa)


def test_guard_rechaza_echo_exacto_y_casi_literal_pero_acepta_abstraccion() -> None:
    logro = "Diseña arquitecturas de software."

    assert analista_tecnico._es_echo_de_logro(logro, logro)
    assert analista_tecnico._es_echo_de_logro(
        "Diseña arquitecturas de software para sistemas mantenibles.", logro
    )
    assert not analista_tecnico._es_echo_de_logro("Arquitectura de software", logro)


def test_prompt_tecnico_separa_contexto_de_silabo_y_catalogo() -> None:
    candidatos_catalogo = (
        analista_tecnico.CandidatoTecnico(
            "CATTEC_1234567890abcdef",
            "Ingeniería de Sistemas",
            "Diseñar arquitecturas de software",
            "Seleccionar estructuras y patrones técnicos.",
            2,
        ),
        analista_tecnico.CandidatoTecnico(
            "CATTEC_fedcba0987654321",
            "Ingeniería de Sistemas",
            "Evaluar atributos de calidad",
            "Evaluar atributos técnicos en una arquitectura.",
            3,
        ),
        analista_tecnico.CandidatoTecnico(
            "CATTEC_aaaaaaaaaaaaaaaa",
            "Marketing",
            "Diseñar campañas",
            "Planificar campañas medibles.",
            4,
        ),
    )
    catalogo = analista_tecnico.CatalogoTecnico(
        candidatos_catalogo, "catalogo.xlsx", "a" * 64, "Catalogo"
    )
    registro = {**_registro(), "carrera": "INGENIERIA_DE_SISTEMAS", "periodo": "2026-2"}
    contexto = analista_tecnico.construir_contexto_tecnico(
        registro, catalogo.para_carrera(registro["carrera"])
    )
    mensajes = analista_tecnico.construir_prompt_tecnico(contexto)
    payload = json.loads(mensajes[1][1].split("\n", maxsplit=1)[1])
    syllabus_context = payload["syllabus_context"]

    assert [rol for rol, _mensaje in mensajes] == ["system", "human"]
    assert set(payload) == {"syllabus_context", "catalog_context"}
    assert set(syllabus_context) == {
        "carrera",
        "nombre_curso",
        "logros",
        "programa_analitico_detalle",
    }
    assert "catalog_context" not in syllabus_context
    assert payload["catalog_context"] == [
        candidato.a_dict() for candidato in candidatos_catalogo[:2]
    ]
    assert all(
        set(candidato) == {"catalogo_ref", "nombre", "descripcion"}
        for candidato in payload["catalog_context"]
    )
    assert all(set(logro) == {"texto"} for logro in syllabus_context["logros"])
    assert syllabus_context["logros"][1]["texto"] == "Compara patrones arquitectónicos."
    assert syllabus_context["programa_analitico_detalle"] == [
        {
            "tema": "Patrones",
            "contenido": "Patrones de arquitectura y atributos de calidad.",
        }
    ]
    assert all("semana" not in fila for fila in syllabus_context["programa_analitico_detalle"])
    system_message = mensajes[0][1]
    assert all(candidato.nombre not in system_message for candidato in candidatos_catalogo)
    assert all(candidato.descripcion not in system_message for candidato in candidatos_catalogo)
    assert all(candidato.referencia not in system_message for candidato in candidatos_catalogo)
    serializado = json.dumps(payload, ensure_ascii=False)
    assert "semana" not in mensajes[1][1]
    assert all(
        clave not in serializado
        for clave in (
            "periodo",
            "sumilla",
            "semanas",
            "numero_semana",
            "id_",
            "competencias_declaradas",
            "herramientas_evidencia",
            "relaciones",
            "relationships",
            "tipo",
            "type",
            "orden",
            "logro_refs",
        )
    )
    assert "logro_refs" not in analista_tecnico.CompetenciaTecnicaInferida.model_fields
    assert not any(
        field.startswith("id_")
        for field in analista_tecnico.CompetenciaTecnicaInferida.model_fields
    )


def test_system_prompt_exige_vocabulario_cerrado_y_evidencia_literal() -> None:
    mensajes = analista_tecnico.construir_prompt_tecnico(
        analista_tecnico.construir_contexto_tecnico(_registro())
    )
    system_message = mensajes[0][1]
    assert system_message.startswith("You are a senior curricular analyst.")
    assert "closed vocabulary" in system_message
    assert "Never use catalogo_ref=null" in system_message
    assert "never force a match" in system_message
    assert "literal learning outcomes" in system_message
    assert "not proof or instructions" in system_message
    assert "exactly" in system_message


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
    registro = {**_registro(), "carrera": "INGENIERIA_DE_SISTEMAS", "periodo": "2026-2"}

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
