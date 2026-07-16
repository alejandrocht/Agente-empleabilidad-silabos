"""Auditoría del reconocimiento, parámetros y render de las veinte plantillas."""

from __future__ import annotations

from agente.plantillas import motor
from agente.plantillas.catalogo import PLANTILLAS
from agente.plantillas.motor import buscar_intencion, buscar_plantilla, renderizar


def test_catalogo_contiene_veinte_plantillas() -> None:
    assert len(PLANTILLAS) == 20
    assert len({plantilla["id"] for plantilla in PLANTILLAS}) == 20


def test_pregunta_sin_parametros_selecciona_plantilla() -> None:
    assert buscar_plantilla("¿Cuántas carreras hay?", [])["id"] == "contar_carreras"
    assert buscar_plantilla("?Cu?ntas carreras hay?", [])["id"] == "contar_carreras"


def test_plantilla_parametrizada_exige_entidad() -> None:
    assert buscar_plantilla("cursos de sistemas", []) is None
    assert buscar_intencion("cursos de sistemas")["id"] == "cursos_de_carrera"


def test_pregunta_especifica_no_activa_plantilla_general() -> None:
    pregunta = "Top empresas con más ofertas dirigidas a Derecho"
    assert buscar_intencion(pregunta) is None


def test_render_usa_id_real() -> None:
    entidad = [{"label": "Carrera", "id": "CAR_1", "nombre": "Sistemas"}]
    plantilla = buscar_plantilla("cursos de sistemas", entidad)

    cypher = renderizar(plantilla, entidad)

    assert "CAR_1" in cypher
    assert ":ENSENIA" in cypher
    assert "{id_carrera}" not in cypher


def test_resolver_parametro_sin_llm(monkeypatch) -> None:
    plantilla = buscar_intencion("cuantas ofertas laborales publico EVENTIVA S.A.C.")
    monkeypatch.setattr(
        motor,
        "introspeccionar_schema",
        lambda: {
            "name_props": {"Empresa": "nombre"},
            "props": {"Empresa": ["id_empresa", "nombre"]},
        },
    )
    monkeypatch.setattr(
        motor,
        "_ejecutar_resolucion",
        lambda _cypher, params: (
            [{"nombre": "EVENTIVA S.A.C.", "id": "EMP_1"}]
            if params["terminos"] == ["eventiva"]
            else []
        ),
    )

    entidades = motor.resolver_entidades(
        plantilla, "cuantas ofertas laborales publico EVENTIVA S.A.C.", []
    )

    assert entidades[0]["id"] == "EMP_1"
