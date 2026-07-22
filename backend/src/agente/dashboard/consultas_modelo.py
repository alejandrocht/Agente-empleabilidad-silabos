"""Contrato tipado de los datasets fijos del dashboard estratégico."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConsultaEstrategica:
    """Describe una pregunta de producto y sus vistas macro y de detalle."""

    seccion: str
    slug: str
    pregunta: str
    definicion_medible: str
    limitacion_semantica: str
    cypher_general: str
    cypher_especifica: str
    parametros_especificos: tuple[str, ...]
    granularidad_general: str
    granularidad_especifica: str
    metrica_principal: str
    limite_general: int
    limite_especifico: int
    chart_hint: str
    requiere_curricula: bool
    salidas_general: tuple[str, ...]
    salidas_especifica: tuple[str, ...]

    @property
    def categoria(self) -> str:
        """Alias compatible con el catálogo anterior."""

        return self.seccion

    @property
    def pregunta_original(self) -> str:
        """Alias compatible con el runner anterior."""

        return self.pregunta

    @property
    def pregunta_medible(self) -> str:
        """Alias compatible con el runner anterior."""

        return self.definicion_medible


def consulta(
    *,
    seccion: str,
    slug: str,
    pregunta: str,
    definicion_medible: str,
    limitacion_semantica: str,
    cypher_general: str,
    cypher_especifica: str,
    parametros_especificos: tuple[str, ...],
    granularidad_general: str,
    granularidad_especifica: str,
    metrica_principal: str,
    limite_general: int,
    limite_especifico: int,
    chart_hint: str,
    requiere_curricula: bool,
    salidas_general: tuple[str, ...],
    salidas_especifica: tuple[str, ...],
) -> ConsultaEstrategica:
    """Normaliza texto Cypher al construir una consulta del catálogo."""

    return ConsultaEstrategica(
        seccion=seccion,
        slug=slug,
        pregunta=pregunta,
        definicion_medible=definicion_medible,
        limitacion_semantica=limitacion_semantica,
        cypher_general=cypher_general.strip(),
        cypher_especifica=cypher_especifica.strip(),
        parametros_especificos=parametros_especificos,
        granularidad_general=granularidad_general,
        granularidad_especifica=granularidad_especifica,
        metrica_principal=metrica_principal,
        limite_general=limite_general,
        limite_especifico=limite_especifico,
        chart_hint=chart_hint,
        requiere_curricula=requiere_curricula,
        salidas_general=salidas_general,
        salidas_especifica=salidas_especifica,
    )
