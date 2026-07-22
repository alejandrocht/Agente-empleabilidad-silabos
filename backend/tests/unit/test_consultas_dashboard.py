"""Contratos puros del catálogo fijo del dashboard."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agente.dashboard.consultas_empresas import _LIDERAZGO_REGEX
from agente.dashboard.consultas_estrategicas import (
    CONSULTAS_ESTRATEGICAS,
    todas_las_consultas_estrategicas,
)
from scripts.ejecutar_consultas_estrategicas import preparar_parametros


def _params(slug: str) -> dict[str, str]:
    valores = {
        "carrera_id": "CAR_1",
        "facultad_id": "FAC_1",
        "industria_id": "INDU_1",
        "empresa_a_id": "EMP_A",
        "empresa_b_id": "EMP_B",
        "tipo_conocimiento": "competencia",
        "desde": "2025-01-01T00:00:00Z",
        "hasta": "2026-01-01T00:00:00Z",
    }
    consulta = CONSULTAS_ESTRATEGICAS[slug]
    return {clave: valores[clave] for clave in consulta.parametros_especificos}


def test_catalogo_tiene_doce_slugs_y_cuatro_por_seccion() -> None:
    consultas = todas_las_consultas_estrategicas()
    assert len(consultas) == 12
    assert len({consulta.slug for consulta in consultas}) == 12
    assert {
        seccion: sum(consulta.seccion == seccion for consulta in consultas)
        for seccion in {consulta.seccion for consulta in consultas}
    } == {"Panorama laboral": 4, "Alineación curricular": 4, "Empresas y funciones": 4}


def test_generales_no_tienen_parametros_y_especificas_declaran_referencias_exactas() -> None:
    for consulta in todas_las_consultas_estrategicas():
        assert re.search(r"\$[A-Za-z_]", consulta.cypher_general) is None
        referencias = set(re.findall(r"\$([A-Za-z_]\w*)", consulta.cypher_especifica))
        assert referencias == set(consulta.parametros_especificos)


def test_salidas_estan_separadas_y_no_usan_support_n_ambiguo() -> None:
    for consulta in todas_las_consultas_estrategicas():
        assert consulta.salidas_general
        assert consulta.salidas_especifica
        assert "support_n" not in consulta.salidas_general
        assert "support_n" not in consulta.salidas_especifica


def test_limites_del_catalogo_son_acotados() -> None:
    for consulta in todas_las_consultas_estrategicas():
        assert consulta.limite_general <= 20
        assert consulta.limite_especifico <= 20


@pytest.mark.parametrize("tipo", ["", "conocimiento", "COMPETENCIA", "otro"])
def test_runner_rechaza_tipo_conocimiento_fuera_del_enum(tipo: str) -> None:
    consulta = CONSULTAS_ESTRATEGICAS["cobertura_curricular"]
    with pytest.raises(ValueError, match="tipo_conocimiento"):
        preparar_parametros(
            consulta,
            "especifica",
            {"carrera_id": "CAR_1", "tipo_conocimiento": tipo},
        )


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [
        ("fecha", "2026-01-01T00:00:00Z"),
        ("2026-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
        ("2025-01-01T00:00:00Z", "2026-10-02T00:00:00Z"),
        ("2025-01-31T00:00:00Z", "2026-09-30T00:00:00Z"),
    ],
)
def test_runner_rechaza_rangos_invalidos(desde: str, hasta: str) -> None:
    consulta = CONSULTAS_ESTRATEGICAS["industrias_por_carrera"]
    with pytest.raises(ValueError):
        preparar_parametros(
            consulta,
            "especifica",
            {"carrera_id": "CAR_1", "desde": desde, "hasta": hasta},
        )


def test_runner_rechaza_ids_vacios_y_comparar_la_misma_empresa() -> None:
    consulta_industrias = CONSULTAS_ESTRATEGICAS["industrias_por_carrera"]
    with pytest.raises(ValueError, match="string no vacío"):
        preparar_parametros(
            consulta_industrias,
            "especifica",
            {
                "carrera_id": " ",
                "desde": "2025-01-01T00:00:00Z",
                "hasta": "2026-01-01T00:00:00Z",
            },
        )

    consulta_empresas = CONSULTAS_ESTRATEGICAS["diferenciadores_empresas"]
    parametros = _params("diferenciadores_empresas")
    parametros["empresa_b_id"] = parametros["empresa_a_id"]
    with pytest.raises(ValueError, match="deben ser distintos"):
        preparar_parametros(consulta_empresas, "especifica", parametros)


def test_alineacion_declara_estados_por_dimension_y_sin_mercado() -> None:
    cobertura = CONSULTAS_ESTRATEGICAS["cobertura_curricular"].cypher_especifica
    assert "'incomplete'" in cobertura
    assert "coberturas_dimension = 0" in cobertura
    assert "is_comparable" in cobertura

    for slug in (
        "brechas_demanda_alta",
        "senales_revision_vigencia",
        "cursos_con_mayor_correspondencia",
    ):
        cypher = CONSULTAS_ESTRATEGICAS[slug].cypher_especifica
        assert "'no_market_data'" in cypher
        assert "ELSE null" in cypher


def test_brecha_combina_demanda_y_curriculo_sin_excluir_cobertura_cero() -> None:
    brecha = CONSULTAS_ESTRATEGICAS["brechas_demanda_alta"]
    for cypher in (brecha.cypher_general, brecha.cypher_especifica):
        assert "cursos_cobertura > 0" not in cypher
        assert "EXISTS {" in cypher
        assert "o_demanda:Oferta_Laboral" in cypher

    vigencia = CONSULTAS_ESTRATEGICAS["senales_revision_vigencia"].cypher_especifica
    inicio = vigencia.index("OPTIONAL MATCH (x)")
    fin = vigencia.index("OPTIONAL MATCH (x)-[:REQUIERE]", inicio)
    assert "OR EXISTS" not in vigencia[inicio:fin]


def test_comparabilidad_macro_es_independiente_por_dimension() -> None:
    consulta = CONSULTAS_ESTRATEGICAS["cobertura_curricular"]
    assert {
        "competencia_comparable",
        "habilidad_comparable",
        "herramienta_comparable",
    } <= set(consulta.salidas_general)
    assert "has_any_comparable_dimension" in consulta.salidas_general


def test_texto_publico_no_contiene_reemplazos_utf8_corruptos() -> None:
    corrupto = re.compile(r"[A-Za-zÀ-ɏ]\?[A-Za-zÀ-ɏ]")
    for consulta in todas_las_consultas_estrategicas():
        textos = (
            consulta.pregunta,
            consulta.definicion_medible,
            consulta.limitacion_semantica,
            consulta.metrica_principal,
            consulta.granularidad_general,
            consulta.granularidad_especifica,
        )
        assert all(corrupto.search(texto) is None for texto in textos)
        assert corrupto.search(consulta.cypher_general) is None
        assert corrupto.search(consulta.cypher_especifica) is None

    raiz_backend = Path(__file__).parents[2]
    archivos_publicos = [
        raiz_backend.parent / "PLAN_DASHBOARD_TENDENCIAS.md",
        raiz_backend / "scripts" / "ejecutar_consultas_estrategicas.py",
        *(raiz_backend / "src" / "agente" / "dashboard").glob("*.py"),
    ]
    for archivo in archivos_publicos:
        contenido = archivo.read_text(encoding="utf-8")
        assert not any(marca in contenido for marca in ("\u00c3", "\u00c2", "\ufffd"))


def test_consultas_corregidas_exponen_su_semantica_estatica() -> None:
    tendencia = CONSULTAS_ESTRATEGICAS["tendencia_ofertas"]
    assert "UNWIND meses" in tendencia.cypher_general
    assert "CASE WHEN fecha_corte IS NULL THEN [null]" in tendencia.cypher_general
    assert "UNWIND range(0, 19)" in tendencia.cypher_especifica
    assert "'no_data'" in tendencia.cypher_especifica

    diferenciadores = CONSULTAS_ESTRATEGICAS["diferenciadores_empresas"]
    assert "difference_pp > 0" in diferenciadores.cypher_especifica
    assert "denominator_n >= 5" in diferenciadores.cypher_general

    liderazgo = CONSULTAS_ESTRATEGICAS["conocimientos_liderazgo"]
    assert "manager" not in liderazgo.cypher_general.casefold()
    assert "head of" in liderazgo.cypher_general.casefold()
    assert re.fullmatch(_LIDERAZGO_REGEX, "ASISTENTE DE DIRECTORIO") is None
    assert re.fullmatch(_LIDERAZGO_REGEX, "DIRECTOR DE OPERACIONES") is not None

    funciones = CONSULTAS_ESTRATEGICAS["funciones_por_tipo_empresa"]
    for cypher in (funciones.cypher_general, funciones.cypher_especifica):
        assert "trim(p.nombre) <> ''" in cypher
        assert "[0..4]" in cypher
        assert "[0..5]" in cypher


def test_plantillas_temporales_protegen_fecha_corte_vacia() -> None:
    assert "fecha_corte IS NULL" in CONSULTAS_ESTRATEGICAS["tendencia_ofertas"].cypher_general
    for slug in (
        "conocimientos_mas_demandados",
        "brechas_demanda_alta",
        "empresas_y_conocimientos",
        "diferenciadores_empresas",
    ):
        assert "fecha_corte IS NOT NULL" in CONSULTAS_ESTRATEGICAS[slug].cypher_general
