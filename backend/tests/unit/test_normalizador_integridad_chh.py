"""Tests for deterministic CHH graph invariants."""

from __future__ import annotations

from agente.normalizador.silabos.integridad_chh import validar_integridad_chh
from agente.normalizador.silabos.salida import evaluar_release_gate


def _paquete(*, herramienta: bool = False) -> dict[str, list[dict[str, str]]]:
    return {
        "catalogo_competencias.csv": [
            {
                "id_competencia": "COMP_1",
                "nombre_competencia": "Gestionar campañas",
            }
        ],
        "catalogo_logros.csv": [
            {
                "id_logro": "LOGRO_1",
                "nombre_logro": "Analizar campañas",
                "descripcion_breve": "Capacidad para analizar campañas.",
            }
        ],
        "catalogo_herramientas.csv": (
            [{"id_herramienta": "HERR_1", "nombre_herramienta": "CRM"}] if herramienta else []
        ),
        "cobertura_curricular.csv": [],
    }


def test_grafo_chh_valido_con_herramienta_opcional() -> None:
    paquete = _paquete()
    relaciones = {("CUR_1", "SIL_1", "COMP_1", "LOGRO_1", "")}

    assert validar_integridad_chh(paquete, relaciones) == ()


def test_logro_debe_tener_competencia_pero_competencia_puede_ser_sola() -> None:
    paquete = _paquete()

    hallazgos = validar_integridad_chh(paquete, set())

    assert {hallazgo.codigo for hallazgo in hallazgos} == {"LOGRO_SIN_COMPETENCIA"}


def test_competencia_sola_no_se_bloquea_por_logro_de_otro_paquete() -> None:
    paquete = _paquete()
    paquete["catalogo_competencias.csv"].append(
        {"id_competencia": "COMP_2", "nombre_competencia": "Otra competencia"}
    )

    hallazgos = validar_integridad_chh(
        paquete,
        {("CUR_2", "SIL_2", "COMP_2", "LOGRO_1", "")},
    )

    assert hallazgos == ()


def test_herramienta_debe_tener_cadena_competencia_logro() -> None:
    paquete = _paquete(herramienta=True)
    relaciones = {("CUR_1", "SIL_1", "COMP_1", "LOGRO_1", "")}

    hallazgos = validar_integridad_chh(paquete, relaciones)

    assert [hallazgo.codigo for hallazgo in hallazgos] == ["HERRAMIENTA_SIN_CADENA_CHH"]


def test_relacion_puede_omitir_logro_pero_no_competencia() -> None:
    """Una competencia genérica o específica cubre el curso sin logro asociado."""

    paquete = _paquete()

    sin_logro = validar_integridad_chh(
        paquete,
        {("CUR_1", "SIL_1", "COMP_1", "", "")},
    )
    sin_competencia = validar_integridad_chh(
        paquete,
        {("CUR_1", "SIL_1", "", "LOGRO_1", "")},
    )

    assert all(hallazgo.codigo != "RELACION_CHH_INCOMPLETA" for hallazgo in sin_logro)
    assert any(hallazgo.codigo == "RELACION_CHH_INCOMPLETA" for hallazgo in sin_competencia)


def test_relacion_conserva_origen_y_competencia() -> None:
    paquete = _paquete()

    hallazgos = validar_integridad_chh(
        paquete,
        {("", "", "COMP_1", "LOGRO_1", "")},
    )

    assert any(
        hallazgo.codigo == "RELACION_CHH_INCOMPLETA"
        and hallazgo.fila == 1
        and hallazgo.severidad == "error"
        for hallazgo in hallazgos
    )


def test_release_gate_expone_y_bloquea_invariante_chh() -> None:
    paquete = _paquete(herramienta=True)
    gate = evaluar_release_gate(
        carrera="FINANZAS",
        periodo="2026-1",
        registros=1,
        logros_fuente=1,
        filas_por_archivo=paquete,
        competencias_fuente=[{"id_competencia_canonica": "COMP_1"}],
        habilidades_fuente=[{"id_habilidad_canonica": "LOGRO_1"}],
        herramientas_fuente=[{"id_herramienta_canonica": "HERR_1"}],
        relaciones_canonicas={("CUR_1", "SIL_1", "COMP_1", "LOGRO_1", "")},
        pendientes=[],
        hallazgos=[],
    )

    assert gate["decision"] == "BLOCK_IMPORT"
    assert "CHH_GRAPH_INVALID" in gate["blockers"]
    assert gate["checks"]["chh_graph"]["ok"] is False
