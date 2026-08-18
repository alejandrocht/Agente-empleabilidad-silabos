"""Contexto curricular recuperado y auditable para cada logro."""

from __future__ import annotations

import hashlib
import json
from typing import cast

from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH

CHH_OUTPUT_TYPES = ("competencia", "habilidad", "herramienta")

_VERSION_CONTEXTO = "contexto-curricular/v2"
_LIMITES_CANDIDATOS = {
    "competencia": 4,
    "habilidad": 6,
    "herramienta": 4,
}
_LIMITE_EJEMPLOS = 3


def construir_contexto_por_logro(
    caso: dict[str, object],
    catalogo: CatalogoCHH,
    perfil: dict[str, object],
) -> dict[str, object]:
    """Construye el único contexto recuperado que ve el LLM para un logro.

    Los candidatos del catálogo son sugerencias trazables, no una restricción
    para el sílabo. La curación sin aprobación humana se limita a reglas
    defensivas: nunca incorpora aliases ni ejemplos positivos.
    """

    consulta = _consulta(caso)
    recuperados = catalogo.buscar(consulta, limite=max(_LIMITES_CANDIDATOS.values()))
    candidatos = {
        tipo: [_candidato_dict(concepto, tipo) for concepto in recuperados.get(tipo, ())[:limite]]
        for tipo, limite in _LIMITES_CANDIDATOS.items()
    }
    contexto: dict[str, object] = {
        "version_contexto": _VERSION_CONTEXTO,
        "catalogo": {"version": catalogo.version},
        "perfil_referencia": _perfil_referencia(perfil),
        "taxonomia": {"tipos_salida": list(CHH_OUTPUT_TYPES)},
        "regla": (
            "Las únicas salidas curriculares son Competencia, Habilidad y Herramienta. "
            "Los candidatos son sugerencias recuperadas, no decisiones aprobadas. "
            "Puedes proponer un concepto nuevo solo con evidencia explícita del sílabo."
        ),
        "candidatos": candidatos,
        "ejemplos": [
            ejemplo.a_dict() for ejemplo in catalogo.ejemplos(consulta, limite=_LIMITE_EJEMPLOS)
        ],
        "proveniencia": _proveniencia(caso, perfil, catalogo),
    }
    contexto["fingerprint"] = _fingerprint(contexto)
    return contexto


def _consulta(caso: dict[str, object]) -> str:
    return " ".join(
        str(caso.get(campo) or "")
        for campo in (
            "logro",
            "curso",
            "sumilla",
            "logro_general",
            "contenido_relacionado",
        )
    )


def _candidato_dict(concepto: ConceptoCHH, tipo: str) -> dict[str, str]:
    """Añade el tipo CHH de la colección, aunque el CSV no lo declare."""

    resultado = dict(concepto.a_dict())
    resultado["tipo"] = tipo
    return resultado


def _proveniencia(
    caso: dict[str, object],
    perfil: dict[str, object],
    catalogo: CatalogoCHH,
) -> dict[str, object]:
    """Expone procedencia compacta sin enviar rutas locales al LLM."""

    campos_fuente = (
        "curso",
        "sumilla",
        "logro_general",
        "logro",
        "contenido_relacionado",
        "evidencia_herramientas",
    )
    secciones = [campo for campo in campos_fuente if caso.get(campo)]
    resultado: dict[str, object] = {
        "universidad": str(perfil.get("universidad") or "Universidad de Lima"),
        "carrera": str(perfil.get("carrera") or ""),
        "periodo": str(perfil.get("periodo") or ""),
        "id_silabo": _texto_corto(caso.get("id_silabo")),
        "id_curso": _texto_corto(caso.get("id_curso")),
        "secciones_fuente": secciones,
        "catalogo_version": catalogo.version,
    }
    return {clave: valor for clave, valor in resultado.items() if valor not in ("", [])}


def _texto_corto(valor: object, limite: int = 120) -> str:
    """Evita que identificadores o metadatos de origen arrastren rutas locales."""

    texto = str(valor or "").replace("\\", "/").split("/")[-1]
    return texto[:limite]


def construir_perfil_para_prompt(perfil: dict[str, object]) -> dict[str, object]:
    """Reduce el perfil a la política que viaja una vez por prompt."""

    return _perfil_contextual(perfil)


def _perfil_referencia(perfil: dict[str, object]) -> dict[str, str]:
    perfil_contextual = _perfil_contextual(perfil)
    return {clave: str(perfil_contextual[clave]) for clave in ("estado", "revision", "hash")}


def _perfil_contextual(perfil: dict[str, object]) -> dict[str, object]:
    estado = str(perfil.get("estado") or "BORRADOR").upper()
    if estado not in {"APROBADO", "BORRADOR"}:
        estado = "BORRADOR"
    resultado: dict[str, object] = {
        "carrera": str(perfil.get("carrera") or ""),
        "periodo": str(perfil.get("periodo") or ""),
        "estado": estado,
        "revision": str(perfil.get("revision") or perfil.get("periodo") or "sin_revision"),
        "hash": _fingerprint(perfil),
        "dominios": _lista(perfil.get("dominios")),
        "reglas": _lista(perfil.get("reglas")),
        "exclusiones": _lista(perfil.get("exclusiones")),
        "contraejemplos": _lista(perfil.get("contraejemplos")),
        "habilidades_evitar": _lista(perfil.get("habilidades_evitar")),
    }
    if estado == "APROBADO":
        resultado["competencias_preferidas"] = _lista(perfil.get("competencias_preferidas"))
        resultado["aliases"] = _coleccion(perfil.get("aliases"))
        resultado["ejemplos_positivos"] = _coleccion(perfil.get("ejemplos"))
    return resultado


def _lista(valor: object) -> list[object]:
    return list(valor) if isinstance(valor, list) else []


def _coleccion(valor: object) -> dict[str, object] | list[object]:
    if isinstance(valor, dict):
        return cast(dict[str, object], valor)
    return _lista(valor)


def _fingerprint(valor: object) -> str:
    payload = json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
