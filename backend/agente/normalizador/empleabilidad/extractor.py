"""Extractor CHH laboral con reglas versionadas y propuestas no publicables."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH
from agente.normalizador.empleabilidad.extractor_reglas import (
    ALIASES_HERRAMIENTAS,
    AREA_DEFAULTS,
    HERRAMIENTAS_REGLAS_PREFERIDAS,
    INFERENCIAS_HERRAMIENTA,
    INFORME_CAMPOS,
    REGLAS_LABORALES,
    REGLAS_VERSION,
    ReglaCHH,
    _regla,  # noqa: F401 - compatibility reexport
)


@dataclass(frozen=True, slots=True)
class CadenaCHH:
    """Cadena canónica con evidencia suficiente para auditoría posterior."""

    competencia: ConceptoCHH
    habilidad: ConceptoCHH
    herramienta: ConceptoCHH | None
    tipo: str
    evidencia: str
    confianza: float
    metodo: str
    regla: str

    def a_dict(self) -> dict[str, object]:
        """Serializa una cadena sin incluir texto completo de la fuente."""

        return {
            "competencia": self.competencia.a_dict(),
            "habilidad": self.habilidad.a_dict(),
            "herramienta": self.herramienta.a_dict() if self.herramienta else None,
            "tipo": self.tipo,
            "evidencia": self.evidencia,
            "confianza": self.confianza,
            "metodo": self.metodo,
            "regla": self.regla,
        }


@dataclass(frozen=True, slots=True)
class PropuestaHerramienta:
    """Herramienta inferible que requiere aceptación explícita o revisión LLM."""

    herramienta: ConceptoCHH
    evidencia: str
    confianza: float
    regla: str

    def a_dict(self) -> dict[str, object]:
        return {
            "herramienta": self.herramienta.a_dict(),
            "evidencia": self.evidencia,
            "confianza": self.confianza,
            "regla": self.regla,
        }


@dataclass(frozen=True, slots=True)
class ResultadoExtraccion:
    """Resultado CHH antes de crear relaciones físicas del grafo."""

    cadenas: tuple[CadenaCHH, ...]
    propuestas_herramienta: tuple[PropuestaHerramienta, ...]
    incidencias: tuple[dict[str, str], ...]

    def a_dict(self) -> dict[str, object]:
        return {
            "cadenas": [cadena.a_dict() for cadena in self.cadenas],
            "propuestas_herramienta": [
                propuesta.a_dict() for propuesta in self.propuestas_herramienta
            ],
            "incidencias": list(self.incidencias),
        }


def _clave_texto(texto: str) -> str:
    from agente.normalizador.empleabilidad.catalogo import clave_concepto

    return clave_concepto(texto)


def _herramientas_explicitas(
    texto: str,
    catalogo: CatalogoCHH,
) -> tuple[tuple[ConceptoCHH, tuple[int, int]], ...]:
    """Detecta herramientas solo cuando el nombre aparece en la fuente."""

    normalizado = _clave_texto(texto)
    encontrados: list[tuple[ConceptoCHH, tuple[int, int]]] = []
    ocupados: list[tuple[int, int]] = []
    candidatos: list[tuple[ConceptoCHH, str]] = [
        (herramienta, herramienta.nombre) for herramienta in catalogo.herramientas
    ]
    for alias, nombre in ALIASES_HERRAMIENTAS:
        herramienta = catalogo.obtener("herramienta", nombre)
        if herramienta is not None:
            candidatos.append((herramienta, alias))
    candidatos.sort(key=lambda item: len(_clave_texto(item[1])), reverse=True)
    for herramienta, nombre in candidatos:
        clave = _clave_texto(nombre)
        if len(clave) < 2:
            continue
        patron = rf"(?<![a-z0-9]){re.escape(clave)}(?![a-z0-9])"
        coincidencia = re.search(patron, normalizado)
        if coincidencia is None:
            continue
        span = coincidencia.span()
        if any(span[0] < otro[1] and otro[0] < span[1] for otro in ocupados):
            continue
        ocupados.append(span)
        encontrados.append((herramienta, span))
    return tuple(encontrados)


def _propuestas_herramienta(
    texto: str,
    catalogo: CatalogoCHH,
    explicitas: tuple[tuple[ConceptoCHH, tuple[int, int]], ...],
) -> tuple[PropuestaHerramienta, ...]:
    normalizado = _clave_texto(texto)
    ids_explicitos = {herramienta.id for herramienta, _ in explicitas}
    resultado: list[PropuestaHerramienta] = []
    for indice, (patron, nombre, evidencia, confianza) in enumerate(INFERENCIAS_HERRAMIENTA, 1):
        herramienta = catalogo.obtener("herramienta", nombre)
        if herramienta is None or herramienta.id in ids_explicitos:
            continue
        if re.search(patron, normalizado):
            resultado.append(
                PropuestaHerramienta(
                    herramienta,
                    evidencia,
                    confianza,
                    f"{REGLAS_VERSION}:HERR_INF_{indice:03d}",
                )
            )
    return tuple(resultado)


def extraer(
    texto: str,
    catalogo: CatalogoCHH,
    tipo: str = "exige",
    area: str = "",
) -> ResultadoExtraccion:
    """Extrae cadenas laborales deterministas y deja inferencias de herramienta aparte."""

    normalizado = _clave_texto(texto)
    explicitas = _herramientas_explicitas(texto, catalogo)
    coincidencias: list[tuple[ReglaCHH, re.Match[str]]] = []
    incidencias: list[dict[str, str]] = []
    for regla in REGLAS_LABORALES:
        coincidencia = re.search(regla.patron, normalizado)
        if coincidencia:
            coincidencias.append((regla, coincidencia))

    cadenas: list[CadenaCHH] = []
    vistos: set[tuple[str, str, str]] = set()
    for indice_coincidencia, (regla, coincidencia) in enumerate(coincidencias):
        competencia = catalogo.obtener("competencia", regla.competencia)
        habilidad = catalogo.obtener("habilidad", regla.habilidad)
        if competencia is None or habilidad is None:
            incidencias.append(
                {
                    "codigo": "REGLA_SIN_CONCEPTO_CANONICO",
                    "regla": regla.id,
                    "detalle": f"{regla.competencia} -> {regla.habilidad}",
                }
            )
            continue

        herramientas: Sequence[ConceptoCHH | None] = [None]
        if len(coincidencias) == 1:
            herramientas = [herramienta for herramienta, _ in explicitas]
            if not herramientas:
                herramientas = [None]
        else:
            preferidas = [
                herramienta
                for herramienta, _ in explicitas
                if regla.id in HERRAMIENTAS_REGLAS_PREFERIDAS.get(herramienta.nombre, frozenset())
            ]
            if preferidas:
                herramientas_cercanas = preferidas
            else:
                herramientas_cercanas = []
                for herramienta, span in explicitas:
                    distancias = [
                        abs(span[0] - otra_coincidencia.start())
                        for _, otra_coincidencia in coincidencias
                    ]
                    if (
                        distancias[indice_coincidencia] == min(distancias)
                        and distancias[indice_coincidencia] <= 140
                    ):
                        herramientas_cercanas.append(herramienta)
            herramientas = herramientas_cercanas
            if not herramientas:
                herramientas = [None]
        for herramienta_cadena in herramientas:
            clave = (
                competencia.id,
                habilidad.id,
                herramienta_cadena.id if herramienta_cadena else "",
            )
            if clave in vistos:
                continue
            vistos.add(clave)
            cadenas.append(
                CadenaCHH(
                    competencia,
                    habilidad,
                    herramienta_cadena,
                    tipo,
                    f"señal={coincidencia.group(0)}",
                    0.9 if herramienta_cadena is None else 0.95,
                    "regla_determinista",
                    f"{REGLAS_VERSION}:{regla.id}",
                )
            )

    if not cadenas and area:
        area_normalizada = _clave_texto(area)
        for indice, (patron, nombre_competencia, nombre_habilidad) in enumerate(AREA_DEFAULTS, 1):
            coincidencia_area = re.search(patron, area_normalizada)
            if coincidencia_area is None:
                continue
            competencia = catalogo.obtener("competencia", nombre_competencia)
            habilidad = catalogo.obtener("habilidad", nombre_habilidad)
            if competencia is None or habilidad is None:
                incidencias.append(
                    {
                        "codigo": "REGLA_AREA_SIN_CONCEPTO_CANONICO",
                        "regla": f"{REGLAS_VERSION}:AREA_{indice:03d}",
                        "detalle": f"{nombre_competencia} -> {nombre_habilidad}",
                    }
                )
                break
            cadenas.append(
                CadenaCHH(
                    competencia,
                    habilidad,
                    None,
                    tipo,
                    f"area={coincidencia_area.group(0)}",
                    0.72,
                    "regla_area_determinista",
                    f"{REGLAS_VERSION}:AREA_{indice:03d}",
                )
            )
            break

    propuestas = _propuestas_herramienta(texto, catalogo, explicitas)
    return ResultadoExtraccion(tuple(cadenas), propuestas, tuple(incidencias))


def extraer_informe(datos: dict[str, object], catalogo: CatalogoCHH) -> ResultadoExtraccion:
    """Convierte las columnas de evaluación en cadenas ``aplica`` auditables."""

    cadenas: list[CadenaCHH] = []
    incidencias: list[dict[str, str]] = []
    vistos: set[tuple[str, str]] = set()
    for campo, (nombre_competencia, nombre_habilidad, _) in INFORME_CAMPOS.items():
        valor = str(datos.get(campo, "") or "").strip().lower()
        if not valor or valor in {"-", "na", "n/a", "nan"}:
            continue
        competencia = catalogo.obtener("competencia", nombre_competencia)
        habilidad = catalogo.obtener("habilidad", nombre_habilidad)
        if competencia is None or habilidad is None:
            incidencias.append(
                {
                    "codigo": "CAMPO_INFORME_SIN_CONCEPTO_CANONICO",
                    "campo": campo,
                    "detalle": f"{nombre_competencia} -> {nombre_habilidad}",
                }
            )
            continue
        clave = (competencia.id, habilidad.id)
        if clave in vistos:
            continue
        vistos.add(clave)
        cadenas.append(
            CadenaCHH(
                competencia,
                habilidad,
                None,
                "aplica",
                f"campo={campo};valor={valor}",
                0.98,
                "campo_evaluacion_determinista",
                f"{REGLAS_VERSION}:INFORME_{campo.upper()}",
            )
        )

    funciones = " ".join(
        str(datos.get(campo, "") or "")
        for campo in (
            "funciones_iniciales",
            "funciones_finales",
            "compet_otros_1",
            "compet_otros_2",
        )
    )
    extraido = extraer(funciones, catalogo, tipo="aplica")
    return ResultadoExtraccion(
        tuple(cadenas) + extraido.cadenas,
        extraido.propuestas_herramienta,
        tuple(incidencias) + extraido.incidencias,
    )
