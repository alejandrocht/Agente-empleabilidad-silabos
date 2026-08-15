"""Pruebas offline del seam de contexto curricular por logro."""

from __future__ import annotations

import json

from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH, EjemploCHH
from agente.normalizador.silabos import analista_llm
from agente.normalizador.silabos.contexto_curricular import (
    construir_contexto_por_logro,
    construir_perfil_para_prompt,
)


def _catalogo(version: str = "catalogo-r1") -> CatalogoCHH:
    competencias = tuple(
        ConceptoCHH(f"COMP_{indice}", f"Competencia marketing {indice}", "marketing")
        for indice in range(6)
    )
    habilidades = tuple(
        ConceptoCHH(f"HAB_{indice}", f"Analizar marketing {indice}", "marketing")
        for indice in range(8)
    )
    herramientas = tuple(
        ConceptoCHH(f"HERR_{indice}", f"Herramienta marketing {indice}", "marketing")
        for indice in range(6)
    )
    ejemplos = {
        habilidad.id: (
            EjemploCHH(
                competencias[indice % len(competencias)],
                habilidad,
                herramientas[indice % len(herramientas)],
                "curricular",
            ),
        )
        for indice, habilidad in enumerate(habilidades)
    }
    return CatalogoCHH(
        competencias,
        habilidades,
        herramientas,
        ejemplos,
        origen=("test",),
        version=version,
    )


def _perfil(estado: str = "BORRADOR", revision: str = "r1") -> dict[str, object]:
    return {
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "estado": estado,
        "revision": revision,
        "dominios": ["investigación de mercados"],
        "reglas": ["Usar evidencia del sílabo."],
        "exclusiones": ["No inventar herramientas."],
        "contraejemplos": ["VPN financiera no es una herramienta de red."],
        "competencias_preferidas": ["Competencia no aprobada"],
        "aliases": {"marketing falso": "Alias no aprobado"},
        "ejemplos": [{"competencia": "Ejemplo no aprobado"}],
    }


def test_limita_candidatos_y_ejemplos_con_catalogo_vacio() -> None:
    contexto = construir_contexto_por_logro(
        {"logro": "Analizar marketing"},
        _catalogo(),
        _perfil(),
    )
    candidatos = contexto["candidatos"]
    assert isinstance(candidatos, dict)
    assert len(candidatos["competencia"]) == 4
    assert len(candidatos["habilidad"]) == 6
    assert len(candidatos["herramienta"]) == 4
    assert len(contexto["ejemplos"]) == 3

    vacio = CatalogoCHH((), (), (), {}, ("test",), "vacio")
    contexto_vacio = construir_contexto_por_logro({"logro": "Marketing"}, vacio, _perfil())
    candidatos_vacios = contexto_vacio["candidatos"]
    assert candidatos_vacios == {"competencia": [], "habilidad": [], "herramienta": []}
    assert contexto_vacio["ejemplos"] == []


def test_borrador_excluye_aliases_y_ejemplos_positivos() -> None:
    contexto = construir_contexto_por_logro({"logro": "Analizar marketing"}, _catalogo(), _perfil())
    referencia = contexto["perfil_referencia"]
    assert referencia.keys() == {"estado", "revision", "hash"}
    assert referencia["estado"] == "BORRADOR"
    assert "perfil" not in contexto
    serializado = json.dumps(contexto, ensure_ascii=False)
    assert "Alias no aprobado" not in serializado
    assert "Ejemplo no aprobado" not in serializado
    assert "Competencia no aprobada" not in serializado

    perfil_prompt = construir_perfil_para_prompt(_perfil())
    assert "aliases" not in perfil_prompt
    assert "ejemplos_positivos" not in perfil_prompt
    assert "competencias_preferidas" not in perfil_prompt
    assert perfil_prompt["dominios"] == ["investigación de mercados"]
    assert perfil_prompt["reglas"] == ["Usar evidencia del sílabo."]
    assert perfil_prompt["exclusiones"] == ["No inventar herramientas."]
    assert perfil_prompt["contraejemplos"] == ["VPN financiera no es una herramienta de red."]


def test_aprobado_incluye_contexto_positivo_solo_en_perfil_global() -> None:
    perfil = _perfil("APROBADO")
    contexto = construir_contexto_por_logro({"logro": "Analizar marketing"}, _catalogo(), perfil)
    assert contexto["perfil_referencia"].keys() == {"estado", "revision", "hash"}

    perfil_prompt = construir_perfil_para_prompt(perfil)
    assert perfil_prompt["competencias_preferidas"] == ["Competencia no aprobada"]
    assert perfil_prompt["aliases"] == {"marketing falso": "Alias no aprobado"}
    assert perfil_prompt["ejemplos_positivos"] == [{"competencia": "Ejemplo no aprobado"}]


def test_fingerprint_es_determinista_y_sensible_a_catalogo_y_perfil() -> None:
    caso = {"logro": "Analizar marketing", "curso": "Investigación"}
    primero = construir_contexto_por_logro(caso, _catalogo(), _perfil())
    segundo = construir_contexto_por_logro(caso, _catalogo(), _perfil())
    revision_nueva = construir_contexto_por_logro(caso, _catalogo(), _perfil(revision="r2"))
    catalogo_nuevo = construir_contexto_por_logro(caso, _catalogo("catalogo-r2"), _perfil())

    assert primero["fingerprint"] == segundo["fingerprint"]
    assert primero["fingerprint"] != revision_nueva["fingerprint"]
    assert primero["fingerprint"] != catalogo_nuevo["fingerprint"]
    assert analista_llm._clave_lote(
        ({"contexto_recuperado": primero},), _perfil(), "modelo-prueba"
    ) != analista_llm._clave_lote(
        ({"contexto_recuperado": catalogo_nuevo},), _perfil(), "modelo-prueba"
    )
