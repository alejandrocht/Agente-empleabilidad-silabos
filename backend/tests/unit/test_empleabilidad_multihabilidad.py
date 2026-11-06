"""Cobertura de extracción múltiple, citas verificables y aislamiento por función."""

import csv
import json
from pathlib import Path

import pytest

from agente.normalizador.empleabilidad.analista_habilidades import (
    AnalistaHabilidades,
    DecisionHabilidades,
    DecisionReferencias,
    EleccionHabilidad,
    ErrorAnalisisHabilidades,
    ReferenciaHabilidad,
    VeredictoHabilidad,
    VerificacionHabilidades,
    aplicar_verificacion,
    validar_selecciones,
)
from agente.normalizador.empleabilidad.hab_tec_retriever import HabTecMatch
from agente.normalizador.empleabilidad.pipeline import normalizar_staging
from agente.normalizador.modelos import ResultadoValidacionEntrada

H1 = HabTecMatch("H1", "Economía", "Análisis financiero", "Analizar estados financieros", 0.9)
H2 = HabTecMatch("H2", "Economía", "Presupuestos", "Elaborar presupuestos", 0.8)
FUNCIONES = "Analizar estados financieros. Elaborar presupuestos."


def test_verificacion_descarta_afinidad_y_exige_veredictos_completos():
    referencias = DecisionReferencias(
        selecciones=[
            ReferenciaHabilidad(candidato=0, funcion=0),
            ReferenciaHabilidad(candidato=1, funcion=1),
        ]
    )
    verificacion = VerificacionHabilidades(
        verificaciones=[
            VeredictoHabilidad(seleccion=0, sustentada=True),
            VeredictoHabilidad(seleccion=1, sustentada=False),
        ]
    )
    assert (
        aplicar_verificacion(referencias, verificacion).selecciones == referencias.selecciones[:1]
    )
    with pytest.raises(ErrorAnalisisHabilidades):
        aplicar_verificacion(referencias, VerificacionHabilidades(verificaciones=[]))


def test_copia_evidencia_de_la_fuente_y_cachea_solo_decisiones_verificadas(tmp_path, monkeypatch):
    from agente.normalizador.empleabilidad import analista_habilidades as modulo

    llamadas = []

    class Runnable:
        def __init__(self, schema):
            self.schema = schema

        def invoke(self, mensajes):
            llamadas.append(self.schema)
            if self.schema is DecisionReferencias:
                return DecisionReferencias(
                    selecciones=[
                        ReferenciaHabilidad(candidato=0, funcion=0),
                        ReferenciaHabilidad(candidato=1, funcion=1),
                    ]
                )
            return VerificacionHabilidades(
                verificaciones=[
                    VeredictoHabilidad(seleccion=0, sustentada=True),
                    VeredictoHabilidad(seleccion=1, sustentada=False),
                ]
            )

    class Cliente:
        model_name = "modelo-prueba"
        openai_api_base = "http://unused"

        def with_structured_output(self, schema, **kwargs):
            return Runnable(schema)

    monkeypatch.setattr(modulo, "build_chat_openai", lambda profile: Cliente())
    analista = AnalistaHabilidades(tmp_path)
    primera = analista.seleccionar(FUNCIONES, "Economía", (H1, H2))
    segunda = analista.seleccionar(FUNCIONES, "Economía", (H1, H2))
    assert primera == segunda
    assert len(primera) == 1
    assert primera[0].evidencia == "Analizar estados financieros."
    assert len(llamadas) == 2


@pytest.mark.parametrize(
    "eleccion",
    [
        EleccionHabilidad(candidato=9, evidencia="Analizar estados financieros"),
        EleccionHabilidad(candidato=0, evidencia="Realizar auditorías contables"),
        EleccionHabilidad(candidato=0, evidencia="financieros"),
    ],
)
def test_rechaza_referencias_y_evidencia_inventadas(eleccion):
    with pytest.raises(ErrorAnalisisHabilidades):
        validar_selecciones(DecisionHabilidades(selecciones=[eleccion]), (H1, H2), FUNCIONES)


def test_reintenta_referencia_inexistente_sin_convertirla_silenciosamente(tmp_path, monkeypatch):
    from agente.normalizador.empleabilidad import analista_habilidades as modulo

    llamadas = []

    class Cliente:
        model_name = "modelo-prueba"
        openai_api_base = "http://unused"

        def with_structured_output(self, schema, **kwargs):
            class Runnable:
                def invoke(self, mensajes):
                    llamadas.append(schema)
                    if schema is DecisionReferencias:
                        funcion = 99 if len(llamadas) == 1 else 0
                        return DecisionReferencias(
                            selecciones=[ReferenciaHabilidad(candidato=0, funcion=funcion)]
                        )
                    return VerificacionHabilidades(
                        verificaciones=[
                            VeredictoHabilidad(seleccion=0, sustentada=True)
                        ]
                    )

            return Runnable()

    monkeypatch.setattr(modulo, "build_chat_openai", lambda profile: Cliente())
    resultado = AnalistaHabilidades(tmp_path).seleccionar(FUNCIONES, "Economía", (H1,))
    assert len(llamadas) == 3
    assert resultado[0].evidencia == "Analizar estados financieros."


def test_acepta_cero_y_varias_habilidades_sin_repetir_ids():
    assert validar_selecciones(DecisionHabilidades(selecciones=[]), (H1,), FUNCIONES) == ()
    decision = DecisionHabilidades(
        selecciones=[
            EleccionHabilidad(candidato=0, evidencia="Analizar estados financieros"),
            EleccionHabilidad(candidato=1, evidencia="Elaborar presupuestos"),
            EleccionHabilidad(candidato=0, evidencia="Analizar estados financieros"),
        ]
    )
    assert [
        s.candidato.id_habilidad for s in validar_selecciones(decision, (H1, H2), FUNCIONES)
    ] == ["H1", "H2"]


def test_pipeline_recupera_por_funcion_y_conserva_varias_habilidades(tmp_path: Path):
    consultas = []

    class Retriever:
        def buscar(self, texto, carrera, *, sin_limite=False):
            assert sin_limite
            consultas.append(texto)
            assert carrera == "Economía"
            assert "Director" not in texto
            return (H1,) if "financieros" in texto else (H2,)

    class Analista:
        def seleccionar(self, funciones, carrera, candidatos):
            assert len(candidatos) == 2
            decision = DecisionHabilidades(
                selecciones=[
                    EleccionHabilidad(candidato=0, evidencia="Analizar estados financieros"),
                    EleccionHabilidad(candidato=1, evidencia="Elaborar presupuestos"),
                ]
            )
            return validar_selecciones(decision, candidatos, funciones)

    (tmp_path / "limpios").mkdir()
    registro = {
        "id_registro": "fila_1",
        "datos": {
            "identificacion": "123",
            "ruc": "20100000000",
            "razon_social": "Empresa",
            "cargo": "Director",
            "carrera_resumen": "Economía",
            "funciones": FUNCIONES
            + (" Analizar estados financieros. Otras funciones inherentes al puesto."),
        },
    }
    (tmp_path / "limpios/publicaciones.jsonl").write_text(json.dumps(registro), encoding="utf-8")
    resultado = normalizar_staging(
        tmp_path,
        ResultadoValidacionEntrada("fuente.xlsx", "hash", True, (), ()),
        hab_tec_retriever=Retriever(),
        analista_habilidades=Analista(),
    )
    assert resultado.publicable
    assert resultado.relaciones == 2
    assert len(consultas) == 3
    with (tmp_path / "salidas/requerimiento_laboral.csv").open(encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f))
    assert {r["id_habilidad"] for r in filas} == {"H1", "H2"}
    assert {r["id_oferta_laboral"] for r in filas} == {"LAB_123"}


def test_fallo_del_analista_no_se_convierte_en_coincidencia_aceptada(tmp_path: Path):
    class Retriever:
        def buscar(self, *args, **kwargs):
            return (H1,)

    class Analista:
        def seleccionar(self, *args):
            raise ErrorAnalisisHabilidades("Error del modelo")

    (tmp_path / "limpios").mkdir()
    (tmp_path / "limpios/publicaciones.jsonl").write_text(
        json.dumps(
            {
                "datos": {
                    "ruc": "20100000000",
                    "razon_social": "Empresa",
                    "cargo": "Analista",
                    "carrera_resumen": "Economía",
                    "funciones": FUNCIONES,
                }
            }
        ),
        encoding="utf-8",
    )
    resultado = normalizar_staging(
        tmp_path,
        ResultadoValidacionEntrada("fuente.xlsx", "hash", True, (), ()),
        hab_tec_retriever=Retriever(),
        analista_habilidades=Analista(),
    )
    assert resultado.relaciones == 0
    assert any(h.codigo == "HAB_TEC_ANALISIS_ERROR" for h in resultado.hallazgos)
